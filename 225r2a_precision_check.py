from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import re
import sys

source = Path("225r1_medicare_partc_stdout.txt")

print("ETL-225R2A - MEDICARE PART C PRECISION CHECK")

if not source.exists():
    sys.exit("ERROR: ETL-225R1 output file not found")

text = source.read_text(encoding="utf-16")

pattern = re.compile(
    r"Year:\s*(\d{4})\s+"
    r"Registry amount:\s*([0-9.]+)\s+"
    r"Database amount:\s*([0-9.]+)"
)

matches = pattern.findall(text)
errors = []
years = set()

print("Observations found:", len(matches))

for year_text, registry_text, database_text in matches:
    year = int(year_text)
    registry = Decimal(registry_text)
    database = Decimal(database_text)

    rounded = database.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )

    difference = database - registry
    passed = (
        rounded == registry
        and abs(difference) < Decimal("0.005")
        and year not in years
    )

    years.add(year)

    print(
        f"{year}: "
        f"registry={registry}, "
        f"rounded_database={rounded}, "
        f"difference={difference:+f}, "
        f"PASS={passed}"
    )

    if not passed:
        errors.append(str(year))

if years != set(range(2018, 2025)):
    errors.append("Year coverage mismatch")

if errors:
    print("ETL-225R2A FAIL:", ", ".join(errors))
    sys.exit(1)

print("ETL-225R2A PASS")
print("Seven annual amounts reconcile at cent precision.")
print("No database or registry modifications.")

