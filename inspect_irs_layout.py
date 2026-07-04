from pathlib import Path
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 300)

def inspect_workbook(path):
    print("=" * 80)
    print(path.name)
    print("=" * 80)

    xls = pd.ExcelFile(path)

    print("\nSheets:")
    for sheet in xls.sheet_names:
        print(f"  - {sheet}")

    df = pd.read_excel(
        path,
        sheet_name=0,
        header=None
    )

    print("\nWorksheet shape:")
    print(df.shape)

    print("\nFirst 20 rows / first 25 columns")
    print(df.iloc[:20, :25])

    print("\nHeader detail: rows 3-6, columns 12-35")
    print(df.iloc[3:7, 12:36].to_string())


if __name__ == "__main__":

    inspect_workbook(Path("data/raw/irs/irs_soi_wa_2015.xls"))
    inspect_workbook(Path("data/raw/irs/irs_soi_wa_2016.xls"))
    inspect_workbook(Path("data/raw/irs/irs_soi_wa_2017.xlsx"))