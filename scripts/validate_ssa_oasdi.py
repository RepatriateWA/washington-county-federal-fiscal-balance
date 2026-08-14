from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from etl.common.db import get_connection
from etl.validation.procurement import checks


# SSA Table 5 monetary amounts are published in $000s.
# Component categories and TOTAL are independently rounded.
#
# With eight component categories, a conservative county-level tolerance
# of $5,000 accommodates the theoretical accumulation of source rounding
# while remaining far tighter than any analytically meaningful difference.
MONTHLY_ROUNDING_TOLERANCE_THOUSANDS = Decimal("5")

# Annualized amounts are derived as December monthly amount × 12.
ANNUAL_ROUNDING_TOLERANCE_THOUSANDS = (
    MONTHLY_ROUNDING_TOLERANCE_THOUSANDS * Decimal("12")
)

# Statewide reporting is component-derived across 39 counties.
# 39 counties × $5,000 monthly tolerance × 12 months.
STATEWIDE_ROUNDING_TOLERANCE_DOLLARS = (
    Decimal("39")
    * MONTHLY_ROUNDING_TOLERANCE_THOUSANDS
    * Decimal("1000")
    * Decimal("12")
)

YEARS = tuple(range(2015, 2025))
EXPECTED_COUNTIES = 39
EXPECTED_BENEFIT_TYPES = 9
EXPECTED_ROWS_PER_YEAR = 351
EXPECTED_TOTAL_ROWS = 3510
EXPECTED_TOTAL_CONTROL_ROWS = 390


@dataclass(frozen=True)
class Check:
    code: str
    label: str
    passed: bool
    detail: str


def add_check(checks, code, label, passed, detail):
    checks.append(Check(code, label, passed, detail))


