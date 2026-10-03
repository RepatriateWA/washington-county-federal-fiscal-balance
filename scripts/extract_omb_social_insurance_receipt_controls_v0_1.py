from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


# =============================================================================
# ETL-172F-2C
# OMB HISTORICAL TABLE 2.4 NATIONAL SOCIAL-INSURANCE RECEIPT CONTROLS
#
# Purpose:
#   Extract and certify FY2015-FY2024 national OASI, DI, and HI receipt controls
#   from the preserved FY2027 OMB Historical Table 2.4 workbook.
#
# Boundaries:
#   - National controls only.
#   - No Washington allocation.
#   - No SSA allocation shares.
#   - No 2024 SSA carry-forward.
#   - No Rockefeller reconstruction.
#   - No database writes.
#   - No federal-receipts ledger inclusion.
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
    / "BUDGET-2027-TAB-3-4.xlsx"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "social_insurance_receipt_controls_v0_1"
)

EXTRACT_CSV = OUTPUT_DIR / "national_social_insurance_receipt_controls.csv"
CERTIFICATION_JSON = OUTPUT_DIR / "certification.json"
CERTIFICATION_REPORT = OUTPUT_DIR / "certification_report.txt"

EXPECTED_SHA256 = (
    "21D071576D5627A18C3F62DE86BFC7FA"
    "ECED1A68265F2DB87B4F737B2773C5BD"
)

EXPECTED_SHEET = "Table"

YEAR_HEADER_ROW = 3

TARGET_START_YEAR = 2015
TARGET_END_YEAR = 2024
TARGET_YEARS = list(
    range(
        TARGET_START_YEAR,
        TARGET_END_YEAR + 1,
    )
)

SOURCE_UNIT = "millions of dollars"
DOLLAR_MULTIPLIER = Decimal("1000000")

EXPECTED_FIRST_ESTIMATE_YEAR = 2026

SERIES_SPEC = {
    "OASI": {
        "row": 8,
        "expected_label": "Trust funds (Off-Budget)",
        "parent_row": 6,
        "expected_parent_label": "Old-age and survivors insurance:",
        "budget_status": "OFF_BUDGET",
    },
    "DI": {
        "row": 9,
        "expected_label": "Disability insurance (Off-Budget)",
        "parent_row": None,
        "expected_parent_label": None,
        "budget_status": "OFF_BUDGET",
    },
    "HI": {
        "row": 10,
        "expected_label": "Hospital insurance",
        "parent_row": None,
        "expected_parent_label": None,
        "budget_status": "ON_BUDGET_UNLESS_OTHERWISE_NOTED",
    },
}

EXPECTED_OBSERVATION_COUNT = (
    len(TARGET_YEARS)
    * len(SERIES_SPEC)
)


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

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def parse_year_header(value: Any) -> tuple[int | None, str]:
    """
    Return:
        (year, status)

    status is one of:
        ACTUAL_OR_HISTORICAL
        ESTIMATE
        NOT_YEAR
    """

    if value is None:
        return None, "NOT_YEAR"

    if isinstance(value, bool):
        return None, "NOT_YEAR"

    if isinstance(value, int):
        if 1900 <= value <= 2200:
            return value, "ACTUAL_OR_HISTORICAL"
        return None, "NOT_YEAR"

    if isinstance(value, float):
        if value.is_integer():
            year = int(value)

            if 1900 <= year <= 2200:
                return year, "ACTUAL_OR_HISTORICAL"

        return None, "NOT_YEAR"

    text = normalize_text(value)

    plain_match = re.fullmatch(
        r"(19|20|21)\d{2}",
        text,
    )

    if plain_match:
        return int(text), "ACTUAL_OR_HISTORICAL"

    estimate_match = re.fullmatch(
        r"((?:19|20|21)\d{2})\s+Estimate",
        text,
        flags=re.IGNORECASE,
    )

    if estimate_match:
        return (
            int(estimate_match.group(1)),
            "ESTIMATE",
        )

    return None, "NOT_YEAR"


