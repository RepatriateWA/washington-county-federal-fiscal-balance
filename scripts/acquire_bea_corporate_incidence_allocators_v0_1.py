from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


# =============================================================================
# ETL-172H-2B
# BEA CORPORATE-INCOME-TAX INCIDENCE ALLOCATOR ACQUISITION
#
# Purpose:
#   Acquire and certify the BEA SAINC4 observations required for the
#   Rockefeller-style corporate-income-tax incidence allocation.
#
# Required concepts:
#
#   CAPITAL COMPONENT 1
#       SAINC4 line 46
#       Dividends, interest, and rent
#
#   CAPITAL COMPONENT 2
#       SAINC4 line 70
#       Proprietors' income
#
#   LABOR
#       SAINC4 line 50
#       Wages and salaries
#
# Geography:
#   GeoFIPS=STATE
#
# This returns the source-provided United States observation (00000)
# together with the state universe. Washington is 53000.
#
# Years:
#   2015-2024
#
# Boundaries:
#   - Raw acquisition and source certification only.
#   - No capital-income construction.
#   - No Washington / United States shares.
#   - No 75/25 corporate-incidence weighting.
#   - No OMB corporate-receipt allocation.
#   - No Rockefeller target matching.
#   - No IRS gross-collections reconciliation.
#   - No database writes.
#   - No final ledger inclusion authorization.
# =============================================================================


REPO_ROOT = Path(__file__).resolve().parents[1]

BEA_API_URL = "https://apps.bea.gov/api/data/"

OUTPUT_ROOT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "bea"
    / "corporate_incidence"
)

SOURCE_DIR = OUTPUT_ROOT / "source"
VALIDATION_DIR = OUTPUT_ROOT / "validation"

MANIFEST_FILE = (
    VALIDATION_DIR
    / "bea_corporate_incidence_acquisition_manifest_v0_1.json"
)

REPORT_FILE = (
    VALIDATION_DIR
    / "bea_corporate_incidence_acquisition_report_v0_1.txt"
)


DATASET_NAME = "Regional"
TABLE_NAME = "SAINC4"
GEO_FIPS_REQUEST = "STATE"

TARGET_YEARS = list(range(2015, 2025))
YEAR_PARAMETER = ",".join(str(year) for year in TARGET_YEARS)

EXPECTED_UNIT = "Millions of dollars"
EXPECTED_UNIT_MULT = "6"

US_GEOFIPS = "00000"
WA_GEOFIPS = "53000"

