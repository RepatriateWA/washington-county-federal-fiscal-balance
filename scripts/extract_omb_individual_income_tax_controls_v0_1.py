from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import warnings
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


# =============================================================================
# ETL-172G-1C
# OMB NATIONAL INDIVIDUAL-INCOME-TAX RECEIPT CONTROLS
#
# Purpose:
#   Extract and certify FY2015-FY2024 national Individual Income Taxes
#   receipts from the preserved FY2027 OMB Historical Table 2.1 workbook.
#
# Boundaries:
#   - National controls only.
#   - No Washington allocation.
#   - No IRS SOI state-share application.
#   - No Rockefeller reconstruction.
#   - No database writes.
#   - No receipts-ledger inclusion.
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
    / "individual_income_tax_receipt_controls_v0_1"
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "national_individual_income_tax_receipt_controls.csv"
)

OUTPUT_JSON = (
    OUTPUT_DIR
    / "certification.json"
)

OUTPUT_REPORT = (
    OUTPUT_DIR
    / "certification_report.txt"
)


EXPECTED_SHA256 = (
    "1212DA86947A71D9A0268E23D3DE789402BCFB80B308CD48A32926A65B2E7BC3"
)

EXPECTED_SHEET = "Table"

EXPECTED_TITLE = (
    "Table 2.1 - RECEIPTS BY SOURCE: 1934 - 2031"
)

EXPECTED_UNITS = "(in millions of dollars)"

EXPECTED_SERIES_LABEL = "Individual Income Taxes"

SERIES_COLUMN = 2       # B
SERIES_HEADER_ROW = 3

YEAR_COLUMN = 1         # A

TARGET_YEARS = list(range(2015, 2025))

EXPECTED_FIRST_ESTIMATE_YEAR = 2026

SOURCE_UNIT_MULTIPLIER = Decimal("1000000")


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


def decimal_from_cell(value: Any) -> Decimal:
    if value is None:
        raise ValueError(
            "Source value is NULL."
        )

    if isinstance(value, bool):
        raise ValueError(
            f"Boolean is not a receipt value: {value!r}"
        )

    if isinstance(value, Decimal):
        result = value

    elif isinstance(value, int):
        result = Decimal(value)

    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                f"Non-finite source value: {value!r}"
            )

        result = Decimal(str(value))

    else:
        text = (
            str(value)
            .strip()
            .replace(",", "")
        )

        if not text:
            raise ValueError(
                "Source value is blank."
            )

        try:
            result = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(
                f"Non-numeric source value: {value!r}"
            ) from exc

    if not result.is_finite():
        raise ValueError(
            f"Non-finite source value: {value!r}"
        )

    return result


def plain_decimal(value: Decimal) -> str:
    return format(value, "f")


def parse_year_label(value: Any) -> tuple[int | None, bool]:
    """
    Parse the Table 2.1 year label.

    Returns:
        (year, is_explicit_estimate)

    Examples:
        2024          -> (2024, False)
        "2026 estimate" -> (2026, True)
    """

    if value is None:
        return None, False

    if isinstance(value, bool):
        return None, False

    if isinstance(value, int):
        if 1900 <= value <= 2199:
            return value, False

        return None, False

    if isinstance(value, float):
        if (
            value.is_integer()
            and 1900 <= int(value) <= 2199
        ):
            return int(value), False

        return None, False

    text = normalize_text(value)

    if not text:
        return None, False

    lower = text.lower()

    tokens = text.split()

    if not tokens:
        return None, False

    try:
        year = int(tokens[0])
    except ValueError:
        return None, False

    if not 1900 <= year <= 2199:
        return None, False

    is_estimate = (
        "estimate" in lower
        or "estimated" in lower
    )

    return year, is_estimate


def certify_source() -> dict[str, Any]:
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

    return {
        "path": str(
            SOURCE_FILE.relative_to(
                REPO_ROOT
            )
        ),
        "bytes": SOURCE_FILE.stat().st_size,
        "sha256": actual_hash,
        "hash_status": "PASS",
    }


