"""
ETL-004A.3H — Link award transactions to canonical places.

Populates procurement.place_of_performance by joining normalized
award transactions back to immutable raw USAspending observations and
resolving each observation to procurement.place.

Usage:
    python -m etl.loaders.link_procurement_places

Optional explicit batch:
    python -m etl.loaders.link_procurement_places --load-batch-id 2

Prerequisite:
    Migration 113 must have been applied.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from etl.common.db import get_connection


COMPLETED_STATUSES = {"COMPLETED", "COMPLETED_WITH_REJECTIONS"}


@dataclass(frozen=True)
class LinkSummary:
    transactions_examined: int
    inserted: int
    updated: int
    unchanged: int
    resolved_places: int
    unresolved_places: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Link procurement transactions to canonical places."
    )
    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=None,
        help=(
            "Load batch to link. Defaults to the latest completed batch "
            "containing normalized award transactions."
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
                    COUNT(at.award_transaction_id)
                FROM procurement.load_batch AS lb
                LEFT JOIN procurement.award_transaction AS at
                    ON at.load_batch_id = lb.load_batch_id
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
                    COUNT(at.award_transaction_id)
                FROM procurement.load_batch AS lb
                JOIN procurement.award_transaction AS at
                    ON at.load_batch_id = lb.load_batch_id
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
                "No completed procurement batch containing normalized "
                "transactions was found."
            )
        raise ValueError(f"Load batch {requested_batch_id} does not exist.")

    load_batch_id, source_file, load_status, transaction_count = row

    if load_status not in COMPLETED_STATUSES:
        raise ValueError(
            f"Load batch {load_batch_id} has status {load_status!r}; "
            "a completed batch is required."
        )

    if int(transaction_count) == 0:
        raise ValueError(
            f"Load batch {load_batch_id} contains no normalized transactions."
        )

    return int(load_batch_id), str(source_file), int(transaction_count)


def verify_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'procurement'
                  AND table_name = 'place_of_performance'
                  AND column_name = 'place_id'
            );
            """
        )
        if not bool(cur.fetchone()[0]):
            raise ValueError(
                "procurement.place_of_performance.place_id does not exist. "
                "Apply Migration 113 first."
            )


