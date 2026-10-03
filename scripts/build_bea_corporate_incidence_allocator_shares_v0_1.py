from __future__ import annotations

import csv
import hashlib
import json
import sys
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any


# =============================================================================
# ETL-172H-3
# BEA WASHINGTON CORPORATE-INCOME-TAX INCIDENCE ALLOCATOR SHARES
#
# Purpose:
#   Construct Washington / United States annual allocator shares from the
#   preserved and certified ETL-172H-2B BEA SAINC4 source observations.
#
# Capital allocator:
#
#   WA capital income =
#       SAINC4-46 WA Dividends, interest, and rent
#     + SAINC4-70 WA Proprietors' income
#
#   US capital income =
#       SAINC4-46 US Dividends, interest, and rent
#     + SAINC4-70 US Proprietors' income
#
#   WA capital share =
#       WA capital income / US capital income
#
# Labor allocator:
#
#   WA labor share =
#       SAINC4-50 WA Wages and salaries
#       --------------------------------
#       SAINC4-50 US Wages and salaries
#
# Geography:
#   United States = BEA GeoFips 00000
#   Washington    = BEA GeoFips 53000
#
# Years:
#   2015-2024
#
# Boundaries:
#   - No Rockefeller 75/25 weighting.
#   - No combined corporate-incidence share.
#   - No OMB corporate-income-tax receipt allocation.
#   - No Rockefeller target matching.
#   - No IRS gross-collections reconciliation.
#   - No database writes.
#   - No final ledger inclusion authorization.
# =============================================================================


getcontext().prec = 50


REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_ROOT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "bea"
    / "corporate_incidence"
)

SOURCE_DIR = SOURCE_ROOT / "source"
VALIDATION_DIR = SOURCE_ROOT / "validation"

MANIFEST_FILE = (
    VALIDATION_DIR
    / "bea_corporate_incidence_acquisition_manifest_v0_1.json"
)

