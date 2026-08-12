from etl.common.db import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT
        ordinal_position,
        column_name,
        data_type
    FROM information_schema.columns
    WHERE table_schema = 'procurement'
      AND table_name = 'award_transaction'
    ORDER BY ordinal_position;
""")

for row in cur.fetchall():
    print(row)

cur.close()
conn.close()