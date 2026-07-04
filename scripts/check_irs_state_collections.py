from etl.db import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
SELECT
    fiscal_year,
    tax_category,
    returns_filed,
    gross_collections_thousands,
    refund_amount_thousands
FROM irs.state_collections
ORDER BY fiscal_year, tax_category;
""")

for row in cur.fetchall():
    print(row)

cur.close()
conn.close()