def decimal_from_cell(value: Any) -> Decimal:
    if value is None:
        raise ValueError("Source value is NULL.")

    if isinstance(value, bool):
        raise ValueError(
            f"Boolean source value is invalid: {value!r}"
        )

    if isinstance(value, Decimal):
        result = value

    elif isinstance(value, int):
        result = Decimal(value)

    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                f"Non-finite numeric value: {value!r}"
            )

        result = Decimal(str(value))

    else:
        text = normalize_text(value).replace(",", "")

        if not text:
            raise ValueError("Source value is blank.")

        try:
            result = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(
                f"Non-numeric source value: {value!r}"
            ) from exc

    if not result.is_finite():
        raise ValueError(
            f"Non-finite Decimal value: {result!r}"
        )

    return result


def decimal_to_plain_string(value: Decimal) -> str:
    """
    Preserve exact decimal value without scientific notation.
    """

    return format(value, "f")


def certify_source() -> dict[str, Any]:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Source workbook not found: {SOURCE_FILE}"
        )

    actual_sha256 = sha256_file(SOURCE_FILE)

    if actual_sha256 != EXPECTED_SHA256:
        raise RuntimeError(
            "SOURCE HASH CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_SHA256}\n"
            f"Actual  : {actual_sha256}\n"
            "Refusing to extract from a changed source artifact."
        )

    return {
        "source_file": str(
            SOURCE_FILE.relative_to(REPO_ROOT)
        ),
        "source_bytes": SOURCE_FILE.stat().st_size,
        "source_sha256": actual_sha256,
        "source_hash_status": "PASS",
    }


def inspect_year_headers(ws) -> dict[str, Any]:
    year_columns: dict[int, int] = {}
    year_status: dict[int, str] = {}
    year_raw_headers: dict[int, str] = {}

    for column in range(
        1,
        ws.max_column + 1,
    ):
        raw_value = ws.cell(
            row=YEAR_HEADER_ROW,
            column=column,
        ).value

        year, status = parse_year_header(
            raw_value
        )

        if year is None:
            continue

        if year in year_columns:
            raise RuntimeError(
                "YEAR HEADER CERTIFICATION FAILURE\n"
                f"Duplicate year header detected: {year}"
            )

        year_columns[year] = column
        year_status[year] = status
        year_raw_headers[year] = normalize_text(
            raw_value
        )

    missing_target_years = [
        year
        for year in TARGET_YEARS
        if year not in year_columns
    ]

    if missing_target_years:
        raise RuntimeError(
            "YEAR HEADER CERTIFICATION FAILURE\n"
            "Missing target fiscal years: "
            + ", ".join(
                str(year)
                for year in missing_target_years
            )
        )

    nonhistorical_target_years = [
        year
        for year in TARGET_YEARS
        if year_status[year]
        != "ACTUAL_OR_HISTORICAL"
    ]

    if nonhistorical_target_years:
        raise RuntimeError(
            "ACTUAL/ESTIMATE CERTIFICATION FAILURE\n"
            "Target years marked as estimates: "
            + ", ".join(
                str(year)
                for year in nonhistorical_target_years
            )
        )

    estimate_years = sorted(
        year
        for year, status in year_status.items()
        if status == "ESTIMATE"
    )

    if not estimate_years:
        raise RuntimeError(
            "ACTUAL/ESTIMATE CERTIFICATION FAILURE\n"
            "No explicitly estimated years were detected."
        )

    first_estimate_year = estimate_years[0]

    if (
        first_estimate_year
        != EXPECTED_FIRST_ESTIMATE_YEAR
    ):
        raise RuntimeError(
            "ACTUAL/ESTIMATE CERTIFICATION FAILURE\n"
            "Unexpected first estimate year.\n"
            f"Expected: {EXPECTED_FIRST_ESTIMATE_YEAR}\n"
            f"Actual  : {first_estimate_year}"
        )

    if 2025 not in year_columns:
        raise RuntimeError(
            "ACTUAL/ESTIMATE CERTIFICATION FAILURE\n"
            "FY2025 header is absent; cannot confirm the "
            "historical/estimate transition observed in profiling."
        )

    if (
        year_status[2025]
        != "ACTUAL_OR_HISTORICAL"
    ):
        raise RuntimeError(
            "ACTUAL/ESTIMATE CERTIFICATION FAILURE\n"
            "FY2025 is not on the historical side of the "
            "explicit estimate boundary."
        )

    return {
        "year_columns": year_columns,
        "year_status": year_status,
        "year_raw_headers": year_raw_headers,
        "estimate_years": estimate_years,
        "first_estimate_year": first_estimate_year,
    }


