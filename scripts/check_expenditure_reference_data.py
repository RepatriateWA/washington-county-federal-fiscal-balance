from etl.db import get_connection

conn = get_connection()
cur = conn.cursor()

print("=" * 60)
print("Programs")
print("=" * 60)

cur.execute("""
SELECT program_id, program_code, program_name
FROM expenditure.program
ORDER BY program_id;
""")

for row in cur.fetchall():
    print(row)

print()

print("=" * 60)
print("Data Sources")
print("=" * 60)

cur.execute("""
SELECT data_source_id,
       source_code,
       source_name
FROM expenditure.data_source
ORDER BY data_source_id;
""")

for row in cur.fetchall():
    print(row)

cur.close()
conn.close()