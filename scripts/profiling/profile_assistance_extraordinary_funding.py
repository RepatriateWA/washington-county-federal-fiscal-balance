"""Profile extraordinary funding in FY2024 Washington assistance data."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


SOURCE_FILE = Path(
    "data/raw/usaspending/FY2024_WA/original/"
    "Assistance_PrimeTransactions_2026-07-30_H01M19S42_1.csv"
)

PROFILE_DIRECTORY = Path(
    "data/raw/usaspending/FY2024_WA/profiling"
)

REPORT_FILE = (
    PROFILE_DIRECTORY
    / "Assistance_Profile_008_ExtraordinaryFunding.txt"
)

AGENCY_SUMMARY_FILE = (
    PROFILE_DIRECTORY
    / "Assistance_ExtraordinaryFunding_AgencySummary.csv"
)

LISTING_SUMMARY_FILE = (
    PROFILE_DIRECTORY
    / "Assistance_ExtraordinaryFunding_ListingSummary.csv"
)


AWARD_KEY = "assistance_award_unique_key"

COVID_OBLIGATION = (
    "obligated_amount_from_COVID-19_"
    "supplementals_for_overall_award"
)

COVID_OUTLAY = (
    "outlayed_amount_from_COVID-19_"
    "supplementals_for_overall_award"
)

IIJA_OBLIGATION = (
    "obligated_amount_from_IIJA_"
    "supplemental_for_overall_award"
)

IIJA_OUTLAY = (
    "outlayed_amount_from_IIJA_"
    "supplemental_for_overall_award"
)

DEFC_FIELD = (
    "disaster_emergency_fund_codes_for_overall_award"
)

MONEY_COLUMNS = [
    "federal_action_obligation",
    COVID_OBLIGATION,
    COVID_OUTLAY,
    IIJA_OBLIGATION,
    IIJA_OUTLAY,
]

USE_COLUMNS = [
    AWARD_KEY,
    "assistance_transaction_unique_key",
    "action_date",
    "action_date_fiscal_year",
    "awarding_agency_code",
    "awarding_agency_name",
    "cfda_number",
    "cfda_title",
    "recipient_state_code",
    "primary_place_of_performance_state_name",
    DEFC_FIELD,
    *MONEY_COLUMNS,
]


def clean_text(series: pd.Series) -> pd.Series:
    """Trim text and normalize blank-like values to null."""

    return (
        series.astype("string")
        .str.strip()
        .replace(
            {
                "": pd.NA,
                "NULL": pd.NA,
                "None": pd.NA,
                "nan": pd.NA,
            }
        )
    )


def parse_money(series: pd.Series) -> pd.Series:
    """Parse monetary source values without using binary floats."""

    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .replace("", pd.NA)
    )

    return pd.to_numeric(
        cleaned,
        errors="coerce",
    )


def money(value: float | int) -> str:
    """Format one monetary value."""

    return f"${value:,.2f}"


def profile_money_column(
    frame: pd.DataFrame,
    column: str,
) -> dict[str, int | float]:
    """Build descriptive statistics for one monetary column."""

    values = frame[column]
    populated = int(values.notna().sum())
    missing = int(values.isna().sum())
    zero = int((values == 0).sum())
    positive = int((values > 0).sum())
    negative = int((values < 0).sum())

    non_null = values.dropna()

    return {
        "populated": populated,
        "missing": missing,
        "zero": zero,
        "positive": positive,
        "negative": negative,
        "minimum": (
            float(non_null.min())
            if not non_null.empty
            else 0.0
        ),
        "maximum": (
            float(non_null.max())
            if not non_null.empty
            else 0.0
        ),
        "total": float(non_null.sum()),
    }


def print_money_profile(
    lines: list[str],
    *,
    label: str,
    statistics: dict[str, int | float],
) -> None:
    """Append one monetary profile to the report."""

    lines.extend(
        [
            label,
            "-" * 76,
            (
                f"Populated rows ................ "
                f"{statistics['populated']:,}"
            ),
            (
                f"Blank rows .................... "
                f"{statistics['missing']:,}"
            ),
            (
                f"Zero values ................... "
                f"{statistics['zero']:,}"
            ),
            (
                f"Positive values ............... "
                f"{statistics['positive']:,}"
            ),
            (
                f"Negative values ............... "
                f"{statistics['negative']:,}"
            ),
            (
                f"Minimum ....................... "
                f"{money(statistics['minimum'])}"
            ),
            (
                f"Maximum ....................... "
                f"{money(statistics['maximum'])}"
            ),
            (
                f"Total ......................... "
                f"{money(statistics['total'])}"
            ),
            "",
        ]
    )


def split_defc_values(value: object) -> list[str]:
    """
    Split a DEFC source value conservatively.

    The profiler preserves the original combination separately and
    derives individual tokens only for exploratory frequency counts.
    """

    if value is None or pd.isna(value):
        return []

    text = str(value).strip()

    if not text:
        return []

    for delimiter in [";", "|", ","]:
        text = text.replace(delimiter, " ")

    return [
        token.strip()
        for token in text.split()
        if token.strip()
    ]


def build_award_classification(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Build one derived extraordinary-funding row per award."""

    grouped = (
        frame.groupby(
            AWARD_KEY,
            dropna=False,
        )
        .agg(
            covid_obligation=(COVID_OBLIGATION, "max"),
            covid_outlay=(COVID_OUTLAY, "max"),
            iija_obligation=(IIJA_OBLIGATION, "max"),
            iija_outlay=(IIJA_OUTLAY, "max"),
            transaction_obligation=(
                "federal_action_obligation",
                "sum",
            ),
            transaction_count=(
                "assistance_transaction_unique_key",
                "nunique",
            ),
            defc_observation_count=(
                DEFC_FIELD,
                lambda values: int(values.notna().sum()),
            ),
        )
        .reset_index()
    )

    grouped["has_covid"] = (
        grouped[
            [
                "covid_obligation",
                "covid_outlay",
            ]
        ]
        .fillna(0)
        .ne(0)
        .any(axis=1)
    )

    grouped["has_iija"] = (
        grouped[
            [
                "iija_obligation",
                "iija_outlay",
            ]
        ]
        .fillna(0)
        .ne(0)
        .any(axis=1)
    )

    grouped["has_defc"] = (
        grouped["defc_observation_count"] > 0
    )

    grouped["extraordinary_classification"] = "ORDINARY_OR_UNCLASSIFIED"

    grouped.loc[
        grouped["has_covid"]
        & ~grouped["has_iija"],
        "extraordinary_classification",
    ] = "COVID"

    grouped.loc[
        ~grouped["has_covid"]
        & grouped["has_iija"],
        "extraordinary_classification",
    ] = "IIJA"

    grouped.loc[
        grouped["has_covid"]
        & grouped["has_iija"],
        "extraordinary_classification",
    ] = "COVID_AND_IIJA"

    grouped.loc[
        ~grouped["has_covid"]
        & ~grouped["has_iija"]
        & grouped["has_defc"],
        "extraordinary_classification",
    ] = "DEFC_OTHER_OR_UNRESOLVED"

    return grouped


