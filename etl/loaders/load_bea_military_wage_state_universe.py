from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from etl.common.db import get_connection


ROOT = Path(__file__).resolve().parents[2]

SOURCE_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "wages"
    / "state_universe"
)

EXPECTED_YEARS = set(range(2015, 2025))
EXPECTED_TOTAL_ROWS = 600
EXPECTED_ROWS_PER_YEAR = 60
EXPECTED_STATE_DC_ROWS_PER_YEAR = 51
EXPECTED_REGION_ROWS_PER_YEAR = 8

WASHINGTON_GEOFIPS = "53000"
UNITED_STATES_GEOFIPS = "00000"

BEA_REGION_GEOFIPS = {
    "91000",
    "92000",
    "93000",
    "94000",
    "95000",
    "96000",
    "97000",
    "98000",
}

EXPECTED_TABLE = "SAINC7N"
EXPECTED_LINE_CODE = "2002"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def find_latest_source_file() -> Path:
    matches = sorted(
        SOURCE_DIR.glob(
            "sainc7n_military_wages_all_states_"
            "2015_2024_retrieved_*.json"
        )
    )

    if not matches:
        raise RuntimeError(
            "No preserved BEA SAINC7N all-state military-wage "
            f"response found under {SOURCE_DIR}"
        )

    return matches[-1]


def parse_retrieval_timestamp(
    source_path: Path,
) -> datetime | None:

    name = source_path.stem

    marker = "_retrieved_"

    if marker not in name:
        return None

    stamp = name.split(marker, 1)[1]

    try:
        return datetime.strptime(
            stamp,
            "%Y%m%dT%H%M%SZ",
        ).replace(
            tzinfo=timezone.utc
        )

    except ValueError:
        return None


def load_source_rows(
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
            "BEA API response contains an error:\n"
            + json.dumps(
                results["Error"],
                indent=2,
            )
        )

    data = results.get("Data")

    if not data:
        raise RuntimeError(
            "BEA API response contains no Data rows."
        )

    rows = []

    for source_row_number, row in enumerate(
        data,
        start=1,
    ):
        year = int(
            row["TimePeriod"]
        )

        if year not in EXPECTED_YEARS:
            continue

        geo_fips = (
            row["GeoFips"]
            .strip()
        )

        geo_name = (
            row["GeoName"]
            .strip()
        )

        raw_value = (
            row["DataValue"]
            .strip()
        )

        numeric_value = float(
            raw_value.replace(",", "")
        )

        unit_multiplier = int(
            row.get(
                "UNIT_MULT",
                "0",
            )
        )

        value_dollars = int(
            round(
                numeric_value
                * (10 ** unit_multiplier)
            )
        )

        rows.append(
            {
                "source_row_number":
                    source_row_number,

                "calendar_year":
                    year,

                "source_geo_fips":
                    geo_fips,

                "source_geo_name":
                    geo_name,

                "source_data_value":
                    raw_value,

                "source_unit":
                    row.get("CL_UNIT"),

                "source_unit_multiplier":
                    unit_multiplier,

                "value_dollars":
                    value_dollars,
            }
        )

    return rows


def classify_geography(
    geo_fips: str,
) -> str:

    if geo_fips == UNITED_STATES_GEOFIPS:
        return "UNITED_STATES"

    if geo_fips in BEA_REGION_GEOFIPS:
        return "BEA_REGION"

    if geo_fips == "11000":
        return "DISTRICT_OF_COLUMBIA"

    if (
        len(geo_fips) == 5
        and geo_fips.endswith("000")
    ):
        state_fips = int(
            geo_fips[:2]
        )

        if 1 <= state_fips <= 56:
            return "STATE"

    raise RuntimeError(
        f"Unexpected BEA geography: {geo_fips}"
    )


