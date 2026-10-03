from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


# =============================================================================
# ETL-172G-1B
# OMB HISTORICAL TABLE 2.1 STRUCTURAL / SEMANTIC PROFILE
#
# Purpose:
#   Inspect the preserved FY2027 OMB Historical Table 2.1 workbook and
#   establish its physical and semantic structure before extracting any
#   national individual-income-tax receipt controls.
#
# Boundaries:
#   - No receipt-control extraction.
#   - No Washington allocation.
#   - No IRS SOI allocator application.
#   - No Rockefeller reconstruction.
#   - No database writes.
#   - No receipts-ledger inclusion.
#
# The profiler intentionally does not assume:
#   - sheet name
#   - year-header row
#   - individual-income-tax row
#   - units row
#   - first estimate year
# =============================================================================


REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "source"
    / "BUDGET-2027-TAB-3-1.xlsx"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "table_2_1_structural_profile_v0_1"
)

EXPECTED_SHA256 = (
    "1212DA86947A71D9A0268E23D3DE789402BCFB80B308CD48A32926A65B2E7BC3"
)

TARGET_YEARS = list(range(2015, 2025))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest().upper()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value)
        .replace("\r", " ")
        .replace("\n", " ")
        .split()
    )


def classify_semantic(
    text: str,
) -> list[str]:
    """
    Broad semantic classifier.

    This is intentionally inclusive. ETL-172G-1B profiles candidate
    semantics; it does not select the final control row.
    """

    normalized = normalize_text(text)
    lower = normalized.lower()

    hits: list[str] = []

    if not normalized:
        return hits

    if (
        "table 2.1" in lower
        or "receipts by source" in lower
    ):
        hits.append("TABLE_TITLE")

    if (
        "million" in lower
        and "dollar" in lower
    ):
        hits.append("UNITS")

    if (
        "individual income" in lower
        or "individual-income" in lower
        or "individual income tax" in lower
        or "individual income taxes" in lower
    ):
        hits.append("INDIVIDUAL_INCOME_TAX")

    if (
        "corporation income" in lower
        or "corporate income" in lower
        or "corporation income tax" in lower
    ):
        hits.append("CORPORATE_INCOME_TAX")

    if (
        "social insurance" in lower
        or "retirement receipts" in lower
    ):
        hits.append("SOCIAL_INSURANCE")

    if "excise" in lower:
        hits.append("EXCISE")

    if (
        "estate" in lower
        and "gift" in lower
    ):
        hits.append("ESTATE_GIFT")

    if (
        "customs" in lower
        or "custom duties" in lower
    ):
        hits.append("CUSTOMS")

    if "other receipts" in lower:
        hits.append("OTHER_RECEIPTS")

    if (
        "total receipts" in lower
        or lower == "total"
    ):
        hits.append("TOTAL_RECEIPTS")

    if (
        "estimate" in lower
        or "estimated" in lower
        or lower.endswith(" est.")
        or lower.endswith(" estimate")
    ):
        hits.append("ACTUAL_ESTIMATE")

    if (
        "actual" in lower
        or "historical" in lower
    ):
        hits.append("ACTUAL_ESTIMATE")

    if (
        "note:" in lower
        or "notes:" in lower
        or lower.startswith("note ")
        or lower.startswith("notes ")
        or normalized.startswith("(")
    ):
        hits.append("FOOTNOTE")

    return hits


def parse_year_candidate(
    value: Any,
) -> int | None:
    """
    Conservative year detector.

    Only values that can reasonably be interpreted as four-digit years
    from 1900 through 2199 are retained.
    """

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        if 1900 <= value <= 2199:
            return value
        return None

    if isinstance(value, float):
        if (
            value.is_integer()
            and 1900 <= int(value) <= 2199
        ):
            return int(value)
        return None

    text = normalize_text(value)

    match = re.search(
        r"\b(19\d{2}|20\d{2}|21\d{2})\b",
        text,
    )

    if not match:
        return None

    return int(match.group(1))


