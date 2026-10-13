
"""
ETL-201Q Stage E.2C.3C.1
Historical assistance transaction ledger staging validator.

Temporary staging only.
No production INSERT, UPDATE, DELETE, or COMMIT.
No production sequence consumption.
Permanent historical insertion is NOT authorized.
"""

from __future__ import annotations

import argparse
import importlib
import sys

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values


historical = importlib.import_module(
    "etl.loaders."
    "load_usaspending_assistance_historical_transactions_201q"
)

normalizer = importlib.import_module(
    "etl.loaders.normalize_usaspending_assistance_transactions"
)

STAGE = "etl_201q_historical_stage"

EXPECTED_COLUMNS = 31
EXPECTED_TOTAL = 207343


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def scalar(cursor, statement, params=None):
    cursor.execute(statement, params)
    return int(cursor.fetchone()[0])


def verify_mapping(cursor):
    columns = tuple(normalizer.LEDGER_COLUMNS)

    require(
        len(columns) == EXPECTED_COLUMNS,
        "Production ledger column count changed",
    )

    require(
        len(set(columns)) == EXPECTED_COLUMNS,
        "Duplicate production ledger column",
    )

    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'assistance'
          AND table_name = 'award_transaction'
        """
    )

    available = {row[0] for row in cursor.fetchall()}

    missing = set(columns) - available

    require(
        not missing,
        f"Missing production columns: {sorted(missing)}",
    )

    require(
        "raw_assistance_transaction_id" not in columns,
        "Raw observation ID unexpectedly appears in ledger mapping",
    )

    print("31-column production mapping: PASS")

    return columns


def create_stage(cursor, columns):
    identifiers = sql.SQL(", ").join(
        sql.Identifier(column)
        for column in columns
    )

    cursor.execute(
        sql.SQL(
            """
            CREATE TEMP TABLE {} ON COMMIT DROP AS
            SELECT
                {} 
            FROM assistance.award_transaction
            WITH NO DATA
            """
        ).format(
            sql.Identifier(STAGE),
            identifiers,
        )
    )

    cursor.execute(
        sql.SQL(
            """
            ALTER TABLE {}
            ADD COLUMN raw_assistance_transaction_id BIGINT
            """
        ).format(sql.Identifier(STAGE))
    )

    require(
        scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM pg_catalog.pg_class
            WHERE relname = %s
              AND relnamespace = pg_my_temp_schema()
            """,
            (STAGE,),
        ) == 1,
        "Temporary staging table missing",
    )

    print("Typed temporary staging table: PASS")


def stage_batch(cursor, batch_id, config, columns):
    historical.verify_batch_registry(
        cursor, batch_id, config
    )

    eligible_count = historical.verify_batch_population(
        cursor, batch_id, config
    )

    raw_count, transactions = normalizer.extract_transactions(
        cursor,
        load_batch_id=batch_id,
        expected_resolved_count=eligible_count,
    )

    require(
        raw_count == config["raw"],
        f"Batch {batch_id}: raw count mismatch",
    )

    require(
        len(transactions) == eligible_count,
        f"Batch {batch_id}: eligible count mismatch",
    )

    rows = []

    for transaction in transactions:
        require(
            transaction.load_batch_id == batch_id,
            "Normalized batch mismatch",
        )

        require(
            transaction.action_date_fiscal_year == config["year"],
            "Normalized fiscal-year mismatch",
        )

        require(
            transaction.action_date is not None,
            "Missing action date",
        )

        require(
            transaction.federal_action_obligation is not None,
            "Missing federal action obligation",
        )

        require(
            transaction.assistance_award_id is not None
            and transaction.assistance_award_id > 0,
            "Missing canonical award",
        )

        require(
            transaction.assistance_listing_id is not None
            and transaction.assistance_type_id is not None,
            "Missing classification reference",
        )

        key = transaction.assistance_transaction_unique_key

        require(
            key is not None and bool(key.strip()),
            "Blank transaction key",
        )

        values = normalizer.transaction_values(transaction)

        require(
            len(values) == len(columns),
            "Transaction value mapping mismatch",
        )

        rows.append(
            (
                *values,
                transaction.raw_assistance_transaction_id,
            )
        )

    insert_columns = (
        *columns,
        "raw_assistance_transaction_id",
    )

    column_sql = sql.SQL(", ").join(
        sql.Identifier(column)
        for column in insert_columns
    )

    statement = sql.SQL(
        "INSERT INTO {} ({}) VALUES %s"
    ).format(
        sql.Identifier(STAGE),
        column_sql,
    ).as_string(cursor)

    execute_values(
        cursor,
        statement,
        rows,
        page_size=1000,
    )

    staged_count = scalar(
        cursor,
        sql.SQL(
            "SELECT COUNT(*) FROM {} WHERE load_batch_id = %s"
        ).format(sql.Identifier(STAGE)),
        (batch_id,),
    )

    require(
        staged_count == eligible_count,
        f"Batch {batch_id}: staged count mismatch",
    )

    print(
        f"Batch {batch_id} / FY{config['year']}: "
        f"{staged_count:,} ledger rows staged; "
        f"{config['held']:,} held"
    )

    return staged_count


