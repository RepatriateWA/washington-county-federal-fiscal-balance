from etl.db import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
SELECT
    county_fips,
    agi_bracket_label,
    number_of_returns,
    adjusted_gross_income,
    total_income_amount,
    salaries_and_wages_amount,
    taxable_interest_amount,
    ordinary_dividends_amount,
    qualified_dividends_amount,
    business_net_income_amount,
    net_capital_gain_amount
FROM irs.county_income_tax
WHERE tax_year = 2015
  AND county_fips IN ('000', '033')
  AND agi_bracket_label = 'Total'
ORDER BY county_fips;
""")

for row in cur.fetchall():
    print(row)

cur.close()
conn.close()