from etl.db import get_connection

EXPECTED_WA_2020 = {
    "Total": 101041925,
    "Business income taxes": 7771455,
    "Individual income tax, employment taxes, and estate and trust income tax": 91388620,
    "Estate tax": 823083,
    "Gift tax": 35343,
    "Excise taxes": 1023424,
}

conn = get_connection()
cur = conn.cursor()

print("=" * 70)
print("IRS DATA BOOK TABLE 5 VALIDATION — FY2020 WASHINGTON")
print("=" * 70)

passed = True

for category, expected in EXPECTED_WA_2020.items():
    cur.execute("""
        SELECT gross_collections_thousands
        FROM irs.state_collections
        WHERE fiscal_year = 2020
          AND state_id = 48
          AND tax_category = %s;
    """, (category,))

    row = cur.fetchone()
    actual = row[0] if row else None

    status = "PASS" if actual == expected else "FAIL"
    if actual != expected:
        passed = False

    print(f"{status:4} {category:<70} actual={actual} expected={expected}")

cur.close()
conn.close()

print("=" * 70)

if not passed:
    raise AssertionError("IRS Data Book Table 5 validation failed.")

print("IRS Data Book Table 5 validation passed.")