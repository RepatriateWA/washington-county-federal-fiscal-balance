from etl.db import get_connection


EXPECTED_ROWS = 351
EXPECTED_COUNTIES = 39
EXPECTED_BENEFIT_TYPES = 9


def check(label, actual, expected):
    status = "PASS" if actual == expected else "FAIL"
    print(f"{status:4} {label:<45} actual={actual} expected={expected}")
    return status == "PASS"


def scalar(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()[0]


def main():
    conn = get_connection()
    cur = conn.cursor()

    passed = True

    print("=" * 90)
    print("SSA OASDI VALIDATION — WASHINGTON 2024")
    print("=" * 90)

    passed &= check(
        "benefit payment rows",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM ssa.benefit_payments
            WHERE report_year = 2024
              AND agency_code = 'SSA';
            """,
        ),
        EXPECTED_ROWS,
    )

    passed &= check(
        "distinct counties",
        scalar(
            cur,
            """
            SELECT COUNT(DISTINCT county_id)
            FROM ssa.benefit_payments
            WHERE report_year = 2024
              AND agency_code = 'SSA';
            """,
        ),
        EXPECTED_COUNTIES,
    )

    passed &= check(
        "distinct benefit types",
        scalar(
            cur,
            """
            SELECT COUNT(DISTINCT ssa_benefit_type_id)
            FROM ssa.benefit_payments
            WHERE report_year = 2024
              AND agency_code = 'SSA';
            """,
        ),
        EXPECTED_BENEFIT_TYPES,
    )

    passed &= check(
        "duplicate county-benefit rows",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    report_year,
                    county_id,
                    ssa_benefit_type_id,
                    COUNT(*)
                FROM ssa.benefit_payments
                WHERE report_year = 2024
                  AND agency_code = 'SSA'
                GROUP BY
                    report_year,
                    county_id,
                    ssa_benefit_type_id
                HAVING COUNT(*) > 1
            ) duplicates;
            """,
        ),
        0,
    )

    passed &= check(
        "orphan county rows",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM ssa.benefit_payments
            WHERE report_year = 2024
              AND agency_code = 'SSA'
              AND county_id IS NULL;
            """,
        ),
        0,
    )

    print("\nWashington control totals")
    print("-" * 90)

    cur.execute(
        """
        SELECT
            benefit_type,
            SUM(beneficiary_count) AS beneficiaries,
            SUM(monthly_benefits_thousands) AS monthly_thousands,
            SUM(annual_benefits_thousands) AS annualized_thousands
        FROM ssa.benefit_payments
        WHERE report_year = 2024
          AND agency_code = 'SSA'
        GROUP BY benefit_type
        ORDER BY benefit_type;
        """
    )

    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()

    print("=" * 90)

    if not passed:
        print("SSA OASDI validation failed.")
        raise SystemExit(1)

    print("SSA OASDI validation passed.")


if __name__ == "__main__":
    main()