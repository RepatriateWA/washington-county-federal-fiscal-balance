from etl.common.db import get_connection

conn = get_connection()
cur = conn.cursor()

print("=" * 90)
print("PROCUREMENT FISCAL YEAR BY LOAD BATCH")
print("=" * 90)

cur.execute("""
    SELECT
        load_batch_id,
        fiscal_year,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation) AS obligation
    FROM procurement.award_transaction
    GROUP BY
        load_batch_id,
        fiscal_year
    ORDER BY
        load_batch_id,
        fiscal_year;
""")

for row in cur.fetchall():
    print(row)

cur.close()
conn.close()