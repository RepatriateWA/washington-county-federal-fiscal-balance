"""
ETL-172B-2
Structural and variable profile of IRS SOI Historic Table 2.

Acquisition has already been certified by ETL-172B-1.

This script:
- inventories TY2015-TY2023 CSV structure,
- tests for Rockefeller-relevant variables,
- inventories STATE / AGI_STUB structure,
- identifies Washington rows,
- records column drift,
- writes validation evidence only.

It does NOT:
- construct tax liability,
- sum allocation variables,
- calculate Washington shares,
- map tax years to fiscal years,
- extrapolate TY2024,
- write to PostgreSQL,
- authorize ledger inclusion.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd


SOURCE_DIR = Path(
    "data/raw/irs/historic_table_2/source"
)

OUTPUT_DIR = Path(
    "data/raw/irs/historic_table_2/"
    "validation/structural_profile_v0_1"
)

TAX_YEARS = tuple(range(2015, 2024))

TARGET_VARIABLES = (
    "A06500",
    "A85530",
    "A85300",
)

IDENTIFIER_CANDIDATES = (
    "STATE",
    "state",
    "State",
    "AGI_STUB",
    "agi_stub",
)


def source_path(tax_year: int) -> Path:
    return SOURCE_DIR / (
        f"irs_historic_table_2_"
        f"state_data_ty{tax_year}.csv"
    )


def normalize_columns(
    columns,
) -> list[str]:
    return [
        str(column).strip()
        for column in columns
    ]


def find_column(
    columns: list[str],
    candidate: str,
) -> str | None:
    candidate_upper = candidate.upper()

    for column in columns:
        if column.upper() == candidate_upper:
            return column

    return None


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 92)
    print(
        "IRS HISTORIC TABLE 2 STRUCTURAL PROFILE "
        "v0.1 — ETL-172B-2"
    )
    print("=" * 92)
    print()
    print("Tax years       : 2015-2023")
    print("Database writes : NONE")
    print("Liability calc  : NONE")
    print("FY/TY mapping   : NONE")
    print("TY2024 estimate : NONE")
    print()

    summary_rows = []
    variable_rows = []
    washington_rows = []
    column_inventory = {}

    reference_columns = None

    for tax_year in TAX_YEARS:
        path = source_path(tax_year)

        if not path.exists():
            raise FileNotFoundError(
                f"Missing source file: {path}"
            )

        df = pd.read_csv(
            path,
            dtype=str,
            low_memory=False,
        )

        df.columns = normalize_columns(
            df.columns
        )

        columns = list(df.columns)

        if reference_columns is None:
            reference_columns = columns

        state_column = find_column(
            columns,
            "STATE",
        )

        agi_column = find_column(
            columns,
            "AGI_STUB",
        )

        if state_column is None:
            raise RuntimeError(
                f"TY{tax_year}: STATE column not found."
            )

        if agi_column is None:
            raise RuntimeError(
                f"TY{tax_year}: AGI_STUB column not found."
            )

        state_values = (
            df[state_column]
            .dropna()
            .astype(str)
            .str.strip()
        )

        states = sorted(
            state_values.unique().tolist()
        )

        agi_values = sorted(
            df[agi_column]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        wa_mask = (
            df[state_column]
            .astype(str)
            .str.strip()
            .str.upper()
            == "WA"
        )

        wa = df.loc[wa_mask].copy()

        target_presence = {}

        for variable in TARGET_VARIABLES:
            actual_column = find_column(
                columns,
                variable,
            )

            present = actual_column is not None

            target_presence[
                variable
            ] = present

            variable_rows.append(
                {
                    "tax_year": tax_year,
                    "variable": variable,
                    "present": present,
                    "actual_column": (
                        actual_column or ""
                    ),
                }
            )

        summary_rows.append(
            {
                "tax_year": tax_year,
                "source_path": path.as_posix(),
                "row_count": len(df),
                "column_count": len(columns),
                "state_column": state_column,
                "agi_stub_column": agi_column,
                "distinct_state_codes": len(states),
                "distinct_agi_stubs": len(agi_values),
                "washington_rows": len(wa),
                "A06500_present": (
                    target_presence["A06500"]
                ),
                "A85530_present": (
                    target_presence["A85530"]
                ),
                "A85300_present": (
                    target_presence["A85300"]
                ),
            }
        )

        for _, row in wa.iterrows():
            record = {
                "tax_year": tax_year,
                "state": row[state_column],
                "agi_stub": row[agi_column],
            }

            for variable in TARGET_VARIABLES:
                actual_column = find_column(
                    columns,
                    variable,
                )

                record[variable] = (
                    row[actual_column]
                    if actual_column is not None
                    else None
                )

            washington_rows.append(
                record
            )

        column_inventory[str(tax_year)] = {
            "columns": columns,
            "state_values": states,
            "agi_stub_values": agi_values,
            "added_vs_2015": sorted(
                set(columns)
                - set(reference_columns)
            ),
            "missing_vs_2015": sorted(
                set(reference_columns)
                - set(columns)
            ),
        }

        print(
            f"TY{tax_year}: "
            f"{len(df):,} rows | "
            f"{len(columns):,} columns | "
            f"{len(states):,} state codes | "
            f"{len(wa):,} WA rows"
        )

        print(
            "  target variables: "
            + " | ".join(
                f"{variable}="
                f"{'YES' if target_presence[variable] else 'NO'}"
                for variable in TARGET_VARIABLES
            )
        )

    summary_path = (
        OUTPUT_DIR / "workbook_summary.csv"
    )

    variables_path = (
        OUTPUT_DIR / "target_variable_presence.csv"
    )

    washington_path = (
        OUTPUT_DIR / "washington_target_rows.csv"
    )

    inventory_path = (
        OUTPUT_DIR / "column_inventory.json"
    )

    report_path = (
        OUTPUT_DIR / "profile_report.txt"
    )

    pd.DataFrame(
        summary_rows
    ).to_csv(
        summary_path,
        index=False,
    )

    pd.DataFrame(
        variable_rows
    ).to_csv(
        variables_path,
        index=False,
    )

    pd.DataFrame(
        washington_rows
    ).to_csv(
        washington_path,
        index=False,
    )

    inventory_path.write_text(
        json.dumps(
            column_inventory,
            indent=2,
        ),
        encoding="utf-8",
    )

    all_targets_present = all(
        row[
            f"{variable}_present"
        ]
        for row in summary_rows
        for variable in TARGET_VARIABLES
    )

    report_lines = [
        "=" * 92,
        (
            "IRS HISTORIC TABLE 2 STRUCTURAL "
            "PROFILE v0.1 — ETL-172B-2"
        ),
        "=" * 92,
        "",
        "Tax years: 2015-2023",
        "",
    ]

    for row in summary_rows:
        report_lines.extend(
            [
                (
                    f"TY{row['tax_year']}: "
                    f"{row['row_count']:,} rows | "
                    f"{row['column_count']:,} columns | "
                    f"{row['distinct_state_codes']:,} "
                    f"state codes | "
                    f"{row['washington_rows']:,} WA rows"
                ),
                (
                    "  A06500: "
                    f"{'PRESENT' if row['A06500_present'] else 'MISSING'}"
                ),
                (
                    "  A85530: "
                    f"{'PRESENT' if row['A85530_present'] else 'MISSING'}"
                ),
                (
                    "  A85300: "
                    f"{'PRESENT' if row['A85300_present'] else 'MISSING'}"
                ),
                "",
            ]
        )

    report_lines.extend(
        [
            "-" * 92,
            "TARGET VARIABLE COVERAGE",
            "-" * 92,
            "",
            (
                "All three Rockefeller-relevant "
                "variables present in every year: "
                f"{'YES' if all_targets_present else 'NO'}"
            ),
            "",
            "No liability calculation performed.",
            "No Washington allocation share calculated.",
            "No FY/TY mapping performed.",
            "No TY2024 extrapolation performed.",
            "No database writes performed.",
            "",
            (
                "PROFILE RESULT: "
                + (
                    "STRUCTURALLY COMPLETE"
                    if all_targets_present
                    else "REVIEW REQUIRED"
                )
            ),
        ]
    )

    report_path.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 92)
    print("PROFILE SUMMARY")
    print("=" * 92)
    print()
    print(
        "All target variables present "
        "TY2015-TY2023: "
        f"{'YES' if all_targets_present else 'NO'}"
    )
    print()
    print("Outputs:")
    print(f"  {summary_path}")
    print(f"  {variables_path}")
    print(f"  {washington_path}")
    print(f"  {inventory_path}")
    print(f"  {report_path}")
    print()
    print(
        "PROFILE RESULT: "
        + (
            "STRUCTURALLY COMPLETE"
            if all_targets_present
            else "REVIEW REQUIRED"
        )
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())

    except Exception as exc:
        print()
        print("=" * 92, file=sys.stderr)
        print(
            "PROFILE RESULT: FAIL",
            file=sys.stderr,
        )
        print("=" * 92, file=sys.stderr)
        print(
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise