
"""
ETL-201Q E.2C.4C.1
Historical assistance transaction insert-only engine.

VERSION: PLAN ONLY

No permanent database writes.
No production sequence consumption.
No commit capability.

Production insertion requires a separately reviewed implementation
and explicit authorization.
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

d4 = importlib.import_module(
    "etl.validation.assistance."
    "201q_d4_validate_historical_transactions"
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def scalar(cursor, statement, params=None):
    cursor.execute(statement, params)
    return int(cursor.fetchone()[0])


def verify_no_production_collisions(cursor, batch_id):
    """
    Check canonical transaction keys, batch/row identities,
    and raw-observation provenance links.
    """

    cursor.execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE canonical_key.assistance_transaction_id IS NOT NULL
            ) AS key_collisions,

            COUNT(*) FILTER (
                WHERE canonical_row.assistance_transaction_id IS NOT NULL
            ) AS batch_row_collisions,

            COUNT(*) FILTER (
                WHERE provenance.award_transaction_observation_id IS NOT NULL
            ) AS provenance_collisions

        FROM assistance.raw_award_transaction AS raw

        LEFT JOIN assistance.award_transaction AS canonical_key
          ON canonical_key.assistance_transaction_unique_key =
             raw.assistance_transaction_unique_key

        LEFT JOIN assistance.award_transaction AS canonical_row
          ON canonical_row.load_batch_id = raw.load_batch_id
         AND canonical_row.source_row_number = raw.source_row_number

        LEFT JOIN assistance.award_transaction_observation AS provenance
          ON provenance.raw_assistance_transaction_id =
             raw.raw_assistance_transaction_id

        WHERE raw.load_batch_id = %s
        """,
        (batch_id,),
    )

    key_count, row_count, provenance_count = (
        int(value) for value in cursor.fetchone()
    )

    print(f"Canonical key collisions : {key_count:,}")
    print(f"Batch/row collisions     : {row_count:,}")
    print(f"Provenance collisions    : {provenance_count:,}")

    require(
        key_count == 0,
        f"Batch {batch_id}: canonical key collisions",
    )

    require(
        row_count == 0,
        f"Batch {batch_id}: batch/row collisions",
    )

    require(
        provenance_count == 0,
        f"Batch {batch_id}: provenance collisions",
    )


def verify_batch(cursor, batch_id, config):
    historical.verify_batch_registry(
        cursor,
        batch_id,
        config,
    )

    eligible = historical.verify_batch_population(
        cursor,
        batch_id,
        config,
    )

    raw = d4.get_raw_count(cursor, batch_id)

    require(
        raw == config["raw"],
        f"Batch {batch_id}: raw count mismatch",
    )

    require(
        eligible == config["eligible"],
        f"Batch {batch_id}: eligible count mismatch",
    )

    held = raw - eligible

    require(
        held == config["held"],
        f"Batch {batch_id}: held count mismatch",
    )

    print()
    print(f"BATCH {batch_id} / FY{config['year']}")
    print("-" * 68)
    print(f"Raw observations        : {raw:,}")
    print(f"Eligible transactions   : {eligible:,}")
    print(f"Held observations       : {held:,}")

    verify_no_production_collisions(cursor, batch_id)

    print(f"Batch {batch_id} plan: PASS")

    return raw, eligible, held


def run_plan():
    connection = psycopg2.connect(
        dbname="wcffbp",
        user="postgres",
        host="localhost",
        port=5432,
    )

    try:
        connection.set_session(
            readonly=True,
            autocommit=False,
            isolation_level="REPEATABLE READ",
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SET LOCAL statement_timeout = '600s'"
            )

            print("=" * 76)
            print("ETL-201Q E.2C.4C.1")
            print("HISTORICAL INSERT-ONLY ENGINE — PLAN MODE")
            print("=" * 76)

            historical.verify_preservation_baseline(cursor)

            existing_transactions = scalar(
                cursor,
                "SELECT COUNT(*) FROM assistance.award_transaction",
            )

            existing_links = scalar(
                cursor,
                """
                SELECT COUNT(*)
                FROM assistance.award_transaction_observation
                """,
            )

            totals = [0, 0, 0]

            for batch_id, config in historical.EXPECTED.items():
                counts = verify_batch(
                    cursor,
                    batch_id,
                    config,
                )

                for index, value in enumerate(counts):
                    totals[index] += value

            require(
                totals[1] == historical.EXPECTED_TOTAL,
                "Combined eligible count mismatch",
            )

            require(
                totals[2] == historical.EXPECTED_HELD,
                "Combined held count mismatch",
            )

            projected_transactions = (
                existing_transactions + totals[1]
            )

            projected_links = existing_links + totals[1]

            require(
                projected_transactions == 1_233_050,
                "Projected canonical count mismatch",
            )

            require(
                projected_links == 1_698_173,
                "Projected provenance count mismatch",
            )

            print()
            print("=" * 76)
            print("COMBINED HISTORICAL INSERTION PLAN")
            print("=" * 76)
            print(f"Raw observations             : {totals[0]:,}")
            print(f"Eligible new transactions    : {totals[1]:,}")
            print(f"Held observations            : {totals[2]:,}")
            print()
            print(f"Existing canonical rows      : {existing_transactions:,}")
            print(f"Projected canonical rows     : {projected_transactions:,}")
            print()
            print(f"Existing provenance links    : {existing_links:,}")
            print(f"Projected provenance links   : {projected_links:,}")
            print()
            print("Existing canonical updates   : 0 planned")
            print("Existing canonical revisions : 0 planned")
            print("Held observations inserted   : 0 planned")
            print()
            print("E.2C.4C.1 PLAN: PASS")
            print("PERMANENT INSERTION: NOT AUTHORIZED")

    finally:
        connection.rollback()
        connection.close()

        print()
        print("READ-ONLY TRANSACTION ROLLED BACK")
        print("CONNECTION CLOSED")
        print("NO PRODUCTION DML")
        print("NO PRODUCTION SEQUENCE CONSUMPTION")


def main():
    parser = argparse.ArgumentParser()

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument("--plan", action="store_true")
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

    if not args.plan:
        parser.error("Specify --plan")

    run_plan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