def verify_stage(cursor):
    count_checks = {
        "Staged ledger rows": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage
        """,
        "Distinct transaction keys": """
            SELECT COUNT(DISTINCT assistance_transaction_unique_key)
            FROM etl_201q_historical_stage
        """,
        "Distinct raw observation IDs": """
            SELECT COUNT(DISTINCT raw_assistance_transaction_id)
            FROM etl_201q_historical_stage
        """,
        "Distinct batch/row pairs": """
            SELECT COUNT(*)
            FROM (
                SELECT load_batch_id, source_row_number
                FROM etl_201q_historical_stage
                GROUP BY load_batch_id, source_row_number
            ) AS pairs
        """,
    }

    for label, statement in count_checks.items():
        actual = scalar(cursor, statement)

        require(
            actual == EXPECTED_TOTAL,
            f"{label}: expected {EXPECTED_TOTAL:,}, "
            f"found {actual:,}",
        )

        print(f"{label}: {actual:,} PASS")

    collision_checks = {
        "Existing canonical transaction keys": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage AS staged
            JOIN assistance.award_transaction AS existing
              ON existing.assistance_transaction_unique_key
                 = staged.assistance_transaction_unique_key
        """,
        "Existing canonical batch/row pairs": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage AS staged
            JOIN assistance.award_transaction AS existing
              ON existing.load_batch_id = staged.load_batch_id
             AND existing.source_row_number
                 = staged.source_row_number
        """,
        "Existing raw provenance links": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage AS staged
            JOIN assistance.award_transaction_observation AS existing
              ON existing.raw_assistance_transaction_id
                 = staged.raw_assistance_transaction_id
        """,
    }

    for label, statement in collision_checks.items():
        actual = scalar(cursor, statement)

        require(
            actual == 0,
            f"{label}: {actual:,} collisions",
        )

        print(f"{label}: {actual:,} PASS")

    null_checks = {
        "Null transaction keys": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage
            WHERE assistance_transaction_unique_key IS NULL
               OR BTRIM(assistance_transaction_unique_key) = ''
        """,
        "Null canonical award IDs": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage
            WHERE assistance_award_id IS NULL
        """,
        "Null raw observation IDs": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage
            WHERE raw_assistance_transaction_id IS NULL
        """,
        "Null batch/row identities": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage
            WHERE load_batch_id IS NULL
               OR source_row_number IS NULL
        """,
    }

    for label, statement in null_checks.items():
        actual = scalar(cursor, statement)

        require(
            actual == 0,
            f"{label}: {actual:,} invalid rows",
        )

        print(f"{label}: {actual:,} PASS")

    print()
    print("E.2C.3C.1 LEDGER STAGING: PASS")
    print("PERMANENT INSERTION: NOT AUTHORIZED")


