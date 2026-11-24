
"""
ETL-201Q E.2C.4C.4
Controlled historical assistance transaction loader.

SOURCE REVIEW VERSION — PRODUCTION EXECUTION DISABLED.

Historical batches:
    20 / FY2018: 100,426 eligible
    21 / FY2019: 106,917 eligible

Rules:
    - Strict INSERT only
    - No UPSERT or conflict suppression
    - No canonical UPDATE or revision
    - Exact raw-observation provenance
    - One atomic transaction
    - Commit authorization deliberately disabled
"""

from __future__ import annotations

import argparse
import importlib
import sys

import psycopg2
from psycopg2.extras import execute_values


historical = importlib.import_module(
    "etl.loaders."
    "load_usaspending_assistance_historical_transactions_201q"
)

staging = importlib.import_module(
    "etl.validation.assistance."
    "201q_e2c3_validate_historical_staging"
)

normalizer = importlib.import_module(
    "etl.loaders.normalize_usaspending_assistance_transactions"
)

EXPECTED = 207_343
EXPECTED_HELD = 844
BASELINE_CANONICAL = 1_025_707
BASELINE_PROVENANCE = 1_490_830

# Deliberately locked. Do not change during source review.
COMMIT_AUTHORIZED = False


def require(actual, expected, label):
    if actual != expected:
        raise AssertionError(
            f"{label}: expected {expected:,}, got {actual:,}"
        )
    print(f"{label}: {actual:,} PASS", flush=True)


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return int(cur.fetchone()[0])


def prepare_stage(cur):
    """Build and certify the complete historical population."""

    historical.verify_preservation_baseline(cur)

    columns = staging.verify_mapping(cur)

    if tuple(columns) != tuple(normalizer.LEDGER_COLUMNS):
        raise AssertionError("Production ledger mapping changed")

    staging.create_stage(cur, columns)

    total = 0

    for batch_id, config in historical.EXPECTED.items():
        total += staging.stage_batch(
            cur,
            batch_id,
            config,
            columns,
        )

    require(total, EXPECTED, "Eligible staged transactions")

    staging.verify_stage(cur)
    staging.verify_references(cur)

    return columns


def insert_canonical(cur, columns):
    """
    Intended production operation.

    This function is not reachable from the locked CLI.

    Insert canonical rows and capture database-generated IDs.
    """

    selected = ", ".join(columns)

    cur.execute(
        f"""
        INSERT INTO assistance.award_transaction (
            {selected}
        )
        SELECT
            {selected}
        FROM pg_temp.{staging.STAGE}
        ORDER BY load_batch_id, source_row_number
        RETURNING
            assistance_transaction_id,
            assistance_transaction_unique_key,
            load_batch_id,
            source_row_number
        """
    )

    returned = cur.fetchall()

    require(
        len(returned),
        EXPECTED,
        "Canonical INSERT RETURNING population",
    )

    # Mapping table is temporary and does not inherit any
    # production identity defaults or sequence dependencies.

    cur.execute(
        """
        CREATE TEMP TABLE etl_201q_inserted_ids (
            assistance_transaction_id BIGINT NOT NULL,
            assistance_transaction_unique_key TEXT NOT NULL,
            load_batch_id BIGINT NOT NULL,
            source_row_number BIGINT NOT NULL
        ) ON COMMIT DROP
        """
    )

    execute_values(
        cur,
        """
        INSERT INTO pg_temp.etl_201q_inserted_ids (
            assistance_transaction_id,
            assistance_transaction_unique_key,
            load_batch_id,
            source_row_number
        )
        VALUES %s
        """,
        returned,
        page_size=5000,
    )

    cur.execute(
        """
        CREATE UNIQUE INDEX etl_201q_inserted_id_uq
        ON pg_temp.etl_201q_inserted_ids (
            assistance_transaction_id
        )
        """
    )

    cur.execute(
        """
        CREATE UNIQUE INDEX etl_201q_inserted_key_uq
        ON pg_temp.etl_201q_inserted_ids (
            assistance_transaction_unique_key
        )
        """
    )

    cur.execute(
        """
        CREATE UNIQUE INDEX etl_201q_inserted_batch_row_uq
        ON pg_temp.etl_201q_inserted_ids (
            load_batch_id,
            source_row_number
        )
        """
    )


