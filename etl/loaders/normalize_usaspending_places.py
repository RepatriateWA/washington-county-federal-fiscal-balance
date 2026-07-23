"""
ETL-004A.3G — Normalize USAspending places of performance.

Builds the canonical procurement.place dimension from immutable
USAspending award transaction observations stored in
procurement.raw_award_transaction.raw_record.

Canonical identity:
    country_code
    state_fips
    county_fips
    city_name
    zip4

Congressional districts and geographic names are descriptive attributes,
not components of the stable place identity.

Usage:
    python -m etl.loaders.normalize_usaspending_places

Optional explicit batch:
    python -m etl.loaders.normalize_usaspending_places \
        --load-batch-id 2
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from etl.common.db import get_connection


COMPLETED_STATUSES = {"COMPLETED", "COMPLETED_WITH_REJECTIONS"}


@dataclass(frozen=True)
class LoadSummary:
    raw_observations: int
    canonical_candidates: int
    inserted: int
    updated: int
    unchanged: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize USAspending places of performance."
    )
    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=None,
        help=(
            "Raw procurement load batch to normalize. Defaults to the latest "
            "completed batch containing raw observations."
        ),
    )
    return parser.parse_args()


def get_target_batch(
    conn,
    requested_batch_id: int | None,
) -> tuple[int, str, int]:
    with conn.cursor() as cur:
        if requested_batch_id is not None:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id)
                FROM procurement.load_batch AS lb
                LEFT JOIN procurement.raw_award_transaction AS raw
                    ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_batch_id = %s
                GROUP BY
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status;
                """,
                (requested_batch_id,),
            )
        else:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id)
                FROM procurement.load_batch AS lb
                JOIN procurement.raw_award_transaction AS raw
                    ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_status IN (
                    'COMPLETED',
                    'COMPLETED_WITH_REJECTIONS'
                )
                GROUP BY
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status
                ORDER BY lb.load_batch_id DESC
                LIMIT 1;
                """
            )

        row = cur.fetchone()

    if row is None:
        if requested_batch_id is None:
            raise ValueError(
                "No completed procurement batch containing raw rows was found."
            )
        raise ValueError(f"Load batch {requested_batch_id} does not exist.")

    load_batch_id, source_file, load_status, raw_count = row

    if load_status not in COMPLETED_STATUSES:
        raise ValueError(
            f"Load batch {load_batch_id} has status {load_status!r}; "
            "a completed batch is required."
        )

    if int(raw_count) == 0:
        raise ValueError(f"Load batch {load_batch_id} contains no raw rows.")

    return int(load_batch_id), str(source_file), int(raw_count)


def create_candidate_table(conn, load_batch_id: int) -> int:
    """
    Create one deterministic candidate row per canonical place identity.

    Source placeholders such as empty string, NULL, N/A, and NAN become SQL
    NULL. Codes and names are uppercased, whitespace is collapsed, and only
    values satisfying the Migration 111 formats are retained.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TEMP TABLE tmp_procurement_place_candidate
            ON COMMIT DROP
            AS
            WITH extracted AS (
                SELECT
                    raw_award_transaction_id,

                    UPPER(NULLIF(BTRIM(
                        raw_record ->>
                        'primary_place_of_performance_country_code'
                    ), '')) AS country_code,

                    UPPER(NULLIF(BTRIM(
                        raw_record ->>
                        'primary_place_of_performance_country_name'
                    ), '')) AS country_name,

                    UPPER(NULLIF(BTRIM(
                        raw_record ->>
                        'primary_place_of_performance_state_code'
                    ), '')) AS state_code,

                    UPPER(NULLIF(BTRIM(
                        raw_record ->>
                        'primary_place_of_performance_state_name'
                    ), '')) AS state_name,

                    NULLIF(BTRIM(
                        raw_record ->>
                        'prime_award_transaction_place_of_performance_state_fips_code'
                    ), '') AS state_fips,

                    UPPER(NULLIF(BTRIM(
                        raw_record ->>
                        'primary_place_of_performance_county_name'
                    ), '')) AS county_name,

                    NULLIF(BTRIM(
                        raw_record ->>
                        'prime_award_transaction_place_of_performance_county_fips_code'
                    ), '') AS county_fips,

                    UPPER(NULLIF(
                        REGEXP_REPLACE(
                            BTRIM(
                                raw_record ->>
                                'primary_place_of_performance_city_name'
                            ),
                            '\\s+',
                            ' ',
                            'g'
                        ),
                        ''
                    )) AS city_name,

                    NULLIF(
                        REGEXP_REPLACE(
                            BTRIM(
                                raw_record ->>
                                'primary_place_of_performance_zip_4'
                            ),
                            '[^0-9]',
                            '',
                            'g'
                        ),
                        ''
                    ) AS zip4,

                    UPPER(NULLIF(BTRIM(
                        raw_record ->>
                        'prime_award_transaction_place_of_performance_cd_current'
                    ), '')) AS congressional_district_current,

                    UPPER(NULLIF(BTRIM(
                        raw_record ->>
                        'prime_award_transaction_place_of_performance_cd_original'
                    ), '')) AS congressional_district_original

                FROM procurement.raw_award_transaction
                WHERE load_batch_id = %s
            ),
            cleaned AS (
                SELECT
                    CASE
                        WHEN country_code IN (
                            'NULL', 'NONE', 'N/A', 'NA', 'NAN'
                        ) THEN NULL
                        ELSE country_code
                    END AS country_code,

                    CASE
                        WHEN country_name IN (
                            'NULL', 'NONE', 'N/A', 'NA', 'NAN'
                        ) THEN NULL
                        ELSE country_name
                    END AS country_name,

                    CASE
                        WHEN state_code IN (
                            'NULL', 'NONE', 'N/A', 'NA', 'NAN'
                        ) THEN NULL
                        ELSE state_code
                    END AS state_code,

                    CASE
                        WHEN state_name IN (
                            'NULL', 'NONE', 'N/A', 'NA', 'NAN'
                        ) THEN NULL
                        ELSE state_name
                    END AS state_name,

                    CASE
                        WHEN state_fips ~ '^[0-9]{2}$'
                        THEN state_fips
                        ELSE NULL
                    END AS state_fips,

                    CASE
                        WHEN county_name IN (
                            'NULL', 'NONE', 'N/A', 'NA', 'NAN'
                        ) THEN NULL
                        ELSE county_name
                    END AS county_name,

                    CASE
                        WHEN county_fips ~ '^[0-9]{5}$'
                        THEN county_fips
                        ELSE NULL
                    END AS county_fips,

                    CASE
                        WHEN city_name IN (
                            'NULL', 'NONE', 'N/A', 'NA', 'NAN'
                        ) THEN NULL
                        ELSE city_name
                    END AS city_name,

                    CASE
                        WHEN zip4 ~ '^[0-9]{5}([0-9]{4})?$'
                        THEN zip4
                        ELSE NULL
                    END AS zip4,

                    CASE
                        WHEN congressional_district_current
                             ~ '^[A-Z]{2}-(AL|[0-9]{1,2})$'
                        THEN congressional_district_current
                        ELSE NULL
                    END AS congressional_district_current,

                    CASE
                        WHEN congressional_district_original
                             ~ '^[A-Z]{2}-(AL|[0-9]{1,2})$'
                        THEN congressional_district_original
                        ELSE NULL
                    END AS congressional_district_original

                FROM extracted
            )
            SELECT
                country_code,
                MAX(country_name) AS country_name,
                MAX(state_code) AS state_code,
                MAX(state_name) AS state_name,
                state_fips,
                MAX(county_name) AS county_name,
                county_fips,
                city_name,
                zip4,
                MAX(congressional_district_current)
                    AS congressional_district_current,
                MAX(congressional_district_original)
                    AS congressional_district_original
            FROM cleaned
            WHERE
                country_code IS NOT NULL
                OR state_fips IS NOT NULL
                OR county_fips IS NOT NULL
                OR city_name IS NOT NULL
                OR zip4 IS NOT NULL
            GROUP BY
                country_code,
                state_fips,
                county_fips,
                city_name,
                zip4;
            """,
            (load_batch_id,),
        )

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_candidate;
            """
        )
        return int(cur.fetchone()[0])


def count_changes(conn) -> tuple[int, int, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_candidate AS c
            LEFT JOIN procurement.place AS p
              ON p.country_code IS NOT DISTINCT FROM c.country_code
             AND p.state_fips IS NOT DISTINCT FROM c.state_fips
             AND p.county_fips IS NOT DISTINCT FROM c.county_fips
             AND p.city_name IS NOT DISTINCT FROM c.city_name
             AND p.zip4 IS NOT DISTINCT FROM c.zip4
            WHERE p.place_id IS NULL;
            """
        )
        inserted = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_candidate AS c
            JOIN procurement.place AS p
              ON p.country_code IS NOT DISTINCT FROM c.country_code
             AND p.state_fips IS NOT DISTINCT FROM c.state_fips
             AND p.county_fips IS NOT DISTINCT FROM c.county_fips
             AND p.city_name IS NOT DISTINCT FROM c.city_name
             AND p.zip4 IS NOT DISTINCT FROM c.zip4
            WHERE
                p.country_name IS DISTINCT FROM c.country_name
                OR p.state_code IS DISTINCT FROM c.state_code
                OR p.state_name IS DISTINCT FROM c.state_name
                OR p.county_name IS DISTINCT FROM c.county_name
                OR p.congressional_district_current
                    IS DISTINCT FROM c.congressional_district_current
                OR p.congressional_district_original
                    IS DISTINCT FROM c.congressional_district_original;
            """
        )
        updated = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_candidate AS c
            JOIN procurement.place AS p
              ON p.country_code IS NOT DISTINCT FROM c.country_code
             AND p.state_fips IS NOT DISTINCT FROM c.state_fips
             AND p.county_fips IS NOT DISTINCT FROM c.county_fips
             AND p.city_name IS NOT DISTINCT FROM c.city_name
             AND p.zip4 IS NOT DISTINCT FROM c.zip4
            WHERE
                p.country_name IS NOT DISTINCT FROM c.country_name
                AND p.state_code IS NOT DISTINCT FROM c.state_code
                AND p.state_name IS NOT DISTINCT FROM c.state_name
                AND p.county_name IS NOT DISTINCT FROM c.county_name
                AND p.congressional_district_current
                    IS NOT DISTINCT FROM c.congressional_district_current
                AND p.congressional_district_original
                    IS NOT DISTINCT FROM c.congressional_district_original;
            """
        )
        unchanged = int(cur.fetchone()[0])

    return inserted, updated, unchanged


def apply_candidates(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO procurement.place (
                country_code,
                country_name,
                state_code,
                state_name,
                state_fips,
                county_name,
                county_fips,
                city_name,
                zip4,
                congressional_district_current,
                congressional_district_original
            )
            SELECT
                country_code,
                country_name,
                state_code,
                state_name,
                state_fips,
                county_name,
                county_fips,
                city_name,
                zip4,
                congressional_district_current,
                congressional_district_original
            FROM tmp_procurement_place_candidate
            ON CONFLICT ON CONSTRAINT uq_procurement_place_identity
            DO UPDATE SET
                country_name = EXCLUDED.country_name,
                state_code = EXCLUDED.state_code,
                state_name = EXCLUDED.state_name,
                county_name = EXCLUDED.county_name,
                congressional_district_current =
                    EXCLUDED.congressional_district_current,
                congressional_district_original =
                    EXCLUDED.congressional_district_original,
                updated_at = CURRENT_TIMESTAMP
            WHERE
                procurement.place.country_name
                    IS DISTINCT FROM EXCLUDED.country_name
                OR procurement.place.state_code
                    IS DISTINCT FROM EXCLUDED.state_code
                OR procurement.place.state_name
                    IS DISTINCT FROM EXCLUDED.state_name
                OR procurement.place.county_name
                    IS DISTINCT FROM EXCLUDED.county_name
                OR procurement.place.congressional_district_current
                    IS DISTINCT FROM
                    EXCLUDED.congressional_district_current
                OR procurement.place.congressional_district_original
                    IS DISTINCT FROM
                    EXCLUDED.congressional_district_original;
            """
        )


def validate_dimension(conn, expected_candidates: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    country_code,
                    state_fips,
                    county_fips,
                    city_name,
                    zip4
                FROM procurement.place
                GROUP BY
                    country_code,
                    state_fips,
                    county_fips,
                    city_name,
                    zip4
                HAVING COUNT(*) > 1
            ) AS duplicates;
            """
        )
        duplicate_identities = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_candidate AS c
            LEFT JOIN procurement.place AS p
              ON p.country_code IS NOT DISTINCT FROM c.country_code
             AND p.state_fips IS NOT DISTINCT FROM c.state_fips
             AND p.county_fips IS NOT DISTINCT FROM c.county_fips
             AND p.city_name IS NOT DISTINCT FROM c.city_name
             AND p.zip4 IS NOT DISTINCT FROM c.zip4
            WHERE p.place_id IS NULL;
            """
        )
        unresolved_candidates = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM procurement.place
            WHERE county_fips IS NOT NULL
              AND state_fips IS NOT NULL
              AND LEFT(county_fips, 2) <> state_fips;
            """
        )
        inconsistent_fips = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM procurement.place
            WHERE country_code IS NULL
              AND state_fips IS NULL
              AND county_fips IS NULL
              AND city_name IS NULL
              AND zip4 IS NULL;
            """
        )
        empty_places = int(cur.fetchone()[0])

    if duplicate_identities:
        raise ValueError(
            f"Duplicate canonical place identities found: "
            f"{duplicate_identities}"
        )

    if unresolved_candidates:
        raise ValueError(
            f"Canonical candidates not resolved after upsert: "
            f"{unresolved_candidates}"
        )

    if inconsistent_fips:
        raise ValueError(
            f"Places with inconsistent state/county FIPS: "
            f"{inconsistent_fips}"
        )

    if empty_places:
        raise ValueError(
            f"Completely empty canonical places found: {empty_places}"
        )

    if expected_candidates <= 0:
        raise ValueError("No canonical place candidates were produced.")


