from pathlib import Path

import pandas as pd


SOURCE_DIR = Path(
    "data/raw/cms/medicare_geographic_variation"
)


def main() -> None:
    files = sorted(
        [
            path
            for path in SOURCE_DIR.iterdir()
            if path.suffix.lower() in {".csv", ".xlsx", ".xls", ".zip"}
        ]
    )

    if not files:
        raise FileNotFoundError(
            f"No Medicare source files found in {SOURCE_DIR}"
        )

    print("=" * 100)
    print("CMS MEDICARE GEOGRAPHIC VARIATION INSPECTION")
    print("=" * 100)

    for source_file in files:
        print(f"\nSource: {source_file}")
        print("-" * 100)

        if source_file.suffix.lower() == ".csv":
            df = pd.read_csv(source_file, low_memory=False)

        elif source_file.suffix.lower() in {".xlsx", ".xls"}:
            workbook = pd.ExcelFile(source_file)
            print("Sheets:", workbook.sheet_names)
            df = pd.read_excel(
                source_file,
                sheet_name=workbook.sheet_names[0],
            )

        else:
            print("ZIP file detected; leave it compressed for now.")
            continue

        print("Shape:", df.shape)
        print("\nColumns:")
        for index, column in enumerate(df.columns):
            print(f"{index:>3}: {column}")

        print("\nFirst 10 rows:")
        print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()