def validate_source_rows(
    rows: list[dict],
) -> None:

    if len(rows) != EXPECTED_TOTAL_ROWS:
        raise RuntimeError(
            f"Expected {EXPECTED_TOTAL_ROWS} BEA rows; "
            f"found {len(rows)}."
        )

    years_seen = {
        row["calendar_year"]
        for row in rows
    }

    if years_seen != EXPECTED_YEARS:
        raise RuntimeError(
            "Expected exactly calendar years 2015-2024."
        )

    seen_keys = set()

    for row in rows:

        key = (
            row["calendar_year"],
            row["source_geo_fips"],
        )

        if key in seen_keys:
            raise RuntimeError(
                f"Duplicate source key: {key}"
            )

        seen_keys.add(
            key
        )

        geography_level = classify_geography(
            row["source_geo_fips"]
        )

        row["geography_level"] = (
            geography_level
        )

    for year in sorted(
        EXPECTED_YEARS
    ):

        year_rows = [
            row
            for row in rows
            if row["calendar_year"] == year
        ]

        if len(year_rows) != EXPECTED_ROWS_PER_YEAR:
            raise RuntimeError(
                f"{year}: expected "
                f"{EXPECTED_ROWS_PER_YEAR} rows; "
                f"found {len(year_rows)}."
            )

        us_rows = [
            row
            for row in year_rows
            if row["geography_level"]
            == "UNITED_STATES"
        ]

        if len(us_rows) != 1:
            raise RuntimeError(
                f"{year}: expected exactly one "
                "United States row."
            )

        state_dc_rows = [
            row
            for row in year_rows
            if row["geography_level"]
            in {
                "STATE",
                "DISTRICT_OF_COLUMBIA",
            }
        ]

        if (
            len(state_dc_rows)
            != EXPECTED_STATE_DC_ROWS_PER_YEAR
        ):
            raise RuntimeError(
                f"{year}: expected 51 state/DC rows; "
                f"found {len(state_dc_rows)}."
            )

        region_rows = [
            row
            for row in year_rows
            if row["geography_level"]
            == "BEA_REGION"
        ]

        if (
            len(region_rows)
            != EXPECTED_REGION_ROWS_PER_YEAR
        ):
            raise RuntimeError(
                f"{year}: expected 8 BEA-region rows; "
                f"found {len(region_rows)}."
            )

        wa_rows = [
            row
            for row in state_dc_rows
            if row["source_geo_fips"]
            == WASHINGTON_GEOFIPS
        ]

        if len(wa_rows) != 1:
            raise RuntimeError(
                f"{year}: expected exactly one "
                "Washington row."
            )

        state_dc_sum = sum(
            row["value_dollars"]
            for row in state_dc_rows
        )

        us_value = (
            us_rows[0]["value_dollars"]
        )

        if state_dc_sum != us_value:
            raise RuntimeError(
                f"{year}: state/DC sum does not "
                "reconcile to BEA United States. "
                f"state/DC=${state_dc_sum:,}; "
                f"US=${us_value:,}; "
                f"difference="
                f"${state_dc_sum - us_value:,}"
            )

        region_sum = sum(
            row["value_dollars"]
            for row in region_rows
        )

        if region_sum != us_value:
            raise RuntimeError(
                f"{year}: BEA-region sum does not "
                "reconcile to United States. "
                f"regions=${region_sum:,}; "
                f"US=${us_value:,}; "
                f"difference="
                f"${region_sum - us_value:,}"
            )


