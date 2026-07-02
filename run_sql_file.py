from pathlib import Path
from etl.loaders.load_states import get_connection

sql_file = Path("etl/sql/002_create_irs_schema.sql")

conn = get_connection()
cur = conn.cursor()

cur.execute(sql_file.read_text())

conn.commit()
cur.close()
conn.close()

print(f"Executed {sql_file}")