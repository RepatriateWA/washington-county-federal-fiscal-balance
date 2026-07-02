from etl.db import get_connection

conn = get_connection()
cur = conn.cursor()

print("=" * 60)
print("IRS SOI 2015 VALIDATION")
print("=" * 60)

# Total rows
cur.execute("""
SELECT COUNT(*)
FROM irs.county_income_tax
WHERE tax_year = 2015;
""")
print(f"Rows loaded: {cur.fetchone()[0]}")

# Distinct counties
cur.execute("""
SELECT COUNT(DISTINCT county_fips)
FROM irs.county_income_tax
WHERE tax_year = 2015;
""")
print(f"Distinct county FIPS: {cur.fetchone()[0]}")

# Total records
cur.execute("""
SELECT county_fips,
       county_id,
       agi_bracket_label,
       number_of_returns,
       adjusted_gross_income
FROM irs.county_income_tax
WHERE tax_year = 2015
  AND agi_bracket_label = 'Total'
ORDER BY county_fips;
""")

rows = cur.fetchall()

print("\nCounty totals:")
for row in rows:
    print(row)

# King County summary
cur.execute("""
SELECT
    number_of_returns,
    adjusted_gross_income,
    salaries_and_wages_amount
FROM irs.county_income_tax
WHERE county_fips='033'
AND agi_bracket_label='Total';
""")

print("\nKing County:")
print(cur.fetchone())

cur.close()
conn.close()

print("\nValidation complete.")