def build_state_id_lookup(
    conn,
) -> dict[str, int]:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                state_fips,
                state_id
            FROM reference.state_registry
            """
        )

        rows = cur.fetchall()

    return {
        str(state_fips).strip().zfill(2):
            int(state_id)
        for state_fips, state_id in rows
    }

def resolve_state_id(
    row: dict,
    state_lookup: dict[str, int],
) -> int | None:

    if row["geography_level"] not in {
        "STATE",
        "DISTRICT_OF_COLUMBIA",
    }:
        return None

    state_fips = (
        row["source_geo_fips"][:2]
    )

    state_id = state_lookup.get(
        state_fips
    )

    if state_id is None:
        raise RuntimeError(
            "Could not resolve reference.state_registry "
            f"for state FIPS {state_fips} "
            f"({row['source_geo_name']})."
        )

    return state_id


def create_load_batch(
    conn,
    *,
    source_path: Path,
    source_sha256: str,
    retrieved_utc: datetime | None,
) -> int:

    with conn.cursor() as cur:

        cur.execute(
            """
            INSERT INTO bea.wage_load_batch (
                dataset_name,
                source_table,
                source_line_code,
                source_file,
                source_file_sha256,
                source_retrieved_utc,
                calendar_year_start,
                calendar_year_end,
                expected_rows,
                status,
                notes
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                2015,
                2024,
                600,
                'STARTED',
                %s
            )
            RETURNING load_batch_id
            """,
            (
                "BEA_REGIONAL",
                EXPECTED_TABLE,
                EXPECTED_LINE_CODE,
                str(
                    source_path.relative_to(
                        ROOT
                    )
                ),
                source_sha256,
                retrieved_utc,
                (
                    "BEA SAINC7N line 2002 federal military "
                    "wage-and-salary evidence. Preserves the "
                    "United States, 50 states, District of "
                    "Columbia, and eight BEA regions for "
                    "calendar years 2015-2024. Geographic "
                    "allocation evidence only; OMB remains "
                    "the national federal wage accounting "
                    "control."
                ),
            ),
        )

        return int(
            cur.fetchone()[0]
        )


def insert_rows(
    conn,
    *,
    load_batch_id: int,
    rows: list[dict],
    source_path: Path,
    source_sha256: str,
    state_lookup: dict[str, int],
) -> int:

    inserted = 0

    relative_source_path = str(
        source_path.relative_to(
            ROOT
        )
    )

    with conn.cursor() as cur:

        for row in rows:

            state_id = resolve_state_id(
                row,
                state_lookup,
            )

            cur.execute(
                """
                INSERT INTO bea.wage_observation (
                    load_batch_id,
                    wage_family,
                    accounting_measure,
                    reference_period_type,
                    calendar_year,
                    geographic_basis,
                    geography_level,
                    state_id,
                    source_dataset,
                    source_table,
                    source_line_code,
                    source_code,
                    source_geo_fips,
                    source_geo_name,
                    source_data_value,
                    source_unit,
                    source_unit_multiplier,
                    value_dollars,
                    source_file,
                    source_file_sha256,
                    source_row_number
                )
                VALUES (
                    %s,
                    'MILITARY',
                    'WAGES_AND_SALARIES',
                    'CALENDAR_YEAR',
                    %s,
                    'BEA_STATE_ALLOCATION',
                    %s,
                    %s,
                    'BEA_REGIONAL',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    load_batch_id,
                    row["calendar_year"],
                    row["geography_level"],
                    state_id,
                    EXPECTED_TABLE,
                    EXPECTED_LINE_CODE,
                    "FEDERAL_MILITARY",
                    row["source_geo_fips"],
                    row["source_geo_name"],
                    row["source_data_value"],
                    row["source_unit"],
                    row[
                        "source_unit_multiplier"
                    ],
                    row["value_dollars"],
                    relative_source_path,
                    source_sha256,
                    row[
                        "source_row_number"
                    ],
                ),
            )

            inserted += 1

    return inserted


def validate_database_population(
    conn,
    load_batch_id: int,
) -> None:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT COUNT(*)
            FROM bea.wage_observation
            WHERE load_batch_id = %s
            """,
            (load_batch_id,),
        )

        row_count = int(
            cur.fetchone()[0]
        )

        if row_count != 600:
            raise RuntimeError(
                "Database validation failed: "
                f"expected 600 rows; found {row_count}."
            )

        cur.execute(
            """
            SELECT
                calendar_year,

                COUNT(*) AS total_rows,

                COUNT(*) FILTER (
                    WHERE geography_level = 'UNITED_STATES'
                ) AS us_rows,

                COUNT(*) FILTER (
                    WHERE geography_level IN (
                        'STATE',
                        'DISTRICT_OF_COLUMBIA'
                    )
                ) AS state_dc_rows,

                COUNT(*) FILTER (
                    WHERE geography_level = 'BEA_REGION'
                ) AS region_rows,

                COUNT(*) FILTER (
                    WHERE source_geo_fips = '53000'
                ) AS wa_rows,

                SUM(value_dollars) FILTER (
                    WHERE geography_level IN (
                        'STATE',
                        'DISTRICT_OF_COLUMBIA'
                    )
                ) AS state_dc_sum,

                MAX(value_dollars) FILTER (
                    WHERE geography_level = 'UNITED_STATES'
                ) AS us_value,

                SUM(value_dollars) FILTER (
                    WHERE geography_level = 'BEA_REGION'
                ) AS region_sum

            FROM bea.wage_observation

            WHERE load_batch_id = %s

            GROUP BY calendar_year

            ORDER BY calendar_year
            """,
            (load_batch_id,),
        )

        results = cur.fetchall()

    if len(results) != 10:
        raise RuntimeError(
            "Database validation failed: "
            f"expected 10 annual groups; "
            f"found {len(results)}."
        )

    for (
        year,
        total_rows,
        us_rows,
        state_dc_rows,
        region_rows,
        wa_rows,
        state_dc_sum,
        us_value,
        region_sum,
    ) in results:

        if int(total_rows) != 60:
            raise RuntimeError(
                f"{year}: expected 60 rows."
            )

        if int(us_rows) != 1:
            raise RuntimeError(
                f"{year}: expected one US row."
            )

        if int(state_dc_rows) != 51:
            raise RuntimeError(
                f"{year}: expected 51 state/DC rows."
            )

        if int(region_rows) != 8:
            raise RuntimeError(
                f"{year}: expected 8 BEA region rows."
            )

        if int(wa_rows) != 1:
            raise RuntimeError(
                f"{year}: expected one Washington row."
            )

        if int(state_dc_sum) != int(us_value):
            raise RuntimeError(
                f"{year}: state/DC database reconciliation "
                "failed."
            )

        if int(region_sum) != int(us_value):
            raise RuntimeError(
                f"{year}: region database reconciliation "
                "failed."
            )


def mark_batch_complete(
    conn,
    *,
    load_batch_id: int,
    rows_loaded: int,
) -> None:

    with conn.cursor() as cur:

        cur.execute(
            """
            UPDATE bea.wage_load_batch
            SET
                rows_loaded = %s,
                status = 'COMPLETED',
                completed_at = CURRENT_TIMESTAMP
            WHERE load_batch_id = %s
            """,
            (
                rows_loaded,
                load_batch_id,
            ),
        )


def main() -> None:

    source_path = (
        find_latest_source_file()
    )

    source_sha256 = sha256_file(
        source_path
    )

    retrieved_utc = (
        parse_retrieval_timestamp(
            source_path
        )
    )

    print(
        f"Source file:       {source_path}"
    )

    print(
        f"Source SHA-256:    {source_sha256}"
    )

    if retrieved_utc is not None:
        print(
            "Retrieved UTC:     "
            f"{retrieved_utc.isoformat()}"
        )

    rows = load_source_rows(
        source_path
    )

    validate_source_rows(
        rows
    )

    print()
    print(
        "Pre-load source validation: PASSED"
    )

    print(
        "Rows:               600"
    )

    print(
        "Years:              2015-2024"
    )

    print(
        "Geographies/year:   60"
    )

    print(
        "State/DC rows/year: 51"
    )

    print(
        "BEA regions/year:   8"
    )

    print(
        "State/DC = U.S.:    PASSED"
    )

    print(
        "Regions = U.S.:     PASSED"
    )

    conn = get_connection()

    try:

        state_lookup = (
            build_state_id_lookup(
                conn
            )
        )

        load_batch_id = (
            create_load_batch(
                conn,
                source_path=source_path,
                source_sha256=source_sha256,
                retrieved_utc=retrieved_utc,
            )
        )

        print()
        print(
            "Created BEA wage "
            f"load_batch_id={load_batch_id}"
        )

        inserted = insert_rows(
            conn,
            load_batch_id=load_batch_id,
            rows=rows,
            source_path=source_path,
            source_sha256=source_sha256,
            state_lookup=state_lookup,
        )

        if inserted != 600:
            raise RuntimeError(
                f"Expected 600 inserts; "
                f"inserted {inserted}."
            )

        validate_database_population(
            conn,
            load_batch_id,
        )

        mark_batch_complete(
            conn,
            load_batch_id=load_batch_id,
            rows_loaded=inserted,
        )

        conn.commit()

        print()
        print("=" * 72)
        print(
            "BEA MILITARY WAGE STATE-UNIVERSE LOAD COMPLETE"
        )
        print("=" * 72)

        print(
            f"Load batch ID:      {load_batch_id}"
        )

        print(
            f"Rows loaded:        {inserted}"
        )

        print(
            "Source table:       SAINC7N"
        )

        print(
            "Source line code:   2002"
        )

        print(
            "Wage family:        MILITARY"
        )

        print(
            "Calendar years:     2015-2024"
        )

        print(
            "State/DC = U.S.:    PASSED"
        )

        print(
            "Regions = U.S.:     PASSED"
        )

        print(
            "Database validation: PASSED"
        )

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()


if __name__ == "__main__":
    main()