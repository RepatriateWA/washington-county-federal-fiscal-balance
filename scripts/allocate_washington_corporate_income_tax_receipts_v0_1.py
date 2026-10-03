from __future__ import annotations

import csv
import hashlib
import json
import sys
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any


# =============================================================================
# ETL-172H-4
# WASHINGTON CORPORATE-INCOME-TAX RECEIPTS
#
# Purpose:
#   Allocate national federal corporate-income-tax receipts to Washington
#   using the Rockefeller-style 75-percent capital / 25-percent labor
#   economic-incidence assumption.
#
# Certified upstream inputs:
#
#   ETL-172H-1
#       OMB Historical Table 2.1 national Corporation Income Taxes
#       FFY2015-FFY2024.
#
#   ETL-172H-3
#       BEA SAINC4 Washington / United States annual allocator shares:
#
#       capital share =
#           WA (SAINC4-46 + SAINC4-70)
#           --------------------------
#           US (SAINC4-46 + SAINC4-70)
#
#       labor share =
#           WA SAINC4-50 wages and salaries
#           --------------------------------
#           US SAINC4-50 wages and salaries
#
# Corporate-incidence assumption:
#
#   combined corporate share =
#       0.75 * capital share
#       + 0.25 * labor share
#
# Washington corporate-income-tax receipts:
#
#   national corporate-income-tax receipts
#       * combined corporate share
#
# Timing convention:
#
#   Principal WCFFBP historical reconstruction uses the finalized BEA
#   allocator carrying the same named annual year as the OMB federal
#   fiscal-year receipt control:
#
#       FFY2015 -> CY2015
#       ...
#       FFY2024 -> CY2024
#
#   This is labeled CONTEMPORANEOUS_FINAL_ALLOCATOR.
#
#   It is a WCFFBP reconstruction convention. It does NOT assert that the
#   federal fiscal year and calendar year are temporally identical, and it
#   does NOT assert that this is Rockefeller's historical-vintage timing
#   convention.
#
# Boundaries:
#   - Economic-incidence estimate, not observed Washington corporate tax.
#   - No forced reconciliation to IRS gross collections.
#   - No Rockefeller target matching.
#   - No Rockefeller-vintage replication.
#   - No database writes.
#   - No final ledger inclusion authorization in this script.
# =============================================================================


getcontext().prec = 50


REPO_ROOT = Path(__file__).resolve().parents[1]


H1_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "corporate_income_tax_receipt_controls_v0_1"
    / "national_corporate_income_tax_receipt_controls.csv"
)

H1_CERTIFICATION_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "corporate_income_tax_receipt_controls_v0_1"
    / "certification.json"
)


H3_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "bea"
    / "corporate_incidence"
    / "validation"
    / "washington_corporate_incidence_allocator_shares_v0_1"
    / "washington_corporate_incidence_allocator_shares.csv"
)

H3_CERTIFICATION_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "bea"
    / "corporate_incidence"
    / "validation"
    / "washington_corporate_incidence_allocator_shares_v0_1"
    / "certification.json"
)


OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "bea"
    / "corporate_incidence"
    / "validation"
    / "washington_corporate_income_tax_receipts_v0_1"
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "washington_corporate_income_tax_receipts.csv"
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

CAPITAL_WEIGHT = Decimal("0.75")
LABOR_WEIGHT = Decimal("0.25")

EXPECTED_WEIGHT_SUM = Decimal("1.00")

TIMING_CONVENTION = "CONTEMPORANEOUS_FINAL_ALLOCATOR"

ACCOUNTING_CONCEPT = "ECONOMIC_INCIDENCE_ESTIMATE"

SOURCE_PERIOD_BASIS = "FEDERAL_FISCAL_YEAR"

ALLOCATOR_PERIOD_BASIS = "CALENDAR_YEAR"


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
            f"{context}: {value!r}"
        ) from exc

    if not result.is_finite():
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: non-finite"
        )

    return result


def plain_decimal(
    value: Decimal,
) -> str:
    return format(value, "f")


def read_csv_rows(
    path: Path,
) -> list[dict[str, str]]:
    if not path.exists():
        raise RuntimeError(
            "UPSTREAM FILE NOT FOUND\n"
            f"{path.relative_to(REPO_ROOT)}"
        )

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        return list(
            csv.DictReader(handle)
        )


