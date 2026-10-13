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

    raw_assistance_transaction_id: int
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


POLICY_VERSION = "ANALYSIS-162-v1"

FIRST_SEEN_PROVENANCE_COLUMNS = (
    "load_batch_id",
    "source_row_number",
)

# Hard gate: any difference in these fields means the repeated source
# observation no longer describes the same protected canonical fiscal event.
PROTECTED_STABLE_COLUMNS = (
    "assistance_transaction_unique_key",
    "assistance_award_id",
    "modification_number",
    "action_date",
    "action_date_fiscal_year",
    "federal_action_obligation",
    "face_value_of_loan",
    "original_loan_subsidy_cost",
    "generated_pragmatic_obligations",
    "assistance_listing_id",
    "assistance_type_id",
    "action_type_code",
)

# Economically meaningful transaction-associated values that USAspending can
# later correct while retaining the same transaction key. Differences are
# recorded explicitly and never silently overwritten.
REVISABLE_ECONOMIC_COLUMNS = (
    "indirect_cost_federal_share_amount",
    "non_federal_funding_amount",
)

# Cumulative/overall-award state repeated on transaction rows.
AWARD_SNAPSHOT_COLUMNS = (
    "total_obligated_amount",
    "total_outlayed_amount_for_overall_award",
    "total_non_federal_funding_amount",
    "total_face_value_of_loan",
    "total_loan_subsidy_cost",
    "covid_overall_award_obligation",
    "covid_overall_award_outlay",
    "iija_overall_award_obligation",
    "iija_overall_award_outlay",
    "disaster_emergency_fund_codes_raw",
)

# Award-related metadata that may legitimately be republished differently.
MUTABLE_AWARD_METADATA_COLUMNS = (
    "funding_opportunity_id",
)

# Source/publication metadata. Historical values remain immutable in the raw
# layer and are linked to the canonical transaction through ETL-161.
PUBLICATION_METADATA_COLUMNS = (
    "transaction_description",
    "record_type_code",
    "correction_delete_indicator_code",
    "usaspending_permalink",
    "initial_report_date",
    "last_modified_date",
)

FIELD_CLASS_COLUMNS = {
    "PROTECTED_STABLE": PROTECTED_STABLE_COLUMNS,
    "REVISABLE_ECONOMIC": REVISABLE_ECONOMIC_COLUMNS,
    "AWARD_SNAPSHOT": AWARD_SNAPSHOT_COLUMNS,
    "MUTABLE_AWARD_METADATA": MUTABLE_AWARD_METADATA_COLUMNS,
    "PUBLICATION_METADATA": PUBLICATION_METADATA_COLUMNS,
}

REVISION_CLASS_COLUMNS = {
    field_class: columns
    for field_class, columns in FIELD_CLASS_COLUMNS.items()
    if field_class != "PROTECTED_STABLE"
}

COMPARISON_COLUMNS = tuple(
    column
    for columns in FIELD_CLASS_COLUMNS.values()
    for column in columns
)

# Preserve the physical first-seen canonical row for backward compatibility.
# Later differences are represented in award_transaction_revision, not by
# overwriting assistance.award_transaction.
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
    expected_resolved_count: int | None = None,
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
            raw.raw_record ->> 'last_modified_date',

            raw.raw_assistance_transaction_id

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
                raw_assistance_transaction_id=int(row[33]),
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

    reconciliation_count = (
        raw_row_count
        if expected_resolved_count is None
        else expected_resolved_count
    )

    if expected_resolved_count is not None:
        if (
            type(expected_resolved_count) is not int
            or not 0 < expected_resolved_count <= raw_row_count
        ):
            raise ValueError(
                "Invalid expected resolved transaction count: "
                f"raw={raw_row_count:,}, "
                f"expected={expected_resolved_count!r}."
            )

    if len(transactions) != reconciliation_count:
        raise ValueError(
            "Transaction extraction failed to reconcile: "
            f"raw={raw_row_count:,}, "
            f"expected_resolved={reconciliation_count:,}, "
            f"resolved={len(transactions):,}."
        )

    return raw_row_count, transactions

def transaction_values(
    transaction: NormalizedTransaction,
) -> tuple[Any, ...]:
    """Return ledger insert values in deterministic order."""

    return tuple(
        getattr(transaction, column)
        for column in LEDGER_COLUMNS
    )


def comparison_values(
    transaction: NormalizedTransaction,
) -> dict[str, Any]:
    """Return all classified canonical-comparison values by field name."""

    return {
        column: getattr(transaction, column)
        for column in COMPARISON_COLUMNS
    }


def value_as_text(value: Any) -> str | None:
    """Serialize a comparison value deterministically for revision evidence."""

    if value is None:
        return None

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Decimal):
        return format(value, "f")

    return str(value)