def verify_references(cursor):
    """Validate staged foreign keys and raw observation identity."""

    checks = {
        "Canonical award references": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage AS staged
            LEFT JOIN assistance.award AS parent
              ON parent.assistance_award_id = staged.assistance_award_id
            WHERE parent.assistance_award_id IS NULL
        """,
        "Batch registry references": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage AS staged
            LEFT JOIN procurement.load_batch AS parent
              ON parent.load_batch_id = staged.load_batch_id
            WHERE parent.load_batch_id IS NULL
        """,
        "Assistance listing references": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage AS staged
            LEFT JOIN assistance.assistance_listing AS parent
              ON parent.assistance_listing_id = staged.assistance_listing_id
            WHERE staged.assistance_listing_id IS NOT NULL
              AND parent.assistance_listing_id IS NULL
        """,
        "Assistance type references": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage AS staged
            LEFT JOIN assistance.assistance_type AS parent
              ON parent.assistance_type_id = staged.assistance_type_id
            WHERE staged.assistance_type_id IS NOT NULL
              AND parent.assistance_type_id IS NULL
        """,
        "Funding opportunity references": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage AS staged
            LEFT JOIN assistance.funding_opportunity AS parent
              ON parent.funding_opportunity_id
                 = staged.funding_opportunity_id
            WHERE staged.funding_opportunity_id IS NOT NULL
              AND parent.funding_opportunity_id IS NULL
        """,
        "Raw observation identity mismatches": """
            SELECT COUNT(*)
            FROM etl_201q_historical_stage AS staged
            LEFT JOIN assistance.raw_award_transaction AS raw
              ON raw.raw_assistance_transaction_id
                 = staged.raw_assistance_transaction_id
            WHERE raw.raw_assistance_transaction_id IS NULL
               OR raw.load_batch_id IS DISTINCT FROM staged.load_batch_id
               OR raw.source_row_number
                  IS DISTINCT FROM staged.source_row_number
               OR raw.assistance_transaction_unique_key
                  IS DISTINCT FROM staged.assistance_transaction_unique_key
        """,
    }

    for label, statement in checks.items():
        failures = scalar(cursor, statement)

        require(
            failures == 0,
            f"{label}: {failures:,} failures",
        )

        print(f"{label}: {failures:,} PASS")

    print("E.2C.3C.2 REFERENTIAL INTEGRITY: PASS")


def run_stage():
    print("=" * 76)
    print("ETL-201Q E.2C.3C.1 - TYPED LEDGER STAGING")
    print("TEMPORARY TABLE ONLY - NO PRODUCTION DML")
    print("=" * 76)

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

            require(
                normalizer.POLICY_VERSION == "ANALYSIS-162-v1",
                "Normalization policy changed",
            )

            normalizer.validate_field_policy(cursor)
            print("ANALYSIS-162-v1 field policy: PASS")

            historical.verify_preservation_baseline(cursor)

            columns = verify_mapping(cursor)
            create_stage(cursor, columns)

            total = 0

            for batch_id, config in historical.EXPECTED.items():
                total += stage_batch(
                    cursor,
                    batch_id,
                    config,
                    columns,
                )

            require(
                total == historical.EXPECTED_TOTAL == EXPECTED_TOTAL,
                "Combined staging population mismatch",
            )

            require(
                sum(
                    config["held"]
                    for config in historical.EXPECTED.values()
                ) == historical.EXPECTED_HELD,
                "Held population control mismatch",
            )

            verify_stage(cursor)
            verify_references(cursor)

    finally:
        connection.rollback()
        connection.close()

        print()
        print("ROLLBACK COMPLETE - CONNECTION CLOSED")
        print("NO PRODUCTION DML")
        print("NO PRODUCTION SEQUENCE CONSUMPTION")


def main():
    parser = argparse.ArgumentParser(
        description="ETL-201Q historical typed staging validator"
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--stage",
        action="store_true",
        help="Validate typed temporary ledger staging",
    )

    mode.add_argument(
        "--commit",
        action="store_true",
        help="Disabled: permanent insertion unauthorized",
    )

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

    if not args.stage:
        parser.error("Specify --stage")

    run_stage()
    return 0


if __name__ == "__main__":
    sys.exit(main())
