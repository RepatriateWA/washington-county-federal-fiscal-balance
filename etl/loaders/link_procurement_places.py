"""
ETL-004A.3H - Link normalized procurement transactions to canonical places.

This loader:

1. Selects a completed procurement load batch.
2. Joins normalized award transactions to their immutable raw observations.
3. Normalizes transaction-level place-of-performance fields.
4. Constructs the same deterministic place identity key used by
   procurement.place.
5. Resolves each transaction to procurement.place through the indexed
   place_identity_key.
6. Inserts or updates one procurement.place_of_performance relationship
   per normalized award transaction.
7. Reconciles and validates the resulting relationships.

Usage:
    python -m etl.loaders.link_procurement_places

Explicit batch:
    python -m etl.loaders.link_procurement_places --load-batch-id 5
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from etl.common.db import get_connection


COMPLETED_STATUSES = {
    "COMPLETED",
    "COMPLETED_WITH_REJECTIONS",
}


@dataclass(frozen=True)
class LinkSummary:
    """Summary of one place-linking run."""

    transactions_examined: int
    inserted: int
    updated: int
    unchanged: int
    resolved_places: int
    unresolved_places: int


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Link normalized USAspending procurement transactions "
            "to canonical places."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=None,
        help=(
            "Normalized procurement load batch to process. "
            "Defaults to the latest completed batch containing "
            "normalized transactions."
        ),
    )

    return parser.parse_args()


def get_target_batch(
    conn,
    requested_batch_id: int | None,
) -> tuple[int, str, int]:
    """Return the target batch ID, source file, and transaction count."""

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

        raise ValueError(
            f"Load batch {requested_batch_id} does not exist."
        )

    (
        load_batch_id,
        source_file,
        load_status,
        transaction_count,
    ) = row

    if load_status not in COMPLETED_STATUSES:
        raise ValueError(
            f"Load batch {load_batch_id} has status "
            f"{load_status!r}; a completed batch is required."
        )

    if int(transaction_count) == 0:
        raise ValueError(
            f"Load batch {load_batch_id} contains no "
            "normalized transactions."
        )

    return (
        int(load_batch_id),
        str(source_file),
        int(transaction_count),
    )


def verify_schema(conn) -> None:
    """Verify the schema additions required by the linker."""

    required_columns = (
        (
            "place_of_performance",
            "place_id",
            "Apply Migration 113 first.",
        ),
        (
            "place",
            "place_identity_key",
            "Apply Migration 118 first.",
        ),
    )

    with conn.cursor() as cur:
        for table_name, column_name, instruction in required_columns:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'procurement'
                      AND table_name = %s
                      AND column_name = %s
                );
                """,
                (
                    table_name,
                    column_name,
                ),
            )

            if not bool(cur.fetchone()[0]):
                raise ValueError(
                    f"procurement.{table_name}.{column_name} "
                    f"does not exist. {instruction}"
                )