def validate_field_policy(cur) -> None:
    """Refuse code/database policy drift before normalizing any rows."""

    expected = {
        column: field_class
        for field_class, columns in FIELD_CLASS_COLUMNS.items()
        for column in columns
    }

    cur.execute(
        """
        SELECT field_name, field_class, policy_version
        FROM assistance.transaction_field_policy
        WHERE field_name = ANY(%s);
        """,
        (list(expected),),
    )

    rows = cur.fetchall()

    observed = {
        str(field_name): (
            str(field_class),
            str(policy_version),
        )
        for field_name, field_class, policy_version in rows
    }

    missing = sorted(set(expected) - set(observed))

    mismatches = sorted(
        field_name
        for field_name, field_class in expected.items()
        if field_name in observed
        and observed[field_name] != (
            field_class,
            POLICY_VERSION,
        )
    )

    if missing or mismatches:
        raise ValueError(
            "ANALYSIS-162 field-policy validation failed. "
            f"Missing fields: {missing or 'none'}. "
            f"Mismatched fields: {mismatches or 'none'}."
        )


def link_transaction_observation(
    cur,
    *,
    transaction: NormalizedTransaction,
    assistance_transaction_id: int,
) -> None:
    """Link one immutable raw observation to its canonical transaction."""

    cur.execute(
        """
        INSERT INTO assistance.award_transaction_observation (
            raw_assistance_transaction_id,
            assistance_transaction_id
        )
        VALUES (%s, %s)
        ON CONFLICT (raw_assistance_transaction_id) DO NOTHING;
        """,
        (
            transaction.raw_assistance_transaction_id,
            assistance_transaction_id,
        ),
    )

    cur.execute(
        """
        SELECT assistance_transaction_id
        FROM assistance.award_transaction_observation
        WHERE raw_assistance_transaction_id = %s;
        """,
        (transaction.raw_assistance_transaction_id,),
    )

    linked = cur.fetchone()

    if linked is None:
        raise ValueError(
            "Failed to persist provenance link for raw Assistance "
            f"transaction {transaction.raw_assistance_transaction_id}."
        )

    linked_transaction_id = int(linked[0])

    if linked_transaction_id != assistance_transaction_id:
        raise ValueError(
            "Raw Assistance observation provenance conflict: "
            f"raw_assistance_transaction_id="
            f"{transaction.raw_assistance_transaction_id} is linked to "
            f"canonical transaction {linked_transaction_id}, but the "
            f"current normalization resolved it to "
            f"{assistance_transaction_id}."
        )


def record_revision(
    cur,
    *,
    transaction: NormalizedTransaction,
    assistance_transaction_id: int,
    field_name: str,
    revision_class: str,
    canonical_value: Any,
    observed_value: Any,
) -> None:
    """Persist one explicit source-observation difference idempotently."""

    canonical_text = value_as_text(canonical_value)
    observed_text = value_as_text(observed_value)

    cur.execute(
        """
        INSERT INTO assistance.award_transaction_revision (
            assistance_transaction_id,
            raw_assistance_transaction_id,
            field_name,
            revision_class,
            canonical_first_seen_value_text,
            observed_value_text,
            policy_version
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (
            raw_assistance_transaction_id,
            field_name
        ) DO NOTHING;
        """,
        (
            assistance_transaction_id,
            transaction.raw_assistance_transaction_id,
            field_name,
            revision_class,
            canonical_text,
            observed_text,
            POLICY_VERSION,
        ),
    )

    cur.execute(
        """
        SELECT
            assistance_transaction_id,
            revision_class,
            canonical_first_seen_value_text,
            observed_value_text,
            policy_version
        FROM assistance.award_transaction_revision
        WHERE raw_assistance_transaction_id = %s
          AND field_name = %s;
        """,
        (
            transaction.raw_assistance_transaction_id,
            field_name,
        ),
    )

    existing = cur.fetchone()

    expected = (
        assistance_transaction_id,
        revision_class,
        canonical_text,
        observed_text,
        POLICY_VERSION,
    )

    if existing != expected:
        raise ValueError(
            "Existing Assistance revision provenance does not match "
            f"the current normalization policy for raw observation "
            f"{transaction.raw_assistance_transaction_id}, "
            f"field {field_name!r}. "
            f"Stored={existing!r}; expected={expected!r}."
        )