def load_source():
    warnings.filterwarnings(
        "ignore",
        message="Workbook contains no default style",
    )

    workbook = load_workbook(
        SOURCE_FILE,
        data_only=True,
        read_only=False,
    )

    if EXPECTED_SHEET not in workbook.sheetnames:
        raise RuntimeError(
            "WORKSHEET CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_SHEET!r}\n"
            f"Actual  : {workbook.sheetnames}"
        )

    return workbook[EXPECTED_SHEET]


def certify_semantics(ws) -> dict[str, Any]:
    title = normalize_text(
        ws["A1"].value
    )

    units = normalize_text(
        ws["A2"].value
    )

    series_label = normalize_text(
        ws.cell(
            row=SERIES_HEADER_ROW,
            column=SERIES_COLUMN,
        ).value
    )

    if title != EXPECTED_TITLE:
        raise RuntimeError(
            "TABLE TITLE CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_TITLE!r}\n"
            f"Actual  : {title!r}"
        )

    if units != EXPECTED_UNITS:
        raise RuntimeError(
            "UNITS CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_UNITS!r}\n"
            f"Actual  : {units!r}"
        )

    if series_label != EXPECTED_SERIES_LABEL:
        raise RuntimeError(
            "SERIES LABEL CERTIFICATION FAILURE\n"
            f"Expected cell : B3\n"
            f"Expected      : {EXPECTED_SERIES_LABEL!r}\n"
            f"Actual        : {series_label!r}"
        )

    return {
        "title": title,
        "units": units,
        "series_label": series_label,
        "series_header_cell": "B3",
    }


def map_year_rows(ws) -> dict[str, Any]:
    year_rows: dict[int, int] = {}
    estimate_years: list[int] = []

    for row_number in range(
        1,
        ws.max_row + 1,
    ):
        value = ws.cell(
            row=row_number,
            column=YEAR_COLUMN,
        ).value

        year, is_estimate = (
            parse_year_label(value)
        )

        if year is None:
            continue

        if year in year_rows:
            raise RuntimeError(
                "YEAR UNIQUENESS CERTIFICATION FAILURE\n"
                f"Year {year} appears more than once "
                f"in column A."
            )

        year_rows[year] = row_number

        if is_estimate:
            estimate_years.append(
                year
            )

    missing = [
        year
        for year in TARGET_YEARS
        if year not in year_rows
    ]

    if missing:
        raise RuntimeError(
            "TARGET YEAR COVERAGE FAILURE\n"
            f"Missing years: {missing}"
        )

    if not estimate_years:
        raise RuntimeError(
            "ESTIMATE BOUNDARY CERTIFICATION FAILURE\n"
            "No explicitly estimated years were found."
        )

    first_estimate_year = min(
        estimate_years
    )

    if (
        first_estimate_year
        != EXPECTED_FIRST_ESTIMATE_YEAR
    ):
        raise RuntimeError(
            "ESTIMATE BOUNDARY CERTIFICATION FAILURE\n"
            f"Expected first estimate: "
            f"{EXPECTED_FIRST_ESTIMATE_YEAR}\n"
            f"Actual first estimate  : "
            f"{first_estimate_year}"
        )

    target_estimate_years = sorted(
        set(TARGET_YEARS)
        & set(estimate_years)
    )

    if target_estimate_years:
        raise RuntimeError(
            "TARGET YEAR STATUS FAILURE\n"
            "Study years explicitly marked estimate: "
            f"{target_estimate_years}"
        )

    # FY2025 should also be on the historical side of the
    # explicit FY2026 estimate boundary in this vintage.
    if 2025 not in year_rows:
        raise RuntimeError(
            "FY2025 BOUNDARY CHECK FAILURE\n"
            "FY2025 was not found."
        )

    if 2025 in estimate_years:
        raise RuntimeError(
            "FY2025 BOUNDARY CHECK FAILURE\n"
            "FY2025 is explicitly marked estimate."
        )

    return {
        "year_rows": year_rows,
        "estimate_years": sorted(
            estimate_years
        ),
        "first_estimate_year": (
            first_estimate_year
        ),
    }