OUTPUT_DIR = (
    VALIDATION_DIR
    / "washington_corporate_incidence_allocator_shares_v0_1"
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "washington_corporate_incidence_allocator_shares.csv"
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

US_GEOFIPS = "00000"
WA_GEOFIPS = "53000"

EXPECTED_UNIT = "Millions of dollars"
EXPECTED_UNIT_MULT = "6"


SERIES_BY_CODE = {
    "SAINC4-46": {
        "role": "CAPITAL_COMPONENT",
        "description": "Dividends, interest, and rent",
    },
    "SAINC4-70": {
        "role": "CAPITAL_COMPONENT",
        "description": "Proprietors' income",
    },
    "SAINC4-50": {
        "role": "LABOR_COMPONENT",
        "description": "Wages and salaries",
    },
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


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_FILE.exists():
        raise RuntimeError(
            "ETL-172H-2B MANIFEST NOT FOUND\n"
            f"{MANIFEST_FILE.relative_to(REPO_ROOT)}"
        )

    payload = json.loads(
        MANIFEST_FILE.read_text(
            encoding="utf-8"
        )
    )

    if payload.get("etl_step") != "ETL-172H-2B":
        raise RuntimeError(
            "UPSTREAM MANIFEST CERTIFICATION FAILURE\n"
            "Unexpected etl_step."
        )

    if payload.get("result") != "PASS":
        raise RuntimeError(
            "UPSTREAM MANIFEST CERTIFICATION FAILURE\n"
            "ETL-172H-2B is not PASS."
        )

    return payload


def validate_manifest_series(
    manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    entries = manifest.get("series")

    if not isinstance(entries, list):
        raise RuntimeError(
            "UPSTREAM MANIFEST STRUCTURE FAILURE\n"
            "series is not a list."
        )

    indexed: dict[str, dict[str, Any]] = {}

    for entry in entries:
        code = str(
            entry.get("bea_code", "")
        ).strip()

        if code:
            indexed[code] = entry

    expected_codes = set(
        SERIES_BY_CODE
    )

    actual_codes = set(
        indexed
    )

    if actual_codes != expected_codes:
        raise RuntimeError(
            "UPSTREAM SERIES COVERAGE FAILURE\n"
            f"Expected: {sorted(expected_codes)}\n"
            f"Actual  : {sorted(actual_codes)}"
        )

    required_status_fields = (
        "series_code_status",
        "unit_status",
        "unit_mult_status",
        "year_coverage_status",
        "us_geography_status",
        "washington_geography_status",
        "us_year_uniqueness_status",
        "washington_year_uniqueness_status",
        "required_numeric_values_status",
    )

    for code in sorted(expected_codes):
        certification = (
            indexed[code].get(
                "certification",
                {}
            )
        )

        for field in required_status_fields:
            if certification.get(field) != "PASS":
                raise RuntimeError(
                    "UPSTREAM SERIES CERTIFICATION FAILURE\n"
                    f"{code}: {field}="
                    f"{certification.get(field)!r}"
                )

    return indexed


def load_source_rows(
    entry: dict[str, Any],
) -> tuple[list[dict[str, Any]], Path]:
    relative_path = str(
        entry.get("source_file", "")
    ).strip()

    if not relative_path:
        raise RuntimeError(
            "UPSTREAM SOURCE PATH FAILURE"
        )

    source_path = (
        REPO_ROOT / relative_path
    )

    if not source_path.exists():
        raise RuntimeError(
            "UPSTREAM SOURCE FILE NOT FOUND\n"
            f"{relative_path}"
        )

    expected_sha = str(
        entry.get("source_sha256", "")
    ).strip().upper()

    actual_sha = sha256_file(
        source_path
    )

    if actual_sha != expected_sha:
        raise RuntimeError(
            "UPSTREAM SOURCE HASH FAILURE\n"
            f"File     : {relative_path}\n"
            f"Expected : {expected_sha}\n"
            f"Actual   : {actual_sha}"
        )

    payload = json.loads(
        source_path.read_text(
            encoding="utf-8"
        )
    )

    try:
        rows = payload[
            "BEAAPI"
        ][
            "Results"
        ][
            "Data"
        ]
    except (
        KeyError,
        TypeError,
    ) as exc:
        raise RuntimeError(
            "UPSTREAM SOURCE STRUCTURE FAILURE\n"
            f"{relative_path}"
        ) from exc

    if not isinstance(rows, list):
        raise RuntimeError(
            "UPSTREAM SOURCE STRUCTURE FAILURE\n"
            f"{relative_path}: Data is not a list."
        )

    return rows, source_path


def extract_required_values(
    *,
    code: str,
    rows: list[dict[str, Any]],
) -> dict[int, dict[str, Decimal]]:
    output: dict[
        int,
        dict[str, Decimal],
    ] = {}

    for year in TARGET_YEARS:
        output[year] = {}

        for geography_name, geo_fips in (
            ("US", US_GEOFIPS),
            ("WA", WA_GEOFIPS),
        ):
            matches = [
                row
                for row in rows
                if str(
                    row.get(
                        "GeoFips",
                        "",
                    )
                ).strip() == geo_fips
                and str(
                    row.get(
                        "TimePeriod",
                        "",
                    )
                ).strip() == str(year)
            ]

            if len(matches) != 1:
                raise RuntimeError(
                    "REQUIRED OBSERVATION UNIQUENESS FAILURE\n"
                    f"Series    : {code}\n"
                    f"Year      : {year}\n"
                    f"Geography : {geography_name}\n"
                    f"Count     : {len(matches)}"
                )

            row = matches[0]

            observed_code = str(
                row.get(
                    "Code",
                    "",
                )
            ).strip()

            if observed_code != code:
                raise RuntimeError(
                    "SOURCE SERIES CODE FAILURE\n"
                    f"Expected : {code}\n"
                    f"Observed : {observed_code}"
                )

            unit = str(
                row.get(
                    "CL_UNIT",
                    "",
                )
            ).strip()

            unit_mult = str(
                row.get(
                    "UNIT_MULT",
                    "",
                )
            ).strip()

            if unit != EXPECTED_UNIT:
                raise RuntimeError(
                    "SOURCE UNIT FAILURE\n"
                    f"{code} {year} {geography_name}: "
                    f"{unit!r}"
                )

            if unit_mult != EXPECTED_UNIT_MULT:
                raise RuntimeError(
                    "SOURCE UNIT_MULT FAILURE\n"
                    f"{code} {year} {geography_name}: "
                    f"{unit_mult!r}"
                )

            value = decimal_from_value(
                row.get("DataValue"),
                context=(
                    f"{code} {year} "
                    f"{geography_name}"
                ),
            )

            if value <= 0:
                raise RuntimeError(
                    "SOURCE VALUE FAILURE\n"
                    f"{code} {year} {geography_name}: "
                    f"{value}"
                )

            output[year][
                geography_name
            ] = value

    return output


def build_allocator_rows(
    values: dict[
        str,
        dict[
            int,
            dict[str, Decimal],
        ],
    ],
    source_entries: dict[
        str,
        dict[str, Any],
    ],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for year in TARGET_YEARS:
        wa_dir = values[
            "SAINC4-46"
        ][year]["WA"]

        us_dir = values[
            "SAINC4-46"
        ][year]["US"]

        wa_prop = values[
            "SAINC4-70"
        ][year]["WA"]

        us_prop = values[
            "SAINC4-70"
        ][year]["US"]

        wa_wages = values[
            "SAINC4-50"
        ][year]["WA"]

        us_wages = values[
            "SAINC4-50"
        ][year]["US"]

        wa_capital = (
            wa_dir
            + wa_prop
        )

        us_capital = (
            us_dir
            + us_prop
        )

        if us_capital <= 0:
            raise RuntimeError(
                "CAPITAL DENOMINATOR FAILURE\n"
                f"Year: {year}"
            )

        if us_wages <= 0:
            raise RuntimeError(
                "LABOR DENOMINATOR FAILURE\n"
                f"Year: {year}"
            )

        capital_share = (
            wa_capital
            / us_capital
        )

        labor_share = (
            wa_wages
            / us_wages
        )

        if not (
            Decimal("0")
            < capital_share
            < Decimal("1")
        ):
            raise RuntimeError(
                "CAPITAL SHARE RANGE FAILURE\n"
                f"Year: {year}\n"
                f"Share: {capital_share}"
            )

        if not (
            Decimal("0")
            < labor_share
            < Decimal("1")
        ):
            raise RuntimeError(
                "LABOR SHARE RANGE FAILURE\n"
                f"Year: {year}\n"
                f"Share: {labor_share}"
            )

        rows.append(
            {
                "year": year,
                "bea_period_basis": "CALENDAR_YEAR",
                "wa_dividends_interest_rent_millions": (
                    plain_decimal(
                        wa_dir
                    )
                ),
                "us_dividends_interest_rent_millions": (
                    plain_decimal(
                        us_dir
                    )
                ),
                "wa_proprietors_income_millions": (
                    plain_decimal(
                        wa_prop
                    )
                ),
                "us_proprietors_income_millions": (
                    plain_decimal(
                        us_prop
                    )
                ),
                "wa_capital_income_millions": (
                    plain_decimal(
                        wa_capital
                    )
                ),
                "us_capital_income_millions": (
                    plain_decimal(
                        us_capital
                    )
                ),
                "washington_capital_share": (
                    plain_decimal(
                        capital_share
                    )
                ),
                "wa_wages_salaries_millions": (
                    plain_decimal(
                        wa_wages
                    )
                ),
                "us_wages_salaries_millions": (
                    plain_decimal(
                        us_wages
                    )
                ),
                "washington_labor_share": (
                    plain_decimal(
                        labor_share
                    )
                ),
                "capital_formula": (
                    "SAINC4-46 + SAINC4-70"
                ),
                "labor_formula": (
                    "SAINC4-50"
                ),
                "us_denominator_geofips": (
                    US_GEOFIPS
                ),
                "washington_numerator_geofips": (
                    WA_GEOFIPS
                ),
                "sainc4_46_source_sha256": (
                    source_entries[
                        "SAINC4-46"
                    ][
                        "source_sha256"
                    ]
                ),
                "sainc4_70_source_sha256": (
                    source_entries[
                        "SAINC4-70"
                    ][
                        "source_sha256"
                    ]
                ),
                "sainc4_50_source_sha256": (
                    source_entries[
                        "SAINC4-50"
                    ][
                        "source_sha256"
                    ]
                ),
                "corporate_incidence_75_25_status": (
                    "NOT_APPLIED"
                ),
                "omb_corporate_receipt_allocation_status": (
                    "NOT_PERFORMED"
                ),
                "ledger_status": (
                    "NOT_YET_AUTHORIZED"
                ),
            }
        )

    return rows


def certify_output_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(rows) != 10:
        raise RuntimeError(
            "OUTPUT OBSERVATION COUNT FAILURE\n"
            f"Expected 10; found {len(rows)}"
        )

    years = [
        int(row["year"])
        for row in rows
    ]

    if years != TARGET_YEARS:
        raise RuntimeError(
            "OUTPUT YEAR COVERAGE FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {years}"
        )

    if len(set(years)) != 10:
        raise RuntimeError(
            "OUTPUT YEAR UNIQUENESS FAILURE"
        )

    for row in rows:
        year = int(
            row["year"]
        )

        wa_dir = Decimal(
            row[
                "wa_dividends_interest_rent_millions"
            ]
        )

        wa_prop = Decimal(
            row[
                "wa_proprietors_income_millions"
            ]
        )

        us_dir = Decimal(
            row[
                "us_dividends_interest_rent_millions"
            ]
        )

        us_prop = Decimal(
            row[
                "us_proprietors_income_millions"
            ]
        )

        wa_capital = Decimal(
            row[
                "wa_capital_income_millions"
            ]
        )

        us_capital = Decimal(
            row[
                "us_capital_income_millions"
            ]
        )

        capital_share = Decimal(
            row[
                "washington_capital_share"
            ]
        )

        wa_wages = Decimal(
            row[
                "wa_wages_salaries_millions"
            ]
        )

        us_wages = Decimal(
            row[
                "us_wages_salaries_millions"
            ]
        )

        labor_share = Decimal(
            row[
                "washington_labor_share"
            ]
        )

        if wa_capital != (
            wa_dir + wa_prop
        ):
            raise RuntimeError(
                "WA CAPITAL ARITHMETIC FAILURE\n"
                f"Year: {year}"
            )

        if us_capital != (
            us_dir + us_prop
        ):
            raise RuntimeError(
                "US CAPITAL ARITHMETIC FAILURE\n"
                f"Year: {year}"
            )

        expected_capital_share = (
            wa_capital
            / us_capital
        )

        if capital_share != (
            expected_capital_share
        ):
            raise RuntimeError(
                "CAPITAL SHARE ARITHMETIC FAILURE\n"
                f"Year: {year}"
            )

        expected_labor_share = (
            wa_wages
            / us_wages
        )

        if labor_share != (
            expected_labor_share
        ):
            raise RuntimeError(
                "LABOR SHARE ARITHMETIC FAILURE\n"
                f"Year: {year}"
            )

        if (
            row[
                "bea_period_basis"
            ]
            != "CALENDAR_YEAR"
        ):
            raise RuntimeError(
                "BEA PERIOD BASIS FAILURE\n"
                f"Year: {year}"
            )

        if (
            row[
                "corporate_incidence_75_25_status"
            ]
            != "NOT_APPLIED"
        ):
            raise RuntimeError(
                "75/25 BOUNDARY FAILURE\n"
                f"Year: {year}"
            )

        if (
            row[
                "omb_corporate_receipt_allocation_status"
            ]
            != "NOT_PERFORMED"
        ):
            raise RuntimeError(
                "OMB ALLOCATION BOUNDARY FAILURE\n"
                f"Year: {year}"
            )

        if (
            row["ledger_status"]
            != "NOT_YET_AUTHORIZED"
        ):
            raise RuntimeError(
                "LEDGER BOUNDARY FAILURE\n"
                f"Year: {year}"
            )

    return {
        "expected_observations": 10,
        "actual_observations": 10,
        "year_coverage": "PASS",
        "year_uniqueness": "PASS",
        "source_hash_integrity": "PASS",
        "source_units": "PASS",
        "source_geography": "PASS",
        "wa_capital_arithmetic": "PASS",
        "us_capital_arithmetic": "PASS",
        "capital_share_arithmetic": "PASS",
        "labor_share_arithmetic": "PASS",
        "bea_period_basis": "PASS",
        "corporate_incidence_75_25_boundary": "PASS",
        "omb_allocation_boundary": "PASS",
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
    manifest_sha256: str,
    source_entries: dict[
        str,
        dict[str, Any],
    ],
    rows: list[dict[str, Any]],
    certification: dict[str, Any],
) -> str:
    lines: list[str] = [
        "=" * 100,
        (
            "BEA WASHINGTON CORPORATE-INCOME-TAX "
            "INCIDENCE ALLOCATOR SHARES - ETL-172H-3"
        ),
        "=" * 100,
        "",
        (
            "Construct Washington / United States capital "
            "and labor allocator shares."
        ),
        (
            "No Rockefeller 75/25 weighting and no OMB "
            "corporate-income-tax allocation are performed."
        ),
        "",
        "UPSTREAM PROVENANCE",
        "-" * 100,
        (
            "H-2B manifest SHA256 : "
            f"{manifest_sha256}"
        ),
    ]

    for code in (
        "SAINC4-46",
        "SAINC4-70",
        "SAINC4-50",
    ):
        entry = source_entries[
            code
        ]

        lines.append(
            f"{code:<12} SHA256 : "
            f"{entry['source_sha256']}"
        )

    lines.extend(
        [
            "",
            "METHOD",
            "-" * 100,
            (
                "Capital = SAINC4-46 "
                "(Dividends, interest, and rent)"
            ),
            (
                "        + SAINC4-70 "
                "(Proprietors' income)"
            ),
            (
                "Capital share = "
                "Washington capital / United States capital"
            ),
            (
                "Labor share = "
                "Washington SAINC4-50 wages and salaries "
                "/ United States SAINC4-50 wages and salaries"
            ),
            (
                "United States denominator = "
                "BEA source-provided GeoFips 00000."
            ),
            (
                "Washington numerator = "
                "BEA GeoFips 53000."
            ),
            (
                "BEA observations are annual calendar-year values."
            ),
            "",
            "WASHINGTON ALLOCATOR SHARES",
            "-" * 100,
            (
                f"{'YEAR':<8}"
                f"{'WA CAPITAL':>18}"
                f"{'US CAPITAL':>20}"
                f"{'CAP SHARE':>16}"
                f"{'WA WAGES':>18}"
                f"{'US WAGES':>20}"
                f"{'LAB SHARE':>16}"
            ),
            "-" * 100,
        ]
    )

    for row in rows:
        wa_capital = Decimal(
            row[
                "wa_capital_income_millions"
            ]
        )

        us_capital = Decimal(
            row[
                "us_capital_income_millions"
            ]
        )

        capital_share = Decimal(
            row[
                "washington_capital_share"
            ]
        )

        wa_wages = Decimal(
            row[
                "wa_wages_salaries_millions"
            ]
        )

        us_wages = Decimal(
            row[
                "us_wages_salaries_millions"
            ]
        )

        labor_share = Decimal(
            row[
                "washington_labor_share"
            ]
        )

        lines.append(
            f"{row['year']:<8}"
            f"{wa_capital:>18,.1f}"
            f"{us_capital:>20,.1f}"
            f"{capital_share * 100:>15.6f}%"
            f"{wa_wages:>18,.1f}"
            f"{us_wages:>20,.1f}"
            f"{labor_share * 100:>15.6f}%"
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
            f"{key:<40}: {value}"
        )

    lines.extend(
        [
            "",
            "BOUNDARY",
            "-" * 100,
            (
                "These are BEA-derived Washington / United States "
                "capital and labor shares only."
            ),
            (
                "The Rockefeller 75-percent capital / 25-percent "
                "labor weighting is not applied in ETL-172H-3."
            ),
            (
                "No national corporate-income-tax receipts are "
                "allocated to Washington."
            ),
            (
                "Final receipts-ledger inclusion remains unauthorized."
            ),
            "",
            "ETL-172H-3 RESULT: PASS",
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
        "BEA WASHINGTON CORPORATE-INCOME-TAX "
        "INCIDENCE ALLOCATOR SHARES - ETL-172H-3"
    )
    print("=" * 100)
    print()
    print(
        "BEA allocator-share construction only. "
        "No 75/25 weighting and no OMB receipt allocation."
    )
    print()

    manifest = load_manifest()

    manifest_sha256 = sha256_file(
        MANIFEST_FILE
    )

    source_entries = (
        validate_manifest_series(
            manifest
        )
    )

    values: dict[
        str,
        dict[
            int,
            dict[str, Decimal],
        ],
    ] = {}

    for code in (
        "SAINC4-46",
        "SAINC4-70",
        "SAINC4-50",
    ):
        entry = source_entries[
            code
        ]

        rows, _ = load_source_rows(
            entry
        )

        values[code] = (
            extract_required_values(
                code=code,
                rows=rows,
            )
        )

    output_rows = build_allocator_rows(
        values,
        source_entries,
    )

    certification = certify_output_rows(
        output_rows
    )

    write_csv(
        OUTPUT_CSV,
        output_rows,
    )

    payload = {
        "etl_step": "ETL-172H-3",
        "result": "PASS",
        "artifact_type": (
            "WASHINGTON_CORPORATE_INCIDENCE_ALLOCATOR_SHARES"
        ),
        "upstream": {
            "etl_step": "ETL-172H-2B",
            "manifest_file": str(
                MANIFEST_FILE.relative_to(
                    REPO_ROOT
                )
            ),
            "manifest_sha256": (
                manifest_sha256
            ),
            "source_files": {
                code: {
                    "source_file": (
                        source_entries[
                            code
                        ][
                            "source_file"
                        ]
                    ),
                    "source_sha256": (
                        source_entries[
                            code
                        ][
                            "source_sha256"
                        ]
                    ),
                }
                for code in (
                    "SAINC4-46",
                    "SAINC4-70",
                    "SAINC4-50",
                )
            },
        },
        "method": {
            "capital_formula": (
                "SAINC4-46 + SAINC4-70"
            ),
            "capital_share_formula": (
                "WA capital / US capital"
            ),
            "labor_formula": (
                "SAINC4-50"
            ),
            "labor_share_formula": (
                "WA wages and salaries / "
                "US wages and salaries"
            ),
            "us_denominator_geofips": (
                US_GEOFIPS
            ),
            "washington_numerator_geofips": (
                WA_GEOFIPS
            ),
            "period_basis": (
                "CALENDAR_YEAR"
            ),
        },
        "certification": certification,
        "methodological_boundaries": {
            "corporate_incidence_75_25_applied": False,
            "combined_corporate_share_calculated": False,
            "omb_corporate_receipts_allocated": False,
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
        manifest_sha256=manifest_sha256,
        source_entries=source_entries,
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
        "H-2B manifest SHA256 : "
        f"{manifest_sha256}"
    )

    for code in (
        "SAINC4-46",
        "SAINC4-70",
        "SAINC4-50",
    ):
        print(
            f"{code:<12} SHA256 : "
            f"{source_entries[code]['source_sha256']}"
        )

    print()
    print("WASHINGTON ALLOCATOR SHARES")
    print("-" * 100)
    print(
        f"{'YEAR':<8}"
        f"{'CAPITAL SHARE':>20}"
        f"{'LABOR SHARE':>20}"
    )

    for row in output_rows:
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

        print(
            f"{row['year']:<8}"
            f"{capital_share * 100:>19.6f}%"
            f"{labor_share * 100:>19.6f}%"
        )

    print()
    print("CERTIFICATION")
    print("-" * 100)

    for key, value in certification.items():
        print(
            f"{key:<40}: {value}"
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
        "ETL-172H-3 RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )