from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from etl.common.db import get_connection


ROOT = Path(__file__).resolve().parents[2]

RAW_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "compensation"
)

EXPECTED_TOTAL_ROWS = 820
EXPECTED_COUNTY_ROWS = 780
EXPECTED_STATE_ROWS = 40

EXPECTED_YEARS = set(range(2015, 2025))

SERIES = {
    ("CAINC6N", "2001"): "FEDERAL_CIVILIAN_COMPENSATION",
    ("CAINC6N", "2002"): "MILITARY_COMPENSATION",
    ("SAINC6N", "2001"): "FEDERAL_CIVILIAN_COMPENSATION",
    ("SAINC6N", "2002"): "MILITARY_COMPENSATION",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def find_latest_manifest() -> Path:
    manifests = sorted(
        RAW_ROOT.glob(
            "bea_compensation_acquisition_manifest_*.json"
        )
    )

    if not manifests:
        raise RuntimeError(
            "No BEA compensation acquisition manifest found."
        )

    return manifests[-1]


def load_json(path: Path) -> dict:
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def resolve_repo_path(
    relative_path: str,
) -> Path:

    path = ROOT / Path(relative_path)

    if not path.exists():
        raise RuntimeError(
            f"Manifest source file does not exist: {path}"
        )

    return path


def parse_bea_code(
    source_code: str,
) -> tuple[str, str]:

    try:
        table_name, line_code = (
            source_code.split("-", 1)
        )
    except ValueError as exc:
        raise RuntimeError(
            f"Unexpected BEA Code: {source_code!r}"
        ) from exc

    if (
        table_name,
        line_code,
    ) not in SERIES:
        raise RuntimeError(
            "Unexpected BEA compensation series: "
            f"{table_name}-{line_code}"
        )

    return table_name, line_code


def normalize_value_dollars(
    row: dict,
) -> Decimal:

    raw_value = str(
        row.get("DataValue", "")
    ).strip()

    if raw_value in {
        "",
        "(NA)",
        "(D)",
        "(L)",
        "NA",
        "N/A",
    }:
        raise RuntimeError(
            "Non-numeric or suppressed BEA value: "
            f"{raw_value!r} for "
            f"{row.get('GeoFips')} "
            f"{row.get('TimePeriod')}"
        )

    raw_value = raw_value.replace(",", "")

    try:
        source_value = Decimal(
            raw_value
        )
    except InvalidOperation as exc:
        raise RuntimeError(
            f"Invalid BEA DataValue: {raw_value!r}"
        ) from exc

    try:
        unit_multiplier = int(
            row["UNIT_MULT"]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise RuntimeError(
            "Invalid or missing UNIT_MULT in BEA row."
        ) from exc

    return (
        source_value
        * (Decimal(10) ** unit_multiplier)
    )


def get_reference_geography(
    conn,
) -> tuple[int, dict[str, int]]:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT state_id
            FROM reference.state_registry
            WHERE state_abbreviation = 'WA'
            """
        )

        row = cur.fetchone()

        if row is None:
            raise RuntimeError(
                "Washington not found in "
                "reference.state_registry."
            )

        state_id = row[0]

        cur.execute(
            """
            SELECT
                full_fips,
                county_id
            FROM reference.county_registry
            WHERE state_id = %s
            ORDER BY full_fips
            """,
            (state_id,),
        )

        county_map = {
            full_fips: county_id
            for full_fips, county_id
            in cur.fetchall()
        }

    if len(county_map) != 39:
        raise RuntimeError(
            "Expected 39 Washington counties in "
            "reference.county_registry; "
            f"found {len(county_map)}."
        )

    return state_id, county_map


def validate_manifest(
    manifest_path: Path,
    manifest: dict,
) -> list[dict]:

    requests = manifest.get(
        "requests"
    )

    if not isinstance(
        requests,
        list,
    ):
        raise RuntimeError(
            "Manifest requests field is missing "
            "or is not a list."
        )

    if len(requests) != 4:
        raise RuntimeError(
            "Expected exactly four BEA source "
            f"requests; found {len(requests)}."
        )

    expected_pairs = {
        ("CAINC6N", "2001"),
        ("CAINC6N", "2002"),
        ("SAINC6N", "2001"),
        ("SAINC6N", "2002"),
    }

    observed_pairs = {
        (
            str(item["table_name"]),
            str(item["line_code"]),
        )
        for item in requests
    }

    if observed_pairs != expected_pairs:
        raise RuntimeError(
            "Manifest does not contain the expected "
            "four BEA compensation series. "
            f"Observed: {observed_pairs}"
        )

    for item in requests:

        source_path = resolve_repo_path(
            item["file"]
        )

        actual_sha256 = sha256_file(
            source_path
        )

        expected_sha256 = str(
            item["sha256"]
        )

        if (
            actual_sha256
            != expected_sha256
        ):
            raise RuntimeError(
                "SHA-256 mismatch for "
                f"{source_path}\n"
                f"Expected: {expected_sha256}\n"
                f"Actual:   {actual_sha256}"
            )

        if int(
            item.get(
                "row_count",
                0,
            )
        ) <= 0:
            raise RuntimeError(
                "Manifest contains a zero-row "
                f"source file: {source_path}"
            )

    return requests


def create_load_batch(
    conn,
    manifest_path: Path,
    manifest: dict,
) -> int:

    manifest_sha256 = sha256_file(
        manifest_path
    )

    retrieved_values = [
        item.get("retrieved_utc")
        for item in manifest["requests"]
        if item.get("retrieved_utc")
    ]

    source_retrieved_utc = None

    if retrieved_values:
        source_retrieved_utc = min(
            datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )
            for value in retrieved_values
        )

    with conn.cursor() as cur:

        cur.execute(
            """
            INSERT INTO bea.compensation_load_batch (
                acquisition_manifest_path,
                acquisition_manifest_sha256,
                source_retrieved_utc,
                calendar_year_start,
                calendar_year_end,
                status,
                notes
            )
            VALUES (
                %s,
                %s,
                %s,
                2015,
                2024,
                'STARTED',
                %s
            )
            RETURNING load_batch_id
            """,
            (
                str(
                    manifest_path.relative_to(
                        ROOT
                    )
                ),
                manifest_sha256,
                source_retrieved_utc,
                (
                    "Initial WCFFBP BEA federal "
                    "civilian and military "
                    "compensation load from "
                    "preserved API acquisition."
                ),
            ),
        )

        return cur.fetchone()[0]


def extract_data_rows(
    source_path: Path,
) -> list[dict]:

    payload = load_json(
        source_path
    )

    beaapi = payload.get(
        "BEAAPI",
        {},
    )

    if "Error" in beaapi:
        raise RuntimeError(
            "Preserved BEA source contains API error: "
            + json.dumps(
                beaapi["Error"],
                indent=2,
            )
        )

    results = beaapi.get(
        "Results",
        {},
    )

    if not isinstance(
        results,
        dict,
    ):
        raise RuntimeError(
            f"Missing BEA Results in {source_path}"
        )

    rows = results.get(
        "Data"
    )

    if not isinstance(
        rows,
        list,
    ):
        raise RuntimeError(
            f"Missing BEA Results.Data in {source_path}"
        )

    if not rows:
        raise RuntimeError(
            f"Zero BEA data rows in {source_path}"
        )

    return rows


def insert_source_file(
    conn,
    *,
    load_batch_id: int,
    source_path: Path,
    source_file_sha256: str,
    expected_table: str,
    expected_line_code: str,
    state_id: int,
    county_map: dict[str, int],
) -> tuple[int, int, int]:

    rows = extract_data_rows(
        source_path
    )

    loaded = 0
    county_rows = 0
    state_rows = 0

    with conn.cursor() as cur:

        for source_row_number, row in enumerate(
            rows,
            start=1,
        ):

            source_code = str(
                row["Code"]
            )

            (
                source_table,
                source_line_code,
            ) = parse_bea_code(
                source_code
            )

            if (
                source_table
                != expected_table
            ):
                raise RuntimeError(
                    "Source-table mismatch in "
                    f"{source_path}: "
                    f"{source_table} != "
                    f"{expected_table}"
                )

            if (
                source_line_code
                != expected_line_code
            ):
                raise RuntimeError(
                    "Line-code mismatch in "
                    f"{source_path}: "
                    f"{source_line_code} != "
                    f"{expected_line_code}"
                )

            compensation_family = SERIES[
                (
                    source_table,
                    source_line_code,
                )
            ]

            calendar_year = int(
                row["TimePeriod"]
            )

            if (
                calendar_year
                not in EXPECTED_YEARS
            ):
                raise RuntimeError(
                    "Unexpected calendar year "
                    f"{calendar_year} "
                    f"in {source_path}"
                )

            source_geo_fips = str(
                row["GeoFips"]
            ).strip()

            source_geo_name = str(
                row["GeoName"]
            ).strip()

            if source_geo_fips == "53000":

                geography_level = "STATE"
                county_id = None
                state_rows += 1

            else:

                geography_level = "COUNTY"

                if (
                    not source_geo_fips.startswith(
                        "53"
                    )
                ):
                    raise RuntimeError(
                        "Non-Washington geography "
                        f"found: {source_geo_fips}"
                    )

                county_id = county_map.get(
                    source_geo_fips
                )

                if county_id is None:
                    raise RuntimeError(
                        "BEA county FIPS not found in "
                        "reference.county_registry: "
                        f"{source_geo_fips} "
                        f"{source_geo_name}"
                    )

                county_rows += 1

            source_data_value = str(
                row["DataValue"]
            )

            source_unit = str(
                row["CL_UNIT"]
            )

            source_unit_multiplier = int(
                row["UNIT_MULT"]
            )

            value_dollars = (
                normalize_value_dollars(
                    row
                )
            )

            cur.execute(
                """
                INSERT INTO bea.compensation_observation (
                    load_batch_id,

                    compensation_family,
                    accounting_measure,
                    reference_period_type,
                    calendar_year,
                    geographic_basis,
                    geography_level,

                    state_id,
                    county_id,

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

                    %s,
                    'COMPENSATION_OF_EMPLOYEES',
                    'CALENDAR_YEAR',
                    %s,
                    'PLACE_OF_WORK',
                    %s,

                    %s,
                    %s,

                    'Regional',
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

                    compensation_family,
                    calendar_year,
                    geography_level,

                    state_id,
                    county_id,

                    source_table,
                    source_line_code,
                    source_code,
                    source_geo_fips,
                    source_geo_name,

                    source_data_value,
                    source_unit,
                    source_unit_multiplier,
                    value_dollars,

                    str(
                        source_path.relative_to(
                            ROOT
                        )
                    ),
                    source_file_sha256,
                    source_row_number,
                ),
            )

            loaded += 1

    return (
        loaded,
        county_rows,
        state_rows,
    )


def validate_loaded_counts(
    *,
    total_rows: int,
    county_rows: int,
    state_rows: int,
) -> None:

    if total_rows != EXPECTED_TOTAL_ROWS:
        raise RuntimeError(
            "Unexpected total load count: "
            f"{total_rows}; expected "
            f"{EXPECTED_TOTAL_ROWS}."
        )

    if county_rows != EXPECTED_COUNTY_ROWS:
        raise RuntimeError(
            "Unexpected county load count: "
            f"{county_rows}; expected "
            f"{EXPECTED_COUNTY_ROWS}."
        )

    if state_rows != EXPECTED_STATE_ROWS:
        raise RuntimeError(
            "Unexpected state load count: "
            f"{state_rows}; expected "
            f"{EXPECTED_STATE_ROWS}."
        )


def mark_batch_completed(
    conn,
    load_batch_id: int,
    rows_loaded: int,
) -> None:

    with conn.cursor() as cur:

        cur.execute(
            """
            UPDATE bea.compensation_load_batch
            SET
                status = 'COMPLETED',
                rows_loaded = %s,
                completed_at = CURRENT_TIMESTAMP
            WHERE load_batch_id = %s
            """,
            (
                rows_loaded,
                load_batch_id,
            ),
        )


def main() -> None:

    manifest_path = find_latest_manifest()

    manifest = load_json(
        manifest_path
    )

    requests = validate_manifest(
        manifest_path,
        manifest,
    )

    print(
        f"Manifest: {manifest_path}"
    )

    print(
        f"Manifest SHA-256: "
        f"{sha256_file(manifest_path)}"
    )

    print()

    conn = get_connection()

    try:

        state_id, county_map = (
            get_reference_geography(
                conn
            )
        )

        load_batch_id = (
            create_load_batch(
                conn,
                manifest_path,
                manifest,
            )
        )

        print(
            f"Created BEA compensation "
            f"load_batch_id={load_batch_id}"
        )

        total_loaded = 0
        total_county_rows = 0
        total_state_rows = 0

        for item in requests:

            source_path = resolve_repo_path(
                item["file"]
            )

            source_sha256 = sha256_file(
                source_path
            )

            table_name = str(
                item["table_name"]
            )

            line_code = str(
                item["line_code"]
            )

            print()
            print(
                f"Loading {table_name}-"
                f"{line_code}"
            )

            print(
                f"  Source: {source_path}"
            )

            (
                loaded,
                county_rows,
                state_rows,
            ) = insert_source_file(
                conn,
                load_batch_id=load_batch_id,
                source_path=source_path,
                source_file_sha256=source_sha256,
                expected_table=table_name,
                expected_line_code=line_code,
                state_id=state_id,
                county_map=county_map,
            )

            total_loaded += loaded
            total_county_rows += (
                county_rows
            )
            total_state_rows += (
                state_rows
            )

            print(
                f"  Loaded: {loaded}"
            )

            print(
                f"  County observations: "
                f"{county_rows}"
            )

            print(
                f"  State observations: "
                f"{state_rows}"
            )

        validate_loaded_counts(
            total_rows=total_loaded,
            county_rows=total_county_rows,
            state_rows=total_state_rows,
        )

        mark_batch_completed(
            conn,
            load_batch_id,
            total_loaded,
        )

        conn.commit()

        print()
        print("=" * 72)
        print(
            "BEA FEDERAL COMPENSATION "
            "LOAD COMPLETE"
        )
        print("=" * 72)

        print(
            f"Load batch ID: "
            f"{load_batch_id}"
        )

        print(
            f"Rows loaded: "
            f"{total_loaded}"
        )

        print(
            f"County observations: "
            f"{total_county_rows}"
        )

        print(
            f"State observations: "
            f"{total_state_rows}"
        )

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


if __name__ == "__main__":
    main()