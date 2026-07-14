from etl.db import get_connection

SOI_YEARS = range(2015, 2023)
DATABOOK_YEARS = range(2015, 2025)
SSA_YEARS = [2024]
EXPECTED_SSA_COUNTIES = 39
EXPECTED_SSA_BENEFIT_TYPES = 9
EXPECTED_SSA_ROWS_PER_YEAR = (
    EXPECTED_SSA_COUNTIES * EXPECTED_SSA_BENEFIT_TYPES
)

EXPECTED_STATE_COLLECTION_CATEGORIES = 6
MINIMUM_STATE_COLLECTION_ROWS = 300


def check(label, actual, expected):
    status = "PASS" if actual == expected else "FAIL"
    print(f"{status:4} {label:<45} actual={actual} expected={expected}")
    return status == "PASS"


def check_minimum(label, actual, minimum):
    status = "PASS" if actual >= minimum else "FAIL"
    print(f"{status:4} {label:<45} actual={actual} expected>={minimum}")
    return status == "PASS"


def scalar(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()[0]


def main():
    conn = get_connection()
    cur = conn.cursor()

    passed = True

    print("=" * 80)
    print("RELEASE VALIDATION")
    print("=" * 80)

    print("\nReference Data")
    print("-" * 80)

    passed &= check(
        "state_registry rows",
        scalar(cur, "SELECT COUNT(*) FROM reference.state_registry;"),
        57,
    )

    passed &= check(
        "Washington county rows",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM reference.county_registry
            WHERE state_id = 48;
            """,
        ),
        39,
    )

    print("\nIRS SOI County Data")
    print("-" * 80)

    for year in SOI_YEARS:
        passed &= check(
            f"{year} SOI rows",
            scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM irs.county_income_tax
                WHERE tax_year = %s;
                """,
                (year,),
            ),
            360,
        )

    print("\nIRS Data Book Table 5")
    print("-" * 80)

    for year in DATABOOK_YEARS:
        passed &= check_minimum(
            f"FY{year} state collection rows",
            scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM irs.state_collections
                WHERE fiscal_year = %s;
                """,
                (year,),
            ),
            MINIMUM_STATE_COLLECTION_ROWS,
        )

        passed &= check(
            f"FY{year} WA categories",
            scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM irs.state_collections
                WHERE fiscal_year = %s
                  AND state_id = 48;
                """,
                (year,),
            ),
            EXPECTED_STATE_COLLECTION_CATEGORIES,
        )

        print("\nSSA OASDI County Benefits")
    print("-" * 80)

    for year in SSA_YEARS:
        passed &= check(
            f"{year} SSA benefit rows",
            scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM ssa.benefit_payments
                WHERE report_year = %s
                  AND agency_code = 'SSA';
                """,
                (year,),
            ),
            EXPECTED_SSA_ROWS_PER_YEAR,
        )

        passed &= check(
            f"{year} SSA counties",
            scalar(
                cur,
                """
                SELECT COUNT(DISTINCT county_id)
                FROM ssa.benefit_payments
                WHERE report_year = %s
                  AND agency_code = 'SSA';
                """,
                (year,),
            ),
            EXPECTED_SSA_COUNTIES,
        )

        passed &= check(
            f"{year} SSA benefit types",
            scalar(
                cur,
                """
                SELECT COUNT(DISTINCT ssa_benefit_type_id)
                FROM ssa.benefit_payments
                WHERE report_year = %s
                  AND agency_code = 'SSA';
                """,
                (year,),
            ),
            EXPECTED_SSA_BENEFIT_TYPES,
        )
    
 
    
    print("\nDatabase Integrity")

    passed &= check(
        "duplicate SSA benefit rows",
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

    print("-" * 80)

    passed &= check(
        "duplicate SOI rows",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT tax_year, county_fips, agi_bracket_label, COUNT(*)
                FROM irs.county_income_tax
                GROUP BY tax_year, county_fips, agi_bracket_label
                HAVING COUNT(*) > 1
            ) dup;
            """,
        ),
        0,
    )

    passed &= check(
        "duplicate Data Book rows",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT fiscal_year, state_id, tax_category, COUNT(*)
                FROM irs.state_collections
                GROUP BY fiscal_year, state_id, tax_category
                HAVING COUNT(*) > 1
            ) dup;
            """,
        ),
        0,
    )

    passed &= check(
        "SOI orphan county rows",
        scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM irs.county_income_tax
            WHERE county_fips <> '000'
              AND county_id IS NULL;
            """,
        ),
        0,
    )

    cur.close()
    conn.close()

    print("\nOverall")
    print("-" * 80)

    if not passed:
        print("RELEASE VALIDATION FAILED")
        raise SystemExit(1)

    print("RELEASE VALIDATION PASSED")


if __name__ == "__main__":
    main()