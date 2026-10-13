
"""
ETL-201Q E.2C.4C.6
Historical assistance transaction production loader.

FY2018: batch 20, 100426 eligible
FY2019: batch 21, 106917 eligible

PRE-FLIGHT:
    --preflight
    Temporary tables only. No production DML or sequence use.

PRODUCTION:
    --commit --authorization <separately approved token>
    Strict, atomic insert-only operation.

No UPSERT, UPDATE, DELETE, or conflict suppression.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys

import psycopg2
from psycopg2 import sql
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

EXPECTED_BY_BATCH = {20: 100426, 21: 106917}
EXPECTED = 207343
EXPECTED_HELD = 844
BASE_CANONICAL = 1025707
BASE_PROVENANCE = 1490830

# This value is deliberately unset for source review.
# A separately reviewed release must supply authorization.
RELEASE_AUTHORIZATION = "ETL-201Q-FY2018-FY2019-207343"


def require(actual, expected, label):
    if actual != expected:
        raise AssertionError(
            f"{label}: expected {expected:,}; got {actual:,}"
        )
    print(f"PASS {label}: {actual:,}", flush=True)


def count(cur, query, params=None):
    cur.execute(query, params)
    return int(cur.fetchone()[0])


def check_baseline(cur):
    require(
        count(cur, "SELECT COUNT(*) FROM assistance.award_transaction"),
        BASE_CANONICAL,
        "Existing canonical baseline",
    )
    require(
        count(
            cur,
            "SELECT COUNT(*) "
            "FROM assistance.award_transaction_observation",
        ),
        BASE_PROVENANCE,
        "Existing provenance baseline",
    )
    historical.verify_preservation_baseline(cur)


def prepare_stage(cur):
    columns = tuple(staging.verify_mapping(cur))

    if columns != tuple(normalizer.LEDGER_COLUMNS):
        raise AssertionError("31-column interface changed")

    require(len(columns), 31, "Ledger column count")

    staging.create_stage(cur, columns)

    total = 0
    for batch_id in (20, 21):
        config = historical.EXPECTED[batch_id]
        require(
            config["eligible"],
            EXPECTED_BY_BATCH[batch_id],
            f"Batch {batch_id} configured eligibility",
        )
        total += staging.stage_batch(
            cur, batch_id, config, columns
        )

    require(total, EXPECTED, "Staged eligible population")

    staging.verify_stage(cur)
    staging.verify_references(cur)

    return columns


def verify_collisions(cur):
    stage = sql.Identifier("pg_temp", staging.STAGE)

    checks = {
        "Canonical transaction-key collisions": sql.SQL("""
            SELECT COUNT(*)
            FROM {} AS s
            JOIN assistance.award_transaction AS t
              ON t.assistance_transaction_unique_key =
                 s.assistance_transaction_unique_key
        """).format(stage),
        "Canonical batch-row collisions": sql.SQL("""
            SELECT COUNT(*)
            FROM {} AS s
            JOIN assistance.award_transaction AS t
              ON t.load_batch_id = s.load_batch_id
             AND t.source_row_number = s.source_row_number
        """).format(stage),
        "Existing provenance collisions": sql.SQL("""
            SELECT COUNT(*)
            FROM {} AS s
            JOIN assistance.award_transaction_observation AS p
              ON p.raw_assistance_transaction_id =
                 s.raw_assistance_transaction_id
        """).format(stage),
    }

    for label, query in checks.items():
        require(count(cur, query), 0, label)


def verify_held(cur):
    stage = sql.Identifier("pg_temp", staging.STAGE)

    cur.execute(
        sql.SQL("""
            SELECT
                COUNT(*),
                COUNT(p.raw_assistance_transaction_id)
            FROM assistance.raw_award_transaction AS r
            LEFT JOIN {} AS s
              ON s.raw_assistance_transaction_id =
                 r.raw_assistance_transaction_id
            LEFT JOIN assistance.award_transaction_observation AS p
              ON p.raw_assistance_transaction_id =
                 r.raw_assistance_transaction_id
            WHERE r.load_batch_id IN (20, 21)
              AND s.raw_assistance_transaction_id IS NULL
        """).format(stage)
    )

    held, linked = map(int, cur.fetchone())
    require(held, EXPECTED_HELD, "Held raw observations")
    require(linked, 0, "Held observations with provenance")


def insert_canonical(cur, columns):
    column_sql = sql.SQL(", ").join(
        sql.Identifier(name) for name in columns
    )

    query = sql.SQL("""
        INSERT INTO assistance.award_transaction ({columns})
        SELECT {columns}
        FROM {stage}
        ORDER BY load_batch_id, source_row_number
        RETURNING
            assistance_transaction_id,
            assistance_transaction_unique_key,
            load_batch_id,
            source_row_number
    """).format(
        columns=column_sql,
        stage=sql.Identifier("pg_temp", staging.STAGE),
    )

    cur.execute(query)
    rows = cur.fetchall()

    require(len(rows), EXPECTED, "Canonical INSERT RETURNING")

    cur.execute("""
        CREATE TEMP TABLE etl_201q_inserted_ids (
            assistance_transaction_id BIGINT PRIMARY KEY,
            assistance_transaction_unique_key TEXT UNIQUE NOT NULL,
            load_batch_id BIGINT NOT NULL,
            source_row_number BIGINT NOT NULL,
            UNIQUE (load_batch_id, source_row_number)
        ) ON COMMIT DROP
    """)

    execute_values(
        cur,
        """
        INSERT INTO pg_temp.etl_201q_inserted_ids
        (
            assistance_transaction_id,
            assistance_transaction_unique_key,
            load_batch_id,
            source_row_number
        )
        VALUES %s
        """,
        rows,
        page_size=5000,
    )


def verify_id_mapping(cur):
    stage = sql.Identifier("pg_temp", staging.STAGE)

    require(
        count(cur, sql.SQL("""
            SELECT COUNT(*)
            FROM {} AS s
            LEFT JOIN pg_temp.etl_201q_inserted_ids AS i
              ON i.assistance_transaction_unique_key =
                 s.assistance_transaction_unique_key
             AND i.load_batch_id = s.load_batch_id
             AND i.source_row_number = s.source_row_number
            WHERE i.assistance_transaction_id IS NULL
        """).format(stage)),
        0,
        "Staged transactions without returned IDs",
    )

    require(
        count(cur, sql.SQL("""
            SELECT COUNT(*)
            FROM pg_temp.etl_201q_inserted_ids AS i
            LEFT JOIN {} AS s
              ON s.assistance_transaction_unique_key =
                 i.assistance_transaction_unique_key
             AND s.load_batch_id = i.load_batch_id
             AND s.source_row_number = i.source_row_number
            WHERE s.assistance_transaction_unique_key IS NULL
        """).format(stage)),
        0,
        "Returned IDs without staged transactions",
    )


def insert_provenance(cur):
    cur.execute(
        sql.SQL("""
            INSERT INTO assistance.award_transaction_observation (
                raw_assistance_transaction_id,
                assistance_transaction_id
            )
            SELECT
                s.raw_assistance_transaction_id,
                i.assistance_transaction_id
            FROM {} AS s
            JOIN pg_temp.etl_201q_inserted_ids AS i
              ON i.assistance_transaction_unique_key =
                 s.assistance_transaction_unique_key
             AND i.load_batch_id = s.load_batch_id
             AND i.source_row_number = s.source_row_number
            ORDER BY s.load_batch_id, s.source_row_number
        """).format(sql.Identifier("pg_temp", staging.STAGE))
    )

    require(cur.rowcount, EXPECTED, "Provenance inserts")


def verify_persisted_fields(cur, columns):
    stage = sql.Identifier("pg_temp", staging.STAGE)

    # PostgreSQL's IS DISTINCT FROM is NULL-safe.
    # Compare every persisted column with its staged value.
    differences = sql.SQL(" OR ").join(
        sql.SQL("t.{} IS DISTINCT FROM s.{}").format(
            sql.Identifier(name),
            sql.Identifier(name),
        )
        for name in columns
    )

    query = sql.SQL("""
        SELECT COUNT(*)
        FROM {} AS s
        JOIN pg_temp.etl_201q_inserted_ids AS i
          ON i.assistance_transaction_unique_key =
             s.assistance_transaction_unique_key
         AND i.load_batch_id = s.load_batch_id
         AND i.source_row_number = s.source_row_number
        JOIN assistance.award_transaction AS t
          ON t.assistance_transaction_id =
             i.assistance_transaction_id
        WHERE {}
    """).format(stage, differences)

    require(
        count(cur, query),
        0,
        "Persisted rows with field differences",
    )

    print(
        f"PASS persisted field coverage: "
        f"{EXPECTED * len(columns):,} comparisons",
        flush=True,
    )

def verify_exact_provenance_mapping(cur):
    """
    Verify every staged historical observation is linked to
    exactly its newly inserted canonical transaction.
    """

    stage = sql.Identifier("pg_temp", staging.STAGE)

    require(
        count(
            cur,
            sql.SQL("""
                SELECT COUNT(*)
                FROM {} AS s
                JOIN pg_temp.etl_201q_inserted_ids AS i
                  ON i.assistance_transaction_unique_key =
                     s.assistance_transaction_unique_key
                 AND i.load_batch_id = s.load_batch_id
                 AND i.source_row_number = s.source_row_number
                JOIN assistance.award_transaction AS t
                  ON t.assistance_transaction_id =
                     i.assistance_transaction_id
                 AND t.assistance_transaction_unique_key =
                     s.assistance_transaction_unique_key
                 AND t.load_batch_id = s.load_batch_id
                 AND t.source_row_number = s.source_row_number
                JOIN assistance.award_transaction_observation AS p
                  ON p.assistance_transaction_id =
                     i.assistance_transaction_id
                 AND p.raw_assistance_transaction_id =
                     s.raw_assistance_transaction_id
            """).format(stage),
        ),
        EXPECTED,
        "Exact canonical-to-provenance mappings",
    )

    require(
        count(
            cur,
            sql.SQL("""
                SELECT COUNT(*)
                FROM pg_temp.etl_201q_inserted_ids AS i
                JOIN assistance.award_transaction_observation AS p
                  ON p.assistance_transaction_id =
                     i.assistance_transaction_id
                LEFT JOIN {} AS s
                  ON s.raw_assistance_transaction_id =
                     p.raw_assistance_transaction_id
                 AND s.assistance_transaction_unique_key =
                     i.assistance_transaction_unique_key
                 AND s.load_batch_id = i.load_batch_id
                 AND s.source_row_number = i.source_row_number
                WHERE s.raw_assistance_transaction_id IS NULL
            """).format(stage),
        ),
        0,
        "Unexpected provenance links to new transactions",
    )

def verify_post_insert(cur, columns):
    require(
        count(cur, "SELECT COUNT(*) FROM assistance.award_transaction"),
        BASE_CANONICAL + EXPECTED,
        "Final canonical population",
    )

    require(
        count(
            cur,
            "SELECT COUNT(*) "
            "FROM assistance.award_transaction_observation",
        ),
        BASE_PROVENANCE + EXPECTED,
        "Final provenance population",
    )

    verify_id_mapping(cur)
    verify_exact_provenance_mapping(cur)
    verify_persisted_fields(cur, columns)
    verify_held(cur)

    for batch_id, eligible in EXPECTED_BY_BATCH.items():
        require(
            count(
                cur,
                """
                SELECT COUNT(*)
                FROM assistance.award_transaction
                WHERE load_batch_id = %s
                """,
                (batch_id,),
            ),
            eligible,
            f"Batch {batch_id} canonical population",
        )

        result = normalizer.validate_results(
            cur,
            load_batch_id=batch_id,
            raw_row_count=eligible,
        )

        require(
            result["normalized_row_count"],
            eligible,
            f"Batch {batch_id} provenance population",
        )

        require(
            result["cross_batch_reobservation_count"],
            0,
            f"Batch {batch_id} cross-batch reobservations",
        )


def connect():
    # Uses existing libpq environment credentials.
    # PGHOST, PGPORT, PGUSER, PGPASSWORD / pgpass.
    return psycopg2.connect(
        dbname=os.environ.get("PGDATABASE", "wcffbp"),
        application_name="ETL-201Q-E2C4C6",
        connect_timeout=15,
    )


def run(preflight):
    connection = connect()
    committed = False

    try:
        connection.autocommit = False

        with connection.cursor() as cur:
            cur.execute(
                "SET TRANSACTION ISOLATION LEVEL READ COMMITTED"
            )

            # Lock before staging and baseline verification.
            # Lock order is fixed for this loader.
            cur.execute("""
                LOCK TABLE
                    assistance.award_transaction,
                    assistance.award_transaction_observation
                IN SHARE ROW EXCLUSIVE MODE
            """)

            check_baseline(cur)
            columns = prepare_stage(cur)
            verify_collisions(cur)
            verify_held(cur)

            if preflight:
                print("PREFLIGHT PASS")
                print("PRODUCTION INSERTS: NONE")
                print("SEQUENCE CONSUMPTION: NONE")
                return

            insert_canonical(cur, columns)
            verify_id_mapping(cur)
            insert_provenance(cur)
            verify_post_insert(cur, columns)

            print("ALL PRE-COMMIT VALIDATIONS PASS")

        connection.commit()
        committed = True
        print("PRODUCTION COMMIT COMPLETE")

    finally:
        if not committed:
            connection.rollback()
            print("TRANSACTION ROLLED BACK", flush=True)
        connection.close()


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)

    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--commit", action="store_true")

    parser.add_argument("--authorization", default=None)
    args = parser.parse_args()

    if args.commit:
        if (
            RELEASE_AUTHORIZATION is None
            or args.authorization != RELEASE_AUTHORIZATION
        ):
            print(
                "REFUSED: production release authorization "
                "has not been configured.",
                file=sys.stderr,
            )
            print("NO DATABASE CONNECTION")
            return 2

    if args.authorization and not args.commit:
        parser.error("--authorization requires --commit")

    print("=" * 76)
    print("ETL-201Q E.2C.4C.6")
    print(
        "READ-ONLY PREFLIGHT"
        if args.preflight
        else "AUTHORIZED PRODUCTION LOAD"
    )
    print("=" * 76)

    run(preflight=args.preflight)
    return 0


if __name__ == "__main__":
    sys.exit(main())
