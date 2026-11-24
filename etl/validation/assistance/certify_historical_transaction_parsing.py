
"""ETL-201Q Stage C.5: certify historical transaction field parsing.

READ ONLY. No database writes.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from etl.common.db import get_connection
from etl.loaders.normalize_usaspending_assistance_transactions import (
    parse_date,
    parse_decimal,
    parse_integer,
)

BATCH_IDS = (20, 21)

DATE_FIELDS = (
    "action_date",
    "initial_report_date",
    "last_modified_date",
)

DECIMAL_FIELDS = (
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
    "obligated_amount_from_COVID-19_supplementals_for_overall_award",
    "outlayed_amount_from_COVID-19_supplementals_for_overall_award",
    "obligated_amount_from_IIJA_supplemental_for_overall_award",
    "outlayed_amount_from_IIJA_supplemental_for_overall_award",
)

INTEGER_FIELDS = ("action_date_fiscal_year",)


def main() -> None:
    conn = get_connection()

    examined = Counter()
    missing = Counter()
    errors = Counter()
    examples = []

    try:
        conn.set_session(
            readonly=True,
            autocommit=False,
            isolation_level="REPEATABLE READ",
        )

        with conn.cursor(name="historical_parser_cursor") as cur:
            cur.itersize = 2000

            cur.execute(
                """
                SELECT
                    r.load_batch_id,
                    r.source_row_number,
                    r.raw_record
                FROM assistance.raw_award_transaction r
                WHERE r.load_batch_id IN (20, 21)
                  AND EXISTS (
                      SELECT 1
                      FROM assistance.award a
                      WHERE a.assistance_award_unique_key =
                            r.assistance_award_unique_key
                  )
                ORDER BY
                    r.load_batch_id,
                    r.source_row_number
                """
            )

            for batch_id, source_row_number, record in cur:
                examined[batch_id] += 1

                fields = (
                    [(field, parse_date) for field in DATE_FIELDS]
                    + [(field, parse_decimal) for field in DECIMAL_FIELDS]
                    + [(field, parse_integer) for field in INTEGER_FIELDS]
                )

                for field_name, parser in fields:
                    value = record.get(field_name)

                    try:
                        parsed = parser(
                            value,
                            field_name=field_name,
                            source_row_number=source_row_number,
                        )

                        if parsed is None:
                            missing[field_name] += 1

                        if (
                            field_name in DECIMAL_FIELDS
                            and parsed is not None
                            and not isinstance(parsed, Decimal)
                        ):
                            raise TypeError(
                                "Monetary parser did not return Decimal"
                            )

                    except (ValueError, TypeError, OverflowError) as exc:
                        errors[field_name] += 1

                        if len(examples) < 30:
                            examples.append(
                                (
                                    batch_id,
                                    source_row_number,
                                    field_name,
                                    repr(value),
                                    str(exc),
                                )
                            )

        conn.rollback()

        print("=" * 76)
        print("ETL-201Q STAGE C.5 - HISTORICAL PARSER CERTIFICATION")
        print("READ ONLY - NO DATABASE WRITES")
        print("=" * 76)

        for batch_id in BATCH_IDS:
            print(
                f"Batch {batch_id}: "
                f"{examined[batch_id]:,} observations examined"
            )

        total = sum(examined.values())

        print(f"Total observations: {total:,}")
        print(f"Expected observations: {207343:,}")
        print(f"Fields tested per observation: {len(DATE_FIELDS) + len(DECIMAL_FIELDS) + len(INTEGER_FIELDS)}")
        print(f"Total field tests: {total * 19:,}")

        print()
        print("PARSER ERRORS")
        for field_name in DATE_FIELDS + DECIMAL_FIELDS + INTEGER_FIELDS:
            print(f"{field_name:65s} {errors[field_name]:,}")

        print()
        print("MISSING VALUES")
        for field_name in DATE_FIELDS + DECIMAL_FIELDS + INTEGER_FIELDS:
            print(f"{field_name:65s} {missing[field_name]:,}")

        if examples:
            print()
            print("ERROR EXAMPLES")
            for example in examples:
                print(example)

        passed = (
            examined[20] == 100426
            and examined[21] == 106917
            and sum(errors.values()) == 0
        )

        print()
        print("CERTIFICATION:", "PASS" if passed else "FAIL")
        print("DATABASE TRANSACTION: ROLLBACK")

        if not passed:
            raise SystemExit(1)

    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    main()
