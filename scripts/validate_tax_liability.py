from etl.db import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
SELECT
    tax_year,
    total_tax_liability_amount,
    income_tax_amount,
    total_tax_payments_amount,
    overpayments_refunded_amount
FROM irs.county_income_tax
WHERE county_fips = '000'
  AND agi_bracket_label = 'Total'
ORDER BY tax_year;
""")

print("=" * 100)
print("WASHINGTON STATEWIDE TAX TOTALS")
print("=" * 100)

for row in cur.fetchall():
    print(row)

cur.close()
conn.close()