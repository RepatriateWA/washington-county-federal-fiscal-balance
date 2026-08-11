"""Load raw USAspending Assistance Prime Transactions into PostgreSQL."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Iterator

from psycopg2.extras import execute_values

from etl.common.db import get_connection


DEFAULT_SOURCE_FILE = Path(
    "data/raw/usaspending/FY2024_WA/original/"
    "Assistance_PrimeTransactions_2026-07-30_H01M19S42_1.csv"
)

REQUIRED_COLUMNS = {
    "assistance_transaction_unique_key",
    "assistance_award_unique_key",
}

INSERT_PAGE_SIZE = 1_000


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load raw USAspending Assistance Prime Transactions "
            "into PostgreSQL."
        )
    )

    parser.add_argument(
        "--source-file",
        type=Path,
        default=DEFAULT_SOURCE_FILE,
        help="Path to the Assistance Prime Transactions CSV.",
    )

    parser.add_argument(
        "--fiscal-year",
        type=int,
        default=2024,
        help="Fiscal year represented by the source extract.",
    )

    return parser.parse_args()


def calculate_sha256(path: Path) -> str:
    """Calculate the SHA-256 hash of a source file."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def clean_required(
    value: str | None,
    *,
    field_name: str,
    source_row_number: int,
) -> str:
    """Validate and trim a required source identifier."""

    cleaned = (value or "").strip()

    if not cleaned:
        raise ValueError(
            f"Source row {source_row_number:,}: "
            f"{field_name} is blank."
        )

    return cleaned