def create_link_candidate_table(conn, load_batch_id: int) -> int:
    """
    Create one deterministic place-of-performance candidate per transaction.

    Normalization mirrors ETL-112 so that the canonical identity resolves
    exactly against procurement.place.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TEMP TABLE tmp_procurement_place_link
            ON COMMIT DROP
            AS
            WITH extracted AS (
                SELECT
                    at.award_transaction_id,

                    UPPER(NULLIF(BTRIM(
                        raw.raw_record ->>
                        'primary_place_of_performance_country_code'
                    ), '')) AS country_code,

                    UPPER(NULLIF(BTRIM(
                        raw.raw_record ->>
                        'primary_place_of_performance_state_code'
                    ), '')) AS state_code,

                    NULLIF(BTRIM(
                        raw.raw_record ->>
                        'prime_award_transaction_place_of_performance_state_fips_code'
                    ), '') AS state_fips,

                    NULLIF(BTRIM(
                        raw.raw_record ->>
                        'prime_award_transaction_place_of_performance_county_fips_code'
                    ), '') AS county_fips,

                    UPPER(NULLIF(
                        REGEXP_REPLACE(
                            BTRIM(
                                raw.raw_record ->>
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
                                raw.raw_record ->>
                                'primary_place_of_performance_zip_4'
                            ),
                            '[^0-9]',
                            '',
                            'g'
                        ),
                        ''
                    ) AS zip4,

                    UPPER(NULLIF(BTRIM(
                        raw.raw_record ->>
                        'prime_award_transaction_place_of_performance_cd_current'
                    ), '')) AS congressional_district_current

                FROM procurement.award_transaction AS at
                JOIN procurement.raw_award_transaction AS raw
                  ON raw.load_batch_id = at.load_batch_id
                 AND raw.source_row_number = at.source_row_number
                WHERE at.load_batch_id = %s
            ),
            cleaned AS (
                SELECT
                    award_transaction_id,

                    CASE
                        WHEN country_code IN (
                            'NULL', 'NONE', 'N/A', 'NA', 'NAN'
                        ) THEN NULL
                        ELSE country_code
                    END AS country_code,

                    CASE
                        WHEN state_code IN (
                            'NULL', 'NONE', 'N/A', 'NA', 'NAN'
                        ) THEN NULL
                        ELSE state_code
                    END AS state_code,

                    CASE
                        WHEN state_fips ~ '^[0-9]{2}$'
                        THEN state_fips
                        ELSE NULL
                    END AS state_fips,

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
                    END AS congressional_district_current

                FROM extracted
            )
            SELECT
                c.award_transaction_id,
                p.place_id,
                sr.state_id,
                cr.county_id,
                c.country_code,
                c.state_code,
                c.county_fips AS county_code,
                c.city_name,
                c.congressional_district_current
                    AS congressional_district,
                c.zip4 AS zip_code,
                CASE
                    WHEN p.place_id IS NOT NULL THEN 'OBSERVED'
                    ELSE 'UNRESOLVED'
                END AS location_scope
            FROM cleaned AS c
            LEFT JOIN procurement.place AS p
              ON p.country_code IS NOT DISTINCT FROM c.country_code
             AND p.state_fips IS NOT DISTINCT FROM c.state_fips
             AND p.county_fips IS NOT DISTINCT FROM c.county_fips
             AND p.city_name IS NOT DISTINCT FROM c.city_name
             AND p.zip4 IS NOT DISTINCT FROM c.zip4
            LEFT JOIN reference.state_registry AS sr
              ON sr.state_fips = c.state_fips
            LEFT JOIN reference.county_registry AS cr
              ON cr.full_fips = c.county_fips;
            """,
            (load_batch_id,),
        )

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link;
            """
        )
        return int(cur.fetchone()[0])


def count_changes(conn) -> tuple[int, int, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link AS c
            LEFT JOIN procurement.place_of_performance AS pop
              ON pop.award_transaction_id = c.award_transaction_id
            WHERE pop.place_of_performance_id IS NULL;
            """
        )
        inserted = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link AS c
            JOIN procurement.place_of_performance AS pop
              ON pop.award_transaction_id = c.award_transaction_id
            WHERE
                pop.place_id IS DISTINCT FROM c.place_id
                OR pop.state_id IS DISTINCT FROM c.state_id
                OR pop.county_id IS DISTINCT FROM c.county_id
                OR pop.country_code IS DISTINCT FROM c.country_code
                OR pop.state_code IS DISTINCT FROM c.state_code
                OR pop.county_code IS DISTINCT FROM c.county_code
                OR pop.city_name IS DISTINCT FROM c.city_name
                OR pop.congressional_district
                    IS DISTINCT FROM c.congressional_district
                OR pop.zip_code IS DISTINCT FROM c.zip_code
                OR pop.location_scope IS DISTINCT FROM c.location_scope;
            """
        )
        updated = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link AS c
            JOIN procurement.place_of_performance AS pop
              ON pop.award_transaction_id = c.award_transaction_id
            WHERE
                pop.place_id IS NOT DISTINCT FROM c.place_id
                AND pop.state_id IS NOT DISTINCT FROM c.state_id
                AND pop.county_id IS NOT DISTINCT FROM c.county_id
                AND pop.country_code IS NOT DISTINCT FROM c.country_code
                AND pop.state_code IS NOT DISTINCT FROM c.state_code
                AND pop.county_code IS NOT DISTINCT FROM c.county_code
                AND pop.city_name IS NOT DISTINCT FROM c.city_name
                AND pop.congressional_district
                    IS NOT DISTINCT FROM c.congressional_district
                AND pop.zip_code IS NOT DISTINCT FROM c.zip_code
                AND pop.location_scope IS NOT DISTINCT FROM c.location_scope;
            """
        )
        unchanged = int(cur.fetchone()[0])

    return inserted, updated, unchanged


