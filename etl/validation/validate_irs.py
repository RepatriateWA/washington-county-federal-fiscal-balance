from etl.db import get_connection


EXPECTED_2015 = {
    "row_count": 360,
    "county_fips_count": 40,
    "total_rows": 40,
    "statewide_agi": 261527628,
    "statewide_total_income": 265256858,
    "statewide_wages": 180577520,
}


def validate_irs_year(tax_year: int):
    expected = EXPECTED_2015 if tax_year == 2015 else None

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

    print("=" * 60)
    print(f"IRS VALIDATION: {tax_year}")
    print("=" * 60)

    passed = True

    for key, actual in checks.items():
        if expected and key in expected:
            exp = expected[key]
            status = "PASS" if actual == exp else "FAIL"
            if actual != exp:
                passed = False
            print(f"{status:4} {key:25} actual={actual} expected={exp}")
        else:
            print(f"INFO {key:25} actual={actual}")

    print("=" * 60)

    if passed:
        print("IRS validation passed.")
    else:
        raise AssertionError("IRS validation failed.")


if __name__ == "__main__":
    validate_irs_year(2015)