"""
ETL-004B — Inspect raw sources for award relationship enrichment.

This script is read-only. It displays the complete structure of the raw
procurement table and inspects one representative record from a selected
load batch.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from etl.common.db import get_connection
from etl.common.validation import print_header


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Inspect the raw procurement structure and identify potential "
            "sources for award relationship enrichment."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=4,
        help="Procurement load batch to inspect. Defaults to Batch 4.",
    )

    return parser.parse_args()


def get_raw_table_columns(cur) -> list[tuple[str, str, str]]:
    """
    Return all columns from procurement.raw_award_transaction.
    """
    cur.execute(
        """
        SELECT
            column_name,
            data_type,
            udt_name
        FROM information_schema.columns
        WHERE table_schema = 'procurement'
          AND table_name = 'raw_award_transaction'
        ORDER BY ordinal_position;
        """
    )

    return [
        (
            str(column_name),
            str(data_type),
            str(udt_name),
        )
        for column_name, data_type, udt_name in cur.fetchall()
    ]


def print_raw_table_columns(
    columns: list[tuple[str, str, str]],
) -> None:
    """
    Print the complete raw-table column structure.
    """
    print()
    print("=" * 76)
    print("RAW AWARD TRANSACTION COLUMNS")
    print("=" * 76)

    if not columns:
        print("No columns were found.")
        return

    print(f"{'Column':<45} {'Data type':<20} PostgreSQL type")
    print("-" * 76)

    for column_name, data_type, udt_name in columns:
        print(
            f"{column_name:<45} "
            f"{data_type:<20} "
            f"{udt_name}"
        )


def quote_identifier(identifier: str) -> str:
    """
    Safely quote a PostgreSQL identifier.
    """
    return '"' + identifier.replace('"', '""') + '"'


def get_sample_raw_record(
    cur,
    *,
    load_batch_id: int,
    columns: list[tuple[str, str, str]],
) -> tuple[list[str], tuple[Any, ...]] | None:
    """
    Return one representative raw record from the selected batch.
    """
    column_names = [column_name for column_name, _, _ in columns]

    if not column_names:
        return None

    select_columns = ",\n            ".join(
        quote_identifier(column_name)
        for column_name in column_names
    )

    cur.execute(
        f"""
        SELECT
            {select_columns}
        FROM procurement.raw_award_transaction
        WHERE load_batch_id = %s
        ORDER BY raw_award_transaction_id
        LIMIT 1;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        return None

    return column_names, row


def format_value(value: Any) -> str:
    """
    Format a database value for readable diagnostic output.
    """
    if value is None:
        return "NULL"

    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            indent=2,
            sort_keys=True,
            default=str,
        )

    return str(value)


def print_sample_raw_record(
    sample: tuple[list[str], tuple[Any, ...]] | None,
    *,
    load_batch_id: int,
) -> None:
    """
    Print one representative raw record.
    """
    print()
    print("=" * 76)
    print(f"SAMPLE RAW RECORD — BATCH {load_batch_id}")
    print("=" * 76)

    if sample is None:
        print(f"No raw records were found for Batch {load_batch_id}.")
        return

    column_names, row = sample

    for column_name, value in zip(column_names, row):
        print()
        print(f"{column_name}")
        print("-" * len(column_name))
        print(format_value(value))


def print_normalized_entities(cur) -> None:
    """
    Print currently available normalized recipients and agencies.
    """
    print()
    print("=" * 76)
    print("NORMALIZED RECIPIENTS")
    print("=" * 76)

    cur.execute(
        """
        SELECT
            recipient_id,
            recipient_uei,
            recipient_duns,
            recipient_name,
            recipient_name_normalized
        FROM procurement.recipient
        ORDER BY recipient_id;
        """
    )

    recipients = cur.fetchall()

    if not recipients:
        print("No normalized recipients found.")
    else:
        for recipient in recipients:
            print(recipient)

    print()
    print("=" * 76)
    print("NORMALIZED AGENCIES")
    print("=" * 76)

    cur.execute(
        """
        SELECT
            agency_id,
            agency_code,
            agency_name,
            agency_name_normalized,
            parent_agency_id,
            agency_level
        FROM procurement.agency
        ORDER BY agency_id;
        """
    )

    agencies = cur.fetchall()

    if not agencies:
        print("No normalized agencies found.")
    else:
        for agency in agencies:
            print(agency)


def main() -> None:
    """
    Run the ETL-004B source inspection.
    """
    args = parse_arguments()
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            columns = get_raw_table_columns(cur)

            print_header(
                "ETL-004B — AWARD RELATIONSHIP SOURCE INSPECTION",
                subtitle=f"Load batch ID: {args.load_batch_id}",
            )

            print_raw_table_columns(columns)

            sample = get_sample_raw_record(
                cur,
                load_batch_id=args.load_batch_id,
                columns=columns,
            )

            print_sample_raw_record(
                sample,
                load_batch_id=args.load_batch_id,
            )

            print_normalized_entities(cur)

    except Exception as exc:
        print()
        print("Award relationship source inspection failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()