"""
WCFFBP
CMS MSSP Settlement Semantics Profiler v0.1

PURPOSE
-------
Read the already-preserved CMS MSSP documentation package and extract
documented field semantics relevant to MSSP settlement accounting.

Questions addressed
-------------------
For each MSSP performance period:
    - What does CMS document for EarnSaveLoss?
    - What does CMS document for GenSaveLoss?
    - What advance-payment / AIM / AIP fields are documented?
    - What does CMS say about recoupment?
    - Which governing dictionary supports each observation?

IMPORTANT
---------
This profiler is evidence-first.

It does NOT:
    - infer an accounting formula;
    - classify EarnSaveLoss as additive;
    - infer cash-payment timing;
    - infer Washington payment-dollar incidence;
    - infer beneficiary residence;
    - net advance payments or recoupments;
    - write to PostgreSQL;
    - alter the principal ledger.

No new acquisition is performed.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]

DOC_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "documentation"
    / "Performance Year Financial and Quality Results - Documentation.zip"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "validation"
    / "settlement_semantics_v0_1"
)

INVENTORY_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_document_inventory_v0_1.csv"
)

FIELD_EVIDENCE_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_field_evidence_v0_1.csv"
)

PERIOD_MATRIX_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_semantics_matrix_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_semantics_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_mssp_settlement_semantics_report_v0_1.txt"
)


EXPECTED_PERIODS = [
    "2015",
    "2016",
    "2017",
    "2018",
    "2019",
    "2019A",
    "2020",
    "2021",
    "2022",
    "2023",
    "2024",
]


# These are discovery targets, not accounting conclusions.
TARGET_FIELDS = [
    "EarnSaveLoss",
    "GenSaveLoss",
    "Adv_Pay",
    "Adv_Pay_Amt",
    "Adv_Pay_Recoup",
    "AIM",
    "AIP",
    "AIPBalance",
    "AIPRecoup",
    "AIPOwe",
]


SEARCH_TERMS = [
    "EarnSaveLoss",
    "GenSaveLoss",
    "Adv_Pay",
    "Adv Pay",
    "advance payment",
    "advance payments",
    "recoup",
    "AIM",
    "AIP",
    "advance investment payment",
    "shared savings",
    "shared losses",
    "sequestration",
    "payment limit",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            h.update(block)

    return h.hexdigest().upper()


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\x00", " ")
    text = text.replace("\r", "\n")

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n[ \t]+",
        "\n",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


def compact_text(value: str | None) -> str:
    return re.sub(
        r"\s+",
        " ",
        normalize_text(value),
    ).strip()


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
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def extract_pdf_text(data: bytes) -> tuple[str, int]:
    reader = PdfReader(
        io.BytesIO(data)
    )

    page_text = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            text = (
                f"[PAGE EXTRACTION ERROR: {exc}]"
            )

        page_text.append(
            f"\n[[PAGE {page_number}]]\n{text}"
        )

    return (
        normalize_text(
            "\n".join(page_text)
        ),
        len(reader.pages),
    )


def infer_periods_from_path(
    member_name: str,
) -> list[str]:
    """
    Infer performance-period applicability from archive path/name.

    This is used only as source-path evidence. It does not override
    document-text evidence.
    """
    text = member_name.replace(
        "\\",
        "/",
    ).lower()

    periods = []

    if (
        "2019_off-cycle_1" in text
        or "2019_off_cycle_1" in text
        or "2019a" in text
    ):
        periods.append("2019A")

    for year in range(
        2015,
        2025,
    ):
        if re.search(
            rf"(?<!\d){year}(?!\d)",
            text,
        ):
            periods.append(str(year))

    # Remove duplicate 2019 if the path is specifically 2019A.
    if (
        "2019A" in periods
        and "2019" in periods
    ):
        periods.remove("2019")

    return list(
        dict.fromkeys(periods)
    )


def document_kind(
    member_name: str,
    text: str,
) -> str:
    combined = (
        member_name
        + "\n"
        + text[:5000]
    ).lower()

    if (
        "data dictionary" in combined
        or "dictionary" in member_name.lower()
    ):
        return "DATA_DICTIONARY"

    if "methodology" in combined:
        return "METHODOLOGY"

    return "OTHER"


def page_number_for_offset(
    text: str,
    offset: int,
) -> str:
    """
    Determine the nearest preceding [[PAGE N]] marker.
    """
    prefix = text[:offset]

    matches = list(
        re.finditer(
            r"\[\[PAGE\s+(\d+)\]\]",
            prefix,
            flags=re.IGNORECASE,
        )
    )

    if not matches:
        return ""

    return matches[-1].group(1)


def context_window(
    text: str,
    start: int,
    end: int,
    before: int = 650,
    after: int = 1400,
) -> str:
    left = max(
        0,
        start - before,
    )

    right = min(
        len(text),
        end + after,
    )

    return compact_text(
        text[left:right]
    )


def search_document(
    member_name: str,
    document_sha256: str,
    document_type: str,
    periods: list[str],
    text: str,
) -> list[dict]:
    evidence = []
    seen = set()

    for term in SEARCH_TERMS:
        pattern = re.compile(
            re.escape(term),
            flags=re.IGNORECASE,
        )

        for match in pattern.finditer(
            text
        ):
            page = page_number_for_offset(
                text,
                match.start(),
            )

            context = context_window(
                text,
                match.start(),
                match.end(),
            )

            dedupe_key = (
                term.lower(),
                page,
                context,
            )

            if dedupe_key in seen:
                continue

            seen.add(
                dedupe_key
            )

            evidence.append(
                {
                    "member_name": member_name,
                    "document_sha256": document_sha256,
                    "document_type": document_type,
                    "path_periods": ";".join(
                        periods
                    ),
                    "search_term": term,
                    "page": page,
                    "context": context,
                }
            )

    return evidence


def detect_field_presence(
    text: str,
    field: str,
) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9_])"
            rf"{re.escape(field)}"
            rf"(?![A-Za-z0-9_])",
            text,
            flags=re.IGNORECASE,
        )
    )


def infer_governing_periods(
    inventory_rows: list[dict],
) -> dict[str, list[dict]]:
    """
    Build a conservative period -> candidate dictionary map.

    We do not silently choose a dictionary when source-path evidence
    does not identify a period.

    Older repeated dictionaries may govern several historical periods.
    The matrix therefore records all candidate governing dictionaries
    discovered from archive placement.
    """
    mapping: dict[
        str,
        list[dict],
    ] = defaultdict(list)

    for row in inventory_rows:
        if (
            row["document_type"]
            != "DATA_DICTIONARY"
        ):
            continue

        periods = [
            p
            for p in row[
                "path_periods"
            ].split(";")
            if p
        ]

        for period in periods:
            if (
                period
                in EXPECTED_PERIODS
            ):
                mapping[
                    period
                ].append(row)

    return mapping


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    checks: list[dict] = []
    errors: list[str] = []

    def add_check(
        name: str,
        passed: bool,
        detail: str,
    ) -> None:
        checks.append(
            {
                "check": name,
                "status": (
                    "PASS"
                    if passed
                    else "FAIL"
                ),
                "detail": detail,
            }
        )

    # ------------------------------------------------------------
    # Input
    # ------------------------------------------------------------
    add_check(
        "Preserved MSSP documentation package exists",
        DOC_ZIP.exists(),
        str(
            DOC_ZIP.relative_to(
                REPO_ROOT
            )
        ),
    )

    if not DOC_ZIP.exists():
        write_csv(
            CHECKS_CSV,
            [
                "check",
                "status",
                "detail",
            ],
            checks,
        )

        print(
            f"FAIL: missing documentation package: {DOC_ZIP}"
        )

        return 1

    # ------------------------------------------------------------
    # Read every PDF from preserved archive
    # ------------------------------------------------------------
    inventory_rows: list[dict] = []
    evidence_rows: list[dict] = []
    document_text_by_sha: dict[
        str,
        str,
    ] = {}

    with zipfile.ZipFile(
        DOC_ZIP,
        "r",
    ) as archive:
        pdf_members = [
            info
            for info in archive.infolist()
            if (
                not info.is_dir()
                and info.filename.lower().endswith(
                    ".pdf"
                )
            )
        ]

        for info in pdf_members:
            try:
                data = archive.read(
                    info
                )

                digest = sha256_bytes(
                    data
                )

                text, page_count = (
                    extract_pdf_text(
                        data
                    )
                )

                document_text_by_sha[
                    digest
                ] = text

                periods = (
                    infer_periods_from_path(
                        info.filename
                    )
                )

                kind = document_kind(
                    info.filename,
                    text,
                )

                inventory_rows.append(
                    {
                        "member_name": info.filename,
                        "bytes": len(data),
                        "sha256": digest,
                        "pages": page_count,
                        "document_type": kind,
                        "path_periods": ";".join(
                            periods
                        ),
                        "text_characters": len(
                            text
                        ),
                    }
                )

                evidence_rows.extend(
                    search_document(
                        member_name=info.filename,
                        document_sha256=digest,
                        document_type=kind,
                        periods=periods,
                        text=text,
                    )
                )

            except Exception as exc:
                errors.append(
                    f"{info.filename}: {exc}"
                )

    unique_sha = {
        row["sha256"]
        for row in inventory_rows
    }

    unique_dictionary_sha = {
        row["sha256"]
        for row in inventory_rows
        if row[
            "document_type"
        ]
        == "DATA_DICTIONARY"
    }

    add_check(
        "All documentation PDFs parse",
        len(errors) == 0,
        (
            f"{len(inventory_rows)} PDFs parsed; "
            f"{len(errors)} failures"
        ),
    )

    add_check(
        "Documentation package reproduces 22 PDF members",
        len(
            inventory_rows
        )
        == 22,
        f"{len(inventory_rows)}/22",
    )

    add_check(
        "Documentation package reproduces 7 unique PDF byte streams",
        len(
            unique_sha
        )
        == 7,
        f"{len(unique_sha)}/7",
    )

    # ------------------------------------------------------------
    # Candidate governing dictionary map
    # ------------------------------------------------------------
    governing = infer_governing_periods(
        inventory_rows
    )

    matrix_rows = []

    for period in EXPECTED_PERIODS:
        candidates = governing.get(
            period,
            [],
        )

        candidate_shas = list(
            dict.fromkeys(
                row["sha256"]
                for row in candidates
            )
        )

        candidate_names = list(
            dict.fromkeys(
                row["member_name"]
                for row in candidates
            )
        )

        combined_text = "\n".join(
            document_text_by_sha.get(
                sha,
                "",
            )
            for sha in candidate_shas
        )

        row = {
            "performance_period": period,
            "candidate_dictionary_count": len(
                candidate_shas
            ),
            "candidate_dictionary_sha256": ";".join(
                candidate_shas
            ),
            "candidate_dictionary_members": " || ".join(
                candidate_names
            ),
        }

        for field in TARGET_FIELDS:
            row[
                f"{field}_documented"
            ] = (
                "YES"
                if detect_field_presence(
                    combined_text,
                    field,
                )
                else "NO"
            )

        row[
            "advance_payment_term_present"
        ] = (
            "YES"
            if re.search(
                r"advance payment",
                combined_text,
                flags=re.IGNORECASE,
            )
            else "NO"
        )

        row[
            "recoup_term_present"
        ] = (
            "YES"
            if re.search(
                r"recoup",
                combined_text,
                flags=re.IGNORECASE,
            )
            else "NO"
        )

        row[
            "sequestration_term_present"
        ] = (
            "YES"
            if re.search(
                r"sequestration",
                combined_text,
                flags=re.IGNORECASE,
            )
            else "NO"
        )

        row[
            "payment_limit_term_present"
        ] = (
            "YES"
            if re.search(
                r"payment limit",
                combined_text,
                flags=re.IGNORECASE,
            )
            else "NO"
        )

        matrix_rows.append(
            row
        )

    periods_with_dictionary = [
        row["performance_period"]
        for row in matrix_rows
        if int(
            row[
                "candidate_dictionary_count"
            ]
        )
        > 0
    ]

    add_check(
        "All 11 performance periods have dictionary evidence from archive placement",
        set(
            periods_with_dictionary
        )
        == set(
            EXPECTED_PERIODS
        ),
        (
            f"{len(periods_with_dictionary)}/11 | "
            + ",".join(
                periods_with_dictionary
            )
        ),
    )

    # ------------------------------------------------------------
    # Fundamental semantic targets
    # ------------------------------------------------------------
    earn_periods = [
        row["performance_period"]
        for row in matrix_rows
        if row[
            "EarnSaveLoss_documented"
        ]
        == "YES"
    ]

    gen_periods = [
        row["performance_period"]
        for row in matrix_rows
        if row[
            "GenSaveLoss_documented"
        ]
        == "YES"
    ]

    add_check(
        "EarnSaveLoss documented across all 11 periods",
        set(
            earn_periods
        )
        == set(
            EXPECTED_PERIODS
        ),
        f"{len(earn_periods)}/11",
    )

    add_check(
        "GenSaveLoss documented across all 11 periods",
        set(
            gen_periods
        )
        == set(
            EXPECTED_PERIODS
        ),
        f"{len(gen_periods)}/11",
    )

    # We intentionally do NOT require every advance/AIM/AIP field
    # in every period. Their historical appearance is part of what
    # this profiler is meant to measure.

    # ------------------------------------------------------------
    # Evidence coverage
    # ------------------------------------------------------------
    evidence_terms = Counter(
        row["search_term"]
        for row in evidence_rows
    )

    add_check(
        "Settlement-semantic evidence extracted",
        len(
            evidence_rows
        )
        > 0,
        (
            f"{len(evidence_rows)} evidence windows | "
            + "; ".join(
                f"{term}={count}"
                for term, count
                in sorted(
                    evidence_terms.items()
                )
            )
        ),
    )

    # ------------------------------------------------------------
    # Write outputs
    # ------------------------------------------------------------
    write_csv(
        INVENTORY_CSV,
        [
            "member_name",
            "bytes",
            "sha256",
            "pages",
            "document_type",
            "path_periods",
            "text_characters",
        ],
        inventory_rows,
    )

    write_csv(
        FIELD_EVIDENCE_CSV,
        [
            "member_name",
            "document_sha256",
            "document_type",
            "path_periods",
            "search_term",
            "page",
            "context",
        ],
        evidence_rows,
    )

    matrix_fields = [
        "performance_period",
        "candidate_dictionary_count",
        "candidate_dictionary_sha256",
        "candidate_dictionary_members",
    ]

    matrix_fields.extend(
        f"{field}_documented"
        for field in TARGET_FIELDS
    )

    matrix_fields.extend(
        [
            "advance_payment_term_present",
            "recoup_term_present",
            "sequestration_term_present",
            "payment_limit_term_present",
        ]
    )

    write_csv(
        PERIOD_MATRIX_CSV,
        matrix_fields,
        matrix_rows,
    )

    write_csv(
        CHECKS_CSV,
        [
            "check",
            "status",
            "detail",
        ],
        checks,
    )

    overall_pass = (
        not errors
        and all(
            check["status"]
            == "PASS"
            for check in checks
        )
    )

    # ------------------------------------------------------------
    # Human-readable report
    # ------------------------------------------------------------
    lines: list[str] = []

    lines.append("=" * 108)
    lines.append(
        "CMS MSSP SETTLEMENT SEMANTICS PROFILE v0.1"
    )
    lines.append("=" * 108)
    lines.append("")

    lines.append("BOUNDARY")
    lines.append("-" * 108)
    lines.append(
        "READ-ONLY extraction from the already-preserved CMS MSSP documentation package."
    )
    lines.append(
        "No accounting formula inferred."
    )
    lines.append(
        "No additivity conclusion."
    )
    lines.append(
        "No advance/AIM/AIP netting."
    )
    lines.append(
        "No Washington payment-dollar incidence inferred."
    )
    lines.append(
        "No database writes."
    )
    lines.append(
        "No ledger inclusion."
    )
    lines.append("")

    lines.append("DOCUMENTATION INVENTORY")
    lines.append("-" * 108)
    lines.append(
        f"PDF members: {len(inventory_rows)}"
    )
    lines.append(
        f"Unique PDF byte streams: {len(unique_sha)}"
    )
    lines.append(
        f"Unique data-dictionary byte streams: {len(unique_dictionary_sha)}"
    )
    lines.append(
        f"Documentation ZIP SHA-256: {sha256_file(DOC_ZIP)}"
    )
    lines.append("")

    lines.append("PERIOD SEMANTICS MATRIX")
    lines.append("-" * 108)

    for row in matrix_rows:
        advance_fields = [
            field
            for field in TARGET_FIELDS
            if (
                field
                not in (
                    "EarnSaveLoss",
                    "GenSaveLoss",
                )
                and row[
                    f"{field}_documented"
                ]
                == "YES"
            )
        ]

        lines.append(
            f"{row['performance_period']:<6} | "
            f"dictionary_docs={row['candidate_dictionary_count']} | "
            f"EarnSaveLoss={row['EarnSaveLoss_documented']} | "
            f"GenSaveLoss={row['GenSaveLoss_documented']} | "
            f"advance_fields="
            f"{','.join(advance_fields) if advance_fields else 'NONE'} | "
            f"recoup_term={row['recoup_term_present']} | "
            f"sequestration={row['sequestration_term_present']} | "
            f"payment_limit={row['payment_limit_term_present']}"
        )

    lines.append("")
    lines.append("SEARCH-EVIDENCE COUNTS")
    lines.append("-" * 108)

    for term, count in sorted(
        evidence_terms.items()
    ):
        lines.append(
            f"{term:<30} {count:>5}"
        )

    lines.append("")
    lines.append("CHECKS")
    lines.append("-" * 108)

    for check in checks:
        lines.append(
            f"{check['status']} | "
            f"{check['check']} | "
            f"{check['detail']}"
        )

    if errors:
        lines.append("")
        lines.append("ERRORS")
        lines.append("-" * 108)

        for error in errors:
            lines.append(
                f"FAIL | {error}"
            )

    lines.append("")
    lines.append("=" * 108)
    lines.append(
        "OVERALL CMS MSSP SETTLEMENT SEMANTICS PROFILE v0.1: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )
    lines.append("=" * 108)
    lines.append("")

    lines.append("Interpretive boundary:")
    lines.append(
        "  PASS means the preserved CMS documentation can support the next semantic review."
    )
    lines.append(
        "  PASS does not establish an MSSP settlement accounting identity."
    )
    lines.append(
        "  Field presence does not imply that two fields may be added, subtracted, or netted."
    )
    lines.append(
        "  Extracted context remains documentary evidence, not an accounting conclusion."
    )
    lines.append(
        "  No source is additive by default."
    )

    report = "\n".join(
        lines
    )

    REPORT_TXT.write_text(
        report,
        encoding="utf-8",
    )

    print(report)
    print("")
    print("Evidence written:")

    for path in [
        INVENTORY_CSV,
        FIELD_EVIDENCE_CSV,
        PERIOD_MATRIX_CSV,
        CHECKS_CSV,
        REPORT_TXT,
    ]:
        print(
            f"  {path.relative_to(REPO_ROOT)}"
        )

    return (
        0
        if overall_pass
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
