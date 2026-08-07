"""Profile FY2024 Washington assistance award identity."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


SOURCE_FILE = Path(
    "data/raw/usaspending/FY2024_WA/original/"
    "Assistance_PrimeTransactions_2026-07-30_H01M19S42_1.csv"
)

OUTPUT_FILE = Path(
    "data/raw/usaspending/FY2024_WA/profiling/"
    "Assistance_Profile_001_AwardIdentity.txt"
)

IDENTITY_COLUMNS = [
    "assistance_transaction_unique_key",
    "assistance_award_unique_key",
    "award_id_fain",
    "award_id_uri",
    "sai_number",
]


def clean_identifier(series: pd.Series) -> pd.Series:
    """Normalize blank identifier values to pandas nulls."""

    return (
        series.astype("string")
        .str.strip()
        .replace("", pd.NA)
    )


def count_duplicate_values(series: pd.Series) -> int:
    """Count distinct populated values appearing more than once."""

    populated = series.dropna()

    return int(
        (populated.value_counts() > 1).sum()
    )


def count_conflicting_mappings(
    frame: pd.DataFrame,
    *,
    left: str,
    right: str,
) -> int:
    """
    Count populated left-side identifiers mapping to multiple
    populated right-side identifiers.
    """

    pairs = frame[[left, right]].dropna().drop_duplicates()

    if pairs.empty:
        return 0

    return int(
        (
            pairs.groupby(left, dropna=False)[right]
            .nunique(dropna=True)
            > 1
        ).sum()
    )


def build_report(frame: pd.DataFrame) -> str:
    """Build the human-readable award identity profile."""

    total_rows = len(frame)

    lines: list[str] = [
        "=" * 76,
        "ETL-005A — ASSISTANCE AWARD IDENTITY PROFILE",
        "=" * 76,
        f"Source file: {SOURCE_FILE}",
        f"Rows examined: {total_rows:,}",
        "",
        "IDENTIFIER COVERAGE",
        "-" * 76,
    ]

    for column in IDENTITY_COLUMNS:
        series = frame[column]
        populated = int(series.notna().sum())
        missing = total_rows - populated
        distinct = int(series.nunique(dropna=True))

        lines.append(
            f"{column:<42} "
            f"populated={populated:>9,}  "
            f"missing={missing:>9,}  "
            f"distinct={distinct:>9,}"
        )

    lines.extend(
        [
            "",
            "DUPLICATE VALUE GROUPS",
            "-" * 76,
        ]
    )

    for column in IDENTITY_COLUMNS:
        duplicate_groups = count_duplicate_values(
            frame[column]
        )

        lines.append(
            f"{column:<42} "
            f"{duplicate_groups:>9,}"
        )

    lines.extend(
        [
            "",
            "IDENTIFIER MULTIPLICITY",
            "-" * 76,
        ]
    )

    comparisons = [
        (
            "assistance_award_unique_key",
            "award_id_fain",
        ),
        (
            "award_id_fain",
            "assistance_award_unique_key",
        ),
        (
            "assistance_award_unique_key",
            "award_id_uri",
        ),
        (
            "award_id_uri",
            "assistance_award_unique_key",
        ),
        (
            "assistance_award_unique_key",
            "sai_number",
        ),
        (
            "sai_number",
            "assistance_award_unique_key",
        ),
    ]

    for left, right in comparisons:
        conflicts = count_conflicting_mappings(
            frame,
            left=left,
            right=right,
        )

        lines.append(
            f"{left} -> {right:<34} "
            f"{conflicts:>9,} multi-mapping identifiers"
        )

    transaction_key = frame[
        "assistance_transaction_unique_key"
    ]

    transaction_duplicate_rows = int(
        transaction_key.duplicated(
            keep=False
        ).sum()
    )

    award_key = frame[
        "assistance_award_unique_key"
    ]

    lines.extend(
        [
            "",
            "PRELIMINARY ASSESSMENT",
            "-" * 76,
            (
                "Duplicate transaction-key rows: "
                f"{transaction_duplicate_rows:,}"
            ),
            (
                "Distinct populated award keys: "
                f"{award_key.nunique(dropna=True):,}"
            ),
            "",
            (
                "Recommendation remains provisional until "
                "multi-mapping examples and correction/delete "
                "behavior are inspected."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    if not SOURCE_FILE.is_file():
        raise FileNotFoundError(
            f"Assistance source file not found: {SOURCE_FILE}"
        )

    frame = pd.read_csv(
        SOURCE_FILE,
        usecols=IDENTITY_COLUMNS,
        dtype="string",
        low_memory=False,
    )

    for column in IDENTITY_COLUMNS:
        frame[column] = clean_identifier(
            frame[column]
        )

    report = build_report(frame)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        report,
        encoding="utf-8",
        newline="\n",
    )

    print(report)
    print(f"Profile written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()