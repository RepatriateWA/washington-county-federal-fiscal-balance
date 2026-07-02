from etl.loaders.load_states import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'reference'
ORDER BY table_name;
""")

for row in cur.fetchall():
    print(row)

cur.close()
conn.close()