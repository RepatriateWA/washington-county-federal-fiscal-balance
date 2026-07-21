from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from etl.db import get_connection


@dataclass
class ValidationResult:
    name: str
    passed: bool
    details: str


def get_latest_batch_id(cursor, fiscal_year: int) -> int:
    cursor.execute(
        """
        SELECT load_batch_id
        FROM chip.cms21_load_batch
        WHERE fiscal_year = %s
        ORDER BY loaded_at DESC, load_batch_id DESC
        LIMIT 1;
        """,
        (fiscal_year,),
    )

    row = cursor.fetchone()

    if row is None:
        raise ValueError(
            f"No CHIP CMS-21 load batch was found for fiscal year {fiscal_year}."
        )

    return row[0]


def validate_row_parity(cursor, load_batch_id: int) -> ValidationResult:
    cursor.execute(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM chip.cms21_raw_row
                WHERE load_batch_id = %s
            ) AS raw_rows,
            (
                SELECT COUNT(*)
                FROM chip.cms21_expenditure
                WHERE load_batch_id = %s
            ) AS curated_rows;
        """,
        (load_batch_id, load_batch_id),
    )

    raw_rows, curated_rows = cursor.fetchone()
    passed = raw_rows == curated_rows and raw_rows > 0

    return ValidationResult(
        name="Raw-to-curated row parity",
        passed=passed,
        details=f"raw={raw_rows}, curated={curated_rows}",
    )


def validate_accounting_identity(cursor, load_batch_id: int) -> ValidationResult:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM chip.cms21_expenditure
        WHERE load_batch_id = %s
          AND total_computable <> federal_share + state_share;
        """,
        (load_batch_id,),
    )

    failures = cursor.fetchone()[0]

    return ValidationResult(
        name="Accounting identity",
        passed=failures == 0,
        details=f"failures={failures}",
    )


def validate_unique_source_rows(cursor, load_batch_id: int) -> ValidationResult:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT source_sheet, source_row
            FROM chip.cms21_raw_row
            WHERE load_batch_id = %s
            GROUP BY source_sheet, source_row
            HAVING COUNT(*) > 1
        ) duplicates;
        """,
        (load_batch_id,),
    )

    duplicates = cursor.fetchone()[0]

    return ValidationResult(
        name="Unique source rows",
        passed=duplicates == 0,
        details=f"duplicate source rows={duplicates}",
    )


def validate_worksheet_types(cursor, load_batch_id: int) -> ValidationResult:
    cursor.execute(
        """
        SELECT DISTINCT worksheet_type
        FROM chip.cms21_expenditure
        WHERE load_batch_id = %s
        ORDER BY worksheet_type;
        """,
        (load_batch_id,),
    )

    actual = {row[0] for row in cursor.fetchall()}
    expected = {"CHIP", "MCHIP", "MCHIP_20_PERCENT"}

    return ValidationResult(
        name="Worksheet coverage",
        passed=actual == expected,
        details=f"expected={sorted(expected)}, actual={sorted(actual)}",
    )


def validate_control_totals(cursor, load_batch_id: int) -> ValidationResult:
    cursor.execute(
        """
        SELECT
            worksheet_type,
            COUNT(*) FILTER (WHERE is_control_total = TRUE)
        FROM chip.cms21_expenditure
        WHERE load_batch_id = %s
        GROUP BY worksheet_type
        ORDER BY worksheet_type;
        """,
        (load_batch_id,),
    )

    rows = cursor.fetchall()
    counts = {worksheet_type: count for worksheet_type, count in rows}

    expected_types = {"CHIP", "MCHIP", "MCHIP_20_PERCENT"}
    passed = (
        set(counts) == expected_types
        and all(count == 1 for count in counts.values())
    )

    return ValidationResult(
        name="Control total count",
        passed=passed,
        details=str(counts),
    )


def validate_classification(cursor, load_batch_id: int) -> ValidationResult:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM chip.cms21_expenditure
        WHERE load_batch_id = %s
          AND (
                (
                    worksheet_type IN ('CHIP', 'MCHIP')
                    AND (
                        is_additive_expenditure IS NOT TRUE
                        OR is_financing_adjustment IS NOT FALSE
                    )
                )
                OR
                (
                    worksheet_type = 'MCHIP_20_PERCENT'
                    AND (
                        is_additive_expenditure IS NOT FALSE
                        OR is_financing_adjustment IS NOT TRUE
                    )
                )
          );
        """,
        (load_batch_id,),
    )

    failures = cursor.fetchone()[0]

    return ValidationResult(
        name="Worksheet classification",
        passed=failures == 0,
        details=f"misclassified rows={failures}",
    )


