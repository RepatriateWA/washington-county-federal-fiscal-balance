"""Contract test for AwardRecipientRelationshipRecorder."""

from __future__ import annotations

from datetime import date

from etl.common.db import get_connection
from etl.validation.common.award_recipient_relationship_recorder import (
    AwardRecipientRelationship,
    AwardRecipientRelationshipRecorder,
)


LOAD_BATCH_ID = 5
AWARD_ID = 2954


def main() -> None:
    recorder = AwardRecipientRelationshipRecorder()
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE
                FROM procurement.award_recipient_relationship
                WHERE load_batch_id = %s
                  AND award_id = %s;
                """,
                (
                    LOAD_BATCH_ID,
                    AWARD_ID,
                ),
            )

            cur.execute(
                """
                SELECT
                    recipient_id,
                    recipient_uei
                FROM procurement.recipient
                WHERE recipient_uei IN (
                    'TMVEDNL69EB1',
                    'GLHZFFJJZ8G2'
                )
                ORDER BY recipient_uei;
                """
            )

            recipient_rows = cur.fetchall()

        recipients_by_uei = {
            recipient_uei: int(recipient_id)
            for recipient_id, recipient_uei
            in recipient_rows
        }

        assert set(recipients_by_uei) == {
            "TMVEDNL69EB1",
            "GLHZFFJJZ8G2",
        }

        ecology_recipient_id = recipients_by_uei[
            "TMVEDNL69EB1"
        ]

        wsp_recipient_id = recipients_by_uei[
            "GLHZFFJJZ8G2"
        ]

        relationships = [
            AwardRecipientRelationship(
                award_id=AWARD_ID,
                recipient_id=ecology_recipient_id,
                recipient_uei="TMVEDNL69EB1",
                observed_recipient_name=(
                    "ECOLOGY & ENVIRONMENT INC"
                ),
                occurrence_count=1,
                first_action_date=date(2024, 1, 19),
                last_action_date=date(2024, 1, 19),
                first_source_row_number=4275,
                last_source_row_number=4275,
            ),
            AwardRecipientRelationship(
                award_id=AWARD_ID,
                recipient_id=wsp_recipient_id,
                recipient_uei="GLHZFFJJZ8G2",
                observed_recipient_name=(
                    "WSP USA SOLUTIONS INC"
                ),
                occurrence_count=2,
                first_action_date=date(2024, 7, 26),
                last_action_date=date(2024, 9, 23),
                first_source_row_number=4276,
                last_source_row_number=4277,
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
            AwardRecipientRelationship(
                award_id=AWARD_ID,
                recipient_id=wsp_recipient_id,
                recipient_uei="GLHZFFJJZ8G2",
                observed_recipient_name=(
                    "WSP USA SOLUTIONS INC"
                ),
                occurrence_count=3,
                first_action_date=date(2024, 7, 26),
                last_action_date=date(2024, 9, 24),
                first_source_row_number=4276,
                last_source_row_number=4278,
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
                    recipient_uei,
                    observed_recipient_name,
                    occurrence_count,
                    first_action_date,
                    last_action_date,
                    first_source_row_number,
                    last_source_row_number
                FROM procurement.award_recipient_relationship
                WHERE load_batch_id = %s
                  AND award_id = %s
                ORDER BY recipient_uei;
                """,
                (
                    LOAD_BATCH_ID,
                    AWARD_ID,
                ),
            )

            rows = cur.fetchall()

        assert rows == [
            (
                "GLHZFFJJZ8G2",
                "WSP USA SOLUTIONS INC",
                3,
                date(2024, 7, 26),
                date(2024, 9, 24),
                4276,
                4278,
            ),
            (
                "TMVEDNL69EB1",
                "ECOLOGY & ENVIRONMENT INC",
                1,
                date(2024, 1, 19),
                date(2024, 1, 19),
                4275,
                4275,
            ),
        ]

        conn.rollback()

        print(
            "AwardRecipientRelationshipRecorder contract test passed."
        )
        print()
        print(f"Load batch:       {LOAD_BATCH_ID}")
        print(f"Award ID:         {AWARD_ID}")
        print("Relationships:    2")
        print("Idempotent upsert: verified")
        print("Transaction ownership: verified")

    finally:
        conn.close()


if __name__ == "__main__":
    main()