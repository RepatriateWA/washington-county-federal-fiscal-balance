"""Compare FY2024 USAspending contract and assistance transaction schemas."""

from pathlib import Path

import pandas as pd


ROOT = Path(
    "data/raw/usaspending/FY2024_WA/original"
)

CONTRACTS_FILE = ROOT / (
    "Contracts_PrimeTransactions_"
    "2026-07-30_H01M09S18_1.csv"
)

ASSISTANCE_FILE = ROOT / (
    "Assistance_PrimeTransactions_"
    "2026-07-30_H01M19S42_1.csv"
)


def read_columns(path: Path) -> list[str]:
    """Read only the CSV header."""

    return list(
        pd.read_csv(
            path,
            nrows=0,
        ).columns
    )


def print_columns(
    title: str,
    columns: list[str],
) -> None:
    print()
    print(title)
    print("-" * 76)

    if not columns:
        print("(none)")
        return

    for number, column in enumerate(
        columns,
        start=1,
    ):
        print(f"{number:3}. {column}")


def main() -> None:
    contract_columns = read_columns(
        CONTRACTS_FILE
    )

    assistance_columns = read_columns(
        ASSISTANCE_FILE
    )

    contract_set = set(contract_columns)
    assistance_set = set(assistance_columns)

    shared = sorted(
        contract_set & assistance_set
    )

    contracts_only = sorted(
        contract_set - assistance_set
    )

    assistance_only = sorted(
        assistance_set - contract_set
    )

    print("=" * 76)
    print("USAspending Transaction Schema Comparison")
    print("=" * 76)

    print(
        f"Contract columns:       "
        f"{len(contract_columns)}"
    )
    print(
        f"Assistance columns:     "
        f"{len(assistance_columns)}"
    )
    print(
        f"Exact shared columns:   "
        f"{len(shared)}"
    )
    print(
        f"Contracts-only columns: "
        f"{len(contracts_only)}"
    )
    print(
        f"Assistance-only columns:"
        f" {len(assistance_only)}"
    )

    print_columns(
        "EXACT SHARED COLUMNS",
        shared,
    )

    print_columns(
        "CONTRACTS-ONLY COLUMNS",
        contracts_only,
    )

    print_columns(
        "ASSISTANCE-ONLY COLUMNS",
        assistance_only,
    )


if __name__ == "__main__":
    main()