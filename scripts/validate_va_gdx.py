"""
Validate VA Geographic Distribution of Expenditures (GDX) FY2015-FY2024.

Checks
------
1. Completed load batch exists for every fiscal year.
2. Exactly one completed source-hash batch per fiscal year.
3. 39 Washington counties represented in expenditures every year.
4. Expected expenditure observation counts:
       FY2015-FY2023: 312 per year
       FY2024:        429
5. Expected metric observation counts:
       FY2015-FY2023: 78 per year
       FY2024:         0
6. No duplicate county/category/source-class observations.
7. No duplicate source locations.
8. Legacy years contain exactly the expected category population.
9. Legacy source units are USD_THOUSANDS.
10. FY2024 source units are USD.
11. Legacy county Total Expenditure reconciles to the sum of components.
12. FY2024 Total Direct Expenditure reconciles to direct components.
13. FY2024 Total Indirect Expenditure reconciles to indirect components.
14. FY2024 direct and indirect county populations match.
15. County control-total view contains exactly 39 counties per year.
16. County control-total view agrees with source control rows in the
    normalized expenditure table.
17. Prints statewide Washington annual VA GDX control totals.

Reconciliation tolerance
------------------------
Amounts are stored as NUMERIC(24,2) after normalization to dollars.
Component sums are therefore compared to source control totals with
a $0.10 tolerance to permit harmless cent-rounding accumulation across
multiple source components while still catching substantive mismatches.

Usage
-----
    python -m scripts.validate_va_gdx
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from etl.common.db import get_connection


YEARS = tuple(range(2015, 2025))
LEGACY_YEARS = tuple(range(2015, 2024))
REVISED_YEAR = 2024

EXPECTED_COUNTIES = 39
EXPECTED_LEGACY_EXPENDITURES = 312
EXPECTED_LEGACY_METRICS = 78
EXPECTED_2024_EXPENDITURES = 429
EXPECTED_2024_METRICS = 0

TOLERANCE = Decimal("0.10")

LEGACY_COMPONENT_CODES = {
    "COMPENSATION_PENSION",
    "CONSTRUCTION",
    "EDUCATION_VRE",
    "LOAN_GUARANTY",
    "GENERAL_OPERATING_EXPENSES",
    "INSURANCE_INDEMNITIES",
    "MEDICAL_CARE",
}

LEGACY_ALL_CODES = LEGACY_COMPONENT_CODES | {
    "TOTAL_EXPENDITURE",
}

DIRECT_2024_COMPONENT_CODES = {
    "COMPENSATION_PENSION",
    "INSURANCE",
    "DIC_SURVIVORS_PENSION",
}

DIRECT_2024_ALL_CODES = DIRECT_2024_COMPONENT_CODES | {
    "TOTAL_DIRECT_EXPENDITURE",
}

INDIRECT_2024_COMPONENT_CODES = {
    "MEMORIAL_BENEFITS",
    "CONSTRUCTION",
    "EDUCATION_VRE",
    "LOAN_GUARANTY",
    "MEDICAL_CARE",
    "SPECIALLY_ADAPTED_HOUSING_AUTOMOBILES",
}

INDIRECT_2024_ALL_CODES = INDIRECT_2024_COMPONENT_CODES | {
    "TOTAL_INDIRECT_EXPENDITURE",
}


@dataclass(frozen=True)
class Check:
    code: str
    label: str
    passed: bool
    detail: str


def add_check(
    checks: list[Check],
    code: str,
    label: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append(
        Check(
            code=code,
            label=label,
            passed=passed,
            detail=detail,
        )
    )


def print_check(check: Check) -> None:
    status = "PASS" if check.passed else "FAIL"
    print(
        f"[{status}] {check.code:<10} "
        f"{check.label:<58} {check.detail}"
    )


def validate_load_batches(cur, checks: list[Check]) -> None:
    cur.execute(
        """
        SELECT
            fiscal_year,
            COUNT(*) FILTER (WHERE load_status = 'COMPLETED') AS completed_count,
            COUNT(*) AS all_count
        FROM va.gdx_load_batch
        WHERE fiscal_year BETWEEN 2015 AND 2024
        GROUP BY fiscal_year
        ORDER BY fiscal_year;
        """
    )

    rows = {
        int(year): (int(completed_count), int(all_count))
        for year, completed_count, all_count in cur.fetchall()
    }

    missing = [
        year
        for year in YEARS
        if rows.get(year, (0, 0))[0] != 1
    ]

    add_check(
        checks,
        "BATCH-001",
        "Exactly one completed GDX batch per fiscal year",
        not missing,
        (
            "FY2015-FY2024"
            if not missing
            else f"exceptions={missing}"
        ),
    )

    cur.execute(
        """
        SELECT fiscal_year, source_sha256, COUNT(*)
        FROM va.gdx_load_batch
        WHERE fiscal_year BETWEEN 2015 AND 2024
          AND load_status = 'COMPLETED'
        GROUP BY fiscal_year, source_sha256
        HAVING COUNT(*) > 1
        ORDER BY fiscal_year;
        """
    )

    duplicate_hash_batches = cur.fetchall()

    add_check(
        checks,
        "BATCH-002",
        "Completed year/source-hash batches are unique",
        not duplicate_hash_batches,
        (
            "0 duplicates"
            if not duplicate_hash_batches
            else f"duplicates={duplicate_hash_batches}"
        ),
    )


def validate_year_counts(cur, checks: list[Check]) -> None:
    cur.execute(
        """
        SELECT
            fiscal_year,
            COUNT(*) AS expenditure_rows,
            COUNT(DISTINCT county_id) AS counties
        FROM va.gdx_county_expenditure
        WHERE fiscal_year BETWEEN 2015 AND 2024
        GROUP BY fiscal_year
        ORDER BY fiscal_year;
        """
    )

    expenditure_rows = {
        int(year): (int(row_count), int(counties))
        for year, row_count, counties in cur.fetchall()
    }

    bad_counts = []

    for year in YEARS:
        expected_rows = (
            EXPECTED_2024_EXPENDITURES
            if year == REVISED_YEAR
            else EXPECTED_LEGACY_EXPENDITURES
        )

        actual_rows, counties = expenditure_rows.get(
            year,
            (0, 0),
        )

        if (
            actual_rows != expected_rows
            or counties != EXPECTED_COUNTIES
        ):
            bad_counts.append(
                (
                    year,
                    expected_rows,
                    actual_rows,
                    counties,
                )
            )

    add_check(
        checks,
        "COUNT-001",
        "Expenditure row counts and 39-county coverage",
        not bad_counts,
        (
            "all years correct"
            if not bad_counts
            else f"exceptions={bad_counts}"
        ),
    )

    cur.execute(
        """
        SELECT fiscal_year, COUNT(*)
        FROM va.gdx_county_metric
        WHERE fiscal_year BETWEEN 2015 AND 2024
        GROUP BY fiscal_year
        ORDER BY fiscal_year;
        """
    )

    metric_rows = {
        int(year): int(row_count)
        for year, row_count in cur.fetchall()
    }

    bad_metric_counts = []

    for year in YEARS:
        expected = (
            EXPECTED_2024_METRICS
            if year == REVISED_YEAR
            else EXPECTED_LEGACY_METRICS
        )

        actual = metric_rows.get(
            year,
            0,
        )

        if actual != expected:
            bad_metric_counts.append(
                (
                    year,
                    expected,
                    actual,
                )
            )

    add_check(
        checks,
        "COUNT-002",
        "Metric row counts",
        not bad_metric_counts,
        (
            "FY2015-FY2023=78; FY2024=0"
            if not bad_metric_counts
            else f"exceptions={bad_metric_counts}"
        ),
    )


def validate_duplicates(cur, checks: list[Check]) -> None:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                fiscal_year,
                county_id,
                expenditure_class,
                gdx_category_id,
                COUNT(*) AS n
            FROM va.gdx_county_expenditure
            WHERE fiscal_year BETWEEN 2015 AND 2024
            GROUP BY
                fiscal_year,
                county_id,
                expenditure_class,
                gdx_category_id
            HAVING COUNT(*) > 1
        ) AS d;
        """
    )

    duplicate_observations = int(
        cur.fetchone()[0]
    )

    add_check(
        checks,
        "DUP-001",
        "County/category/class expenditure observations are unique",
        duplicate_observations == 0,
        f"{duplicate_observations} duplicates",
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                gdx_load_batch_id,
                source_sheet,
                source_row_number,
                source_column_number,
                COUNT(*) AS n
            FROM va.gdx_county_expenditure
            GROUP BY
                gdx_load_batch_id,
                source_sheet,
                source_row_number,
                source_column_number
            HAVING COUNT(*) > 1
        ) AS d;
        """
    )

    duplicate_source_locations = int(
        cur.fetchone()[0]
    )

    add_check(
        checks,
        "DUP-002",
        "Expenditure source locations are unique",
        duplicate_source_locations == 0,
        f"{duplicate_source_locations} duplicates",
    )


def validate_categories(cur, checks: list[Check]) -> None:
    cur.execute(
        """
        SELECT DISTINCT
            e.fiscal_year,
            c.category_code
        FROM va.gdx_county_expenditure AS e
        JOIN va.gdx_expenditure_category AS c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year BETWEEN 2015 AND 2024
        ORDER BY e.fiscal_year, c.category_code;
        """
    )

    categories: dict[int, set[str]] = {
        year: set()
        for year in YEARS
    }

    for year, code in cur.fetchall():
        categories[int(year)].add(
            str(code)
        )

    legacy_bad = [
        (
            year,
            sorted(categories[year]),
        )
        for year in LEGACY_YEARS
        if categories[year] != LEGACY_ALL_CODES
    ]

    add_check(
        checks,
        "CAT-001",
        "Legacy category population is exact",
        not legacy_bad,
        (
            "8 expected categories"
            if not legacy_bad
            else f"exceptions={legacy_bad}"
        ),
    )

    cur.execute(
        """
        SELECT DISTINCT
            e.expenditure_class,
            c.category_code
        FROM va.gdx_county_expenditure AS e
        JOIN va.gdx_expenditure_category AS c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year = 2024
        ORDER BY e.expenditure_class, c.category_code;
        """
    )

    revised: dict[str, set[str]] = {
        "DIRECT": set(),
        "INDIRECT": set(),
    }

    for expenditure_class, code in cur.fetchall():
        revised[str(expenditure_class)].add(
            str(code)
        )

    revised_ok = (
        revised.get("DIRECT", set())
        == DIRECT_2024_ALL_CODES
        and revised.get("INDIRECT", set())
        == INDIRECT_2024_ALL_CODES
    )

    add_check(
        checks,
        "CAT-002",
        "FY2024 Direct/Indirect category populations are exact",
        revised_ok,
        (
            "DIRECT=4; INDIRECT=7"
            if revised_ok
            else f"actual={revised}"
        ),
    )


def validate_units(cur, checks: list[Check]) -> None:
    cur.execute(
        """
        SELECT fiscal_year, source_unit, COUNT(*)
        FROM va.gdx_county_expenditure
        WHERE fiscal_year BETWEEN 2015 AND 2024
        GROUP BY fiscal_year, source_unit
        ORDER BY fiscal_year, source_unit;
        """
    )

    bad = []

    for year, source_unit, row_count in cur.fetchall():
        year = int(year)
        expected = (
            "USD"
            if year == 2024
            else "USD_THOUSANDS"
        )

        if str(source_unit) != expected:
            bad.append(
                (
                    year,
                    source_unit,
                    row_count,
                )
            )

    add_check(
        checks,
        "UNIT-001",
        "Source-unit regime is correct by methodology era",
        not bad,
        (
            "legacy=USD_THOUSANDS; FY2024=USD"
            if not bad
            else f"exceptions={bad}"
        ),
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM va.gdx_county_expenditure
        WHERE fiscal_year BETWEEN 2015 AND 2023
          AND expenditure_amount
              <> ROUND(source_amount * 1000, 2);
        """
    )

    legacy_conversion_errors = int(
        cur.fetchone()[0]
    )

    add_check(
        checks,
        "UNIT-002",
        "Legacy $000 source values normalize correctly to dollars",
        legacy_conversion_errors == 0,
        f"{legacy_conversion_errors} mismatches",
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM va.gdx_county_expenditure
        WHERE fiscal_year = 2024
          AND expenditure_amount
              <> ROUND(source_amount, 2);
        """
    )

    revised_conversion_errors = int(
        cur.fetchone()[0]
    )

    add_check(
        checks,
        "UNIT-003",
        "FY2024 dollar source values normalize correctly",
        revised_conversion_errors == 0,
        f"{revised_conversion_errors} mismatches",
    )


def validate_legacy_reconciliation(
    cur,
    checks: list[Check],
) -> None:
    cur.execute(
        """
        WITH classified AS (
            SELECT
                e.fiscal_year,
                e.county_id,
                c.category_code,
                e.expenditure_amount
            FROM va.gdx_county_expenditure AS e
            JOIN va.gdx_expenditure_category AS c
              ON c.gdx_category_id = e.gdx_category_id
            WHERE e.fiscal_year BETWEEN 2015 AND 2023
        ),
        county_recon AS (
            SELECT
                fiscal_year,
                county_id,
                MAX(expenditure_amount)
                    FILTER (
                        WHERE category_code = 'TOTAL_EXPENDITURE'
                    ) AS control_total,
                SUM(expenditure_amount)
                    FILTER (
                        WHERE category_code <> 'TOTAL_EXPENDITURE'
                    ) AS component_total
            FROM classified
            GROUP BY fiscal_year, county_id
        )
        SELECT
            fiscal_year,
            county_id,
            control_total,
            component_total,
            ABS(control_total - component_total) AS difference
        FROM county_recon
        WHERE control_total IS NULL
           OR component_total IS NULL
           OR ABS(control_total - component_total) > %s
        ORDER BY fiscal_year, county_id;
        """,
        (TOLERANCE,),
    )

    failures = cur.fetchall()

    add_check(
        checks,
        "FIN-001",
        "Legacy county totals reconcile to component sums",
        not failures,
        (
            f"351/351 counties within ${TOLERANCE}"
            if not failures
            else f"{len(failures)} failures"
        ),
    )

    if failures:
        print()
        print("Legacy reconciliation exceptions:")
        for row in failures[:20]:
            print(" ", row)


def validate_fy2024_reconciliation(
    cur,
    checks: list[Check],
) -> None:
    cur.execute(
        """
        WITH classified AS (
            SELECT
                e.county_id,
                e.expenditure_class,
                c.category_code,
                e.expenditure_amount
            FROM va.gdx_county_expenditure AS e
            JOIN va.gdx_expenditure_category AS c
              ON c.gdx_category_id = e.gdx_category_id
            WHERE e.fiscal_year = 2024
        ),
        direct_recon AS (
            SELECT
                county_id,
                MAX(expenditure_amount)
                    FILTER (
                        WHERE category_code =
                            'TOTAL_DIRECT_EXPENDITURE'
                    ) AS control_total,
                SUM(expenditure_amount)
                    FILTER (
                        WHERE category_code <>
                            'TOTAL_DIRECT_EXPENDITURE'
                    ) AS component_total
            FROM classified
            WHERE expenditure_class = 'DIRECT'
            GROUP BY county_id
        )
        SELECT
            county_id,
            control_total,
            component_total,
            ABS(control_total - component_total) AS difference
        FROM direct_recon
        WHERE control_total IS NULL
           OR component_total IS NULL
           OR ABS(control_total - component_total) > %s
        ORDER BY county_id;
        """,
        (TOLERANCE,),
    )

    direct_failures = cur.fetchall()

    add_check(
        checks,
        "FIN-002",
        "FY2024 Direct totals reconcile to component sums",
        not direct_failures,
        (
            f"39/39 counties within ${TOLERANCE}"
            if not direct_failures
            else f"{len(direct_failures)} failures"
        ),
    )

    cur.execute(
        """
        WITH classified AS (
            SELECT
                e.county_id,
                e.expenditure_class,
                c.category_code,
                e.expenditure_amount
            FROM va.gdx_county_expenditure AS e
            JOIN va.gdx_expenditure_category AS c
              ON c.gdx_category_id = e.gdx_category_id
            WHERE e.fiscal_year = 2024
        ),
        indirect_recon AS (
            SELECT
                county_id,
                MAX(expenditure_amount)
                    FILTER (
                        WHERE category_code =
                            'TOTAL_INDIRECT_EXPENDITURE'
                    ) AS control_total,
                SUM(expenditure_amount)
                    FILTER (
                        WHERE category_code <>
                            'TOTAL_INDIRECT_EXPENDITURE'
                    ) AS component_total
            FROM classified
            WHERE expenditure_class = 'INDIRECT'
            GROUP BY county_id
        )
        SELECT
            county_id,
            control_total,
            component_total,
            ABS(control_total - component_total) AS difference
        FROM indirect_recon
        WHERE control_total IS NULL
           OR component_total IS NULL
           OR ABS(control_total - component_total) > %s
        ORDER BY county_id;
        """,
        (TOLERANCE,),
    )

    indirect_failures = cur.fetchall()

    add_check(
        checks,
        "FIN-003",
        "FY2024 Indirect totals reconcile to component sums",
        not indirect_failures,
        (
            f"39/39 counties within ${TOLERANCE}"
            if not indirect_failures
            else f"{len(indirect_failures)} failures"
        ),
    )

    cur.execute(
        """
        SELECT expenditure_class, COUNT(DISTINCT county_id)
        FROM va.gdx_county_expenditure
        WHERE fiscal_year = 2024
        GROUP BY expenditure_class
        ORDER BY expenditure_class;
        """
    )

    class_counts = {
        str(expenditure_class): int(counties)
        for expenditure_class, counties in cur.fetchall()
    }

    populations_match = (
        class_counts.get("DIRECT") == EXPECTED_COUNTIES
        and class_counts.get("INDIRECT") == EXPECTED_COUNTIES
    )

    add_check(
        checks,
        "FIN-004",
        "FY2024 Direct/Indirect county populations are complete",
        populations_match,
        f"{class_counts}",
    )

    if direct_failures:
        print()
        print("FY2024 Direct reconciliation exceptions:")
        for row in direct_failures[:20]:
            print(" ", row)

    if indirect_failures:
        print()
        print("FY2024 Indirect reconciliation exceptions:")
        for row in indirect_failures[:20]:
            print(" ", row)


def validate_control_view(
    cur,
    checks: list[Check],
) -> list[tuple[int, Decimal]]:
    cur.execute(
        """
        SELECT
            fiscal_year,
            COUNT(*) AS county_rows,
            SUM(va_gdx_expenditure_amount) AS state_total
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2015 AND 2024
        GROUP BY fiscal_year
        ORDER BY fiscal_year;
        """
    )

    rows = [
        (
            int(year),
            int(county_rows),
            Decimal(state_total),
        )
        for year, county_rows, state_total in cur.fetchall()
    ]

    bad_counties = [
        (
            year,
            county_rows,
        )
        for year, county_rows, _ in rows
        if county_rows != EXPECTED_COUNTIES
    ]

    years_present = {
        year
        for year, _, _ in rows
    }

    missing_years = sorted(
        set(YEARS) - years_present
    )

    view_ok = (
        not bad_counties
        and not missing_years
    )

    add_check(
        checks,
        "VIEW-001",
        "County control-total view has 39 rows for every year",
        view_ok,
        (
            "FY2015-FY2024"
            if view_ok
            else (
                f"bad_counts={bad_counties}, "
                f"missing={missing_years}"
            )
        ),
    )

    cur.execute(
        """
        WITH expected AS (
            SELECT
                e.fiscal_year,
                e.county_id,
                SUM(e.expenditure_amount) AS expected_amount
            FROM va.gdx_county_expenditure AS e
            JOIN va.gdx_expenditure_category AS c
              ON c.gdx_category_id = e.gdx_category_id
            WHERE (
                e.fiscal_year BETWEEN 2015 AND 2023
                AND c.category_code = 'TOTAL_EXPENDITURE'
            )
            OR (
                e.fiscal_year = 2024
                AND c.category_code IN (
                    'TOTAL_DIRECT_EXPENDITURE',
                    'TOTAL_INDIRECT_EXPENDITURE'
                )
            )
            GROUP BY
                e.fiscal_year,
                e.county_id
        )
        SELECT COUNT(*)
        FROM expected AS x
        FULL OUTER JOIN va.v_washington_county_gdx_control_total AS v
          ON v.fiscal_year = x.fiscal_year
         AND v.county_id = x.county_id
        WHERE x.expected_amount IS DISTINCT FROM
              v.va_gdx_expenditure_amount;
        """
    )

    view_mismatches = int(
        cur.fetchone()[0]
    )

    add_check(
        checks,
        "VIEW-002",
        "Control-total view agrees with normalized source controls",
        view_mismatches == 0,
        f"{view_mismatches} mismatches",
    )

    return [
        (
            year,
            state_total,
        )
        for year, _, state_total in rows
    ]


def validate_null_amounts(
    cur,
    checks: list[Check],
) -> None:
    # Control totals must always be numeric.
    cur.execute(
        """
        SELECT COUNT(*)
        FROM va.gdx_county_expenditure AS e
        JOIN va.gdx_expenditure_category AS c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year BETWEEN 2015 AND 2024
          AND c.category_code IN (
              'TOTAL_EXPENDITURE',
              'TOTAL_DIRECT_EXPENDITURE',
              'TOTAL_INDIRECT_EXPENDITURE'
          )
          AND (
              e.source_amount IS NULL
              OR e.expenditure_amount IS NULL
          );
        """
    )

    null_control_totals = int(
        cur.fetchone()[0]
    )

    add_check(
        checks,
        "NULL-001",
        "Control-total observations contain numeric amounts",
        null_control_totals == 0,
        f"{null_control_totals} null control-total rows",
    )

    # Component blanks are preserved as NULL when the VA source cell
    # itself is blank. These are allowed, provided reconciliation passes.
    cur.execute(
        """
        SELECT COUNT(*)
        FROM va.gdx_county_expenditure AS e
        JOIN va.gdx_expenditure_category AS c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year BETWEEN 2015 AND 2024
          AND c.aggregation_role = 'COMPONENT'
          AND (
              e.source_amount IS NULL
              OR e.expenditure_amount IS NULL
          );
        """
    )

    null_component_rows = int(
        cur.fetchone()[0]
    )

    add_check(
        checks,
        "NULL-002",
        "Source-blank component observations are preserved",
        True,
        f"{null_component_rows} source-blank component rows",
    )


def main() -> int:
    checks: list[Check] = []

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            validate_load_batches(
                cur,
                checks,
            )
            validate_year_counts(
                cur,
                checks,
            )
            validate_duplicates(
                cur,
                checks,
            )
            validate_categories(
                cur,
                checks,
            )
            validate_units(
                cur,
                checks,
            )
            validate_null_amounts(
                cur,
                checks,
            )
            validate_legacy_reconciliation(
                cur,
                checks,
            )
            validate_fy2024_reconciliation(
                cur,
                checks,
            )
            annual_totals = validate_control_view(
                cur,
                checks,
            )

    finally:
        conn.close()

    print("=" * 104)
    print("VA GDX FY2015-FY2024 VALIDATION")
    print("=" * 104)
    print()

    sections = [
        (
            "LOAD / COVERAGE",
            {"BATCH", "COUNT"},
        ),
        (
            "UNIQUENESS / CATEGORIES",
            {"DUP", "CAT"},
        ),
        (
            "UNITS / NUMERIC INTEGRITY",
            {"UNIT", "NULL"},
        ),
        (
            "FINANCIAL RECONCILIATION",
            {"FIN"},
        ),
        (
            "CONTROL VIEW",
            {"VIEW"},
        ),
    ]

    for section_name, prefixes in sections:
        print("-" * 104)
        print(section_name)
        print("-" * 104)

        for check in checks:
            prefix = check.code.split("-")[0]
            if prefix in prefixes:
                print_check(check)

        print()

    print("-" * 104)
    print("WASHINGTON VA GDX ANNUAL CONTROL TOTALS")
    print("-" * 104)

    for fiscal_year, amount in annual_totals:
        print(
            f"FY{fiscal_year} "
            f"${amount:>20,.2f}"
        )

    print()

    passed = sum(
        1
        for check in checks
        if check.passed
    )

    failed = len(checks) - passed

    print("=" * 104)
    print(f"Checks passed ..................... {passed}")
    print(f"Checks failed ..................... {failed}")
    print()

    if failed == 0:
        print("OVERALL RESULT: PASS")
        print("=" * 104)
        return 0

    print("OVERALL RESULT: FAIL")
    print("=" * 104)

    print()
    print("FAILED CHECKS")
    print("-" * 104)

    for check in checks:
        if not check.passed:
            print_check(check)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())