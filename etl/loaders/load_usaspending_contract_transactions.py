"""
ETL-004A — USAspending Contract Transactions Loader.

Current milestone:
    ETL-004A.2 raw observation import.

This loader:
    1. Locates the configured USAspending CSV file.
    2. Validates the required source headers.
    3. Computes a SHA-256 fingerprint for the source file.
    4. Counts source data rows.
    5. Creates a procurement.load_batch record.
    6. Preserves every CSV row as JSONB in
       procurement.raw_award_transaction.
    7. Computes a deterministic SHA-256 fingerprint for every raw row.
    8. Marks the load batch COMPLETED only after all rows are inserted.

The loader deliberately performs no normalization, interpretation, joins,
county allocation, or fiscal analysis. It preserves source observations.
"""

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


SOURCE_RELATIVE_PATH = Path(
    "data/raw/usaspending/contracts/"
    "Contract_DEAC2701RV14136_TransactionHistory_1.csv"
)

REQUIRED_HEADERS = {
    "contract_transaction_unique_key",
    "contract_award_unique_key",
}

INSERT_PAGE_SIZE = 1_000


def get_repository_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parents[2]


def locate_source_file() -> Path:
    """
    Locate the configured USAspending source file.

    The configured source name currently has no extension, so the loader
    checks both the exact path and the same path with a .csv extension.
    """
    configured_path = get_repository_root() / SOURCE_RELATIVE_PATH

    candidates = (
        configured_path,
        configured_path.with_suffix(".csv"),
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    checked_paths = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(
        "USAspending source file was not found.\n"
        "Checked the following paths:\n"
        f"{checked_paths}"
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
        formatted = "\n".join(f"  - {header}" for header in duplicate_headers)
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
    """Compute and return the SHA-256 checksum of the source file."""
    sha256 = hashlib.sha256()

    with source_file.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def count_source_rows(source_file: Path) -> int:
    """Count CSV data rows, excluding the header row."""
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
    return hashlib.sha256(canonical_record.encode("utf-8")).hexdigest()


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
            raise ValueError("USAspending source file has no header row.")

        reader.fieldnames = [header.strip() for header in reader.fieldnames]

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


def run_raw_import(
    *,
    source_file: Path,
    file_sha256: str,
    source_record_count: int,
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
            source_record_count=source_record_count,
            notes=(
                "ETL-004A.2 raw USAspending contract transaction import."
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
            notes=(
                "ETL-004A.2 completed successfully. "
                f"Preserved {loaded_record_count:,} raw USAspending "
                "contract transaction observations."
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
                print(f"Load batch {load_batch_id} marked FAILED.")
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
    print("=" * 68)
    print("ETL-004A.2 — USAspending Raw Contract Transaction Import")
    print("=" * 68)

    try:
        source_file = locate_source_file()
        print(f"Source file located:\n  {source_file}")

        headers = read_csv_headers(source_file)
        print(f"Columns detected: {len(headers)}")

        validate_headers(headers)
        print("Required-header validation: PASS")

        file_sha256 = compute_sha256(source_file)
        print(f"Source SHA-256:\n  {file_sha256}")

        source_record_count = count_source_rows(source_file)
        print(f"Source records detected: {source_record_count:,}")

        load_batch_id, loaded_record_count = run_raw_import(
            source_file=source_file,
            file_sha256=file_sha256,
            source_record_count=source_record_count,
        )

        print()
        print("ETL-004A.2 completed successfully.")
        print(f"Registered load batch ID: {load_batch_id}")
        print(f"Raw observations preserved: {loaded_record_count:,}")

    except Exception as exc:
        print()
        print("ETL-004A.2 failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()