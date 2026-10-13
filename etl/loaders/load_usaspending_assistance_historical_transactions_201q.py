
"""
ETL-201Q Stage E.2A
FY2018-FY2019 Historical Assistance Transaction Loader v0.1

STATUS: PREFLIGHT ONLY
PERMANENT INSERTION NOT AUTHORIZED.

--preflight: read-only validation
--commit:    deliberately disabled

No DDL, DML, COMMIT, or sequence consumption.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import psycopg2


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

normalizer = importlib.import_module(
    "etl.loaders.normalize_usaspending_assistance_transactions"
)

d4 = importlib.import_module(
    "etl.validation.assistance."
    "201q_d4_validate_historical_transactions"
)


EXPECTED = {
    20: {"year": 2018, "raw": 100849, "eligible": 100426, "held": 423},
    21: {"year": 2019, "raw": 107338, "eligible": 106917, "held": 421},
}

BASELINE_TRANSACTIONS = 1025707
BASELINE_OBSERVATIONS = 1490830

EXPECTED_TOTAL = 207343
EXPECTED_HELD = 844


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def scalar(cursor, sql, params=None):
    cursor.execute(sql, params)
    return int(cursor.fetchone()[0])


def verify_preservation_baseline(cursor):
    transaction_count = scalar(
        cursor,
        "SELECT COUNT(*) FROM assistance.award_transaction"
    )

    observation_count = scalar(
        cursor,
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction_observation
        """
    )

    require(
        transaction_count == BASELINE_TRANSACTIONS,
        "Canonical transaction baseline changed: "
        f"{transaction_count:,}"
    )

    require(
        observation_count == BASELINE_OBSERVATIONS,
        "Observation provenance baseline changed: "
        f"{observation_count:,}"
    )

    print(
        "Existing canonical transactions : "
        f"{transaction_count:,}"
    )
    print(
        "Existing observation links      : "
        f"{observation_count:,}"
    )


def verify_batch_registry(cursor, batch_id, config):
    cursor.execute(
        """
        SELECT
            fiscal_year_start,
            fiscal_year_end,
            source_record_count,
            loaded_record_count,
            rejected_record_count,
            load_status
        FROM procurement.load_batch
        WHERE load_batch_id = %s
        """,
        (batch_id,),
    )

    row = cursor.fetchone()

    require(row is not None, f"Missing batch {batch_id}")

    (
        fiscal_year_start,
        fiscal_year_end,
        source_count,
        loaded_count,
        rejected_count,
        status,
    ) = row

    require(
        fiscal_year_start == config["year"]
        and fiscal_year_end == config["year"],
        f"Batch {batch_id}: fiscal-year registry mismatch"
    )

    require(
        source_count == config["raw"]
        and loaded_count == config["raw"]
        and rejected_count == 0,
        f"Batch {batch_id}: source-count registry mismatch"
    )

    require(
        status == "COMPLETED",
        f"Batch {batch_id}: load status is {status!r}"
    )


def verify_batch_population(cursor, batch_id, config):
    raw_count = d4.get_raw_count(cursor, batch_id)
    eligible_count = d4.get_eligible_count(cursor, batch_id)

    require(
        raw_count == config["raw"],
        f"Batch {batch_id}: raw count changed"
    )

    require(
        eligible_count == config["eligible"],
        f"Batch {batch_id}: eligible count changed"
    )

    require(
        raw_count - eligible_count == config["held"],
        f"Batch {batch_id}: held count changed"
    )

    require(
        d4.check_existing_canonical(cursor, batch_id) == 0,
        f"Batch {batch_id}: existing canonical collision"
    )

    require(
        d4.check_existing_links(cursor, batch_id) == 0,
        f"Batch {batch_id}: existing observation link"
    )

    batch_row_collisions = scalar(
        cursor,
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction raw
        JOIN assistance.award_transaction transaction
          ON transaction.load_batch_id = raw.load_batch_id
         AND transaction.source_row_number =
             raw.source_row_number
        WHERE raw.load_batch_id = %s
        """,
        (batch_id,),
    )

    require(
        batch_row_collisions == 0,
        f"Batch {batch_id}: existing batch/row collision"
    )

    return eligible_count

def normalize_batch(cursor, batch_id, config, eligible_count):
    extracted_count, transactions = (
        normalizer.extract_transactions(
            cursor,
            load_batch_id=batch_id,
            expected_resolved_count=eligible_count,
        )
    )

    require(
        extracted_count == config["raw"],
        f"Batch {batch_id}: raw count mismatch"
    )

    require(
        len(transactions) == eligible_count,
        f"Batch {batch_id}: normalized count mismatch"
    )

    keys = set()
    raw_ids = set()
    row_numbers = set()

    for transaction in transactions:
        require(
            transaction.load_batch_id == batch_id,
            "Normalized batch mismatch"
        )

        require(
            transaction.action_date_fiscal_year == config["year"],
            "Normalized fiscal-year mismatch"
        )

        require(
            transaction.action_date is not None,
            "Missing action date"
        )

        require(
            transaction.federal_action_obligation is not None,
            "Missing federal action obligation"
        )

        require(
            transaction.assistance_award_id is not None
            and transaction.assistance_award_id > 0,
            "Missing canonical award"
        )

        require(
            transaction.assistance_listing_id is not None
            and transaction.assistance_type_id is not None,
            "Missing required classification reference"
        )

        key = transaction.assistance_transaction_unique_key
        raw_id = transaction.raw_assistance_transaction_id
        row_number = transaction.source_row_number

        require(
            key is not None and bool(key.strip()),
            "Blank transaction key"
        )

        require(key not in keys, "Duplicate transaction key")
        require(raw_id not in raw_ids, "Duplicate raw ID")
        require(
            row_number not in row_numbers,
            "Duplicate source row"
        )

        keys.add(key)
        raw_ids.add(raw_id)
        row_numbers.add(row_number)

        values = normalizer.transaction_values(transaction)

        require(
            len(values) == len(normalizer.LEDGER_COLUMNS) == 31,
            "Unexpected production insert mapping"
        )

    print(
        f"Batch {batch_id} / FY{config['year']}: "
        f"{len(transactions):,} normalized; "
        f"{config['held']:,} held"
    )

    return keys, raw_ids


def preflight():
    print("=" * 76)
    print("ETL-201Q STAGE E.2A - HISTORICAL INSERT-ONLY LOADER")
    print("PREFLIGHT ONLY - NO PERMANENT INSERTION AUTHORIZED")
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
            cursor.execute(
                "SET LOCAL statement_timeout = '600s'"
            )

            require(
                normalizer.POLICY_VERSION == "ANALYSIS-162-v1",
                "Production normalization policy changed"
            )

            normalizer.validate_field_policy(cursor)

            print()
            print("ANALYSIS-162-v1 field policy: PASS")

            verify_preservation_baseline(cursor)

            all_keys = set()
            all_raw_ids = set()

            total_normalized = 0
            total_held = 0

            for batch_id, config in EXPECTED.items():
                verify_batch_registry(
                    cursor, batch_id, config
                )

                eligible_count = verify_batch_population(
                    cursor, batch_id, config
                )

                keys, raw_ids = normalize_batch(
                    cursor,
                    batch_id,
                    config,
                    eligible_count,
                )

                require(
                    all_keys.isdisjoint(keys),
                    "Cross-batch transaction key collision"
                )

                require(
                    all_raw_ids.isdisjoint(raw_ids),
                    "Cross-batch raw observation collision"
                )

                all_keys.update(keys)
                all_raw_ids.update(raw_ids)

                total_normalized += len(keys)
                total_held += config["held"]

            require(
                total_normalized == EXPECTED_TOTAL,
                "Combined normalized count mismatch"
            )

            require(
                total_held == EXPECTED_HELD,
                "Combined held count mismatch"
            )

            require(
                len(all_keys) == EXPECTED_TOTAL,
                "Global transaction uniqueness failure"
            )

            require(
                len(all_raw_ids) == EXPECTED_TOTAL,
                "Global raw-observation uniqueness failure"
            )

            print()
            print("=" * 76)
            print("FINAL PREFLIGHT ACCEPTANCE")
            print("=" * 76)
            print(
                f"Eligible normalized transactions: "
                f"{total_normalized:,}"
            )
            print(
                f"Held unresolved observations    : "
                f"{total_held:,}"
            )
            print(
                f"Distinct transaction keys      : "
                f"{len(all_keys):,}"
            )
            print(
                f"Distinct raw observation IDs   : "
                f"{len(all_raw_ids):,}"
            )

            print()
            print("STAGE E.2A PREFLIGHT: PASS")
            print("PERMANENT INSERTION: NOT AUTHORIZED")

    finally:
        connection.rollback()
        connection.close()

        print()
        print("ROLLBACK COMPLETE - CONNECTION CLOSED")
        print("NO PERMANENT DATABASE WRITES")
        print("NO PRODUCTION SEQUENCE CONSUMPTION")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "ETL-201Q historical assistance loader "
            "(preflight-only version)"
        )
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--preflight",
        action="store_true",
        help="Perform read-only validation (default)",
    )

    mode.add_argument(
        "--commit",
        action="store_true",
        help="Reserved; permanent insertion is not authorized",
    )

    args = parser.parse_args()

    if args.commit:
        print(
            "REFUSED: --commit is disabled in Stage E.2A v0.1.",
            file=sys.stderr,
        )
        print(
            "No database connection opened.",
            file=sys.stderr,
        )
        return 2

    preflight()
    return 0


if __name__ == "__main__":
    sys.exit(main())
