from etl.db import get_connection


YEARS = range(2015, 2025)


def check(label, actual, expected):
    status = "PASS" if actual == expected else "FAIL"
    print(f"{status:4} {label:<50} actual={actual} expected={expected}")
    return status == "PASS"


def scalar(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()[0]


def main():
    conn = get_connection()
    cur = conn.cursor()

    passed = True

    print("=" * 90)
    print("CMS MEDICARE GEOGRAPHIC RAW VALIDATION")
    print("=" * 90)

    passed &= check(
        "raw row count",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM cms_raw.medicare_geographic_variation;
            """,
        ),
        36994,
    )

    passed &= check(
        "first year",
        scalar(
            cur,
            """
            SELECT MIN(report_year)
            FROM cms_raw.medicare_geographic_variation;
            """,
        ),
        2014,
    )

    passed &= check(
        "last year",
        scalar(
            cur,
            """
            SELECT MAX(report_year)
            FROM cms_raw.medicare_geographic_variation;
            """,
        ),
        2024,
    )

    print("\nWashington county coverage")
    print("-" * 90)

    for year in YEARS:
        passed &= check(
            f"{year} WA county rows, all ages",
            scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM cms_raw.medicare_geographic_variation
                WHERE report_year = %s
                  AND geography_level = 'County'
                  AND geography_name LIKE 'WA-%%'
                  AND geography_code <> '53000' 
                  AND age_group = 'All';
                """,
                (year,),
            ),
            39,
        )

    passed &= check(
        "duplicate WA county-year-age rows",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    report_year,
                    geography_code,
                    age_group,
                    COUNT(*)
                FROM cms_raw.medicare_geographic_variation
                WHERE geography_level = 'County'
                  AND geography_name LIKE 'WA-%%'
                  AND geography_code <> '53000'
                GROUP BY
                    report_year,
                    geography_code,
                    age_group
                HAVING COUNT(*) > 1
            ) duplicates;
            """,
        ),
        0,
    )

    cur.close()
    conn.close()

    print("=" * 90)

    if not passed:
        print("CMS Medicare raw validation failed.")
        raise SystemExit(1)

    print("CMS Medicare raw validation passed.")


if __name__ == "__main__":
    main()