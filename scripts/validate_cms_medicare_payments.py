from etl.db import get_connection


YEARS = range(2015, 2025)
EXPECTED_COUNTIES = 39
EXPECTED_ROWS = 390


def check(label, actual, expected):
    status = "PASS" if actual == expected else "FAIL"
    print(f"{status:4} {label:<55} actual={actual} expected={expected}")
    return status == "PASS"


def scalar(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()[0]


def main():
    conn = get_connection()
    cur = conn.cursor()

    passed = True

    print("=" * 100)
    print("CMS MEDICARE GEOGRAPHIC PAYMENTS VALIDATION")
    print("=" * 100)

    passed &= check(
        "curated row count",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM cms.medicare_geographic_payments;
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
            FROM cms.medicare_geographic_payments;
            """,
        ),
        EXPECTED_COUNTIES,
    )

    print("\nAnnual county coverage")
    print("-" * 100)

    for year in YEARS:
        passed &= check(
            f"{year} county rows",
            scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM cms.medicare_geographic_payments
                WHERE report_year = %s;
                """,
                (year,),
            ),
            EXPECTED_COUNTIES,
        )

    print("\nDatabase integrity")
    print("-" * 100)

    passed &= check(
        "duplicate county-year rows",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    report_year,
                    county_id,
                    age_group,
                    COUNT(*)
                FROM cms.medicare_geographic_payments
                GROUP BY
                    report_year,
                    county_id,
                    age_group
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
            FROM cms.medicare_geographic_payments
            WHERE county_id IS NULL;
            """,
        ),
        0,
    )

    passed &= check(
        "missing Medicare program mappings",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM cms.medicare_geographic_payments
            WHERE federal_program_id IS NULL;
            """,
        ),
        0,
    )

    passed &= check(
        "negative actual payment rows",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM cms.medicare_geographic_payments
            WHERE total_medicare_payments_dollars < 0;
            """,
        ),
        0,
    )

    print("\nWashington annual totals")
    print("-" * 100)

    cur.execute(
        """
        SELECT
            report_year,
            SUM(original_medicare_beneficiaries) AS original_medicare_beneficiaries,
            SUM(medicare_advantage_beneficiaries) AS medicare_advantage_beneficiaries,
            SUM(total_medicare_payments_dollars) AS actual_payments_dollars,
            SUM(standardized_medicare_payments_dollars) AS standardized_payments_dollars
        FROM cms.medicare_geographic_payments
        GROUP BY report_year
        ORDER BY report_year;
        """
    )

    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()

    print("=" * 100)

    if not passed:
        print("CMS Medicare validation failed.")
        raise SystemExit(1)

    print("CMS Medicare validation passed.")


if __name__ == "__main__":
    main()