def profile_workbook() -> dict[str, Any]:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Source workbook not found: {SOURCE_FILE}"
        )

    actual_hash = sha256_file(
        SOURCE_FILE
    )

    if actual_hash != EXPECTED_SHA256:
        raise RuntimeError(
            "SOURCE HASH CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_SHA256}\n"
            f"Actual  : {actual_hash}"
        )

    # This warning is cosmetic for these OMB workbooks.
    warnings.filterwarnings(
        "ignore",
        message=(
            "Workbook contains no default style"
        ),
    )

    workbook = load_workbook(
        SOURCE_FILE,
        data_only=False,
        read_only=False,
    )

    workbook_summary_rows: list[
        dict[str, Any]
    ] = []

    nonempty_rows: list[
        dict[str, Any]
    ] = []

    semantic_rows: list[
        dict[str, Any]
    ] = []

    year_rows: list[
        dict[str, Any]
    ] = []

    semantic_counts: Counter[str] = Counter()

    target_year_hits: dict[
        int,
        list[dict[str, Any]]
    ] = {
        year: []
        for year in TARGET_YEARS
    }

    all_year_candidates: list[int] = []

    for worksheet in workbook.worksheets:
        merged_count = len(
            worksheet.merged_cells.ranges
        )

        workbook_summary_rows.append(
            {
                "sheet_name": (
                    worksheet.title
                ),
                "max_row": (
                    worksheet.max_row
                ),
                "max_column": (
                    worksheet.max_column
                ),
                "merged_range_count": (
                    merged_count
                ),
            }
        )

        for row in worksheet.iter_rows():
            for cell in row:
                value = cell.value

                if value is None:
                    continue

                text = normalize_text(
                    value
                )

                if text == "":
                    continue

                coordinate = (
                    cell.coordinate
                )

                column_letter = (
                    get_column_letter(
                        cell.column
                    )
                )

                nonempty_rows.append(
                    {
                        "sheet_name": (
                            worksheet.title
                        ),
                        "row": cell.row,
                        "column": (
                            cell.column
                        ),
                        "column_letter": (
                            column_letter
                        ),
                        "coordinate": (
                            coordinate
                        ),
                        "value": text,
                        "python_type": (
                            type(value).__name__
                        ),
                    }
                )

                semantic_hits = (
                    classify_semantic(
                        text
                    )
                )

                for semantic in (
                    semantic_hits
                ):
                    semantic_counts[
                        semantic
                    ] += 1

                    semantic_rows.append(
                        {
                            "sheet_name": (
                                worksheet.title
                            ),
                            "row": (
                                cell.row
                            ),
                            "column": (
                                cell.column
                            ),
                            "coordinate": (
                                coordinate
                            ),
                            "semantic": (
                                semantic
                            ),
                            "value": text,
                        }
                    )

                year = (
                    parse_year_candidate(
                        value
                    )
                )

                if year is not None:
                    all_year_candidates.append(
                        year
                    )

                    record = {
                        "sheet_name": (
                            worksheet.title
                        ),
                        "row": (
                            cell.row
                        ),
                        "column": (
                            cell.column
                        ),
                        "coordinate": (
                            coordinate
                        ),
                        "year": year,
                        "value": text,
                    }

                    year_rows.append(
                        record
                    )

                    if (
                        year
                        in target_year_hits
                    ):
                        target_year_hits[
                            year
                        ].append(
                            record
                        )

    profile = {
        "etl_step": (
            "ETL-172G-1B"
        ),
        "source": {
            "path": str(
                SOURCE_FILE.relative_to(
                    REPO_ROOT
                )
            ),
            "bytes": (
                SOURCE_FILE.stat().st_size
            ),
            "sha256_expected": (
                EXPECTED_SHA256
            ),
            "sha256_actual": (
                actual_hash
            ),
            "hash_status": "PASS",
        },
        "workbook": {
            "sheet_names": (
                workbook.sheetnames
            ),
            "sheet_count": (
                len(
                    workbook.sheetnames
                )
            ),
        },
        "semantic_counts": dict(
            sorted(
                semantic_counts.items()
            )
        ),
        "year_candidate_summary": {
            "minimum": (
                min(all_year_candidates)
                if all_year_candidates
                else None
            ),
            "maximum": (
                max(all_year_candidates)
                if all_year_candidates
                else None
            ),
            "target_year_hit_counts": {
                str(year): len(
                    target_year_hits[
                        year
                    ]
                )
                for year in TARGET_YEARS
            },
        },
        "interpretation_boundary": {
            "national_control_selected": (
                False
            ),
            "washington_allocation": (
                False
            ),
            "irs_allocator_applied": (
                False
            ),
            "rockefeller_reconstruction": (
                False
            ),
            "database_writes": False,
            "ledger_inclusion_authorized": (
                False
            ),
        },
    }

    return {
        "profile": profile,
        "workbook_summary_rows": (
            workbook_summary_rows
        ),
        "nonempty_rows": (
            nonempty_rows
        ),
        "semantic_rows": (
            semantic_rows
        ),
        "year_rows": (
            year_rows
        ),
        "target_year_hits": (
            target_year_hits
        ),
    }


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
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

        if rows:
            writer.writerows(
                rows
            )


