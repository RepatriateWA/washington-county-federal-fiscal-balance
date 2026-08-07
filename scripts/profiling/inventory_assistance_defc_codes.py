"""Inventory DEFC codes observed in FY2024 Washington assistance data.

This script parses code-description pairs without interpreting their
funding family. Classification will occur only after authoritative
federal documentation and citations are assembled.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd


SOURCE_FILE = Path(
    "data/raw/usaspending/FY2024_WA/original/"
    "Assistance_PrimeTransactions_2026-07-30_H01M19S42_1.csv"
)

OUTPUT_DIRECTORY = Path(
    "data/raw/usaspending/FY2024_WA/profiling"
)

CSV_OUTPUT = (
    OUTPUT_DIRECTORY
    / "Assistance_DEFC_Observed_Code_Inventory.csv"
)

TEXT_OUTPUT = (
    OUTPUT_DIRECTORY
    / "Assistance_Profile_009_DEFC_Code_Inventory.txt"
)

MARKDOWN_OUTPUT = Path(
    "docs/research/DEFC_CLASSIFICATION.md"
)

DEFC_FIELD = (
    "disaster_emergency_fund_codes_for_overall_award"
)

USE_COLUMNS = [
    "assistance_award_unique_key",
    "assistance_transaction_unique_key",
    "action_date",
    DEFC_FIELD,
]

SEGMENT_SPLITTER = re.compile(
    r";+|[|](?=[A-Za-z0-9]+\s*:)"
)

CODE_DESCRIPTION_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9]+)\s*:\s*(.*?)\s*$"
)


@dataclass
class DefcCodeProfile:
    """Observed properties for one DEFC code."""

    code: str
    descriptions: set[str] = field(default_factory=set)
    awards: set[str] = field(default_factory=set)
    transactions: set[str] = field(default_factory=set)
    raw_combinations: set[str] = field(default_factory=set)
    first_action_date: date | None = None
    last_action_date: date | None = None

    def observe_date(
        self,
        action_date: date | None,
    ) -> None:
        if action_date is None:
            return

        if (
            self.first_action_date is None
            or action_date < self.first_action_date
        ):
            self.first_action_date = action_date

        if (
            self.last_action_date is None
            or action_date > self.last_action_date
        ):
            self.last_action_date = action_date


def clean_text(value: object) -> str | None:
    """Normalize a source text value."""

    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    return text


def parse_action_date(
    value: object,
) -> date | None:
    """Parse one source action date."""

    text = clean_text(value)

    if text is None:
        return None

    parsed = pd.to_datetime(
        text,
        errors="coerce",
    )

    if pd.isna(parsed):
        return None

    return parsed.date()


def parse_defc_segments(
    raw_value: str,
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Parse one raw DEFC combination.

    Returns:
        parsed code-description pairs;
        unparsed segments requiring review.
    """

    observations: list[tuple[str, str]] = []
    unparsed: list[str] = []

    for segment in SEGMENT_SPLITTER.split(raw_value):
        segment = segment.strip()

        if not segment:
            continue

        match = CODE_DESCRIPTION_PATTERN.match(
            segment
        )

        if match is None:
            unparsed.append(segment)
            continue

        code = match.group(1).upper()
        description = match.group(2).strip()

        observations.append(
            (
                code,
                description,
            )
        )

    return observations, unparsed


