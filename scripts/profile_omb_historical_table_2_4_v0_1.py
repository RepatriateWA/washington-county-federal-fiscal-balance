from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "source"
)

SOURCE_FILE = SOURCE_DIR / "BUDGET-2027-TAB-3-4.xlsx"

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "table_2_4_structural_profile_v0_1"
)

WORKBOOK_SUMMARY_CSV = OUTPUT_DIR / "workbook_summary.csv"
NONEMPTY_CELLS_CSV = OUTPUT_DIR / "nonempty_cells.csv"
SEMANTIC_HITS_CSV = OUTPUT_DIR / "semantic_hits.csv"
YEAR_ROWS_CSV = OUTPUT_DIR / "year_rows.csv"
PROFILE_JSON = OUTPUT_DIR / "profile.json"
REPORT_TXT = OUTPUT_DIR / "profile_report.txt"

EXPECTED_SHA256 = (
    "21D071576D5627A18C3F62DE86BFC7FA"
    "ECED1A68265F2DB87B4F737B2773C5BD"
)

TARGET_START_YEAR = 2015
TARGET_END_YEAR = 2024

SEMANTIC_PATTERNS = {
    "TABLE_TITLE": [
        r"composition of social insurance",
        r"social insurance and retirement receipts",
        r"excise taxes",
        r"table\s*2\.4",
    ],
    "OASI": [
        r"old[\s-]*age.*surviv",
        r"old age.*surviv",
        r"\boasi\b",
    ],
    "DI": [
        r"disability insurance",
        r"\bdisability\b",
    ],
    "HI": [
        r"hospital insurance",
        r"\bhi\b",
    ],
    "UNITS": [
        r"millions of dollars",
        r"million dollars",
        r"billions of dollars",
        r"thousands of dollars",
    ],
    "ACTUAL_ESTIMATE": [
        r"\bactual\b",
        r"\bestimate",
        r"\bestimated\b",
    ],
    "FOOTNOTE": [
        r"note:",
        r"notes:",
        r"source:",
        r"^1/",
        r"^2/",
        r"^3/",
        r"^4/",
        r"^5/",
    ],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def normalized_lower(value: Any) -> str:
    return normalize_text(value).lower()


def classify_semantic_hits(value: Any) -> list[str]:
    text = normalized_lower(value)

    if not text:
        return []

    hits: list[str] = []

    for category, patterns in SEMANTIC_PATTERNS.items():
        for pattern in patterns:
            if re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                hits.append(category)
                break

    return hits


def extract_year(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        if 1900 <= value <= 2200:
            return value
        return None

    if isinstance(value, float):
        if value.is_integer():
            year = int(value)
            if 1900 <= year <= 2200:
                return year
        return None

    text = normalize_text(value)

    match = re.fullmatch(
        r"(19|20|21)\d{2}",
        text,
    )

    if match:
        return int(text)

    return None


def value_repr(value: Any) -> str:
    if value is None:
        return ""

    return str(value)


def row_nonempty_values(ws, row_number: int) -> list[str]:
    values: list[str] = []

    for col in range(1, ws.max_column + 1):
        value = ws.cell(
            row=row_number,
            column=col,
        ).value

        text = normalize_text(value)

        if text:
            values.append(text)

    return values


def inspect_workbook() -> dict[str, Any]:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Source workbook not found: {SOURCE_FILE}"
        )

    actual_sha256 = sha256_file(SOURCE_FILE)

    if actual_sha256 != EXPECTED_SHA256:
        raise RuntimeError(
            "SHA-256 mismatch for preserved source workbook.\n"
            f"Expected: {EXPECTED_SHA256}\n"
            f"Actual  : {actual_sha256}\n"
            "Refusing to profile a changed source artifact."
        )

    wb = load_workbook(
        SOURCE_FILE,
        read_only=False,
        data_only=False,
    )

    workbook_summary: list[dict[str, Any]] = []
    nonempty_cells: list[dict[str, Any]] = []
    semantic_hits: list[dict[str, Any]] = []
    year_rows: list[dict[str, Any]] = []

    target_years_found: set[int] = set()
    all_years_found: set[int] = set()

    for ws in wb.worksheets:
        workbook_summary.append(
            {
                "sheet_name": ws.title,
                "max_row": ws.max_row,
                "max_column": ws.max_column,
                "merged_range_count": len(ws.merged_cells.ranges),
                "merged_ranges": "; ".join(
                    str(item)
                    for item in ws.merged_cells.ranges
                ),
            }
        )

        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue

                text = normalize_text(cell.value)

                if not text:
                    continue

                nonempty_cells.append(
                    {
                        "sheet_name": ws.title,
                        "coordinate": cell.coordinate,
                        "row": cell.row,
                        "column": cell.column,
                        "value": value_repr(cell.value),
                        "data_type": cell.data_type,
                        "number_format": cell.number_format,
                    }
                )

                categories = classify_semantic_hits(
                    cell.value
                )

                for category in categories:
                    semantic_hits.append(
                        {
                            "sheet_name": ws.title,
                            "coordinate": cell.coordinate,
                            "row": cell.row,
                            "column": cell.column,
                            "category": category,
                            "value": value_repr(cell.value),
                        }
                    )

        for row_number in range(
            1,
            ws.max_row + 1,
        ):
            detected_years: list[tuple[int, int]] = []

            for col in range(
                1,
                ws.max_column + 1,
            ):
                value = ws.cell(
                    row=row_number,
                    column=col,
                ).value

                year = extract_year(value)

                if year is not None:
                    detected_years.append(
                        (col, year)
                    )

            if not detected_years:
                continue

            row_values = row_nonempty_values(
                ws,
                row_number,
            )

            row_text = " | ".join(row_values)

            for col, year in detected_years:
                all_years_found.add(year)

                if (
                    TARGET_START_YEAR
                    <= year
                    <= TARGET_END_YEAR
                ):
                    target_years_found.add(year)

                year_rows.append(
                    {
                        "sheet_name": ws.title,
                        "row": row_number,
                        "year_column": col,
                        "year": year,
                        "target_period": (
                            TARGET_START_YEAR
                            <= year
                            <= TARGET_END_YEAR
                        ),
                        "row_text": row_text,
                    }
                )

    wb.close()

    semantic_counts: dict[str, int] = {}

    for row in semantic_hits:
        category = str(row["category"])
        semantic_counts[category] = (
            semantic_counts.get(category, 0) + 1
        )

    return {
        "source_file": str(
            SOURCE_FILE.relative_to(REPO_ROOT)
        ),
        "bytes": SOURCE_FILE.stat().st_size,
        "sha256": actual_sha256,
        "sheet_names": [
            row["sheet_name"]
            for row in workbook_summary
        ],
        "workbook_summary": workbook_summary,
        "nonempty_cells": nonempty_cells,
        "semantic_hits": semantic_hits,
        "semantic_counts": semantic_counts,
        "year_rows": year_rows,
        "all_years_found": sorted(all_years_found),
        "target_years_found": sorted(
            target_years_found
        ),
        "target_years_expected": list(
            range(
                TARGET_START_YEAR,
                TARGET_END_YEAR + 1,
            )
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
        writer.writerows(rows)


def build_report(profile: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.extend(
        [
            "=" * 100,
            (
                "OMB HISTORICAL TABLE 2.4 "
                "STRUCTURAL / SEMANTIC PROFILE - "
                "ETL-172F-2B"
            ),
            "=" * 100,
            "",
            (
                "Observation only. No receipt-control "
                "selection, dollar extraction into the "
                "ledger, allocation, reconciliation, "
                "or DB writes."
            ),
            "",
            "SOURCE INTEGRITY",
            "-" * 100,
            f"Source : {profile['source_file']}",
            f"Bytes  : {profile['bytes']:,}",
            f"SHA256 : {profile['sha256']}",
            "Hash   : PASS",
            "",
            "WORKBOOK STRUCTURE",
            "-" * 100,
        ]
    )

    for row in profile["workbook_summary"]:
        lines.append(
            f"{row['sheet_name']:<40} "
            f"rows={row['max_row']:<5} "
            f"cols={row['max_column']:<4} "
            f"merged={row['merged_range_count']}"
        )

    lines.extend(
        [
            "",
            "SEMANTIC HIT COUNTS",
            "-" * 100,
        ]
    )

    for category in sorted(
        SEMANTIC_PATTERNS
    ):
        count = profile[
            "semantic_counts"
        ].get(category, 0)

        lines.append(
            f"{category:<25} {count:>6}"
        )

    lines.extend(
        [
            "",
            "SEMANTIC HITS",
            "-" * 100,
        ]
    )

    if profile["semantic_hits"]:
        for row in profile["semantic_hits"]:
            lines.append(
                f"{row['sheet_name']}!"
                f"{row['coordinate']:<8} | "
                f"{row['category']:<16} | "
                f"{row['value']}"
            )
    else:
        lines.append("NONE")

    lines.extend(
        [
            "",
            "YEAR COVERAGE",
            "-" * 100,
        ]
    )

    all_years = profile["all_years_found"]

    if all_years:
        lines.append(
            f"Minimum detected year : {min(all_years)}"
        )
        lines.append(
            f"Maximum detected year : {max(all_years)}"
        )
    else:
        lines.append(
            "No standalone year cells detected."
        )

    expected = set(
        profile["target_years_expected"]
    )
    found = set(
        profile["target_years_found"]
    )

    missing = sorted(expected - found)

    lines.append(
        "Target years expected : "
        + ", ".join(
            str(year)
            for year in sorted(expected)
        )
    )

    lines.append(
        "Target years found    : "
        + (
            ", ".join(
                str(year)
                for year in sorted(found)
            )
            if found
            else "NONE"
        )
    )

    lines.append(
        "Target years missing  : "
        + (
            ", ".join(
                str(year)
                for year in missing
            )
            if missing
            else "NONE"
        )
    )

    lines.extend(
        [
            "",
            "TARGET-YEAR ROW CONTEXT",
            "-" * 100,
        ]
    )

    target_rows = [
        row
        for row in profile["year_rows"]
        if row["target_period"]
    ]

    if target_rows:
        for row in target_rows:
            lines.append(
                f"{row['year']} | "
                f"{row['sheet_name']} "
                f"row {row['row']} | "
                f"{row['row_text']}"
            )
    else:
        lines.append("NONE")

    lines.extend(
        [
            "",
            "INTERPRETATION BOUNDARY",
            "-" * 100,
            (
                "This profile establishes only the "
                "preserved workbook's structure and "
                "visible semantics."
            ),
            (
                "It does not select OASI, DI, or HI "
                "national receipt-control cells."
            ),
            (
                "It does not decide the actual/estimate "
                "boundary unless that boundary is "
                "explicitly visible in the workbook."
            ),
            (
                "It does not apply SSA Washington "
                "allocation shares."
            ),
            (
                "It does not reproduce Rockefeller "
                "receipt estimates."
            ),
            (
                "It does not authorize federal-receipts "
                "ledger inclusion."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 100)
    print(
        "OMB HISTORICAL TABLE 2.4 "
        "STRUCTURAL / SEMANTIC PROFILE - "
        "ETL-172F-2B"
    )
    print("=" * 100)
    print()
    print(
        "Observation only. No receipt-control selection, "
        "ledger extraction, allocation, reconciliation, "
        "or DB writes."
    )
    print()

    profile = inspect_workbook()

    write_csv(
        WORKBOOK_SUMMARY_CSV,
        profile["workbook_summary"],
        [
            "sheet_name",
            "max_row",
            "max_column",
            "merged_range_count",
            "merged_ranges",
        ],
    )

    write_csv(
        NONEMPTY_CELLS_CSV,
        profile["nonempty_cells"],
        [
            "sheet_name",
            "coordinate",
            "row",
            "column",
            "value",
            "data_type",
            "number_format",
        ],
    )

    write_csv(
        SEMANTIC_HITS_CSV,
        profile["semantic_hits"],
        [
            "sheet_name",
            "coordinate",
            "row",
            "column",
            "category",
            "value",
        ],
    )

    write_csv(
        YEAR_ROWS_CSV,
        profile["year_rows"],
        [
            "sheet_name",
            "row",
            "year_column",
            "year",
            "target_period",
            "row_text",
        ],
    )

    json_profile = {
        key: value
        for key, value in profile.items()
        if key not in {
            "nonempty_cells",
            "semantic_hits",
            "year_rows",
        }
    }

    PROFILE_JSON.write_text(
        json.dumps(
            json_profile,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(profile)

    REPORT_TXT.write_text(
        report,
        encoding="utf-8",
    )

    print("SOURCE INTEGRITY")
    print("-" * 100)
    print(
        f"Source : {profile['source_file']}"
    )
    print(
        f"Bytes  : {profile['bytes']:,}"
    )
    print(
        f"SHA256 : {profile['sha256']}"
    )
    print("Hash   : PASS")
    print()

    print("WORKBOOK STRUCTURE")
    print("-" * 100)

    for row in profile["workbook_summary"]:
        print(
            f"{row['sheet_name']:<40} "
            f"rows={row['max_row']:<5} "
            f"cols={row['max_column']:<4} "
            f"merged={row['merged_range_count']}"
        )

    print()
    print("SEMANTIC HIT COUNTS")
    print("-" * 100)

    for category in sorted(
        SEMANTIC_PATTERNS
    ):
        count = profile[
            "semantic_counts"
        ].get(category, 0)

        print(
            f"{category:<25} {count:>6}"
        )

    print()
    print("TARGET YEAR COVERAGE")
    print("-" * 100)

    expected = set(
        profile["target_years_expected"]
    )
    found = set(
        profile["target_years_found"]
    )
    missing = sorted(expected - found)

    print(
        "Found   : "
        + (
            ", ".join(
                str(year)
                for year in sorted(found)
            )
            if found
            else "NONE"
        )
    )

    print(
        "Missing : "
        + (
            ", ".join(
                str(year)
                for year in missing
            )
            if missing
            else "NONE"
        )
    )

    print()
    print(
        f"Workbook summary : "
        f"{WORKBOOK_SUMMARY_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"Nonempty cells   : "
        f"{NONEMPTY_CELLS_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"Semantic hits    : "
        f"{SEMANTIC_HITS_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"Year rows        : "
        f"{YEAR_ROWS_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"Profile JSON     : "
        f"{PROFILE_JSON.relative_to(REPO_ROOT)}"
    )
    print(
        f"Report           : "
        f"{REPORT_TXT.relative_to(REPO_ROOT)}"
    )
    print()

    print(
        "ETL-172F-2B RESULT: STRUCTURAL PROFILE COMPLETE"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())