def build_agency_summary(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize extraordinary funding by awarding agency."""

    award_agency = (
        frame.groupby(
            [
                AWARD_KEY,
                "awarding_agency_code",
                "awarding_agency_name",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            covid_obligation=(
                COVID_OBLIGATION,
                "max",
            ),
            covid_outlay=(
                COVID_OUTLAY,
                "max",
            ),
            iija_obligation=(
                IIJA_OBLIGATION,
                "max",
            ),
            iija_outlay=(
                IIJA_OUTLAY,
                "max",
            ),
            transaction_obligation=(
                "federal_action_obligation",
                "sum",
            ),
        )
    )

    return (
        award_agency.groupby(
            [
                "awarding_agency_code",
                "awarding_agency_name",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            award_count=(
                AWARD_KEY,
                "nunique",
            ),
            covid_obligation=(
                "covid_obligation",
                "sum",
            ),
            covid_outlay=(
                "covid_outlay",
                "sum",
            ),
            iija_obligation=(
                "iija_obligation",
                "sum",
            ),
            iija_outlay=(
                "iija_outlay",
                "sum",
            ),
            transaction_obligation=(
                "transaction_obligation",
                "sum",
            ),
        )
        .sort_values(
            [
                "covid_obligation",
                "covid_outlay",
            ],
            ascending=False,
        )
    )


def build_listing_summary(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize extraordinary funding by Assistance Listing."""

    award_listing = (
        frame.groupby(
            [
                AWARD_KEY,
                "cfda_number",
                "cfda_title",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            covid_obligation=(
                COVID_OBLIGATION,
                "max",
            ),
            covid_outlay=(
                COVID_OUTLAY,
                "max",
            ),
            iija_obligation=(
                IIJA_OBLIGATION,
                "max",
            ),
            iija_outlay=(
                IIJA_OUTLAY,
                "max",
            ),
        )
    )

    return (
        award_listing.groupby(
            [
                "cfda_number",
                "cfda_title",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            award_count=(
                AWARD_KEY,
                "nunique",
            ),
            covid_obligation=(
                "covid_obligation",
                "sum",
            ),
            covid_outlay=(
                "covid_outlay",
                "sum",
            ),
            iija_obligation=(
                "iija_obligation",
                "sum",
            ),
            iija_outlay=(
                "iija_outlay",
                "sum",
            ),
        )
        .sort_values(
            [
                "covid_obligation",
                "covid_outlay",
            ],
            ascending=False,
        )
    )


def build_report(
    frame: pd.DataFrame,
    *,
    award_profile: pd.DataFrame,
    agency_summary: pd.DataFrame,
    listing_summary: pd.DataFrame,
) -> str:
    """Build the complete profiling report."""

    lines: list[str] = [
        "=" * 76,
        "ETL-005A.8 — ASSISTANCE EXTRAORDINARY FUNDING PROFILE",
        "=" * 76,
        f"Source file: {SOURCE_FILE}",
        f"Rows examined: {len(frame):,}",
        (
            "Distinct awards: "
            f"{frame[AWARD_KEY].nunique(dropna=True):,}"
        ),
        "",
        "IMPORTANT INTERPRETIVE NOTE",
        "-" * 76,
        (
            "The COVID and IIJA fields are overall-award measures repeated "
            "across transaction rows. They must not be summed directly "
            "across all transactions."
        ),
        (
            "This profiler uses maximum observed overall-award values "
            "within each award before producing agency or listing totals."
        ),
        "",
    ]

    profiles = [
        (
            "COVID OBLIGATIONS — RAW ROW PROFILE",
            COVID_OBLIGATION,
        ),
        (
            "COVID OUTLAYS — RAW ROW PROFILE",
            COVID_OUTLAY,
        ),
        (
            "IIJA OBLIGATIONS — RAW ROW PROFILE",
            IIJA_OBLIGATION,
        ),
        (
            "IIJA OUTLAYS — RAW ROW PROFILE",
            IIJA_OUTLAY,
        ),
    ]

    for label, column in profiles:
        print_money_profile(
            lines,
            label=label,
            statistics=profile_money_column(
                frame,
                column,
            ),
        )

    original_defc = frame[DEFC_FIELD]
    populated_defc = original_defc.dropna()

    lines.extend(
        [
            "DISASTER EMERGENCY FUND CODE PROFILE",
            "-" * 76,
            (
                f"Populated rows ................ "
                f"{populated_defc.shape[0]:,}"
            ),
            (
                f"Blank rows .................... "
                f"{original_defc.isna().sum():,}"
            ),
            (
                f"Distinct raw combinations ..... "
                f"{populated_defc.nunique():,}"
            ),
            "",
            "TOP RAW DEFC COMBINATIONS",
            "-" * 76,
        ]
    )

    raw_counts = (
        populated_defc.value_counts()
        .head(25)
    )

    if raw_counts.empty:
        lines.append("(none)")
    else:
        for value, count in raw_counts.items():
            lines.append(
                f"{str(value):<55} {int(count):>10,}"
            )

    token_counts: dict[str, int] = {}

    for value in populated_defc:
        for token in split_defc_values(value):
            token_counts[token] = (
                token_counts.get(token, 0) + 1
            )

    lines.extend(
        [
            "",
            "TOP DERIVED DEFC TOKENS",
            "-" * 76,
        ]
    )

    for token, count in sorted(
        token_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    )[:25]:
        lines.append(
            f"{token:<25} {count:>10,}"
        )

    classification_counts = (
        award_profile[
            "extraordinary_classification"
        ]
        .value_counts()
    )

    lines.extend(
        [
            "",
            "AWARD CLASSIFICATION",
            "-" * 76,
        ]
    )

    for classification, count in classification_counts.items():
        lines.append(
            f"{classification:<35} {int(count):>10,}"
        )

    lines.extend(
        [
            "",
            "AWARD-LEVEL EXTRAORDINARY FUNDING TOTALS",
            "-" * 76,
            (
                "COVID obligations .............. "
                f"{money(award_profile['covid_obligation'].fillna(0).sum())}"
            ),
            (
                "COVID outlays .................. "
                f"{money(award_profile['covid_outlay'].fillna(0).sum())}"
            ),
            (
                "IIJA obligations ............... "
                f"{money(award_profile['iija_obligation'].fillna(0).sum())}"
            ),
            (
                "IIJA outlays ................... "
                f"{money(award_profile['iija_outlay'].fillna(0).sum())}"
            ),
            "",
            "TOP 20 AWARDING AGENCIES BY COVID OBLIGATIONS",
            "-" * 76,
        ]
    )

    top_agencies = agency_summary.head(20)

    if top_agencies.empty:
        lines.append("(none)")
    else:
        for row in top_agencies.itertuples(index=False):
            agency_name = (
                row.awarding_agency_name
                if not pd.isna(row.awarding_agency_name)
                else "(missing agency)"
            )

            lines.append(
                f"{str(agency_name)[:42]:<42} "
                f"awards={int(row.award_count):>7,}  "
                f"COVID={money(row.covid_obligation):>20}"
            )

    lines.extend(
        [
            "",
            "TOP 20 ASSISTANCE LISTINGS BY COVID OBLIGATIONS",
            "-" * 76,
        ]
    )

    top_listings = listing_summary.head(20)

    if top_listings.empty:
        lines.append("(none)")
    else:
        for row in top_listings.itertuples(index=False):
            number = (
                row.cfda_number
                if not pd.isna(row.cfda_number)
                else "(missing)"
            )

            title = (
                row.cfda_title
                if not pd.isna(row.cfda_title)
                else "(missing title)"
            )

            lines.append(
                f"{str(number):<10} "
                f"{str(title)[:36]:<36} "
                f"awards={int(row.award_count):>7,}  "
                f"COVID={money(row.covid_obligation):>20}"
            )

    recipient_states = (
        frame["recipient_state_code"]
        .fillna("(missing)")
        .value_counts()
        .head(20)
    )

    performance_states = (
        frame[
            "primary_place_of_performance_state_name"
        ]
        .fillna("(missing)")
        .value_counts()
        .head(20)
    )

    lines.extend(
        [
            "",
            "TOP RECIPIENT STATES BY SOURCE ROW COUNT",
            "-" * 76,
        ]
    )

    for state, count in recipient_states.items():
        lines.append(
            f"{str(state):<35} {int(count):>10,}"
        )

    lines.extend(
        [
            "",
            "TOP PERFORMANCE STATES BY SOURCE ROW COUNT",
            "-" * 76,
        ]
    )

    for state, count in performance_states.items():
        lines.append(
            f"{str(state):<35} {int(count):>10,}"
        )

    lines.extend(
        [
            "",
            "PRELIMINARY CLASSIFICATION POLICY",
            "-" * 76,
            (
                "COVID classification is based first on explicit "
                "USAspending COVID overall-award amount fields."
            ),
            (
                "IIJA classification is based first on explicit "
                "USAspending IIJA overall-award amount fields."
            ),
            (
                "DEFC-only awards remain separately classified until "
                "the authoritative meaning of each observed code is "
                "documented."
            ),
            (
                "Text matching is not used as primary evidence in this "
                "profile."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def write_csv(
    frame: pd.DataFrame,
    path: Path,
) -> None:
    """Write a deterministic UTF-8 CSV."""

    frame.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )


def main() -> None:
    if not SOURCE_FILE.is_file():
        raise FileNotFoundError(
            f"Assistance source file not found: {SOURCE_FILE}"
        )

    frame = pd.read_csv(
        SOURCE_FILE,
        usecols=USE_COLUMNS,
        dtype="string",
        low_memory=False,
    )

    text_columns = [
        column
        for column in USE_COLUMNS
        if column not in MONEY_COLUMNS
    ]

    for column in text_columns:
        frame[column] = clean_text(
            frame[column]
        )

    for column in MONEY_COLUMNS:
        frame[column] = parse_money(
            frame[column]
        )

    award_profile = build_award_classification(
        frame
    )

    agency_summary = build_agency_summary(
        frame
    )

    listing_summary = build_listing_summary(
        frame
    )

    report = build_report(
        frame,
        award_profile=award_profile,
        agency_summary=agency_summary,
        listing_summary=listing_summary,
    )

    PROFILE_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_FILE.write_text(
        report,
        encoding="utf-8",
        newline="\n",
    )

    write_csv(
        agency_summary,
        AGENCY_SUMMARY_FILE,
    )

    write_csv(
        listing_summary,
        LISTING_SUMMARY_FILE,
    )

    print(report)
    print(f"Report written to: {REPORT_FILE}")
    print(
        "Agency summary written to: "
        f"{AGENCY_SUMMARY_FILE}"
    )
    print(
        "Listing summary written to: "
        f"{LISTING_SUMMARY_FILE}"
    )


if __name__ == "__main__":
    main()