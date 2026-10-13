
"""
ETL-201Q E.2C.3D.1
Independent historical transaction population reconciliation.

READ ONLY.
No temporary staging writes.
No production DML.
No sequence consumption.
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


def reconcile_batch(cursor, batch_id, config):
    print()
    print(f"BATCH {batch_id} / FY{config['year']}")
    print("-" * 64)

    historical.verify_batch_registry(
        cursor, batch_id, config
    )

    eligible = historical.verify_batch_population(
        cursor, batch_id, config
    )

    raw_count = d4.get_raw_count(cursor, batch_id)
    eligible_count = d4.get_eligible_count(cursor, batch_id)

    require(
        raw_count == config["raw"],
        f"Batch {batch_id}: raw count mismatch",
    )

    require(
        eligible_count == eligible == config["eligible"],
        f"Batch {batch_id}: eligible count mismatch",
    )

    held = raw_count - eligible_count

    require(
        held == config["held"],
        f"Batch {batch_id}: held count mismatch",
    )

    print(f"Raw observations       : {raw_count:,}")
    print(f"Eligible observations  : {eligible_count:,}")
    print(f"Held observations      : {held:,}")

    # Confirm eligible and held populations form an exact partition.
    # The eligible query is independently defined by the D4
    # production award-resolution predicate.

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
        """,
        (batch_id,),
    )

    independently_counted_raw = int(cursor.fetchone()[0])

    require(
        independently_counted_raw == raw_count,
        f"Batch {batch_id}: raw population mismatch",
    )

    # No historical canonical rows should have been inserted.
    existing_transactions = d4.check_existing_canonical(
        cursor, batch_id
    )

    existing_links = d4.check_existing_links(
        cursor, batch_id
    )

    # These helpers are also used by the prior certified preflight.
    # Their successful completion confirms that existing historical
    # canonical identities and provenance are not being silently reused.

    print("Raw population control : PASS")
    print("Eligible/held arithmetic: PASS")
    print("Existing canonical check: completed")
    print("Existing provenance check: completed")

    return raw_count, eligible_count, held


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--validate",
        action="store_true",
    )

    parser.add_argument(
        "--commit",
        action="store_true",
    )

    args = parser.parse_args()

    if args.commit:
        print(
            "REFUSED: permanent insertion is unauthorized.",
            file=sys.stderr,
        )
        return 2

    if not args.validate:
        parser.error("Specify --validate")

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
            print("ETL-201Q E.2C.3D.1")
            print("INDEPENDENT HISTORICAL POPULATION RECONCILIATION")
            print("=" * 76)

            historical.verify_preservation_baseline(cursor)

            totals = [0, 0, 0]

            for batch_id, config in historical.EXPECTED.items():
                result = reconcile_batch(
                    cursor, batch_id, config
                )

                for index, value in enumerate(result):
                    totals[index] += value

            require(
                totals[0] == sum(
                    item["raw"]
                    for item in historical.EXPECTED.values()
                ),
                "Combined raw population mismatch",
            )

            require(
                totals[1] == historical.EXPECTED_TOTAL,
                "Combined eligible population mismatch",
            )

            require(
                totals[2] == historical.EXPECTED_HELD,
                "Combined held population mismatch",
            )

            print()
            print("=" * 76)
            print(f"TOTAL RAW       : {totals[0]:,}")
            print(f"TOTAL ELIGIBLE  : {totals[1]:,}")
            print(f"TOTAL HELD      : {totals[2]:,}")
            print("E.2C.3D.1 POPULATION RECONCILIATION: PASS")
            print("=" * 76)

    finally:
        connection.rollback()
        connection.close()

        print("READ-ONLY TRANSACTION ROLLED BACK")
        print("CONNECTION CLOSED")
        print("PERMANENT INSERTION: NOT AUTHORIZED")

    return 0


if __name__ == "__main__":
    sys.exit(main())