SERIES = {
    "46": {
        "code": "SAINC4-46",
        "slug": "dividends_interest_rent",
        "description": "Dividends, interest, and rent",
        "role": "CAPITAL_COMPONENT",
    },
    "70": {
        "code": "SAINC4-70",
        "slug": "proprietors_income",
        "description": "Proprietors' income",
        "role": "CAPITAL_COMPONENT",
    },
    "50": {
        "code": "SAINC4-50",
        "slug": "wages_salaries",
        "description": "Wages and salaries",
        "role": "LABOR_COMPONENT",
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


def require_api_key() -> str:
    api_key = os.environ.get(
        "BEA_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise RuntimeError(
            "BEA_API_KEY environment variable is not set."
        )

    return api_key


def request_series(
    *,
    api_key: str,
    line_code: str,
) -> dict[str, Any]:
    params = {
        "UserID": api_key,
        "method": "GetData",
        "datasetname": DATASET_NAME,
        "TableName": TABLE_NAME,
        "LineCode": line_code,
        "GeoFIPS": GEO_FIPS_REQUEST,
        "Year": YEAR_PARAMETER,
        "ResultFormat": "JSON",
    }

    response = requests.get(
        BEA_API_URL,
        params=params,
        timeout=120,
    )

    response.raise_for_status()

    payload = response.json()

    if "BEAAPI" not in payload:
        raise RuntimeError(
            f"Malformed BEA response for line {line_code}: "
            "missing BEAAPI."
        )

    bea_api = payload["BEAAPI"]

    results = bea_api.get("Results")

    if results is None:
        raise RuntimeError(
            f"Malformed BEA response for line {line_code}: "
            "missing Results."
        )

    # Explicitly detect API error responses.
    if isinstance(results, dict) and "Error" in results:
        raise RuntimeError(
            "BEA API ERROR\n"
            f"Line code: {line_code}\n"
            f"{json.dumps(results['Error'], indent=2)}"
        )

    data = (
        results.get("Data")
        if isinstance(results, dict)
        else None
    )

    if not isinstance(data, list):
        raise RuntimeError(
            f"Malformed BEA response for line {line_code}: "
            "Results.Data is not a list."
        )

    if not data:
        raise RuntimeError(
            f"BEA returned zero observations for line {line_code}."
        )

    return payload


def write_json(
    path: Path,
    payload: Any,
) -> None:
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def get_data_rows(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    return payload["BEAAPI"]["Results"]["Data"]


def certify_series(
    *,
    line_code: str,
    metadata: dict[str, str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_code = metadata["code"]

    observed_codes = sorted(
        {
            str(row.get("Code", "")).strip()
            for row in rows
        }
    )

    if observed_codes != [expected_code]:
        raise RuntimeError(
            "BEA SERIES-CODE CERTIFICATION FAILURE\n"
            f"Line code      : {line_code}\n"
            f"Expected code  : {expected_code}\n"
            f"Observed codes : {observed_codes}"
        )

    observed_units = sorted(
        {
            str(row.get("CL_UNIT", "")).strip()
            for row in rows
        }
    )

    if observed_units != [EXPECTED_UNIT]:
        raise RuntimeError(
            "BEA UNIT CERTIFICATION FAILURE\n"
            f"Line code      : {line_code}\n"
            f"Expected unit  : {EXPECTED_UNIT}\n"
            f"Observed units : {observed_units}"
        )

    observed_unit_mult = sorted(
        {
            str(row.get("UNIT_MULT", "")).strip()
            for row in rows
        }
    )

    if observed_unit_mult != [EXPECTED_UNIT_MULT]:
        raise RuntimeError(
            "BEA UNIT_MULT CERTIFICATION FAILURE\n"
            f"Line code          : {line_code}\n"
            f"Expected UNIT_MULT : {EXPECTED_UNIT_MULT}\n"
            f"Observed           : {observed_unit_mult}"
        )

    observed_years: set[int] = set()

    for row in rows:
        value = str(
            row.get("TimePeriod", "")
        ).strip()

        try:
            year = int(value)
        except ValueError as exc:
            raise RuntimeError(
                "BEA YEAR CERTIFICATION FAILURE\n"
                f"Line code: {line_code}\n"
                f"Invalid TimePeriod: {value!r}"
            ) from exc

        observed_years.add(year)

    expected_years = set(TARGET_YEARS)

    if observed_years != expected_years:
        raise RuntimeError(
            "BEA YEAR-COVERAGE CERTIFICATION FAILURE\n"
            f"Line code : {line_code}\n"
            f"Expected  : {sorted(expected_years)}\n"
            f"Observed  : {sorted(observed_years)}"
        )

    geographies = {
        str(row.get("GeoFips", "")).strip()
        for row in rows
    }

    if US_GEOFIPS not in geographies:
        raise RuntimeError(
            "BEA UNITED-STATES GEOGRAPHY FAILURE\n"
            f"Line code {line_code}: "
            f"{US_GEOFIPS} not found."
        )

    if WA_GEOFIPS not in geographies:
        raise RuntimeError(
            "BEA WASHINGTON GEOGRAPHY FAILURE\n"
            f"Line code {line_code}: "
            f"{WA_GEOFIPS} not found."
        )

    # Require exactly one US observation and one WA observation per year.
    us_counts: dict[int, int] = {}
    wa_counts: dict[int, int] = {}

    for year in TARGET_YEARS:
        us_counts[year] = sum(
            1
            for row in rows
            if str(row.get("GeoFips", "")).strip() == US_GEOFIPS
            and str(row.get("TimePeriod", "")).strip() == str(year)
        )

        wa_counts[year] = sum(
            1
            for row in rows
            if str(row.get("GeoFips", "")).strip() == WA_GEOFIPS
            and str(row.get("TimePeriod", "")).strip() == str(year)
        )

    bad_us = {
        year: count
        for year, count in us_counts.items()
        if count != 1
    }

    bad_wa = {
        year: count
        for year, count in wa_counts.items()
        if count != 1
    }

    if bad_us:
        raise RuntimeError(
            "BEA US OBSERVATION UNIQUENESS FAILURE\n"
            f"Line code: {line_code}\n"
            f"{bad_us}"
        )

    if bad_wa:
        raise RuntimeError(
            "BEA WA OBSERVATION UNIQUENESS FAILURE\n"
            f"Line code: {line_code}\n"
            f"{bad_wa}"
        )

    # Confirm required observations have numeric DataValue fields.
    for geography, geo_fips in (
        ("United States", US_GEOFIPS),
        ("Washington", WA_GEOFIPS),
    ):
        for year in TARGET_YEARS:
            matches = [
                row
                for row in rows
                if str(row.get("GeoFips", "")).strip() == geo_fips
                and str(row.get("TimePeriod", "")).strip() == str(year)
            ]

            row = matches[0]

            raw_value = str(
                row.get("DataValue", "")
            ).strip().replace(",", "")

            try:
                numeric_value = float(raw_value)
            except ValueError as exc:
                raise RuntimeError(
                    "BEA REQUIRED OBSERVATION NUMERIC FAILURE\n"
                    f"Line code : {line_code}\n"
                    f"Geography : {geography}\n"
                    f"Year      : {year}\n"
                    f"DataValue : {raw_value!r}"
                ) from exc

            if numeric_value <= 0:
                raise RuntimeError(
                    "BEA REQUIRED OBSERVATION VALUE FAILURE\n"
                    f"Line code : {line_code}\n"
                    f"Geography : {geography}\n"
                    f"Year      : {year}\n"
                    f"DataValue : {numeric_value}"
                )

    return {
        "line_code": line_code,
        "bea_code": expected_code,
        "description": metadata["description"],
        "role": metadata["role"],
        "observation_count": len(rows),
        "distinct_geography_count": len(geographies),
        "year_coverage": TARGET_YEARS,
        "unit": EXPECTED_UNIT,
        "unit_mult": EXPECTED_UNIT_MULT,
        "series_code_status": "PASS",
        "unit_status": "PASS",
        "unit_mult_status": "PASS",
        "year_coverage_status": "PASS",
        "us_geography_status": "PASS",
        "washington_geography_status": "PASS",
        "us_year_uniqueness_status": "PASS",
        "washington_year_uniqueness_status": "PASS",
        "required_numeric_values_status": "PASS",
    }


def main() -> int:
    api_key = require_api_key()

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 100)
    print(
        "BEA CORPORATE-INCOME-TAX INCIDENCE "
        "ALLOCATOR ACQUISITION - ETL-172H-2B"
    )
    print("=" * 100)
    print()
    print(
        "Acquisition and source certification only. "
        "No Washington corporate-tax incidence allocation."
    )
    print()

    retrieved_utc = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    manifest_series: list[dict[str, Any]] = []

    for line_code, metadata in SERIES.items():
        print(
            f"Acquiring {metadata['code']} - "
            f"{metadata['description']} ..."
        )

        payload = request_series(
            api_key=api_key,
            line_code=line_code,
        )

        filename = (
            f"sainc4_{metadata['slug']}_"
            f"2015_2024_retrieved_{retrieved_utc}.json"
        )

        output_file = SOURCE_DIR / filename

        write_json(
            output_file,
            payload,
        )

        rows = get_data_rows(
            payload
        )

        certification = certify_series(
            line_code=line_code,
            metadata=metadata,
            rows=rows,
        )

        source_sha256 = sha256_file(
            output_file
        )

        source_bytes = (
            output_file.stat().st_size
        )

        entry = {
            "line_code": line_code,
            "bea_code": metadata["code"],
            "description": metadata["description"],
            "role": metadata["role"],
            "source_file": str(
                output_file.relative_to(
                    REPO_ROOT
                )
            ),
            "source_bytes": source_bytes,
            "source_sha256": source_sha256,
            "certification": certification,
        }

        manifest_series.append(
            entry
        )

        print(
            f"  observations : "
            f"{certification['observation_count']:,}"
        )
        print(
            f"  geographies  : "
            f"{certification['distinct_geography_count']:,}"
        )
        print(
            f"  years        : "
            f"{TARGET_YEARS[0]}-{TARGET_YEARS[-1]}"
        )
        print(
            f"  units        : "
            f"{EXPECTED_UNIT}"
        )
        print(
            f"  UNIT_MULT    : "
            f"{EXPECTED_UNIT_MULT}"
        )
        print(
            f"  US           : PASS"
        )
        print(
            f"  Washington   : PASS"
        )
        print(
            f"  SHA256       : "
            f"{source_sha256}"
        )
        print()

    manifest = {
        "etl_step": "ETL-172H-2B",
        "result": "PASS",
        "retrieved_utc": retrieved_utc,
        "api": {
            "dataset_name": DATASET_NAME,
            "table_name": TABLE_NAME,
            "geo_fips_request": GEO_FIPS_REQUEST,
            "years": TARGET_YEARS,
            "api_key_persisted": False,
        },
        "allocator_source_definition": {
            "capital_component_1": {
                "line_code": "46",
                "description": (
                    "Dividends, interest, and rent"
                ),
            },
            "capital_component_2": {
                "line_code": "70",
                "description": (
                    "Proprietors' income"
                ),
            },
            "labor_component": {
                "line_code": "50",
                "description": (
                    "Wages and salaries"
                ),
            },
            "capital_formula": (
                "SAINC4 line 46 + SAINC4 line 70"
            ),
            "labor_formula": (
                "SAINC4 line 50"
            ),
            "us_denominator_source": (
                "BEA source-provided United States observation "
                "GeoFips 00000"
            ),
            "washington_geography": (
                "BEA GeoFips 53000"
            ),
        },
        "series": manifest_series,
        "methodological_boundaries": {
            "capital_income_constructed": False,
            "washington_us_shares_calculated": False,
            "corporate_incidence_75_25_applied": False,
            "omb_corporate_receipts_allocated": False,
            "rockefeller_target_matching": False,
            "irs_gross_collections_reconciliation": False,
            "database_writes": False,
            "final_ledger_inclusion_authorized": False,
        },
    }

    write_json(
        MANIFEST_FILE,
        manifest,
    )

    report_lines: list[str] = [
        "=" * 100,
        (
            "BEA CORPORATE-INCOME-TAX INCIDENCE "
            "ALLOCATOR ACQUISITION - ETL-172H-2B"
        ),
        "=" * 100,
        "",
        "SOURCE",
        "-" * 100,
        f"Dataset     : {DATASET_NAME}",
        f"Table       : {TABLE_NAME}",
        f"GeoFIPS     : {GEO_FIPS_REQUEST}",
        (
            f"Years       : "
            f"{TARGET_YEARS[0]}-{TARGET_YEARS[-1]}"
        ),
        "",
        "CERTIFIED SERIES",
        "-" * 100,
    ]

    for entry in manifest_series:
        cert = entry["certification"]

        report_lines.extend(
            [
                (
                    f"{entry['bea_code']:<12} "
                    f"{entry['description']}"
                ),
                (
                    f"  role             : "
                    f"{entry['role']}"
                ),
                (
                    f"  observations     : "
                    f"{cert['observation_count']:,}"
                ),
                (
                    f"  geographies      : "
                    f"{cert['distinct_geography_count']:,}"
                ),
                (
                    f"  units            : "
                    f"{cert['unit']}"
                ),
                (
                    f"  UNIT_MULT        : "
                    f"{cert['unit_mult']}"
                ),
                (
                    f"  year coverage    : PASS"
                ),
                (
                    f"  US geography     : PASS"
                ),
                (
                    f"  Washington       : PASS"
                ),
                (
                    f"  required values  : PASS"
                ),
                (
                    f"  SHA256           : "
                    f"{entry['source_sha256']}"
                ),
                "",
            ]
        )

    report_lines.extend(
        [
            "ALLOCATOR DEFINITION",
            "-" * 100,
            (
                "Capital numerator/denominator components:"
            ),
            (
                "  SAINC4-46 Dividends, interest, and rent"
            ),
            (
                "  + SAINC4-70 Proprietors' income"
            ),
            "",
            "Labor component:",
            (
                "  SAINC4-50 Wages and salaries"
            ),
            "",
            (
                "United States denominator will use the "
                "source-provided GeoFips 00000 observation."
            ),
            (
                "Washington numerator will use GeoFips 53000."
            ),
            "",
            "BOUNDARY",
            "-" * 100,
            (
                "No capital aggregate or Washington/US shares "
                "are calculated in ETL-172H-2B."
            ),
            (
                "The Rockefeller 75/25 corporate-incidence "
                "weighting is not applied."
            ),
            (
                "No OMB corporate-income-tax receipts are allocated."
            ),
            (
                "Final ledger inclusion remains unauthorized."
            ),
            "",
            "ETL-172H-2B RESULT: PASS",
            "",
        ]
    )

    REPORT_FILE.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    print("CERTIFICATION SUMMARY")
    print("-" * 100)

    for entry in manifest_series:
        print(
            f"{entry['bea_code']:<12} "
            f"{entry['description']:<35} PASS"
        )

    print()
    print(
        "Manifest : "
        f"{MANIFEST_FILE.relative_to(REPO_ROOT)}"
    )
    print(
        "Report   : "
        f"{REPORT_FILE.relative_to(REPO_ROOT)}"
    )
    print()
    print(
        "ETL-172H-2B RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )