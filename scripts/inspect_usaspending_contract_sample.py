"""Inspect a USAspending contract transaction export before ETL development.

The script accepts either:
- a CSV file,
- a ZIP archive containing CSV files, or
- no argument, in which case it searches data/raw/usaspending/contracts.

It reports:
- source file information,
- column names,
- row count,
- missing-value rates,
- candidate identifier uniqueness,
- obligation statistics,
- fiscal-year and geography values,
- representative values for important fields.
"""

from __future__ import annotations

import argparse
import csv
import sys
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator, TextIO


DEFAULT_DIRECTORY = Path("data/raw/usaspending/contracts")

TRANSACTION_ID_CANDIDATES = (
    "contract_transaction_unique_key",
    "transaction_id",
)

AWARD_ID_CANDIDATES = (
    "contract_award_unique_key",
    "generated_unique_award_id",
    "award_id_piid",
)

OBLIGATION_CANDIDATES = (
    "federal_action_obligation",
    "federal_action_obligation_amount",
    "action_obligation",
)

FISCAL_YEAR_CANDIDATES = (
    "action_date_fiscal_year",
    "fiscal_year",
)

ACTION_DATE_CANDIDATES = (
    "action_date",
)

STATE_CANDIDATES = (
    "primary_place_of_performance_state_code",
    "place_of_performance_state_code",
    "recipient_state_code",
)

COUNTY_CANDIDATES = (
    "primary_place_of_performance_county_name",
    "primary_place_of_performance_county_code",
    "place_of_performance_county_name",
    "place_of_performance_county_code",
)

IMPORTANT_FIELD_PATTERNS = (
    "award",
    "transaction",
    "piid",
    "recipient",
    "uei",
    "duns",
    "obligation",
    "action_date",
    "fiscal",
    "awarding_agency",
    "awarding_sub_agency",
    "funding_agency",
    "funding_sub_agency",
    "place_of_performance",
    "naics",
    "product_or_service",
    "description",
    "modification",
)


