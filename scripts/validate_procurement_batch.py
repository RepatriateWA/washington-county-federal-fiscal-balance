"""
ETL-114B — Validate a normalized procurement load batch.

Provides an end-to-end certification report for one procurement
load batch, including summary metrics and validation results.

Usage:
    python -m scripts.validate_procurement_batch

Optional explicit batch:
    python -m scripts.validate_procurement_batch \
        --load-batch-id 4
"""

from __future__ import annotations

import argparse

from etl.common.db import get_connection
from etl.common.validation import (
    print_header,
    print_metrics,
)

from etl.common.validation import (
    print_header,
    print_metrics,
    scalar_int,
)

def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Validate a normalized procurement load batch."
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=None,
        help=(
            "Validate a specific procurement load batch. "
            "Defaults to the newest completed batch."
        ),
    )

    return parser.parse_args()


def get_target_batch(
    conn,
    requested_batch_id: int | None,
) -> tuple[int, str, str]:
    """
    Return the target procurement batch metadata.

    Defaults to the newest completed batch containing raw observations.
    """
    with conn.cursor() as cur:
        if requested_batch_id is not None:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id) AS raw_row_count
                FROM procurement.load_batch AS lb
                LEFT JOIN procurement.raw_award_transaction AS raw
                  ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_batch_id = %s
                GROUP BY
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status;
                """,
                (requested_batch_id,),
            )
        else:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id) AS raw_row_count
                FROM procurement.load_batch AS lb
                JOIN procurement.raw_award_transaction AS raw
                  ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_status IN (
                    'COMPLETED',
                    'COMPLETED_WITH_REJECTIONS'
                )
                GROUP BY
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status
                ORDER BY lb.load_batch_id DESC
                LIMIT 1;
                """
            )

        row = cur.fetchone()

    if row is None:
        if requested_batch_id is None:
            raise ValueError(
                "No completed procurement batch containing raw rows was found."
            )

        raise ValueError(
            f"Procurement load batch {requested_batch_id} does not exist."
        )

    load_batch_id, source_file, load_status, raw_row_count = row

    if load_status not in {
        "COMPLETED",
        "COMPLETED_WITH_REJECTIONS",
    }:
        raise ValueError(
            f"Load batch {load_batch_id} has status {load_status!r}; "
            "a completed batch is required."
        )

    if int(raw_row_count) == 0:
        raise ValueError(
            f"Load batch {load_batch_id} contains no raw observations."
        )

    return (
        int(load_batch_id),
        str(source_file),
        str(load_status),
    )

   
def collect_metrics(
    conn,
    load_batch_id: int,
) -> dict[str, int]:
    """
    Collect summary metrics for one normalized procurement load batch.

    Entity counts are restricted to records referenced by transactions
    belonging to the selected batch.
    """
    with conn.cursor() as cur:
        raw_observations = scalar_int(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.raw_award_transaction
            WHERE load_batch_id = %s;
            """,
            (load_batch_id,),
        )

        award_transactions = scalar_int(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.award_transaction
            WHERE load_batch_id = %s;
            """,
            (load_batch_id,),
        )

        awards = scalar_int(
            cur,
            """
            SELECT COUNT(DISTINCT at.award_id)
            FROM procurement.award_transaction AS at
            WHERE at.load_batch_id = %s;
            """,
            (load_batch_id,),
        )

        recipients = scalar_int(
            cur,
            """
            SELECT COUNT(DISTINCT aw.recipient_id)
            FROM procurement.award_transaction AS at
            JOIN procurement.award AS aw
              ON aw.award_id = at.award_id
            WHERE at.load_batch_id = %s
              AND aw.recipient_id IS NOT NULL;
            """,
            (load_batch_id,),
        )

        agencies = scalar_int(
            cur,
            """
            SELECT COUNT(DISTINCT agency_id)
            FROM (
                SELECT aw.awarding_agency_id AS agency_id
                FROM procurement.award_transaction AS at
                JOIN procurement.award AS aw
                  ON aw.award_id = at.award_id
                WHERE at.load_batch_id = %s

                UNION

                SELECT aw.funding_agency_id AS agency_id
                FROM procurement.award_transaction AS at
                JOIN procurement.award AS aw
                  ON aw.award_id = at.award_id
                WHERE at.load_batch_id = %s
            ) AS referenced_agencies
            WHERE agency_id IS NOT NULL;
            """,
            (load_batch_id, load_batch_id),
        )

        naics = scalar_int(
            cur,
            """
            SELECT COUNT(DISTINCT at.naics_code)
            FROM procurement.award_transaction AS at
            WHERE at.load_batch_id = %s
              AND at.naics_code IS NOT NULL;
            """,
            (load_batch_id,),
        )

        psc = scalar_int(
            cur,
            """
            SELECT COUNT(DISTINCT at.psc_code)
            FROM procurement.award_transaction AS at
            WHERE at.load_batch_id = %s
              AND at.psc_code IS NOT NULL;
            """,
            (load_batch_id,),
        )

        canonical_places = scalar_int(
            cur,
            """
            SELECT COUNT(DISTINCT pop.place_id)
            FROM procurement.award_transaction AS at
            JOIN procurement.place_of_performance AS pop
              ON pop.award_transaction_id = at.award_transaction_id
            WHERE at.load_batch_id = %s
              AND pop.place_id IS NOT NULL;
            """,
            (load_batch_id,),
        )

    return {
        "Raw observations": raw_observations,
        "Awards": awards,
        "Award transactions": award_transactions,
        "Recipients": recipients,
        "Agencies": agencies,
        "NAICS": naics,
        "PSC": psc,
        "Canonical places": canonical_places,
    }

def main() -> None:
    """
    ETL-114B entry point.
    """
    args = parse_arguments()
    conn = get_connection()

    try:
        load_batch_id, source_file, load_status = get_target_batch(
            conn,
            args.load_batch_id,
        )

        metrics = collect_metrics(
        conn,
        load_batch_id,
        )

        print_header(
            "PROCUREMENT BATCH VALIDATION",
            subtitle=(
                f"Batch ID: {load_batch_id}\n"
                f"Source file: {source_file}\n"
                f"Load status: {load_status}"
            ),
        )
        
        print_metrics(metrics)

    except Exception as exc:
        print()
        print("Procurement batch validation failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()

if __name__ == "__main__":
    main()