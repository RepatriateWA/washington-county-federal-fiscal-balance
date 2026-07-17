"""
Validate the raw CMS Medicaid MBES load in:

    cms_raw.medicaid_mbes

Example:

    python -m scripts.validate_medicaid_mbes_raw

Optional fiscal year:

    python -m scripts.validate_medicaid_mbes_raw --fiscal-year 2024
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from typing import Optional

import psycopg2
from dotenv import load_dotenv


DATABASE_TABLE = "cms_raw.medicaid_mbes"
DEFAULT_FISCAL_YEAR = 2024
DEFAULT_STATE_NAME = "Washington"
DEFAULT_WORKSHEET_NAME = "MAP - Washington"


def first_environment_value(
    *names: str,
    default: Optional[str] = None,
) -> Optional[str]:
    for name in names:
        value = os.getenv(name)

        if value is not None and value.strip():
            return value.strip()

    return default


def get_connection():
    load_dotenv()

    host = first_environment_value(
        "DB_HOST",
        "POSTGRES_HOST",
        "PGHOST",
        default="localhost",
    )

    port = first_environment_value(
        "DB_PORT",
        "POSTGRES_PORT",
        "PGPORT",
        default="5432",
    )

    database = first_environment_value(
        "DB_NAME",
        "POSTGRES_DB",
        "PGDATABASE",
        default="wcffbp",
    )

    user = first_environment_value(
        "DB_USER",
        "POSTGRES_USER",
        "PGUSER",
        default="postgres",
    )

    password = first_environment_value(
        "DB_PASSWORD",
        "POSTGRES_PASSWORD",
        "PGPASSWORD",
    )

    if not password:
        raise RuntimeError(
            "Database password was not found in the .env file."
        )

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
    )


def format_amount(value: Optional[Decimal]) -> str:
    if value is None:
        return "NULL"

    return f"{value:,.2f}"


def print_check(
    label: str,
    passed: bool,
    detail: str,
) -> None:
    status = "PASS" if passed else "FAIL"
    print(f"{status:<6} {label:<44} {detail}")


def fetch_one(cursor, sql: str, parameters: tuple):
    cursor.execute(sql, parameters)
    return cursor.fetchone()


def fetch_all(cursor, sql: str, parameters: tuple):
    cursor.execute(sql, parameters)
    return cursor.fetchall()


def validate(
    fiscal_year: int,
    state_name: str,
    worksheet_name: str,
) -> bool:
    parameters = (
        fiscal_year,
        state_name,
        worksheet_name,
    )

    all_passed = True

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            row_count = fetch_one(
                cursor,
                f"""
                SELECT COUNT(*)
                FROM {DATABASE_TABLE}
                WHERE fiscal_year = %s
                  AND state_name = %s
                  AND worksheet_name = %s;
                """,
                parameters,
            )[0]

            print()
            print("=" * 96)
            print("CMS MEDICAID MBES RAW VALIDATION")
            print("=" * 96)
            print(f"Fiscal year:   {fiscal_year}")
            print(f"State:         {state_name}")
            print(f"Worksheet:     {worksheet_name}")
            print(f"Rows found:    {row_count:,}")
            print("-" * 96)

            passed = row_count > 0
            print_check(
                "Raw rows exist",
                passed,
                f"{row_count:,} rows",
            )
            all_passed &= passed

            duplicate_count = fetch_one(
                cursor,
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT
                        fiscal_year,
                        state_name,
                        worksheet_name,
                        source_row_number,
                        source_file,
                        COUNT(*) AS row_count
                    FROM {DATABASE_TABLE}
                    WHERE fiscal_year = %s
                      AND state_name = %s
                      AND worksheet_name = %s
                    GROUP BY
                        fiscal_year,
                        state_name,
                        worksheet_name,
                        source_row_number,
                        source_file
                    HAVING COUNT(*) > 1
                ) duplicate_rows;
                """,
                parameters,
            )[0]

            passed = duplicate_count == 0
            print_check(
                "No duplicate source rows",
                passed,
                f"{duplicate_count:,} duplicate keys",
            )
            all_passed &= passed

            missing_classification_count = fetch_one(
                cursor,
                f"""
                SELECT COUNT(*)
                FROM {DATABASE_TABLE}
                WHERE fiscal_year = %s
                  AND state_name = %s
                  AND worksheet_name = %s
                  AND (
                        section_code IS NULL
                     OR row_type IS NULL
                     OR include_in_detail_reporting IS NULL
                  );
                """,
                parameters,
            )[0]

            passed = missing_classification_count == 0
            print_check(
                "All rows classified",
                passed,
                f"{missing_classification_count:,} incomplete rows",
            )
            all_passed &= passed

            section_counts = fetch_all(
                cursor,
                f"""
                SELECT
                    section_code,
                    COUNT(*)
                FROM {DATABASE_TABLE}
                WHERE fiscal_year = %s
                  AND state_name = %s
                  AND worksheet_name = %s
                GROUP BY section_code
                ORDER BY section_code;
                """,
                parameters,
            )

            print()
            print("Rows by section")
            print("-" * 96)

            section_count_map = dict(section_counts)

            for section_code in ("PRIMARY", "C", "T", "FOOTER"):
                print(
                    f"{section_code:<20}"
                    f"{section_count_map.get(section_code, 0):>12,}"
                )

            expected_sections_present = all(
                section_count_map.get(section_code, 0) > 0
                for section_code in ("PRIMARY", "C", "T", "FOOTER")
            )

            print_check(
                "Expected accounting sections present",
                expected_sections_present,
                "PRIMARY, C, T, and FOOTER",
            )
            all_passed &= expected_sections_present

            row_type_counts = fetch_all(
                cursor,
                f"""
                SELECT
                    row_type,
                    COUNT(*)
                FROM {DATABASE_TABLE}
                WHERE fiscal_year = %s
                  AND state_name = %s
                  AND worksheet_name = %s
                GROUP BY row_type
                ORDER BY row_type;
                """,
                parameters,
            )

            print()
            print("Rows by type")
            print("-" * 96)

            for row_type, count in row_type_counts:
                print(f"{row_type:<20}{count:>12,}")

            control_rows = fetch_all(
                cursor,
                f"""
                SELECT
                    raw_row_id,
                    source_row_number,
                    total_computable,
                    federal_share,
                    federal_share_medicaid,
                    federal_share_arra,
                    federal_share_covid,
                    state_share
                FROM {DATABASE_TABLE}
                WHERE fiscal_year = %s
                  AND state_name = %s
                  AND worksheet_name = %s
                  AND section_code = 'PRIMARY'
                  AND LOWER(service_category) =
                      'total net expenditures'
                ORDER BY raw_row_id;
                """,
                parameters,
            )

            passed = len(control_rows) == 1
            print_check(
                "One primary control-total row",
                passed,
                f"{len(control_rows)} rows found",
            )
            all_passed &= passed

            if len(control_rows) == 1:
                (
                    _raw_row_id,
                    source_row_number,
                    total_computable,
                    federal_share,
                    federal_share_medicaid,
                    federal_share_arra,
                    federal_share_covid,
                    state_share,
                ) = control_rows[0]

                print()
                print("Primary Total Net Expenditures")
                print("-" * 96)
                print(
                    f"{'Source Excel row':<34}"
                    f"{source_row_number:>24}"
                )
                print(
                    f"{'Total computable':<34}"
                    f"{format_amount(total_computable):>24}"
                )
                print(
                    f"{'Federal share':<34}"
                    f"{format_amount(federal_share):>24}"
                )
                print(
                    f"{'Federal share Medicaid':<34}"
                    f"{format_amount(federal_share_medicaid):>24}"
                )
                print(
                    f"{'Federal share ARRA':<34}"
                    f"{format_amount(federal_share_arra):>24}"
                )
                print(
                    f"{'Federal share COVID':<34}"
                    f"{format_amount(federal_share_covid):>24}"
                )
                print(
                    f"{'State share':<34}"
                    f"{format_amount(state_share):>24}"
                )

                financial_values_present = all(
                    value is not None
                    for value in (
                        total_computable,
                        federal_share,
                        state_share,
                    )
                )

                print_check(
                    "Control-total amounts populated",
                    financial_values_present,
                    "total, federal, and state shares",
                )
                all_passed &= financial_values_present

                if financial_values_present:
                    total_reconciliation_difference = (
                        total_computable
                        - federal_share
                        - state_share
                    )

                    passed = (
                        abs(total_reconciliation_difference)
                        <= Decimal("1.00")
                    )

                    print_check(
                        "Federal plus state equals total",
                        passed,
                        (
                            "difference "
                            f"{format_amount(total_reconciliation_difference)}"
                        ),
                    )
                    all_passed &= passed

                federal_component_values_present = all(
                    value is not None
                    for value in (
                        federal_share,
                        federal_share_medicaid,
                        federal_share_arra,
                        federal_share_covid,
                    )
                )

                if federal_component_values_present:
                    federal_component_difference = (
                        federal_share
                        - federal_share_medicaid
                        - federal_share_arra
                        - federal_share_covid
                    )

                    passed = (
                        abs(federal_component_difference)
                        <= Decimal("1.00")
                    )

                    print_check(
                        "Federal components equal federal share",
                        passed,
                        (
                            "difference "
                            f"{format_amount(federal_component_difference)}"
                        ),
                    )
                    all_passed &= passed
                else:
                    print_check(
                        "Federal components equal federal share",
                        False,
                        "one or more federal components are NULL",
                    )
                    all_passed = False

            reporting_flag_errors = fetch_one(
                cursor,
                f"""
                SELECT COUNT(*)
                FROM {DATABASE_TABLE}
                WHERE fiscal_year = %s
                  AND state_name = %s
                  AND worksheet_name = %s
                  AND include_in_detail_reporting = TRUE
                  AND (
                        section_code <> 'PRIMARY'
                     OR row_type NOT IN ('DETAIL', 'ADJUSTMENT')
                  );
                """,
                parameters,
            )[0]

            passed = reporting_flag_errors == 0
            print_check(
                "Reporting flags obey classification",
                passed,
                f"{reporting_flag_errors:,} invalid flags",
            )
            all_passed &= passed

            excluded_primary_totals = fetch_one(
                cursor,
                f"""
                SELECT COUNT(*)
                FROM {DATABASE_TABLE}
                WHERE fiscal_year = %s
                  AND state_name = %s
                  AND worksheet_name = %s
                  AND section_code = 'PRIMARY'
                  AND row_type IN (
                      'CONTROL_TOTAL',
                      'SUBTOTAL'
                  )
                  AND include_in_detail_reporting = TRUE;
                """,
                parameters,
            )[0]

            passed = excluded_primary_totals == 0
            print_check(
                "Primary totals excluded from detail",
                passed,
                f"{excluded_primary_totals:,} included totals",
            )
            all_passed &= passed

            included_detail_count = fetch_one(
                cursor,
                f"""
                SELECT COUNT(*)
                FROM {DATABASE_TABLE}
                WHERE fiscal_year = %s
                  AND state_name = %s
                  AND worksheet_name = %s
                  AND include_in_detail_reporting = TRUE;
                """,
                parameters,
            )[0]

            passed = included_detail_count > 0
            print_check(
                "Detail-reporting rows exist",
                passed,
                f"{included_detail_count:,} rows",
            )
            all_passed &= passed

            footer_count = fetch_one(
                cursor,
                f"""
                SELECT COUNT(*)
                FROM {DATABASE_TABLE}
                WHERE fiscal_year = %s
                  AND state_name = %s
                  AND worksheet_name = %s
                  AND row_type = 'FOOTER';
                """,
                parameters,
            )[0]

            passed = footer_count == 1
            print_check(
                "One source footer preserved",
                passed,
                f"{footer_count:,} footer rows",
            )
            all_passed &= passed

            print()
            print("=" * 96)

            if all_passed:
                print("MEDICAID MBES RAW VALIDATION: PASS")
            else:
                print("MEDICAID MBES RAW VALIDATION: FAIL")

            print("=" * 96)

            return all_passed

    finally:
        connection.close()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the CMS Medicaid MBES raw table."
    )

    parser.add_argument(
        "--fiscal-year",
        type=int,
        default=DEFAULT_FISCAL_YEAR,
    )

    parser.add_argument(
        "--state-name",
        default=DEFAULT_STATE_NAME,
    )

    parser.add_argument(
        "--worksheet-name",
        default=DEFAULT_WORKSHEET_NAME,
    )

    return parser


def main() -> int:
    args = build_argument_parser().parse_args()

    try:
        passed = validate(
            fiscal_year=args.fiscal_year,
            state_name=args.state_name,
            worksheet_name=args.worksheet_name,
        )

        return 0 if passed else 1

    except Exception as exc:
        print(
            f"Medicaid MBES raw validation failed with an error: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())