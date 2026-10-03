from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any

import pandas as pd


# =============================================================================
# ETL-172G-2A/2B
# IRS SOI INDIVIDUAL-INCOME-TAX ALLOCATOR CERTIFICATION
#
# Purpose:
#   For TY2015-TY2023:
#
#       liability =
#           A06500
#         + A85530
#         + A85300
#
#   Extract the source-provided US and Washington total rows and calculate:
#
#       WA liability share =
#           WA liability / US liability
#
# Boundaries:
#   - Tax-year allocator certification only.
#   - No FFY-to-TY mapping.
#   - No OMB national-control allocation.
#   - No Rockefeller dollar reconstruction.
#   - No forced reconciliation to IRS gross collections.
#   - No database writes.
#   - No receipts-ledger inclusion.
#
# Important:
#   The source-provided US row is used as the denominator.
#   State rows are NOT summed to construct a national denominator.
# =============================================================================


getcontext().prec = 40


REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "irs"
    / "historic_table_2"
    / "source"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "irs"
    / "historic_table_2"
    / "validation"
    / "individual_income_tax_allocator_certification_v0_1"
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "washington_individual_income_tax_allocator.csv"
)

OUTPUT_JSON = (
    OUTPUT_DIR
    / "certification.json"
)

OUTPUT_REPORT = (
    OUTPUT_DIR
    / "certification_report.txt"
)


TARGET_YEARS = list(range(2015, 2024))

TARGET_VARIABLES = [
    "A06500",
    "A85530",
    "A85300",
]

GEOGRAPHY_COLUMN = "STATE"
AGI_STUB_COLUMN = "AGI_STUB"

US_GEOGRAPHY = "US"
WA_GEOGRAPHY = "WA"

TOTAL_AGI_STUB = 0

SOURCE_FILE_PATTERN = (
    "irs_historic_table_2_state_data_ty{year}.csv"
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


def decimal_from_value(
    value: Any,
    *,
    context: str,
) -> Decimal:
    if value is None:
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: value is NULL"
        )

    if isinstance(value, bool):
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: boolean value {value!r}"
        )

    try:
        if pd.isna(value):
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: value is NA"
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
                f"{context}: non-finite value {value!r}"
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
                f"{context}: blank value"
            )

        try:
            result = Decimal(text)
        except InvalidOperation as exc:
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: non-numeric value {value!r}"
            ) from exc

    if not result.is_finite():
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: non-finite Decimal"
        )

    return result


def normalize_state(
    value: Any,
) -> str:
    return str(value).strip().upper()


def normalize_agi_stub(
    value: Any,
) -> int:
    try:
        numeric = Decimal(
            str(value).strip()
        )
    except InvalidOperation as exc:
        raise RuntimeError(
            "AGI_STUB CERTIFICATION FAILURE\n"
            f"Unrecognized AGI_STUB value: {value!r}"
        ) from exc

    if numeric != numeric.to_integral_value():
        raise RuntimeError(
            "AGI_STUB CERTIFICATION FAILURE\n"
            f"Non-integral AGI_STUB value: {value!r}"
        )

    return int(numeric)


def plain_decimal(
    value: Decimal,
) -> str:
    return format(
        value,
        "f",
    )


def extract_tax_year_from_filename(
    path: Path,
) -> int:
    match = re.fullmatch(
        r"irs_historic_table_2_state_data_ty(\d{4})\.csv",
        path.name,
        flags=re.IGNORECASE,
    )

    if not match:
        raise RuntimeError(
            "SOURCE FILE NAME CERTIFICATION FAILURE\n"
            f"Unexpected file name: {path.name}"
        )

    return int(
        match.group(1)
    )


