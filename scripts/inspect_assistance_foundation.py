from pathlib import Path
import pandas as pd

FILE = Path(
    "data/raw/usaspending/FY2024_WA/original/"
    "Assistance_PrimeTransactions_2026-07-30_H01M19S42_1.csv"
)

print("=" * 72)
print("ETL-005A.2 — Assistance Source Inventory")
print("=" * 72)

df = pd.read_csv(
    FILE,
    nrows=5,
    low_memory=False,
)

print(f"File: {FILE.name}")
print(f"Columns: {len(df.columns)}")

print("\nCOLUMN NAMES")
print("-" * 72)

for i, column in enumerate(df.columns, start=1):
    print(f"{i:3}. {column}")