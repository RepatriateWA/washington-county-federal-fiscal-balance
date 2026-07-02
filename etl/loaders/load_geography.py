from pathlib import Path

import pandas as pd

from etl.utils.download import download_file

# Official Census state reference file (tab-delimited text)
URL = "https://www2.census.gov/geo/docs/reference/state.txt"

OUTPUT = Path("data/raw/reference/census/state.txt")


def main():
    file_path = download_file(URL, OUTPUT)

    print(f"\nReading: {file_path}")

    df = pd.read_csv(file_path, sep="|")

    print("\nColumns:")
    print(list(df.columns))

    print("\nNumber of rows:")
    print(len(df))

    print("\nFirst five rows:")
    print(df.head())


if __name__ == "__main__":
    main()