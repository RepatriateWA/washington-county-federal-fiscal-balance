from etl.common.db import get_connection

conn = get_connection()
cur = conn.cursor()

print("=" * 80)
print("1. RAW PROCUREMENT ROWS BY LOAD BATCH")
print("=" * 80)

cur.execute("""
    SELECT
        load_batch_id,
        COUNT(*)
    FROM procurement.raw_award_transaction
    GROUP BY load_batch_id
    ORDER BY load_batch_id;
""")

for row in cur.fetchall():
    print(row)


print()
print("=" * 80)
print("2. CANONICAL PROCUREMENT TRANSACTIONS BY LOAD BATCH")
print("=" * 80)

cur.execute("""
    SELECT
        load_batch_id,
        COUNT(*),
        COUNT(DISTINCT award_id)
    FROM procurement.award_transaction
    GROUP BY load_batch_id
    ORDER BY load_batch_id;
""")

for row in cur.fetchall():
    print(row)


print()
print("=" * 80)
print("3. PROCUREMENT TRANSACTIONS BY FISCAL YEAR")
print("=" * 80)

cur.execute("""
    SELECT
        fiscal_year,
        COUNT(*),
        SUM(federal_action_obligation)
    FROM procurement.award_transaction
    GROUP BY fiscal_year
    ORDER BY fiscal_year;
""")

for row in cur.fetchall():
    print(row)


cur.close()
conn.close()

print()
print("=" * 80)
print("PROCUREMENT COVERAGE INSPECTION COMPLETE")
print("=" * 80)