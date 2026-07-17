from pathlib import Path

import pandas as pd


SOURCE_FILE = Path(
    "data/raw/cms/medicaid_mbes/2024/extracted/"
    "FY 2024 FMR NET EXPENDITURES.xlsx"
)

SHEET_NAME = "MAP - Washington"
HEADER_ROW = 6

OUTPUT_COLUMNS = [
    "service_category",
    "total_computable",
    "federal_share",
    "federal_share_medicaid",
    "federal_share_arra",
    "federal_share_covid",
    "state_share",
]


def parse_amount(value):
    if pd.isna(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none"}:
        return None

    negative = text.startswith("(") and text.endswith(")")

    text = (
        text.replace(",", "")
        .replace("$", "")
        .replace("(", "")
        .replace(")", "")
        .strip()
    )

    if not text:
        return None

    amount = float(text)

    return -amount if negative else amount


def main():

    raw = pd.read_excel(
        SOURCE_FILE,
        sheet_name=SHEET_NAME,
        header=HEADER_ROW,
    )

    df = raw.iloc[:, :7].copy()
    df.columns = OUTPUT_COLUMNS

    df["service_category"] = (
        df["service_category"]
        .astype(str)
        .str.strip()
    )

    df = df[
        (df["service_category"] != "")
        & (df["service_category"] != "nan")
    ].copy()

    for column in OUTPUT_COLUMNS[1:]:
        df[column] = df[column].map(parse_amount)

    print("=" * 120)
    print("MEDICAID MAP EXPLORATION")
    print("=" * 120)

    print(f"\nRows parsed: {len(df)}")

    print("\n")
    print("=" * 120)
    print("SECTION HEADERS")
    print("=" * 120)

    prefixes = (
        "",
        "C-",
        "T-",
    )

    for prefix in prefixes:

        print(f"\n---- {prefix or 'UNPREFIXED'} ----")

        subset = df[
            df["service_category"].str.startswith(prefix)
            if prefix
            else ~df["service_category"].str.startswith(("C-", "T-"))
        ]

        print(f"Rows: {len(subset)}")

        print(subset["service_category"].head(15).to_string(index=False))

    print("\n")
    print("=" * 120)
    print("ROWS CONTAINING 'TOTAL'")
    print("=" * 120)

    totals = df[
        df["service_category"]
        .str.contains("Total|TOTAL|Net", regex=True)
    ]

    print(
        totals[
            [
                "service_category",
                "total_computable",
                "federal_share",
                "state_share",
            ]
        ].to_string(index=False)
    )

    print("\n")
    print("=" * 120)
    print("NEGATIVE FEDERAL SHARE ROWS")
    print("=" * 120)

    negatives = df[
        df["federal_share"].fillna(0) < 0
    ]

    print(
        negatives[
            [
                "service_category",
                "federal_share",
            ]
        ].to_string(index=False)
    )

    print("\n")
    print("=" * 120)
    print("COLUMN TOTALS")
    print("=" * 120)

    for column in OUTPUT_COLUMNS[1:]:

        print(
            f"{column:<30}"
            f"{df[column].fillna(0).sum():>20,.0f}"
        )


if __name__ == "__main__":
    main()