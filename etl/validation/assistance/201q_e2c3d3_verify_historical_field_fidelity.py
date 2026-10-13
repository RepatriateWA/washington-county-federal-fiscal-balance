
"""
ETL-201Q E.2C.3D.3
Historical transaction field-level fidelity certification.

Compares all 31 normalized Python ledger values with their
PostgreSQL typed temporary-stage representations.

No permanent database writes.
No production sequence consumption.
Unconditional rollback.
"""

from __future__ import annotations

import argparse
from collections import Counter
import importlib
import sys

import psycopg2
from psycopg2 import sql


historical = importlib.import_module(
    "etl.loaders."
    "load_usaspending_assistance_historical_transactions_201q"
)

normalizer = importlib.import_module(
    "etl.loaders.normalize_usaspending_assistance_transactions"
)

staging = importlib.import_module(
    "etl.validation.assistance."
    "201q_e2c3_validate_historical_staging"
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def verify_batch_fields(cursor, batch_id, config, columns):
    """
    Independently re-extract normalized Python values and compare
    them with values already written to typed temporary staging.
    """

    eligible_count = config["eligible"]

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
        f"Batch {batch_id}: extraction count mismatch",
    )

    select_columns = (
        *columns,
        "raw_assistance_transaction_id",
    )

    identifiers = sql.SQL(", ").join(
        sql.Identifier(column)
        for column in select_columns
    )

    query = sql.SQL(
        """
        SELECT {}
        FROM {}
        WHERE load_batch_id = %s
        ORDER BY source_row_number
        """
    ).format(
        identifiers,
        sql.Identifier(staging.STAGE),
    )

    cursor.execute(query, (batch_id,))

    mismatches = Counter()
    samples = {}
    compared_rows = 0
    compared_fields = 0

    expected = sorted(
        transactions,
        key=lambda transaction: transaction.source_row_number,
    )

    for transaction in expected:
        staged = cursor.fetchone()

        require(
            staged is not None,
            f"Batch {batch_id}: staging ended prematurely",
        )

        expected_values = (
            *normalizer.transaction_values(transaction),
            transaction.raw_assistance_transaction_id,
        )

        require(
            len(expected_values) == len(select_columns),
            "Expected field count mismatch",
        )

        require(
            len(staged) == len(select_columns),
            "Staged field count mismatch",
        )

        for column, expected_value, staged_value in zip(
            select_columns,
            expected_values,
            staged,
        ):
            compared_fields += 1

            # Python equality handles Decimal values, date objects,
            # integers, strings, and None. Decimal equality detects
            # numeric value changes but intentionally ignores scale
            # differences such as 1.0 versus 1.00.
            if expected_value != staged_value:
                mismatches[column] += 1

                if column not in samples:
                    samples[column] = (
                        transaction.source_row_number,
                        repr(expected_value)[:120],
                        repr(staged_value)[:120],
                    )

        compared_rows += 1

    require(
        cursor.fetchone() is None,
        f"Batch {batch_id}: unexpected extra staged rows",
    )

    require(
        compared_rows == eligible_count,
        f"Batch {batch_id}: compared row count mismatch",
    )

    print()
    print(f"BATCH {batch_id} / FY{config['year']}")
    print("-" * 72)
    print(f"Transactions compared : {compared_rows:,}")
    print(f"Ledger fields per row : {len(columns)}")
    print(f"Field comparisons     : {compared_fields:,}")

    for column in select_columns:
        print(
            f"{column:<45} "
            f"{mismatches[column]:>8,} mismatches"
        )

    if mismatches:
        print()
        print("FIRST MISMATCH SAMPLES")

        for column, sample in samples.items():
            row_number, expected_value, staged_value = sample

            print(
                f"{column}: source row {row_number:,}; "
                f"Python={expected_value}; PostgreSQL={staged_value}"
            )

    require(
        sum(mismatches.values()) == 0,
        f"Batch {batch_id}: "
        f"{sum(mismatches.values()):,} field mismatches",
    )

    print(f"Batch {batch_id} field fidelity: PASS")

    return compared_rows, compared_fields


def run_validation():
    print("=" * 76)
    print("ETL-201Q E.2C.3D.3")
    print("HISTORICAL TRANSACTION FIELD-LEVEL FIDELITY")
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
                "Field policy version changed",
            )

            normalizer.validate_field_policy(cursor)

            historical.verify_preservation_baseline(cursor)

            columns = staging.verify_mapping(cursor)

            require(
                len(columns) == 31,
                "Unexpected ledger column count",
            )

            staging.create_stage(cursor, columns)

            staged_total = 0

            for batch_id, config in historical.EXPECTED.items():
                staged_total += staging.stage_batch(
                    cursor,
                    batch_id,
                    config,
                    columns,
                )

            require(
                staged_total == historical.EXPECTED_TOTAL,
                "Staged population mismatch",
            )

            staging.verify_stage(cursor)
            staging.verify_references(cursor)

            print()
            print("INDEPENDENT PYTHON / POSTGRESQL FIELD COMPARISON")

            total_rows = 0
            total_fields = 0

            for batch_id, config in historical.EXPECTED.items():
                rows, fields = verify_batch_fields(
                    cursor,
                    batch_id,
                    config,
                    columns,
                )

                total_rows += rows
                total_fields += fields

            require(
                total_rows == historical.EXPECTED_TOTAL,
                "Final transaction count mismatch",
            )

            require(
                total_fields == total_rows * 32,
                "Final field comparison count mismatch",
            )

            print()
            print("=" * 76)
            print(f"TOTAL TRANSACTIONS : {total_rows:,}")
            print(f"LEDGER COLUMNS     : {len(columns)}")
            print(f"IDENTITY COLUMNS   : 1 additional raw observation ID")
            print(f"TOTAL COMPARISONS  : {total_fields:,}")
            print("FIELD MISMATCHES   : 0")
            print("E.2C.3D.3 FIELD-LEVEL FIDELITY: PASS")
            print("=" * 76)

    finally:
        connection.rollback()
        connection.close()

        print()
        print("ROLLBACK COMPLETE - CONNECTION CLOSED")
        print("PRODUCTION DML: NONE")
        print("PRODUCTION SEQUENCE CONSUMPTION: NONE")
        print("PERMANENT INSERTION: NOT AUTHORIZED")


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

    run_validation()
    return 0


if __name__ == "__main__":
    sys.exit(main())
