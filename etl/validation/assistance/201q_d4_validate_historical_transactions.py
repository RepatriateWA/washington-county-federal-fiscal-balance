
"""
ETL-201Q Stage D.4
Historical Assistance Transaction Normalization Dry Run v0.1

READ ONLY.
No INSERT, UPDATE, DELETE, DDL, sequence consumption, or COMMIT.

Historical batches:
    FY2018: load_batch_id 20
    FY2019: load_batch_id 21

Reuses the production ANALYSIS-162-v1 extractor and parsers.
The historical adapter changes only the count supplied to the
extractor's full-batch reconciliation check.

It does not modify the production loader.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import psycopg2


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from etl.loaders import (  # noqa: E402
    normalize_usaspending_assistance_transactions as normalizer,
)


EXPECTED = {
    20: {
        "fiscal_year": 2018,
        "raw": 100849,
        "eligible": 100426,
        "held": 423,
    },
    21: {
        "fiscal_year": 2019,
        "raw": 107338,
        "eligible": 106917,
        "held": 421,
    },
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class HistoricalExtractionCursor:
    """
    Read-only adapter for the production extractor.

    The production extractor first requests the raw batch count,
    then executes its existing normalization SELECT.

    For historical batches, the first count must represent the
    eligible population rather than the complete raw population.

    No SQL joins, filters, parsers, or field mappings are changed.
    """

    def __init__(self, cursor, eligible_count):
        self.cursor = cursor
        self.eligible_count = eligible_count
        self.count_intercepted = False
        self.query_count = 0

    def execute(self, sql, params=None):
        normalized_sql = " ".join(sql.lower().split())

        if (
            "select count(*)" in normalized_sql
            and "from assistance.raw_award_transaction" in normalized_sql
            and "where load_batch_id = %s" in normalized_sql
        ):
            require(
                not self.count_intercepted,
                "Historical count intercepted more than once",
            )

            self.count_intercepted = True
            self.query_count += 1
            return

        self.query_count += 1
        return self.cursor.execute(sql, params)

    def fetchone(self):
        if self.count_intercepted:
            self.count_intercepted = False
            return (self.eligible_count,)

        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


def get_raw_count(cursor, batch_id):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
        """,
        (batch_id,),
    )
    return int(cursor.fetchone()[0])


def get_eligible_count(cursor, batch_id):
    """
    Count observations satisfying the production extractor's
    required joins, without multiplying the result by optional
    reference-table joins.
    """

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction raw
        WHERE raw.load_batch_id = %s
          AND EXISTS (
              SELECT 1
              FROM assistance.award award
              WHERE award.assistance_award_unique_key =
                    raw.assistance_award_unique_key
          )
          AND EXISTS (
              SELECT 1
              FROM assistance.assistance_listing listing
              WHERE listing.cfda_number =
                    BTRIM(raw.raw_record ->> 'cfda_number')
          )
          AND EXISTS (
              SELECT 1
              FROM assistance.assistance_type assistance_type
              WHERE assistance_type.assistance_type_code =
                    BTRIM(
                        raw.raw_record ->> 'assistance_type_code'
                    )
          )
        """,
        (batch_id,),
    )

    return int(cursor.fetchone()[0])


def check_existing_canonical(cursor, batch_id):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction raw
        JOIN assistance.award_transaction transaction
          ON transaction.assistance_transaction_unique_key =
             raw.assistance_transaction_unique_key
        WHERE raw.load_batch_id = %s
        """,
        (batch_id,),
    )

    return int(cursor.fetchone()[0])


def check_existing_links(cursor, batch_id):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction raw
        JOIN assistance.award_transaction_observation observation
          ON observation.raw_assistance_transaction_id =
             raw.raw_assistance_transaction_id
        WHERE raw.load_batch_id = %s
        """,
        (batch_id,),
    )

    return int(cursor.fetchone()[0])


def validate_batch(cursor, batch_id, config):
    expected_year = config["fiscal_year"]

    raw_count = get_raw_count(cursor, batch_id)
    eligible_count = get_eligible_count(cursor, batch_id)

    require(
        raw_count == config["raw"],
        f"Batch {batch_id}: raw count changed: {raw_count}",
    )

    require(
        eligible_count == config["eligible"],
        f"Batch {batch_id}: eligible count changed: {eligible_count}",
    )

    require(
        raw_count - eligible_count == config["held"],
        f"Batch {batch_id}: held count mismatch",
    )

    require(
        check_existing_canonical(cursor, batch_id) == 0,
        f"Batch {batch_id}: canonical transaction already exists",
    )

    require(
        check_existing_links(cursor, batch_id) == 0,
        f"Batch {batch_id}: observation link already exists",
    )

    adapter = HistoricalExtractionCursor(
        cursor,
        eligible_count=eligible_count,
    )

    extracted_count, transactions = normalizer.extract_transactions(
        adapter,
        load_batch_id=batch_id,
    )

    require(
        extracted_count == eligible_count,
        f"Batch {batch_id}: extractor count mismatch",
    )

    require(
        len(transactions) == eligible_count,
        f"Batch {batch_id}: normalized count mismatch",
    )

    require(
        adapter.query_count == 2,
        f"Batch {batch_id}: unexpected extractor query count",
    )

    transaction_keys = set()
    raw_ids = set()
    batch_rows = set()

    missing_values = Counter()
    fiscal_years = Counter()

    ledger_columns = normalizer.LEDGER_COLUMNS

    require(
        len(ledger_columns) == 31,
        "Production ledger column count changed",
    )

    for transaction in transactions:
        require(
            transaction.load_batch_id == batch_id,
            "Unexpected transaction batch",
        )

        require(
            transaction.action_date_fiscal_year == expected_year,
            "Unexpected transaction fiscal year",
        )

        require(
            transaction.action_date is not None,
            "Missing transaction action date",
        )

        require(
            transaction.federal_action_obligation is not None,
            "Missing federal action obligation",
        )

        require(
            transaction.assistance_award_id > 0,
            "Missing canonical award reference",
        )

        require(
            transaction.assistance_listing_id > 0,
            "Missing assistance listing reference",
        )

        require(
            transaction.assistance_type_id > 0,
            "Missing assistance type reference",
        )

        key = transaction.assistance_transaction_unique_key
        raw_id = transaction.raw_assistance_transaction_id
        row_identity = (
            transaction.load_batch_id,
            transaction.source_row_number,
        )

        require(
            key and key.strip(),
            "Blank transaction key",
        )

        require(
            key not in transaction_keys,
            f"Duplicate transaction key: {key}",
        )

        require(
            raw_id not in raw_ids,
            f"Duplicate raw observation ID: {raw_id}",
        )

        require(
            row_identity not in batch_rows,
            f"Duplicate batch/source row: {row_identity}",
        )

        transaction_keys.add(key)
        raw_ids.add(raw_id)
        batch_rows.add(row_identity)

        values = normalizer.transaction_values(transaction)

        require(
            len(values) == len(ledger_columns),
            "Transaction value/column count mismatch",
        )

        for column, value in zip(ledger_columns, values):
            require(
                getattr(transaction, column) == value,
                f"Ledger mapping mismatch: {column}",
            )

            if value is None:
                missing_values[column] += 1

        fiscal_years[transaction.action_date_fiscal_year] += 1

    print()
    print(f"BATCH {batch_id} / FY{expected_year}")
    print("-" * 68)
    print(f"Raw observations             : {raw_count:,}")
    print(f"Eligible observations        : {eligible_count:,}")
    print(f"Held observations            : {raw_count - eligible_count:,}")
    print(f"Normalized transactions      : {len(transactions):,}")
    print(f"Distinct transaction keys    : {len(transaction_keys):,}")
    print(f"Distinct raw observation IDs : {len(raw_ids):,}")
    print(f"Distinct batch/row identities: {len(batch_rows):,}")
    print(f"Canonical insert columns     : {len(ledger_columns)}")
    print(f"Fiscal-year distribution     : {dict(fiscal_years)}")
    print(f"Existing canonical matches   : 0")
    print(f"Existing observation links   : 0")

    print()
    print("NULL COUNTS BY INSERT COLUMN")
    for column in ledger_columns:
        if missing_values[column]:
            print(
                f"  {column:<43} "
                f"{missing_values[column]:>9,}"
            )

    return {
        "raw": raw_count,
        "eligible": eligible_count,
        "held": raw_count - eligible_count,
        "normalized": len(transactions),
        "keys": transaction_keys,
        "raw_ids": raw_ids,
    }


def main():
    print("=" * 76)
    print("ETL-201Q STAGE D.4 - HISTORICAL NORMALIZATION DRY RUN")
    print("READ ONLY - NO DATABASE WRITES OR SEQUENCE CONSUMPTION")
    print("=" * 76)

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
            normalizer.validate_field_policy(cursor)

            print()
            print(
                "ANALYSIS-162-v1 field policy: PASS"
            )

            results = {}

            for batch_id, config in EXPECTED.items():
                results[batch_id] = validate_batch(
                    cursor,
                    batch_id,
                    config,
                )

            all_keys = set()
            all_raw_ids = set()

            for batch_id, result in results.items():
                require(
                    not all_keys.intersection(result["keys"]),
                    f"Cross-batch transaction key collision: {batch_id}",
                )

                require(
                    not all_raw_ids.intersection(result["raw_ids"]),
                    f"Cross-batch raw ID collision: {batch_id}",
                )

                all_keys.update(result["keys"])
                all_raw_ids.update(result["raw_ids"])

            total_raw = sum(r["raw"] for r in results.values())
            total_eligible = sum(
                r["eligible"] for r in results.values()
            )
            total_held = sum(r["held"] for r in results.values())
            total_normalized = sum(
                r["normalized"] for r in results.values()
            )

            require(total_raw == 208187, "Total raw mismatch")
            require(total_eligible == 207343, "Total eligible mismatch")
            require(total_held == 844, "Total held mismatch")
            require(
                total_normalized == 207343,
                "Total normalized mismatch",
            )
            require(
                len(all_keys) == 207343,
                "Global transaction-key uniqueness failure",
            )
            require(
                len(all_raw_ids) == 207343,
                "Global raw-observation uniqueness failure",
            )

            print()
            print("=" * 76)
            print("COMBINED ACCEPTANCE CONTROLS")
            print("=" * 76)
            print(f"Raw observations       : {total_raw:,}")
            print(f"Eligible observations  : {total_eligible:,}")
            print(f"Held observations      : {total_held:,}")
            print(f"Normalized transactions: {total_normalized:,}")
            print(f"Distinct keys          : {len(all_keys):,}")
            print(f"Distinct raw IDs       : {len(all_raw_ids):,}")

            print()
            print("ETL-201Q STAGE D.4: PASS")

    finally:
        connection.rollback()
        connection.close()

        print()
        print("ROLLBACK COMPLETE - CONNECTION CLOSED")
        print("NO PERMANENT DATABASE WRITES")


if __name__ == "__main__":
    main()
