import argparse

from etl.db import get_connection


EXPECTED_VALUES = {
    2015: {
        "row_count": 360,
        "county_fips_count": 40,
        "total_rows": 40,
        "statewide_agi": 261527628,
        "statewide_total_income": 265256858,
        "statewide_wages": 180577520,
    }
}


STRUCTURAL_EXPECTATIONS = {
    "row_count": 360,
    "county_fips_count": 40,
    "total_rows": 40,
    "duplicate_rows": 0,
    "orphan_county_rows": 0,
}


def fetch_checks(tax_year: int):
    conn = get_connection()
    cur = conn.cursor()

    checks = {}

    cur.execute("""
        SELECT COUNT(*)
        FROM irs.county_income_tax
        WHERE tax_year = %s;
    """, (tax_year,))
    checks["row_count"] = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(DISTINCT county_fips)
        FROM irs.county_income_tax
        WHERE tax_year = %s;
    """, (tax_year,))
    checks["county_fips_count"] = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM irs.county_income_tax
        WHERE tax_year = %s
          AND agi_bracket_label = 'Total';
    """, (tax_year,))
    checks["total_rows"] = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT tax_year, county_fips, agi_bracket_label, COUNT(*) AS row_count
            FROM irs.county_income_tax
            WHERE tax_year = %s
            GROUP BY tax_year, county_fips, agi_bracket_label
            HAVING COUNT(*) > 1
        ) duplicates;
    """, (tax_year,))
    checks["duplicate_rows"] = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM irs.county_income_tax cit
        LEFT JOIN reference.county_registry cr
            ON cit.county_id = cr.county_id
        WHERE cit.tax_year = %s
          AND cit.county_fips <> '000'
          AND cr.county_id IS NULL;
    """, (tax_year,))
    checks["orphan_county_rows"] = cur.fetchone()[0]

    cur.execute("""
        SELECT
            adjusted_gross_income,
            total_income_amount,
            salaries_and_wages_amount
        FROM irs.county_income_tax
        WHERE tax_year = %s
          AND county_fips = '000'
          AND agi_bracket_label = 'Total';
    """, (tax_year,))
    row = cur.fetchone()

    if row:
        checks["statewide_agi"] = row[0]
        checks["statewide_total_income"] = row[1]
        checks["statewide_wages"] = row[2]
    else:
        checks["statewide_agi"] = None
        checks["statewide_total_income"] = None
        checks["statewide_wages"] = None

    cur.close()
    conn.close()

    return checks


def validate_against_expectations(checks, expectations, label):
    passed = True

    print(f"\n{label}")
    print("-" * 60)

    for key, expected in expectations.items():
        actual = checks.get(key)
        status = "PASS" if actual == expected else "FAIL"

        if actual != expected:
            passed = False

        print(f"{status:4} {key:25} actual={actual} expected={expected}")

    return passed


def validate_irs_year(tax_year: int):
    checks = fetch_checks(tax_year)

    print("=" * 60)
    print(f"IRS VALIDATION: {tax_year}")
    print("=" * 60)

    structural_passed = validate_against_expectations(
        checks,
        STRUCTURAL_EXPECTATIONS,
        "Structural checks",
    )

    value_passed = True

    if tax_year in EXPECTED_VALUES:
        value_passed = validate_against_expectations(
            checks,
            EXPECTED_VALUES[tax_year],
            "Known-value checks",
        )
    else:
        print("\nKnown-value checks")
        print("-" * 60)
        print(f"INFO No hard-coded expected totals for {tax_year}.")
        print(f"INFO statewide_agi          actual={checks.get('statewide_agi')}")
        print(f"INFO statewide_total_income actual={checks.get('statewide_total_income')}")
        print(f"INFO statewide_wages        actual={checks.get('statewide_wages')}")

    print("=" * 60)

    if structural_passed and value_passed:
        print("IRS validation passed.")
    else:
        raise AssertionError("IRS validation failed.")


def main():
    parser = argparse.ArgumentParser(description="Validate IRS SOI data for a tax year.")
    parser.add_argument("tax_year", type=int, nargs="?", default=2015)

    args = parser.parse_args()
    validate_irs_year(args.tax_year)


if __name__ == "__main__":
    main()