"""
ETL-114 — Procurement Batch Certification command-line interface.

The certification implementation resides in:

    etl.validation.procurement

This script is the command-line entry point only.
"""

from __future__ import annotations

import argparse

from etl.common.db import get_connection
from etl.validation.procurement.certification import (
    run_certification,
)
from etl.validation.procurement.reporting import (
    print_report,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run ETL-114 procurement certification checks "
            "for one load batch."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Procurement load batch ID to certify.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            summary = run_certification(
                cur,
                load_batch_id=args.load_batch_id,
            )

        print_report(summary)

        if not summary.is_certified:
            raise SystemExit(1)

    except SystemExit:
        raise

    except Exception as exc:
        print()
        print("Procurement certification failed unexpectedly.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()