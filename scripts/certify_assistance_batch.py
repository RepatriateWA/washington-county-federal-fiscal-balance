"""
ETL-115 — Assistance Batch Certification command-line interface.
"""
from __future__ import annotations
import argparse
from etl.common.db import get_connection
from etl.validation.assistance.certification import run_certification
from etl.validation.assistance.reporting import print_report

def parse_arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run ETL-115 assistance certification checks for one analytical load batch."
    )
    p.add_argument("--load-batch-id", type=int, required=True)
    return p.parse_args()

def main() -> None:
    args = parse_arguments()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            summary = run_certification(cur, load_batch_id=args.load_batch_id)
        print_report(summary)
        if not summary.is_certified:
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as exc:
        print()
        print("Assistance certification failed unexpectedly.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    finally:
        conn.close()

if __name__ == "__main__":
    main()