def build_report(
    result: dict[str, Any],
) -> str:
    profile = result["profile"]

    lines: list[str] = []

    lines.extend(
        [
            "=" * 100,
            (
                "OMB HISTORICAL TABLE 2.1 "
                "STRUCTURAL / SEMANTIC PROFILE "
                "- ETL-172G-1B"
            ),
            "=" * 100,
            "",
            (
                "Profile only. No national-control "
                "selection, Washington allocation, "
                "IRS allocator application, Rockefeller "
                "reconstruction, DB writes, or "
                "receipts-ledger inclusion."
            ),
            "",
            "SOURCE CERTIFICATION",
            "-" * 100,
            (
                "Source : "
                f"{profile['source']['path']}"
            ),
            (
                "Bytes  : "
                f"{profile['source']['bytes']:,}"
            ),
            (
                "SHA256 : "
                f"{profile['source']['sha256_actual']}"
            ),
            (
                "Hash   : "
                f"{profile['source']['hash_status']}"
            ),
            "",
            "WORKBOOK STRUCTURE",
            "-" * 100,
        ]
    )

    for row in result[
        "workbook_summary_rows"
    ]:
        lines.append(
            f"Sheet={row['sheet_name']!r} "
            f"rows={row['max_row']} "
            f"cols={row['max_column']} "
            f"merged={row['merged_range_count']}"
        )

    lines.extend(
        [
            "",
            "SEMANTIC HIT COUNTS",
            "-" * 100,
        ]
    )

    semantic_counts = (
        profile[
            "semantic_counts"
        ]
    )

    if semantic_counts:
        for semantic, count in (
            semantic_counts.items()
        ):
            lines.append(
                f"{semantic:<30} "
                f"{count:>6}"
            )
    else:
        lines.append(
            "(none)"
        )

    lines.extend(
        [
            "",
            "SEMANTIC HITS",
            "-" * 100,
        ]
    )

    if result["semantic_rows"]:
        for row in result[
            "semantic_rows"
        ]:
            lines.append(
                f"{row['sheet_name']}!"
                f"{row['coordinate']} | "
                f"{row['semantic']} | "
                f"{row['value']}"
            )
    else:
        lines.append(
            "(none)"
        )

    lines.extend(
        [
            "",
            "TARGET FISCAL-YEAR HITS",
            "-" * 100,
        ]
    )

    for year in TARGET_YEARS:
        hits = result[
            "target_year_hits"
        ][year]

        lines.append(
            f"{year}: {len(hits)} hit(s)"
        )

        for hit in hits:
            lines.append(
                f"    "
                f"{hit['sheet_name']}!"
                f"{hit['coordinate']} | "
                f"{hit['value']}"
            )

    lines.extend(
        [
            "",
            "YEAR CANDIDATE SUMMARY",
            "-" * 100,
            (
                "Minimum detected candidate : "
                f"{profile['year_candidate_summary']['minimum']}"
            ),
            (
                "Maximum detected candidate : "
                f"{profile['year_candidate_summary']['maximum']}"
            ),
            "",
            "INTERPRETATION BOUNDARY",
            "-" * 100,
            (
                "This profile establishes source integrity, "
                "workbook geometry, candidate year locations, "
                "and semantic locations only."
            ),
            (
                "It does not select a national "
                "individual-income-tax control row."
            ),
            (
                "It does not classify any study-year value "
                "as final for ETL-172G."
            ),
            (
                "It does not apply IRS SOI state shares."
            ),
            (
                "It does not authorize receipts-ledger inclusion."
            ),
            "",
            "ETL-172G-1B RESULT: PASS",
            "",
        ]
    )

    return "\n".join(
        lines
    )


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = profile_workbook()

    profile = result[
        "profile"
    ]

    write_csv(
        OUTPUT_DIR
        / "workbook_summary.csv",
        result[
            "workbook_summary_rows"
        ],
        [
            "sheet_name",
            "max_row",
            "max_column",
            "merged_range_count",
        ],
    )

    write_csv(
        OUTPUT_DIR
        / "nonempty_cells.csv",
        result[
            "nonempty_rows"
        ],
        [
            "sheet_name",
            "row",
            "column",
            "column_letter",
            "coordinate",
            "value",
            "python_type",
        ],
    )

    write_csv(
        OUTPUT_DIR
        / "semantic_hits.csv",
        result[
            "semantic_rows"
        ],
        [
            "sheet_name",
            "row",
            "column",
            "coordinate",
            "semantic",
            "value",
        ],
    )

    write_csv(
        OUTPUT_DIR
        / "year_rows.csv",
        result[
            "year_rows"
        ],
        [
            "sheet_name",
            "row",
            "column",
            "coordinate",
            "year",
            "value",
        ],
    )

    (
        OUTPUT_DIR
        / "profile.json"
    ).write_text(
        json.dumps(
            profile,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        result
    )

    (
        OUTPUT_DIR
        / "profile_report.txt"
    ).write_text(
        report,
        encoding="utf-8",
    )

    print("=" * 100)
    print(
        "OMB HISTORICAL TABLE 2.1 "
        "STRUCTURAL / SEMANTIC PROFILE "
        "- ETL-172G-1B"
    )
    print("=" * 100)
    print()
    print(
        "Profile only. No national-control selection, "
        "Washington allocation, IRS allocator application, "
        "Rockefeller reconstruction, DB writes, or "
        "receipts-ledger inclusion."
    )
    print()

    print("SOURCE CERTIFICATION")
    print("-" * 100)
    print(
        f"Source : "
        f"{profile['source']['path']}"
    )
    print(
        f"Bytes  : "
        f"{profile['source']['bytes']:,}"
    )
    print(
        f"SHA256 : "
        f"{profile['source']['sha256_actual']}"
    )
    print(
        f"Hash   : "
        f"{profile['source']['hash_status']}"
    )
    print()

    print("WORKBOOK STRUCTURE")
    print("-" * 100)

    for row in result[
        "workbook_summary_rows"
    ]:
        print(
            f"Sheet={row['sheet_name']!r} "
            f"rows={row['max_row']} "
            f"cols={row['max_column']} "
            f"merged={row['merged_range_count']}"
        )

    print()
    print("SEMANTIC HIT COUNTS")
    print("-" * 100)

    for semantic, count in (
        profile[
            "semantic_counts"
        ].items()
    ):
        print(
            f"{semantic:<30} "
            f"{count:>6}"
        )

    print()
    print("KEY SEMANTIC HITS")
    print("-" * 100)

    key_semantics = {
        "TABLE_TITLE",
        "UNITS",
        "INDIVIDUAL_INCOME_TAX",
        "ACTUAL_ESTIMATE",
        "FOOTNOTE",
    }

    key_rows = [
        row
        for row in result[
            "semantic_rows"
        ]
        if row["semantic"]
        in key_semantics
    ]

    if key_rows:
        for row in key_rows:
            print(
                f"{row['sheet_name']}!"
                f"{row['coordinate']} | "
                f"{row['semantic']} | "
                f"{row['value']}"
            )
    else:
        print(
            "(none)"
        )

    print()
    print("TARGET FISCAL YEARS")
    print("-" * 100)

    for year in TARGET_YEARS:
        hits = result[
            "target_year_hits"
        ][year]

        coordinates = ", ".join(
            (
                f"{hit['sheet_name']}!"
                f"{hit['coordinate']}"
            )
            for hit in hits
        )

        if not coordinates:
            coordinates = "(none)"

        print(
            f"{year}: "
            f"{len(hits)} hit(s) | "
            f"{coordinates}"
        )

    print()

    print(
        "Profile : "
        f"{(
            OUTPUT_DIR / 'profile_report.txt'
        ).relative_to(REPO_ROOT)}"
    )
    print(
        "Cells   : "
        f"{(
            OUTPUT_DIR / 'nonempty_cells.csv'
        ).relative_to(REPO_ROOT)}"
    )
    print(
        "Semantic: "
        f"{(
            OUTPUT_DIR / 'semantic_hits.csv'
        ).relative_to(REPO_ROOT)}"
    )
    print(
        "Years   : "
        f"{(
            OUTPUT_DIR / 'year_rows.csv'
        ).relative_to(REPO_ROOT)}"
    )
    print()
    print(
        "ETL-172G-1B RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())