"""Inspect representative FY2024 assistance award identifiers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


SOURCE_FILE = Path(
    "data/raw/usaspending/FY2024_WA/original/"
    "Assistance_PrimeTransactions_2026-07-30_H01M19S42_1.csv"
)

COLUMNS = [
    "assistance_award_unique_key",
    "award_id_fain",
    "award_id_uri",
    "sai_number",
    "assistance_transaction_unique_key",
    "action_date",
    "recipient_name",
    "awarding_agency_name",
]


def clean_text(frame: pd.DataFrame) -> pd.DataFrame:
    """Trim text and convert blank values to null."""

    for column in frame.columns:
        frame[column] = (
            frame[column]
            .astype("string")
            .str.strip()
            .replace("", pd.NA)
        )

    return frame


def print_section(
    title: str,
    frame: pd.DataFrame,
) -> None:
    print()
    print(title)
    print("-" * 100)

    if frame.empty:
        print("(none)")
        return

    print(
        frame.to_string(
            index=False,
            max_colwidth=50,
        )
    )


def main() -> None:
    frame = pd.read_csv(
        SOURCE_FILE,
        usecols=COLUMNS,
        dtype="string",
        low_memory=False,
    )

    frame = clean_text(frame)

    award_rows = (
        frame.sort_values(
            [
                "assistance_award_unique_key",
                "action_date",
                "assistance_transaction_unique_key",
            ],
            na_position="last",
        )
        .drop_duplicates(
            subset=["assistance_award_unique_key"],
            keep="first",
        )
    )

    print("=" * 100)
    print("ETL-005A — ASSISTANCE AWARD IDENTIFIER INSPECTION")
    print("=" * 100)
    print(f"Source rows: {len(frame):,}")
    print(
        "Distinct award keys: "
        f"{frame['assistance_award_unique_key'].nunique(dropna=True):,}"
    )

    print_section(
        "FIRST 25 DISTINCT AWARDS",
        award_rows[COLUMNS[:4]].head(25),
    )

    print_section(
        "AWARDS WITH FAIN BUT NO URI",
        award_rows[
            award_rows["award_id_fain"].notna()
            & award_rows["award_id_uri"].isna()
        ][COLUMNS[:4]].head(15),
    )

    print_section(
        "AWARDS WITH URI BUT NO FAIN",
        award_rows[
            award_rows["award_id_uri"].notna()
            & award_rows["award_id_fain"].isna()
        ][COLUMNS[:4]].head(15),
    )

    print_section(
        "AWARDS WITH NEITHER FAIN NOR URI",
        award_rows[
            award_rows["award_id_fain"].isna()
            & award_rows["award_id_uri"].isna()
        ][
            [
                "assistance_award_unique_key",
                "sai_number",
                "recipient_name",
                "awarding_agency_name",
            ]
        ].head(25),
    )

    sai_multiplicity = (
        frame[
            [
                "sai_number",
                "assistance_award_unique_key",
            ]
        ]
        .dropna()
        .drop_duplicates()
        .groupby("sai_number")[
            "assistance_award_unique_key"
        ]
        .nunique()
        .sort_values(
            ascending=False
        )
    )

    print()
    print("SAI NUMBER MULTIPLICITY")
    print("-" * 100)
    print(
        sai_multiplicity.to_string()
        if not sai_multiplicity.empty
        else "(none)"
    )


if __name__ == "__main__":
    main()