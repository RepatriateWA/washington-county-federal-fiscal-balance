"""Populate Assistance award-recipient and recipient-parent history."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date

from psycopg2.extras import execute_values

from etl.common.db import get_connection
from etl.common.identity import (
    RecipientIdentityInput,
    classify_recipient_identity,
)
from etl.common.normalization.text import clean_optional_text


PAGE_SIZE = 1_000


@dataclass(frozen=True)
class HistoryObservation:
    """One raw Assistance recipient observation with resolved relationships."""

    load_batch_id: int
    source_row_number: int
    assistance_award_id: int
    assistance_transaction_id: int

    child_recipient_id: int
    child_identity_key: str

    action_date: date | None

    observed_parent_uei: str | None
    observed_parent_name: str | None
    parent_recipient_id: int | None

    selected_as_canonical_award_recipient: bool
    is_self_parent: bool


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate Assistance recipient relationship history "
            "for one raw load batch."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()


def parse_date(value: object) -> date | None:
    """Parse an optional ISO-style source date."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError as exc:
        raise ValueError(
            f"Invalid action_date value {value!r}."
        ) from exc


def load_recipient_lookup(
    cur,
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Load recipient lookups.

    Returns:
        recipient identity key -> recipient ID;
        uppercase UEI -> recipient ID.
    """

    cur.execute(
        """
        SELECT
            recipient_id,
            recipient_identity_key,
            recipient_uei
        FROM procurement.recipient;
        """
    )

    identity_lookup: dict[str, int] = {}
    uei_lookup: dict[str, int] = {}

    for recipient_id, identity_key, recipient_uei in cur.fetchall():
        recipient_id = int(recipient_id)

        if identity_key is not None:
            key = str(identity_key)

            if key in identity_lookup:
                raise ValueError(
                    f"Duplicate recipient identity key {key!r}."
                )

            identity_lookup[key] = recipient_id

        cleaned_uei = clean_optional_text(
            recipient_uei
        )

        if cleaned_uei is not None:
            key = cleaned_uei.upper()

            existing_id = uei_lookup.get(key)

            if (
                existing_id is not None
                and existing_id != recipient_id
            ):
                raise ValueError(
                    f"UEI {key!r} resolves to multiple "
                    "shared recipient rows."
                )

            uei_lookup[key] = recipient_id

    return identity_lookup, uei_lookup


def classify_child_identity(
    row: tuple[object, ...],
) -> str:
    """Recompute the child recipient identity from raw source attributes."""

    recipient_name = clean_optional_text(
        row[7]
    )

    if recipient_name is None:
        raise ValueError(
            f"Source row {row[0]} has no recipient_name."
        )

    identity = classify_recipient_identity(
        RecipientIdentityInput(
            recipient_name=recipient_name,
            recipient_uei=clean_optional_text(
                row[8]
            ),
            recipient_country_code=clean_optional_text(
                row[9]
            ),
            recipient_state_code=clean_optional_text(
                row[10]
            ),
            recipient_city_name=clean_optional_text(
                row[11]
            ),
            recipient_zip_code=clean_optional_text(
                row[12]
            ),
            recipient_address_line_1=clean_optional_text(
                row[13]
            ),
            business_types_code=clean_optional_text(
                row[14]
            ),
        )
    )

    return identity.identity_key


def extract_observations(
    cur,
    *,
    load_batch_id: int,
    identity_lookup: dict[str, int],
    uei_lookup: dict[str, int],
) -> tuple[int, list[HistoryObservation]]:
    """Extract all award-recipient and parent observations."""

    cur.execute(
        """
        SELECT
            raw.source_row_number,
            award.assistance_award_id,
            transaction.assistance_transaction_id,
            transaction.recipient_id,
            award.recipient_id AS canonical_award_recipient_id,
            raw.raw_record ->> 'action_date',

            raw.assistance_award_unique_key,

            raw.raw_record ->> 'recipient_name',
            raw.raw_record ->> 'recipient_uei',
            raw.raw_record ->> 'recipient_country_code',
            raw.raw_record ->> 'recipient_state_code',
            raw.raw_record ->> 'recipient_city_name',
            raw.raw_record ->> 'recipient_zip_code',
            raw.raw_record ->> 'recipient_address_line_1',
            raw.raw_record ->> 'business_types_code',

            raw.raw_record ->> 'recipient_parent_uei',
            raw.raw_record ->> 'recipient_parent_name'

        FROM assistance.raw_award_transaction AS raw

        JOIN assistance.award_transaction AS transaction
          ON transaction.load_batch_id = raw.load_batch_id
         AND transaction.source_row_number = raw.source_row_number

        JOIN assistance.award AS award
          ON award.assistance_award_id
             = transaction.assistance_award_id

        WHERE raw.load_batch_id = %s

        ORDER BY raw.source_row_number;
        """,
        (load_batch_id,),
    )

    rows = cur.fetchall()

    observations: list[HistoryObservation] = []

    for row in rows:
        source_row_number = int(row[0])
        child_identity_key = classify_child_identity(
            row
        )

        expected_child_id = identity_lookup.get(
            child_identity_key
        )

        if expected_child_id is None:
            raise ValueError(
                f"Source row {source_row_number:,} has unresolved "
                f"child identity {child_identity_key!r}."
            )

        transaction_recipient_id = int(row[3])

        if transaction_recipient_id != expected_child_id:
            raise ValueError(
                f"Source row {source_row_number:,} transaction "
                "recipient does not match recomputed identity."
            )

        canonical_award_recipient_id = int(
            row[4]
        )

        observed_parent_uei = clean_optional_text(
            row[15]
        )
        observed_parent_name = clean_optional_text(
            row[16]
        )

        parent_recipient_id: int | None = None

        if observed_parent_uei is not None:
            parent_recipient_id = uei_lookup.get(
                observed_parent_uei.upper()
            )

        is_self_parent = (
            observed_parent_uei is not None
            and clean_optional_text(row[8]) is not None
            and observed_parent_uei.upper()
            == clean_optional_text(row[8]).upper()
        )

        if (
            is_self_parent
            and parent_recipient_id is None
        ):
            parent_recipient_id = expected_child_id

        observations.append(
            HistoryObservation(
                load_batch_id=load_batch_id,
                source_row_number=source_row_number,
                assistance_award_id=int(row[1]),
                assistance_transaction_id=int(row[2]),
                child_recipient_id=expected_child_id,
                child_identity_key=child_identity_key,
                action_date=parse_date(row[5]),
                observed_parent_uei=observed_parent_uei,
                observed_parent_name=observed_parent_name,
                parent_recipient_id=parent_recipient_id,
                selected_as_canonical_award_recipient=(
                    expected_child_id
                    == canonical_award_recipient_id
                ),
                is_self_parent=is_self_parent,
            )
        )

    return len(rows), observations


def load_award_recipient_history(
    cur,
    observations: list[HistoryObservation],
) -> None:
    """Upsert one award-recipient history row per raw source row."""

    values = [
        (
            item.load_batch_id,
            item.source_row_number,
            item.assistance_award_id,
            item.assistance_transaction_id,
            item.child_recipient_id,
            item.action_date,
            item.child_identity_key,
            item.selected_as_canonical_award_recipient,
        )
        for item in observations
    ]

    execute_values(
        cur,
        """
        INSERT INTO assistance.award_recipient_history (
            load_batch_id,
            source_row_number,
            assistance_award_id,
            assistance_transaction_id,
            recipient_id,
            action_date,
            recipient_identity_key,
            selected_as_canonical_award_recipient
        )
        VALUES %s
        ON CONFLICT (
            load_batch_id,
            source_row_number
        )
        DO UPDATE SET
            assistance_award_id = EXCLUDED.assistance_award_id,
            assistance_transaction_id =
                EXCLUDED.assistance_transaction_id,
            recipient_id = EXCLUDED.recipient_id,
            action_date = EXCLUDED.action_date,
            recipient_identity_key =
                EXCLUDED.recipient_identity_key,
            selected_as_canonical_award_recipient =
                EXCLUDED.selected_as_canonical_award_recipient;
        """,
        values,
        page_size=PAGE_SIZE,
    )


def load_parent_history(
    cur,
    observations: list[HistoryObservation],
) -> int:
    """Upsert rows that contain an observed parent value."""

    parent_observations = [
        item
        for item in observations
        if (
            item.observed_parent_uei is not None
            or item.observed_parent_name is not None
        )
    ]

    if not parent_observations:
        return 0

    values = [
        (
            item.load_batch_id,
            item.source_row_number,
            item.child_recipient_id,
            item.parent_recipient_id,
            item.observed_parent_uei,
            item.observed_parent_name,
            item.action_date,
            item.is_self_parent,
        )
        for item in parent_observations
    ]

    execute_values(
        cur,
        """
        INSERT INTO assistance.recipient_parent_history (
            load_batch_id,
            source_row_number,
            child_recipient_id,
            parent_recipient_id,
            observed_parent_uei,
            observed_parent_name,
            action_date,
            is_self_parent
        )
        VALUES %s
        ON CONFLICT (
            load_batch_id,
            source_row_number
        )
        DO UPDATE SET
            child_recipient_id =
                EXCLUDED.child_recipient_id,
            parent_recipient_id =
                EXCLUDED.parent_recipient_id,
            observed_parent_uei =
                EXCLUDED.observed_parent_uei,
            observed_parent_name =
                EXCLUDED.observed_parent_name,
            action_date =
                EXCLUDED.action_date,
            is_self_parent =
                EXCLUDED.is_self_parent;
        """,
        values,
        page_size=PAGE_SIZE,
    )

    return len(parent_observations)


def validate_results(
    cur,
    *,
    load_batch_id: int,
    expected_award_history_count: int,
    expected_parent_history_count: int,
) -> dict[str, int]:
    """Validate recipient-history completeness and integrity."""

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_recipient_history
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    award_history_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.recipient_parent_history
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    parent_history_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_recipient_history AS history
        JOIN assistance.award AS award
          ON award.assistance_award_id
             = history.assistance_award_id
        WHERE history.load_batch_id = %s
          AND history.selected_as_canonical_award_recipient = TRUE
          AND history.recipient_id <> award.recipient_id;
        """,
        (load_batch_id,),
    )

    canonical_mismatch_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.recipient_parent_history
        WHERE load_batch_id = %s
          AND is_self_parent = TRUE
          AND parent_recipient_id
              IS DISTINCT FROM child_recipient_id;
        """,
        (load_batch_id,),
    )

    self_parent_mismatch_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.recipient_parent_history
        WHERE load_batch_id = %s
          AND parent_recipient_id IS NULL;
        """,
        (load_batch_id,),
    )

    unresolved_parent_count = int(
        cur.fetchone()[0]
    )

    if award_history_count != expected_award_history_count:
        raise ValueError(
            "Award-recipient history count mismatch: "
            f"expected={expected_award_history_count:,}, "
            f"stored={award_history_count:,}."
        )

    if parent_history_count != expected_parent_history_count:
        raise ValueError(
            "Recipient-parent history count mismatch: "
            f"expected={expected_parent_history_count:,}, "
            f"stored={parent_history_count:,}."
        )

    if canonical_mismatch_count:
        raise ValueError(
            f"{canonical_mismatch_count:,} canonical award-recipient "
            "history rows disagree with assistance.award."
        )

    if self_parent_mismatch_count:
        raise ValueError(
            f"{self_parent_mismatch_count:,} self-parent rows "
            "are internally inconsistent."
        )

    return {
        "award_history_count": award_history_count,
        "parent_history_count": parent_history_count,
        "canonical_mismatch_count": canonical_mismatch_count,
        "self_parent_mismatch_count": self_parent_mismatch_count,
        "unresolved_parent_count": unresolved_parent_count,
    }


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    print("=" * 72)
    print("ETL-005D.3 — Load Assistance Recipient History")
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            (
                identity_lookup,
                uei_lookup,
            ) = load_recipient_lookup(cur)

            (
                raw_row_count,
                observations,
            ) = extract_observations(
                cur,
                load_batch_id=args.load_batch_id,
                identity_lookup=identity_lookup,
                uei_lookup=uei_lookup,
            )

            load_award_recipient_history(
                cur,
                observations,
            )

            parent_observation_count = load_parent_history(
                cur,
                observations,
            )

            validation = validate_results(
                cur,
                load_batch_id=args.load_batch_id,
                expected_award_history_count=(
                    raw_row_count
                ),
                expected_parent_history_count=(
                    parent_observation_count
                ),
            )

        conn.commit()

        print()
        print("=" * 72)
        print("ETL-005D.3 SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Award-recipient history rows ... "
            f"{validation['award_history_count']:,}"
        )
        print(
            "Recipient-parent history rows .. "
            f"{validation['parent_history_count']:,}"
        )
        print(
            "Unresolved parent identities ... "
            f"{validation['unresolved_parent_count']:,}"
        )
        print(
            "Canonical recipient mismatches . "
            f"{validation['canonical_mismatch_count']:,}"
        )
        print(
            "Self-parent inconsistencies .... "
            f"{validation['self_parent_mismatch_count']:,}"
        )
        print(
            "Validation ..................... PASS"
        )
        print("=" * 72)
        print()
        print(
            "Assistance recipient history loaded successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance recipient history load failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()