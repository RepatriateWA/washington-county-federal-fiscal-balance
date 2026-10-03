from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import warnings
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any

import pandas as pd


# =============================================================================
# ETL-172H-1
# OMB NATIONAL CORPORATE-INCOME-TAX RECEIPT CONTROLS
#
# Purpose:
#   Extract and certify national federal Corporation Income Taxes receipts
#   for FFY2015-FFY2024 from the already-preserved FY2027 OMB Historical
#   Table 2.1 workbook.
#
# Source:
#   OMB Historical Table 2.1 - Receipts by Source: 1934-2031
#   BUDGET-2027-TAB-3-1.xlsx
#
# Certified source structure established before this script:
#
#   Column A = Fiscal Year
#   Column B = Individual Income Taxes
#   Column C = Corporation Income Taxes (1)
#
# Units:
#   Millions of dollars.
#
# Boundaries:
#   - National receipt controls only.
#   - No Washington allocation.
#   - No 75/25 corporate-incidence assumption.
#   - No BEA allocator.
#   - No Rockefeller-vintage replication.
#   - No IRS gross-collections reconciliation.
#   - No database writes.
#   - No final ledger inclusion authorization.
# =============================================================================


getcontext().prec = 40


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
    / "corporate_income_tax_receipt_controls_v0_1"
)


OUTPUT_CSV = (
    OUTPUT_DIR
    / "national_corporate_income_tax_receipt_controls.csv"
)


OUTPUT_JSON = (
    OUTPUT_DIR
    / "certification.json"
)


OUTPUT_REPORT = (
    OUTPUT_DIR
    / "certification_report.txt"
)


TARGET_YEARS = list(range(2015, 2025))


EXPECTED_VALUES_MILLIONS = {
    2015: Decimal("343797"),
    2016: Decimal("299571"),
    2017: Decimal("297048"),
    2018: Decimal("204733"),
    2019: Decimal("230245"),
    2020: Decimal("211845"),
    2021: Decimal("371831"),
    2022: Decimal("424865"),
    2023: Decimal("419584"),
    2024: Decimal("529867"),
}


EXPECTED_TITLE = (
    "Table 2.1 - RECEIPTS BY SOURCE:  1934 - 2031"
)


EXPECTED_UNITS_TEXT = (
    "(in millions of dollars)"
)


EXPECTED_FISCAL_YEAR_HEADER = "Fiscal Year"


EXPECTED_SERIES_HEADER = (
    "Corporation Income Taxes (1)"
)


RECEIPT_SERIES = "CORPORATE_INCOME_TAX"


SOURCE_UNITS = "MILLIONS_OF_DOLLARS"


DOLLAR_CONVERSION_FACTOR = Decimal("1000000")


# The FY2027 workbook profile already established that explicit estimates
# begin in 2026. This script independently checks the target period against
# that boundary rather than classifying individual cells by formatting.
FIRST_EXPLICIT_ESTIMATE_YEAR = 2026


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest().upper()


def decimal_from_value(
    value: Any,
    *,
    context: str,
) -> Decimal:
    if value is None:
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: NULL"
        )

    if isinstance(value, bool):
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: boolean"
        )

    try:
        if pd.isna(value):
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: NA"
            )
    except TypeError:
        pass

    if isinstance(value, Decimal):
        result = value

    elif isinstance(value, int):
        result = Decimal(value)

    elif isinstance(value, float):
        if not math.isfinite(value):
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: non-finite"
            )

        result = Decimal(str(value))

    else:
        text = (
            str(value)
            .strip()
            .replace(",", "")
        )

        if not text:
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: blank"
            )

        try:
            result = Decimal(text)
        except InvalidOperation as exc:
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: non-numeric {value!r}"
            ) from exc

    if not result.is_finite():
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: non-finite Decimal"
        )

    return result


def plain_decimal(value: Decimal) -> str:
    return format(value, "f")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass

    return " ".join(
        str(value).strip().split()
    )


