from __future__ import annotations

import csv
import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from etl.common.db import get_connection


ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "wages"
    / "state_universe"
)

INTERIM_DIR = (
    ROOT
    / "data"
    / "interim"
    / "bea"
)

BEA_API_URL = "https://apps.bea.gov/api/data"

YEARS = list(range(2015, 2025))

TABLE_NAME = "SAINC7N"
LINE_CODE = "2002"

WASHINGTON_GEOFIPS = "53000"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def get_bea_api_key() -> str:
    for env_name in (
        "BEA_API_KEY",
        "BEA_API_USER_ID",
        "BEA_USER_ID",
    ):
        value = os.environ.get(env_name)

        if value:
            return value.strip()

    raise RuntimeError(
        "BEA API key not found. Expected one of: "
        "BEA_API_KEY, BEA_API_USER_ID, BEA_USER_ID."
    )


def acquire_bea_state_universe() -> Path:
    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    api_key = get_bea_api_key()

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    output_path = (
        RAW_DIR
        / (
            "sainc7n_military_wages_all_states_"
            f"2015_2024_retrieved_{timestamp}.json"
        )
    )

    params = {
        "UserID": api_key,
        "method": "GetData",
        "datasetname": "Regional",
        "TableName": TABLE_NAME,
        "LineCode": LINE_CODE,
        "Year": ",".join(str(y) for y in YEARS),
        "GeoFips": "STATE",
        "ResultFormat": "json",
    }

    url = (
        BEA_API_URL
        + "?"
        + urllib.parse.urlencode(params)
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "WCFFBP/1.0 "
                "OMB-BEA military wage allocation diagnostic"
            )
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=120,
    ) as response:
        payload = response.read()

    output_path.write_bytes(
        payload
    )

    print(
        f"Preserved BEA state-universe response: {output_path}"
    )

    print(
        f"SHA-256: {sha256_file(output_path)}"
    )

    return output_path


def extract_bea_rows(
    source_path: Path,
) -> list[dict]:
    payload = json.loads(
        source_path.read_text(
            encoding="utf-8"
        )
    )

    try:
        results = payload[
            "BEAAPI"
        ][
            "Results"
        ]

    except KeyError as exc:
        raise RuntimeError(
            "Unexpected BEA API response structure."
        ) from exc

    if "Error" in results:
        raise RuntimeError(
            "BEA API returned an error:\n"
            + json.dumps(
                results["Error"],
                indent=2,
            )
        )

    data = results.get(
        "Data"
    )

    if not data:
        raise RuntimeError(
            "BEA API response contains no Data rows."
        )

    rows = []

    for row in data:
        year = int(
            row["TimePeriod"]
        )

        if year not in YEARS:
            continue

        value_text = (
            row["DataValue"]
            .replace(",", "")
            .strip()
        )

        if not value_text:
            continue

        value = float(
            value_text
        )

        unit_mult = int(
            row.get(
                "UNIT_MULT",
                "0",
            )
        )

        value_dollars = int(
            round(
                value
                * (10 ** unit_mult)
            )
        )

        rows.append(
            {
                "geo_fips": (
                    row["GeoFips"]
                    .strip()
                ),
                "geo_name": (
                    row["GeoName"]
                    .strip()
                ),
                "year": year,
                "value_raw": value,
                "unit_mult": unit_mult,
                "value_dollars": value_dollars,
            }
        )

    return rows


def validate_bea_rows(
    rows: list[dict],
) -> None:
    if not rows:
        raise RuntimeError(
            "No BEA rows were parsed."
        )

    years_seen = {
        row["year"]
        for row in rows
    }

    if years_seen != set(YEARS):
        raise RuntimeError(
            "BEA state-universe response does not contain "
            "exactly 2015-2024."
        )

    wa_rows = [
        row
        for row in rows
        if row["geo_fips"] == WASHINGTON_GEOFIPS
    ]

    if len(wa_rows) != 10:
        raise RuntimeError(
            "Expected 10 Washington observations; "
            f"found {len(wa_rows)}."
        )


