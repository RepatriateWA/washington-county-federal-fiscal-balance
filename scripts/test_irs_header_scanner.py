from pathlib import Path
import pandas as pd

from etl.utils.irs_header_scanner import find_amount_column, find_single_value_column

FILES = [
    Path("data/raw/irs/irs_soi_wa_2015.xls"),
    Path("data/raw/irs/irs_soi_wa_2017.xlsx"),
    Path("data/raw/irs/irs_soi_wa_2022.xlsx"),
]

SINGLE_VALUE_FIELDS = [
    "Adjusted gross income",
]

AMOUNT_FIELDS = [
    "Total income",
    "Salaries and wages",
    "Income tax before credits",
    "Total tax liability",
    "Total tax payments",
    "Overpayments refunded",
]

for path in FILES:
    print("=" * 80)
    print(path.name)
    print("=" * 80)

    df = pd.read_excel(path, sheet_name=0, header=None)

    for field in SINGLE_VALUE_FIELDS:
        try:
            col = find_single_value_column(df, field)
            statewide_value = df.iloc[6, col]
            print(f"{field:<35} column={col:<4} statewide={statewide_value}")
        except Exception as exc:
            print(f"{field:<35} ERROR: {exc}")

    for field in AMOUNT_FIELDS:
        try:
            col = find_amount_column(df, field)
            statewide_value = df.iloc[6, col]
            print(f"{field:<35} column={col:<4} statewide={statewide_value}")
        except Exception as exc:
            print(f"{field:<35} ERROR: {exc}")

    print()