def certify_units(ws) -> dict[str, str]:
    raw_units = normalize_text(
        ws["A2"].value
    )

    normalized_units = (
        raw_units
        .lower()
        .replace("(", "")
        .replace(")", "")
        .strip()
    )

    if normalized_units != "in millions of dollars":
        raise RuntimeError(
            "UNIT CERTIFICATION FAILURE\n"
            "Unexpected units in Table!A2.\n"
            "Expected semantic value: "
            "'(in millions of dollars)'\n"
            f"Actual: {raw_units!r}"
        )

    return {
        "source_units_raw": raw_units,
        "source_units_normalized": SOURCE_UNIT,
    }


def certify_series_labels(ws) -> dict[str, dict[str, Any]]:
    certified: dict[str, dict[str, Any]] = {}

    for series, spec in SERIES_SPEC.items():
        row_number = int(spec["row"])
        expected_label = str(
            spec["expected_label"]
        )

        actual_label = normalize_text(
            ws.cell(
                row=row_number,
                column=1,
            ).value
        )

        if actual_label != expected_label:
            raise RuntimeError(
                "SERIES LABEL CERTIFICATION FAILURE\n"
                f"Series       : {series}\n"
                f"Expected row : {row_number}\n"
                f"Expected     : {expected_label!r}\n"
                f"Actual       : {actual_label!r}"
            )

        parent_row = spec.get("parent_row")
        expected_parent_label = spec.get(
            "expected_parent_label"
        )

        actual_parent_label = None

        if parent_row is not None:
            actual_parent_label = normalize_text(
                ws.cell(
                    row=int(parent_row),
                    column=1,
                ).value
            )

            if (
                actual_parent_label
                != expected_parent_label
            ):
                raise RuntimeError(
                    "SERIES PARENT LABEL CERTIFICATION FAILURE\n"
                    f"Series              : {series}\n"
                    f"Expected parent row : {parent_row}\n"
                    f"Expected parent     : "
                    f"{expected_parent_label!r}\n"
                    f"Actual parent       : "
                    f"{actual_parent_label!r}"
                )

        certified[series] = {
            "row": row_number,
            "label": actual_label,
            "parent_row": parent_row,
            "parent_label": actual_parent_label,
            "budget_status": spec[
                "budget_status"
            ],
        }

    return certified