def upsert_transactions(
    cur,
    transactions: list[NormalizedTransaction],
) -> dict[str, int]:
    """
    Insert new canonical transactions, link all raw observations, and record
    later source revisions without silently overwriting first-seen values.

    Protected stable differences remain hard failures.
    """

    counts = {
        "inserted": 0,
        "existing_no_difference": 0,
        "revised_transactions": 0,
        "revision_rows": 0,
        "revisable_economic_differences": 0,
        "award_snapshot_differences": 0,
        "mutable_award_metadata_differences": 0,
        "publication_metadata_differences": 0,
        "protected_conflicts": 0,
    }

    selected_columns = ", ".join(LEDGER_COLUMNS)
    comparison_columns = ", ".join(COMPARISON_COLUMNS)

    field_to_class = {
        column: field_class
        for field_class, columns in FIELD_CLASS_COLUMNS.items()
        for column in columns
    }

    for transaction in transactions:
        proposed = transaction_values(transaction)
        proposed_by_field = comparison_values(transaction)

        cur.execute(
            f"""
            SELECT
                assistance_transaction_id,
                {comparison_columns}
            FROM assistance.award_transaction
            WHERE assistance_transaction_unique_key = %s;
            """,
            (transaction.assistance_transaction_unique_key,),
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
                VALUES ({placeholders})
                RETURNING assistance_transaction_id;
                """,
                proposed,
            )

            assistance_transaction_id = int(cur.fetchone()[0])

            link_transaction_observation(
                cur,
                transaction=transaction,
                assistance_transaction_id=assistance_transaction_id,
            )

            counts["inserted"] += 1
            continue

        assistance_transaction_id = int(existing[0])

        canonical_by_field = dict(
            zip(
                COMPARISON_COLUMNS,
                existing[1:],
            )
        )

        protected_differences = [
            column
            for column in PROTECTED_STABLE_COLUMNS
            if canonical_by_field[column]
            != proposed_by_field[column]
        ]

        if protected_differences:
            counts["protected_conflicts"] += 1

            raise ValueError(
                "Protected stable transaction conflict for transaction "
                f"{transaction.assistance_transaction_unique_key!r} "
                f"at source row "
                f"{transaction.source_row_number:,}. "
                "Differing protected fields: "
                f"{', '.join(protected_differences)}."
            )

        link_transaction_observation(
            cur,
            transaction=transaction,
            assistance_transaction_id=assistance_transaction_id,
        )

        revision_fields = [
            column
            for column in COMPARISON_COLUMNS
            if column not in PROTECTED_STABLE_COLUMNS
            and canonical_by_field[column]
            != proposed_by_field[column]
        ]

        if not revision_fields:
            counts["existing_no_difference"] += 1
            continue

        counts["revised_transactions"] += 1

        for field_name in revision_fields:
            revision_class = field_to_class[field_name]

            record_revision(
                cur,
                transaction=transaction,
                assistance_transaction_id=assistance_transaction_id,
                field_name=field_name,
                revision_class=revision_class,
                canonical_value=canonical_by_field[field_name],
                observed_value=proposed_by_field[field_name],
            )

            counts["revision_rows"] += 1

            if revision_class == "REVISABLE_ECONOMIC":
                counts["revisable_economic_differences"] += 1
            elif revision_class == "AWARD_SNAPSHOT":
                counts["award_snapshot_differences"] += 1
            elif revision_class == "MUTABLE_AWARD_METADATA":
                counts["mutable_award_metadata_differences"] += 1
            elif revision_class == "PUBLICATION_METADATA":
                counts["publication_metadata_differences"] += 1
            else:
                raise ValueError(
                    f"Unhandled revision class {revision_class!r}."
                )

    return counts


def validate_results(
    cur,
    *,
    load_batch_id: int,
    raw_row_count: int,
) -> dict[str, int]:
    """Run ledger and provenance acceptance checks for one raw batch."""

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction_observation AS observation
        JOIN assistance.raw_award_transaction AS raw
          ON raw.raw_assistance_transaction_id
             = observation.raw_assistance_transaction_id
        WHERE raw.load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    normalized_row_count = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT transaction.assistance_transaction_unique_key
            FROM assistance.award_transaction_observation AS observation
            JOIN assistance.raw_award_transaction AS raw
              ON raw.raw_assistance_transaction_id
                 = observation.raw_assistance_transaction_id
            JOIN assistance.award_transaction AS transaction
              ON transaction.assistance_transaction_id
                 = observation.assistance_transaction_id
            WHERE raw.load_batch_id = %s
            GROUP BY transaction.assistance_transaction_unique_key
            HAVING COUNT(*) > 1
        ) AS duplicates;
        """,
        (load_batch_id,),
    )

    duplicate_key_count = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction_observation AS observation
        JOIN assistance.raw_award_transaction AS raw
          ON raw.raw_assistance_transaction_id
             = observation.raw_assistance_transaction_id
        JOIN assistance.award_transaction AS transaction
          ON transaction.assistance_transaction_id
             = observation.assistance_transaction_id
        LEFT JOIN assistance.award AS award
          ON award.assistance_award_id
             = transaction.assistance_award_id
        WHERE raw.load_batch_id = %s
          AND award.assistance_award_id IS NULL;
        """,
        (load_batch_id,),
    )

    orphan_award_count = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction_observation AS observation
        JOIN assistance.raw_award_transaction AS raw
          ON raw.raw_assistance_transaction_id
             = observation.raw_assistance_transaction_id
        JOIN assistance.award_transaction AS transaction
          ON transaction.assistance_transaction_id
             = observation.assistance_transaction_id
        WHERE raw.load_batch_id = %s
          AND (
                transaction.assistance_transaction_unique_key IS NULL
             OR BTRIM(transaction.assistance_transaction_unique_key) = ''
          );
        """,
        (load_batch_id,),
    )

    blank_identity_count = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction_observation AS observation
        JOIN assistance.raw_award_transaction AS raw
          ON raw.raw_assistance_transaction_id
             = observation.raw_assistance_transaction_id
        JOIN assistance.award_transaction AS transaction
          ON transaction.assistance_transaction_id
             = observation.assistance_transaction_id
        WHERE raw.load_batch_id = %s
          AND raw.assistance_transaction_unique_key
              IS DISTINCT FROM
              transaction.assistance_transaction_unique_key;
        """,
        (load_batch_id,),
    )

    provenance_identity_mismatch_count = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction_observation AS observation
        JOIN assistance.raw_award_transaction AS raw
          ON raw.raw_assistance_transaction_id
             = observation.raw_assistance_transaction_id
        JOIN assistance.award_transaction AS transaction
          ON transaction.assistance_transaction_id
             = observation.assistance_transaction_id
        WHERE raw.load_batch_id = %s
          AND transaction.load_batch_id <> %s;
        """,
        (
            load_batch_id,
            load_batch_id,
        ),
    )

    cross_batch_reobservation_count = int(cur.fetchone()[0])

    if normalized_row_count != raw_row_count:
        raise ValueError(
            "Transaction-observation reconciliation failed: "
            f"raw={raw_row_count:,}, "
            f"represented={normalized_row_count:,}."
        )

    if duplicate_key_count:
        raise ValueError(
            f"Batch contains {duplicate_key_count:,} duplicate "
            "canonical transaction-key groups after provenance linking."
        )

    if orphan_award_count:
        raise ValueError(
            f"Batch contains {orphan_award_count:,} "
            "orphan award references."
        )

    if blank_identity_count:
        raise ValueError(
            f"Batch contains {blank_identity_count:,} "
            "blank canonical transaction identities."
        )

    if provenance_identity_mismatch_count:
        raise ValueError(
            f"Batch contains {provenance_identity_mismatch_count:,} "
            "raw-to-canonical transaction identity mismatches."
        )

    return {
        "normalized_row_count": normalized_row_count,
        "duplicate_key_count": duplicate_key_count,
        "orphan_award_count": orphan_award_count,
        "blank_identity_count": blank_identity_count,
        "provenance_identity_mismatch_count": (
            provenance_identity_mismatch_count
        ),
        "cross_batch_reobservation_count": (
            cross_batch_reobservation_count
        ),
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
            validate_field_policy(cur)

            (
                raw_row_count,
                transactions,
            ) = extract_transactions(
                cur,
                load_batch_id=args.load_batch_id,
            )

            normalization = upsert_transactions(
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
            "Transactions represented ....... "
            f"{validation['normalized_row_count']:,}"
        )
        print(
            "Transactions inserted .......... "
            f"{normalization['inserted']:,}"
        )
        print(
            "Existing/no differences ........ "
            f"{normalization['existing_no_difference']:,}"
        )
        print(
            "Revised transactions observed .. "
            f"{normalization['revised_transactions']:,}"
        )
        print(
            "Revision rows recorded ......... "
            f"{normalization['revision_rows']:,}"
        )
        print(
            "  Revisable economic ........... "
            f"{normalization['revisable_economic_differences']:,}"
        )
        print(
            "  Award snapshot ............... "
            f"{normalization['award_snapshot_differences']:,}"
        )
        print(
            "  Mutable award metadata ....... "
            f"{normalization['mutable_award_metadata_differences']:,}"
        )
        print(
            "  Publication metadata ......... "
            f"{normalization['publication_metadata_differences']:,}"
        )
        print(
            "Protected stable conflicts ..... "
            f"{normalization['protected_conflicts']:,}"
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
            "Provenance identity mismatches . "
            f"{validation['provenance_identity_mismatch_count']:,}"
        )
        print(
            "Cross-batch re-observations .... "
            f"{validation['cross_batch_reobservation_count']:,}"
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