def print_check(check):
    status = "PASS" if check.passed else "FAIL"
    print(f"[{status}] {check.code:<11} {check.label:<62} {check.detail}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()[0]


def main() -> int:
    checks = []
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            total_rows = int(scalar(cur, """
                SELECT COUNT(*)
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024
                  AND agency_code = 'SSA';
            """))
            add_check(
                checks, "POP-001",
                "Total FY2015-FY2024 SSA OASDI observation count",
                total_rows == EXPECTED_TOTAL_ROWS,
                f"actual={total_rows:,}; expected={EXPECTED_TOTAL_ROWS:,}",
            )

            cur.execute("""
                SELECT
                    report_year,
                    COUNT(*) AS rows,
                    COUNT(DISTINCT county_id) AS counties,
                    COUNT(DISTINCT ssa_benefit_type_id) AS benefit_types
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024
                  AND agency_code = 'SSA'
                GROUP BY report_year
                ORDER BY report_year;
            """)
            by_year = {
                int(y): (int(r), int(c), int(t))
                for y, r, c, t in cur.fetchall()
            }

            missing_years = sorted(set(YEARS) - set(by_year))
            row_errors = []
            county_errors = []
            type_errors = []

            for year in YEARS:
                rows, counties, types = by_year.get(year, (0, 0, 0))
                if rows != EXPECTED_ROWS_PER_YEAR:
                    row_errors.append((year, rows))
                if counties != EXPECTED_COUNTIES:
                    county_errors.append((year, counties))
                if types != EXPECTED_BENEFIT_TYPES:
                    type_errors.append((year, types))

            add_check(
                checks, "POP-002", "All ten report years are present",
                not missing_years,
                "FY2015-FY2024" if not missing_years else f"missing={missing_years}",
            )
            add_check(
                checks, "POP-003", "Exactly 351 observations per report year",
                not row_errors,
                "10/10 years" if not row_errors else f"exceptions={row_errors}",
            )
            add_check(
                checks, "POP-004", "Exactly 39 Washington counties per report year",
                not county_errors,
                "10/10 years" if not county_errors else f"exceptions={county_errors}",
            )
            add_check(
                checks, "POP-005", "Exactly 9 OASDI benefit types per report year",
                not type_errors,
                "10/10 years" if not type_errors else f"exceptions={type_errors}",
            )

            duplicates = int(scalar(cur, """
                SELECT COUNT(*)
                FROM (
                    SELECT
                        report_year,
                        county_id,
                        ssa_benefit_type_id,
                        COUNT(*) AS n
                    FROM ssa.benefit_payments
                    WHERE report_year BETWEEN 2015 AND 2024
                      AND agency_code = 'SSA'
                    GROUP BY report_year, county_id, ssa_benefit_type_id
                    HAVING COUNT(*) > 1
                ) AS d;
            """))
            add_check(
                checks, "KEY-001",
                "Year/county/benefit-type observations are unique",
                duplicates == 0,
                f"{duplicates} duplicate keys",
            )

            orphan_counties = int(scalar(cur, """
                SELECT COUNT(*)
                FROM ssa.benefit_payments AS bp
                LEFT JOIN reference.county_registry AS c
                  ON c.county_id = bp.county_id
                WHERE bp.report_year BETWEEN 2015 AND 2024
                  AND bp.agency_code = 'SSA'
                  AND c.county_id IS NULL;
            """))
            add_check(
                checks, "REF-001",
                "All observations resolve to canonical county references",
                orphan_counties == 0,
                f"{orphan_counties} orphan rows",
            )

            orphan_types = int(scalar(cur, """
                SELECT COUNT(*)
                FROM ssa.benefit_payments AS bp
                LEFT JOIN reference.ssa_benefit_type AS bt
                  ON bt.ssa_benefit_type_id = bp.ssa_benefit_type_id
                WHERE bp.report_year BETWEEN 2015 AND 2024
                  AND bp.agency_code = 'SSA'
                  AND bt.ssa_benefit_type_id IS NULL;
            """))
            add_check(
                checks, "REF-002",
                "All observations resolve to SSA benefit-type references",
                orphan_types == 0,
                f"{orphan_types} orphan rows",
            )

            non_ssa = int(scalar(cur, """
                SELECT COUNT(*)
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024
                  AND agency_code IS DISTINCT FROM 'SSA';
            """))
            add_check(
                checks, "REF-003",
                "All observations carry agency_code='SSA'",
                non_ssa == 0,
                f"{non_ssa} exceptions",
            )

            annualization_errors = int(scalar(cur, """
                SELECT COUNT(*)
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024
                  AND agency_code = 'SSA'
                  AND annual_benefits_thousands
                      IS DISTINCT FROM monthly_benefits_thousands * 12;
            """))
            add_check(
                checks, "MEAS-001",
                "Annualized amount equals December monthly amount x 12",
                annualization_errors == 0,
                f"{annualization_errors} mismatches",
            )

            total_controls = int(scalar(cur, """
                SELECT COUNT(*)
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024
                  AND agency_code = 'SSA'
                  AND UPPER(TRIM(benefit_type)) = 'TOTAL';
            """))
            add_check(
                checks, "CTRL-001",
                "Exactly one TOTAL control observation per county/year",
                total_controls == EXPECTED_TOTAL_CONTROL_ROWS,
                f"actual={total_controls}; expected={EXPECTED_TOTAL_CONTROL_ROWS}",
            )

            cur.execute("""
                WITH county_values AS (
                    SELECT
                        report_year,
                        county_id,
                        MAX(beneficiary_count) FILTER (
                            WHERE UPPER(TRIM(benefit_type)) = 'TOTAL'
                        ) AS total_beneficiaries,
                        SUM(beneficiary_count) FILTER (
                            WHERE UPPER(TRIM(benefit_type)) <> 'TOTAL'
                        ) AS component_beneficiaries,
                        MAX(monthly_benefits_thousands) FILTER (
                            WHERE UPPER(TRIM(benefit_type)) = 'TOTAL'
                        ) AS total_monthly,
                        SUM(monthly_benefits_thousands) FILTER (
                            WHERE UPPER(TRIM(benefit_type)) <> 'TOTAL'
                        ) AS component_monthly,
                        MAX(annual_benefits_thousands) FILTER (
                            WHERE UPPER(TRIM(benefit_type)) = 'TOTAL'
                        ) AS total_annualized,
                        SUM(annual_benefits_thousands) FILTER (
                            WHERE UPPER(TRIM(benefit_type)) <> 'TOTAL'
                        ) AS component_annualized
                    FROM ssa.benefit_payments
                    WHERE report_year BETWEEN 2015 AND 2024
                      AND agency_code = 'SSA'
                    GROUP BY report_year, county_id
                )
                SELECT
                    report_year,
                    county_id,
                    total_beneficiaries,
                    component_beneficiaries,
                    total_monthly,
                    component_monthly,
                    total_annualized,
                    component_annualized
                FROM county_values
                ORDER BY report_year, county_id;
            """)

            beneficiary_failures = []
            monthly_failures = []
            annual_failures = []

            for row in cur.fetchall():
                (
                    year, county_id,
                    tb, cb,
                    tm, cm,
                    ta, ca,
                ) = row

                if tb is None or cb is None or int(tb) != int(cb):
                    beneficiary_failures.append((year, county_id, tb, cb))

                if (
                    tm is None or cm is None
                    or abs(Decimal(tm) - Decimal(cm)) > MONTHLY_ROUNDING_TOLERANCE_THOUSANDS
                ):
                    monthly_failures.append((year, county_id, tm, cm))

                if (
                    ta is None or ca is None
                    or abs(Decimal(ta) - Decimal(ca)) > ANNUAL_ROUNDING_TOLERANCE_THOUSANDS
                ):
                    annual_failures.append((year, county_id, ta, ca))

            add_check(
                checks, "RECON-001",
                "TOTAL beneficiaries equal sum of component benefit types",
                not beneficiary_failures,
                "390/390 county-years" if not beneficiary_failures
                else f"{len(beneficiary_failures)} failures",
            )
            
            unmapped_non_total = int(scalar(cur, """
                SELECT COUNT(*)
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024
                  AND agency_code = 'SSA'
                  AND UPPER(TRIM(benefit_type)) <> 'TOTAL'
                  AND federal_program_id IS NULL;
            """))
            add_check(
                checks, "PROG-001",
                "Non-TOTAL observations map to a federal program",
                unmapped_non_total == 0,
                f"{unmapped_non_total} unmapped rows",
            )

            mapped_total = int(scalar(cur, """
                SELECT COUNT(*)
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024
                  AND agency_code = 'SSA'
                  AND UPPER(TRIM(benefit_type)) = 'TOTAL'
                  AND federal_program_id IS NOT NULL;
            """))
            add_check(
                checks, "PROG-002",
                "TOTAL controls remain intentionally unmapped to one program",
                mapped_total == 0,
                f"{mapped_total} incorrectly mapped TOTAL rows",
            )

            cur.execute("""
                WITH controls AS (
                    SELECT
                        report_year,
                        SUM(annual_benefits_thousands) * 1000 AS control_dollars
                    FROM ssa.benefit_payments
                    WHERE report_year BETWEEN 2015 AND 2024
                      AND agency_code = 'SSA'
                      AND UPPER(TRIM(benefit_type)) = 'TOTAL'
                    GROUP BY report_year
                ),
                reporting AS (
                    SELECT
                        report_year,
                        SUM(annualized_benefits_dollars) AS reporting_dollars
                    FROM reporting.v_washington_ssa_summary
                    WHERE report_year BETWEEN 2015 AND 2024
                    GROUP BY report_year
                )
                SELECT
                    c.report_year,
                    c.control_dollars,
                    r.reporting_dollars,
                    ABS(c.control_dollars - r.reporting_dollars) AS difference
                FROM controls AS c
                FULL OUTER JOIN reporting AS r
                  ON r.report_year = c.report_year
                WHERE c.control_dollars IS NULL
                   OR r.reporting_dollars IS NULL
                   OR ABS(c.control_dollars - r.reporting_dollars) > %s
                ORDER BY COALESCE(c.report_year, r.report_year);
            """, (STATEWIDE_ROUNDING_TOLERANCE_DOLLARS,))
            view_failures = cur.fetchall()

            add_check(
                checks, "VIEW-001",
                "Component-derived reporting view agrees with published TOTAL within SSA rounding bounds",
                not view_failures,
                "10/10 years" if not view_failures
                else f"{len(view_failures)} failures",
            )

            add_check(
                checks,
                "RECON-002",
                "Published TOTAL monthly benefits reconcile to components within $000 source-rounding bounds",
                not monthly_failures,
                (
                    "390/390 county-years within ±$5,000"
                    if not monthly_failures
                    else f"{len(monthly_failures)} failures"
                ),
            )

            add_check(
                checks,
                "RECON-003",
                "Annualized TOTAL benefits reconcile to components within propagated source-rounding bounds",
                not annual_failures,
                (
                    "390/390 county-years within ±$60,000 annualized"
                    if not annual_failures
                    else f"{len(annual_failures)} failures"
                ),
            )

            cur.execute("""
                SELECT
                    report_year,
                    SUM(beneficiary_count) AS beneficiaries,
                    SUM(monthly_benefits_thousands) AS monthly_thousands,
                    SUM(annual_benefits_thousands) AS annualized_thousands
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024
                  AND agency_code = 'SSA'
                  AND UPPER(TRIM(benefit_type)) = 'TOTAL'
                GROUP BY report_year
                ORDER BY report_year;
            """)
            annual_controls = cur.fetchall()

    finally:
        conn.close()

    print("=" * 110)
    print("SSA OASDI FY2015-FY2024 VALIDATION — WASHINGTON COUNTY SERIES")
    print("=" * 110)
    print()

    for section, prefixes in [
        ("POPULATION / COVERAGE", {"POP"}),
        ("UNIQUENESS / REFERENCES", {"KEY", "REF"}),
        ("MEASURE INTEGRITY", {"MEAS", "CTRL"}),
        ("COUNTY CONTROL RECONCILIATION", {"RECON"}),
        ("PROGRAM / REPORTING INTEGRATION", {"PROG", "VIEW"}),
    ]:
        print("-" * 110)
        print(section)
        print("-" * 110)
        for check in checks:
            if check.code.split("-")[0] in prefixes:
                print_check(check)
        print()

    print("-" * 110)
    print("WASHINGTON SSA OASDI ANNUAL CONTROL TOTALS")
    print("-" * 110)
    print(
        "NOTE: annualized dollars = December monthly benefit amount x 12; "
        "not observed FFY cash outlays."
    )
    print()

    for year, beneficiaries, monthly_thousands, annualized_thousands in annual_controls:
        monthly_dollars = Decimal(monthly_thousands) * Decimal("1000")
        annualized_dollars = Decimal(annualized_thousands) * Decimal("1000")
        print(
            f"{year}  beneficiaries={int(beneficiaries):>10,}  "
            f"December=${monthly_dollars:>18,.2f}  "
            f"annualized=${annualized_dollars:>20,.2f}"
        )

    passed = sum(1 for check in checks if check.passed)
    failed = len(checks) - passed

    print()
    print("=" * 110)
    print(f"Checks passed ..................... {passed}")
    print(f"Checks failed ..................... {failed}")
    print()

    if failed == 0:
        print("OVERALL RESULT: PASS")
        print("=" * 110)
        return 0

    print("OVERALL RESULT: FAIL")
    print("=" * 110)
    print()
    print("FAILED CHECKS")
    print("-" * 110)
    for check in checks:
        if not check.passed:
            print_check(check)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())