def normalize_column_name(value: str) -> str:
    """Return a normalized form suitable for column matching."""
    return (
        value.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def discover_source(path_argument: str | None) -> Path:
    """Resolve the source file from an argument or the default directory."""
    if path_argument:
        source = Path(path_argument)
        if not source.exists():
            raise FileNotFoundError(f"Source file does not exist: {source}")
        return source

    if not DEFAULT_DIRECTORY.exists():
        raise FileNotFoundError(
            f"Directory does not exist: {DEFAULT_DIRECTORY}"
        )

    candidates = sorted(
        path
        for path in DEFAULT_DIRECTORY.iterdir()
        if path.is_file() and path.suffix.lower() in {".csv", ".zip"}
    )

    if not candidates:
        raise FileNotFoundError(
            f"No CSV or ZIP files found in {DEFAULT_DIRECTORY}"
        )

    if len(candidates) > 1:
        print("Multiple source files found:")
        for candidate in candidates:
            print(f"  {candidate}")

        print(f"\nUsing the most recently modified file: "
              f"{max(candidates, key=lambda item: item.stat().st_mtime)}")

    return max(candidates, key=lambda item: item.stat().st_mtime)


def open_csv_source(source: Path) -> tuple[TextIO, str, zipfile.ZipFile | None]:
    """Open a CSV directly or open the first CSV contained in a ZIP archive."""
    if source.suffix.lower() == ".csv":
        handle = source.open(
            "r",
            encoding="utf-8-sig",
            newline="",
            errors="replace",
        )
        return handle, source.name, None

    if source.suffix.lower() != ".zip":
        raise ValueError(f"Unsupported source type: {source.suffix}")

    archive = zipfile.ZipFile(source)

    csv_members = sorted(
        member
        for member in archive.namelist()
        if member.lower().endswith(".csv")
        and not member.endswith("/")
    )

    if not csv_members:
        archive.close()
        raise ValueError(f"No CSV files found inside ZIP archive: {source}")

    print("\nCSV files inside archive:")
    for member in csv_members:
        print(f"  {member}")

    selected_member = csv_members[0]
    binary_handle = archive.open(selected_member)
    text_handle = __import__("io").TextIOWrapper(
        binary_handle,
        encoding="utf-8-sig",
        newline="",
        errors="replace",
    )

    return text_handle, selected_member, archive


def find_column(
    normalized_columns: dict[str, str],
    candidates: Iterable[str],
) -> str | None:
    """Return the original column name matching the first candidate found."""
    for candidate in candidates:
        if candidate in normalized_columns:
            return normalized_columns[candidate]
    return None


def decimal_value(raw_value: str | None) -> Decimal | None:
    """Convert a text value to Decimal, returning None for blanks or errors."""
    if raw_value is None:
        return None

    cleaned = raw_value.strip().replace(",", "").replace("$", "")

    if not cleaned:
        return None

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def percentage(numerator: int, denominator: int) -> float:
    """Calculate a percentage safely."""
    if denominator == 0:
        return 0.0
    return numerator / denominator * 100.0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a USAspending contract transaction export."
    )
    parser.add_argument(
        "source",
        nargs="?",
        help=(
            "CSV or ZIP source path. If omitted, the newest file in "
            "data/raw/usaspending/contracts is used."
        ),
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=5,
        help="Maximum representative values retained per important column.",
    )
    args = parser.parse_args()

    source: Path | None = None
    csv_handle: TextIO | None = None
    archive: zipfile.ZipFile | None = None

    try:
        source = discover_source(args.source)

        print("USAspending Contract Sample Inspection")
        print("=" * 88)
        print(f"Source: {source}")
        print(f"Size:   {source.stat().st_size:,} bytes")

        csv_handle, internal_name, archive = open_csv_source(source)
        print(f"CSV:    {internal_name}")

        reader = csv.DictReader(csv_handle)

        if not reader.fieldnames:
            raise ValueError("The CSV has no header row.")

        original_columns = [
            column.strip() if column is not None else ""
            for column in reader.fieldnames
        ]

        normalized_columns = {
            normalize_column_name(column): column
            for column in original_columns
            if column
        }

        transaction_column = find_column(
            normalized_columns,
            TRANSACTION_ID_CANDIDATES,
        )
        award_column = find_column(
            normalized_columns,
            AWARD_ID_CANDIDATES,
        )
        obligation_column = find_column(
            normalized_columns,
            OBLIGATION_CANDIDATES,
        )
        fiscal_year_column = find_column(
            normalized_columns,
            FISCAL_YEAR_CANDIDATES,
        )
        action_date_column = find_column(
            normalized_columns,
            ACTION_DATE_CANDIDATES,
        )
        state_column = find_column(
            normalized_columns,
            STATE_CANDIDATES,
        )

        county_columns = [
            original
            for normalized, original in normalized_columns.items()
            if normalized in COUNTY_CANDIDATES
        ]

        important_columns = [
            original
            for normalized, original in normalized_columns.items()
            if any(pattern in normalized for pattern in IMPORTANT_FIELD_PATTERNS)
        ]

        missing_counts: Counter[str] = Counter()
        value_samples: dict[str, list[str]] = defaultdict(list)
        value_sample_sets: dict[str, set[str]] = defaultdict(set)

        transaction_ids: set[str] = set()
        duplicate_transaction_count = 0
        blank_transaction_count = 0

        award_ids: set[str] = set()
        blank_award_count = 0

        fiscal_year_counts: Counter[str] = Counter()
        state_counts: Counter[str] = Counter()
        county_counts: dict[str, Counter[str]] = {
            column: Counter() for column in county_columns
        }

        obligation_count = 0
        obligation_invalid_count = 0
        obligation_positive_count = 0
        obligation_negative_count = 0
        obligation_zero_count = 0
        obligation_total = Decimal("0")
        obligation_minimum: Decimal | None = None
        obligation_maximum: Decimal | None = None

        row_count = 0

        for row_count, row in enumerate(reader, start=1):
            for column in original_columns:
                value = row.get(column)

                if value is None or not value.strip():
                    missing_counts[column] += 1
                    continue

                if (
                    column in important_columns
                    and len(value_samples[column]) < args.sample_limit
                    and value not in value_sample_sets[column]
                ):
                    value_samples[column].append(value)
                    value_sample_sets[column].add(value)

            if transaction_column:
                transaction_id = (row.get(transaction_column) or "").strip()

                if not transaction_id:
                    blank_transaction_count += 1
                elif transaction_id in transaction_ids:
                    duplicate_transaction_count += 1
                else:
                    transaction_ids.add(transaction_id)

            if award_column:
                award_id = (row.get(award_column) or "").strip()

                if not award_id:
                    blank_award_count += 1
                else:
                    award_ids.add(award_id)

            if fiscal_year_column:
                value = (row.get(fiscal_year_column) or "").strip()
                fiscal_year_counts[value or "<BLANK>"] += 1

            if state_column:
                value = (row.get(state_column) or "").strip()
                state_counts[value or "<BLANK>"] += 1

            for county_column in county_columns:
                value = (row.get(county_column) or "").strip()
                county_counts[county_column][value or "<BLANK>"] += 1

            if obligation_column:
                raw_obligation = row.get(obligation_column)
                obligation = decimal_value(raw_obligation)

                if raw_obligation and raw_obligation.strip() and obligation is None:
                    obligation_invalid_count += 1

                if obligation is not None:
                    obligation_count += 1
                    obligation_total += obligation

                    if obligation > 0:
                        obligation_positive_count += 1
                    elif obligation < 0:
                        obligation_negative_count += 1
                    else:
                        obligation_zero_count += 1

                    if (
                        obligation_minimum is None
                        or obligation < obligation_minimum
                    ):
                        obligation_minimum = obligation

                    if (
                        obligation_maximum is None
                        or obligation > obligation_maximum
                    ):
                        obligation_maximum = obligation

        print("\nFile summary")
        print("-" * 88)
        print(f"Rows:    {row_count:,}")
        print(f"Columns: {len(original_columns):,}")

        print("\nDetected key fields")
        print("-" * 88)
        print(f"Transaction identifier: {transaction_column or 'NOT FOUND'}")
        print(f"Award identifier:       {award_column or 'NOT FOUND'}")
        print(f"Obligation amount:      {obligation_column or 'NOT FOUND'}")
        print(f"Fiscal year:            {fiscal_year_column or 'NOT FOUND'}")
        print(f"Action date:            {action_date_column or 'NOT FOUND'}")
        print(f"Performance state:      {state_column or 'NOT FOUND'}")
        print(
            "Performance county:     "
            + (", ".join(county_columns) if county_columns else "NOT FOUND")
        )

        print("\nColumn inventory")
        print("-" * 88)
        for number, column in enumerate(original_columns, start=1):
            print(f"{number:>3}. {column}")

        print("\nMissingness")
        print("-" * 88)
        print(f"{'Column':55} {'Missing':>12} {'Percent':>10}")
        print("-" * 88)

        for column in sorted(
            original_columns,
            key=lambda item: (-missing_counts[item], item.lower()),
        ):
            missing = missing_counts[column]
            print(
                f"{column[:55]:55} "
                f"{missing:>12,} "
                f"{percentage(missing, row_count):>9.2f}%"
            )

        if transaction_column:
            print("\nTransaction identifier review")
            print("-" * 88)
            print(f"Column:                 {transaction_column}")
            print(f"Distinct nonblank IDs:  {len(transaction_ids):,}")
            print(f"Blank IDs:              {blank_transaction_count:,}")
            print(f"Duplicate occurrences:  {duplicate_transaction_count:,}")

        if award_column:
            print("\nAward identifier review")
            print("-" * 88)
            print(f"Column:                 {award_column}")
            print(f"Distinct nonblank IDs:  {len(award_ids):,}")
            print(f"Blank IDs:              {blank_award_count:,}")

        if obligation_column:
            print("\nFederal action obligation review")
            print("-" * 88)
            print(f"Column:           {obligation_column}")
            print(f"Numeric values:   {obligation_count:,}")
            print(f"Invalid values:   {obligation_invalid_count:,}")
            print(f"Positive values:  {obligation_positive_count:,}")
            print(f"Negative values:  {obligation_negative_count:,}")
            print(f"Zero values:      {obligation_zero_count:,}")
            print(f"Net obligation:   {obligation_total:,.2f}")
            print(
                "Minimum:          "
                f"{obligation_minimum:,.2f}"
                if obligation_minimum is not None
                else "Minimum:          N/A"
            )
            print(
                "Maximum:          "
                f"{obligation_maximum:,.2f}"
                if obligation_maximum is not None
                else "Maximum:          N/A"
            )

        if fiscal_year_counts:
            print("\nFiscal-year values")
            print("-" * 88)
            for value, count in fiscal_year_counts.most_common():
                print(f"{value:<30} {count:>12,}")

        if state_counts:
            print("\nPlace-of-performance state values")
            print("-" * 88)
            for value, count in state_counts.most_common(20):
                print(f"{value:<30} {count:>12,}")

        for county_column, counts in county_counts.items():
            print(f"\nCounty values: {county_column}")
            print("-" * 88)
            for value, count in counts.most_common(20):
                print(f"{value[:60]:<60} {count:>12,}")

        print("\nRepresentative values for important fields")
        print("-" * 88)

        for column in important_columns:
            samples = value_samples.get(column, [])

            if not samples:
                continue

            print(f"\n{column}")
            for sample in samples:
                compact_sample = " ".join(sample.split())
                print(f"  {compact_sample[:250]}")

        print("\nINSPECTION COMPLETED")
        return 0

    except Exception as exc:
        print(f"Inspection failed: {exc}", file=sys.stderr)
        return 1

    finally:
        if csv_handle is not None:
            csv_handle.close()

        if archive is not None:
            archive.close()


if __name__ == "__main__":
    raise SystemExit(main())