def certify_source_inventory() -> dict[int, Path]:
    expected_paths = {
        year: (
            SOURCE_DIR
            / SOURCE_FILE_PATTERN.format(
                year=year
            )
        )
        for year in TARGET_YEARS
    }

    missing = [
        str(
            path.relative_to(
                REPO_ROOT
            )
        )
        for path in expected_paths.values()
        if not path.exists()
    ]

    if missing:
        raise RuntimeError(
            "SOURCE COVERAGE CERTIFICATION FAILURE\n"
            "Missing source files:\n"
            + "\n".join(
                missing
            )
        )

    discovered = sorted(
        SOURCE_DIR.glob(
            "irs_historic_table_2_state_data_ty*.csv"
        )
    )

    discovered_years = [
        extract_tax_year_from_filename(
            path
        )
        for path in discovered
    ]

    missing_years = sorted(
        set(TARGET_YEARS)
        - set(discovered_years)
    )

    if missing_years:
        raise RuntimeError(
            "SOURCE YEAR CERTIFICATION FAILURE\n"
            f"Missing years: {missing_years}"
        )

    return expected_paths


def certify_schema(
    frame: pd.DataFrame,
    *,
    tax_year: int,
) -> None:
    required = {
        GEOGRAPHY_COLUMN,
        AGI_STUB_COLUMN,
        *TARGET_VARIABLES,
    }

    missing = sorted(
        required
        - set(frame.columns)
    )

    if missing:
        raise RuntimeError(
            "SCHEMA CERTIFICATION FAILURE\n"
            f"TY{tax_year}: missing columns {missing}"
        )


def select_total_row(
    frame: pd.DataFrame,
    *,
    tax_year: int,
    geography: str,
) -> tuple[pd.Series, int]:
    states = frame[
        GEOGRAPHY_COLUMN
    ].map(
        normalize_state
    )

    stubs = frame[
        AGI_STUB_COLUMN
    ].map(
        normalize_agi_stub
    )

    mask = (
        (states == geography)
        & (stubs == TOTAL_AGI_STUB)
    )

    matches = frame.loc[
        mask
    ]

    if len(matches) != 1:
        raise RuntimeError(
            "TOTAL ROW CERTIFICATION FAILURE\n"
            f"TY{tax_year} geography={geography!r} "
            f"AGI_STUB={TOTAL_AGI_STUB}: "
            f"expected 1 row, found {len(matches)}"
        )

    source_index = int(
        matches.index[0]
    )

    # CSV physical line number:
    # pandas index 0 = first data row = line 2.
    source_line = (
        source_index
        + 2
    )

    return (
        matches.iloc[0],
        source_line,
    )


def extract_component(
    row: pd.Series,
    variable: str,
    *,
    tax_year: int,
    geography: str,
) -> Decimal:
    return decimal_from_value(
        row[variable],
        context=(
            f"TY{tax_year} "
            f"{geography} "
            f"{variable}"
        ),
    )


