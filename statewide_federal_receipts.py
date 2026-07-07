from decimal import Decimal

from etl.db import get_connection


def dollars(thousands):
    return Decimal(thousands) * Decimal(1000)


def fmt(value):
    return f"${value:,.0f}"


conn = get_connection()
cur = conn.cursor()

cur.execute("""
SELECT
    fiscal_year,
    gross_collections_thousands
FROM irs.state_collections
WHERE state_id = 48
  AND tax_category = 'Total'
ORDER BY fiscal_year;
""")

rows = cur.fetchall()

print("=" * 80)
print("WASHINGTON STATE — OFFICIAL IRS GROSS COLLECTIONS")
print("=" * 80)
print()
print(f"{'Fiscal Year':<15}{'Gross Collections ($)':>25}")
print("-" * 80)

values = []

for fiscal_year, amount_thousands in rows:
    amount = dollars(amount_thousands)
    values.append((fiscal_year, amount))
    print(f"{fiscal_year:<15}{fmt(amount):>25}")

print("-" * 80)

total = sum(amount for _, amount in values)
average = total / len(values)
highest_year, highest_value = max(values, key=lambda x: x[1])
lowest_year, lowest_value = min(values, key=lambda x: x[1])

print(f"{'10-year total':<15}{fmt(total):>25}")
print(f"{'Average':<15}{fmt(average):>25}")
print(f"{'Highest':<15}{highest_year}  {fmt(highest_value):>18}")
print(f"{'Lowest':<15}{lowest_year}  {fmt(lowest_value):>18}")

cur.close()
conn.close()