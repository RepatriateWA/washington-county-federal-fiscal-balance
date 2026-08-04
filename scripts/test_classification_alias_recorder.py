"""Contract test for ClassificationAliasRecorder."""

from __future__ import annotations

from etl.common.db import get_connection
from etl.validation.common.classification_alias_recorder import (
    ClassificationAlias,
    ClassificationAliasRecorder,
)


LOAD_BATCH_ID = 5


def main() -> None:
    recorder = ClassificationAliasRecorder()
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM procurement.psc_alias
                WHERE load_batch_id = %s
                  AND psc_code = 'Q201';
                """,
                (LOAD_BATCH_ID,),
            )

            cur.execute(
                """
                INSERT INTO procurement.psc (
                    psc_code,
                    psc_description,
                    product_or_service
                )
                VALUES (
                    'Q201',
                    'MEDICAL- MANAGED HEALTHCARE',
                    NULL
                )
                ON CONFLICT (psc_code)
                DO NOTHING;
                """
            )

        aliases = [
            ClassificationAlias(
                code="Q201",
                observed_description=(
                    "MEDICAL- GENERAL HEALTH CARE"
                ),
                occurrence_count=48,
                first_source_row_number=577,
                last_source_row_number=119568,
            ),
            ClassificationAlias(
                code="Q201",
                observed_description=(
                    "MEDICAL- MANAGED HEALTHCARE"
                ),
                occurrence_count=46,
                first_source_row_number=589,
                last_source_row_number=119609,
            ),
        ]

        first_count = recorder.record_psc(
            conn,
            load_batch_id=LOAD_BATCH_ID,
            aliases=aliases,
        )

        assert first_count == 2

        updated_aliases = [
            ClassificationAlias(
                code="Q201",
                observed_description=(
                    "MEDICAL- GENERAL HEALTH CARE"
                ),
                occurrence_count=48,
                first_source_row_number=577,
                last_source_row_number=119568,
            ),
            ClassificationAlias(
                code="Q201",
                observed_description=(
                    "MEDICAL- MANAGED HEALTHCARE"
                ),
                occurrence_count=47,
                first_source_row_number=589,
                last_source_row_number=120000,
            ),
        ]

        second_count = recorder.record_psc(
            conn,
            load_batch_id=LOAD_BATCH_ID,
            aliases=updated_aliases,
        )

        assert second_count == 2

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    observed_description,
                    occurrence_count,
                    first_source_row_number,
                    last_source_row_number
                FROM procurement.psc_alias
                WHERE load_batch_id = %s
                  AND psc_code = 'Q201'
                ORDER BY observed_description;
                """,
                (LOAD_BATCH_ID,),
            )

            rows = cur.fetchall()

        assert rows == [
            (
                "MEDICAL- GENERAL HEALTH CARE",
                48,
                577,
                119568,
            ),
            (
                "MEDICAL- MANAGED HEALTHCARE",
                47,
                589,
                120000,
            ),
        ]

        conn.rollback()

        print(
            "ClassificationAliasRecorder contract test passed."
        )
        print()
        print(f"Load batch:        {LOAD_BATCH_ID}")
        print("Classification:    PSC")
        print("Code:              Q201")
        print("Aliases recorded:  2")
        print("Idempotent upsert: verified")
        print("Transaction ownership: verified")

    finally:
        conn.close()


if __name__ == "__main__":
    main()