def load_omb_controls() -> dict[int, int]:
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    fiscal_year,
                    military_wage_obligations_dollars
                FROM omb.v_federal_wage_obligation_control
                WHERE fiscal_year BETWEEN 2015 AND 2024
                ORDER BY fiscal_year
                """
            )

            rows = cur.fetchall()

    finally:
        conn.close()

    if len(rows) != 10:
        raise RuntimeError(
            "Expected 10 OMB military wage controls; "
            f"found {len(rows)}."
        )

    return {
        int(year): int(value)
        for year, value in rows
    }


def build_diagnostic(
    bea_rows: list[dict],
    omb_controls: dict[int, int],
) -> list[dict]:

    results = []

    for year in YEARS:

        year_rows = [
            row
            for row in bea_rows
            if row["year"] == year
        ]

        # --------------------------------------------------------------
        # Identify the BEA United States control row.
        # --------------------------------------------------------------

        us_rows = [
            row
            for row in year_rows
            if row["geo_fips"] == "00000"
        ]

        if len(us_rows) != 1:
            raise RuntimeError(
                f"FFY{year}: expected exactly one BEA "
                f"United States row; found {len(us_rows)}."
            )

        bea_us_dollars = (
            us_rows[0]["value_dollars"]
        )

        # --------------------------------------------------------------
        # Define the allocation universe explicitly:
        #
        # 50 states + District of Columbia.
        #
        # BEA GeoFips returned by GeoFips=STATE also includes:
        #
        #   00000       United States
        #   91000-98000 BEA regions
        #
        # Those aggregate geographies MUST NOT enter the state-share
        # denominator.
        #
        # State/DC GeoFips have the form XX000 and use ordinary state
        # FIPS prefixes 01-56, including DC = 11.
        # --------------------------------------------------------------

        state_rows = []

        for row in year_rows:

            geo_fips = row["geo_fips"]

            if len(geo_fips) != 5:
                continue

            if not geo_fips.endswith("000"):
                continue

            state_fips = int(
                geo_fips[:2]
            )

            if 1 <= state_fips <= 56:
                state_rows.append(
                    row
                )

        # We require exactly 50 states + DC.
        if len(state_rows) != 51:
            raise RuntimeError(
                f"FFY{year}: expected exactly 51 "
                "state/DC observations; "
                f"found {len(state_rows)}."
            )

        # --------------------------------------------------------------
        # Washington must occur exactly once inside the state universe.
        # --------------------------------------------------------------

        washington_rows = [
            row
            for row in state_rows
            if row["geo_fips"]
            == WASHINGTON_GEOFIPS
        ]

        if len(washington_rows) != 1:
            raise RuntimeError(
                f"FFY{year}: expected exactly one "
                "Washington observation."
            )

        wa_dollars = (
            washington_rows[0][
                "value_dollars"
            ]
        )

        # --------------------------------------------------------------
        # Sum only the 50 states + DC.
        # --------------------------------------------------------------

        state_sum_dollars = sum(
            row["value_dollars"]
            for row in state_rows
        )

        if state_sum_dollars <= 0:
            raise RuntimeError(
                f"FFY{year}: invalid BEA state denominator."
            )

        # --------------------------------------------------------------
        # Independent geography reconciliation.
        #
        # The state/DC universe should reconcile to BEA's published
        # United States control. Do not silently proceed if it does not.
        # --------------------------------------------------------------

        state_us_difference = (
            state_sum_dollars
            - bea_us_dollars
        )

        if state_us_difference != 0:
            raise RuntimeError(
                f"FFY{year}: sum of 50 states + DC "
                "does not reconcile to BEA United States. "
                f"State sum=${state_sum_dollars:,}; "
                f"US=${bea_us_dollars:,}; "
                f"difference=${state_us_difference:,}."
            )

        # --------------------------------------------------------------
        # Washington allocation share.
        # --------------------------------------------------------------

        wa_share = (
            wa_dollars
            / state_sum_dollars
        )

        omb_us_dollars = (
            omb_controls[year]
        )

        allocated_omb_dollars = int(
            round(
                omb_us_dollars
                * wa_share
            )
        )

        difference_dollars = (
            allocated_omb_dollars
            - wa_dollars
        )

        ratio = (
            allocated_omb_dollars
            / wa_dollars
            if wa_dollars
            else None
        )

        results.append(
            {
                "fiscal_year":
                    year,

                "omb_us_military_wage_obligations_dollars":
                    omb_us_dollars,

                "bea_us_military_wages_dollars":
                    bea_us_dollars,

                "bea_state_dc_sum_military_wages_dollars":
                    state_sum_dollars,

                "bea_state_dc_minus_us_dollars":
                    state_us_difference,

                "bea_wa_military_wages_dollars":
                    wa_dollars,

                "wa_bea_share":
                    wa_share,

                "allocated_omb_wa_military_wages_dollars":
                    allocated_omb_dollars,

                "allocated_minus_bea_wa_dollars":
                    difference_dollars,

                "allocated_to_bea_wa_ratio":
                    ratio,
            }
        )

    return results


def write_diagnostic_csv(
    results: list[dict],
) -> Path:

    INTERIM_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        INTERIM_DIR
        / "omb_bea_military_wage_allocation_diagnostic_2015_2024.csv"
    )

    fieldnames = list(
        results[0].keys()
    )

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(
            results
        )

    return output_path


def print_results(
    results: list[dict],
) -> None:

    print()
    print("=" * 126)

    print(
        "OMB × BEA MILITARY WAGE ALLOCATION DIAGNOSTIC"
    )

    print("=" * 126)

    print(
        "FY    "
        "OMB US $B    "
        "BEA US $B    "
        "States+DC $B    "
        "BEA WA $B    "
        "WA Share    "
        "OMB→WA $B    "
        "Δ vs BEA $B    "
        "Ratio"
    )

    print("-" * 126)

    for row in results:

        print(
            f"{row['fiscal_year']}  "
            f"{row['omb_us_military_wage_obligations_dollars'] / 1e9:10.3f}  "
            f"{row['bea_us_military_wages_dollars'] / 1e9:9.3f}  "
            f"{row['bea_state_dc_sum_military_wages_dollars'] / 1e9:12.3f}  "
            f"{row['bea_wa_military_wages_dollars'] / 1e9:9.3f}  "
            f"{row['wa_bea_share']:8.4%}  "
            f"{row['allocated_omb_wa_military_wages_dollars'] / 1e9:9.3f}  "
            f"{row['allocated_minus_bea_wa_dollars'] / 1e9:11.3f}  "
            f"{row['allocated_to_bea_wa_ratio']:6.3f}"
        )

    print()
    print(
        "BEA geography reconciliation: "
        "50 STATES + DC = UNITED STATES — PASSED"
    )


def main() -> None:

    print(
        "Acquiring BEA SAINC7N military wages for all states..."
    )

    source_path = (
        acquire_bea_state_universe()
    )

    bea_rows = extract_bea_rows(
        source_path
    )

    validate_bea_rows(
        bea_rows
    )

    print(
        "BEA state-universe validation: PASSED"
    )

    omb_controls = (
        load_omb_controls()
    )

    print(
        "OMB control retrieval: PASSED"
    )

    results = build_diagnostic(
        bea_rows,
        omb_controls,
    )

    print_results(
        results
    )

    output_path = (
        write_diagnostic_csv(
            results
        )
    )

    print()
    print(
        f"Diagnostic CSV: {output_path}"
    )

    print(
        f"Diagnostic SHA-256: "
        f"{sha256_file(output_path)}"
    )

    print()
    print(
        "DIAGNOSTIC COMPLETE — "
        "NO DATABASE VALUES WERE WRITTEN."
    )


if __name__ == "__main__":
    main()