def extract_controls(
    ws,
    year_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    year_rows = year_profile[
        "year_rows"
    ]

    for fiscal_year in TARGET_YEARS:
        row_number = year_rows[
            fiscal_year
        ]

        year_cell = ws.cell(
            row=row_number,
            column=YEAR_COLUMN,
        )

        value_cell = ws.cell(
            row=row_number,
            column=SERIES_COLUMN,
        )

        source_millions = (
            decimal_from_cell(
                value_cell.value
            )
        )

        if source_millions < 0:
            raise RuntimeError(
                "NEGATIVE RECEIPT CONTROL FAILURE\n"
                f"FY{fiscal_year} "
                f"{value_cell.coordinate} = "
                f"{source_millions}"
            )

        dollars = (
            source_millions
            * SOURCE_UNIT_MULTIPLIER
        )

        output.append(
            {
                "fiscal_year": fiscal_year,
                "year_source_cell": (
                    year_cell.coordinate
                ),
                "year_source_label": (
                    normalize_text(
                        year_cell.value
                    )
                ),
                "receipt_series": (
                    "INDIVIDUAL_INCOME_TAX"
                ),
                "source_series_label": (
                    EXPECTED_SERIES_LABEL
                ),
                "source_series_header_cell": (
                    "B3"
                ),
                "source_value_cell": (
                    value_cell.coordinate
                ),
                "source_units": (
                    EXPECTED_UNITS
                ),
                "source_value_millions": (
                    plain_decimal(
                        source_millions
                    )
                ),
                "national_receipts_dollars": (
                    plain_decimal(
                        dollars
                    )
                ),
                "source_status": (
                    "HISTORICAL_SIDE_OF_"
                    "EXPLICIT_ESTIMATE_BOUNDARY"
                ),
            }
        )

    return output


def certify_extract(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_count = len(
        TARGET_YEARS
    )

    actual_count = len(
        rows
    )

    if actual_count != expected_count:
        raise RuntimeError(
            "OBSERVATION COUNT FAILURE\n"
            f"Expected: {expected_count}\n"
            f"Actual  : {actual_count}"
        )

    years = [
        int(row["fiscal_year"])
        for row in rows
    ]

    if years != TARGET_YEARS:
        raise RuntimeError(
            "YEAR ORDER/COVERAGE FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {years}"
        )

    if len(set(years)) != len(years):
        raise RuntimeError(
            "YEAR UNIQUENESS FAILURE"
        )

    cells = [
        row["source_value_cell"]
        for row in rows
    ]

    if len(set(cells)) != len(cells):
        raise RuntimeError(
            "SOURCE CELL UNIQUENESS FAILURE"
        )

    return {
        "expected_observations": (
            expected_count
        ),
        "actual_observations": (
            actual_count
        ),
        "coverage": "PASS",
        "year_uniqueness": "PASS",
        "source_cell_uniqueness": (
            "PASS"
        ),
    }


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        raise RuntimeError(
            "Refusing to write empty extract."
        )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(
                rows[0].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(rows)


def build_report(
    source_profile: dict[str, Any],
    semantic_profile: dict[str, Any],
    year_profile: dict[str, Any],
    extract_cert: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    lines.extend(
        [
            "=" * 100,
            (
                "OMB NATIONAL INDIVIDUAL-INCOME-TAX "
                "RECEIPT CONTROLS - ETL-172G-1C"
            ),
            "=" * 100,
            "",
            (
                "National control extraction and certification "
                "only. No Washington allocation, IRS SOI "
                "state-share application, Rockefeller "
                "reconstruction, DB writes, or receipts-ledger "
                "inclusion."
            ),
            "",
            "SOURCE CERTIFICATION",
            "-" * 100,
            (
                f"Source : "
                f"{source_profile['path']}"
            ),
            (
                f"Bytes  : "
                f"{source_profile['bytes']:,}"
            ),
            (
                f"SHA256 : "
                f"{source_profile['sha256']}"
            ),
            (
                f"Hash   : "
                f"{source_profile['hash_status']}"
            ),
            "",
            "SEMANTIC CERTIFICATION",
            "-" * 100,
            (
                f"Sheet                  : "
                f"{EXPECTED_SHEET}"
            ),
            (
                f"Title                  : "
                f"{semantic_profile['title']}"
            ),
            (
                f"Units                  : "
                f"{semantic_profile['units']}"
            ),
            (
                f"Series                 : "
                f"{semantic_profile['series_label']}"
            ),
            (
                f"Series header          : "
                f"{semantic_profile['series_header_cell']}"
            ),
            (
                f"Target fiscal years    : "
                f"{TARGET_YEARS[0]}-{TARGET_YEARS[-1]}"
            ),
            (
                f"First explicit estimate: "
                f"{year_profile['first_estimate_year']}"
            ),
            "",
            "EXTRACTION CERTIFICATION",
            "-" * 100,
            (
                f"Expected observations : "
                f"{extract_cert['expected_observations']}"
            ),
            (
                f"Actual observations   : "
                f"{extract_cert['actual_observations']}"
            ),
            (
                f"Coverage              : "
                f"{extract_cert['coverage']}"
            ),
            (
                f"Year uniqueness       : "
                f"{extract_cert['year_uniqueness']}"
            ),
            (
                f"Source-cell uniqueness: "
                f"{extract_cert['source_cell_uniqueness']}"
            ),
            "",
            "NATIONAL INDIVIDUAL-INCOME-TAX CONTROLS",
            "-" * 100,
            (
                f"{'FY':<6}"
                f"{'CELL':<10}"
                f"{'SOURCE $M':>20}"
                f"{'DOLLARS':>24}"
            ),
            "-" * 100,
        ]
    )

    for row in rows:
        source_millions = Decimal(
            row[
                "source_value_millions"
            ]
        )

        dollars = Decimal(
            row[
                "national_receipts_dollars"
            ]
        )

        lines.append(
            f"{row['fiscal_year']:<6}"
            f"{row['source_value_cell']:<10}"
            f"{source_millions:>20,.3f}"
            f"{dollars:>24,.0f}"
        )

    lines.extend(
        [
            "",
            "INTERPRETATION BOUNDARY",
            "-" * 100,
            (
                "These values are national federal "
                "Individual Income Taxes receipts controls "
                "from OMB Historical Table 2.1."
            ),
            (
                "FY2015-FY2024 are on the historical side "
                "of the workbook's explicit FY2026 estimate "
                "boundary."
            ),
            (
                "This step does not determine Washington's "
                "share of those receipts."
            ),
            (
                "It does not apply IRS SOI tax-liability "
                "variables A06500, A85530, or A85300."
            ),
            (
                "It does not force reconciliation to IRS "
                "state gross collections."
            ),
            (
                "It does not authorize final receipts-ledger "
                "inclusion."
            ),
            "",
            "ETL-172G-1C RESULT: PASS",
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

    print("=" * 100)
    print(
        "OMB NATIONAL INDIVIDUAL-INCOME-TAX "
        "RECEIPT CONTROLS - ETL-172G-1C"
    )
    print("=" * 100)
    print()
    print(
        "National control extraction and certification only. "
        "No Washington allocation, IRS SOI state-share "
        "application, Rockefeller reconstruction, DB writes, "
        "or receipts-ledger inclusion."
    )
    print()

    source_profile = (
        certify_source()
    )

    ws = load_source()

    semantic_profile = (
        certify_semantics(
            ws
        )
    )

    year_profile = (
        map_year_rows(
            ws
        )
    )

    rows = extract_controls(
        ws,
        year_profile,
    )

    extract_cert = (
        certify_extract(
            rows
        )
    )

    write_csv(
        OUTPUT_CSV,
        rows,
    )

    certification = {
        "etl_step": "ETL-172G-1C",
        "result": "PASS",
        "purpose": (
            "Extract and certify FY2015-FY2024 "
            "national Individual Income Taxes receipts "
            "from OMB Historical Table 2.1."
        ),
        "source": source_profile,
        "semantics": semantic_profile,
        "year_profile": {
            "first_explicit_estimate_year": (
                year_profile[
                    "first_estimate_year"
                ]
            ),
            "target_years": (
                TARGET_YEARS
            ),
            "target_year_status": (
                "HISTORICAL_SIDE_OF_"
                "EXPLICIT_ESTIMATE_BOUNDARY"
            ),
        },
        "extract_certification": (
            extract_cert
        ),
        "interpretation_boundary": {
            "washington_allocation": False,
            "irs_soi_allocator_applied": False,
            "rockefeller_reconstruction": False,
            "forced_irs_reconciliation": False,
            "database_writes": False,
            "final_ledger_inclusion_authorized": False,
        },
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            certification,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        source_profile,
        semantic_profile,
        year_profile,
        extract_cert,
        rows,
    )

    OUTPUT_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print("SOURCE CERTIFICATION")
    print("-" * 100)
    print(
        f"Source : "
        f"{source_profile['path']}"
    )
    print(
        f"Bytes  : "
        f"{source_profile['bytes']:,}"
    )
    print(
        f"SHA256 : "
        f"{source_profile['sha256']}"
    )
    print(
        f"Hash   : "
        f"{source_profile['hash_status']}"
    )
    print()

    print("SEMANTIC CERTIFICATION")
    print("-" * 100)
    print(
        f"Sheet                  : "
        f"{EXPECTED_SHEET}"
    )
    print(
        f"Units                  : "
        f"{semantic_profile['units']}"
    )
    print(
        f"Series                 : "
        f"{semantic_profile['series_label']}"
    )
    print(
        f"Series header          : "
        f"{semantic_profile['series_header_cell']}"
    )
    print(
        f"Target fiscal years    : "
        f"{TARGET_YEARS[0]}-{TARGET_YEARS[-1]}"
    )
    print(
        f"First explicit estimate: "
        f"{year_profile['first_estimate_year']}"
    )
    print()

    print("EXTRACTION CERTIFICATION")
    print("-" * 100)
    print(
        f"Expected observations : "
        f"{extract_cert['expected_observations']}"
    )
    print(
        f"Actual observations   : "
        f"{extract_cert['actual_observations']}"
    )
    print(
        f"Coverage              : "
        f"{extract_cert['coverage']}"
    )
    print(
        f"Year uniqueness       : "
        f"{extract_cert['year_uniqueness']}"
    )
    print(
        f"Source-cell uniqueness: "
        f"{extract_cert['source_cell_uniqueness']}"
    )
    print()

    print(
        "NATIONAL INDIVIDUAL-INCOME-TAX CONTROLS"
    )
    print("-" * 100)
    print(
        f"{'FY':<6}"
        f"{'CELL':<10}"
        f"{'SOURCE $M':>20}"
        f"{'DOLLARS':>24}"
    )

    for row in rows:
        source_millions = Decimal(
            row[
                "source_value_millions"
            ]
        )

        dollars = Decimal(
            row[
                "national_receipts_dollars"
            ]
        )

        print(
            f"{row['fiscal_year']:<6}"
            f"{row['source_value_cell']:<10}"
            f"{source_millions:>20,.3f}"
            f"{dollars:>24,.0f}"
        )

    print()
    print(
        f"Extract : "
        f"{OUTPUT_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"JSON    : "
        f"{OUTPUT_JSON.relative_to(REPO_ROOT)}"
    )
    print(
        f"Report  : "
        f"{OUTPUT_REPORT.relative_to(REPO_ROOT)}"
    )
    print()
    print(
        "ETL-172G-1C RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())