
"""
ETL-201Q Stage D.5
Historical Assistance Transaction Staging Simulation v0.1

Creates and populates a PostgreSQL TEMPORARY table only.

No permanent database writes.
No production identity-sequence consumption.
No modifications to the existing production loader.

Uses the established Stage D.4 validation module.
"""

from __future__ import annotations

import importlib
import sys
from collections import Counter
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

normalizer = importlib.import_module(
    "etl.loaders.normalize_usaspending_assistance_transactions"
)

d4 = importlib.import_module(
    "etl.validation.assistance.201q_d4_validate_historical_transactions"
)


EXPECTED_ELIGIBLE = {
    20: 100426,
    21: 106917,
}

EXPECTED_HELD = {
    20: 423,
    21: 421,
}

EXPECTED_TOTAL = 207343


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def extract_batch(cursor, batch_id, expected_count):
    """
    Reuse the production extraction SQL and parsing functions,
    adapting only its historical population-count assertion.
    """

    adapter = d4.HistoricalExtractionCursor(
        cursor,
        eligible_count=expected_count,
    )

    extracted_count, transactions = normalizer.extract_transactions(
        adapter,
        load_batch_id=batch_id,
    )

    require(
        extracted_count == expected_count,
        f"Batch {batch_id}: extraction count mismatch",
    )

    require(
        len(transactions) == expected_count,
        f"Batch {batch_id}: normalized count mismatch",
    )

    require(
        adapter.query_count == 2,
        f"Batch {batch_id}: unexpected extraction query count",
    )

    return transactions


def create_staging_table(cursor):
    """
    Copy production column definitions without copying identity
    properties, defaults, indexes, or production constraints.

    Add staging-specific uniqueness controls and provenance IDs.
    """

    cursor.execute(
        """
        CREATE TEMP TABLE historical_transaction_stage
        ON COMMIT DROP
        AS
        SELECT
            transaction.load_batch_id,
            transaction.source_row_number,
            transaction.assistance_transaction_unique_key,
            transaction.assistance_award_id,
            transaction.modification_number,
            transaction.action_date,
            transaction.action_date_fiscal_year,
            transaction.federal_action_obligation,
            transaction.total_obligated_amount,
            transaction.total_outlayed_amount_for_overall_award,
            transaction.indirect_cost_federal_share_amount,
            transaction.non_federal_funding_amount,
            transaction.total_non_federal_funding_amount,
            transaction.face_value_of_loan,
            transaction.original_loan_subsidy_cost,
            transaction.total_face_value_of_loan,
            transaction.total_loan_subsidy_cost,
            transaction.generated_pragmatic_obligations,
            transaction.covid_overall_award_obligation,
            transaction.covid_overall_award_outlay,
            transaction.iija_overall_award_obligation,
            transaction.iija_overall_award_outlay,
            transaction.disaster_emergency_fund_codes_raw,
            transaction.assistance_listing_id,
            transaction.assistance_type_id,
            transaction.funding_opportunity_id,
            transaction.transaction_description,
            transaction.action_type_code,
            transaction.record_type_code,
            transaction.correction_delete_indicator_code,
            transaction.usaspending_permalink,
            NULL::bigint AS raw_assistance_transaction_id
        FROM assistance.award_transaction transaction
        WHERE FALSE;
        """
    )

    cursor.execute(
        """
        ALTER TABLE historical_transaction_stage
            ALTER COLUMN raw_assistance_transaction_id
                SET NOT NULL;

        ALTER TABLE historical_transaction_stage
            ADD CONSTRAINT historical_stage_transaction_key_uq
                UNIQUE (assistance_transaction_unique_key);

        ALTER TABLE historical_transaction_stage
            ADD CONSTRAINT historical_stage_batch_row_uq
                UNIQUE (load_batch_id, source_row_number);

        ALTER TABLE historical_transaction_stage
            ADD CONSTRAINT historical_stage_raw_id_uq
                UNIQUE (raw_assistance_transaction_id);
        """
    )


def insert_staging_batch(cursor, transactions):
    columns = (
        list(normalizer.LEDGER_COLUMNS)
        + ["raw_assistance_transaction_id"]
    )

    column_sql = ", ".join(columns)

    rows = [
        normalizer.transaction_values(transaction)
        + (transaction.raw_assistance_transaction_id,)
        for transaction in transactions
    ]

    require(
        all(len(row) == len(columns) for row in rows),
        "Staging column/value count mismatch",
    )

    sql = f"""
        INSERT INTO historical_transaction_stage (
            {column_sql}
        )
        VALUES %s
    """

    execute_values(
        cursor,
        sql,
        rows,
        page_size=1000,
    )

    return len(rows)


def validate_staging(cursor):
    cursor.execute(
        """
        SELECT
            load_batch_id,
            COUNT(*) AS staged_rows,
            COUNT(DISTINCT assistance_transaction_unique_key)
                AS distinct_keys,
            COUNT(DISTINCT raw_assistance_transaction_id)
                AS distinct_raw_ids,
            COUNT(*) FILTER (
                WHERE assistance_award_id IS NULL
            ) AS null_award_ids,
            COUNT(*) FILTER (
                WHERE action_date IS NULL
            ) AS null_action_dates,
            COUNT(*) FILTER (
                WHERE federal_action_obligation IS NULL
            ) AS null_obligations
        FROM historical_transaction_stage
        GROUP BY load_batch_id
        ORDER BY load_batch_id;
        """
    )

    results = cursor.fetchall()

    total = 0

    for (
        batch_id,
        staged_rows,
        distinct_keys,
        distinct_raw_ids,
        null_award_ids,
        null_action_dates,
        null_obligations,
    ) in results:

        expected = EXPECTED_ELIGIBLE[batch_id]

        require(
            staged_rows == expected,
            f"Batch {batch_id}: staging count mismatch",
        )

        require(
            distinct_keys == expected,
            f"Batch {batch_id}: key uniqueness mismatch",
        )

        require(
            distinct_raw_ids == expected,
            f"Batch {batch_id}: raw ID uniqueness mismatch",
        )

        require(
            null_award_ids == 0,
            f"Batch {batch_id}: null award reference",
        )

        require(
            null_action_dates == 0,
            f"Batch {batch_id}: null action date",
        )

        require(
            null_obligations == 0,
            f"Batch {batch_id}: null obligation",
        )

        total += staged_rows

        print(
            f"Batch {batch_id}: "
            f"{staged_rows:,} staged / "
            f"{distinct_keys:,} keys / "
            f"{distinct_raw_ids:,} raw IDs"
        )

    require(
        total == EXPECTED_TOTAL,
        f"Total staging mismatch: {total}",
    )

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM historical_transaction_stage stage
        LEFT JOIN assistance.award award
          ON award.assistance_award_id =
             stage.assistance_award_id
        WHERE award.assistance_award_id IS NULL;
        """
    )

    orphan_awards = int(cursor.fetchone()[0])

    require(
        orphan_awards == 0,
        f"Orphan award references: {orphan_awards}",
    )

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM historical_transaction_stage stage
        JOIN assistance.award_transaction existing
          ON existing.assistance_transaction_unique_key =
             stage.assistance_transaction_unique_key;
        """
    )

    canonical_collisions = int(cursor.fetchone()[0])

    require(
        canonical_collisions == 0,
        f"Existing canonical key collisions: {canonical_collisions}",
    )

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM historical_transaction_stage stage
        JOIN assistance.award_transaction_observation existing
          ON existing.raw_assistance_transaction_id =
             stage.raw_assistance_transaction_id;
        """
    )

    existing_links = int(cursor.fetchone()[0])

    require(
        existing_links == 0,
        f"Existing provenance-link collisions: {existing_links}",
    )

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM historical_transaction_stage stage
        JOIN assistance.raw_award_transaction raw
          ON raw.raw_assistance_transaction_id =
             stage.raw_assistance_transaction_id
        WHERE stage.load_batch_id <> raw.load_batch_id
           OR stage.source_row_number <> raw.source_row_number
           OR stage.assistance_transaction_unique_key
              IS DISTINCT FROM
              raw.assistance_transaction_unique_key;
        """
    )

    provenance_mismatches = int(cursor.fetchone()[0])

    require(
        provenance_mismatches == 0,
        f"Raw provenance identity mismatches: {provenance_mismatches}",
    )

    print()
    print("Orphan award references       : 0")
    print("Existing canonical collisions : 0")
    print("Existing provenance collisions: 0")
    print("Raw provenance mismatches     : 0")

    return total


def main():
    print("=" * 76)
    print("ETL-201Q STAGE D.5 - HISTORICAL STAGING SIMULATION")
    print("TEMP TABLE ONLY - NO PRODUCTION SEQUENCE CONSUMPTION")
    print("=" * 76)

    connection = psycopg2.connect(
        dbname="wcffbp",
        user="postgres",
        host="localhost",
        port=5432,
    )

    try:
        connection.autocommit = False

        with connection.cursor() as cursor:
            cursor.execute(
                """
                BEGIN;
                SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
                SET LOCAL statement_timeout = '600s';
                """
            )

            normalizer.validate_field_policy(cursor)

            print()
            print("ANALYSIS-162-v1 policy: PASS")

            create_staging_table(cursor)

            inserted = 0

            for batch_id, expected_count in EXPECTED_ELIGIBLE.items():
                transactions = extract_batch(
                    cursor,
                    batch_id,
                    expected_count,
                )

                inserted += insert_staging_batch(
                    cursor,
                    transactions,
                )

                del transactions

            require(
                inserted == EXPECTED_TOTAL,
                f"Staged insertion count mismatch: {inserted}",
            )

            print()
            print("STAGING POPULATION")
            print("-" * 68)

            total = validate_staging(cursor)

            print()
            print(f"Total staged transactions: {total:,}")
            print("PostgreSQL staging compatibility: PASS")
            print("ETL-201Q STAGE D.5: PASS")

    finally:
        connection.rollback()
        connection.close()

        print()
        print("ROLLBACK COMPLETE - TEMPORARY TABLE DISCARDED")
        print("NO PERMANENT DATABASE WRITES")
        print("NO PRODUCTION IDENTITY SEQUENCE CONSUMPTION")


if __name__ == "__main__":
    main()