def validate_control_values(
    cursor,
    load_batch_id: int,
    fiscal_year: int,
) -> ValidationResult:
    cursor.execute(
        """
        SELECT
            worksheet_type,
            total_computable,
            federal_share,
            state_share
        FROM chip.cms21_expenditure
        WHERE load_batch_id = %s
          AND is_control_total = TRUE
        ORDER BY worksheet_type;
        """,
        (load_batch_id,),
    )

    actual = {
        worksheet_type: (
            total_computable,
            federal_share,
            state_share,
        )
        for (
            worksheet_type,
            total_computable,
            federal_share,
            state_share,
        ) in cursor.fetchall()
    }

    if fiscal_year != 2015:
        return ValidationResult(
            name="Known FY2015 control values",
            passed=True,
            details="not applicable outside FY2015",
        )

    expected = {
        "CHIP": (89_537_469, 58_294_556, 31_242_913),
        "MCHIP": (28_316_844, 18_410_252, 9_906_592),
        "MCHIP_20_PERCENT": (0, 48_597_111, -48_597_111),
    }

    return ValidationResult(
        name="Known FY2015 control values",
        passed=actual == expected,
        details=f"expected={expected}, actual={actual}",
    )


def validate_additive_federal_total(
    cursor,
    load_batch_id: int,
    fiscal_year: int,
) -> ValidationResult:
    cursor.execute(
        """
        SELECT COALESCE(SUM(federal_share), 0)
        FROM chip.cms21_expenditure
        WHERE load_batch_id = %s
          AND is_control_total = TRUE
          AND is_additive_expenditure = TRUE;
        """,
        (load_batch_id,),
    )

    actual = cursor.fetchone()[0]

    if fiscal_year != 2015:
        return ValidationResult(
            name="Known FY2015 additive federal total",
            passed=True,
            details=f"not applicable outside FY2015; actual={actual:,}",
        )

    expected = 76_704_808

    return ValidationResult(
        name="Known FY2015 additive federal total",
        passed=actual == expected,
        details=f"expected={expected:,}, actual={actual:,}",
    )


def print_control_totals(cursor, load_batch_id: int) -> None:
    cursor.execute(
        """
        SELECT
            worksheet_type,
            total_computable,
            federal_share,
            state_share,
            is_additive_expenditure,
            is_financing_adjustment
        FROM chip.cms21_expenditure
        WHERE load_batch_id = %s
          AND is_control_total = TRUE
        ORDER BY worksheet_type;
        """,
        (load_batch_id,),
    )

    print()
    print("CONTROL TOTALS")
    print("-" * 100)

    for row in cursor.fetchall():
        (
            worksheet_type,
            total_computable,
            federal_share,
            state_share,
            is_additive,
            is_adjustment,
        ) = row

        print(
            f"{worksheet_type:20} "
            f"Total={total_computable:>15,}  "
            f"Federal={federal_share:>15,}  "
            f"State={state_share:>15,}  "
            f"Additive={str(is_additive):<5}  "
            f"Adjustment={str(is_adjustment):<5}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a CHIP CMS-21 database load."
    )

    parser.add_argument(
        "--fiscal-year",
        type=int,
        default=2015,
        help="Fiscal year to validate. Default: 2015.",
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=None,
        help=(
            "Specific load batch to validate. "
            "Defaults to the latest batch for the fiscal year."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    conn = get_connection()

    try:
        cursor = conn.cursor()

        load_batch_id = (
            args.load_batch_id
            if args.load_batch_id is not None
            else get_latest_batch_id(cursor, args.fiscal_year)
        )

        validations = [
            validate_row_parity(cursor, load_batch_id),
            validate_accounting_identity(cursor, load_batch_id),
            validate_unique_source_rows(cursor, load_batch_id),
            validate_worksheet_types(cursor, load_batch_id),
            validate_control_totals(cursor, load_batch_id),
            validate_classification(cursor, load_batch_id),
            validate_control_values(
                cursor,
                load_batch_id,
                args.fiscal_year,
            ),
            validate_additive_federal_total(
                cursor,
                load_batch_id,
                args.fiscal_year,
            ),
        ]

        print()
        print("CHIP CMS-21 VALIDATION")
        print("=" * 100)
        print(f"Fiscal year:   {args.fiscal_year}")
        print(f"Load batch ID: {load_batch_id}")
        print()

        for result in validations:
            status = "PASS" if result.passed else "FAIL"
            print(f"[{status}] {result.name}")
            print(f"       {result.details}")

        print_control_totals(cursor, load_batch_id)

        passed = all(result.passed for result in validations)

        print()
        print("=" * 100)
        print("OVERALL RESULT:", "PASS" if passed else "FAIL")

        cursor.close()

        return 0 if passed else 1

    except Exception as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 1

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())