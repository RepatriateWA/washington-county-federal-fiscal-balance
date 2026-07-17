from pathlib import Path

import pandas as pd


SOURCE_DIR = Path("data/raw/cms/medicaid_mbes/2024/extracted")
TARGET_SHEET = "MAP - Washington"


def find_workbook() -> Path:
    candidates = sorted(
        path
        for path in SOURCE_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}
    )

    for path in candidates:
        try:
            workbook = pd.ExcelFile(path)

            if TARGET_SHEET in workbook.sheet_names:
                return path

        except Exception:
            continue

    raise FileNotFoundError(
        f"Could not find a workbook containing '{TARGET_SHEET}' under {SOURCE_DIR}"
    )


def main() -> None:
    source_file = find_workbook()

    df = pd.read_excel(
        source_file,
        sheet_name=TARGET_SHEET,
        header=None,
    )

    print("=" * 110)
    print("CMS MEDICAID MAP — WASHINGTON FY2024")
    print("=" * 110)
    print(f"Source: {source_file}")
    print(f"Shape: {df.shape}")

    print("\nFirst 20 rows")
    print("-" * 110)
    print(df.head(20).to_string())

    print("\nLast 20 rows")
    print("-" * 110)
    print(df.tail(20).to_string())

    print("\nCandidate header rows")
    print("-" * 110)

    for index, row in df.iterrows():
        first_cell = str(row.iloc[0]).strip()

        if first_cell == "Service Category":
            print(f"Header row index: {index}")
            print(row.to_list())


if __name__ == "__main__":
    main()