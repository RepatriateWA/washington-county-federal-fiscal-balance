"""
profile_cms_wa_mffs_performance_payment_evidence_v0_1.py

WCFFBP
Washington MFFS Performance-Payment Evidence Profiler v0.1

Purpose
-------
Profile the seven locally certified CMS Washington MFFS actuarial
reports for evidence concerning:

    * retrospective performance payments
    * performance payments
    * payments to the State
    * Medicare savings
    * quality requirements
    * payment eligibility
    * payment timing
    * final versus preliminary results

READ-ONLY with respect to source PDFs and database.

This script DOES NOT:
    * calculate an additive federal inflow;
    * infer a payment from savings;
    * substitute preliminary for final observations;
    * allocate dollars to counties;
    * write to PostgreSQL;
    * authorize ledger inclusion.

It writes only validation/evidence artifacts.
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
    / "actuarial_reports"
    / "v0_2"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_mffs"
    / "washington"
    / "validation"
    / "performance_payment_evidence_v0_1"
)

EVIDENCE_CSV = (
    OUTPUT_DIR
    / "cms_wa_mffs_performance_payment_evidence_v0_1.csv"
)

DOCUMENT_CSV = (
    OUTPUT_DIR
    / "cms_wa_mffs_performance_payment_document_profile_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_wa_mffs_performance_payment_evidence_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_wa_mffs_performance_payment_evidence_report_v0_1.txt"
)


@dataclass(frozen=True)
class RequiredDocument:
    slot: str
    final_dy: int
    preliminary_dy: int


REQUIRED_DOCUMENTS = [
    RequiredDocument("DY1_FINAL_DY2_PRELIM", 1, 2),
    RequiredDocument("DY2_FINAL_DY3_PRELIM", 2, 3),
    RequiredDocument("DY3_FINAL_DY4_PRELIM", 3, 4),
    RequiredDocument("DY4_FINAL_DY5_PRELIM", 4, 5),
    RequiredDocument("DY5_FINAL_DY6_PRELIM", 5, 6),
    RequiredDocument("DY6_FINAL_DY7_PRELIM", 6, 7),
    RequiredDocument("DY7_FINAL_DY8_PRELIM", 7, 8),
]


SEARCH_PATTERNS = [
    (
        "RETROSPECTIVE_PERFORMANCE_PAYMENT",
        re.compile(
            r"\bretrospective\s+performance\s+payment(?:s)?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "PERFORMANCE_PAYMENT",
        re.compile(
            r"\bperformance\s+payment(?:s)?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "PAYMENT_TO_STATE",
        re.compile(
            r"\bpayment(?:s)?\s+to\s+(?:the\s+)?state\b",
            re.IGNORECASE,
        ),
    ),
    (
        "STATE_ELIGIBLE_PAYMENT",
        re.compile(
            r"\bstate\b.{0,100}\b(?:eligible|eligibility)\b"
            r".{0,100}\bpayment\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "MEDICARE_SAVINGS",
        re.compile(
            r"\bmedicare\s+(?:cost\s+)?savings\b",
            re.IGNORECASE,
        ),
    ),
    (
        "GROSS_SAVINGS",
        re.compile(
            r"\bgross\s+(?:medicare\s+)?savings\b",
            re.IGNORECASE,
        ),
    ),
    (
        "NET_SAVINGS",
        re.compile(
            r"\bnet\s+(?:medicare\s+)?savings\b",
            re.IGNORECASE,
        ),
    ),
    (
        "QUALITY",
        re.compile(
            r"\bquality\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ELIGIBLE",
        re.compile(
            r"\beligib(?:le|ility)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "SHARED_SAVINGS",
        re.compile(
            r"\bshared?\s+savings\b",
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
        (?:million|billion|thousand|M|B|K)?
    )
    |
    (?:
        \b
        \d+(?:\.\d+)?
        \s+
        (?:million|billion)
        \b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def source_path(document: RequiredDocument) -> Path:
    return (
        SOURCE_DIR
        / (
            f"{document.slot}__"
            "cms_wa_mffs_medicare_cost_savings_report.pdf"
        )
    )


def page_texts(path: Path) -> list[str]:
    reader = PdfReader(str(path))

    output: list[str] = []

    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        output.append(text)

    return output


def context_window(
    text: str,
    start: int,
    end: int,
    radius: int = 450,
) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)

    return normalize_space(
        text[left:right]
    )


def dollars_in_context(context: str) -> str:
    values = [
        normalize_space(match.group(0))
        for match in DOLLAR_PATTERN.finditer(context)
    ]

    # Preserve order while removing exact duplicates.
    return " | ".join(dict.fromkeys(values))


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
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
        "CMS WASHINGTON MFFS PERFORMANCE-PAYMENT "
        "EVIDENCE PROFILER v0.1"
    )
    print("=" * 100)
    print()
    print("READ-ONLY source profiling.")
    print("No database writes.")
    print("No payment reconstruction.")
    print("No inferred payments.")
    print("No ledger inclusion.")
    print()

    evidence_rows: list[dict] = []
    document_rows: list[dict] = []

    missing_documents: list[str] = []
    unreadable_documents: list[str] = []

    for document in REQUIRED_DOCUMENTS:
        path = source_path(document)

        print("-" * 100)
        print(document.slot)
        print("-" * 100)
        print(path.relative_to(REPO_ROOT))

        if not path.exists():
            print("MISSING")
            print()

            missing_documents.append(
                document.slot
            )

            document_rows.append(
                {
                    "slot": document.slot,
                    "final_dy": document.final_dy,
                    "preliminary_dy": document.preliminary_dy,
                    "source_path": str(
                        path.relative_to(REPO_ROOT)
                    ),
                    "exists": "NO",
                    "pages": 0,
                    "text_pages": 0,
                    "evidence_hits": 0,
                    "dollar_context_hits": 0,
                    "status": "MISSING",
                }
            )

            continue

        try:
            pages = page_texts(path)
        except Exception as exc:
            print(
                "UNREADABLE: "
                f"{type(exc).__name__}: {exc}"
            )
            print()

            unreadable_documents.append(
                document.slot
            )

            document_rows.append(
                {
                    "slot": document.slot,
                    "final_dy": document.final_dy,
                    "preliminary_dy": document.preliminary_dy,
                    "source_path": str(
                        path.relative_to(REPO_ROOT)
                    ),
                    "exists": "YES",
                    "pages": 0,
                    "text_pages": 0,
                    "evidence_hits": 0,
                    "dollar_context_hits": 0,
                    "status": "UNREADABLE",
                }
            )

            continue

        text_pages = sum(
            bool(normalize_space(text))
            for text in pages
        )

        document_hit_count = 0
        dollar_context_count = 0

        seen_evidence: set[
            tuple[int, str, str]
        ] = set()

        for page_index, text in enumerate(
            pages,
            start=1,
        ):
            if not text:
                continue

            for evidence_type, pattern in SEARCH_PATTERNS:
                for match in pattern.finditer(text):
                    context = context_window(
                        text,
                        match.start(),
                        match.end(),
                    )

                    dedupe_key = (
                        page_index,
                        evidence_type,
                        context,
                    )

                    if dedupe_key in seen_evidence:
                        continue

                    seen_evidence.add(
                        dedupe_key
                    )

                    dollars = dollars_in_context(
                        context
                    )

                    if dollars:
                        dollar_context_count += 1

                    evidence_rows.append(
                        {
                            "slot": document.slot,
                            "final_dy": document.final_dy,
                            "preliminary_dy": (
                                document.preliminary_dy
                            ),
                            "page_number": page_index,
                            "evidence_type": evidence_type,
                            "matched_text": normalize_space(
                                match.group(0)
                            ),
                            "dollar_values_in_context": dollars,
                            "context": context,
                            "source_path": str(
                                path.relative_to(REPO_ROOT)
                            ),
                        }
                    )

                    document_hit_count += 1

        status = (
            "PROFILED"
            if text_pages > 0
            else "NO_EXTRACTABLE_TEXT"
        )

        document_rows.append(
            {
                "slot": document.slot,
                "final_dy": document.final_dy,
                "preliminary_dy": document.preliminary_dy,
                "source_path": str(
                    path.relative_to(REPO_ROOT)
                ),
                "exists": "YES",
                "pages": len(pages),
                "text_pages": text_pages,
                "evidence_hits": document_hit_count,
                "dollar_context_hits": dollar_context_count,
                "status": status,
            }
        )

        print(f"Pages:               {len(pages):,}")
        print(f"Pages with text:     {text_pages:,}")
        print(
            f"Evidence hits:       "
            f"{document_hit_count:,}"
        )
        print(
            f"Dollar-context hits: "
            f"{dollar_context_count:,}"
        )
        print(f"Status:              {status}")
        print()

    write_csv(
        DOCUMENT_CSV,
        [
            "slot",
            "final_dy",
            "preliminary_dy",
            "source_path",
            "exists",
            "pages",
            "text_pages",
            "evidence_hits",
            "dollar_context_hits",
            "status",
        ],
        document_rows,
    )

    write_csv(
        EVIDENCE_CSV,
        [
            "slot",
            "final_dy",
            "preliminary_dy",
            "page_number",
            "evidence_type",
            "matched_text",
            "dollar_values_in_context",
            "context",
            "source_path",
        ],
        evidence_rows,
    )

    slots_with_evidence = {
        row["slot"]
        for row in evidence_rows
    }

    performance_types = {
        "RETROSPECTIVE_PERFORMANCE_PAYMENT",
        "PERFORMANCE_PAYMENT",
        "PAYMENT_TO_STATE",
        "STATE_ELIGIBLE_PAYMENT",
    }

    slots_with_performance_evidence = {
        row["slot"]
        for row in evidence_rows
        if row["evidence_type"] in performance_types
    }

    performance_dollar_rows = [
        row
        for row in evidence_rows
        if (
            row["evidence_type"] in performance_types
            and row["dollar_values_in_context"]
        )
    ]

    checks: list[tuple[str, bool, str]] = []

    checks.append(
        (
            "Seven certified source PDFs present",
            len(missing_documents) == 0,
            (
                f"{7 - len(missing_documents)}/7 present"
            ),
        )
    )

    checks.append(
        (
            "Seven certified source PDFs readable",
            (
                len(missing_documents) == 0
                and len(unreadable_documents) == 0
            ),
            (
                f"{7 - len(unreadable_documents) - len(missing_documents)}"
                "/7 readable"
            ),
        )
    )

    checks.append(
        (
            "All seven documents yielded extractable text",
            (
                len(document_rows) == 7
                and all(
                    int(row["text_pages"]) > 0
                    for row in document_rows
                )
            ),
            (
                f"{sum(int(row['text_pages']) > 0 for row in document_rows)}"
                "/7"
            ),
        )
    )

    checks.append(
        (
            "Evidence vocabulary found in every report",
            len(slots_with_evidence) == 7,
            f"{len(slots_with_evidence)}/7 reports",
        )
    )

    checks.append(
        (
            "Performance-payment vocabulary found",
            len(slots_with_performance_evidence) > 0,
            (
                f"{len(slots_with_performance_evidence)}"
                "/7 reports"
            ),
        )
    )

    checks.append(
        (
            "At least one performance-payment context contains dollars",
            len(performance_dollar_rows) > 0,
            (
                f"{len(performance_dollar_rows)} "
                "evidence rows"
            ),
        )
    )

    checks.append(
        (
            "Profiler performs no inferred dollar reconstruction",
            True,
            "Evidence extraction only",
        )
    )

    overall_pass = all(
        passed
        for _, passed, _ in checks
    )

    check_rows = [
        {
            "check": name,
            "status": (
                "PASS"
                if passed
                else "FAIL"
            ),
            "detail": detail,
        }
        for name, passed, detail in checks
    ]

    write_csv(
        CHECKS_CSV,
        [
            "check",
            "status",
            "detail",
        ],
        check_rows,
    )

    evidence_type_counts: dict[str, int] = {}

    for row in evidence_rows:
        evidence_type = row["evidence_type"]

        evidence_type_counts[evidence_type] = (
            evidence_type_counts.get(
                evidence_type,
                0,
            )
            + 1
        )

    lines: list[str] = []

    lines.append("=" * 100)
    lines.append(
        "CMS WASHINGTON MFFS PERFORMANCE-PAYMENT "
        "EVIDENCE PROFILER v0.1"
    )
    lines.append("=" * 100)
    lines.append("")
    lines.append("READ-ONLY source profiling.")
    lines.append("No database writes.")
    lines.append("No payment reconstruction.")
    lines.append("No inferred payments.")
    lines.append("No ledger inclusion.")
    lines.append("")

    lines.append("DOCUMENT PROFILE")
    lines.append("-" * 100)

    for row in document_rows:
        lines.append(
            f"{row['slot']:<24} "
            f"pages={int(row['pages']):>3}  "
            f"text_pages={int(row['text_pages']):>3}  "
            f"hits={int(row['evidence_hits']):>4}  "
            f"dollar_context={int(row['dollar_context_hits']):>4}  "
            f"{row['status']}"
        )

    lines.append("")
    lines.append("EVIDENCE TYPE COUNTS")
    lines.append("-" * 100)

    for evidence_type in sorted(
        evidence_type_counts
    ):
        lines.append(
            f"{evidence_type:<38} "
            f"{evidence_type_counts[evidence_type]:>6}"
        )

    lines.append("")
    lines.append(
        "PERFORMANCE-PAYMENT DOLLAR CONTEXTS"
    )
    lines.append("-" * 100)

    if not performance_dollar_rows:
        lines.append(
            "None found in the seven actuarial reports."
        )
    else:
        for row in performance_dollar_rows:
            context = row["context"]

            if len(context) > 500:
                context = (
                    context[:497]
                    + "..."
                )

            lines.append(
                f"{row['slot']} | "
                f"page {row['page_number']} | "
                f"{row['evidence_type']} | "
                f"{row['dollar_values_in_context']}"
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
        "OVERALL EVIDENCE PROFILER v0.1: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("Interpretive boundary:")
    lines.append(
        "  PASS means the certified actuarial reports were "
        "successfully profiled for payment-related evidence."
    )
    lines.append(
        "  Dollar strings are evidence candidates only."
    )
    lines.append(
        "  No dollar value is classified as a Washington "
        "performance payment merely because it appears near "
        "payment terminology."
    )
    lines.append(
        "  Savings are not treated as payments."
    )
    lines.append(
        "  Preliminary observations are not substituted for "
        "final observations."
    )
    lines.append(
        "  No payment is additive to Original Medicare/FFS "
        "without a separate overlap certification."
    )
    lines.append("")

    report = "\n".join(lines)

    REPORT_TXT.write_text(
        report,
        encoding="utf-8",
    )

    print(report)

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
    print()

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
