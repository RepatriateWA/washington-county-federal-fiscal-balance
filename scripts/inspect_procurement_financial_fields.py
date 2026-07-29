"""
Inspect procurement financial fields for ETL-114C.1.

This script is read-only. It identifies:

1. Monetary-looking columns in procurement.award_transaction.
2. PostgreSQL data types and numeric precision.
3. Monetary-looking keys in raw_award_transaction.raw_record.
4. Example raw and normalized values for one load batch.
5. Candidate award and agency fields needed for reconciliation.

Run:

    python -m scripts.inspect_procurement_financial_fields \
        --load-batch-id 4
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Any

from etl.common.db import get_connection


MONEY_TERMS = (
    "obligation",
    "amount",
    "value",
    "outlay",
    "subsidy",
    "cost",
    "price",
    "dollar",
)

IDENTIFIER_TERMS = (
    "award",
    "piid",
    "agency",
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect raw and normalized procurement financial fields "
            "for one load batch."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Procurement load batch ID to inspect.",
    )

    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Number of sample records to display.",
    )

    return parser.parse_args()


def is_candidate_name(
    name: str,
    terms: tuple[str, ...],
) -> bool:
    normalized_name = name.lower()

    return any(
        term in normalized_name
        for term in terms
    )


def print_heading(
    title: str,
    character: str = "=",
    width: int = 88,
) -> None:
    print(character * width)
    print(title)
    print(character * width)


def inspect_normalized_columns(cur) -> list[str]:
    cur.execute(
        """
        SELECT
            column_name,
            data_type,
            udt_name,
            numeric_precision,
            numeric_scale,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'procurement'
          AND table_name = 'award_transaction'
        ORDER BY ordinal_position;
        """
    )

    rows = cur.fetchall()

    candidate_columns: list[str] = []

    print_heading(
        "NORMALIZED AWARD_TRANSACTION CANDIDATE FIELDS",
        "-",
    )

    for row in rows:
        (
            column_name,
            data_type,
            udt_name,
            numeric_precision,
            numeric_scale,
            is_nullable,
        ) = row

        if not (
            is_candidate_name(column_name, MONEY_TERMS)
            or is_candidate_name(column_name, IDENTIFIER_TERMS)
        ):
            continue

        candidate_columns.append(column_name)

        precision_text = "—"

        if numeric_precision is not None:
            precision_text = (
                f"{numeric_precision},{numeric_scale}"
            )

        print(
            f"{column_name:<44} "
            f"type={data_type:<22} "
            f"udt={udt_name:<12} "
            f"precision={precision_text:<8} "
            f"nullable={is_nullable}"
        )

    if not candidate_columns:
        print("No candidate normalized fields found.")

    print()

    return candidate_columns


def inspect_raw_json_keys(
    cur,
    load_batch_id: int,
) -> list[tuple[str, int]]:
    cur.execute(
        """
        SELECT
            key,
            COUNT(*) AS occurrence_count
        FROM procurement.raw_award_transaction AS raw
        CROSS JOIN LATERAL jsonb_object_keys(
            raw.raw_record
        ) AS keys(key)
        WHERE raw.load_batch_id = %s
        GROUP BY key
        ORDER BY key;
        """,
        (load_batch_id,),
    )

    rows = cur.fetchall()

    candidates = [
        (str(key), int(count))
        for key, count in rows
        if (
            is_candidate_name(str(key), MONEY_TERMS)
            or is_candidate_name(str(key), IDENTIFIER_TERMS)
        )
    ]

    print_heading(
        "RAW JSON CANDIDATE FIELDS",
        "-",
    )

    for key, count in candidates:
        print(
            f"{key:<58} "
            f"occurrences={count}"
        )

    if not candidates:
        print("No candidate raw JSON fields found.")

    print()

    return candidates


def inspect_raw_value_profiles(
    cur,
    load_batch_id: int,
    raw_candidates: list[tuple[str, int]],
) -> None:
    financial_keys = [
        key
        for key, _ in raw_candidates
        if is_candidate_name(key, MONEY_TERMS)
    ]

    print_heading(
        "RAW FINANCIAL VALUE PROFILES",
        "-",
    )

    if not financial_keys:
        print("No raw financial keys available to profile.")
        print()
        return

    for key in financial_keys:
        cur.execute(
            """
            SELECT raw_record ->> %s AS raw_value
            FROM procurement.raw_award_transaction
            WHERE load_batch_id = %s
              AND raw_record ? %s;
            """,
            (
                key,
                load_batch_id,
                key,
            ),
        )

        values = [
            row[0]
            for row in cur.fetchall()
        ]

        null_or_blank_count = sum(
            value is None
            or str(value).strip() == ""
            for value in values
        )

        nonblank_values = [
            str(value).strip()
            for value in values
            if value is not None
            and str(value).strip() != ""
        ]

        distinct_examples = list(
            dict.fromkeys(nonblank_values)
        )[:5]

        print(key)
        print(f"  Rows present ............ {len(values)}")
        print(f"  Null or blank ........... {null_or_blank_count}")
        print(
            "  Example values .......... "
            f"{distinct_examples or ['—']}"
        )

    print()


def inspect_normalized_samples(
    cur,
    load_batch_id: int,
    candidate_columns: list[str],
    sample_size: int,
) -> None:
    print_heading(
        "NORMALIZED SAMPLE VALUES",
        "-",
    )

    if not candidate_columns:
        print("No normalized candidate columns available.")
        print()
        return

    safe_columns = [
        column
        for column in candidate_columns
        if column.replace("_", "").isalnum()
    ]

    selected_columns = ",\n            ".join(
        f'txn."{column}"'
        for column in safe_columns
    )

    cur.execute(
        f"""
        SELECT
            {selected_columns}
        FROM procurement.award_transaction AS txn
        WHERE txn.load_batch_id = %s
        ORDER BY txn.source_row_number
        LIMIT %s;
        """,
        (
            load_batch_id,
            sample_size,
        ),
    )

    rows = cur.fetchall()
    column_names = [
        description.name
        for description in cur.description
    ]

    for index, row in enumerate(rows, start=1):
        print(f"Sample {index}")

        for column_name, value in zip(
            column_names,
            row,
            strict=True,
        ):
            print(
                f"  {column_name:<42} "
                f"{value!r}"
            )

        print()

    if not rows:
        print("No normalized rows found for the batch.")
        print()


def inspect_raw_samples(
    cur,
    load_batch_id: int,
    raw_candidates: list[tuple[str, int]],
    sample_size: int,
) -> None:
    print_heading(
        "RAW JSON SAMPLE VALUES",
        "-",
    )

    selected_keys = [
        key
        for key, _ in raw_candidates
    ]

    if not selected_keys:
        print("No raw candidate keys available.")
        print()
        return

    cur.execute(
        """
        SELECT
            source_row_number,
            raw_record
        FROM procurement.raw_award_transaction
        WHERE load_batch_id = %s
        ORDER BY source_row_number
        LIMIT %s;
        """,
        (
            load_batch_id,
            sample_size,
        ),
    )

    rows = cur.fetchall()

    for sample_number, (
        source_row_number,
        raw_record,
    ) in enumerate(rows, start=1):
        print(
            f"Sample {sample_number} "
            f"(source row {source_row_number})"
        )

        for key in selected_keys:
            if key in raw_record:
                print(
                    f"  {key:<54} "
                    f"{raw_record.get(key)!r}"
                )

        print()

    if not rows:
        print("No raw rows found for the batch.")
        print()


def inspect_record_counts(
    cur,
    load_batch_id: int,
) -> None:
    print_heading(
        "BATCH COUNTS",
        "-",
    )

    cur.execute(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM procurement.raw_award_transaction
                WHERE load_batch_id = %s
            ) AS raw_count,
            (
                SELECT COUNT(*)
                FROM procurement.award_transaction
                WHERE load_batch_id = %s
            ) AS normalized_count,
            (
                SELECT COUNT(DISTINCT award_id)
                FROM procurement.award_transaction
                WHERE load_batch_id = %s
            ) AS award_count;
        """,
        (
            load_batch_id,
            load_batch_id,
            load_batch_id,
        ),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Batch-count query returned no result."
        )

    print(f"Raw observations ............... {int(row[0])}")
    print(f"Normalized transactions ........ {int(row[1])}")
    print(f"Distinct awards ................ {int(row[2])}")
    print()


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            print_heading(
                "ETL-114C.1 — PROCUREMENT FINANCIAL-FIELD INSPECTION"
            )
            print(f"Load batch ID: {args.load_batch_id}")
            print()

            inspect_record_counts(
                cur,
                args.load_batch_id,
            )

            normalized_candidates = (
                inspect_normalized_columns(cur)
            )

            raw_candidates = inspect_raw_json_keys(
                cur,
                args.load_batch_id,
            )

            inspect_raw_value_profiles(
                cur,
                args.load_batch_id,
                raw_candidates,
            )

            inspect_normalized_samples(
                cur,
                args.load_batch_id,
                normalized_candidates,
                args.sample_size,
            )

            inspect_raw_samples(
                cur,
                args.load_batch_id,
                raw_candidates,
                args.sample_size,
            )

    except Exception as exc:
        print()
        print("Financial-field inspection failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()