def load_source() -> tuple[pd.DataFrame, dict[str, Any]]:
    if not SOURCE_FILE.exists():
        raise RuntimeError(
            "SOURCE FILE NOT FOUND\n"
            f"{SOURCE_FILE.relative_to(REPO_ROOT)}"
        )

    source_sha256 = sha256_file(
        SOURCE_FILE
    )

    source_bytes = SOURCE_FILE.stat().st_size

    # GovInfo workbooks can lack a default Excel style. That warning concerns
    # presentation metadata, not the cell values used by this extraction.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=(
                "Workbook contains no default style, "
                "apply openpyxl's default"
            ),
            category=UserWarning,
        )

        frame = pd.read_excel(
            SOURCE_FILE,
            sheet_name="Table",
            header=None,
            engine="openpyxl",
        )

    source_info = {
        "path": str(
            SOURCE_FILE.relative_to(
                REPO_ROOT
            )
        ),
        "bytes": source_bytes,
        "sha256": source_sha256,
        "sheet": "Table",
    }

    return frame, source_info


def certify_structure(
    frame: pd.DataFrame,
) -> dict[str, Any]:
    if frame.shape[0] < 4:
        raise RuntimeError(
            "SOURCE STRUCTURE FAILURE\n"
            f"Too few rows: {frame.shape[0]}"
        )

    if frame.shape[1] < 3:
        raise RuntimeError(
            "SOURCE STRUCTURE FAILURE\n"
            f"Too few columns: {frame.shape[1]}"
        )

    title = normalize_text(
        frame.iloc[0, 0]
    )

    units = normalize_text(
        frame.iloc[1, 0]
    )

    fiscal_year_header = normalize_text(
        frame.iloc[2, 0]
    )

    series_header = normalize_text(
        frame.iloc[2, 2]
    )

    if title != normalize_text(
        EXPECTED_TITLE
    ):
        raise RuntimeError(
            "OMB TITLE CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_TITLE!r}\n"
            f"Actual  : {title!r}"
        )

    if units.lower() != (
        EXPECTED_UNITS_TEXT.lower()
    ):
        raise RuntimeError(
            "OMB UNIT CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_UNITS_TEXT!r}\n"
            f"Actual  : {units!r}"
        )

    if fiscal_year_header != (
        EXPECTED_FISCAL_YEAR_HEADER
    ):
        raise RuntimeError(
            "OMB FISCAL-YEAR HEADER FAILURE\n"
            f"Expected: {EXPECTED_FISCAL_YEAR_HEADER!r}\n"
            f"Actual  : {fiscal_year_header!r}"
        )

    if series_header != (
        EXPECTED_SERIES_HEADER
    ):
        raise RuntimeError(
            "OMB CORPORATE SERIES HEADER FAILURE\n"
            f"Expected: {EXPECTED_SERIES_HEADER!r}\n"
            f"Actual  : {series_header!r}"
        )

    return {
        "title": title,
        "units_text": units,
        "fiscal_year_column_index": 0,
        "corporate_income_tax_column_index": 2,
        "corporate_income_tax_header": (
            series_header
        ),
        "structure_status": "PASS",
    }


def extract_rows(
    frame: pd.DataFrame,
    source_info: dict[str, Any],
) -> list[dict[str, Any]]:
    fiscal_year_numeric = pd.to_numeric(
        frame.iloc[:, 0],
        errors="coerce",
    )

    rows: list[dict[str, Any]] = []

    for year in TARGET_YEARS:
        matches = frame.loc[
            fiscal_year_numeric == year
        ]

        if len(matches) != 1:
            raise RuntimeError(
                "FISCAL-YEAR SOURCE-CELL UNIQUENESS FAILURE\n"
                f"FFY{year}: expected 1 row; "
                f"found {len(matches)}"
            )

        source_row_index = int(
            matches.index[0]
        )

        source_excel_row = (
            source_row_index + 1
        )

        raw_value = (
            matches.iloc[0, 2]
        )

        millions = decimal_from_value(
            raw_value,
            context=(
                f"FFY{year} Corporation Income Taxes"
            ),
        )

        dollars = (
            millions
            * DOLLAR_CONVERSION_FACTOR
        )

        rows.append(
            {
                "fiscal_year": year,
                "receipt_series": (
                    RECEIPT_SERIES
                ),
                "national_receipts_millions": (
                    plain_decimal(millions)
                ),
                "national_receipts_dollars": (
                    plain_decimal(dollars)
                ),
                "source_units": (
                    SOURCE_UNITS
                ),
                "dollar_conversion_factor": (
                    plain_decimal(
                        DOLLAR_CONVERSION_FACTOR
                    )
                ),
                "source_file": (
                    SOURCE_FILE.name
                ),
                "source_sha256": (
                    source_info["sha256"]
                ),
                "source_sheet": "Table",
                "source_excel_row": (
                    source_excel_row
                ),
                "source_fiscal_year_column": "A",
                "source_value_column": "C",
                "source_series_header": (
                    EXPECTED_SERIES_HEADER
                ),
                "source_period_basis": (
                    "FEDERAL_FISCAL_YEAR"
                ),
                "source_value_status": (
                    "HISTORICAL_ACTUAL"
                ),
                "washington_allocation_status": (
                    "NOT_PERFORMED"
                ),
                "corporate_incidence_assumption_status": (
                    "NOT_APPLIED"
                ),
                "rockefeller_replication": "NO",
                "ledger_status": (
                    "NOT_YET_AUTHORIZED"
                ),
            }
        )

    return rows