def read_rows(
    source_file: Path,
) -> Iterator[
    tuple[int, str, str, str]
]:
    """
    Yield raw source observations.

    Returns:
        source row number;
        transaction unique key;
        award unique key;
        JSON representation of the complete source row.
    """

    with source_file.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        fieldnames = set(
            reader.fieldnames or []
        )

        missing = REQUIRED_COLUMNS - fieldnames

        if missing:
            raise ValueError(
                "Source CSV is missing required columns: "
                + ", ".join(sorted(missing))
            )

        for source_row_number, raw_record in enumerate(
            reader,
            start=1,
        ):
            transaction_key = clean_required(
                raw_record.get(
                    "assistance_transaction_unique_key"
                ),
                field_name=(
                    "assistance_transaction_unique_key"
                ),
                source_row_number=source_row_number,
            )

            award_key = clean_required(
                raw_record.get(
                    "assistance_award_unique_key"
                ),
                field_name=(
                    "assistance_award_unique_key"
                ),
                source_row_number=source_row_number,
            )

            yield (
                source_row_number,
                transaction_key,
                award_key,
                json.dumps(
                    raw_record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )


def create_load_batch(
    cur,
    *,
    source_file: Path,
    file_sha256: str,
    fiscal_year: int,
) -> int:
    """Register the source ingestion and return its batch ID."""

    cur.execute(
        """
        INSERT INTO procurement.load_batch (
            source_file,
            file_sha256,
            fiscal_year_start,
            fiscal_year_end,
            load_status,
            notes
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            'STARTED',
            %s
        )
        RETURNING load_batch_id;
        """,
        (
            str(source_file.resolve()),
            file_sha256,
            fiscal_year,
            fiscal_year,
            (
                "USAspending Assistance Prime Transactions "
                "raw ingestion."
            ),
        ),
    )

    return int(cur.fetchone()[0])


def mark_batch_completed(
    cur,
    *,
    load_batch_id: int,
    source_record_count: int,
    loaded_record_count: int,
) -> None:
    """Mark a successful raw load batch complete."""

    cur.execute(
        """
        UPDATE procurement.load_batch
        SET
            source_record_count = %s,
            loaded_record_count = %s,
            rejected_record_count = 0,
            load_completed_at = CURRENT_TIMESTAMP,
            load_status = 'COMPLETED'
        WHERE load_batch_id = %s;
        """,
        (
            source_record_count,
            loaded_record_count,
            load_batch_id,
        ),
    )


def mark_batch_failed(
    load_batch_id: int,
    *,
    message: str,
) -> None:
    """
    Mark a failed batch in an independent transaction.

    The primary load transaction may already have been rolled back.
    """

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE procurement.load_batch
                SET
                    load_completed_at = CURRENT_TIMESTAMP,
                    load_status = 'FAILED',
                    notes = CONCAT_WS(
                        E'\n',
                        notes,
                        %s
                    )
                WHERE load_batch_id = %s;
                """,
                (
                    f"Failure: {message}",
                    load_batch_id,
                ),
            )

        conn.commit()

    finally:
        conn.close()


def load_source(
    *,
    source_file: Path,
    fiscal_year: int,
) -> int:
    """Load one Assistance transaction source file."""

    if not source_file.is_file():
        raise FileNotFoundError(
            f"Source file not found: {source_file}"
        )

    file_sha256 = calculate_sha256(
        source_file
    )

    conn = get_connection()
    load_batch_id: int | None = None

    source_record_count = 0

    try:
        with conn.cursor() as cur:
            load_batch_id = create_load_batch(
                cur,
                source_file=source_file,
                file_sha256=file_sha256,
                fiscal_year=fiscal_year,
            )

            # Preserve the batch registration before bulk ingestion so
            # a later failure can be recorded independently.
            conn.commit()

            print(f"Load batch ID: {load_batch_id}")
            print(f"Source SHA-256: {file_sha256}")

            values: list[
                tuple[int, int, str, str, str]
            ] = []

            for (
                source_row_number,
                transaction_key,
                award_key,
                raw_record,
            ) in read_rows(source_file):
                source_record_count += 1

                values.append(
                    (
                        load_batch_id,
                        source_row_number,
                        transaction_key,
                        award_key,
                        raw_record,
                    )
                )

                if len(values) >= INSERT_PAGE_SIZE:
                    execute_values(
                        cur,
                        """
                        INSERT INTO
                            assistance.raw_award_transaction (
                                load_batch_id,
                                source_row_number,
                                assistance_transaction_unique_key,
                                assistance_award_unique_key,
                                raw_record
                            )
                        VALUES %s
                        """,
                        values,
                        template=(
                            "(%s, %s, %s, %s, %s::jsonb)"
                        ),
                        page_size=INSERT_PAGE_SIZE,
                    )

                    values.clear()

            if values:
                execute_values(
                    cur,
                    """
                    INSERT INTO
                        assistance.raw_award_transaction (
                            load_batch_id,
                            source_row_number,
                            assistance_transaction_unique_key,
                            assistance_award_unique_key,
                            raw_record
                        )
                    VALUES %s
                    """,
                    values,
                    template=(
                        "(%s, %s, %s, %s, %s::jsonb)"
                    ),
                    page_size=INSERT_PAGE_SIZE,
                )

            cur.execute(
                """
                SELECT COUNT(*)
                FROM assistance.raw_award_transaction
                WHERE load_batch_id = %s;
                """,
                (load_batch_id,),
            )

            loaded_record_count = int(
                cur.fetchone()[0]
            )

            if (
                loaded_record_count
                != source_record_count
            ):
                raise ValueError(
                    "Raw load count mismatch: "
                    f"source={source_record_count:,}, "
                    f"database={loaded_record_count:,}."
                )

            mark_batch_completed(
                cur,
                load_batch_id=load_batch_id,
                source_record_count=source_record_count,
                loaded_record_count=loaded_record_count,
            )

        conn.commit()

        print()
        print("=" * 72)
        print("ETL-005B — RAW ASSISTANCE LOAD SUMMARY")
        print("=" * 72)
        print(
            "Load batch ID .................. "
            f"{load_batch_id}"
        )
        print(
            "Source rows read ............... "
            f"{source_record_count:,}"
        )
        print(
            "Raw rows inserted .............. "
            f"{loaded_record_count:,}"
        )
        print(
            "Rejected rows .................. 0"
        )
        print(
            "Validation ..................... PASS"
        )
        print("=" * 72)
        print()
        print(
            "Raw Assistance ingestion completed successfully."
        )

        return load_batch_id

    except Exception as exc:
        conn.rollback()

        if load_batch_id is not None:
            mark_batch_failed(
                load_batch_id,
                message=(
                    f"{type(exc).__name__}: {exc}"
                ),
            )

        raise

    finally:
        conn.close()


def main() -> None:
    args = parse_arguments()

    try:
        load_source(
            source_file=args.source_file,
            fiscal_year=args.fiscal_year,
        )

    except Exception as exc:
        print()
        print("Raw Assistance ingestion failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()