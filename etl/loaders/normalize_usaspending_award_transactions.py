"""
ETL-004A.3B — Normalize USAspending award transactions.

Reads immutable rows from procurement.raw_award_transaction, resolves each
row to a normalized procurement.award, derives federal fiscal periods, and
upserts transaction facts into procurement.award_transaction.

Usage:
    python -m etl.loaders.normalize_usaspending_award_transactions

Optional explicit batch:
    python -m etl.loaders.normalize_usaspending_award_transactions \
        --load-batch-id 2
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from psycopg2.extras import execute_values

from etl.common.db import get_connection
from etl.common.usaspending import (
    get_optional,
    get_required,
    parse_date,
    parse_decimal,
)


@dataclass(frozen=True)
class RawObservation:
    source_row_number: int
    raw_record: dict[str, Any]


@dataclass(frozen=True)
class TransactionFact:
    usaspending_transaction_id: str
    award_id: int
    load_batch_id: int
    action_date: date
    fiscal_year: int
    fiscal_quarter: int
    modification_number: str | None
    federal_action_obligation: Decimal
    current_total_value: Decimal | None
    potential_total_value: Decimal | None
    transaction_description: str | None
    naics_code: str | None
    psc_code: str | None
    source_file: str
    source_row_number: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize USAspending award transaction facts."
    )
    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=None,
        help=(
            "Raw procurement load batch to normalize. Defaults to the latest "
            "completed batch containing raw observations."
        ),
    )
    return parser.parse_args()


def get_target_batch(
    conn,
    requested_batch_id: int | None,
) -> tuple[int, str]:
    """Return a completed raw load batch and its source filename."""
    with conn.cursor() as cur:
        if requested_batch_id is not None:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id) AS raw_row_count
                FROM procurement.load_batch lb
                LEFT JOIN procurement.raw_award_transaction raw
                    ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_batch_id = %s
                GROUP BY
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status;
                """,
                (requested_batch_id,),
            )
        else:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id) AS raw_row_count
                FROM procurement.load_batch lb
                JOIN procurement.raw_award_transaction raw
                    ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_status IN (
                    'COMPLETED',
                    'COMPLETED_WITH_REJECTIONS'
                )
                GROUP BY
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status
                ORDER BY lb.load_batch_id DESC
                LIMIT 1;
                """
            )

        row = cur.fetchone()

    if row is None:
        if requested_batch_id is None:
            raise ValueError(
                "No completed procurement batch containing raw rows was found."
            )
        raise ValueError(f"Load batch {requested_batch_id} does not exist.")

    load_batch_id, source_file, load_status, raw_row_count = row

    if load_status not in {"COMPLETED", "COMPLETED_WITH_REJECTIONS"}:
        raise ValueError(
            f"Load batch {load_batch_id} has status {load_status!r}; "
            "a completed batch is required."
        )

    if int(raw_row_count) == 0:
        raise ValueError(f"Load batch {load_batch_id} contains no raw rows.")

    return int(load_batch_id), str(source_file)


def read_raw_observations(
    conn,
    load_batch_id: int,
) -> list[RawObservation]:
    """Read raw observations in deterministic source-row order."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                source_row_number,
                raw_record
            FROM procurement.raw_award_transaction
            WHERE load_batch_id = %s
            ORDER BY
                source_row_number,
                raw_award_transaction_id;
            """,
            (load_batch_id,),
        )
        rows = cur.fetchall()

    return [
        RawObservation(
            source_row_number=int(source_row_number),
            raw_record=raw_record,
        )
        for source_row_number, raw_record in rows
    ]


def build_award_lookup(conn) -> dict[str, int]:
    """Map USAspending award keys to normalized award surrogate keys."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                generated_unique_award_id,
                award_id
            FROM procurement.award;
            """
        )
        rows = cur.fetchall()

    lookup = {
        str(generated_unique_award_id): int(award_id)
        for generated_unique_award_id, award_id in rows
    }

    if not lookup:
        raise ValueError(
            "procurement.award is empty. Run award normalization first."
        )

    return lookup


def fiscal_year_for(action_date: date) -> int:
    """Return the U.S. federal fiscal year for a calendar date."""
    return action_date.year + 1 if action_date.month >= 10 else action_date.year


def fiscal_quarter_for(action_date: date) -> int:
    """Return the U.S. federal fiscal quarter for a calendar date."""
    month = action_date.month
    if month >= 10:
        return 1
    if month <= 3:
        return 2
    if month <= 6:
        return 3
    return 4


def normalize_code(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def derive_transaction_facts(
    *,
    observations: list[RawObservation],
    award_lookup: dict[str, int],
    load_batch_id: int,
    source_file: str,
) -> list[TransactionFact]:
    """Convert raw observations into validated normalized transaction facts."""
    facts: list[TransactionFact] = []
    seen_transaction_ids: set[str] = set()

    for observation in observations:
        row_number = observation.source_row_number
        record = observation.raw_record

        transaction_id = get_required(record, "TRANSACTION_KEY")
        award_key = get_required(record, "AWARD_KEY")

        if transaction_id in seen_transaction_ids:
            raise ValueError(
                f"Duplicate transaction ID {transaction_id!r} "
                f"in raw batch {load_batch_id}."
            )
        seen_transaction_ids.add(transaction_id)

        award_id = award_lookup.get(award_key)
        if award_id is None:
            raise ValueError(
                f"Could not resolve award key {award_key!r} "
                f"at source row {row_number}."
            )

        action_date = parse_date(
            get_required(record, "ACTION_DATE")
        )
        obligation = parse_decimal(
            get_required(record, "FEDERAL_ACTION_OBLIGATION")
        )

        if action_date is None:
            raise ValueError(
                f"Missing or invalid action date at source row {row_number}."
            )
        if obligation is None:
            raise ValueError(
                f"Missing or invalid obligation at source row {row_number}."
            )

        current_total_value = parse_decimal(
            get_optional(record, "CURRENT_TOTAL_VALUE")
        )
        potential_total_value = parse_decimal(
            get_optional(record, "POTENTIAL_TOTAL_VALUE")
        )

        facts.append(
            TransactionFact(
                usaspending_transaction_id=transaction_id,
                award_id=award_id,
                load_batch_id=load_batch_id,
                action_date=action_date,
                fiscal_year=fiscal_year_for(action_date),
                fiscal_quarter=fiscal_quarter_for(action_date),
                modification_number=get_optional(
                    record,
                    "MODIFICATION_NUMBER",
                ),
                federal_action_obligation=obligation,
                current_total_value=current_total_value,
                potential_total_value=potential_total_value,
                transaction_description=get_optional(
                    record,
                    "TRANSACTION_DESCRIPTION",
                ),
                naics_code=normalize_code(
                    get_optional(record, "NAICS")
                ),
                psc_code=normalize_code(
                    get_optional(record, "PSC")
                ),
                source_file=source_file,
                source_row_number=row_number,
            )
        )

    return facts


def validate_reference_codes(
    conn,
    facts: list[TransactionFact],
) -> None:
    """Ensure all non-null NAICS and PSC values satisfy foreign keys."""
    required_naics = {
        fact.naics_code for fact in facts if fact.naics_code is not None
    }
    required_psc = {
        fact.psc_code for fact in facts if fact.psc_code is not None
    }

    with conn.cursor() as cur:
        loaded_naics: set[str] = set()
        loaded_psc: set[str] = set()

        if required_naics:
            cur.execute(
                """
                SELECT naics_code
                FROM procurement.naics
                WHERE naics_code = ANY(%s);
                """,
                (list(required_naics),),
            )
            loaded_naics = {row[0] for row in cur.fetchall()}

        if required_psc:
            cur.execute(
                """
                SELECT psc_code
                FROM procurement.psc
                WHERE psc_code = ANY(%s);
                """,
                (list(required_psc),),
            )
            loaded_psc = {row[0] for row in cur.fetchall()}

    missing_naics = required_naics - loaded_naics
    missing_psc = required_psc - loaded_psc

    if missing_naics:
        raise ValueError(
            "Missing procurement.naics rows for: "
            + ", ".join(sorted(missing_naics))
        )
    if missing_psc:
        raise ValueError(
            "Missing procurement.psc rows for: "
            + ", ".join(sorted(missing_psc))
        )


def upsert_transaction_facts(
    conn,
    facts: list[TransactionFact],
) -> int:
    """Insert or update normalized transaction facts idempotently."""
    sql = """
        INSERT INTO procurement.award_transaction (
            usaspending_transaction_id,
            award_id,
            load_batch_id,
            action_date,
            fiscal_year,
            fiscal_quarter,
            modification_number,
            federal_action_obligation,
            current_total_value,
            potential_total_value,
            transaction_description,
            naics_code,
            psc_code,
            source_file,
            source_row_number
        )
        VALUES %s
        ON CONFLICT (usaspending_transaction_id)
        DO UPDATE SET
            award_id = EXCLUDED.award_id,
            load_batch_id = EXCLUDED.load_batch_id,
            action_date = EXCLUDED.action_date,
            fiscal_year = EXCLUDED.fiscal_year,
            fiscal_quarter = EXCLUDED.fiscal_quarter,
            modification_number = EXCLUDED.modification_number,
            federal_action_obligation =
                EXCLUDED.federal_action_obligation,
            current_total_value = EXCLUDED.current_total_value,
            potential_total_value = EXCLUDED.potential_total_value,
            transaction_description =
                EXCLUDED.transaction_description,
            naics_code = EXCLUDED.naics_code,
            psc_code = EXCLUDED.psc_code,
            source_file = EXCLUDED.source_file,
            source_row_number = EXCLUDED.source_row_number;
    """

    values = [
        (
            fact.usaspending_transaction_id,
            fact.award_id,
            fact.load_batch_id,
            fact.action_date,
            fact.fiscal_year,
            fact.fiscal_quarter,
            fact.modification_number,
            fact.federal_action_obligation,
            fact.current_total_value,
            fact.potential_total_value,
            fact.transaction_description,
            fact.naics_code,
            fact.psc_code,
            fact.source_file,
            fact.source_row_number,
        )
        for fact in facts
    ]

    with conn.cursor() as cur:
        execute_values(
            cur,
            sql,
            values,
            page_size=500,
        )

    return len(values)


def validate_loaded_facts(
    conn,
    *,
    load_batch_id: int,
    expected_facts: list[TransactionFact],
) -> None:
    """Reconcile source-derived facts to the normalized table."""
    expected_ids = {
        fact.usaspending_transaction_id for fact in expected_facts
    }

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                usaspending_transaction_id,
                award_id,
                action_date,
                fiscal_year,
                fiscal_quarter,
                federal_action_obligation,
                source_file,
                source_row_number
            FROM procurement.award_transaction
            WHERE load_batch_id = %s;
            """,
            (load_batch_id,),
        )
        loaded_rows = cur.fetchall()

        cur.execute(
            """
            SELECT COUNT(*)
            FROM procurement.award_transaction tx
            LEFT JOIN procurement.award aw
                ON aw.award_id = tx.award_id
            WHERE tx.load_batch_id = %s
              AND aw.award_id IS NULL;
            """,
            (load_batch_id,),
        )
        orphan_count = int(cur.fetchone()[0])

    loaded_ids = {str(row[0]) for row in loaded_rows}

    missing_ids = expected_ids - loaded_ids
    unexpected_ids = loaded_ids - expected_ids

    if missing_ids:
        raise ValueError(
            f"{len(missing_ids)} expected transactions were not loaded."
        )
    if unexpected_ids:
        raise ValueError(
            f"{len(unexpected_ids)} unexpected transactions exist "
            f"for load batch {load_batch_id}."
        )
    if len(loaded_rows) != len(expected_facts):
        raise ValueError(
            "Transaction row-count reconciliation failed: "
            f"expected {len(expected_facts)}, found {len(loaded_rows)}."
        )
    if orphan_count:
        raise ValueError(
            f"Found {orphan_count} award transactions without a valid award."
        )

    for (
        transaction_id,
        _award_id,
        action_date,
        fiscal_year,
        fiscal_quarter,
        _obligation,
        _source_file,
        source_row_number,
    ) in loaded_rows:
        expected_fy = fiscal_year_for(action_date)
        expected_fq = fiscal_quarter_for(action_date)

        if fiscal_year != expected_fy or fiscal_quarter != expected_fq:
            raise ValueError(
                f"Fiscal-period mismatch for transaction "
                f"{transaction_id!r}, source row {source_row_number}."
            )


def main() -> None:
    args = parse_arguments()

    print("=" * 72)
    print("ETL-004A.3B — Normalize USAspending Award Transactions")
    print("=" * 72)

    conn = get_connection()

    try:
        load_batch_id, source_file = get_target_batch(
            conn,
            args.load_batch_id,
        )
        print(f"Target raw load batch: {load_batch_id}")
        print(f"Source file: {source_file}")

        observations = read_raw_observations(
            conn,
            load_batch_id,
        )
        print(f"Raw observations read: {len(observations):,}")

        award_lookup = build_award_lookup(conn)
        print(f"Normalized awards available: {len(award_lookup):,}")

        facts = derive_transaction_facts(
            observations=observations,
            award_lookup=award_lookup,
            load_batch_id=load_batch_id,
            source_file=source_file,
        )
        print(f"Transaction facts derived: {len(facts):,}")

        validate_reference_codes(conn, facts)
        print("Classification foreign-key validation: PASS")

        affected_rows = upsert_transaction_facts(conn, facts)
        print(f"Transaction facts upserted: {affected_rows:,}")

        validate_loaded_facts(
            conn,
            load_batch_id=load_batch_id,
            expected_facts=facts,
        )
        print("Transaction reconciliation: PASS")

        conn.commit()

        print()
        print("ETL-004A.3B completed successfully.")

    except Exception as exc:
        conn.rollback()
        print()
        print("ETL-004A.3B failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()