def certify_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(rows) != 10:
        raise RuntimeError(
            "OBSERVATION COUNT FAILURE\n"
            f"Expected 10; found {len(rows)}"
        )

    years = [
        int(row["fiscal_year"])
        for row in rows
    ]

    if years != TARGET_YEARS:
        raise RuntimeError(
            "FISCAL-YEAR COVERAGE FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {years}"
        )

    if len(set(years)) != 10:
        raise RuntimeError(
            "FISCAL-YEAR UNIQUENESS FAILURE"
        )

    if max(years) >= (
        FIRST_EXPLICIT_ESTIMATE_YEAR
    ):
        raise RuntimeError(
            "ACTUAL/ESTIMATE BOUNDARY FAILURE\n"
            f"Target years extend into "
            f"{FIRST_EXPLICIT_ESTIMATE_YEAR}+."
        )

    for row in rows:
        year = int(
            row["fiscal_year"]
        )

        actual_millions = Decimal(
            row[
                "national_receipts_millions"
            ]
        )

        expected_millions = (
            EXPECTED_VALUES_MILLIONS[
                year
            ]
        )

        if actual_millions != (
            expected_millions
        ):
            raise RuntimeError(
                "SOURCE VALUE CERTIFICATION FAILURE\n"
                f"FFY{year}: expected "
                f"{expected_millions}; "
                f"found {actual_millions}"
            )

        actual_dollars = Decimal(
            row[
                "national_receipts_dollars"
            ]
        )

        expected_dollars = (
            expected_millions
            * DOLLAR_CONVERSION_FACTOR
        )

        if actual_dollars != (
            expected_dollars
        ):
            raise RuntimeError(
                "UNIT CONVERSION FAILURE\n"
                f"FFY{year}: expected "
                f"{expected_dollars}; "
                f"found {actual_dollars}"
            )

        if (
            row[
                "source_value_status"
            ]
            != "HISTORICAL_ACTUAL"
        ):
            raise RuntimeError(
                "SOURCE VALUE STATUS FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "washington_allocation_status"
            ]
            != "NOT_PERFORMED"
        ):
            raise RuntimeError(
                "WASHINGTON ALLOCATION BOUNDARY FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "corporate_incidence_assumption_status"
            ]
            != "NOT_APPLIED"
        ):
            raise RuntimeError(
                "CORPORATE INCIDENCE BOUNDARY FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "rockefeller_replication"
            ]
            != "NO"
        ):
            raise RuntimeError(
                "ROCKEFELLER BOUNDARY FAILURE\n"
                f"FFY{year}"
            )

        if (
            row["ledger_status"]
            != "NOT_YET_AUTHORIZED"
        ):
            raise RuntimeError(
                "LEDGER BOUNDARY FAILURE\n"
                f"FFY{year}"
            )

    return {
        "expected_observations": 10,
        "actual_observations": 10,
        "fiscal_year_coverage": "PASS",
        "fiscal_year_uniqueness": "PASS",
        "source_cell_uniqueness": "PASS",
        "source_value_certification": "PASS",
        "unit_conversion": "PASS",
        "actual_estimate_boundary": "PASS",
        "washington_allocation_boundary": "PASS",
        "corporate_incidence_boundary": "PASS",
        "rockefeller_replication_boundary": "PASS",
        "ledger_boundary": "PASS",
    }


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        raise RuntimeError(
            "Refusing to write empty output."
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
    source_info: dict[str, Any],
    structure: dict[str, Any],
    certification: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    lines.extend(
        [
            "=" * 100,
            (
                "OMB NATIONAL CORPORATE-INCOME-TAX "
                "RECEIPT CONTROLS - ETL-172H-1"
            ),
            "=" * 100,
            "",
            (
                "National federal receipt controls only. "
                "No Washington corporate-tax incidence "
                "allocation is performed."
            ),
            "",
            "SOURCE CERTIFICATION",
            "-" * 100,
            (
                "Source : "
                f"{source_info['path']}"
            ),
            (
                "SHA256 : "
                f"{source_info['sha256']}"
            ),
            (
                "Bytes  : "
                f"{source_info['bytes']:,}"
            ),
            (
                "Sheet  : "
                f"{source_info['sheet']}"
            ),
            (
                "Title  : "
                f"{structure['title']}"
            ),
            (
                "Units  : "
                f"{structure['units_text']}"
            ),
            (
                "Series : "
                f"{structure['corporate_income_tax_header']}"
            ),
            "",
            "METHOD",
            "-" * 100,
            (
                "Extract OMB Historical Table 2.1 "
                "Corporation Income Taxes for FFY2015-FFY2024."
            ),
            (
                "Source values are millions of dollars; "
                "multiply by 1,000,000 for dollars."
            ),
            (
                "FFY2015-FFY2024 are before the workbook's "
                "first explicit estimate year, 2026."
            ),
            (
                "No Washington allocation or corporate-incidence "
                "assumption is applied in ETL-172H-1."
            ),
            "",
            "CERTIFICATION",
            "-" * 100,
        ]
    )

    labels = [
        (
            "Expected observations",
            certification[
                "expected_observations"
            ],
        ),
        (
            "Actual observations",
            certification[
                "actual_observations"
            ],
        ),
        (
            "Fiscal-year coverage",
            certification[
                "fiscal_year_coverage"
            ],
        ),
        (
            "Fiscal-year uniqueness",
            certification[
                "fiscal_year_uniqueness"
            ],
        ),
        (
            "Source-cell uniqueness",
            certification[
                "source_cell_uniqueness"
            ],
        ),
        (
            "Source-value certification",
            certification[
                "source_value_certification"
            ],
        ),
        (
            "Unit conversion",
            certification[
                "unit_conversion"
            ],
        ),
        (
            "Actual/estimate boundary",
            certification[
                "actual_estimate_boundary"
            ],
        ),
        (
            "Washington allocation boundary",
            certification[
                "washington_allocation_boundary"
            ],
        ),
        (
            "Corporate-incidence boundary",
            certification[
                "corporate_incidence_boundary"
            ],
        ),
        (
            "Rockefeller replication boundary",
            certification[
                "rockefeller_replication_boundary"
            ],
        ),
        (
            "Ledger boundary",
            certification[
                "ledger_boundary"
            ],
        ),
    ]

    for label, value in labels:
        lines.append(
            f"{label:<34}: {value}"
        )

    lines.extend(
        [
            "",
            "NATIONAL CORPORATE-INCOME-TAX RECEIPTS",
            "-" * 100,
            (
                f"{'FFY':<8}"
                f"{'MILLIONS':>18}"
                f"{'DOLLARS':>28}"
                f"{'STATUS':>24}"
            ),
            "-" * 100,
        ]
    )

    for row in rows:
        millions = Decimal(
            row[
                "national_receipts_millions"
            ]
        )

        dollars = Decimal(
            row[
                "national_receipts_dollars"
            ]
        )

        lines.append(
            f"{row['fiscal_year']:<8}"
            f"{millions:>18,.0f}"
            f"{dollars:>28,.0f}"
            f"{row['source_value_status']:>24}"
        )

    lines.extend(
        [
            "",
            "BOUNDARY",
            "-" * 100,
            (
                "These values are national federal corporate "
                "income-tax receipt controls."
            ),
            (
                "They are not Washington corporate-tax payments "
                "or Washington corporate-tax incidence estimates."
            ),
            (
                "The Rockefeller 75-percent capital / 25-percent "
                "labor incidence assumption is not applied here."
            ),
            (
                "No BEA allocator is used in ETL-172H-1."
            ),
            (
                "Final receipts-ledger inclusion remains unauthorized."
            ),
            "",
            "ETL-172H-1 RESULT: PASS",
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
        "OMB NATIONAL CORPORATE-INCOME-TAX "
        "RECEIPT CONTROLS - ETL-172H-1"
    )
    print("=" * 100)
    print()
    print(
        "National federal receipt controls only. "
        "No Washington corporate-tax incidence "
        "allocation is performed."
    )
    print()

    frame, source_info = load_source()

    structure = certify_structure(
        frame
    )

    rows = extract_rows(
        frame,
        source_info,
    )

    certification = certify_rows(
        rows
    )

    write_csv(
        OUTPUT_CSV,
        rows,
    )

    payload = {
        "etl_step": "ETL-172H-1",
        "result": "PASS",
        "artifact_type": (
            "NATIONAL_RECEIPT_CONTROL"
        ),
        "source": source_info,
        "structure": structure,
        "series": {
            "receipt_series": (
                RECEIPT_SERIES
            ),
            "source_header": (
                EXPECTED_SERIES_HEADER
            ),
            "source_units": (
                SOURCE_UNITS
            ),
            "dollar_conversion_factor": (
                plain_decimal(
                    DOLLAR_CONVERSION_FACTOR
                )
            ),
            "period_basis": (
                "FEDERAL_FISCAL_YEAR"
            ),
            "target_years": (
                TARGET_YEARS
            ),
            "first_explicit_estimate_year": (
                FIRST_EXPLICIT_ESTIMATE_YEAR
            ),
        },
        "certification": certification,
        "methodological_boundaries": {
            "washington_allocation_performed": False,
            "corporate_incidence_assumption_applied": False,
            "capital_weight_applied": False,
            "labor_weight_applied": False,
            "bea_allocator_used": False,
            "rockefeller_vintage_replication": False,
            "irs_gross_collections_reconciliation": False,
            "database_writes": False,
            "final_ledger_inclusion_authorized": False,
        },
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        source_info,
        structure,
        certification,
        rows,
    )

    OUTPUT_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print("SOURCE CERTIFICATION")
    print("-" * 100)
    print(
        "Source : "
        f"{source_info['path']}"
    )
    print(
        "SHA256 : "
        f"{source_info['sha256']}"
    )
    print(
        "Bytes  : "
        f"{source_info['bytes']:,}"
    )
    print(
        "Sheet  : "
        f"{source_info['sheet']}"
    )
    print(
        "Series : "
        f"{structure['corporate_income_tax_header']}"
    )
    print(
        "Units  : "
        f"{structure['units_text']}"
    )
    print()

    print("CERTIFICATION")
    print("-" * 100)
    print(
        "Expected observations          : "
        f"{certification['expected_observations']}"
    )
    print(
        "Actual observations            : "
        f"{certification['actual_observations']}"
    )
    print(
        "Fiscal-year coverage           : "
        f"{certification['fiscal_year_coverage']}"
    )
    print(
        "Fiscal-year uniqueness         : "
        f"{certification['fiscal_year_uniqueness']}"
    )
    print(
        "Source-cell uniqueness         : "
        f"{certification['source_cell_uniqueness']}"
    )
    print(
        "Source-value certification     : "
        f"{certification['source_value_certification']}"
    )
    print(
        "Unit conversion                : "
        f"{certification['unit_conversion']}"
    )
    print(
        "Actual/estimate boundary       : "
        f"{certification['actual_estimate_boundary']}"
    )
    print(
        "Washington allocation boundary : "
        f"{certification['washington_allocation_boundary']}"
    )
    print(
        "Corporate-incidence boundary   : "
        f"{certification['corporate_incidence_boundary']}"
    )
    print(
        "Rockefeller replication boundary: "
        f"{certification['rockefeller_replication_boundary']}"
    )
    print(
        "Ledger boundary                : "
        f"{certification['ledger_boundary']}"
    )
    print()

    print(
        "NATIONAL CORPORATE-INCOME-TAX RECEIPTS"
    )
    print("-" * 100)
    print(
        f"{'FFY':<8}"
        f"{'MILLIONS':>18}"
        f"{'DOLLARS':>28}"
        f"{'STATUS':>24}"
    )

    for row in rows:
        millions = Decimal(
            row[
                "national_receipts_millions"
            ]
        )

        dollars = Decimal(
            row[
                "national_receipts_dollars"
            ]
        )

        print(
            f"{row['fiscal_year']:<8}"
            f"{millions:>18,.0f}"
            f"{dollars:>28,.0f}"
            f"{row['source_value_status']:>24}"
        )

    print()
    print(
        "Output : "
        f"{OUTPUT_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        "JSON   : "
        f"{OUTPUT_JSON.relative_to(REPO_ROOT)}"
    )
    print(
        "Report : "
        f"{OUTPUT_REPORT.relative_to(REPO_ROOT)}"
    )
    print()
    print(
        "ETL-172H-1 RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )