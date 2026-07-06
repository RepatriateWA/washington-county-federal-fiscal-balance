from etl.db import get_connection

conn = get_connection()
cur = conn.cursor()

print("=" * 110)
print("WASHINGTON STATE - ESTIMATED FEDERAL TAXES PAID")
print("=" * 110)
print()

print(f"{'Year':<8}{'Measure':<35}{'Amount ($)':>25}")
print("-" * 110)

#
# 2015-2022
#
cur.execute("""
SELECT
    tax_year,
    total_tax_liability_amount
FROM irs.county_income_tax
WHERE county_fips = '000'
  AND agi_bracket_label = 'Total'
ORDER BY tax_year;
""")

for year, amount in cur.fetchall():
    print(
        f"{year:<8}"
        f"{'Total Tax Liability (IRS SOI)':<35}"
        f"{amount*1000:>25,.0f}"
    )

#
# 2023-2024
#
cur.execute("""
SELECT
    fiscal_year,
    gross_collections_thousands
FROM irs.state_collections
WHERE tax_category='Total [1]'
ORDER BY fiscal_year;
""")

for year, amount in cur.fetchall():
    print(
        f"{year:<8}"
        f"{'Gross IRS Collections':<35}"
        f"{amount*1000:>25,.0f}"
    )

cur.close()
conn.close()