def verify_generated_id_mapping(cur):
    """Check the returned identities against staging."""

    require(
        scalar(
            cur,
            f"""
            SELECT COUNT(*)
            FROM pg_temp.{staging.STAGE} AS s
            LEFT JOIN pg_temp.etl_201q_inserted_ids AS i
              ON i.assistance_transaction_unique_key =
                 s.assistance_transaction_unique_key
             AND i.load_batch_id = s.load_batch_id
             AND i.source_row_number = s.source_row_number
            WHERE i.assistance_transaction_id IS NULL
            """,
        ),
        0,
        "Staged rows without generated IDs",
    )

    require(
        scalar(
            cur,
            f"""
            SELECT COUNT(*)
            FROM pg_temp.etl_201q_inserted_ids AS i
            LEFT JOIN pg_temp.{staging.STAGE} AS s
              ON s.assistance_transaction_unique_key =
                 i.assistance_transaction_unique_key
             AND s.load_batch_id = i.load_batch_id
             AND s.source_row_number = i.source_row_number
            WHERE s.assistance_transaction_unique_key IS NULL
            """,
        ),
        0,
        "Generated IDs without staged rows",
    )


def insert_provenance(cur):
    """
    Strict provenance INSERT.

    No ON CONFLICT clause.
    Every raw observation must map to one new canonical ID.
    """

    cur.execute(
        f"""
        INSERT INTO assistance.award_transaction_observation (
            raw_assistance_transaction_id,
            assistance_transaction_id
        )
        SELECT
            s.raw_assistance_transaction_id,
            i.assistance_transaction_id
        FROM pg_temp.{staging.STAGE} AS s
        JOIN pg_temp.etl_201q_inserted_ids AS i
          ON i.assistance_transaction_unique_key =
             s.assistance_transaction_unique_key
         AND i.load_batch_id = s.load_batch_id
         AND i.source_row_number = s.source_row_number
        ORDER BY s.load_batch_id, s.source_row_number
        """
    )

    require(
        cur.rowcount,
        EXPECTED,
        "Inserted provenance links",
    )


