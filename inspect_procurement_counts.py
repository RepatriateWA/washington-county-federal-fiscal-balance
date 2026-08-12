from etl.common.db import get_connection

TABLES = [
    "agency",
    "award",
    "award_recipient_relationship",
    "award_transaction",
    "load_batch",
    "naics",
    "naics_alias",
    "normalization_exception",
    "place",
    "place_of_performance",
    "psc",
    "psc_alias",
    "raw_award_transaction",
    "recipient",
    "recipient_parent_relationship",
]

conn = get_connection()
cur = conn.cursor()

print("=" * 88)
print("PROCUREMENT TABLE ROW COUNTS")
print("=" * 88)

for table in TABLES:
    cur.execute(f"SELECT COUNT(*) FROM procurement.{table}")
    count = cur.fetchone()[0]
    print(f"{table:<35} {count:>15,}")

cur.close()
conn.close()