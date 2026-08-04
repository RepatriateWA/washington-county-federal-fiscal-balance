"""Persist observed award-to-recipient relationships."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AwardRecipientRelationship:
    """One observed award-recipient relationship in a load batch."""

    award_id: int
    recipient_id: int
    recipient_uei: str | None
    observed_recipient_name: str | None
    occurrence_count: int
    first_action_date: date | None
    last_action_date: date | None
    first_source_row_number: int
    last_source_row_number: int


class AwardRecipientRelationshipRecorder:
    """Persist award-recipient relationships idempotently."""

    def record(
        self,
        conn,
        *,
        load_batch_id: int,
        relationships: list[AwardRecipientRelationship],
    ) -> int:
        """Upsert all observed relationships for one load batch."""

        sql = """
            INSERT INTO procurement.award_recipient_relationship (
                load_batch_id,
                award_id,
                recipient_id,
                recipient_uei,
                observed_recipient_name,
                occurrence_count,
                first_action_date,
                last_action_date,
                first_source_row_number,
                last_source_row_number
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (
                load_batch_id,
                award_id,
                recipient_id
            )
            DO UPDATE SET
                recipient_uei =
                    EXCLUDED.recipient_uei,
                observed_recipient_name =
                    EXCLUDED.observed_recipient_name,
                occurrence_count =
                    EXCLUDED.occurrence_count,
                first_action_date =
                    EXCLUDED.first_action_date,
                last_action_date =
                    EXCLUDED.last_action_date,
                first_source_row_number =
                    EXCLUDED.first_source_row_number,
                last_source_row_number =
                    EXCLUDED.last_source_row_number,
                updated_at = CURRENT_TIMESTAMP;
        """

        with conn.cursor() as cur:
            for relationship in sorted(
                relationships,
                key=lambda item: (
                    item.award_id,
                    item.recipient_id,
                ),
            ):
                cur.execute(
                    sql,
                    (
                        load_batch_id,
                        relationship.award_id,
                        relationship.recipient_id,
                        relationship.recipient_uei,
                        relationship.observed_recipient_name,
                        relationship.occurrence_count,
                        relationship.first_action_date,
                        relationship.last_action_date,
                        relationship.first_source_row_number,
                        relationship.last_source_row_number,
                    ),
                )

        return len(relationships)