def certify_year(
    *,
    tax_year: int,
    path: Path,
) -> dict[str, Any]:
    frame = pd.read_csv(
        path,
        low_memory=False,
    )

    certify_schema(
        frame,
        tax_year=tax_year,
    )

    source_hash = sha256_file(
        path
    )

    us_row, us_line = (
        select_total_row(
            frame,
            tax_year=tax_year,
            geography=US_GEOGRAPHY,
        )
    )

    wa_row, wa_line = (
        select_total_row(
            frame,
            tax_year=tax_year,
            geography=WA_GEOGRAPHY,
        )
    )

    us_values = {
        variable: extract_component(
            us_row,
            variable,
            tax_year=tax_year,
            geography=US_GEOGRAPHY,
        )
        for variable in TARGET_VARIABLES
    }

    wa_values = {
        variable: extract_component(
            wa_row,
            variable,
            tax_year=tax_year,
            geography=WA_GEOGRAPHY,
        )
        for variable in TARGET_VARIABLES
    }

    for geography, values in [
        (US_GEOGRAPHY, us_values),
        (WA_GEOGRAPHY, wa_values),
    ]:
        for variable, value in values.items():
            if value < 0:
                raise RuntimeError(
                    "NEGATIVE LIABILITY COMPONENT FAILURE\n"
                    f"TY{tax_year} "
                    f"{geography} "
                    f"{variable} = {value}"
                )

    us_total = sum(
        us_values.values(),
        Decimal("0"),
    )

    wa_total = sum(
        wa_values.values(),
        Decimal("0"),
    )

    if us_total <= 0:
        raise RuntimeError(
            "DENOMINATOR CERTIFICATION FAILURE\n"
            f"TY{tax_year}: US liability total = {us_total}"
        )

    if wa_total < 0:
        raise RuntimeError(
            "NUMERATOR CERTIFICATION FAILURE\n"
            f"TY{tax_year}: WA liability total = {wa_total}"
        )

    share = (
        wa_total
        / us_total
    )

    if not (
        Decimal("0")
        <= share
        <= Decimal("1")
    ):
        raise RuntimeError(
            "SHARE RANGE CERTIFICATION FAILURE\n"
            f"TY{tax_year}: share = {share}"
        )

    share_percent = (
        share
        * Decimal("100")
    )

    return {
        "tax_year": tax_year,
        "source_file": str(
            path.relative_to(
                REPO_ROOT
            )
        ),
        "source_sha256": (
            source_hash
        ),
        "source_units": (
            "IRS SOI source units; "
            "share is unit-invariant"
        ),
        "us_geography_code": (
            US_GEOGRAPHY
        ),
        "us_agi_stub": (
            TOTAL_AGI_STUB
        ),
        "us_source_line": (
            us_line
        ),
        "us_A06500": (
            plain_decimal(
                us_values[
                    "A06500"
                ]
            )
        ),
        "us_A85530": (
            plain_decimal(
                us_values[
                    "A85530"
                ]
            )
        ),
        "us_A85300": (
            plain_decimal(
                us_values[
                    "A85300"
                ]
            )
        ),
        "us_total_liability": (
            plain_decimal(
                us_total
            )
        ),
        "wa_geography_code": (
            WA_GEOGRAPHY
        ),
        "wa_agi_stub": (
            TOTAL_AGI_STUB
        ),
        "wa_source_line": (
            wa_line
        ),
        "wa_A06500": (
            plain_decimal(
                wa_values[
                    "A06500"
                ]
            )
        ),
        "wa_A85530": (
            plain_decimal(
                wa_values[
                    "A85530"
                ]
            )
        ),
        "wa_A85300": (
            plain_decimal(
                wa_values[
                    "A85300"
                ]
            )
        ),
        "wa_total_liability": (
            plain_decimal(
                wa_total
            )
        ),
        "wa_liability_share": (
            plain_decimal(
                share
            )
        ),
        "wa_liability_share_percent": (
            plain_decimal(
                share_percent
            )
        ),
        "allocator_status": (
            "CONTEMPORANEOUS_TAX_YEAR_SHARE"
        ),
    }


