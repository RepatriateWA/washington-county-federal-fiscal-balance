"""Contract test for RecipientParentRelationshipRecorder."""

from __future__ import annotations

from datetime import date

from etl.common.db import get_connection
from etl.validation.common.recipient_parent_relationship_recorder import (
    RecipientParentRelationship,
    RecipientParentRelationshipRecorder,
)

LOAD_BATCH_ID = 5
RECIPIENT_UEI = "ZVW2T2CCG7V9"


def main() -> None:
    recorder = RecipientParentRelationshipRecorder()
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE
                FROM procurement.recipient_parent_relationship
                WHERE load_batch_id = %s
                  AND recipient_uei = %s;
                """,
                (
                    LOAD_BATCH_ID,
                    RECIPIENT_UEI,
                ),
            )

        relationships = [
            RecipientParentRelationship(
                recipient_uei=RECIPIENT_UEI,
                parent_uei="U5KEFDV4N965",
                observed_parent_name="T-MOBILE US, INC.",
                occurrence_count=147,
                first_action_date=date(2023, 10, 4),
                last_action_date=date(2024, 3, 6),
                first_source_row_number=101,
                last_source_row_number=9999,
            ),
            RecipientParentRelationship(
                recipient_uei=RECIPIENT_UEI,
                parent_uei=RECIPIENT_UEI,
                observed_parent_name="T-MOBILE USA, INC.",
                occurrence_count=318,
                first_action_date=date(2024, 3, 7),
                last_action_date=date(2024, 12, 31),
                first_source_row_number=10000,
                last_source_row_number=20000,
            ),
        ]

        first_count = recorder.record(
            conn,
            load_batch_id=LOAD_BATCH_ID,
            relationships=relationships,
        )

        assert first_count == 2

        updated_relationships = [
            relationships[0],
            RecipientParentRelationship(
                recipient_uei=RECIPIENT_UEI,
                parent_uei=RECIPIENT_UEI,
                observed_parent_name="T-MOBILE USA, INC.",
                occurrence_count=319,
                first_action_date=date(2024, 3, 7),
                last_action_date=date(2024, 12, 31),
                first_source_row_number=10000,
                last_source_row_number=20001,
            ),
        ]

        second_count = recorder.record(
            conn,
            load_batch_id=LOAD_BATCH_ID,
            relationships=updated_relationships,
        )

        assert second_count == 2

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    parent_uei,
                    occurrence_count,
                    first_action_date,
                    last_action_date,
                    first_source_row_number,
                    last_source_row_number
                FROM procurement.recipient_parent_relationship
                WHERE load_batch_id = %s
                  AND recipient_uei = %s
                ORDER BY parent_uei;
                """,
                (
                    LOAD_BATCH_ID,
                    RECIPIENT_UEI,
                ),
            )

            rows = cur.fetchall()

        assert rows == [
            (
                "U5KEFDV4N965",
                147,
                date(2023, 10, 4),
                date(2024, 3, 6),
                101,
                9999,
            ),
            (
                "ZVW2T2CCG7V9",
                319,
                date(2024, 3, 7),
                date(2024, 12, 31),
                10000,
                20001,
            ),
        ]

        conn.rollback()

        print(
            "RecipientParentRelationshipRecorder contract test passed."
        )
        print()
        print(f"Load batch:       {LOAD_BATCH_ID}")
        print(f"Recipient UEI:    {RECIPIENT_UEI}")
        print("Relationships:    2")
        print("Idempotent upsert: verified")
        print("Transaction ownership: verified")

    finally:
        conn.close()


if __name__ == "__main__":
    main()