from __future__ import annotations

import argparse
from pathlib import Path

from etl.loaders.chip_cms21 import (
    fetch_control_totals,
    load_cms21_workbook,
    washington_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load a Washington CMS-21 CHIP workbook into the raw and "
            "curated PostgreSQL tables."
        )
    )

    parser.add_argument(
        "--fiscal-year",
        type=int,
        required=True,
        help="Federal fiscal year represented by the workbook.",
    )

    parser.add_argument(
        "--workbook",
        type=Path,
        required=True,
        help="Path to the CMS-21 Excel workbook.",
    )

    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing load of the same workbook and fiscal year.",
    )

    parser.add_argument(
        "--notes",
        type=str,
        default=None,
        help="Optional provenance notes stored with the load batch.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = washington_config(args.fiscal_year)

    summary = load_cms21_workbook(
        workbook_path=args.workbook,
        config=config,
        replace=args.replace,
        notes=args.notes,
    )

    print()
    print("CMS-21 LOAD COMPLETE")
    print("-" * 72)
    print(f"Fiscal year:       {args.fiscal_year}")
    print(f"Workbook:          {args.workbook}")
    print(f"Load batch ID:     {summary.load_batch_id}")
    print(f"Raw rows:          {summary.raw_rows}")
    print(f"Curated rows:      {summary.curated_rows}")
    print(f"Control totals:    {summary.control_totals}")

    print()
    print("CONTROL TOTALS")
    print("-" * 72)

    control_totals = fetch_control_totals(summary.load_batch_id)

    for (
        worksheet_type,
        total_computable,
        federal_share,
        state_share,
        is_additive,
        is_adjustment,
    ) in control_totals:
        print(
            f"{worksheet_type:20} "
            f"Total={total_computable:>15,}  "
            f"Federal={federal_share:>15,}  "
            f"State={state_share:>15,}  "
            f"Additive={is_additive!s:<5}  "
            f"Adjustment={is_adjustment!s:<5}"
        )


if __name__ == "__main__":
    main()