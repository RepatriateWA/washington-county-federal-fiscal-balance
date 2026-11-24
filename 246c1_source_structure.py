import csv
from decimal import Decimal
from pathlib import Path

ROOT = Path.cwd()
D = Decimal

REFERENCE = ROOT / "docs/presentations/wcffbp-244b/data/243e1_first_draft_annual_balance.csv"
RETIREMENT = ROOT / "245m14_military_retirement_consistent_scenarios.csv"

OUTPUT = ROOT / "246c1_revised_annual_balance_candidate.csv"
REPORT = ROOT / "246c1_validation.txt"

def read(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

reference = read(REFERENCE)
retirement = read(RETIREMENT)

print("REFERENCE COLUMNS:", list(reference[0]))
print("RETIREMENT COLUMNS:", list(retirement[0]))
print("REFERENCE ROWS:", len(reference))
print("RETIREMENT ROWS:", len(retirement))

if len(reference) != 7 or len(retirement) != 7:
    raise ValueError("Expected seven annual records in each source")

REPORT.write_text(
    "ETL-246C1 - SOURCE STRUCTURE VALIDATION\n"
    "No accounting changes performed.\n"
    "Reference columns: " + repr(list(reference[0])) + "\n"
    "Retirement columns: " + repr(list(retirement[0])) + "\n"
    "Reference rows: " + str(len(reference)) + "\n"
    "Retirement rows: " + str(len(retirement)) + "\n",
    encoding="utf-8"
)
