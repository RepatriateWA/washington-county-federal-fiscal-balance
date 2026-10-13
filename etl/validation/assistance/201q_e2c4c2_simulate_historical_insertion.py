
"""
ETL-201Q E.2C.4C.2
Historical transaction insertion simulation.

TEMPORARY TABLES ONLY.
No production DML.
No production identity or sequence consumption.
No permanent commit capability.
"""

from __future__ import annotations

import argparse
import importlib
import sys

import psycopg2


historical = importlib.import_module(
    "etl.loaders."
    "load_usaspending_assistance_historical_transactions_201q"
)

staging = importlib.import_module(
    "etl.validation.assistance."
    "201q_e2c3_validate_historical_staging"
)

EXPECTED = 207_343


def require(actual, expected, label):
    if actual != expected:
        raise AssertionError(
            f"{label}: expected {expected:,}, got {actual:,}"
        )
    print(f"{label}: {actual:,} PASS", flush=True)


def count(cursor, sql):
    cursor.execute(sql)
    return int(cursor.fetchone()[0])


def simulate(cursor):
    print("=" * 76, flush=True)
    print("ETL-201Q E.2C.4C.2", flush=True)
    print("TEMPORARY HISTORICAL INSERTION SIMULATION", flush=True)
    print("=" * 76, flush=True)

    historical.verify_preservation_baseline(cursor)

    columns = staging.verify_mapping(cursor)
    staging.create_stage(cursor, columns)

    total = 0

    for batch_id, config in historical.EXPECTED.items():
        inserted = staging.stage_batch(
            cursor,
            batch_id,
            config,
            columns,
        )
        total += inserted

    require(total, EXPECTED, "Staged historical transactions")

    staging.verify_stage(cursor)
    staging.verify_references(cursor)

    # Simulated canonical IDs are deterministic, negative values.
    # They are NOT obtained from production identity sequences.

    cursor.execute(
        f"""
        CREATE TEMP TABLE etl_201q_simulated_canonical
        ON COMMIT DROP AS
        SELECT
            -ROW_NUMBER() OVER (
                ORDER BY load_batch_id, source_row_number
            )::bigint AS simulated_transaction_id,
            load_batch_id,
            source_row_number,
            assistance_transaction_unique_key,
            raw_assistance_transaction_id
        FROM pg_temp.{staging.STAGE}
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX
            etl_201q_simulated_canonical_id_uq
        ON pg_temp.etl_201q_simulated_canonical (
            simulated_transaction_id
        )
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX
            etl_201q_simulated_canonical_key_uq
        ON pg_temp.etl_201q_simulated_canonical (
            assistance_transaction_unique_key
        )
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX
            etl_201q_simulated_canonical_raw_uq
        ON pg_temp.etl_201q_simulated_canonical (
            raw_assistance_transaction_id
        )
        """
    )

    require(
        count(
            cursor,
            """
            SELECT COUNT(*)
            FROM pg_temp.etl_201q_simulated_canonical
            """,
        ),
        EXPECTED,
        "Simulated canonical transactions",
    )

    # Simulated provenance links use only temporary IDs.

    cursor.execute(
        """
        CREATE TEMP TABLE etl_201q_simulated_provenance
        ON COMMIT DROP AS
        SELECT
            raw_assistance_transaction_id,
            simulated_transaction_id
        FROM pg_temp.etl_201q_simulated_canonical
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX
            etl_201q_simulated_provenance_raw_uq
        ON pg_temp.etl_201q_simulated_provenance (
            raw_assistance_transaction_id
        )
        """
    )

    require(
        count(
            cursor,
            """
            SELECT COUNT(*)
            FROM pg_temp.etl_201q_simulated_provenance
            """,
        ),
        EXPECTED,
        "Simulated provenance links",
    )

    # Independent identity reconciliation.

    require(
        count(
            cursor,
            f"""
            SELECT COUNT(*)
            FROM pg_temp.{staging.STAGE} AS s
            LEFT JOIN pg_temp.etl_201q_simulated_canonical AS c
              ON c.assistance_transaction_unique_key =
                 s.assistance_transaction_unique_key
             AND c.load_batch_id = s.load_batch_id
             AND c.source_row_number = s.source_row_number
             AND c.raw_assistance_transaction_id =
                 s.raw_assistance_transaction_id
            WHERE c.simulated_transaction_id IS NULL
            """,
        ),
        0,
        "Unmapped staged transactions",
    )

    require(
        count(
            cursor,
            """
            SELECT COUNT(*)
            FROM pg_temp.etl_201q_simulated_provenance AS p
            LEFT JOIN pg_temp.etl_201q_simulated_canonical AS c
              ON c.simulated_transaction_id =
                 p.simulated_transaction_id
             AND c.raw_assistance_transaction_id =
                 p.raw_assistance_transaction_id
            WHERE c.simulated_transaction_id IS NULL
            """,
        ),
        0,
        "Invalid simulated provenance links",
    )

    require(
        count(
            cursor,
            """
            SELECT COUNT(*)
            FROM pg_temp.etl_201q_simulated_provenance AS p
            LEFT JOIN assistance.raw_award_transaction AS r
              ON r.raw_assistance_transaction_id =
                 p.raw_assistance_transaction_id
            WHERE r.raw_assistance_transaction_id IS NULL
            """,
        ),
        0,
        "Missing raw observations",
    )

    require(
        count(
            cursor,
            """
            SELECT COUNT(*)
            FROM pg_temp.etl_201q_simulated_canonical
            WHERE simulated_transaction_id >= 0
            """,
        ),
        0,
        "Nonnegative simulated IDs",
    )

    print(flush=True)
    print("=" * 76, flush=True)
    print("E.2C.4C.2 TEMPORARY INSERTION SIMULATION: PASS", flush=True)
    print("PRODUCTION INSERTION: NOT AUTHORIZED", flush=True)
    print("=" * 76, flush=True)


def main():
    parser = argparse.ArgumentParser()

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--simulate", action="store_true")
    mode.add_argument("--commit", action="store_true")

    args = parser.parse_args()

    if args.commit:
        print(
            "REFUSED: production insertion is not authorized.",
            file=sys.stderr,
        )
        return 2

    if not args.simulate:
        parser.error("Specify --simulate")

    connection = psycopg2.connect(
        dbname="wcffbp",
        user="postgres",
        host="localhost",
        port=5432,
    )

    try:
        connection.set_session(
            readonly=False,
            autocommit=False,
            isolation_level="REPEATABLE READ",
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SET LOCAL statement_timeout = '600s'"
            )

            simulate(cursor)

        return 0

    finally:
        connection.rollback()
        connection.close()

        print(flush=True)
        print("ROLLBACK COMPLETE")
        print("CONNECTION CLOSED")
        print("PRODUCTION DML: NONE")
        print("PRODUCTION SEQUENCE CONSUMPTION: NONE")


if __name__ == "__main__":
    sys.exit(main())