def print_summary(
    summary: LoadSummary,
    elapsed_seconds: float,
) -> None:
    print()
    print("=" * 68)
    print("ETL-004A.3G SUMMARY")
    print("=" * 68)
    print(f"Raw observations examined . {summary.raw_observations:,}")
    print(f"Canonical places discovered . {summary.canonical_candidates:,}")
    print(f"Places inserted . {summary.inserted:,}")
    print(f"Places updated . {summary.updated:,}")
    print(f"Places unchanged . {summary.unchanged:,}")
    print("Duplicate canonical identities . 0")
    print("Unresolved place candidates . 0")
    print("Inconsistent state/county FIPS . 0")
    print("Completely empty places . 0")
    print("Validation . PASS")
    print(f"Elapsed time . {elapsed_seconds:.2f} sec")
    print("=" * 68)


def main() -> None:
    args = parse_arguments()
    started = time.perf_counter()

    print("=" * 68)
    print("ETL-004A.3G — Normalize USAspending Places")
    print("=" * 68)

    conn = get_connection()

    try:
        load_batch_id, source_file, raw_count = get_target_batch(
            conn,
            args.load_batch_id,
        )
        print(f"Target raw load batch: {load_batch_id}")
        print(f"Source file: {source_file}")
        print(f"Raw observations: {raw_count:,}")

        candidate_count = create_candidate_table(
            conn,
            load_batch_id,
        )
        print(f"Canonical place candidates: {candidate_count:,}")

        inserted, updated, unchanged = count_changes(conn)
        apply_candidates(conn)
        validate_dimension(conn, candidate_count)
        conn.commit()

        print_summary(
            LoadSummary(
                raw_observations=raw_count,
                canonical_candidates=candidate_count,
                inserted=inserted,
                updated=updated,
                unchanged=unchanged,
            ),
            time.perf_counter() - started,
        )

        print()
        print("ETL-004A.3G completed successfully.")

    except Exception as exc:
        conn.rollback()
        print()
        print("ETL-004A.3G failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()