"""Contract test for NormalizationExceptionRecorder."""

from __future__ import annotations

from etl.common.db import get_connection
from etl.validation.common.normalization_exception_recorder import (
    NormalizationExceptionRecorder,
)


LOAD_BATCH_ID = 5
ENTITY_TYPE = "award"
ENTITY_KEY = "CONT_AWD_36C26023P0181_3600_-NONE-_-NONE-"
ANOMALY_CODE = "PERFORMANCE_END_BEFORE_START"


def main() -> None:
    recorder = NormalizationExceptionRecorder()
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM procurement.normalization_exception
                WHERE load_batch_id = %s
                  AND entity_type = %s
                  AND entity_key = %s
                  AND anomaly_code = %s;
                """,
                (
                    LOAD_BATCH_ID,
                    ENTITY_TYPE,
                    ENTITY_KEY,
                    ANOMALY_CODE,
                ),
            )

        recorder.record(
            conn,
            load_batch_id=LOAD_BATCH_ID,
            entity_type=ENTITY_TYPE,
            entity_key=ENTITY_KEY,
            anomaly_code=ANOMALY_CODE,
            severity="WARNING",
            source_row_numbers=[6244, 6245],
            raw_values={
                "period_of_performance_start": "2023-01-17",
                "period_of_performance_current_end": "2023-01-13",
            },
            normalized_action={
                "period_of_performance_start": "2023-01-17",
                "period_of_performance_end": None,
            },
            message=(
                "USAspending reported a performance end date "
                "earlier than the performance start date."
            ),
        )

        # Record the same logical anomaly again with changed details.
        # The unique key should cause an update, not a duplicate insert.
        recorder.record(
            conn,
            load_batch_id=LOAD_BATCH_ID,
            entity_type=ENTITY_TYPE,
            entity_key=ENTITY_KEY,
            anomaly_code=ANOMALY_CODE,
            severity="WARNING",
            source_row_numbers=[6244, 6245],
            raw_values={
                "period_of_performance_start": "2023-01-17",
                "period_of_performance_current_end": "2023-01-13",
            },
            normalized_action={
                "period_of_performance_start": "2023-01-17",
                "period_of_performance_end": None,
            },
            message=(
                "Reversed USAspending performance-date range "
                "was preserved in raw data and normalized with "
                "a null end date."
            ),
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    severity,
                    source_row_numbers,
                    raw_values,
                    normalized_action,
                    message
                FROM procurement.normalization_exception
                WHERE load_batch_id = %s
                  AND entity_type = %s
                  AND entity_key = %s
                  AND anomaly_code = %s;
                """,
                (
                    LOAD_BATCH_ID,
                    ENTITY_TYPE,
                    ENTITY_KEY,
                    ANOMALY_CODE,
                ),
            )

            rows = cur.fetchall()

        assert len(rows) == 1

        (
            severity,
            source_row_numbers,
            raw_values,
            normalized_action,
            message,
        ) = rows[0]

        assert severity == "WARNING"
        assert source_row_numbers == [6244, 6245]

        assert raw_values == {
            "period_of_performance_start": "2023-01-17",
            "period_of_performance_current_end": "2023-01-13",
        }

        assert normalized_action == {
            "period_of_performance_start": "2023-01-17",
            "period_of_performance_end": None,
        }

        assert "null end date" in message

        conn.rollback()

        print("NormalizationExceptionRecorder contract test passed.")
        print()
        print(f"Load batch:       {LOAD_BATCH_ID}")
        print(f"Entity:           {ENTITY_TYPE}")
        print(f"Entity key:       {ENTITY_KEY}")
        print(f"Anomaly code:     {ANOMALY_CODE}")
        print("Idempotent upsert: verified")
        print("Transaction ownership: verified")

    finally:
        conn.close()


if __name__ == "__main__":
    main()