from pathlib import Path
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 300)
pd.set_option("display.max_rows", 80)

file = Path("data/raw/irs_state/irs_state_wa_2023.xlsx")

xls = pd.ExcelFile(file)

print("Sheets:")
for sheet in xls.sheet_names:
    print(f"- {sheet}")

for sheet in xls.sheet_names:
    print("=" * 80)
    print(sheet)
    print("=" * 80)

    df = pd.read_excel(file, sheet_name=sheet, header=None)
    print("Shape:", df.shape)
    print(df.head(60).to_string())