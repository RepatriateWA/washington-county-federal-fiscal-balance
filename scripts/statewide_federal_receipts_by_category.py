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
    tax_category,
    gross_collections_thousands
FROM irs.state_collections
WHERE state_id = 48
ORDER BY fiscal_year, tax_category;
""")

rows = cur.fetchall()

print("=" * 110)
print("WASHINGTON STATE — OFFICIAL IRS GROSS COLLECTIONS BY TAX CATEGORY")
print("=" * 110)

current_year = None
year_total = Decimal(0)

for fiscal_year, tax_category, amount_thousands in rows:
    amount = dollars(amount_thousands)

    if fiscal_year != current_year:
        if current_year is not None:
            print("-" * 110)
            print(f"{'Category subtotal':<75}{fmt(year_total):>30}")
            print()

        current_year = fiscal_year
        year_total = Decimal(0)

        print()
        print(f"Fiscal Year {fiscal_year}")
        print("-" * 110)
        print(f"{'Tax Category':<75}{'Gross Collections ($)':>30}")

    year_total += amount
    print(f"{tax_category:<75}{fmt(amount):>30}")

if current_year is not None:
    print("-" * 110)
    print(f"{'Category subtotal':<75}{fmt(year_total):>30}")

cur.close()
conn.close()