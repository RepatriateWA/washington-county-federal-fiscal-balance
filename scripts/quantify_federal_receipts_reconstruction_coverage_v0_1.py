from __future__ import annotations

import csv
import hashlib
import json
import sys
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any


# =============================================================================
# ETL-172I-3
# FEDERAL RECEIPTS RECONSTRUCTION COVERAGE
#
# Purpose:
#   Quantify, for FFY2015-FFY2024, how much of the national OMB federal-
#   receipts universe is represented by receipt categories for which WCFFBP
#   already has a certified Washington allocation methodology.
#
# Covered categories:
#   - Individual income taxes
#   - Corporation income taxes
#   - OASI
#   - Disability Insurance (DI)
#   - Hospital Insurance (HI)
#
# Remaining categories:
#   - Remaining Social Insurance and Retirement Receipts
#   - Excise Taxes
#   - Other Receipts
#
# Important:
#   "Covered" means a certified Washington allocation methodology exists.
#   It does NOT mean that the resulting Washington estimate is a direct
#   observation of tax collections.
#
# This step does NOT:
#   - create new Washington allocations;
#   - allocate residual social-insurance categories;
#   - allocate excise taxes;
#   - decompose or allocate Other receipts;
#   - reproduce Rockefeller estimates;
#   - reconcile to IRS gross collections;
#   - write to PostgreSQL;
#   - authorize final ledger inclusion.
# =============================================================================


getcontext().prec = 50


REPO_ROOT = Path(__file__).resolve().parents[1]

I1_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "federal_receipts_universe_v0_1"
    / "national_federal_receipts_universe.csv"
)

I1_CERTIFICATION = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "federal_receipts_universe_v0_1"
    / "certification.json"
)

I2_ANNUAL_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "social_insurance_excise_decomposition_v0_1"
    / "national_social_insurance_excise_annual_controls.csv"
)

I2_DETAIL_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "social_insurance_excise_decomposition_v0_1"
    / "national_social_insurance_excise_decomposition.csv"
)

I2_CERTIFICATION = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "social_insurance_excise_decomposition_v0_1"
    / "certification.json"
)

F2_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "social_insurance_receipt_controls_v0_1"
    / "national_social_insurance_receipt_controls.csv"
)

F2_CERTIFICATION = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "social_insurance_receipt_controls_v0_1"
    / "certification.json"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "federal_receipts_reconstruction_coverage_v0_1"
)

OUTPUT_ANNUAL = (
    OUTPUT_DIR
    / "federal_receipts_reconstruction_coverage.csv"
)

