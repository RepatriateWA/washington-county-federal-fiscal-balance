"""
ETL-004A — USAspending Contract Transactions Loader.

Current milestone:
    ETL-004A.2 raw observation import.

This loader:
    1. Accepts an explicit USAspending Contracts Prime Transactions CSV.
    2. Validates the required source headers.
    3. Computes a SHA-256 fingerprint for the exact CSV payload.
    4. Counts source data rows.
    5. Checks for an already-completed load of the same CSV SHA-256.
    6. Creates a procurement.load_batch record.
    7. Preserves every CSV row as JSONB in
       procurement.raw_award_transaction.
    8. Computes a deterministic SHA-256 fingerprint for every raw row.
    9. Marks the load batch COMPLETED only after all rows are inserted.

The loader deliberately performs no normalization, interpretation, joins,
county allocation, or fiscal analysis. It preserves source observations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Iterator

from psycopg2.extras import Json, execute_values

from etl.common.batches import (
    complete_load_batch,
    create_load_batch,
    fail_load_batch,
)
from etl.common.db import get_connection


REQUIRED_HEADERS = {
    "contract_transaction_unique_key",
    "contract_award_unique_key",
}

INSERT_PAGE_SIZE = 1_000


def get_repository_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Load one USAspending Contracts Prime Transactions CSV into "
            "the immutable procurement raw layer."
        )
    )

    parser.add_argument(
        "--source-file",
        required=True,
        help=(
            "Path to the USAspending Contracts Prime Transactions CSV. "
            "May be absolute or relative to the repository root."
        ),
    )

    parser.add_argument(
        "--fiscal-year",
        required=True,
        type=int,
        help="Federal fiscal year represented by the source acquisition.",
    )

    parser.add_argument(
        "--containing-zip-sha256",
        default=None,
        help=(
            "Optional SHA-256 of the original containing ZIP archive. "
            "Stored in load-batch notes for acquisition provenance."
        ),
    )

    parser.add_argument(
        "--allow-duplicate",
        action="store_true",
        help=(
            "Permit loading a CSV whose SHA-256 already exists in a "
            "completed procurement load batch. Use only deliberately."
        ),
    )

    return parser.parse_args()


def resolve_source_file(source_argument: str) -> Path:
    """
    Resolve and validate the requested source CSV path.

    Relative paths are interpreted relative to the repository root.
    """
    source_path = Path(source_argument).expanduser()

    if not source_path.is_absolute():
        source_path = get_repository_root() / source_path

    source_path = source_path.resolve()

    if not source_path.is_file():
        raise FileNotFoundError(
            f"USAspending source file was not found:\n  {source_path}"
        )

    if source_path.suffix.lower() != ".csv":
        raise ValueError(
            "USAspending procurement raw loader requires an extracted CSV "
            f"payload, not {source_path.suffix or 'a file without an extension'}.\n"
            f"Source supplied:\n  {source_path}"
        )

    return source_path


def validate_fiscal_year(fiscal_year: int) -> None:
    """Apply a basic sanity check to the supplied federal fiscal year."""
    if fiscal_year < 2000 or fiscal_year > 2100:
        raise ValueError(
            f"Fiscal year is outside the accepted range: {fiscal_year}"
        )


def read_csv_headers(source_file: Path) -> list[str]:
    """Read, clean, and return the CSV header row."""
    with source_file.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.reader(csv_file)

        try:
            headers = next(reader)
        except StopIteration as exc:
            raise ValueError(
                f"USAspending source file is empty: {source_file}"
            ) from exc

    cleaned_headers = [header.strip() for header in headers]

    if any(not header for header in cleaned_headers):
        raise ValueError(
            "USAspending source file contains one or more blank column names."
        )

    duplicate_headers = sorted(
        {
            header
            for header in cleaned_headers
            if cleaned_headers.count(header) > 1
        }
    )

    if duplicate_headers:
        formatted = "\n".join(
            f"  - {header}" for header in duplicate_headers
        )
        raise ValueError(
            "USAspending source file contains duplicate column names:\n"
            f"{formatted}"
        )

    return cleaned_headers


def validate_headers(headers: list[str]) -> None:
    """Confirm that all required USAspending columns are present."""
    available_headers = set(headers)
    missing_headers = sorted(REQUIRED_HEADERS - available_headers)

    if missing_headers:
        formatted_missing = "\n".join(
            f"  - {header}" for header in missing_headers
        )
        raise ValueError(
            "USAspending source-header validation failed.\n"
            "Missing required columns:\n"
            f"{formatted_missing}"
        )


def compute_sha256(source_file: Path) -> str:
    """Compute and return the SHA-256 checksum of the exact CSV payload."""
    sha256 = hashlib.sha256()

    with source_file.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def count_source_rows(source_file: Path) -> int:
    """Count logical CSV data rows, excluding the header row."""
    with source_file.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.reader(csv_file)

        try:
            next(reader)
        except StopIteration:
            return 0

        return sum(1 for _ in reader)


def find_completed_duplicate(file_sha256: str) -> list[tuple]:
    """
    Return completed load batches having the same exact source CSV SHA-256.
    """
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    load_batch_id,
                    source_file,
                    fiscal_year_start,
                    fiscal_year_end,
                    source_record_count,
                    loaded_record_count,
                    load_status
                FROM procurement.load_batch
                WHERE file_sha256 = %s
                  AND load_status IN (
                      'COMPLETED',
                      'COMPLETED_WITH_REJECTIONS'
                  )
                ORDER BY load_batch_id;
                """,
                (file_sha256,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def canonicalize_record(raw_record: dict[str, str | None]) -> str:
    """
    Serialize a raw record deterministically for hashing.

    Sorting keys and using fixed JSON separators ensures the same source row
    produces the same hash whenever this loader is rerun.
    """
    return json.dumps(
        raw_record,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def compute_record_sha256(raw_record: dict[str, str | None]) -> str:
    """Return the deterministic SHA-256 fingerprint of one raw source row."""
    canonical_record = canonicalize_record(raw_record)
    return hashlib.sha256(
        canonical_record.encode("utf-8")
    ).hexdigest()


def iter_raw_records(
    source_file: Path,
) -> Iterator[tuple[int, dict[str, str | None], str]]:
    """
    Yield source row number, raw record, and record SHA-256.

    source_row_number begins at 1 for the first data row beneath the header.
    """
    with source_file.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        if reader.fieldnames is None:
            raise ValueError(
                "USAspending source file has no header row."
            )

        reader.fieldnames = [
            header.strip() for header in reader.fieldnames
        ]

        for source_row_number, raw_record in enumerate(reader, start=1):
            if None in raw_record:
                extra_values = raw_record.get(None)
                raise ValueError(
                    "Malformed CSV row detected at source data row "
                    f"{source_row_number}. Extra values: {extra_values!r}"
                )

            cleaned_record = {
                str(column_name).strip(): value
                for column_name, value in raw_record.items()
            }

            record_sha256 = compute_record_sha256(cleaned_record)

            yield source_row_number, cleaned_record, record_sha256


def insert_raw_records(
    conn,
    *,
    load_batch_id: int,
    source_file: Path,
) -> int:
    """
    Insert all raw USAspending observations for one load batch.

    Inserts remain uncommitted until complete_load_batch() succeeds.
    Therefore, a failure rolls back the raw observations for this batch.
    """
    insert_sql = """
        INSERT INTO procurement.raw_award_transaction (
            load_batch_id,
            source_row_number,
            raw_record,
            record_sha256
        )
        VALUES %s
    """

    rows_to_insert: list[tuple[int, int, Json, str]] = []
    loaded_record_count = 0

    with conn.cursor() as cur:
        for source_row_number, raw_record, record_sha256 in iter_raw_records(
            source_file
        ):
            rows_to_insert.append(
                (
                    load_batch_id,
                    source_row_number,
                    Json(raw_record),
                    record_sha256,
                )
            )

            if len(rows_to_insert) >= INSERT_PAGE_SIZE:
                execute_values(
                    cur,
                    insert_sql,
                    rows_to_insert,
                    page_size=INSERT_PAGE_SIZE,
                )
                loaded_record_count += len(rows_to_insert)
                rows_to_insert.clear()

                print(
                    f"Raw observations inserted: "
                    f"{loaded_record_count:,}",
                    end="\r",
                )

        if rows_to_insert:
            execute_values(
                cur,
                insert_sql,
                rows_to_insert,
                page_size=INSERT_PAGE_SIZE,
            )
            loaded_record_count += len(rows_to_insert)

    if loaded_record_count:
        print(
            f"Raw observations inserted: "
            f"{loaded_record_count:,}"
        )

    return loaded_record_count


def build_batch_notes(
    *,
    containing_zip_sha256: str | None,
) -> str:
    """Build durable raw-ingestion provenance notes."""
    notes = [
        "ETL-004A.2 raw USAspending contract transaction import.",
        "file_sha256 is the SHA-256 of the exact loaded CSV payload.",
    ]

    if containing_zip_sha256:
        notes.append(
            f"Containing ZIP SHA-256: {containing_zip_sha256}"
        )

    return "\n".join(notes)


def build_completion_notes(
    *,
    loaded_record_count: int,
    containing_zip_sha256: str | None,
) -> str:
    """Build durable completion notes while retaining provenance."""
    notes = [
        (
            "ETL-004A.2 completed successfully. "
            f"Preserved {loaded_record_count:,} raw USAspending "
            "contract transaction observations."
        ),
        "file_sha256 is the SHA-256 of the exact loaded CSV payload.",
    ]

    if containing_zip_sha256:
        notes.append(
            f"Containing ZIP SHA-256: {containing_zip_sha256}"
        )

    return "\n".join(notes)


def run_raw_import(
    *,
    source_file: Path,
    file_sha256: str,
    source_record_count: int,
    fiscal_year: int,
    containing_zip_sha256: str | None = None,
) -> tuple[int, int]:
    """
    Create the batch, import raw observations, and complete the batch.

    Returns:
        (load_batch_id, loaded_record_count)
    """
    conn = get_connection()
    load_batch_id: int | None = None

    try:
        load_batch_id = create_load_batch(
            conn,
            source_file=str(source_file),
            file_sha256=file_sha256,
            fiscal_year_start=fiscal_year,
            fiscal_year_end=fiscal_year,
            source_record_count=source_record_count,
            notes=build_batch_notes(
                containing_zip_sha256=containing_zip_sha256
            ),
        )

        print(f"Created load batch: {load_batch_id}")

        loaded_record_count = insert_raw_records(
            conn,
            load_batch_id=load_batch_id,
            source_file=source_file,
        )

        if loaded_record_count != source_record_count:
            raise ValueError(
                "Loaded-record count does not match source-record count. "
                f"Source: {source_record_count:,}; "
                f"loaded: {loaded_record_count:,}."
            )

        complete_load_batch(
            conn,
            load_batch_id=load_batch_id,
            loaded_record_count=loaded_record_count,
            rejected_record_count=0,
            notes=build_completion_notes(
                loaded_record_count=loaded_record_count,
                containing_zip_sha256=containing_zip_sha256,
            ),
        )

        print("Load batch status: COMPLETED")
        return load_batch_id, loaded_record_count

    except Exception as exc:
        conn.rollback()

        if load_batch_id is not None:
            try:
                fail_load_batch(
                    conn,
                    load_batch_id=load_batch_id,
                    notes=f"ETL-004A.2 failed: {exc}",
                )
                print(
                    f"Load batch {load_batch_id} marked FAILED."
                )
            except Exception as batch_exc:
                print(
                    "WARNING: Unable to mark the load batch as FAILED: "
                    f"{batch_exc}"
                )

        raise

    finally:
        conn.close()


def main() -> None:
    """Run ETL-004A.2 raw observation import."""
    args = parse_args()

    print("=" * 68)
    print("ETL-004A.2 — USAspending Raw Contract Transaction Import")
    print("=" * 68)

    try:
        validate_fiscal_year(args.fiscal_year)

        source_file = resolve_source_file(args.source_file)
        print(f"Source file located:\n  {source_file}")

        print(f"Federal fiscal year: {args.fiscal_year}")

        headers = read_csv_headers(source_file)
        print(f"Columns detected: {len(headers)}")

        validate_headers(headers)
        print("Required-header validation: PASS")

        file_sha256 = compute_sha256(source_file)
        print(f"Source CSV SHA-256:\n  {file_sha256}")

        if args.containing_zip_sha256:
            print(
                "Containing ZIP SHA-256:\n  "
                f"{args.containing_zip_sha256}"
            )

        source_record_count = count_source_rows(source_file)
        print(
            f"Source records detected: "
            f"{source_record_count:,}"
        )

        duplicates = find_completed_duplicate(file_sha256)

        if duplicates:
            print()
            print("Existing completed load(s) with identical CSV SHA-256:")
            for (
                load_batch_id,
                existing_source_file,
                fiscal_year_start,
                fiscal_year_end,
                existing_source_count,
                existing_loaded_count,
                load_status,
            ) in duplicates:
                print(
                    f"  Batch {load_batch_id}: "
                    f"FY {fiscal_year_start}-{fiscal_year_end}; "
                    f"source={existing_source_count:,}; "
                    f"loaded={existing_loaded_count:,}; "
                    f"status={load_status}"
                )
                print(
                    f"    {existing_source_file}"
                )

            if not args.allow_duplicate:
                raise ValueError(
                    "This exact CSV payload has already been loaded "
                    "successfully. No new batch was created. "
                    "Use --allow-duplicate only for a deliberate "
                    "duplicate-ingestion test."
                )

            print()
            print(
                "WARNING: --allow-duplicate supplied; "
                "continuing deliberately."
            )

        load_batch_id, loaded_record_count = run_raw_import(
            source_file=source_file,
            file_sha256=file_sha256,
            source_record_count=source_record_count,
            fiscal_year=args.fiscal_year,
            containing_zip_sha256=args.containing_zip_sha256,
        )

        print()
        print("ETL-004A.2 completed successfully.")
        print(f"Registered load batch ID: {load_batch_id}")
        print(
            f"Raw observations preserved: "
            f"{loaded_record_count:,}"
        )

    except Exception as exc:
        print()
        print("ETL-004A.2 failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()