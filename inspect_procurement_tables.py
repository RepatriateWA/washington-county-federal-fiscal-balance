from etl.common.db import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
SELECT table_name
FROM information_schema.tables
WHERE table_schema='procurement'
ORDER BY table_name;
""")

for row in cur.fetchall():
    print(row[0])

cur.close()
conn.close()