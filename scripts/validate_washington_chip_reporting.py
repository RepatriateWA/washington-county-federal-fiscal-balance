"""
Validate Migration 107 Washington CHIP reporting integration.

Usage:
    python -m scripts.validate_washington_chip_reporting
"""

from __future__ import annotations

from dataclasses import dataclass

from etl.db import get_connection


EXPECTED_YEARS = set(range(2015, 2025))


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def main() -> int:
    checks: list[Check] = []

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fiscal_year, federal_expenditure_amount
                FROM reporting.v_washington_chip_expenditures
                ORDER BY fiscal_year;
                """
            )
            reporting_rows = cursor.fetchall()
            reporting = {int(year): int(amount) for year, amount in reporting_rows}

            actual_years = set(reporting)
            checks.append(
                Check(
                    "CHIP reporting year coverage",
                    actual_years == EXPECTED_YEARS,
                    f"expected={sorted(EXPECTED_YEARS)}, actual={sorted(actual_years)}",
                )
            )

            cursor.execute(
                """
                SELECT
                    fiscal_year,
                    SUM(federal_share)::bigint AS expected_amount
                FROM chip.v_cms21_control_totals
                WHERE state_abbreviation = 'WA'
                  AND is_additive_expenditure = TRUE
                  AND is_financing_adjustment = FALSE
                GROUP BY fiscal_year
                ORDER BY fiscal_year;
                """
            )
            source = {int(year): int(amount) for year, amount in cursor.fetchall()}

            mismatches = {
                year: (source.get(year), reporting.get(year))
                for year in sorted(set(source) | set(reporting))
                if source.get(year) != reporting.get(year)
            }
            checks.append(
                Check(
                    "Reporting totals match CMS-21 additive totals",
                    not mismatches,
                    f"mismatches={mismatches}",
                )
            )

            cursor.execute(
                """
                SELECT fiscal_year, additive_control_total_count
                FROM reporting.v_washington_chip_expenditures
                WHERE additive_control_total_count <> 2
                ORDER BY fiscal_year;
                """
            )
            bad_counts = cursor.fetchall()
            checks.append(
                Check(
                    "Exactly two additive CHIP control totals per year",
                    not bad_counts,
                    f"exceptions={bad_counts}",
                )
            )

            cursor.execute(
                """
                SELECT report_year, COUNT(*)
                FROM reporting.v_washington_tracked_expenditures
                WHERE agency_code = 'CMS'
                  AND program_code = 'CHIP'
                GROUP BY report_year
                HAVING COUNT(*) <> 1
                ORDER BY report_year;
                """
            )
            duplicate_or_missing = cursor.fetchall()

            cursor.execute(
                """
                SELECT report_year
                FROM reporting.v_washington_tracked_expenditures
                WHERE agency_code = 'CMS'
                  AND program_code = 'CHIP'
                ORDER BY report_year;
                """
            )
            tracked_years = {int(row[0]) for row in cursor.fetchall()}

            tracked_ok = tracked_years == EXPECTED_YEARS and not duplicate_or_missing
            checks.append(
                Check(
                    "Tracked-expenditures CHIP coverage",
                    tracked_ok,
                    (
                        f"expected={sorted(EXPECTED_YEARS)}, "
                        f"actual={sorted(tracked_years)}, "
                        f"count_exceptions={duplicate_or_missing}"
                    ),
                )
            )

            cursor.execute(
                """
                SELECT
                    t.report_year,
                    t.expenditure_dollars,
                    c.federal_expenditure_amount
                FROM reporting.v_washington_tracked_expenditures AS t
                JOIN reporting.v_washington_chip_expenditures AS c
                  ON c.fiscal_year = t.report_year
                WHERE t.agency_code = 'CMS'
                  AND t.program_code = 'CHIP'
                  AND t.expenditure_dollars <> c.federal_expenditure_amount
                ORDER BY t.report_year;
                """
            )
            tracked_mismatches = cursor.fetchall()
            checks.append(
                Check(
                    "Tracked CHIP amounts match dedicated CHIP view",
                    not tracked_mismatches,
                    f"mismatches={tracked_mismatches}",
                )
            )

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM chip.v_cms21_control_totals
                WHERE state_abbreviation = 'WA'
                  AND is_financing_adjustment = TRUE
                  AND is_additive_expenditure = TRUE;
                """
            )
            incorrectly_additive_adjustments = int(cursor.fetchone()[0])
            checks.append(
                Check(
                    "Financing adjustments remain non-additive",
                    incorrectly_additive_adjustments == 0,
                    f"incorrectly_additive={incorrectly_additive_adjustments}",
                )
            )

            cursor.execute(
                """
                SELECT
                    fiscal_year,
                    federal_expenditure_amount,
                    included_worksheet_types
                FROM reporting.v_washington_chip_expenditures
                ORDER BY fiscal_year;
                """
            )
            summary_rows = cursor.fetchall()

    print("WASHINGTON CHIP REPORTING VALIDATION")
    print("=" * 100)

    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"[{status}] {check.name}")
        print(f"       {check.detail}")

    print()
    print("ANNUAL CHIP FEDERAL EXPENDITURES")
    print("-" * 100)
    for year, amount, worksheet_types in summary_rows:
        print(f"FY{year}  ${int(amount):>15,}  {worksheet_types}")

    overall_passed = all(check.passed for check in checks)

    print()
    print("=" * 100)
    print(f"OVERALL RESULT: {'PASS' if overall_passed else 'FAIL'}")

    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())