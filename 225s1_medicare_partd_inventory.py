from pathlib import Path
import csv
import subprocess
import sys

registry = Path(
    "accounting_registry/v0_3_0_working/"
    "annual_accounting_matrix.csv"
)
output = Path("225s1_medicare_partd_inventory.txt")

with registry.open(encoding="utf-8-sig", newline="") as f:
    rows = [
        r for r in csv.DictReader(f)
        if r["family_id"] == "MEDICARE_PART_D"
    ]

report = [
    "ETL-225S1 - MEDICARE PART D INVENTORY",
    "READ ONLY - NO DATABASE OR REGISTRY WRITES",
    "=" * 78,
    "",
    f"Registry observations: {len(rows)}",
    ""
]

for row in sorted(rows, key=lambda r: r["source_year"]):
    report.append(f"YEAR {row['source_year']}")
    for key, value in row.items():
        report.append(f"  {key}: {value}")
    report.append("")

sql = """
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'cms'
  AND table_name = 'medicare_core_state_year'
ORDER BY ordinal_position;
"""

command = [
    r"C:\Program Files\PostgreSQL\18\bin\psql.exe",
    "-X", "-A", "-F", "|", "-t",
    "-h", "localhost",
    "-p", "5432",
    "-U", "postgres",
    "-d", "wcffbp",
    "-v", "ON_ERROR_STOP=1",
    "-c", sql
]

result = subprocess.run(
    command,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace"
)

report.extend([
    "=" * 78,
    "CMS MEDICARE STATE-YEAR TABLE COLUMNS",
    "=" * 78,
    result.stdout,
    "",
    "Database query exit code: " + str(result.returncode)
])

if result.stderr.strip():
    report.extend(["DATABASE STDERR:", result.stderr])

if len(rows) != 7:
    report.append("WARNING: Expected seven Part D registry rows.")

output.write_text("\n".join(report) + "\n", encoding="utf-8")

print(f"Inventory saved: {output}")
print(f"Registry observations: {len(rows)}")
print(f"Database query exit code: {result.returncode}")

if result.returncode != 0 or len(rows) != 7:
    sys.exit(1)

print("ETL-225S1 PASS")
