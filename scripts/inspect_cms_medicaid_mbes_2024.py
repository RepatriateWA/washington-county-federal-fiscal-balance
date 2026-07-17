from pathlib import Path

import pandas as pd


SOURCE_DIR = Path(
    "data/raw/cms/medicaid_mbes/2024/extracted"
)

EXCEL_SUFFIXES = {".xlsx", ".xls", ".xlsm"}


def main() -> None:
    files = sorted(
        path
        for path in SOURCE_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in EXCEL_SUFFIXES
    )

    if not files:
        raise FileNotFoundError(
            f"No Excel files found under {SOURCE_DIR}"
        )

    print("=" * 100)
    print("CMS MEDICAID MBES FY2024 INSPECTION")
    print("=" * 100)

    for source_file in files:
        print(f"\nFILE: {source_file}")
        print("-" * 100)

        workbook = pd.ExcelFile(source_file)

        print("Worksheets:")
        for sheet_name in workbook.sheet_names:
            print(f"  - {sheet_name}")

        for sheet_name in workbook.sheet_names:
            df = pd.read_excel(
                source_file,
                sheet_name=sheet_name,
                header=None,
            )

            print(f"\nSheet: {sheet_name}")
            print(f"Shape: {df.shape}")
            print(df.head(20).to_string())


if __name__ == "__main__":
    main()