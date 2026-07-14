from pathlib import Path

import pandas as pd


SOURCE_FILE = Path(
    "data/raw/ssa/oasdi/2024/ssa_oasdi_wa_2024.xlsx"
)

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 300)
pd.set_option("display.max_rows", 100)


def main() -> None:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"Missing source file: {SOURCE_FILE}")

    workbook = pd.ExcelFile(SOURCE_FILE)

    print("=" * 90)
    print("SSA OASDI WASHINGTON 2024 INSPECTION")
    print("=" * 90)

    print("\nSheets")
    print("-" * 90)

    for sheet_name in workbook.sheet_names:
        print(f"- {sheet_name}")

    for sheet_name in workbook.sheet_names:
        print("\n" + "=" * 90)
        print(sheet_name)
        print("=" * 90)

        df = pd.read_excel(
            SOURCE_FILE,
            sheet_name=sheet_name,
            header=None,
        )

        print(f"Shape: {df.shape}")
        print()
        print(df.head(30).to_string())


if __name__ == "__main__":
    main()