def certify_output(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(rows) != len(
        TARGET_YEARS
    ):
        raise RuntimeError(
            "OUTPUT COVERAGE FAILURE\n"
            f"Expected {len(TARGET_YEARS)} rows; "
            f"found {len(rows)}"
        )

    years = [
        int(
            row["tax_year"]
        )
        for row in rows
    ]

    if years != TARGET_YEARS:
        raise RuntimeError(
            "OUTPUT YEAR CERTIFICATION FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {years}"
        )

    if len(set(years)) != len(years):
        raise RuntimeError(
            "OUTPUT UNIQUENESS FAILURE"
        )

    hashes = [
        row["source_sha256"]
        for row in rows
    ]

    if len(hashes) != len(
        TARGET_YEARS
    ):
        raise RuntimeError(
            "SOURCE HASH COVERAGE FAILURE"
        )

    return {
        "expected_observations": (
            len(TARGET_YEARS)
        ),
        "actual_observations": (
            len(rows)
        ),
        "coverage": "PASS",
        "uniqueness": "PASS",
        "us_total_row_selection": (
            "PASS"
        ),
        "wa_total_row_selection": (
            "PASS"
        ),
        "liability_arithmetic": (
            "PASS"
        ),
        "share_arithmetic": (
            "PASS"
        ),
        "source_hash_coverage": (
            "PASS"
        ),
    }


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        raise RuntimeError(
            "Refusing to write empty certification."
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
        writer.writerows(
            rows
        )


def build_report(
    rows: list[dict[str, Any]],
    certification: dict[str, Any],
) -> str:
    lines: list[str] = []

    lines.extend(
        [
            "=" * 100,
            (
                "IRS SOI INDIVIDUAL-INCOME-TAX "
                "ALLOCATOR CERTIFICATION - ETL-172G-2A/2B"
            ),
            "=" * 100,
            "",
            (
                "Tax-year allocator certification only. "
                "No FFY-to-TY mapping, OMB allocation, "
                "Rockefeller dollar reconstruction, forced "
                "IRS gross-collections reconciliation, DB "
                "writes, or receipts-ledger inclusion."
            ),
            "",
            "METHOD",
            "-" * 100,
            (
                "Liability = "
                "A06500 + A85530 + A85300"
            ),
            (
                "WA share  = "
                "WA liability / source-provided US liability"
            ),
            (
                "Rows      = "
                "STATE in {US, WA}, AGI_STUB = 0"
            ),
            "",
            "CERTIFICATION",
            "-" * 100,
            (
                f"Expected observations : "
                f"{certification['expected_observations']}"
            ),
            (
                f"Actual observations   : "
                f"{certification['actual_observations']}"
            ),
            (
                f"Coverage              : "
                f"{certification['coverage']}"
            ),
            (
                f"Uniqueness            : "
                f"{certification['uniqueness']}"
            ),
            (
                f"US total-row selection: "
                f"{certification['us_total_row_selection']}"
            ),
            (
                f"WA total-row selection: "
                f"{certification['wa_total_row_selection']}"
            ),
            (
                f"Liability arithmetic  : "
                f"{certification['liability_arithmetic']}"
            ),
            (
                f"Share arithmetic      : "
                f"{certification['share_arithmetic']}"
            ),
            (
                f"Source hash coverage  : "
                f"{certification['source_hash_coverage']}"
            ),
            "",
            "WASHINGTON INDIVIDUAL-INCOME-TAX LIABILITY SHARES",
            "-" * 100,
            (
                f"{'TY':<6}"
                f"{'WA LIABILITY':>20}"
                f"{'US LIABILITY':>22}"
                f"{'WA SHARE':>16}"
                f"{'WA %':>14}"
            ),
            "-" * 100,
        ]
    )

    for row in rows:
        wa_total = Decimal(
            row[
                "wa_total_liability"
            ]
        )

        us_total = Decimal(
            row[
                "us_total_liability"
            ]
        )

        share = Decimal(
            row[
                "wa_liability_share"
            ]
        )

        share_percent = Decimal(
            row[
                "wa_liability_share_percent"
            ]
        )

        lines.append(
            f"{row['tax_year']:<6}"
            f"{wa_total:>20,.0f}"
            f"{us_total:>22,.0f}"
            f"{share:>16.10f}"
            f"{share_percent:>13.6f}%"
        )

    lines.extend(
        [
            "",
            "INTERPRETATION BOUNDARY",
            "-" * 100,
            (
                "Each observation is a contemporaneous "
                "IRS tax-year Washington liability share."
            ),
            (
                "No tax-year share has yet been assigned "
                "to a federal fiscal year."
            ),
            (
                "The source-provided US row is the denominator; "
                "state rows are not summed."
            ),
            (
                "No TY2024 value is fabricated or extrapolated."
            ),
            (
                "These shares have not yet been applied to "
                "OMB national Individual Income Taxes receipts."
            ),
            (
                "Final receipts-ledger inclusion is not authorized."
            ),
            "",
            "ETL-172G-2A/2B RESULT: PASS",
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
        "IRS SOI INDIVIDUAL-INCOME-TAX "
        "ALLOCATOR CERTIFICATION - ETL-172G-2A/2B"
    )
    print("=" * 100)
    print()
    print(
        "Tax-year allocator certification only. "
        "No FFY-to-TY mapping, OMB allocation, Rockefeller "
        "dollar reconstruction, forced IRS gross-collections "
        "reconciliation, DB writes, or receipts-ledger inclusion."
    )
    print()

    source_paths = (
        certify_source_inventory()
    )

    rows = [
        certify_year(
            tax_year=year,
            path=source_paths[
                year
            ],
        )
        for year in TARGET_YEARS
    ]

    certification = (
        certify_output(
            rows
        )
    )

    write_csv(
        OUTPUT_CSV,
        rows,
    )

    json_payload = {
        "etl_step": (
            "ETL-172G-2A/2B"
        ),
        "result": "PASS",
        "method": {
            "liability_formula": (
                "A06500 + A85530 + A85300"
            ),
            "share_formula": (
                "WA liability / "
                "source-provided US liability"
            ),
            "geography_column": (
                GEOGRAPHY_COLUMN
            ),
            "agi_stub_column": (
                AGI_STUB_COLUMN
            ),
            "total_agi_stub": (
                TOTAL_AGI_STUB
            ),
            "us_geography": (
                US_GEOGRAPHY
            ),
            "wa_geography": (
                WA_GEOGRAPHY
            ),
        },
        "tax_years": (
            TARGET_YEARS
        ),
        "certification": (
            certification
        ),
        "interpretation_boundary": {
            "ffy_to_tax_year_mapping": (
                False
            ),
            "omb_controls_applied": (
                False
            ),
            "rockefeller_reconstruction": (
                False
            ),
            "forced_irs_gross_reconciliation": (
                False
            ),
            "database_writes": (
                False
            ),
            "final_ledger_inclusion_authorized": (
                False
            ),
        },
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            json_payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        rows,
        certification,
    )

    OUTPUT_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print("METHOD")
    print("-" * 100)
    print(
        "Liability : A06500 + A85530 + A85300"
    )
    print(
        "WA share  : WA liability / source-provided US liability"
    )
    print(
        "Rows      : STATE in {US, WA}, AGI_STUB = 0"
    )
    print()

    print("CERTIFICATION")
    print("-" * 100)
    print(
        f"Expected observations : "
        f"{certification['expected_observations']}"
    )
    print(
        f"Actual observations   : "
        f"{certification['actual_observations']}"
    )
    print(
        f"Coverage              : "
        f"{certification['coverage']}"
    )
    print(
        f"Uniqueness            : "
        f"{certification['uniqueness']}"
    )
    print(
        f"US total-row selection: "
        f"{certification['us_total_row_selection']}"
    )
    print(
        f"WA total-row selection: "
        f"{certification['wa_total_row_selection']}"
    )
    print(
        f"Liability arithmetic  : "
        f"{certification['liability_arithmetic']}"
    )
    print(
        f"Share arithmetic      : "
        f"{certification['share_arithmetic']}"
    )
    print(
        f"Source hash coverage  : "
        f"{certification['source_hash_coverage']}"
    )
    print()

    print(
        "WASHINGTON INDIVIDUAL-INCOME-TAX LIABILITY SHARES"
    )
    print("-" * 100)
    print(
        f"{'TY':<6}"
        f"{'WA LIABILITY':>20}"
        f"{'US LIABILITY':>22}"
        f"{'WA SHARE':>16}"
        f"{'WA %':>14}"
    )

    for row in rows:
        wa_total = Decimal(
            row[
                "wa_total_liability"
            ]
        )

        us_total = Decimal(
            row[
                "us_total_liability"
            ]
        )

        share = Decimal(
            row[
                "wa_liability_share"
            ]
        )

        share_percent = Decimal(
            row[
                "wa_liability_share_percent"
            ]
        )

        print(
            f"{row['tax_year']:<6}"
            f"{wa_total:>20,.0f}"
            f"{us_total:>22,.0f}"
            f"{share:>16.10f}"
            f"{share_percent:>13.6f}%"
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
        "ETL-172G-2A/2B RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())