def verify_post_insert(cur):
    """Check the full insertion before any possible commit."""

    require(
        scalar(
            cur,
            "SELECT COUNT(*) FROM assistance.award_transaction",
        ),
        BASELINE_CANONICAL + EXPECTED,
        "Final canonical population",
    )

    require(
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM assistance.award_transaction_observation
            """,
        ),
        BASELINE_PROVENANCE + EXPECTED,
        "Final provenance population",
    )

    require(
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM pg_temp.etl_201q_inserted_ids
            """,
        ),
        EXPECTED,
        "Inserted ID mapping population",
    )

    require(
        scalar(
            cur,
            f"""
            SELECT COUNT(*)
            FROM pg_temp.{staging.STAGE} AS s
            JOIN pg_temp.etl_201q_inserted_ids AS i
              ON i.assistance_transaction_unique_key =
                 s.assistance_transaction_unique_key
             AND i.load_batch_id = s.load_batch_id
             AND i.source_row_number = s.source_row_number
            JOIN assistance.award_transaction AS t
              ON t.assistance_transaction_id =
                 i.assistance_transaction_id
            JOIN assistance.award_transaction_observation AS p
              ON p.assistance_transaction_id =
                 i.assistance_transaction_id
             AND p.raw_assistance_transaction_id =
                 s.raw_assistance_transaction_id
            """,
        ),
        EXPECTED,
        "Correctly linked new transactions",
    )

    for batch_id, config in historical.EXPECTED.items():
        require(
            scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM assistance.award_transaction
                WHERE load_batch_id = %s
                """,
                (batch_id,),
            ),
            config["eligible"],
            f"Batch {batch_id} canonical population",
        )

        # Reuse the established production validation with
        # the eligible count, not the complete raw count.
        result = normalizer.validate_results(
            cur,
            load_batch_id=batch_id,
            raw_row_count=config["eligible"],
        )

        require(
            result["normalized_row_count"],
            config["eligible"],
            f"Batch {batch_id} provenance population",
        )

        require(
            result["cross_batch_reobservation_count"],
            0,
            f"Batch {batch_id} cross-batch reobservations",
        )

    # No held observation may have gained a provenance link.
    require(
        scalar(
            cur,
            f"""
            SELECT COUNT(*)
            FROM assistance.raw_award_transaction AS r
            JOIN assistance.award_transaction_observation AS p
              ON p.raw_assistance_transaction_id =
                 r.raw_assistance_transaction_id
            WHERE r.load_batch_id IN (20, 21)
              AND NOT EXISTS (
                  SELECT 1
                  FROM pg_temp.{staging.STAGE} AS s
                  WHERE s.raw_assistance_transaction_id =
                        r.raw_assistance_transaction_id
              )
            """,
        ),
        0,
        "Held observations linked",
    )


def production_insertion_contract(cur):
    """
    Source-review-only insertion sequence.

    This function is deliberately not called by main().
    """

    # Prevent concurrent ordinary INSERT/UPDATE/DELETE
    # operations against the two destination tables while
    # the insertion and verification transaction executes.
    cur.execute(
        """
        LOCK TABLE
            assistance.award_transaction,
            assistance.award_transaction_observation
        IN SHARE ROW EXCLUSIVE MODE
        """
    )

    columns = prepare_stage(cur)

    # Constraints and baseline checks are repeated after
    # acquiring the destination-table locks.

    require(
        scalar(
            cur,
            "SELECT COUNT(*) FROM assistance.award_transaction",
        ),
        BASELINE_CANONICAL,
        "Locked canonical baseline",
    )

    require(
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM assistance.award_transaction_observation
            """,
        ),
        BASELINE_PROVENANCE,
        "Locked provenance baseline",
    )

    insert_canonical(cur, columns)
    verify_generated_id_mapping(cur)
    insert_provenance(cur)
    verify_post_insert(cur)


def main():
    parser = argparse.ArgumentParser()

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--review", action="store_true")
    mode.add_argument("--commit", action="store_true")

    args = parser.parse_args()

    if args.commit:
        print(
            "REFUSED: production insertion is not authorized.",
            file=sys.stderr,
        )
        print(
            "No database connection opened.",
            file=sys.stderr,
        )
        return 2

    if not args.review:
        parser.error("Specify --review")

    print("=" * 76)
    print("ETL-201Q E.2C.4C.4")
    print("HISTORICAL INSERT-ONLY LOADER — SOURCE REVIEW")
    print("=" * 76)

    print(f"Commit authorized: {COMMIT_AUTHORIZED}")
    print(f"Expected canonical inserts: {EXPECTED:,}")
    print(f"Expected provenance inserts: {EXPECTED:,}")
    print(f"Expected held observations: {EXPECTED_HELD:,}")
    print(f"Ledger columns: {len(normalizer.LEDGER_COLUMNS)}")

    require(
        len(normalizer.LEDGER_COLUMNS),
        31,
        "Production ledger column count",
    )

    if COMMIT_AUTHORIZED:
        raise AssertionError(
            "Source-review version must remain locked"
        )

    print()
    print("SOURCE REVIEW MODE: PASS")
    print("PRODUCTION CONNECTION: NONE")
    print("PRODUCTION DML: NONE")
    print("PRODUCTION SEQUENCE CONSUMPTION: NONE")
    print("PERMANENT INSERTION: NOT AUTHORIZED")

    return 0


if __name__ == "__main__":
    sys.exit(main())