def apply_links(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO procurement.place_of_performance (
                award_transaction_id,
                place_id,
                state_id,
                county_id,
                country_code,
                state_code,
                county_code,
                city_name,
                congressional_district,
                zip_code,
                location_scope
            )
            SELECT
                award_transaction_id,
                place_id,
                state_id,
                county_id,
                country_code,
                state_code,
                county_code,
                city_name,
                congressional_district,
                zip_code,
                location_scope
            FROM tmp_procurement_place_link
            ON CONFLICT (award_transaction_id)
            DO UPDATE SET
                place_id = EXCLUDED.place_id,
                state_id = EXCLUDED.state_id,
                county_id = EXCLUDED.county_id,
                country_code = EXCLUDED.country_code,
                state_code = EXCLUDED.state_code,
                county_code = EXCLUDED.county_code,
                city_name = EXCLUDED.city_name,
                congressional_district =
                    EXCLUDED.congressional_district,
                zip_code = EXCLUDED.zip_code,
                location_scope = EXCLUDED.location_scope
            WHERE
                procurement.place_of_performance.place_id
                    IS DISTINCT FROM EXCLUDED.place_id
                OR procurement.place_of_performance.state_id
                    IS DISTINCT FROM EXCLUDED.state_id
                OR procurement.place_of_performance.county_id
                    IS DISTINCT FROM EXCLUDED.county_id
                OR procurement.place_of_performance.country_code
                    IS DISTINCT FROM EXCLUDED.country_code
                OR procurement.place_of_performance.state_code
                    IS DISTINCT FROM EXCLUDED.state_code
                OR procurement.place_of_performance.county_code
                    IS DISTINCT FROM EXCLUDED.county_code
                OR procurement.place_of_performance.city_name
                    IS DISTINCT FROM EXCLUDED.city_name
                OR procurement.place_of_performance.congressional_district
                    IS DISTINCT FROM EXCLUDED.congressional_district
                OR procurement.place_of_performance.zip_code
                    IS DISTINCT FROM EXCLUDED.zip_code
                OR procurement.place_of_performance.location_scope
                    IS DISTINCT FROM EXCLUDED.location_scope;
            """
        )


def validate_links(
    conn,
    expected_transactions: int,
) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link
            WHERE place_id IS NOT NULL;
            """
        )
        resolved = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link
            WHERE place_id IS NULL;
            """
        )
        unresolved = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link AS c
            LEFT JOIN procurement.place_of_performance AS pop
              ON pop.award_transaction_id = c.award_transaction_id
            WHERE pop.place_of_performance_id IS NULL;
            """
        )
        missing_relationships = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT award_transaction_id
                FROM procurement.place_of_performance
                GROUP BY award_transaction_id
                HAVING COUNT(*) > 1
            ) AS duplicates;
            """
        )
        duplicate_transactions = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM procurement.place_of_performance AS pop
            LEFT JOIN procurement.place AS p
              ON p.place_id = pop.place_id
            WHERE pop.place_id IS NOT NULL
              AND p.place_id IS NULL;
            """
        )
        orphan_places = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link;
            """
        )
        candidate_count = int(cur.fetchone()[0])

    if candidate_count != expected_transactions:
        raise ValueError(
            "Transaction/raw join mismatch: "
            f"expected {expected_transactions}, produced {candidate_count}."
        )

    if missing_relationships:
        raise ValueError(
            f"Transactions missing place relationships: "
            f"{missing_relationships}"
        )

    if duplicate_transactions:
        raise ValueError(
            f"Duplicate transaction relationships found: "
            f"{duplicate_transactions}"
        )

    if orphan_places:
        raise ValueError(
            f"Orphaned canonical place references found: {orphan_places}"
        )

    if unresolved:
        raise ValueError(
            f"Unresolved canonical places found: {unresolved}"
        )

    return resolved, unresolved


def print_summary(
    summary: LinkSummary,
    elapsed_seconds: float,
) -> None:
    print()
    print("=" * 68)
    print("ETL-004A.3H SUMMARY")
    print("=" * 68)
    print(f"Transactions examined . {summary.transactions_examined:,}")
    print(f"Relationships inserted . {summary.inserted:,}")
    print(f"Relationships updated . {summary.updated:,}")
    print(f"Relationships unchanged . {summary.unchanged:,}")
    print(f"Canonical places resolved . {summary.resolved_places:,}")
    print(f"Canonical places unresolved . {summary.unresolved_places:,}")
    print("Duplicate transaction relationships . 0")
    print("Orphaned canonical place references . 0")
    print("Validation . PASS")
    print(f"Elapsed time . {elapsed_seconds:.2f} sec")
    print("=" * 68)


def main() -> None:
    args = parse_arguments()
    started = time.perf_counter()

    print("=" * 68)
    print("ETL-004A.3H — Link Procurement Places")
    print("=" * 68)

    conn = get_connection()

    try:
        verify_schema(conn)

        load_batch_id, source_file, transaction_count = get_target_batch(
            conn,
            args.load_batch_id,
        )

        print(f"Target load batch: {load_batch_id}")
        print(f"Source file: {source_file}")
        print(f"Normalized transactions: {transaction_count:,}")

        candidate_count = create_link_candidate_table(
            conn,
            load_batch_id,
        )
        print(f"Place-link candidates: {candidate_count:,}")

        inserted, updated, unchanged = count_changes(conn)
        apply_links(conn)
        resolved, unresolved = validate_links(
            conn,
            transaction_count,
        )
        conn.commit()

        print_summary(
            LinkSummary(
                transactions_examined=transaction_count,
                inserted=inserted,
                updated=updated,
                unchanged=unchanged,
                resolved_places=resolved,
                unresolved_places=unresolved,
            ),
            time.perf_counter() - started,
        )

        print()
        print("ETL-004A.3H completed successfully.")

    except Exception as exc:
        conn.rollback()
        print()
        print("ETL-004A.3H failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()