def build_inventory(
    frame: pd.DataFrame,
) -> tuple[
    dict[str, DefcCodeProfile],
    dict[str, int],
]:
    """Build observed DEFC profiles and unparsed-segment counts."""

    profiles: dict[str, DefcCodeProfile] = {}
    unparsed_counts: dict[str, int] = defaultdict(int)

    for row in frame.itertuples(
        index=False,
        name=None,
    ):
        (
            award_key_value,
            transaction_key_value,
            action_date_value,
            raw_defc_value,
        ) = row

        raw_defc = clean_text(raw_defc_value)

        if raw_defc is None:
            continue

        award_key = clean_text(
            award_key_value
        )
        transaction_key = clean_text(
            transaction_key_value
        )
        action_date = parse_action_date(
            action_date_value
        )

        parsed, unparsed = parse_defc_segments(
            raw_defc
        )

        for segment in unparsed:
            unparsed_counts[segment] += 1

        # A code should count at most once per source row,
        # even if repeated in an unusual raw combination.
        row_codes_seen: set[str] = set()

        for code, description in parsed:
            if code in row_codes_seen:
                continue

            row_codes_seen.add(code)

            profile = profiles.setdefault(
                code,
                DefcCodeProfile(code=code),
            )

            if description:
                profile.descriptions.add(
                    description
                )

            if award_key is not None:
                profile.awards.add(
                    award_key
                )

            if transaction_key is not None:
                profile.transactions.add(
                    transaction_key
                )

            profile.raw_combinations.add(
                raw_defc
            )

            profile.observe_date(
                action_date
            )

    return profiles, dict(unparsed_counts)


def inventory_rows(
    profiles: dict[str, DefcCodeProfile],
) -> list[dict[str, object]]:
    """Convert profiles into deterministic output rows."""

    rows: list[dict[str, object]] = []

    for code in sorted(profiles):
        profile = profiles[code]

        descriptions = sorted(
            profile.descriptions
        )

        rows.append(
            {
                "defc_code": code,
                "observed_description_count": len(
                    descriptions
                ),
                "observed_descriptions": " | ".join(
                    descriptions
                ),
                "source_row_count": len(
                    profile.transactions
                ),
                "award_count": len(
                    profile.awards
                ),
                "raw_combination_count": len(
                    profile.raw_combinations
                ),
                "first_action_date": (
                    profile.first_action_date.isoformat()
                    if profile.first_action_date
                    else ""
                ),
                "last_action_date": (
                    profile.last_action_date.isoformat()
                    if profile.last_action_date
                    else ""
                ),
            }
        )

    return rows


def write_csv(
    rows: list[dict[str, object]],
) -> None:
    """Write the observed-code inventory."""

    fieldnames = [
        "defc_code",
        "observed_description_count",
        "observed_descriptions",
        "source_row_count",
        "award_count",
        "raw_combination_count",
        "first_action_date",
        "last_action_date",
    ]

    with CSV_OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(rows)


