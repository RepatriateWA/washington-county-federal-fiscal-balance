"""
WCFFBP
CMS MSSP Settlement Field Definition Precision Extractor v0.1

PURPOSE
-------
Extract precise documentary evidence for MSSP settlement-related fields
from the already-preserved CMS performance-results documentation package.

This is a READ-ONLY evidence extractor.

Primary fields:
    EarnSaveLoss
    GenSaveLoss
    Adv_Pay
    Adv_Pay_Amt
    Adv_Pay_Recoup
    AIM
    AIP
    AIPBalance
    AIPRecoup
    AIPOwe

The extractor preserves:
    - archive member
    - document SHA-256
    - archive-path period
    - page number
    - exact field searched
    - matched text
    - compact documentary context

It does NOT:
    - infer a settlement formula;
    - infer additivity;
    - net advances or recoupments;
    - infer payment timing;
    - infer Washington incidence;
    - write to PostgreSQL;
    - alter the principal ledger.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import Counter
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
    / "settlement_field_definitions_v0_1"
)

DEFINITIONS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_field_definitions_v0_1.csv"
)

PERIOD_FIELD_MATRIX_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_period_field_matrix_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_field_definition_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_mssp_settlement_field_definition_report_v0_1.txt"
)


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


def normalize_page_text(value: str | None) -> str:
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
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
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


def infer_period_from_path(
    member_name: str,
) -> str:
    text = member_name.replace(
        "\\",
        "/",
    ).lower()

    if (
        "2019_off-cycle_1" in text
        or "2019_off_cycle_1" in text
        or "2019a" in text
    ):
        return "2019A"

    for year in range(
        2015,
        2025,
    ):
        if re.search(
            rf"(?<!\d){year}(?!\d)",
            text,
        ):
            return str(year)

    return "UNRESOLVED"


def is_dictionary(
    member_name: str,
    first_pages_text: str,
) -> bool:
    combined = (
        member_name
        + "\n"
        + first_pages_text
    ).lower()

    return (
        "data dictionary" in combined
        or "dictionary" in member_name.lower()
    )


def exact_field_pattern(
    field: str,
) -> re.Pattern:
    return re.compile(
        rf"(?<![A-Za-z0-9_])"
        rf"{re.escape(field)}"
        rf"(?![A-Za-z0-9_])",
        flags=re.IGNORECASE,
    )


def extract_context(
    page_text: str,
    match_start: int,
    match_end: int,
) -> str:
    """
    Extract a relatively tight documentary window.

    Preference:
        surrounding lines first;
        bounded character context second.

    This is evidence extraction, not semantic interpretation.
    """
    lines = page_text.splitlines()

    running = 0
    matched_line = None

    for index, line in enumerate(lines):
        next_running = (
            running
            + len(line)
            + 1
        )

        if (
            running
            <= match_start
            < next_running
        ):
            matched_line = index
            break

        running = next_running

    if matched_line is not None:
        left = max(
            0,
            matched_line - 2,
        )

        right = min(
            len(lines),
            matched_line + 7,
        )

        line_context = compact_text(
            "\n".join(
                lines[left:right]
            )
        )

        if len(line_context) >= 80:
            return line_context

    left = max(
        0,
        match_start - 250,
    )

    right = min(
        len(page_text),
        match_end + 1000,
    )

    return compact_text(
        page_text[left:right]
    )


def classify_context(
    field: str,
    context: str,
) -> dict[str, str]:
    """
    Mechanical terminology flags only.

    These flags are NOT accounting conclusions.
    """
    lower = context.lower()

    return {
        "mentions_shared_savings": (
            "YES"
            if "shared savings" in lower
            else "NO"
        ),
        "mentions_shared_losses": (
            "YES"
            if "shared loss" in lower
            else "NO"
        ),
        "mentions_sequestration": (
            "YES"
            if "sequestration" in lower
            else "NO"
        ),
        "mentions_payment_limit": (
            "YES"
            if "payment limit" in lower
            else "NO"
        ),
        "mentions_advance_payment": (
            "YES"
            if "advance payment" in lower
            else "NO"
        ),
        "mentions_aim": (
            "YES"
            if re.search(
                r"\bAIM\b",
                context,
                flags=re.IGNORECASE,
            )
            else "NO"
        ),
        "mentions_aip": (
            "YES"
            if re.search(
                r"\bAIP\b",
                context,
                flags=re.IGNORECASE,
            )
            else "NO"
        ),
        "mentions_recoup": (
            "YES"
            if "recoup" in lower
            else "NO"
        ),
        "mentions_does_not_account": (
            "YES"
            if "does not account" in lower
            else "NO"
        ),
        "mentions_after": (
            "YES"
            if re.search(
                r"\bafter\b",
                lower,
            )
            else "NO"
        ),
        "mentions_before": (
            "YES"
            if re.search(
                r"\bbefore\b",
                lower,
            )
            else "NO"
        ),
    }


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
    # Required source
    # ------------------------------------------------------------
    add_check(
        "Preserved MSSP documentation ZIP exists",
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
            f"FAIL: missing documentation ZIP: {DOC_ZIP}"
        )

        return 1

    # ------------------------------------------------------------
    # Extract exact field evidence
    # ------------------------------------------------------------
    evidence_rows: list[dict] = []

    parsed_pdf_count = 0
    dictionary_member_count = 0

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

                reader = PdfReader(
                    io.BytesIO(data)
                )

                pages = []

                for page_number, page in enumerate(
                    reader.pages,
                    start=1,
                ):
                    page_text = (
                        page.extract_text()
                        or ""
                    )

                    pages.append(
                        (
                            page_number,
                            normalize_page_text(
                                page_text
                            ),
                        )
                    )

                parsed_pdf_count += 1

                first_pages_text = "\n".join(
                    text
                    for _, text
                    in pages[:3]
                )

                if not is_dictionary(
                    info.filename,
                    first_pages_text,
                ):
                    continue

                dictionary_member_count += 1

                period = infer_period_from_path(
                    info.filename
                )

                for (
                    page_number,
                    page_text,
                ) in pages:
                    if not page_text:
                        continue

                    for field in TARGET_FIELDS:
                        pattern = (
                            exact_field_pattern(
                                field
                            )
                        )

                        matches = list(
                            pattern.finditer(
                                page_text
                            )
                        )

                        for occurrence_number, match in enumerate(
                            matches,
                            start=1,
                        ):
                            context = extract_context(
                                page_text,
                                match.start(),
                                match.end(),
                            )

                            flags = classify_context(
                                field,
                                context,
                            )

                            row = {
                                "performance_period": period,
                                "field_name": field,
                                "member_name": info.filename,
                                "document_sha256": digest,
                                "page": page_number,
                                "occurrence_on_page": occurrence_number,
                                "matched_text": match.group(
                                    0
                                ),
                                "context": context,
                            }

                            row.update(
                                flags
                            )

                            evidence_rows.append(
                                row
                            )

            except Exception as exc:
                errors.append(
                    f"{info.filename}: {exc}"
                )

    add_check(
        "All documentation PDFs parse",
        len(errors) == 0,
        (
            f"{parsed_pdf_count} PDFs parsed; "
            f"{len(errors)} failures"
        ),
    )

    add_check(
        "Documentation package reproduces 22 PDF members",
        parsed_pdf_count == 22,
        f"{parsed_pdf_count}/22",
    )

    add_check(
        "Dictionary members discovered",
        dictionary_member_count > 0,
        f"{dictionary_member_count} dictionary archive members",
    )

    # ------------------------------------------------------------
    # Deduplicate byte-identical dictionary evidence
    #
    # The archive intentionally contains repeated copies of older
    # dictionaries. Preserve source-member provenance in raw evidence,
    # but construct the analytical matrix from unique document SHA /
    # period / field / page / context observations.
    # ------------------------------------------------------------
    deduped_rows = []
    seen = set()

    for row in evidence_rows:
        key = (
            row[
                "performance_period"
            ],
            row[
                "field_name"
            ],
            row[
                "document_sha256"
            ],
            row[
                "page"
            ],
            row[
                "context"
            ],
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        deduped_rows.append(
            row
        )

    # ------------------------------------------------------------
    # Matrix
    # ------------------------------------------------------------
    matrix_rows = []

    for period in EXPECTED_PERIODS:
        period_rows = [
            row
            for row in deduped_rows
            if row[
                "performance_period"
            ]
            == period
        ]

        for field in TARGET_FIELDS:
            field_rows = [
                row
                for row in period_rows
                if row[
                    "field_name"
                ]
                == field
            ]

            matrix_rows.append(
                {
                    "performance_period": period,
                    "field_name": field,
                    "documented": (
                        "YES"
                        if field_rows
                        else "NO"
                    ),
                    "definition_observations": len(
                        field_rows
                    ),
                    "unique_document_count": len(
                        {
                            row[
                                "document_sha256"
                            ]
                            for row in field_rows
                        }
                    ),
                    "pages": ";".join(
                        sorted(
                            {
                                str(
                                    row[
                                        "page"
                                    ]
                                )
                                for row
                                in field_rows
                            },
                            key=lambda x: int(
                                x
                            ),
                        )
                    ),
                    "mentions_shared_savings": (
                        "YES"
                        if any(
                            row[
                                "mentions_shared_savings"
                            ]
                            == "YES"
                            for row
                            in field_rows
                        )
                        else "NO"
                    ),
                    "mentions_shared_losses": (
                        "YES"
                        if any(
                            row[
                                "mentions_shared_losses"
                            ]
                            == "YES"
                            for row
                            in field_rows
                        )
                        else "NO"
                    ),
                    "mentions_sequestration": (
                        "YES"
                        if any(
                            row[
                                "mentions_sequestration"
                            ]
                            == "YES"
                            for row
                            in field_rows
                        )
                        else "NO"
                    ),
                    "mentions_payment_limit": (
                        "YES"
                        if any(
                            row[
                                "mentions_payment_limit"
                            ]
                            == "YES"
                            for row
                            in field_rows
                        )
                        else "NO"
                    ),
                    "mentions_recoup": (
                        "YES"
                        if any(
                            row[
                                "mentions_recoup"
                            ]
                            == "YES"
                            for row
                            in field_rows
                        )
                        else "NO"
                    ),
                    "mentions_does_not_account": (
                        "YES"
                        if any(
                            row[
                                "mentions_does_not_account"
                            ]
                            == "YES"
                            for row
                            in field_rows
                        )
                        else "NO"
                    ),
                }
            )

    # ------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------
    period_field_counts = Counter(
        (
            row[
                "performance_period"
            ],
            row[
                "field_name"
            ],
        )
        for row in deduped_rows
    )

    earn_periods = [
        period
        for period in EXPECTED_PERIODS
        if period_field_counts[
            (
                period,
                "EarnSaveLoss",
            )
        ]
        > 0
    ]

    gen_periods = [
        period
        for period in EXPECTED_PERIODS
        if period_field_counts[
            (
                period,
                "GenSaveLoss",
            )
        ]
        > 0
    ]

    add_check(
        "EarnSaveLoss exact field evidence found for all 11 periods",
        set(
            earn_periods
        )
        == set(
            EXPECTED_PERIODS
        ),
        f"{len(earn_periods)}/11",
    )

    add_check(
        "GenSaveLoss exact field evidence found for all 11 periods",
        set(
            gen_periods
        )
        == set(
            EXPECTED_PERIODS
        ),
        f"{len(gen_periods)}/11",
    )

    historical_advance_fields = {
        "Adv_Pay",
        "Adv_Pay_Amt",
        "Adv_Pay_Recoup",
        "AIM",
    }

    historical_periods_with_advance = {
        period
        for period in EXPECTED_PERIODS
        if any(
            period_field_counts[
                (
                    period,
                    field,
                )
            ]
            > 0
            for field
            in historical_advance_fields
        )
    }

    add_check(
        "Historical advance/AIM field evidence appears through 2021",
        {
            "2015",
            "2016",
            "2017",
            "2018",
            "2019",
            "2019A",
            "2020",
            "2021",
        }.issubset(
            historical_periods_with_advance
        ),
        ",".join(
            sorted(
                historical_periods_with_advance
            )
        ),
    )

    aip_fields = {
        "AIP",
        "AIPBalance",
        "AIPRecoup",
        "AIPOwe",
    }

    periods_with_aip = {
        period
        for period in EXPECTED_PERIODS
        if any(
            period_field_counts[
                (
                    period,
                    field,
                )
            ]
            > 0
            for field
            in aip_fields
        )
    }

    add_check(
        "AIP field evidence is present for 2024",
        "2024" in periods_with_aip,
        ",".join(
            sorted(
                periods_with_aip
            )
        )
        or "NONE",
    )

    add_check(
        "Precision evidence extracted",
        len(
            deduped_rows
        )
        > 0,
        (
            f"{len(evidence_rows)} raw exact-field observations; "
            f"{len(deduped_rows)} deduplicated observations"
        ),
    )

    # ------------------------------------------------------------
    # Write evidence
    # ------------------------------------------------------------
    evidence_fields = [
        "performance_period",
        "field_name",
        "member_name",
        "document_sha256",
        "page",
        "occurrence_on_page",
        "matched_text",
        "context",
        "mentions_shared_savings",
        "mentions_shared_losses",
        "mentions_sequestration",
        "mentions_payment_limit",
        "mentions_advance_payment",
        "mentions_aim",
        "mentions_aip",
        "mentions_recoup",
        "mentions_does_not_account",
        "mentions_after",
        "mentions_before",
    ]

    write_csv(
        DEFINITIONS_CSV,
        evidence_fields,
        deduped_rows,
    )

    write_csv(
        PERIOD_FIELD_MATRIX_CSV,
        [
            "performance_period",
            "field_name",
            "documented",
            "definition_observations",
            "unique_document_count",
            "pages",
            "mentions_shared_savings",
            "mentions_shared_losses",
            "mentions_sequestration",
            "mentions_payment_limit",
            "mentions_recoup",
            "mentions_does_not_account",
        ],
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
            check[
                "status"
            ]
            == "PASS"
            for check in checks
        )
    )

    # ------------------------------------------------------------
    # Human-readable report
    # ------------------------------------------------------------
    lines: list[str] = []

    lines.append(
        "=" * 112
    )
    lines.append(
        "CMS MSSP SETTLEMENT FIELD DEFINITION PRECISION EXTRACTION v0.1"
    )
    lines.append(
        "=" * 112
    )
    lines.append("")

    lines.append(
        "BOUNDARY"
    )
    lines.append(
        "-" * 112
    )
    lines.append(
        "READ-ONLY extraction of exact named-field evidence from preserved CMS MSSP data dictionaries."
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
        "No payment timing inferred."
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

    lines.append(
        "SOURCE"
    )
    lines.append(
        "-" * 112
    )
    lines.append(
        str(
            DOC_ZIP.relative_to(
                REPO_ROOT
            )
        )
    )
    lines.append(
        f"SHA-256: {sha256_file(DOC_ZIP)}"
    )
    lines.append(
        f"PDF members parsed: {parsed_pdf_count}"
    )
    lines.append(
        f"Dictionary archive members: {dictionary_member_count}"
    )
    lines.append(
        f"Raw exact-field observations: {len(evidence_rows)}"
    )
    lines.append(
        f"Deduplicated observations: {len(deduped_rows)}"
    )
    lines.append("")

    lines.append(
        "PERIOD / FIELD PROFILE"
    )
    lines.append(
        "-" * 112
    )

    for period in EXPECTED_PERIODS:
        documented_fields = [
            field
            for field in TARGET_FIELDS
            if period_field_counts[
                (
                    period,
                    field,
                )
            ]
            > 0
        ]

        lines.append(
            f"{period:<6} | "
            + (
                ", ".join(
                    documented_fields
                )
                if documented_fields
                else "NONE"
            )
        )

    lines.append("")
    lines.append(
        "HIGH-VALUE DEFINITION EVIDENCE"
    )
    lines.append(
        "-" * 112
    )

    high_value_fields = [
        "EarnSaveLoss",
        "Adv_Pay_Amt",
        "Adv_Pay_Recoup",
        "AIPBalance",
        "AIPRecoup",
        "AIPOwe",
    ]

    for period in EXPECTED_PERIODS:
        rows = [
            row
            for row in deduped_rows
            if (
                row[
                    "performance_period"
                ]
                == period
                and row[
                    "field_name"
                ]
                in high_value_fields
            )
        ]

        if not rows:
            continue

        lines.append("")
        lines.append(
            f"[{period}]"
        )

        for row in rows:
            context = row[
                "context"
            ]

            if len(context) > 900:
                context = (
                    context[:897]
                    + "..."
                )

            lines.append(
                f"{row['field_name']} | "
                f"page={row['page']} | "
                f"sha={row['document_sha256'][:12]}..."
            )

            lines.append(
                f"  {context}"
            )

    lines.append("")
    lines.append(
        "CHECKS"
    )
    lines.append(
        "-" * 112
    )

    for check in checks:
        lines.append(
            f"{check['status']} | "
            f"{check['check']} | "
            f"{check['detail']}"
        )

    if errors:
        lines.append("")
        lines.append(
            "ERRORS"
        )
        lines.append(
            "-" * 112
        )

        for error in errors:
            lines.append(
                f"FAIL | {error}"
            )

    lines.append("")
    lines.append(
        "=" * 112
    )
    lines.append(
        "OVERALL CMS MSSP SETTLEMENT FIELD DEFINITION PRECISION EXTRACTION v0.1: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )
    lines.append(
        "=" * 112
    )
    lines.append("")

    lines.append(
        "Interpretive boundary:"
    )
    lines.append(
        "  PASS means exact named-field documentary evidence was reproducibly extracted."
    )
    lines.append(
        "  PASS does not establish a settlement accounting identity."
    )
    lines.append(
        "  Documentary context must be reviewed before fields are added, subtracted, or netted."
    )
    lines.append(
        "  Absence of a field from a performance-year dictionary is not evidence of zero dollars."
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

    print(
        report
    )
    print("")
    print(
        "Evidence written:"
    )

    for path in [
        DEFINITIONS_CSV,
        PERIOD_FIELD_MATRIX_CSV,
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
    sys.exit(
        main()
    )
