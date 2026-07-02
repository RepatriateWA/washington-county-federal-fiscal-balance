from etl.loaders.load_states import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
SELECT *
FROM reference.state_registry
WHERE state_abbreviation = 'WA';
""")

print(cur.fetchall())

cur.close()
conn.close()