from pathlib import Path
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 400)

FILES = [
    Path("data/raw/irs/irs_soi_wa_2015.xls"),
    Path("data/raw/irs/irs_soi_wa_2017.xlsx"),
    Path("data/raw/irs/irs_soi_wa_2022.xlsx"),
]

for path in FILES:
    print("=" * 100)
    print(path.name)
    print("=" * 100)

    df = pd.read_excel(path, sheet_name=0, header=None)

    print("\nHeader detail: rows 3-6, columns 80-130")
    print(df.iloc[3:7, 80:131].to_string())