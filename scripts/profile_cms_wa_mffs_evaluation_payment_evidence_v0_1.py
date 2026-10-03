"""
profile_cms_wa_mffs_evaluation_payment_evidence_v0_1.py

WCFFBP
CMS Washington MFFS Evaluation Payment Evidence Profiler v0.1

Purpose
-------
Extract payment-related evidence from the five locally certified
Washington MFFS evaluation reports.

This is an EVIDENCE profiler, not a ledger calculator.

It distinguishes:
    EXPLICIT_PAID_OR_MADE
    EXPLICIT_ISSUED
    EXPLICIT_DETERMINED
    EXPLICIT_CUMULATIVE
    GROSS_NET_RECONCILIATION
    PENDING
    CONTEXT_ONLY

It preserves:
    document
    page number
    matched phrase
    dollar strings
    paragraph/context

It does NOT:
    infer that every dollar near "performance payment" is a payment;
    infer cash timing from determination timing;
    calculate DY allocations;
    add anything to Original Medicare/FFS;
    write to PostgreSQL;
    authorize ledger inclusion.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_mffs"
    / "washington"
    / "evaluation_reports"
    / "v0_1"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_mffs"
    / "washington"
    / "evaluation_reports"
    / "validation"
    / "payment_evidence_v0_1"
)

EVIDENCE_CSV = (
    OUTPUT_DIR
    / "cms_wa_mffs_evaluation_payment_evidence_v0_1.csv"
)

DOCUMENT_CSV = (
    OUTPUT_DIR
    / "cms_wa_mffs_evaluation_payment_document_profile_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_wa_mffs_evaluation_payment_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_wa_mffs_evaluation_payment_report_v0_1.txt"
)


@dataclass(frozen=True)
class Document:
    slot: str
    ordinal: int


DOCUMENTS = [
    Document("EVAL_01_FIRST", 1),
    Document("EVAL_02_SECOND", 2),
    Document("EVAL_03_THIRD", 3),
    Document("EVAL_04_FOURTH", 4),
    Document("EVAL_05_FIFTH", 5),
]


PATTERNS = [
    (
        "EXPLICIT_PAID_OR_MADE",
        re.compile(
            r"""
            (?:
                performance\s+payments?
                .{0,160}?
                (?:
                    made\s+to
                    |
                    paid\s+to
                    |
                    paid
                )
            )
            |
            (?:
                (?:
                    made\s+to
                    |
                    paid\s+to
                )
                .{0,160}?
                performance\s+payments?
            )
            """,
            re.IGNORECASE
            | re.DOTALL
            | re.VERBOSE,
        ),
    ),
    (
        "EXPLICIT_ISSUED",
        re.compile(
            r"""
            (?:
                (?:cms\s+)?(?:has\s+)?issued
                .{0,180}?
                performance\s+payments?
            )
            |
            (?:
                performance\s+payments?
                .{0,180}?
                issued
            )
            """,
            re.IGNORECASE
            | re.DOTALL
            | re.VERBOSE,
        ),
    ),
    (
        "EXPLICIT_DETERMINED",
        re.compile(
            r"""
            (?:
                performance\s+payments?
                .{0,180}?
                (?:
                    determined
                    |
                    calculated
                    |
                    available
                    |
                    maximum
                )
            )
            """,
            re.IGNORECASE
            | re.DOTALL
            | re.VERBOSE,
        ),
    ),
    (
        "EXPLICIT_CUMULATIVE",
        re.compile(
            r"""
            (?:
                performance\s+payments?
                .{0,180}?
                (?:
                    combined
                    |
                    cumulative
                    |
                    through
                    |
                    total
                    |
                    same\s+period
                )
            )
            |
            (?:
                (?:
                    combined
                    |
                    cumulative
                    |
                    total
                )
                .{0,180}?
                performance\s+payments?
            )
            """,
            re.IGNORECASE
            | re.DOTALL
            | re.VERBOSE,
        ),
    ),
    (
        "GROSS_NET_RECONCILIATION",
        re.compile(
            r"""
            (?:
                gross
                .{0,240}?
                savings
                .{0,300}?
                performance\s+payments?
                .{0,300}?
                net
            )
            |
            (?:
                subtract(?:ing|ed)?
                .{0,220}?
                performance\s+payments?
                .{0,300}?
                gross
                .{0,220}?
                savings
            )
            |
            (?:
                gross
                .{0,220}?
                savings
                .{0,300}?
                subtract(?:ing|ed)?
                .{0,220}?
                performance\s+payments?
            )
            """,
            re.IGNORECASE
            | re.DOTALL
            | re.VERBOSE,
        ),
    ),
    (
        "PENDING",
        re.compile(
            r"""
            (?:
                pending
                .{0,260}?
                performance\s+payments?
            )
            |
            (?:
                performance\s+payments?
                .{0,260}?
                pending
            )
            """,
            re.IGNORECASE
            | re.DOTALL
            | re.VERBOSE,
        ),
    ),
    (
        "CONTEXT_ONLY",
        re.compile(
            r"\bperformance\s+payments?\b",
            re.IGNORECASE,
        ),
    ),
]


DOLLAR_PATTERN = re.compile(
    r"""
    (?:
        \$
        \s*
        \d[\d,]*
        (?:\.\d+)?
        \s*
        (?:
            million
            |
            billion
            |
            thousand
            |
            M
            |
            B
            |
            K
        )?
    )
    |
    (?:
        \b
        \d+(?:\.\d+)?
        \s+
        (?:
            million
            |
            billion
        )
        \b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


DY_PATTERN = re.compile(
    r"""
    (?:
        demonstration\s+years?
        \s*
        (\d+)
        \s*
        (?:-|–|—|through|to)
        \s*
        (\d+)
    )
    |
    (?:
        demonstration\s+year
        \s*
        (\d+)
    )
    |
    (?:
        \bDY\s*
        (\d+)
        \s*
        (?:-|–|—|through|to)
        \s*
        DY?\s*
        (\d+)
    )
    |
    (?:
        \bDY\s*
        (\d+)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def normalize_space(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value or "",
    ).strip()


def source_path(document: Document) -> Path:
    return (
        SOURCE_DIR
        / (
            f"{document.slot}__"
            "cms_wa_mffs_evaluation_report.pdf"
        )
    )


def extract_pages(path: Path) -> list[str]:
    reader = PdfReader(str(path))

    pages: list[str] = []

    for page in reader.pages:
        try:
            pages.append(
                page.extract_text() or ""
            )
        except Exception:
            pages.append("")

    return pages


def paragraphish_context(
    text: str,
    start: int,
    end: int,
    radius: int = 650,
) -> str:
    """
    Preserve a generous evidence window.

    PDF extraction often destroys paragraph boundaries,
    so a character window is safer than pretending that
    blank lines always represent true paragraphs.
    """
    left = max(
        0,
        start - radius,
    )

    right = min(
        len(text),
        end + radius,
    )

    return normalize_space(
        text[left:right]
    )


def dollar_values(text: str) -> str:
    values = [
        normalize_space(
            match.group(0)
        )
        for match
        in DOLLAR_PATTERN.finditer(text)
    ]

    return " | ".join(
        dict.fromkeys(values)
    )


def dy_references(text: str) -> str:
    references: list[str] = []

    for match in DY_PATTERN.finditer(text):
        groups = match.groups()

        if groups[0] and groups[1]:
            references.append(
                f"DY{groups[0]}-DY{groups[1]}"
            )

        elif groups[2]:
            references.append(
                f"DY{groups[2]}"
            )

        elif groups[3] and groups[4]:
            references.append(
                f"DY{groups[3]}-DY{groups[4]}"
            )

        elif groups[5]:
            references.append(
                f"DY{groups[5]}"
            )

    return " | ".join(
        dict.fromkeys(references)
    )


def write_csv(
    path: Path,
    fields: list[str],
    rows: list[dict],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 100)
    print(
        "CMS WASHINGTON MFFS EVALUATION "
        "PAYMENT EVIDENCE PROFILER v0.1"
    )
    print("=" * 100)
    print()
    print("READ-ONLY evidence extraction.")
    print("No inferred payments.")
    print("No database writes.")
    print("No ledger inclusion.")
    print()

    evidence_rows: list[dict] = []
    document_rows: list[dict] = []

    missing: list[str] = []
    unreadable: list[str] = []

    for document in DOCUMENTS:
        path = source_path(document)

        print("-" * 100)
        print(document.slot)
        print("-" * 100)

        if not path.exists():
            print("MISSING")
            print()

            missing.append(
                document.slot
            )

            document_rows.append(
                {
                    "slot": document.slot,
                    "pages": 0,
                    "text_pages": 0,
                    "evidence_hits": 0,
                    "dollar_evidence_hits": 0,
                    "status": "MISSING",
                }
            )

            continue

        try:
            pages = extract_pages(path)

        except Exception as exc:
            print(
                "UNREADABLE: "
                f"{type(exc).__name__}: {exc}"
            )
            print()

            unreadable.append(
                document.slot
            )

            document_rows.append(
                {
                    "slot": document.slot,
                    "pages": 0,
                    "text_pages": 0,
                    "evidence_hits": 0,
                    "dollar_evidence_hits": 0,
                    "status": "UNREADABLE",
                }
            )

            continue

        text_pages = sum(
            bool(normalize_space(page))
            for page in pages
        )

        hits = 0
        dollar_hits = 0

        seen: set[
            tuple[int, str, str]
        ] = set()

        for page_number, page_text in enumerate(
            pages,
            start=1,
        ):
            if not page_text:
                continue

            for evidence_class, pattern in PATTERNS:
                for match in pattern.finditer(
                    page_text
                ):
                    context = paragraphish_context(
                        page_text,
                        match.start(),
                        match.end(),
                    )

                    key = (
                        page_number,
                        evidence_class,
                        context,
                    )

                    if key in seen:
                        continue

                    seen.add(key)

                    dollars = dollar_values(
                        context
                    )

                    dys = dy_references(
                        context
                    )

                    if dollars:
                        dollar_hits += 1

                    evidence_rows.append(
                        {
                            "slot": document.slot,
                            "evaluation_number": (
                                document.ordinal
                            ),
                            "page_number": (
                                page_number
                            ),
                            "evidence_class": (
                                evidence_class
                            ),
                            "matched_text": (
                                normalize_space(
                                    match.group(0)
                                )
                            ),
                            "dy_references": dys,
                            "dollar_values": dollars,
                            "context": context,
                            "source_path": str(
                                path.relative_to(
                                    REPO_ROOT
                                )
                            ),
                        }
                    )

                    hits += 1

        document_rows.append(
            {
                "slot": document.slot,
                "pages": len(pages),
                "text_pages": text_pages,
                "evidence_hits": hits,
                "dollar_evidence_hits": (
                    dollar_hits
                ),
                "status": "PROFILED",
            }
        )

        print(
            f"Pages:                 "
            f"{len(pages):,}"
        )
        print(
            f"Pages with text:       "
            f"{text_pages:,}"
        )
        print(
            f"Payment evidence hits: "
            f"{hits:,}"
        )
        print(
            f"Dollar evidence hits:  "
            f"{dollar_hits:,}"
        )
        print("Status:                PROFILED")
        print()

    write_csv(
        DOCUMENT_CSV,
        [
            "slot",
            "pages",
            "text_pages",
            "evidence_hits",
            "dollar_evidence_hits",
            "status",
        ],
        document_rows,
    )

    write_csv(
        EVIDENCE_CSV,
        [
            "slot",
            "evaluation_number",
            "page_number",
            "evidence_class",
            "matched_text",
            "dy_references",
            "dollar_values",
            "context",
            "source_path",
        ],
        evidence_rows,
    )

    non_context_rows = [
        row
        for row in evidence_rows
        if row["evidence_class"]
        != "CONTEXT_ONLY"
    ]

    explicit_payment_rows = [
        row
        for row in evidence_rows
        if row["evidence_class"]
        in {
            "EXPLICIT_PAID_OR_MADE",
            "EXPLICIT_ISSUED",
            "EXPLICIT_DETERMINED",
            "EXPLICIT_CUMULATIVE",
        }
    ]

    explicit_dollar_rows = [
        row
        for row in explicit_payment_rows
        if row["dollar_values"]
    ]

    gross_net_rows = [
        row
        for row in evidence_rows
        if row["evidence_class"]
        == "GROSS_NET_RECONCILIATION"
    ]

    pending_rows = [
        row
        for row in evidence_rows
        if row["evidence_class"]
        == "PENDING"
    ]

    checks = [
        (
            "Five certified evaluation reports present",
            len(missing) == 0,
            f"{5 - len(missing)}/5 present",
        ),
        (
            "Five certified evaluation reports readable",
            (
                len(missing) == 0
                and len(unreadable) == 0
            ),
            (
                f"{5 - len(missing) - len(unreadable)}"
                "/5 readable"
            ),
        ),
        (
            "All reports yielded extractable text",
            (
                len(document_rows) == 5
                and all(
                    int(row["text_pages"]) > 0
                    for row in document_rows
                )
            ),
            (
                f"{sum(int(row['text_pages']) > 0 for row in document_rows)}"
                "/5"
            ),
        ),
        (
            "Payment evidence found",
            len(evidence_rows) > 0,
            f"{len(evidence_rows)} rows",
        ),
        (
            "Classified payment evidence found",
            len(non_context_rows) > 0,
            f"{len(non_context_rows)} rows",
        ),
        (
            "Explicit payment evidence found",
            len(explicit_payment_rows) > 0,
            f"{len(explicit_payment_rows)} rows",
        ),
        (
            "Explicit payment evidence with dollars found",
            len(explicit_dollar_rows) > 0,
            f"{len(explicit_dollar_rows)} rows",
        ),
        (
            "Gross/net reconciliation evidence inventoried",
            True,
            f"{len(gross_net_rows)} rows",
        ),
        (
            "Pending/remittance evidence inventoried",
            True,
            f"{len(pending_rows)} rows",
        ),
        (
            "No inferred DY payment reconstruction performed",
            True,
            "Evidence extraction only",
        ),
    ]

    write_csv(
        CHECKS_CSV,
        [
            "check",
            "status",
            "detail",
        ],
        [
            {
                "check": name,
                "status": (
                    "PASS"
                    if passed
                    else "FAIL"
                ),
                "detail": detail,
            }
            for name, passed, detail
            in checks
        ],
    )

    overall = all(
        passed
        for _, passed, _
        in checks
    )

    class_counts: dict[str, int] = {}

    for row in evidence_rows:
        key = row["evidence_class"]

        class_counts[key] = (
            class_counts.get(
                key,
                0,
            )
            + 1
        )

    lines: list[str] = []

    lines.append("=" * 100)
    lines.append(
        "CMS WASHINGTON MFFS EVALUATION "
        "PAYMENT EVIDENCE PROFILER v0.1"
    )
    lines.append("=" * 100)
    lines.append("")
    lines.append(
        "READ-ONLY evidence extraction."
    )
    lines.append(
        "No inferred payments."
    )
    lines.append(
        "No database writes."
    )
    lines.append(
        "No ledger inclusion."
    )
    lines.append("")

    lines.append("DOCUMENT PROFILE")
    lines.append("-" * 100)

    for row in document_rows:
        lines.append(
            f"{row['slot']:<20} "
            f"pages={int(row['pages']):>4}  "
            f"text={int(row['text_pages']):>4}  "
            f"hits={int(row['evidence_hits']):>4}  "
            f"dollar_hits="
            f"{int(row['dollar_evidence_hits']):>4}  "
            f"{row['status']}"
        )

    lines.append("")
    lines.append("EVIDENCE CLASS COUNTS")
    lines.append("-" * 100)

    for evidence_class in sorted(
        class_counts
    ):
        lines.append(
            f"{evidence_class:<32} "
            f"{class_counts[evidence_class]:>6}"
        )

    lines.append("")
    lines.append(
        "EXPLICIT PAYMENT EVIDENCE WITH DOLLARS"
    )
    lines.append("-" * 100)

    if not explicit_dollar_rows:
        lines.append(
            "None found."
        )

    else:
        for row in explicit_dollar_rows:
            context = row["context"]

            if len(context) > 850:
                context = (
                    context[:847]
                    + "..."
                )

            lines.append(
                f"{row['slot']} | "
                f"page {row['page_number']} | "
                f"{row['evidence_class']} | "
                f"{row['dy_references']} | "
                f"{row['dollar_values']}"
            )

            lines.append(
                f"  {context}"
            )

    lines.append("")
    lines.append(
        "GROSS/NET RECONCILIATION EVIDENCE"
    )
    lines.append("-" * 100)

    if not gross_net_rows:
        lines.append("None found.")
    else:
        for row in gross_net_rows:
            lines.append(
                f"{row['slot']} | "
                f"page {row['page_number']} | "
                f"{row['dy_references']} | "
                f"{row['dollar_values']}"
            )

    lines.append("")
    lines.append(
        "PENDING / ISSUANCE EVIDENCE"
    )
    lines.append("-" * 100)

    issuance_rows = [
        row
        for row in evidence_rows
        if row["evidence_class"]
        in {
            "EXPLICIT_ISSUED",
            "PENDING",
        }
    ]

    if not issuance_rows:
        lines.append("None found.")
    else:
        for row in issuance_rows:
            context = row["context"]

            if len(context) > 850:
                context = (
                    context[:847]
                    + "..."
                )

            lines.append(
                f"{row['slot']} | "
                f"page {row['page_number']} | "
                f"{row['evidence_class']} | "
                f"{row['dy_references']} | "
                f"{row['dollar_values']}"
            )

            lines.append(
                f"  {context}"
            )

    lines.append("")
    lines.append("CHECKS")
    lines.append("-" * 100)

    for name, passed, detail in checks:
        lines.append(
            f"{'PASS' if passed else 'FAIL'} | "
            f"{name} | {detail}"
        )

    lines.append("")
    lines.append("=" * 100)
    lines.append(
        "OVERALL PAYMENT EVIDENCE PROFILER v0.1: "
        + (
            "PASS"
            if overall
            else "FAIL"
        )
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("Interpretive boundary:")
    lines.append(
        "  Explicit dollar evidence is preserved "
        "but not automatically certified as cash "
        "remitted."
    )
    lines.append(
        "  Gross-minus-net relationships are "
        "reconciliation evidence, not independently "
        "observed cash transactions."
    )
    lines.append(
        "  'Issued', 'made', 'determined', and "
        "'pending' remain distinct accounting states."
    )
    lines.append(
        "  No preliminary or cumulative observation "
        "is silently converted into a DY-specific "
        "payment."
    )
    lines.append(
        "  No MFFS amount is additive to Original "
        "Medicare/FFS without a separate overlap "
        "certification."
    )
    lines.append(
        "  No ledger inclusion is authorized."
    )
    lines.append("")

    report_text = "\n".join(lines)

    REPORT_TXT.write_text(
        report_text,
        encoding="utf-8",
    )

    print()
    print(report_text)

    print("Evidence written:")
    print(
        f"  {DOCUMENT_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"  {EVIDENCE_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"  {CHECKS_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"  {REPORT_TXT.relative_to(REPO_ROOT)}"
    )

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