def extract_controls(
    ws,
    year_profile: dict[str, Any],
    series_profile: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    year_columns = year_profile[
        "year_columns"
    ]
    year_status = year_profile[
        "year_status"
    ]
    year_raw_headers = year_profile[
        "year_raw_headers"
    ]

    for fiscal_year in TARGET_YEARS:
        source_column = year_columns[
            fiscal_year
        ]

        for series in (
            "OASI",
            "DI",
            "HI",
        ):
            series_info = series_profile[
                series
            ]

            source_row = int(
                series_info["row"]
            )

            cell = ws.cell(
                row=source_row,
                column=source_column,
            )

            source_value_millions = (
                decimal_from_cell(
                    cell.value
                )
            )

            national_receipts_dollars = (
                source_value_millions
                * DOLLAR_MULTIPLIER
            )

            rows.append(
                {
                    "fiscal_year": fiscal_year,
                    "receipt_series": series,
                    "source_label": series_info[
                        "label"
                    ],
                    "budget_status": series_info[
                        "budget_status"
                    ],
                    "source_sheet": ws.title,
                    "source_cell": cell.coordinate,
                    "source_year_header": (
                        year_raw_headers[
                            fiscal_year
                        ]
                    ),
                    "source_year_status": (
                        year_status[
                            fiscal_year
                        ]
                    ),
                    "source_units": SOURCE_UNIT,
                    "source_value_millions": (
                        decimal_to_plain_string(
                            source_value_millions
                        )
                    ),
                    "normalization_multiplier": (
                        decimal_to_plain_string(
                            DOLLAR_MULTIPLIER
                        )
                    ),
                    "national_receipts_dollars": (
                        decimal_to_plain_string(
                            national_receipts_dollars
                        )
                    ),
                }
            )

    return rows


def certify_extract(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if (
        len(rows)
        != EXPECTED_OBSERVATION_COUNT
    ):
        raise RuntimeError(
            "OBSERVATION COUNT CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_OBSERVATION_COUNT}\n"
            f"Actual  : {len(rows)}"
        )

    expected_keys = {
        (year, series)
        for year in TARGET_YEARS
        for series in SERIES_SPEC
    }

    actual_keys = {
        (
            int(row["fiscal_year"]),
            str(row["receipt_series"]),
        )
        for row in rows
    }

    if len(actual_keys) != len(rows):
        raise RuntimeError(
            "UNIQUENESS CERTIFICATION FAILURE\n"
            "Duplicate fiscal-year / receipt-series "
            "observations detected."
        )

    missing_keys = sorted(
        expected_keys - actual_keys
    )

    unexpected_keys = sorted(
        actual_keys - expected_keys
    )

    if missing_keys or unexpected_keys:
        raise RuntimeError(
            "COVERAGE CERTIFICATION FAILURE\n"
            f"Missing keys    : {missing_keys}\n"
            f"Unexpected keys : {unexpected_keys}"
        )

    per_series_counts = {
        series: sum(
            1
            for row in rows
            if row["receipt_series"]
            == series
        )
        for series in SERIES_SPEC
    }

    for series, count in (
        per_series_counts.items()
    ):
        if count != len(TARGET_YEARS):
            raise RuntimeError(
                "SERIES COVERAGE CERTIFICATION FAILURE\n"
                f"{series}: expected "
                f"{len(TARGET_YEARS)}, got {count}"
            )

    return {
        "expected_observations": (
            EXPECTED_OBSERVATION_COUNT
        ),
        "actual_observations": len(rows),
        "coverage_status": "PASS",
        "uniqueness_status": "PASS",
        "per_series_counts": (
            per_series_counts
        ),
    }


def write_extract_csv(
    rows: list[dict[str, Any]],
) -> None:
    fieldnames = [
        "fiscal_year",
        "receipt_series",
        "source_label",
        "budget_status",
        "source_sheet",
        "source_cell",
        "source_year_header",
        "source_year_status",
        "source_units",
        "source_value_millions",
        "normalization_multiplier",
        "national_receipts_dollars",
    ]

    with EXTRACT_CSV.open(
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


def build_report(
    source_profile: dict[str, Any],
    units_profile: dict[str, Any],
    year_profile: dict[str, Any],
    series_profile: dict[str, Any],
    extract_profile: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    lines.extend(
        [
            "=" * 100,
            (
                "OMB NATIONAL SOCIAL-INSURANCE "
                "RECEIPT CONTROLS - ETL-172F-2C"
            ),
            "=" * 100,
            "",
            (
                "National control extraction and "
                "certification only. No Washington "
                "allocation, SSA-share application, "
                "Rockefeller reconstruction, DB writes, "
                "or receipts-ledger inclusion."
            ),
            "",
            "SOURCE CERTIFICATION",
            "-" * 100,
            (
                f"Source : "
                f"{source_profile['source_file']}"
            ),
            (
                f"Bytes  : "
                f"{source_profile['source_bytes']:,}"
            ),
            (
                f"SHA256 : "
                f"{source_profile['source_sha256']}"
            ),
            (
                f"Hash   : "
                f"{source_profile['source_hash_status']}"
            ),
            "",
            "SEMANTIC CERTIFICATION",
            "-" * 100,
            (
                f"Sheet                    : "
                f"{EXPECTED_SHEET}"
            ),
            (
                f"Source units             : "
                f"{units_profile['source_units_raw']}"
            ),
            (
                f"Normalized source units  : "
                f"{SOURCE_UNIT}"
            ),
            (
                f"Target fiscal years      : "
                f"{TARGET_START_YEAR}-"
                f"{TARGET_END_YEAR}"
            ),
            (
                f"First explicit estimate  : "
                f"{year_profile['first_estimate_year']}"
            ),
            (
                "Target-year status       : "
                "HISTORICAL / ACTUAL SIDE OF "
                "EXPLICIT ESTIMATE BOUNDARY"
            ),
            "",
        ]
    )

    for series in (
        "OASI",
        "DI",
        "HI",
    ):
        item = series_profile[
            series
        ]

        lines.append(
            f"{series:<5} row={item['row']:<3} "
            f"label={item['label']!r} "
            f"budget_status={item['budget_status']}"
        )

    lines.extend(
        [
            "",
            "EXTRACTION CERTIFICATION",
            "-" * 100,
            (
                f"Expected observations : "
                f"{extract_profile['expected_observations']}"
            ),
            (
                f"Actual observations   : "
                f"{extract_profile['actual_observations']}"
            ),
            (
                f"Coverage              : "
                f"{extract_profile['coverage_status']}"
            ),
            (
                f"Uniqueness            : "
                f"{extract_profile['uniqueness_status']}"
            ),
            "",
            "EXTRACTED NATIONAL CONTROLS",
            "-" * 100,
            (
                "FY    SERIES  CELL     "
                "SOURCE_MILLIONS       "
                "NORMALIZED_DOLLARS"
            ),
            "-" * 100,
        ]
    )

    for row in rows:
        source_millions = Decimal(
            row["source_value_millions"]
        )

        normalized_dollars = Decimal(
            row["national_receipts_dollars"]
        )

        lines.append(
            f"{row['fiscal_year']:<5} "
            f"{row['receipt_series']:<7} "
            f"{row['source_cell']:<8} "
            f"{source_millions:>18,.3f} "
            f"{normalized_dollars:>24,.0f}"
        )

    lines.extend(
        [
            "",
            "INTERPRETATION BOUNDARY",
            "-" * 100,
            (
                "PASS certifies source identity, "
                "semantic row identity, units, "
                "year coverage, historical-side status, "
                "numeric extraction, normalization, "
                "coverage, and uniqueness."
            ),
            (
                "PASS does not establish Washington's "
                "share of these national receipts."
            ),
            (
                "PASS does not apply SSA OASDI or HI "
                "contribution shares."
            ),
            (
                "PASS does not authorize a FY2024 "
                "SSA carry-forward assumption."
            ),
            (
                "PASS does not reproduce or validate "
                "Rockefeller state receipt estimates."
            ),
            (
                "PASS does not authorize federal "
                "receipts-ledger inclusion."
            ),
            "",
            "ETL-172F-2C RESULT: PASS",
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
        "OMB NATIONAL SOCIAL-INSURANCE "
        "RECEIPT CONTROLS - ETL-172F-2C"
    )
    print("=" * 100)
    print()
    print(
        "National control extraction and certification "
        "only. No Washington allocation, SSA-share "
        "application, Rockefeller reconstruction, "
        "DB writes, or receipts-ledger inclusion."
    )
    print()

    source_profile = certify_source()

    wb = load_workbook(
        SOURCE_FILE,
        read_only=False,
        data_only=True,
    )

    try:
        if EXPECTED_SHEET not in wb.sheetnames:
            raise RuntimeError(
                "SHEET CERTIFICATION FAILURE\n"
                f"Expected sheet: {EXPECTED_SHEET!r}\n"
                f"Available sheets: {wb.sheetnames}"
            )

        ws = wb[EXPECTED_SHEET]

        units_profile = certify_units(ws)
        year_profile = inspect_year_headers(ws)
        series_profile = certify_series_labels(ws)

        rows = extract_controls(
            ws,
            year_profile,
            series_profile,
        )

        extract_profile = certify_extract(
            rows
        )

    finally:
        wb.close()

    write_extract_csv(rows)

    certification = {
        "etl_step": "ETL-172F-2C",
        "result": "PASS",
        "purpose": (
            "Extract and certify FY2015-FY2024 "
            "national OASI, DI, and HI receipt controls "
            "from OMB Historical Table 2.4."
        ),
        "source": source_profile,
        "units": units_profile,
        "target_fiscal_years": TARGET_YEARS,
        "first_explicit_estimate_year": (
            year_profile[
                "first_estimate_year"
            ]
        ),
        "target_year_status": (
            "HISTORICAL_ACTUAL_SIDE_OF_ESTIMATE_BOUNDARY"
        ),
        "series": series_profile,
        "extraction": extract_profile,
        "normalization": {
            "source_units": SOURCE_UNIT,
            "target_units": "dollars",
            "multiplier": (
                decimal_to_plain_string(
                    DOLLAR_MULTIPLIER
                )
            ),
        },
        "interpretation_boundary": {
            "washington_allocation": False,
            "ssa_shares_applied": False,
            "ssa_2024_carry_forward_authorized": False,
            "rockefeller_reconstruction": False,
            "database_writes": False,
            "ledger_inclusion_authorized": False,
        },
    }

    CERTIFICATION_JSON.write_text(
        json.dumps(
            certification,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        source_profile,
        units_profile,
        year_profile,
        series_profile,
        extract_profile,
        rows,
    )

    CERTIFICATION_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print("SOURCE CERTIFICATION")
    print("-" * 100)
    print(
        f"Source : {source_profile['source_file']}"
    )
    print(
        f"Bytes  : {source_profile['source_bytes']:,}"
    )
    print(
        f"SHA256 : {source_profile['source_sha256']}"
    )
    print("Hash   : PASS")
    print()

    print("SEMANTIC CERTIFICATION")
    print("-" * 100)
    print(
        f"Sheet                  : {EXPECTED_SHEET}"
    )
    print(
        f"Units                  : "
        f"{units_profile['source_units_raw']}"
    )
    print(
        f"Target fiscal years    : "
        f"{TARGET_START_YEAR}-{TARGET_END_YEAR}"
    )
    print(
        f"First explicit estimate: "
        f"{year_profile['first_estimate_year']}"
    )
    print()

    for series in (
        "OASI",
        "DI",
        "HI",
    ):
        item = series_profile[
            series
        ]

        print(
            f"{series:<5} "
            f"row={item['row']:<3} "
            f"{item['label']}"
        )

    print()
    print("EXTRACTION CERTIFICATION")
    print("-" * 100)
    print(
        f"Expected observations : "
        f"{extract_profile['expected_observations']}"
    )
    print(
        f"Actual observations   : "
        f"{extract_profile['actual_observations']}"
    )
    print(
        f"Coverage              : "
        f"{extract_profile['coverage_status']}"
    )
    print(
        f"Uniqueness            : "
        f"{extract_profile['uniqueness_status']}"
    )
    print()

    print("NATIONAL CONTROLS")
    print("-" * 100)
    print(
        f"{'FY':<6}"
        f"{'SERIES':<9}"
        f"{'CELL':<9}"
        f"{'SOURCE $M':>16}"
        f"{'DOLLARS':>24}"
    )

    for row in rows:
        source_millions = Decimal(
            row["source_value_millions"]
        )

        normalized_dollars = Decimal(
            row["national_receipts_dollars"]
        )

        print(
            f"{row['fiscal_year']:<6}"
            f"{row['receipt_series']:<9}"
            f"{row['source_cell']:<9}"
            f"{source_millions:>16,.3f}"
            f"{normalized_dollars:>24,.0f}"
        )

    print()
    print(
        f"Extract : "
        f"{EXTRACT_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"JSON    : "
        f"{CERTIFICATION_JSON.relative_to(REPO_ROOT)}"
    )
    print(
        f"Report  : "
        f"{CERTIFICATION_REPORT.relative_to(REPO_ROOT)}"
    )
    print()
    print("ETL-172F-2C RESULT: PASS")

    return 0


if __name__ == "__main__":
    sys.exit(main())