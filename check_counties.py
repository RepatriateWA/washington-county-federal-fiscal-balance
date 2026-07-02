from etl.loaders.load_states import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
SELECT county_id, state_id, county_fips, full_fips, county_name, county_type
FROM reference.county_registry
ORDER BY full_fips;
""")

rows = cur.fetchall()

print(f"County rows: {len(rows)}")
for row in rows:
    print(row)

cur.close()
conn.close()