def create_link_candidate_table(
    conn,
    load_batch_id: int,
) -> int:
    """
    Create one deterministic place candidate per transaction.

    The normalization rules mirror the canonical-place loader. The
    length-prefixed identity key must remain identical to the generated
    procurement.place.place_identity_key expression.
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

                    UPPER(
                        NULLIF(
                            BTRIM(
                                raw.raw_record ->>
                                'primary_place_of_performance_country_code'
                            ),
                            ''
                        )
                    ) AS country_code,

                    UPPER(
                        NULLIF(
                            BTRIM(
                                raw.raw_record ->>
                                'primary_place_of_performance_state_code'
                            ),
                            ''
                        )
                    ) AS state_code,

                    NULLIF(
                        BTRIM(
                            raw.raw_record ->>
                            'prime_award_transaction_place_of_performance_state_fips_code'
                        ),
                        ''
                    ) AS state_fips,

                    NULLIF(
                        BTRIM(
                            raw.raw_record ->>
                            'prime_award_transaction_place_of_performance_county_fips_code'
                        ),
                        ''
                    ) AS county_fips,

                    UPPER(
                        NULLIF(
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
                        )
                    ) AS city_name,

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

                    UPPER(
                        NULLIF(
                            BTRIM(
                                raw.raw_record ->>
                                'prime_award_transaction_place_of_performance_cd_current'
                            ),
                            ''
                        )
                    ) AS congressional_district_current

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
                            'NULL',
                            'NONE',
                            'N/A',
                            'NA',
                            'NAN'
                        )
                        THEN NULL
                        ELSE country_code
                    END AS country_code,

                    CASE
                        WHEN state_code IN (
                            'NULL',
                            'NONE',
                            'N/A',
                            'NA',
                            'NAN'
                        )
                        THEN NULL
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
                            'NULL',
                            'NONE',
                            'N/A',
                            'NA',
                            'NAN'
                        )
                        THEN NULL
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
            ),
            keyed AS (
                SELECT
                    award_transaction_id,
                    country_code,
                    state_code,
                    state_fips,
                    county_fips,
                    city_name,
                    zip4,
                    congressional_district_current,

                    COALESCE(
                        LENGTH(country_code)::TEXT
                            || ':' || country_code,
                        '-1:'
                    )
                    || '|'
                    || COALESCE(
                        LENGTH(state_fips)::TEXT
                            || ':' || state_fips,
                        '-1:'
                    )
                    || '|'
                    || COALESCE(
                        LENGTH(county_fips)::TEXT
                            || ':' || county_fips,
                        '-1:'
                    )
                    || '|'
                    || COALESCE(
                        LENGTH(city_name)::TEXT
                            || ':' || city_name,
                        '-1:'
                    )
                    || '|'
                    || COALESCE(
                        LENGTH(zip4)::TEXT
                            || ':' || zip4,
                        '-1:'
                    ) AS place_identity_key

                FROM cleaned
            )
            SELECT
                k.award_transaction_id,
                p.place_id,
                sr.state_id,
                cr.county_id,
                k.country_code,
                k.state_code,
                k.county_fips AS county_code,
                k.city_name,
                k.congressional_district_current
                    AS congressional_district,
                k.zip4 AS zip_code,
                CASE
                    WHEN p.place_id IS NOT NULL
                    THEN 'OBSERVED'
                    ELSE 'UNRESOLVED'
                END AS location_scope
            FROM keyed AS k
            LEFT JOIN procurement.place AS p
              ON p.place_identity_key = k.place_identity_key
            LEFT JOIN reference.state_registry AS sr
              ON sr.state_fips = k.state_fips
            LEFT JOIN reference.county_registry AS cr
              ON cr.full_fips = k.county_fips;
            """,
            (load_batch_id,),
        )

        cur.execute(
            """
            CREATE UNIQUE INDEX
                idx_tmp_procurement_place_link_transaction
            ON tmp_procurement_place_link (
                award_transaction_id
            );
            """
        )

        cur.execute(
            """
            ANALYZE tmp_procurement_place_link;
            """
        )

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link;
            """
        )

        return int(cur.fetchone()[0])


def count_changes(conn) -> tuple[int, int, int]:
    """Count rows that will be inserted, updated, or unchanged."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link AS candidate
            LEFT JOIN procurement.place_of_performance AS existing
              ON existing.award_transaction_id =
                 candidate.award_transaction_id
            WHERE existing.place_of_performance_id IS NULL;
            """
        )
        inserted = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link AS candidate
            JOIN procurement.place_of_performance AS existing
              ON existing.award_transaction_id =
                 candidate.award_transaction_id
            WHERE
                existing.place_id
                    IS DISTINCT FROM candidate.place_id
                OR existing.state_id
                    IS DISTINCT FROM candidate.state_id
                OR existing.county_id
                    IS DISTINCT FROM candidate.county_id
                OR existing.country_code
                    IS DISTINCT FROM candidate.country_code
                OR existing.state_code
                    IS DISTINCT FROM candidate.state_code
                OR existing.county_code
                    IS DISTINCT FROM candidate.county_code
                OR existing.city_name
                    IS DISTINCT FROM candidate.city_name
                OR existing.congressional_district
                    IS DISTINCT FROM
                       candidate.congressional_district
                OR existing.zip_code
                    IS DISTINCT FROM candidate.zip_code
                OR existing.location_scope
                    IS DISTINCT FROM candidate.location_scope;
            """
        )
        updated = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM tmp_procurement_place_link AS candidate
            JOIN procurement.place_of_performance AS existing
              ON existing.award_transaction_id =
                 candidate.award_transaction_id
            WHERE
                existing.place_id
                    IS NOT DISTINCT FROM candidate.place_id
                AND existing.state_id
                    IS NOT DISTINCT FROM candidate.state_id
                AND existing.county_id
                    IS NOT DISTINCT FROM candidate.county_id
                AND existing.country_code
                    IS NOT DISTINCT FROM candidate.country_code
                AND existing.state_code
                    IS NOT DISTINCT FROM candidate.state_code
                AND existing.county_code
                    IS NOT DISTINCT FROM candidate.county_code
                AND existing.city_name
                    IS NOT DISTINCT FROM candidate.city_name
                AND existing.congressional_district
                    IS NOT DISTINCT FROM
                       candidate.congressional_district
                AND existing.zip_code
                    IS NOT DISTINCT FROM candidate.zip_code
                AND existing.location_scope
                    IS NOT DISTINCT FROM candidate.location_scope;
            """
        )
        unchanged = int(cur.fetchone()[0])

    return inserted, updated, unchanged


def apply_links(conn) -> None:
    """Insert or update transaction-to-place relationships."""

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
                    IS DISTINCT FROM
                       EXCLUDED.congressional_district
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
    """Validate completeness and referential integrity."""

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
            FROM tmp_procurement_place_link AS candidate
            LEFT JOIN procurement.place_of_performance AS existing
              ON existing.award_transaction_id =
                 candidate.award_transaction_id
            WHERE existing.place_of_performance_id IS NULL;
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
            FROM procurement.place_of_performance AS relationship
            LEFT JOIN procurement.place AS place
              ON place.place_id = relationship.place_id
            WHERE relationship.place_id IS NOT NULL
              AND place.place_id IS NULL;
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
            f"expected {expected_transactions:,}, "
            f"produced {candidate_count:,}."
        )

    if missing_relationships:
        raise ValueError(
            "Transactions missing place relationships: "
            f"{missing_relationships:,}"
        )

    if duplicate_transactions:
        raise ValueError(
            "Duplicate transaction relationships found: "
            f"{duplicate_transactions:,}"
        )

    if orphan_places:
        raise ValueError(
            "Orphaned canonical place references found: "
            f"{orphan_places:,}"
        )

    if unresolved:
        raise ValueError(
            "Unresolved canonical places found: "
            f"{unresolved:,}"
        )

    return resolved, unresolved


def print_summary(
    summary: LinkSummary,
    elapsed_seconds: float,
) -> None:
    """Print the completed-linking summary."""

    print()
    print("=" * 68)
    print("ETL-004A.3H SUMMARY")
    print("=" * 68)
    print(
        f"Transactions examined ................. "
        f"{summary.transactions_examined:,}"
    )
    print(
        f"Relationships inserted ................ "
        f"{summary.inserted:,}"
    )
    print(
        f"Relationships updated ................. "
        f"{summary.updated:,}"
    )
    print(
        f"Relationships unchanged ............... "
        f"{summary.unchanged:,}"
    )
    print(
        f"Canonical places resolved ............. "
        f"{summary.resolved_places:,}"
    )
    print(
        f"Canonical places unresolved ........... "
        f"{summary.unresolved_places:,}"
    )
    print("Duplicate transaction relationships ... 0")
    print("Orphaned canonical place references ... 0")
    print("Validation ............................. PASS")
    print(
        f"Elapsed time ........................... "
        f"{elapsed_seconds:.2f} sec"
    )
    print("=" * 68)


def main() -> None:
    """Run ETL-004A.3H."""

    args = parse_arguments()
    started = time.perf_counter()

    print("=" * 68)
    print("ETL-004A.3H - Link Procurement Places")
    print("=" * 68)

    conn = get_connection()

    try:
        verify_schema(conn)

        (
            load_batch_id,
            source_file,
            transaction_count,
        ) = get_target_batch(
            conn,
            args.load_batch_id,
        )

        print(f"Target load batch: {load_batch_id}")
        print(f"Source file: {source_file}")
        print(
            f"Normalized transactions: "
            f"{transaction_count:,}"
        )

        candidate_count = create_link_candidate_table(
            conn,
            load_batch_id,
        )

        print(
            f"Place-link candidates: "
            f"{candidate_count:,}"
        )

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