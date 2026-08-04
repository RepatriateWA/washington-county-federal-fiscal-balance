"""Persist observed recipient-to-parent UEI relationships."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class RecipientParentRelationship:
    """One observed recipient-parent relationship in a load batch."""

    recipient_uei: str
    parent_uei: str
    observed_parent_name: str | None
    occurrence_count: int
    first_action_date: date | None
    last_action_date: date | None
    first_source_row_number: int
    last_source_row_number: int


class RecipientParentRelationshipRecorder:
    """Persist recipient-parent relationships idempotently."""

    def record(
        self,
        conn,
        *,
        load_batch_id: int,
        relationships: list[RecipientParentRelationship],
    ) -> int:
        """Upsert all observed relationships for one load batch."""

        sql = """
            INSERT INTO procurement.recipient_parent_relationship (
                load_batch_id,
                recipient_uei,
                parent_uei,
                observed_parent_name,
                occurrence_count,
                first_action_date,
                last_action_date,
                first_source_row_number,
                last_source_row_number
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            ON CONFLICT (
                load_batch_id,
                recipient_uei,
                parent_uei
            )
            DO UPDATE SET
                observed_parent_name =
                    EXCLUDED.observed_parent_name,
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
                    item.recipient_uei,
                    item.parent_uei,
                ),
            ):
                cur.execute(
                    sql,
                    (
                        load_batch_id,
                        relationship.recipient_uei,
                        relationship.parent_uei,
                        relationship.observed_parent_name,
                        relationship.occurrence_count,
                        relationship.first_action_date,
                        relationship.last_action_date,
                        relationship.first_source_row_number,
                        relationship.last_source_row_number,
                    ),
                )

        return len(relationships)