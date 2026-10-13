
"""
ETL-201Q E.2C.3D.2
Exact historical transaction membership verification.

READ ONLY.
Independent SQL eligibility set versus production extraction.
No production DML, temporary tables, or sequence consumption.
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

normalizer = importlib.import_module(
    "etl.loaders.normalize_usaspending_assistance_transactions"
)


ELIGIBLE_SQL = """
    SELECT raw.raw_assistance_transaction_id
    FROM assistance.raw_award_transaction AS raw
    WHERE raw.load_batch_id = %s
      AND EXISTS (
          SELECT 1
          FROM assistance.award AS award
          WHERE award.assistance_award_unique_key =
                raw.assistance_award_unique_key
      )
      AND EXISTS (
          SELECT 1
          FROM assistance.assistance_listing AS listing
          WHERE listing.cfda_number =
                BTRIM(raw.raw_record ->> 'cfda_number')
      )
      AND EXISTS (
          SELECT 1
          FROM assistance.assistance_type AS assistance_type
          WHERE assistance_type.assistance_type_code =
                BTRIM(raw.raw_record ->> 'assistance_type_code')
      )
"""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def fetch_ids(cursor, statement, batch_id):
    cursor.execute(statement, (batch_id,))
    ids = [int(row[0]) for row in cursor.fetchall()]

    require(
        len(ids) == len(set(ids)),
        f"Batch {batch_id}: duplicate SQL observation IDs",
    )

    return set(ids)


def verify_batch(cursor, batch_id, config):
    print()
    print(f"BATCH {batch_id} / FY{config['year']}")
    print("-" * 68)

    historical.verify_batch_registry(
        cursor, batch_id, config
    )

    eligible_count = historical.verify_batch_population(
        cursor, batch_id, config
    )

    raw_ids = fetch_ids(
        cursor,
        """
        SELECT raw_assistance_transaction_id
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
        """,
        batch_id,
    )

    eligible_ids = fetch_ids(
        cursor,
        ELIGIBLE_SQL,
        batch_id,
    )

    held_ids = raw_ids - eligible_ids

    raw_count, transactions = normalizer.extract_transactions(
        cursor,
        load_batch_id=batch_id,
        expected_resolved_count=eligible_count,
    )

    extracted_ids = [
        int(transaction.raw_assistance_transaction_id)
        for transaction in transactions
    ]

    extracted_set = set(extracted_ids)

    require(
        len(extracted_ids) == len(extracted_set),
        f"Batch {batch_id}: duplicate extracted observation IDs",
    )

    missing = eligible_ids - extracted_set
    extra = extracted_set - eligible_ids
    held_in_extraction = held_ids & extracted_set

    require(
        len(raw_ids) == config["raw"] == raw_count,
        f"Batch {batch_id}: raw population mismatch",
    )

    require(
        len(eligible_ids) == eligible_count == config["eligible"],
        f"Batch {batch_id}: eligible population mismatch",
    )

    require(
        len(held_ids) == config["held"],
        f"Batch {batch_id}: held population mismatch",
    )

    require(
        len(extracted_set) == eligible_count,
        f"Batch {batch_id}: extraction count mismatch",
    )

    print(f"Raw observation IDs        : {len(raw_ids):,}")
    print(f"SQL eligible IDs           : {len(eligible_ids):,}")
    print(f"Production extracted IDs   : {len(extracted_set):,}")
    print(f"SQL held IDs               : {len(held_ids):,}")
    print(f"Eligible missing           : {len(missing):,}")
    print(f"Extracted but ineligible   : {len(extra):,}")
    print(f"Held IDs in extraction     : {len(held_in_extraction):,}")
    print(
        "Duplicate extracted IDs    : "
        f"{len(extracted_ids) - len(extracted_set):,}"
    )

    require(
        not missing,
        f"Batch {batch_id}: eligible IDs missing: "
        f"{sorted(missing)[:10]}",
    )

    require(
        not extra,
        f"Batch {batch_id}: ineligible IDs extracted: "
        f"{sorted(extra)[:10]}",
    )

    require(
        not held_in_extraction,
        f"Batch {batch_id}: held IDs extracted: "
        f"{sorted(held_in_extraction)[:10]}",
    )

    require(
        raw_ids == eligible_ids | held_ids,
        f"Batch {batch_id}: incomplete raw partition",
    )

    require(
        not (eligible_ids & held_ids),
        f"Batch {batch_id}: overlapping population partition",
    )

    print(f"Batch {batch_id} exact membership: PASS")

    return len(raw_ids), len(eligible_ids), len(held_ids)


def main():
    parser = argparse.ArgumentParser()

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--commit", action="store_true")

    args = parser.parse_args()

    if args.commit:
        print(
            "REFUSED: permanent historical insertion "
            "is not authorized.",
            file=sys.stderr,
        )
        print(
            "No database connection opened.",
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
            print("ETL-201Q E.2C.3D.2")
            print("EXACT HISTORICAL POPULATION MEMBERSHIP")
            print("=" * 76)

            historical.verify_preservation_baseline(cursor)

            totals = [0, 0, 0]

            for batch_id, config in historical.EXPECTED.items():
                result = verify_batch(
                    cursor,
                    batch_id,
                    config,
                )

                for index, value in enumerate(result):
                    totals[index] += value

            require(
                totals[0] == sum(
                    config["raw"]
                    for config in historical.EXPECTED.values()
                ),
                "Combined raw count mismatch",
            )

            require(
                totals[1] == historical.EXPECTED_TOTAL,
                "Combined eligible count mismatch",
            )

            require(
                totals[2] == historical.EXPECTED_HELD,
                "Combined held count mismatch",
            )

            print()
            print("=" * 76)
            print(f"TOTAL RAW OBSERVATIONS : {totals[0]:,}")
            print(f"TOTAL ELIGIBLE         : {totals[1]:,}")
            print(f"TOTAL HELD             : {totals[2]:,}")
            print("E.2C.3D.2 EXACT MEMBERSHIP: PASS")
            print("=" * 76)

    finally:
        connection.rollback()
        connection.close()

        print()
        print("READ-ONLY TRANSACTION ROLLED BACK")
        print("CONNECTION CLOSED")
        print("NO PRODUCTION DML")
        print("NO SEQUENCE CONSUMPTION")
        print("PERMANENT INSERTION: NOT AUTHORIZED")

    return 0


if __name__ == "__main__":
    sys.exit(main())