def build_text_report(
    *,
    frame: pd.DataFrame,
    rows: list[dict[str, object]],
    unparsed_counts: dict[str, int],
) -> str:
    """Build a human-readable inventory report."""

    populated_rows = int(
        frame[DEFC_FIELD].notna().sum()
    )

    lines: list[str] = [
        "=" * 88,
        "ETL-005A.9 — ASSISTANCE DEFC OBSERVED-CODE INVENTORY",
        "=" * 88,
        f"Source file: {SOURCE_FILE}",
        f"Source rows examined: {len(frame):,}",
        f"Rows with DEFC values: {populated_rows:,}",
        f"Distinct parsed DEFC codes: {len(rows):,}",
        (
            "Distinct unparsed segments: "
            f"{len(unparsed_counts):,}"
        ),
        "",
        "OBSERVED CODES",
        "-" * 88,
    ]

    for row in rows:
        descriptions = str(
            row["observed_descriptions"]
        )

        lines.append(
            f"{row['defc_code']:<6} "
            f"rows={int(row['source_row_count']):>7,}  "
            f"awards={int(row['award_count']):>7,}  "
            f"descriptions="
            f"{int(row['observed_description_count']):>3,}  "
            f"{descriptions}"
        )

    lines.extend(
        [
            "",
            "UNPARSED SEGMENTS",
            "-" * 88,
        ]
    )

    if not unparsed_counts:
        lines.append("(none)")
    else:
        for segment, count in sorted(
            unparsed_counts.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        ):
            lines.append(
                f"{count:>8,}  {segment}"
            )

    lines.extend(
        [
            "",
            "INTERPRETIVE LIMIT",
            "-" * 88,
            (
                "This inventory records what the source contains. "
                "It does not classify any DEFC code as COVID, IIJA, "
                "ordinary, disaster, or another funding family."
            ),
            (
                "Classification requires authoritative federal "
                "documentation and a recorded citation."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def build_markdown(
    rows: list[dict[str, object]],
) -> str:
    """Build the initial research-document scaffold."""

    lines: list[str] = [
        "# DEFC Classification Research",
        "",
        "**Status:** Observed-code inventory; classification pending",
        "",
        "## Purpose",
        "",
        (
            "Document every Disaster Emergency Fund Code observed "
            "in the Washington USAspending datasets and establish "
            "an authoritative, cited classification for analytical use."
        ),
        "",
        "No code is classified solely from its label or from project inference.",
        "",
        "## Classification fields",
        "",
        "| Field | Meaning |",
        "|---|---|",
        "| Funding family | Ordinary, COVID, IIJA, other disaster, other emergency, or unresolved |",
        "| Extraordinary | Whether the code represents extraordinary funding |",
        "| COVID related | Whether the code is authoritative evidence of COVID funding |",
        "| IIJA related | Whether the code is authoritative evidence of IIJA funding |",
        "| Confidence | High, medium, low, or unresolved |",
        "| Citation | Primary federal source supporting the classification |",
        "",
        "## Observed codes",
        "",
        (
            "| Code | Observed description(s) | Rows | Awards | "
            "First action | Last action | Proposed family | "
            "COVID | IIJA | Confidence | Citation | Notes |"
        ),
        (
            "|---|---|---:|---:|---|---|---|:---:|:---:|"
            "---|---|---|"
        ),
    ]

    for row in rows:
        description = str(
            row["observed_descriptions"]
        ).replace("|", "<br>")

        lines.append(
            f"| {row['defc_code']} "
            f"| {description} "
            f"| {row['source_row_count']} "
            f"| {row['award_count']} "
            f"| {row['first_action_date']} "
            f"| {row['last_action_date']} "
            "| UNRESOLVED "
            "| "
            "| "
            "| UNRESOLVED "
            "| "
            "| |"
        )

    lines.extend(
        [
            "",
            "## Research requirements",
            "",
            "For every observed code:",
            "",
            "1. Locate the controlling OMB, Treasury, or USAspending documentation.",
            "2. Record the official description.",
            "3. Record the associated public law or appropriation where applicable.",
            "4. Determine whether it is COVID-related, IIJA-related, another extraordinary category, or ordinary.",
            "5. Record the primary citation.",
            "6. Document ambiguity rather than resolving it silently.",
            "",
            "## Measurement policy",
            "",
            (
                "Annual fiscal flows will be measured from transaction-level "
                "`federal_action_obligation` values."
            ),
            "",
            (
                "Overall-award COVID and IIJA fields will be used for "
                "classification support and reconciliation, not as annual "
                "transaction-flow measures."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    if not SOURCE_FILE.is_file():
        raise FileNotFoundError(
            f"Source file not found: {SOURCE_FILE}"
        )

    frame = pd.read_csv(
        SOURCE_FILE,
        usecols=USE_COLUMNS,
        dtype="string",
        low_memory=False,
    )

    # read_csv preserves source-file column order when usecols is used.
    # Reorder explicitly because build_inventory() unpacks rows by position.
    # Guarantee the positional order expected by build_inventory().
    frame = frame.loc[:, USE_COLUMNS]

    profiles, unparsed_counts = (
        build_inventory(frame)
    )

    rows = inventory_rows(
        profiles
    )

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    MARKDOWN_OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(rows)

    report = build_text_report(
        frame=frame,
        rows=rows,
        unparsed_counts=unparsed_counts,
    )

    TEXT_OUTPUT.write_text(
        report,
        encoding="utf-8",
        newline="\n",
    )

    MARKDOWN_OUTPUT.write_text(
        build_markdown(rows),
        encoding="utf-8",
        newline="\n",
    )

    print(report)
    print(f"CSV inventory written to: {CSV_OUTPUT}")
    print(f"Text report written to:   {TEXT_OUTPUT}")
    print(f"Research scaffold written to: {MARKDOWN_OUTPUT}")


if __name__ == "__main__":
    main()