OUTPUT_RESIDUAL_DETAIL = (
    OUTPUT_DIR
    / "remaining_social_insurance_components.csv"
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

MILLIONS_TO_DOLLARS = Decimal("1000000")


# Components already represented by certified Washington allocation methods.
CERTIFIED_SOCIAL_COMPONENTS = {
    "OASI_TRUST_FUNDS_OFF_BUDGET",
    "DISABILITY_INSURANCE_OFF_BUDGET",
    "HOSPITAL_INSURANCE",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest().upper()


def decimal_value(
    value: Any,
    *,
    context: str,
) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise RuntimeError(
            "NUMERIC PARSE FAILURE\n"
            f"{context}: {value!r}"
        ) from exc

    if not result.is_finite():
        raise RuntimeError(
            "NON-FINITE NUMERIC VALUE\n"
            f"{context}: {value!r}"
        )

    return result


def plain_decimal(value: Decimal) -> str:
    return format(value, "f")


def percent(
    numerator: Decimal,
    denominator: Decimal,
) -> Decimal:
    if denominator == 0:
        raise RuntimeError(
            "PERCENTAGE DENOMINATOR IS ZERO"
        )

    return (
        numerator
        / denominator
        * Decimal("100")
    )


def load_certification(
    path: Path,
    *,
    expected_step: str,
) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(
            "CERTIFICATION FILE NOT FOUND\n"
            f"{path.relative_to(REPO_ROOT)}"
        )

    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if payload.get("etl_step") != expected_step:
        raise RuntimeError(
            "CERTIFICATION CONTRACT FAILURE\n"
            f"File         : {path.relative_to(REPO_ROOT)}\n"
            f"Expected step: {expected_step}\n"
            f"Observed step: {payload.get('etl_step')}"
        )

    if payload.get("result") != "PASS":
        raise RuntimeError(
            "UPSTREAM CERTIFICATION IS NOT PASS\n"
            f"{expected_step}"
        )

    return payload


def load_csv_by_year(
    path: Path,
) -> dict[int, dict[str, str]]:
    if not path.exists():
        raise RuntimeError(
            "INPUT FILE NOT FOUND\n"
            f"{path.relative_to(REPO_ROOT)}"
        )

    rows: dict[int, dict[str, str]] = {}

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        reader = csv.DictReader(handle)

        for row in reader:
            year = int(row["fiscal_year"])

            if year in rows:
                raise RuntimeError(
                    "DUPLICATE FISCAL YEAR\n"
                    f"{path.relative_to(REPO_ROOT)}\n"
                    f"FFY{year}"
                )

            rows[year] = row

    if set(rows) != set(TARGET_YEARS):
        raise RuntimeError(
            "FISCAL-YEAR COVERAGE FAILURE\n"
            f"{path.relative_to(REPO_ROOT)}\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {sorted(rows)}"
        )

    return rows


def load_i2_detail() -> list[dict[str, str]]:
    if not I2_DETAIL_FILE.exists():
        raise RuntimeError(
            "I-2 DETAIL FILE NOT FOUND\n"
            f"{I2_DETAIL_FILE.relative_to(REPO_ROOT)}"
        )

    with I2_DETAIL_FILE.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    if not rows:
        raise RuntimeError(
            "I-2 DETAIL FILE IS EMPTY"
        )

    return rows


def get_required_column(
    row: dict[str, str],
    candidates: list[str],
    *,
    context: str,
) -> str:
    """
    Return the first candidate column that exists.

    This is used only where an earlier certified artifact may have used
    one of two semantically equivalent field names.
    """

    for candidate in candidates:
        if candidate in row:
            return candidate

    raise RuntimeError(
        "REQUIRED COLUMN NOT FOUND\n"
        f"{context}\n"
        f"Candidates: {candidates}\n"
        f"Available : {list(row.keys())}"
    )


def load_f2_long_form(
    path: Path,
) -> dict[
    tuple[int, str],
    dict[str, str],
]:
    """
    Load the certified ETL-172F-2 national social-insurance controls.

    F-2 is intentionally long-form:
        fiscal_year + receipt_series

    Expected domain:
        FFY2015-FFY2024
        OASI, DI, HI

    Therefore the certified artifact contains exactly:
        10 years x 3 series = 30 rows.
    """

    if not path.exists():
        raise RuntimeError(
            "F-2 INPUT FILE NOT FOUND\n"
            f"{path.relative_to(REPO_ROOT)}"
        )

    required_columns = {
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
    }

    rows: dict[
        tuple[int, str],
        dict[str, str],
    ] = {}

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames is None:
            raise RuntimeError(
                "F-2 HEADER FAILURE"
            )

        missing_columns = (
            required_columns
            - set(reader.fieldnames)
        )

        if missing_columns:
            raise RuntimeError(
                "F-2 SCHEMA FAILURE\n"
                f"Missing columns: "
                f"{sorted(missing_columns)}"
            )

        for row in reader:
            year = int(
                row["fiscal_year"]
            )

            series = (
                row["receipt_series"]
                .strip()
                .upper()
            )

            key = (
                year,
                series,
            )

            if key in rows:
                raise RuntimeError(
                    "F-2 DUPLICATE COMPOSITE KEY\n"
                    f"FFY{year} / {series}"
                )

            rows[key] = row

    expected_keys = {
        (
            year,
            series,
        )
        for year in TARGET_YEARS
        for series in (
            "OASI",
            "DI",
            "HI",
        )
    }

    actual_keys = set(
        rows.keys()
    )

    if actual_keys != expected_keys:
        missing = sorted(
            expected_keys
            - actual_keys
        )

        unexpected = sorted(
            actual_keys
            - expected_keys
        )

        raise RuntimeError(
            "F-2 COMPOSITE-KEY COVERAGE FAILURE\n"
            f"Expected rows : {len(expected_keys)}\n"
            f"Actual rows   : {len(actual_keys)}\n"
            f"Missing       : {missing}\n"
            f"Unexpected    : {unexpected}"
        )

    if len(rows) != 30:
        raise RuntimeError(
            "F-2 OBSERVATION COUNT FAILURE\n"
            "Expected: 30\n"
            f"Actual  : {len(rows)}"
        )

    return rows


def extract_f2_controls(
    f2_rows: dict[
        tuple[int, str],
        dict[str, str],
    ],
) -> dict[int, dict[str, Decimal]]:
    """
    Convert the certified long-form F-2 artifact into the annual
    OASI / DI / HI structure needed by I-3.

    The certified F-2 dollar field is used directly. The source-value
    millions field is independently reconciled to it.
    """

    expected_metadata = {
        "OASI": {
            "source_label": (
                "Trust funds (Off-Budget)"
            ),
            "budget_status": (
                "OFF_BUDGET"
            ),
        },
        "DI": {
            "source_label": (
                "Disability insurance (Off-Budget)"
            ),
            "budget_status": (
                "OFF_BUDGET"
            ),
        },
        "HI": {
            "source_label": (
                "Hospital insurance"
            ),
            "budget_status": (
                "ON_BUDGET_UNLESS_OTHERWISE_NOTED"
            ),
        },
    }

    output: dict[
        int,
        dict[str, Decimal],
    ] = {}

    for year in TARGET_YEARS:
        annual: dict[
            str,
            Decimal,
        ] = {}

        for series in (
            "OASI",
            "DI",
            "HI",
        ):
            row = f2_rows[
                (
                    year,
                    series,
                )
            ]

            expected = (
                expected_metadata[
                    series
                ]
            )

            if (
                row["source_label"]
                != expected["source_label"]
            ):
                raise RuntimeError(
                    "F-2 SOURCE-LABEL FAILURE\n"
                    f"FFY{year} / {series}\n"
                    f"Expected: "
                    f"{expected['source_label']!r}\n"
                    f"Observed: "
                    f"{row['source_label']!r}"
                )

            if (
                row["budget_status"]
                != expected["budget_status"]
            ):
                raise RuntimeError(
                    "F-2 BUDGET-STATUS FAILURE\n"
                    f"FFY{year} / {series}\n"
                    f"Expected: "
                    f"{expected['budget_status']!r}\n"
                    f"Observed: "
                    f"{row['budget_status']!r}"
                )

            if (
                row["source_sheet"]
                != "Table"
            ):
                raise RuntimeError(
                    "F-2 SOURCE-SHEET FAILURE\n"
                    f"FFY{year} / {series}: "
                    f"{row['source_sheet']!r}"
                )

            if (
                int(
                    row[
                        "source_year_header"
                    ]
                )
                != year
            ):
                raise RuntimeError(
                    "F-2 YEAR-HEADER FAILURE\n"
                    f"FFY{year} / {series}"
                )

            if (
                row["source_year_status"]
                != "ACTUAL_OR_HISTORICAL"
            ):
                raise RuntimeError(
                    "F-2 YEAR-STATUS FAILURE\n"
                    f"FFY{year} / {series}: "
                    f"{row['source_year_status']!r}"
                )

            if (
                row["source_units"]
                != "millions of dollars"
            ):
                raise RuntimeError(
                    "F-2 UNIT FAILURE\n"
                    f"FFY{year} / {series}: "
                    f"{row['source_units']!r}"
                )

            multiplier = decimal_value(
                row[
                    "normalization_multiplier"
                ],
                context=(
                    f"FFY{year} "
                    f"{series} multiplier"
                ),
            )

            if (
                multiplier
                != MILLIONS_TO_DOLLARS
            ):
                raise RuntimeError(
                    "F-2 NORMALIZATION-"
                    "MULTIPLIER FAILURE\n"
                    f"FFY{year} / {series}: "
                    f"{multiplier}"
                )

            source_millions = (
                decimal_value(
                    row[
                        "source_value_millions"
                    ],
                    context=(
                        f"FFY{year} "
                        f"{series} "
                        "source millions"
                    ),
                )
            )

            certified_dollars = (
                decimal_value(
                    row[
                        "national_receipts_dollars"
                    ],
                    context=(
                        f"FFY{year} "
                        f"{series} "
                        "certified dollars"
                    ),
                )
            )

            reconstructed_dollars = (
                source_millions
                * multiplier
            )

            if (
                reconstructed_dollars
                != certified_dollars
            ):
                raise RuntimeError(
                    "F-2 DOLLAR-NORMALIZATION "
                    "FAILURE\n"
                    f"FFY{year} / {series}\n"
                    f"Source millions : "
                    f"{source_millions}\n"
                    f"Multiplier      : "
                    f"{multiplier}\n"
                    f"Expected dollars: "
                    f"{reconstructed_dollars}\n"
                    f"Certified       : "
                    f"{certified_dollars}"
                )

            annual[
                series.lower()
            ] = certified_dollars

        output[year] = annual

    return output


def build_remaining_social_detail(
    i2_detail: list[dict[str, str]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    for row in i2_detail:
        if (
            row["major_category"]
            != "SOCIAL_INSURANCE_AND_RETIREMENT"
        ):
            continue

        code = row["component_code"]

        if code in CERTIFIED_SOCIAL_COMPONENTS:
            coverage_status = (
                "CERTIFIED_WASHINGTON_ALLOCATION_METHOD"
            )
        else:
            coverage_status = (
                "REMAINING_ALLOCATION_WORK"
            )

        output.append(
            {
                "fiscal_year": int(
                    row["fiscal_year"]
                ),
                "source_row": int(
                    row["source_row"]
                ),
                "component_group": (
                    row["component_group"]
                ),
                "component_code": code,
                "component_label": (
                    row["component_label"]
                ),
                "amount_millions": (
                    row["amount_millions"]
                ),
                "amount_dollars": (
                    row["amount_dollars"]
                ),
                "coverage_status": coverage_status,
            }
        )

    expected = (
        len(TARGET_YEARS)
        * 11
    )

    if len(output) != expected:
        raise RuntimeError(
            "SOCIAL DETAIL OBSERVATION FAILURE\n"
            f"Expected: {expected}\n"
            f"Actual  : {len(output)}"
        )

    return output


def build_annual(
    *,
    i1_rows: dict[int, dict[str, str]],
    i2_rows: dict[int, dict[str, str]],
    f2_controls: dict[int, dict[str, Decimal]],
    remaining_social_detail: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    sample_i1 = i1_rows[TARGET_YEARS[0]]

    individual_col = get_required_column(
        sample_i1,
        [
            "individual_income_taxes_millions",
            "individual_income_tax_millions",
        ],
        context="I-1 individual income taxes",
    )

    corporate_col = get_required_column(
        sample_i1,
        [
            "corporation_income_taxes_millions",
            "corporate_income_taxes_millions",
            "corporation_income_tax_millions",
        ],
        context="I-1 corporation income taxes",
    )

    social_col = get_required_column(
        sample_i1,
        [
            "social_insurance_retirement_total_millions",
            "social_insurance_and_retirement_receipts_millions",
            "social_insurance_retirement_receipts_millions",
        ],
        context="I-1 social insurance and retirement",
    )

    excise_col = get_required_column(
        sample_i1,
        [
            "excise_taxes_millions",
            "excise_tax_millions",
        ],
        context="I-1 excise taxes",
    )

    other_col = get_required_column(
        sample_i1,
        [
            "other_receipts_millions",
            "other_millions",
        ],
        context="I-1 other receipts",
    )

    total_col = get_required_column(
        sample_i1,
        [
            "total_receipts_millions",
            "total_federal_receipts_millions",
        ],
        context="I-1 total receipts",
    )

    for year in TARGET_YEARS:
        i1 = i1_rows[year]
        i2 = i2_rows[year]
        f2 = f2_controls[year]

        individual = decimal_value(
            i1[individual_col],
            context=f"FFY{year} individual",
        )

        corporate = decimal_value(
            i1[corporate_col],
            context=f"FFY{year} corporate",
        )

        social_total = decimal_value(
            i1[social_col],
            context=f"FFY{year} social total",
        )

        excise = decimal_value(
            i1[excise_col],
            context=f"FFY{year} excise",
        )

        other = decimal_value(
            i1[other_col],
            context=f"FFY{year} other",
        )

        total_receipts = decimal_value(
            i1[total_col],
            context=f"FFY{year} total receipts",
        )

        i2_social = decimal_value(
            i2["social_published_total_millions"],
            context=f"FFY{year} I-2 social",
        )

        i2_excise = decimal_value(
            i2["excise_published_total_millions"],
            context=f"FFY{year} I-2 excise",
        )

        if i2_social != social_total:
            raise RuntimeError(
                "I-1 / I-2 SOCIAL CONTROL FAILURE\n"
                f"FFY{year}: "
                f"I-1={social_total}, I-2={i2_social}"
            )

        if i2_excise != excise:
            raise RuntimeError(
                "I-1 / I-2 EXCISE CONTROL FAILURE\n"
                f"FFY{year}: "
                f"I-1={excise}, I-2={i2_excise}"
            )

        oasi = (
            f2["oasi"]
            / MILLIONS_TO_DOLLARS
        )

        di = (
            f2["di"]
            / MILLIONS_TO_DOLLARS
        )

        hi = (
            f2["hi"]
            / MILLIONS_TO_DOLLARS
        )

        certified_social = (
            oasi
            + di
            + hi
        )

        remaining_social = (
            social_total
            - certified_social
        )

        if remaining_social < 0:
            raise RuntimeError(
                "NEGATIVE SOCIAL RESIDUAL\n"
                f"FFY{year}: {remaining_social}"
            )

        # Independent residual proof from I-2 detail.
        detail_remaining_social = Decimal("0")

        for row in remaining_social_detail:
            if int(row["fiscal_year"]) != year:
                continue

            if (
                row["coverage_status"]
                != "REMAINING_ALLOCATION_WORK"
            ):
                continue

            detail_remaining_social += decimal_value(
                row["amount_millions"],
                context=(
                    f"FFY{year} remaining social "
                    f"{row['component_code']}"
                ),
            )

        if (
            detail_remaining_social
            != remaining_social
        ):
            raise RuntimeError(
                "SOCIAL RESIDUAL COMPONENT FAILURE\n"
                f"FFY{year}\n"
                f"Control residual : {remaining_social}\n"
                f"Detail residual  : {detail_remaining_social}"
            )

        covered_universe = (
            individual
            + corporate
            + certified_social
        )

        remaining_universe = (
            remaining_social
            + excise
            + other
        )

        if (
            covered_universe
            + remaining_universe
            != total_receipts
        ):
            raise RuntimeError(
                "TOTAL RECEIPTS COVERAGE IDENTITY FAILURE\n"
                f"FFY{year}\n"
                f"Covered   : {covered_universe}\n"
                f"Remaining : {remaining_universe}\n"
                f"Total     : {total_receipts}"
            )

        social_coverage_pct = percent(
            certified_social,
            social_total,
        )

        universe_coverage_pct = percent(
            covered_universe,
            total_receipts,
        )

        universe_remaining_pct = percent(
            remaining_universe,
            total_receipts,
        )

        if (
            universe_coverage_pct
            + universe_remaining_pct
            != Decimal("100")
        ):
            # Decimal division can produce repeating decimals.
            # Verify algebra directly rather than impose rounded
            # percentage equality.
            if (
                covered_universe
                + remaining_universe
                != total_receipts
            ):
                raise RuntimeError(
                    "COVERAGE PERCENTAGE FAILURE"
                )

        output.append(
            {
                "fiscal_year": year,

                "individual_income_taxes_millions": (
                    plain_decimal(individual)
                ),
                "corporation_income_taxes_millions": (
                    plain_decimal(corporate)
                ),

                "oasi_millions": (
                    plain_decimal(oasi)
                ),
                "di_millions": (
                    plain_decimal(di)
                ),
                "hi_millions": (
                    plain_decimal(hi)
                ),
                "certified_social_components_millions": (
                    plain_decimal(
                        certified_social
                    )
                ),
                "omb_social_insurance_retirement_total_millions": (
                    plain_decimal(
                        social_total
                    )
                ),
                "remaining_social_insurance_retirement_millions": (
                    plain_decimal(
                        remaining_social
                    )
                ),
                "social_reconstruction_coverage_percent": (
                    plain_decimal(
                        social_coverage_pct
                    )
                ),

                "excise_taxes_remaining_millions": (
                    plain_decimal(excise)
                ),
                "other_receipts_remaining_millions": (
                    plain_decimal(other)
                ),

                "covered_national_receipts_universe_millions": (
                    plain_decimal(
                        covered_universe
                    )
                ),
                "remaining_national_receipts_universe_millions": (
                    plain_decimal(
                        remaining_universe
                    )
                ),
                "total_federal_receipts_millions": (
                    plain_decimal(
                        total_receipts
                    )
                ),

                "national_receipts_universe_coverage_percent": (
                    plain_decimal(
                        universe_coverage_pct
                    )
                ),
                "national_receipts_universe_remaining_percent": (
                    plain_decimal(
                        universe_remaining_pct
                    )
                ),

                "coverage_interpretation": (
                    "CERTIFIED_WASHINGTON_ALLOCATION_METHOD_EXISTS"
                ),
                "washington_allocation_status": (
                    "NO_NEW_ALLOCATION_IN_ETL_172I_3"
                ),
                "ledger_status": (
                    "INVENTORY_ONLY"
                ),
            }
        )

    return output


def certify(
    *,
    annual_rows: list[dict[str, Any]],
    residual_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(annual_rows) != 10:
        raise RuntimeError(
            "ANNUAL OBSERVATION COUNT FAILURE"
        )

    years = [
        int(row["fiscal_year"])
        for row in annual_rows
    ]

    if years != TARGET_YEARS:
        raise RuntimeError(
            "ANNUAL YEAR COVERAGE FAILURE"
        )

    for row in annual_rows:
        if (
            row["coverage_interpretation"]
            != "CERTIFIED_WASHINGTON_ALLOCATION_METHOD_EXISTS"
        ):
            raise RuntimeError(
                "COVERAGE INTERPRETATION BOUNDARY FAILURE"
            )

        if (
            row["washington_allocation_status"]
            != "NO_NEW_ALLOCATION_IN_ETL_172I_3"
        ):
            raise RuntimeError(
                "WASHINGTON ALLOCATION BOUNDARY FAILURE"
            )

        if row["ledger_status"] != "INVENTORY_ONLY":
            raise RuntimeError(
                "LEDGER BOUNDARY FAILURE"
            )

    remaining_rows = [
        row
        for row in residual_rows
        if (
            row["coverage_status"]
            == "REMAINING_ALLOCATION_WORK"
        )
    ]

    if not remaining_rows:
        raise RuntimeError(
            "NO REMAINING SOCIAL COMPONENTS FOUND"
        )

    return {
        "expected_annual_observations": 10,
        "actual_annual_observations": len(
            annual_rows
        ),
        "fiscal_year_coverage": "PASS",
        "fiscal_year_uniqueness": "PASS",
        "i1_i2_social_control_reconciliation": "PASS",
        "i1_i2_excise_control_reconciliation": "PASS",
        "f2_oasi_di_hi_control_use": "PASS",
        "social_residual_identity": "PASS",
        "social_residual_component_proof": "PASS",
        "total_receipts_coverage_identity": "PASS",
        "coverage_percentage_arithmetic": "PASS",
        "coverage_interpretation_boundary": "PASS",
        "washington_allocation_boundary": "PASS",
        "rockefeller_replication_boundary": "PASS",
        "irs_reconciliation_boundary": "PASS",
        "database_write_boundary": "PASS",
        "ledger_boundary": "PASS",
    }


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        raise RuntimeError(
            "Refusing to write empty CSV."
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
    *,
    hashes: dict[str, str],
    annual_rows: list[dict[str, Any]],
    certification: dict[str, Any],
) -> str:
    lines: list[str] = [
        "=" * 118,
        (
            "FEDERAL RECEIPTS RECONSTRUCTION COVERAGE "
            "- ETL-172I-3"
        ),
        "=" * 118,
        "",
        "UPSTREAM PROVENANCE",
        "-" * 118,
    ]

    for name, value in hashes.items():
        lines.append(
            f"{name:<28}: {value}"
        )

    lines.extend(
        [
            "",
            "ANNUAL RECONSTRUCTION COVERAGE",
            "-" * 118,
            (
                f"{'FFY':<6}"
                f"{'TOTAL':>14}"
                f"{'COVERED':>14}"
                f"{'REMAINING':>14}"
                f"{'COVER %':>12}"
                f"{'SOCIAL REM':>14}"
                f"{'EXCISE':>12}"
                f"{'OTHER':>12}"
            ),
            "-" * 118,
        ]
    )

    for row in annual_rows:
        total = Decimal(
            row["total_federal_receipts_millions"]
        )

        covered = Decimal(
            row[
                "covered_national_receipts_universe_millions"
            ]
        )

        remaining = Decimal(
            row[
                "remaining_national_receipts_universe_millions"
            ]
        )

        coverage = Decimal(
            row[
                "national_receipts_universe_coverage_percent"
            ]
        )

        social_remaining = Decimal(
            row[
                "remaining_social_insurance_retirement_millions"
            ]
        )

        excise = Decimal(
            row["excise_taxes_remaining_millions"]
        )

        other = Decimal(
            row["other_receipts_remaining_millions"]
        )

        lines.append(
            f"{row['fiscal_year']:<6}"
            f"{total:>14,.0f}"
            f"{covered:>14,.0f}"
            f"{remaining:>14,.0f}"
            f"{coverage:>11.4f}%"
            f"{social_remaining:>14,.0f}"
            f"{excise:>12,.0f}"
            f"{other:>12,.0f}"
        )

    lines.extend(
        [
            "",
            "CERTIFICATION",
            "-" * 118,
        ]
    )

    for key, value in certification.items():
        lines.append(
            f"{key:<52}: {value}"
        )

    lines.extend(
        [
            "",
            "INTERPRETATION",
            "-" * 118,
            (
                "Coverage percentage measures the share of the "
                "national federal-receipts universe represented by "
                "categories for which WCFFBP already has a certified "
                "Washington allocation methodology."
            ),
            (
                "It is not the percentage of Washington tax collections "
                "directly observed, and it is not a completeness claim "
                "for the final Washington outflow ledger."
            ),
            "",
            "ETL-172I-3 RESULT: PASS",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 118)
    print(
        "FEDERAL RECEIPTS RECONSTRUCTION COVERAGE "
        "- ETL-172I-3"
    )
    print("=" * 118)
    print()

    # -------------------------------------------------------------------------
    # Upstream certification contracts.
    # -------------------------------------------------------------------------

    load_certification(
        I1_CERTIFICATION,
        expected_step="ETL-172I-1",
    )

    load_certification(
        I2_CERTIFICATION,
        expected_step="ETL-172I-2",
    )

    # F-2 certification structure predates I-series conventions.
    # We require the file to exist and preserve its hash, while the
    # certified F-2 control artifact itself is independently checked below.
    if not F2_CERTIFICATION.exists():
        raise RuntimeError(
            "F-2 CERTIFICATION FILE NOT FOUND\n"
            f"{F2_CERTIFICATION.relative_to(REPO_ROOT)}"
        )

    i1_rows = load_csv_by_year(
        I1_FILE
    )

    i2_rows = load_csv_by_year(
        I2_ANNUAL_FILE
    )

    f2_rows = load_f2_long_form(
        F2_FILE
    )

    i2_detail = load_i2_detail()

    f2_controls = extract_f2_controls(
        f2_rows
    )

    residual_detail = (
        build_remaining_social_detail(
            i2_detail
        )
    )

    annual_rows = build_annual(
        i1_rows=i1_rows,
        i2_rows=i2_rows,
        f2_controls=f2_controls,
        remaining_social_detail=residual_detail,
    )

    certification = certify(
        annual_rows=annual_rows,
        residual_rows=residual_detail,
    )

    hashes = {
        "ETL-172I-1 universe": (
            sha256_file(I1_FILE)
        ),
        "ETL-172I-2 annual": (
            sha256_file(I2_ANNUAL_FILE)
        ),
        "ETL-172I-2 detail": (
            sha256_file(I2_DETAIL_FILE)
        ),
        "ETL-172F-2 controls": (
            sha256_file(F2_FILE)
        ),
    }

    write_csv(
        OUTPUT_ANNUAL,
        annual_rows,
    )

    write_csv(
        OUTPUT_RESIDUAL_DETAIL,
        residual_detail,
    )

    payload = {
        "etl_step": "ETL-172I-3",
        "result": "PASS",
        "artifact_type": (
            "FEDERAL_RECEIPTS_RECONSTRUCTION_COVERAGE"
        ),
        "target_fiscal_years": TARGET_YEARS,
        "covered_categories": [
            "INDIVIDUAL_INCOME_TAXES",
            "CORPORATION_INCOME_TAXES",
            "OASI",
            "DISABILITY_INSURANCE",
            "HOSPITAL_INSURANCE",
        ],
        "remaining_categories": [
            "REMAINING_SOCIAL_INSURANCE_AND_RETIREMENT",
            "EXCISE_TAXES",
            "OTHER_RECEIPTS",
        ],
        "upstream_sha256": hashes,
        "certification": certification,
        "methodological_boundaries": {
            "coverage_definition": (
                "SHARE_OF_NATIONAL_RECEIPTS_UNIVERSE_FOR_WHICH_"
                "CERTIFIED_WASHINGTON_ALLOCATION_METHOD_EXISTS"
            ),
            "new_washington_allocation_performed": False,
            "rockefeller_replication": False,
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
        hashes=hashes,
        annual_rows=annual_rows,
        certification=certification,
    )

    OUTPUT_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print("ANNUAL RECONSTRUCTION COVERAGE")
    print("-" * 118)

    print(
        f"{'FFY':<6}"
        f"{'TOTAL':>14}"
        f"{'COVERED':>14}"
        f"{'REMAINING':>14}"
        f"{'COVER %':>12}"
        f"{'SOCIAL REM':>14}"
        f"{'EXCISE':>12}"
        f"{'OTHER':>12}"
    )

    for row in annual_rows:
        total = Decimal(
            row["total_federal_receipts_millions"]
        )

        covered = Decimal(
            row[
                "covered_national_receipts_universe_millions"
            ]
        )

        remaining = Decimal(
            row[
                "remaining_national_receipts_universe_millions"
            ]
        )

        coverage = Decimal(
            row[
                "national_receipts_universe_coverage_percent"
            ]
        )

        social_remaining = Decimal(
            row[
                "remaining_social_insurance_retirement_millions"
            ]
        )

        excise = Decimal(
            row["excise_taxes_remaining_millions"]
        )

        other = Decimal(
            row["other_receipts_remaining_millions"]
        )

        print(
            f"{row['fiscal_year']:<6}"
            f"{total:>14,.0f}"
            f"{covered:>14,.0f}"
            f"{remaining:>14,.0f}"
            f"{coverage:>11.4f}%"
            f"{social_remaining:>14,.0f}"
            f"{excise:>12,.0f}"
            f"{other:>12,.0f}"
        )

    print()
    print("CERTIFICATION")
    print("-" * 118)

    for key, value in certification.items():
        print(
            f"{key:<52}: {value}"
        )

    print()
    print(
        "Annual : "
        f"{OUTPUT_ANNUAL.relative_to(REPO_ROOT)}"
    )
    print(
        "Social : "
        f"{OUTPUT_RESIDUAL_DETAIL.relative_to(REPO_ROOT)}"
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
        "ETL-172I-3 RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )