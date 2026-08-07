"""Normalize USAspending Assistance transactions into the accounting ledger."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from etl.common.db import get_connection
from etl.common.normalization.text import clean_optional_text


@dataclass(frozen=True)
class NormalizedTransaction:
    """One normalized Assistance transaction."""

    load_batch_id: int
    source_row_number: int

    assistance_transaction_unique_key: str
    assistance_award_id: int

    modification_number: str | None

    action_date: date | None
    action_date_fiscal_year: int | None

    federal_action_obligation: Decimal | None

    total_obligated_amount: Decimal | None
    total_outlayed_amount_for_overall_award: Decimal | None

    indirect_cost_federal_share_amount: Decimal | None
    non_federal_funding_amount: Decimal | None
    total_non_federal_funding_amount: Decimal | None

    face_value_of_loan: Decimal | None
    original_loan_subsidy_cost: Decimal | None
    total_face_value_of_loan: Decimal | None
    total_loan_subsidy_cost: Decimal | None

    generated_pragmatic_obligations: Decimal | None

    covid_overall_award_obligation: Decimal | None
    covid_overall_award_outlay: Decimal | None

    iija_overall_award_obligation: Decimal | None
    iija_overall_award_outlay: Decimal | None

    disaster_emergency_fund_codes_raw: str | None

    assistance_listing_id: int
    assistance_type_id: int
    funding_opportunity_id: int | None

    transaction_description: str | None
    action_type_code: str | None
    record_type_code: str | None
    correction_delete_indicator_code: str | None

    usaspending_permalink: str | None
    initial_report_date: date | None
    last_modified_date: date | None


LEDGER_COLUMNS = (
    "load_batch_id",
    "source_row_number",
    "assistance_transaction_unique_key",
    "assistance_award_id",
    "modification_number",
    "action_date",
    "action_date_fiscal_year",
    "federal_action_obligation",
    "total_obligated_amount",
    "total_outlayed_amount_for_overall_award",
    "indirect_cost_federal_share_amount",
    "non_federal_funding_amount",
    "total_non_federal_funding_amount",
    "face_value_of_loan",
    "original_loan_subsidy_cost",
    "total_face_value_of_loan",
    "total_loan_subsidy_cost",
    "generated_pragmatic_obligations",
    "covid_overall_award_obligation",
    "covid_overall_award_outlay",
    "iija_overall_award_obligation",
    "iija_overall_award_outlay",
    "disaster_emergency_fund_codes_raw",
    "assistance_listing_id",
    "assistance_type_id",
    "funding_opportunity_id",
    "transaction_description",
    "action_type_code",
    "record_type_code",
    "correction_delete_indicator_code",
    "usaspending_permalink",
    "initial_report_date",
    "last_modified_date",
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize Assistance transactions from one raw "
            "USAspending Assistance load batch."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()


def parse_date(
    value: object,
    *,
    field_name: str,
    source_row_number: int,
) -> date | None:
    """Parse a source date without silently accepting malformed values."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError as exc:
        raise ValueError(
            f"Source row {source_row_number:,}: "
            f"invalid {field_name} value {value!r}."
        ) from exc


def parse_integer(
    value: object,
    *,
    field_name: str,
    source_row_number: int,
) -> int | None:
    """Parse an optional integer source field."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError(
            f"Source row {source_row_number:,}: "
            f"invalid {field_name} value {value!r}."
        ) from exc


def parse_decimal(
    value: object,
    *,
    field_name: str,
    source_row_number: int,
) -> Decimal | None:
    """Parse an exact monetary value."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    cleaned = cleaned.replace(",", "").replace("$", "")

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(
            f"Source row {source_row_number:,}: "
            f"invalid {field_name} value {value!r}."
        ) from exc


def extract_transactions(
    cur,
    *,
    load_batch_id: int,
) -> tuple[int, list[NormalizedTransaction]]:
    """Extract and resolve ledger-ready transactions."""

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    raw_row_count = int(cur.fetchone()[0])

    if raw_row_count == 0:
        raise ValueError(
            f"No raw Assistance rows found for load batch "
            f"{load_batch_id}."
        )

    cur.execute(
        """
        SELECT
            raw.load_batch_id,
            raw.source_row_number,
            raw.assistance_transaction_unique_key,

            award.assistance_award_id,

            raw.raw_record ->> 'modification_number',
            raw.raw_record ->> 'action_date',
            raw.raw_record ->> 'action_date_fiscal_year',

            raw.raw_record ->> 'federal_action_obligation',

            raw.raw_record ->> 'total_obligated_amount',
            raw.raw_record
                ->> 'total_outlayed_amount_for_overall_award',

            raw.raw_record
                ->> 'indirect_cost_federal_share_amount',
            raw.raw_record ->> 'non_federal_funding_amount',
            raw.raw_record
                ->> 'total_non_federal_funding_amount',

            raw.raw_record ->> 'face_value_of_loan',
            raw.raw_record ->> 'original_loan_subsidy_cost',
            raw.raw_record ->> 'total_face_value_of_loan',
            raw.raw_record ->> 'total_loan_subsidy_cost',

            raw.raw_record ->> 'generated_pragmatic_obligations',

            raw.raw_record
                ->> 'obligated_amount_from_COVID-19_'
                    'supplementals_for_overall_award',
            raw.raw_record
                ->> 'outlayed_amount_from_COVID-19_'
                    'supplementals_for_overall_award',

            raw.raw_record
                ->> 'obligated_amount_from_IIJA_'
                    'supplemental_for_overall_award',
            raw.raw_record
                ->> 'outlayed_amount_from_IIJA_'
                    'supplemental_for_overall_award',

            raw.raw_record
                ->> 'disaster_emergency_fund_codes_for_overall_award',

            listing.assistance_listing_id,
            assistance_type.assistance_type_id,
            opportunity.funding_opportunity_id,

            raw.raw_record ->> 'transaction_description',
            raw.raw_record ->> 'action_type_code',
            raw.raw_record ->> 'record_type_code',
            raw.raw_record
                ->> 'correction_delete_indicator_code',

            raw.raw_record ->> 'usaspending_permalink',
            raw.raw_record ->> 'initial_report_date',
            raw.raw_record ->> 'last_modified_date'

        FROM assistance.raw_award_transaction AS raw

        JOIN assistance.award AS award
          ON award.assistance_award_unique_key
             = raw.assistance_award_unique_key

        JOIN assistance.assistance_listing AS listing
          ON listing.cfda_number = BTRIM(
                raw.raw_record ->> 'cfda_number'
             )

        JOIN assistance.assistance_type AS assistance_type
          ON assistance_type.assistance_type_code = BTRIM(
                raw.raw_record ->> 'assistance_type_code'
             )

        LEFT JOIN assistance.funding_opportunity AS opportunity
          ON opportunity.funding_opportunity_number = NULLIF(
                BTRIM(
                    raw.raw_record
                    ->> 'funding_opportunity_number'
                ),
                ''
             )

        WHERE raw.load_batch_id = %s

        ORDER BY raw.source_row_number;
        """,
        (load_batch_id,),
    )

    transactions: list[NormalizedTransaction] = []

    for row in cur.fetchall():
        source_row_number = int(row[1])

        transactions.append(
            NormalizedTransaction(
                load_batch_id=int(row[0]),
                source_row_number=source_row_number,
                assistance_transaction_unique_key=str(row[2]),
                assistance_award_id=int(row[3]),

                modification_number=clean_optional_text(row[4]),

                action_date=parse_date(
                    row[5],
                    field_name="action_date",
                    source_row_number=source_row_number,
                ),
                action_date_fiscal_year=parse_integer(
                    row[6],
                    field_name="action_date_fiscal_year",
                    source_row_number=source_row_number,
                ),

                federal_action_obligation=parse_decimal(
                    row[7],
                    field_name="federal_action_obligation",
                    source_row_number=source_row_number,
                ),

                total_obligated_amount=parse_decimal(
                    row[8],
                    field_name="total_obligated_amount",
                    source_row_number=source_row_number,
                ),
                total_outlayed_amount_for_overall_award=parse_decimal(
                    row[9],
                    field_name=(
                        "total_outlayed_amount_for_overall_award"
                    ),
                    source_row_number=source_row_number,
                ),

                indirect_cost_federal_share_amount=parse_decimal(
                    row[10],
                    field_name=(
                        "indirect_cost_federal_share_amount"
                    ),
                    source_row_number=source_row_number,
                ),
                non_federal_funding_amount=parse_decimal(
                    row[11],
                    field_name="non_federal_funding_amount",
                    source_row_number=source_row_number,
                ),
                total_non_federal_funding_amount=parse_decimal(
                    row[12],
                    field_name=(
                        "total_non_federal_funding_amount"
                    ),
                    source_row_number=source_row_number,
                ),

                face_value_of_loan=parse_decimal(
                    row[13],
                    field_name="face_value_of_loan",
                    source_row_number=source_row_number,
                ),
                original_loan_subsidy_cost=parse_decimal(
                    row[14],
                    field_name="original_loan_subsidy_cost",
                    source_row_number=source_row_number,
                ),
                total_face_value_of_loan=parse_decimal(
                    row[15],
                    field_name="total_face_value_of_loan",
                    source_row_number=source_row_number,
                ),
                total_loan_subsidy_cost=parse_decimal(
                    row[16],
                    field_name="total_loan_subsidy_cost",
                    source_row_number=source_row_number,
                ),

                generated_pragmatic_obligations=parse_decimal(
                    row[17],
                    field_name="generated_pragmatic_obligations",
                    source_row_number=source_row_number,
                ),

                covid_overall_award_obligation=parse_decimal(
                    row[18],
                    field_name=(
                        "obligated_amount_from_COVID-19_"
                        "supplementals_for_overall_award"
                    ),
                    source_row_number=source_row_number,
                ),
                covid_overall_award_outlay=parse_decimal(
                    row[19],
                    field_name=(
                        "outlayed_amount_from_COVID-19_"
                        "supplementals_for_overall_award"
                    ),
                    source_row_number=source_row_number,
                ),

                iija_overall_award_obligation=parse_decimal(
                    row[20],
                    field_name=(
                        "obligated_amount_from_IIJA_"
                        "supplemental_for_overall_award"
                    ),
                    source_row_number=source_row_number,
                ),
                iija_overall_award_outlay=parse_decimal(
                    row[21],
                    field_name=(
                        "outlayed_amount_from_IIJA_"
                        "supplemental_for_overall_award"
                    ),
                    source_row_number=source_row_number,
                ),

                disaster_emergency_fund_codes_raw=clean_optional_text(
                    row[22]
                ),

                assistance_listing_id=int(row[23]),
                assistance_type_id=int(row[24]),
                funding_opportunity_id=(
                    int(row[25])
                    if row[25] is not None
                    else None
                ),

                transaction_description=clean_optional_text(row[26]),
                action_type_code=clean_optional_text(row[27]),
                record_type_code=clean_optional_text(row[28]),
                correction_delete_indicator_code=clean_optional_text(
                    row[29]
                ),

                usaspending_permalink=clean_optional_text(row[30]),
                initial_report_date=parse_date(
                    row[31],
                    field_name="initial_report_date",
                    source_row_number=source_row_number,
                ),
                last_modified_date=parse_date(
                    row[32],
                    field_name="last_modified_date",
                    source_row_number=source_row_number,
                ),
            )
        )

    if len(transactions) != raw_row_count:
        raise ValueError(
            "Transaction extraction failed to reconcile: "
            f"raw={raw_row_count:,}, "
            f"resolved={len(transactions):,}."
        )

    return raw_row_count, transactions


def transaction_values(
    transaction: NormalizedTransaction,
) -> tuple[Any, ...]:
    """Return ledger-column values in deterministic order."""

    return tuple(
        getattr(transaction, column)
        for column in LEDGER_COLUMNS
    )


def upsert_transactions(
    cur,
    transactions: list[NormalizedTransaction],
) -> tuple[int, int, int]:
    """
    Insert new transactions and verify existing transactions.

    Existing ledger rows are not updated. A changed source observation
    must be represented as a new USAspending transaction or explicitly
    investigated rather than silently overwriting the ledger.
    """

    inserted = 0
    unchanged = 0
    conflicts = 0

    selected_columns = ", ".join(LEDGER_COLUMNS)

    for transaction in transactions:
        proposed = transaction_values(transaction)

        cur.execute(
            f"""
            SELECT {selected_columns}
            FROM assistance.award_transaction
            WHERE assistance_transaction_unique_key = %s;
            """,
            (
                transaction
                .assistance_transaction_unique_key,
            ),
        )

        existing = cur.fetchone()

        if existing is None:
            placeholders = ", ".join(
                ["%s"] * len(LEDGER_COLUMNS)
            )

            cur.execute(
                f"""
                INSERT INTO assistance.award_transaction (
                    {selected_columns}
                )
                VALUES ({placeholders});
                """,
                proposed,
            )

            inserted += 1

        elif existing == proposed:
            unchanged += 1

        else:
            conflicts += 1

            raise ValueError(
                "Immutable ledger conflict for transaction "
                f"{transaction.assistance_transaction_unique_key!r} "
                f"at source row "
                f"{transaction.source_row_number:,}. "
                "The stored ledger row differs from the proposed "
                "normalized source observation."
            )

    return inserted, unchanged, conflicts


def validate_results(
    cur,
    *,
    load_batch_id: int,
    raw_row_count: int,
) -> dict[str, int]:
    """Run ledger acceptance checks."""

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    normalized_row_count = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT assistance_transaction_unique_key
            FROM assistance.award_transaction
            WHERE load_batch_id = %s
            GROUP BY assistance_transaction_unique_key
            HAVING COUNT(*) > 1
        ) AS duplicates;
        """,
        (load_batch_id,),
    )

    duplicate_key_count = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction AS transaction
        LEFT JOIN assistance.award AS award
          ON award.assistance_award_id
             = transaction.assistance_award_id
        WHERE transaction.load_batch_id = %s
          AND award.assistance_award_id IS NULL;
        """,
        (load_batch_id,),
    )

    orphan_award_count = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction
        WHERE load_batch_id = %s
          AND (
                assistance_transaction_unique_key IS NULL
             OR BTRIM(assistance_transaction_unique_key) = ''
          );
        """,
        (load_batch_id,),
    )

    blank_identity_count = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction
        WHERE load_batch_id <> %s
          AND assistance_transaction_unique_key IN (
              SELECT assistance_transaction_unique_key
              FROM assistance.raw_award_transaction
              WHERE load_batch_id = %s
          );
        """,
        (
            load_batch_id,
            load_batch_id,
        ),
    )

    cross_batch_identity_count = int(cur.fetchone()[0])

    if normalized_row_count != raw_row_count:
        raise ValueError(
            "Ledger row-count reconciliation failed: "
            f"raw={raw_row_count:,}, "
            f"normalized={normalized_row_count:,}."
        )

    if duplicate_key_count:
        raise ValueError(
            f"Ledger contains {duplicate_key_count:,} "
            "duplicate transaction-key groups."
        )

    if orphan_award_count:
        raise ValueError(
            f"Ledger contains {orphan_award_count:,} "
            "orphan award references."
        )

    if blank_identity_count:
        raise ValueError(
            f"Ledger contains {blank_identity_count:,} "
            "blank transaction identities."
        )

    if cross_batch_identity_count:
        raise ValueError(
            f"{cross_batch_identity_count:,} transaction identities "
            "are associated with another load batch."
        )

    return {
        "normalized_row_count": normalized_row_count,
        "duplicate_key_count": duplicate_key_count,
        "orphan_award_count": orphan_award_count,
        "blank_identity_count": blank_identity_count,
        "cross_batch_identity_count": cross_batch_identity_count,
    }


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    print("=" * 72)
    print("ETL-005C.5A — Normalize Assistance Transactions")
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            (
                raw_row_count,
                transactions,
            ) = extract_transactions(
                cur,
                load_batch_id=args.load_batch_id,
            )

            (
                inserted,
                unchanged,
                conflicts,
            ) = upsert_transactions(
                cur,
                transactions,
            )

            validation = validate_results(
                cur,
                load_batch_id=args.load_batch_id,
                raw_row_count=raw_row_count,
            )

        conn.commit()

        print()
        print("=" * 72)
        print("ETL-005C.5A SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Canonical transactions ......... "
            f"{validation['normalized_row_count']:,}"
        )
        print(
            "Transactions inserted .......... "
            f"{inserted:,}"
        )
        print(
            "Transactions unchanged ......... "
            f"{unchanged:,}"
        )
        print(
            "Immutable conflicts ............ "
            f"{conflicts:,}"
        )
        print(
            "Duplicate transaction keys ..... "
            f"{validation['duplicate_key_count']:,}"
        )
        print(
            "Orphan award references ........ "
            f"{validation['orphan_award_count']:,}"
        )
        print(
            "Blank transaction identities ... "
            f"{validation['blank_identity_count']:,}"
        )
        print(
            "Cross-batch identity conflicts . "
            f"{validation['cross_batch_identity_count']:,}"
        )
        print(
            "Validation ..................... PASS"
        )
        print("=" * 72)
        print()
        print(
            "Assistance transaction ledger completed "
            "successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance transaction normalization failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()