def read_json(
    path: Path,
) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(
            "UPSTREAM CERTIFICATION FILE NOT FOUND\n"
            f"{path.relative_to(REPO_ROOT)}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def certify_upstream() -> dict[str, Any]:
    h1_cert = read_json(
        H1_CERTIFICATION_FILE
    )

    h3_cert = read_json(
        H3_CERTIFICATION_FILE
    )

    if h1_cert.get("etl_step") != "ETL-172H-1":
        raise RuntimeError(
            "H-1 UPSTREAM CERTIFICATION FAILURE\n"
            "Unexpected etl_step."
        )

    if h1_cert.get("result") != "PASS":
        raise RuntimeError(
            "H-1 UPSTREAM CERTIFICATION FAILURE\n"
            "Result is not PASS."
        )

    if h3_cert.get("etl_step") != "ETL-172H-3":
        raise RuntimeError(
            "H-3 UPSTREAM CERTIFICATION FAILURE\n"
            "Unexpected etl_step."
        )

    if h3_cert.get("result") != "PASS":
        raise RuntimeError(
            "H-3 UPSTREAM CERTIFICATION FAILURE\n"
            "Result is not PASS."
        )

    h1_checks = h1_cert.get(
        "certification",
        {}
    )

    required_h1 = (
        "fiscal_year_coverage",
        "fiscal_year_uniqueness",
        "source_cell_uniqueness",
        "source_value_certification",
        "unit_conversion",
        "actual_estimate_boundary",
        "washington_allocation_boundary",
        "corporate_incidence_boundary",
        "rockefeller_replication_boundary",
        "ledger_boundary",
    )

    for field in required_h1:
        if h1_checks.get(field) != "PASS":
            raise RuntimeError(
                "H-1 UPSTREAM CHECK FAILURE\n"
                f"{field}: {h1_checks.get(field)!r}"
            )

    h3_checks = h3_cert.get(
        "certification",
        {}
    )

    required_h3 = (
        "year_coverage",
        "year_uniqueness",
        "source_hash_integrity",
        "source_units",
        "source_geography",
        "wa_capital_arithmetic",
        "us_capital_arithmetic",
        "capital_share_arithmetic",
        "labor_share_arithmetic",
        "bea_period_basis",
        "corporate_incidence_75_25_boundary",
        "omb_allocation_boundary",
        "ledger_boundary",
    )

    for field in required_h3:
        if h3_checks.get(field) != "PASS":
            raise RuntimeError(
                "H-3 UPSTREAM CHECK FAILURE\n"
                f"{field}: {h3_checks.get(field)!r}"
            )

    return {
        "h1_certification": h1_cert,
        "h3_certification": h3_cert,
        "h1_csv_sha256": sha256_file(H1_FILE),
        "h1_certification_sha256": sha256_file(
            H1_CERTIFICATION_FILE
        ),
        "h3_csv_sha256": sha256_file(H3_FILE),
        "h3_certification_sha256": sha256_file(
            H3_CERTIFICATION_FILE
        ),
    }


def index_h1(
    rows: list[dict[str, str]],
) -> dict[int, dict[str, str]]:
    indexed: dict[
        int,
        dict[str, str],
    ] = {}

    for row in rows:
        year_text = str(
            row.get(
                "fiscal_year",
                "",
            )
        ).strip()

        try:
            year = int(year_text)
        except ValueError as exc:
            raise RuntimeError(
                "H-1 FISCAL-YEAR FAILURE\n"
                f"{year_text!r}"
            ) from exc

        if year in indexed:
            raise RuntimeError(
                "H-1 FISCAL-YEAR UNIQUENESS FAILURE\n"
                f"Duplicate FFY{year}"
            )

        indexed[year] = row

    if set(indexed) != set(TARGET_YEARS):
        raise RuntimeError(
            "H-1 FISCAL-YEAR COVERAGE FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {sorted(indexed)}"
        )

    return indexed


def index_h3(
    rows: list[dict[str, str]],
) -> dict[int, dict[str, str]]:
    indexed: dict[
        int,
        dict[str, str],
    ] = {}

    for row in rows:
        year_text = str(
            row.get(
                "year",
                "",
            )
        ).strip()

        try:
            year = int(year_text)
        except ValueError as exc:
            raise RuntimeError(
                "H-3 YEAR FAILURE\n"
                f"{year_text!r}"
            ) from exc

        if year in indexed:
            raise RuntimeError(
                "H-3 YEAR UNIQUENESS FAILURE\n"
                f"Duplicate CY{year}"
            )

        indexed[year] = row

    if set(indexed) != set(TARGET_YEARS):
        raise RuntimeError(
            "H-3 YEAR COVERAGE FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {sorted(indexed)}"
        )

    return indexed


def build_rows(
    h1: dict[
        int,
        dict[str, str],
    ],
    h3: dict[
        int,
        dict[str, str],
    ],
    provenance: dict[str, Any],
) -> list[dict[str, Any]]:
    if (
        CAPITAL_WEIGHT
        + LABOR_WEIGHT
        != EXPECTED_WEIGHT_SUM
    ):
        raise RuntimeError(
            "CORPORATE INCIDENCE WEIGHT FAILURE\n"
            f"Capital: {CAPITAL_WEIGHT}\n"
            f"Labor  : {LABOR_WEIGHT}\n"
            f"Sum    : {CAPITAL_WEIGHT + LABOR_WEIGHT}"
        )

    rows: list[dict[str, Any]] = []

    for year in TARGET_YEARS:
        h1_row = h1[year]
        h3_row = h3[year]

        national_receipts = decimal_from_value(
            h1_row.get(
                "national_receipts_dollars"
            ),
            context=(
                f"FFY{year} national "
                "corporate receipts"
            ),
        )

        capital_share = decimal_from_value(
            h3_row.get(
                "washington_capital_share"
            ),
            context=(
                f"CY{year} Washington "
                "capital share"
            ),
        )

        labor_share = decimal_from_value(
            h3_row.get(
                "washington_labor_share"
            ),
            context=(
                f"CY{year} Washington "
                "labor share"
            ),
        )

        if national_receipts <= 0:
            raise RuntimeError(
                "NATIONAL RECEIPT VALUE FAILURE\n"
                f"FFY{year}: {national_receipts}"
            )

        if not (
            Decimal("0")
            < capital_share
            < Decimal("1")
        ):
            raise RuntimeError(
                "CAPITAL SHARE RANGE FAILURE\n"
                f"CY{year}: {capital_share}"
            )

        if not (
            Decimal("0")
            < labor_share
            < Decimal("1")
        ):
            raise RuntimeError(
                "LABOR SHARE RANGE FAILURE\n"
                f"CY{year}: {labor_share}"
            )

        capital_weighted_share = (
            CAPITAL_WEIGHT
            * capital_share
        )

        labor_weighted_share = (
            LABOR_WEIGHT
            * labor_share
        )

        combined_share = (
            capital_weighted_share
            + labor_weighted_share
        )

        washington_receipts = (
            national_receipts
            * combined_share
        )

        rows.append(
            {
                "fiscal_year": year,
                "allocator_year": year,
                "national_corporate_income_tax_receipts_dollars": (
                    plain_decimal(
                        national_receipts
                    )
                ),
                "washington_capital_share": (
                    plain_decimal(
                        capital_share
                    )
                ),
                "capital_weight": (
                    plain_decimal(
                        CAPITAL_WEIGHT
                    )
                ),
                "capital_weighted_share": (
                    plain_decimal(
                        capital_weighted_share
                    )
                ),
                "washington_labor_share": (
                    plain_decimal(
                        labor_share
                    )
                ),
                "labor_weight": (
                    plain_decimal(
                        LABOR_WEIGHT
                    )
                ),
                "labor_weighted_share": (
                    plain_decimal(
                        labor_weighted_share
                    )
                ),
                "washington_combined_corporate_incidence_share": (
                    plain_decimal(
                        combined_share
                    )
                ),
                "washington_corporate_income_tax_receipts_dollars": (
                    plain_decimal(
                        washington_receipts
                    )
                ),
                "national_receipt_period_basis": (
                    SOURCE_PERIOD_BASIS
                ),
                "allocator_period_basis": (
                    ALLOCATOR_PERIOD_BASIS
                ),
                "timing_convention": (
                    TIMING_CONVENTION
                ),
                "accounting_concept": (
                    ACCOUNTING_CONCEPT
                ),
                "incidence_assumption": (
                    "75_PERCENT_CAPITAL_25_PERCENT_LABOR"
                ),
                "rockefeller_vintage_replication": (
                    "NO"
                ),
                "irs_gross_collections_reconciliation": (
                    "NOT_PERFORMED"
                ),
                "h1_input_sha256": (
                    provenance[
                        "h1_csv_sha256"
                    ]
                ),
                "h3_input_sha256": (
                    provenance[
                        "h3_csv_sha256"
                    ]
                ),
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
            "OUTPUT OBSERVATION COUNT FAILURE\n"
            f"Expected 10; found {len(rows)}"
        )

    years = [
        int(row["fiscal_year"])
        for row in rows
    ]

    if years != TARGET_YEARS:
        raise RuntimeError(
            "OUTPUT FISCAL-YEAR COVERAGE FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {years}"
        )

    if len(set(years)) != 10:
        raise RuntimeError(
            "OUTPUT FISCAL-YEAR UNIQUENESS FAILURE"
        )

    for row in rows:
        year = int(
            row["fiscal_year"]
        )

        allocator_year = int(
            row["allocator_year"]
        )

        if allocator_year != year:
            raise RuntimeError(
                "TIMING MAPPING FAILURE\n"
                f"FFY{year} -> CY{allocator_year}"
            )

        capital_share = Decimal(
            row[
                "washington_capital_share"
            ]
        )

        labor_share = Decimal(
            row[
                "washington_labor_share"
            ]
        )

        capital_weight = Decimal(
            row[
                "capital_weight"
            ]
        )

        labor_weight = Decimal(
            row[
                "labor_weight"
            ]
        )

        capital_weighted = Decimal(
            row[
                "capital_weighted_share"
            ]
        )

        labor_weighted = Decimal(
            row[
                "labor_weighted_share"
            ]
        )

        combined_share = Decimal(
            row[
                "washington_combined_corporate_incidence_share"
            ]
        )

        national_receipts = Decimal(
            row[
                "national_corporate_income_tax_receipts_dollars"
            ]
        )

        washington_receipts = Decimal(
            row[
                "washington_corporate_income_tax_receipts_dollars"
            ]
        )

        if (
            capital_weight
            + labor_weight
            != Decimal("1")
        ):
            raise RuntimeError(
                "WEIGHT-SUM FAILURE\n"
                f"FFY{year}"
            )

        if capital_weight != Decimal("0.75"):
            raise RuntimeError(
                "CAPITAL WEIGHT FAILURE\n"
                f"FFY{year}"
            )

        if labor_weight != Decimal("0.25"):
            raise RuntimeError(
                "LABOR WEIGHT FAILURE\n"
                f"FFY{year}"
            )

        expected_capital_weighted = (
            capital_share
            * capital_weight
        )

        if capital_weighted != (
            expected_capital_weighted
        ):
            raise RuntimeError(
                "CAPITAL WEIGHTED-SHARE FAILURE\n"
                f"FFY{year}"
            )

        expected_labor_weighted = (
            labor_share
            * labor_weight
        )

        if labor_weighted != (
            expected_labor_weighted
        ):
            raise RuntimeError(
                "LABOR WEIGHTED-SHARE FAILURE\n"
                f"FFY{year}"
            )

        expected_combined = (
            expected_capital_weighted
            + expected_labor_weighted
        )

        if combined_share != expected_combined:
            raise RuntimeError(
                "COMBINED SHARE ARITHMETIC FAILURE\n"
                f"FFY{year}"
            )

        expected_wa_receipts = (
            national_receipts
            * combined_share
        )

        if washington_receipts != (
            expected_wa_receipts
        ):
            raise RuntimeError(
                "WASHINGTON RECEIPT ARITHMETIC FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "national_receipt_period_basis"
            ]
            != "FEDERAL_FISCAL_YEAR"
        ):
            raise RuntimeError(
                "NATIONAL PERIOD BASIS FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "allocator_period_basis"
            ]
            != "CALENDAR_YEAR"
        ):
            raise RuntimeError(
                "ALLOCATOR PERIOD BASIS FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "timing_convention"
            ]
            != "CONTEMPORANEOUS_FINAL_ALLOCATOR"
        ):
            raise RuntimeError(
                "TIMING CONVENTION FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "accounting_concept"
            ]
            != "ECONOMIC_INCIDENCE_ESTIMATE"
        ):
            raise RuntimeError(
                "ACCOUNTING CONCEPT FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "rockefeller_vintage_replication"
            ]
            != "NO"
        ):
            raise RuntimeError(
                "ROCKEFELLER REPLICATION BOUNDARY FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "irs_gross_collections_reconciliation"
            ]
            != "NOT_PERFORMED"
        ):
            raise RuntimeError(
                "IRS RECONCILIATION BOUNDARY FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "ledger_status"
            ]
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
        "allocator_year_mapping": "PASS",
        "capital_weight": "PASS",
        "labor_weight": "PASS",
        "weight_sum": "PASS",
        "capital_weighted_share_arithmetic": "PASS",
        "labor_weighted_share_arithmetic": "PASS",
        "combined_share_arithmetic": "PASS",
        "washington_receipt_arithmetic": "PASS",
        "national_period_basis": "PASS",
        "allocator_period_basis": "PASS",
        "timing_convention": "PASS",
        "accounting_concept": "PASS",
        "rockefeller_replication_boundary": "PASS",
        "irs_reconciliation_boundary": "PASS",
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
    *,
    provenance: dict[str, Any],
    rows: list[dict[str, Any]],
    certification: dict[str, Any],
) -> str:
    lines: list[str] = [
        "=" * 100,
        (
            "WASHINGTON CORPORATE-INCOME-TAX "
            "RECEIPTS - ETL-172H-4"
        ),
        "=" * 100,
        "",
        (
            "Economic-incidence reconstruction using "
            "75-percent capital / 25-percent labor."
        ),
        "",
        "UPSTREAM PROVENANCE",
        "-" * 100,
        (
            "H-1 national controls SHA256 : "
            f"{provenance['h1_csv_sha256']}"
        ),
        (
            "H-1 certification SHA256     : "
            f"{provenance['h1_certification_sha256']}"
        ),
        (
            "H-3 allocator shares SHA256  : "
            f"{provenance['h3_csv_sha256']}"
        ),
        (
            "H-3 certification SHA256     : "
            f"{provenance['h3_certification_sha256']}"
        ),
        "",
        "METHOD",
        "-" * 100,
        (
            "Combined WA corporate incidence share = "
            "0.75 * WA capital share "
            "+ 0.25 * WA labor share."
        ),
        (
            "WA corporate-income-tax receipts = "
            "OMB national corporate-income-tax receipts "
            "* combined WA incidence share."
        ),
        "",
        (
            "Timing convention: FFY t national receipt control "
            "uses finalized CY t BEA allocator."
        ),
        (
            "Timing label: CONTEMPORANEOUS_FINAL_ALLOCATOR."
        ),
        (
            "This is a WCFFBP principal historical reconstruction "
            "convention, not a Rockefeller-vintage timing claim."
        ),
        "",
        "WASHINGTON CORPORATE-INCOME-TAX RECEIPTS",
        "-" * 100,
        (
            f"{'FFY':<7}"
            f"{'NATIONAL':>22}"
            f"{'CAP SHARE':>14}"
            f"{'LAB SHARE':>14}"
            f"{'COMBINED':>14}"
            f"{'WA RECEIPTS':>22}"
        ),
        "-" * 100,
    ]

    for row in rows:
        national = Decimal(
            row[
                "national_corporate_income_tax_receipts_dollars"
            ]
        )

        capital = Decimal(
            row[
                "washington_capital_share"
            ]
        )

        labor = Decimal(
            row[
                "washington_labor_share"
            ]
        )

        combined = Decimal(
            row[
                "washington_combined_corporate_incidence_share"
            ]
        )

        wa_receipts = Decimal(
            row[
                "washington_corporate_income_tax_receipts_dollars"
            ]
        )

        lines.append(
            f"{row['fiscal_year']:<7}"
            f"{national:>22,.0f}"
            f"{capital * 100:>13.6f}%"
            f"{labor * 100:>13.6f}%"
            f"{combined * 100:>13.6f}%"
            f"{wa_receipts:>22,.0f}"
        )

    lines.extend(
        [
            "",
            "CERTIFICATION",
            "-" * 100,
        ]
    )

    for key, value in certification.items():
        lines.append(
            f"{key:<44}: {value}"
        )

    lines.extend(
        [
            "",
            "ACCOUNTING INTERPRETATION",
            "-" * 100,
            (
                "The Washington values are economic-incidence "
                "estimates, not observed corporate tax collections "
                "from Washington entities."
            ),
            (
                "The 75/25 capital/labor split is an explicit "
                "incidence assumption."
            ),
            (
                "The underlying BEA capital and labor shares remain "
                "separately preserved so alternative incidence "
                "weights can be evaluated later."
            ),
            "",
            "BOUNDARY",
            "-" * 100,
            (
                "No forced reconciliation to IRS Washington gross "
                "collections is performed."
            ),
            (
                "No Rockefeller target matching or historical-vintage "
                "replication is performed."
            ),
            (
                "No database writes are performed."
            ),
            (
                "Final ledger inclusion remains unauthorized by this "
                "certification step."
            ),
            "",
            "ETL-172H-4 RESULT: PASS",
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
        "WASHINGTON CORPORATE-INCOME-TAX "
        "RECEIPTS - ETL-172H-4"
    )
    print("=" * 100)
    print()
    print(
        "Economic-incidence reconstruction using "
        "75-percent capital / 25-percent labor."
    )
    print()

    provenance = certify_upstream()

    h1_rows = read_csv_rows(
        H1_FILE
    )

    h3_rows = read_csv_rows(
        H3_FILE
    )

    h1 = index_h1(
        h1_rows
    )

    h3 = index_h3(
        h3_rows
    )

    output_rows = build_rows(
        h1,
        h3,
        provenance,
    )

    certification = certify_rows(
        output_rows
    )

    write_csv(
        OUTPUT_CSV,
        output_rows,
    )

    payload = {
        "etl_step": "ETL-172H-4",
        "result": "PASS",
        "artifact_type": (
            "WASHINGTON_CORPORATE_INCOME_TAX_"
            "ECONOMIC_INCIDENCE_RECEIPTS"
        ),
        "upstream": {
            "h1": {
                "etl_step": "ETL-172H-1",
                "input_file": str(
                    H1_FILE.relative_to(
                        REPO_ROOT
                    )
                ),
                "input_sha256": (
                    provenance[
                        "h1_csv_sha256"
                    ]
                ),
                "certification_file": str(
                    H1_CERTIFICATION_FILE.relative_to(
                        REPO_ROOT
                    )
                ),
                "certification_sha256": (
                    provenance[
                        "h1_certification_sha256"
                    ]
                ),
            },
            "h3": {
                "etl_step": "ETL-172H-3",
                "input_file": str(
                    H3_FILE.relative_to(
                        REPO_ROOT
                    )
                ),
                "input_sha256": (
                    provenance[
                        "h3_csv_sha256"
                    ]
                ),
                "certification_file": str(
                    H3_CERTIFICATION_FILE.relative_to(
                        REPO_ROOT
                    )
                ),
                "certification_sha256": (
                    provenance[
                        "h3_certification_sha256"
                    ]
                ),
            },
        },
        "method": {
            "capital_weight": (
                plain_decimal(
                    CAPITAL_WEIGHT
                )
            ),
            "labor_weight": (
                plain_decimal(
                    LABOR_WEIGHT
                )
            ),
            "combined_share_formula": (
                "0.75 * Washington capital share "
                "+ 0.25 * Washington labor share"
            ),
            "washington_receipt_formula": (
                "OMB national corporate-income-tax receipts "
                "* Washington combined corporate-incidence share"
            ),
            "national_receipt_period_basis": (
                SOURCE_PERIOD_BASIS
            ),
            "allocator_period_basis": (
                ALLOCATOR_PERIOD_BASIS
            ),
            "timing_convention": (
                TIMING_CONVENTION
            ),
            "timing_mapping": (
                "FFY t -> finalized CY t BEA allocator"
            ),
            "accounting_concept": (
                ACCOUNTING_CONCEPT
            ),
        },
        "certification": certification,
        "methodological_boundaries": {
            "observed_washington_corporate_tax": False,
            "economic_incidence_estimate": True,
            "rockefeller_vintage_replication": False,
            "rockefeller_target_matching": False,
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
        provenance=provenance,
        rows=output_rows,
        certification=certification,
    )

    OUTPUT_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print("UPSTREAM PROVENANCE")
    print("-" * 100)
    print(
        "H-1 national controls SHA256 : "
        f"{provenance['h1_csv_sha256']}"
    )
    print(
        "H-3 allocator shares SHA256  : "
        f"{provenance['h3_csv_sha256']}"
    )
    print()

    print(
        "WASHINGTON CORPORATE-INCOME-TAX RECEIPTS"
    )
    print("-" * 100)
    print(
        f"{'FFY':<7}"
        f"{'NATIONAL':>22}"
        f"{'COMBINED SHARE':>20}"
        f"{'WA RECEIPTS':>22}"
    )

    for row in output_rows:
        national = Decimal(
            row[
                "national_corporate_income_tax_receipts_dollars"
            ]
        )

        combined = Decimal(
            row[
                "washington_combined_corporate_incidence_share"
            ]
        )

        wa_receipts = Decimal(
            row[
                "washington_corporate_income_tax_receipts_dollars"
            ]
        )

        print(
            f"{row['fiscal_year']:<7}"
            f"{national:>22,.0f}"
            f"{combined * 100:>19.6f}%"
            f"{wa_receipts:>22,.0f}"
        )

    print()
    print("CERTIFICATION")
    print("-" * 100)

    for key, value in certification.items():
        print(
            f"{key:<44}: {value}"
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
        "ETL-172H-4 RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )