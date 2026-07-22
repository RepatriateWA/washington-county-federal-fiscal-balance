"""
ETL-004A — USAspending Contract Transactions Loader.

Current milestone:
    ETL-004A.1 source validation and load-batch registration.

This version:
    1. Locates the configured USAspending CSV file.
    2. Reads and validates required headers.
    3. Computes the source-file SHA-256 checksum.
    4. Counts source data rows.
    5. Creates a procurement.load_batch record.
    6. Marks the batch COMPLETED after successful validation.
    7. Loads no procurement observations yet.
"""

import csv
import hashlib
from pathlib import Path

from etl.common.batches import (
    complete_load_batch,
    create_load_batch,
    fail_load_batch,
)
from etl.common.db import get_connection


SOURCE_RELATIVE_PATH = Path(
    "data/raw/usaspending/contracts/"
    "Boeing Contract_N0001904C3146_TransactionHistory_1"
)

REQUIRED_HEADERS = {
    "contract_transaction_unique_key",
    "contract_award_unique_key",
}


def get_repository_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parents[2]


def locate_source_file() -> Path:
    """Locate the configured USAspending source file."""
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
    """Read and return the CSV header row."""
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

    return [header.strip() for header in headers]


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


def register_validated_source(
    *,
    source_file: Path,
    file_sha256: str,
    source_record_count: int,
) -> int:
    """Register this validation run in procurement.load_batch."""
    conn = get_connection()
    load_batch_id: int | None = None

    try:
        load_batch_id = create_load_batch(
            conn,
            source_file=str(source_file),
            file_sha256=file_sha256,
            source_record_count=source_record_count,
            notes=(
                "ETL-004A.1 source validation and batch registration only; "
                "no procurement observations loaded."
            ),
        )

        print(f"Created load batch: {load_batch_id}")

        complete_load_batch(
            conn,
            load_batch_id=load_batch_id,
            loaded_record_count=0,
            rejected_record_count=0,
            notes=(
                "USAspending source file validated successfully. "
                "No procurement observations loaded in ETL-004A.1."
            ),
        )

        print("Load batch status: COMPLETED")
        return load_batch_id

    except Exception as exc:
        if load_batch_id is not None:
            try:
                fail_load_batch(
                    conn,
                    load_batch_id=load_batch_id,
                    notes=f"ETL-004A.1 failed: {exc}",
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
    """Run ETL-004A.1 source validation and batch registration."""
    print("=" * 60)
    print("ETL-004A — USAspending Contract Transactions")
    print("=" * 60)

    try:
        source_file = locate_source_file()
        print(f"Source file located:\n  {source_file}")

        headers = read_csv_headers(source_file)
        print(f"Columns detected: {len(headers)}")

        validate_headers(headers)
        print("Required-header validation: PASS")

        file_sha256 = compute_sha256(source_file)
        print(f"SHA-256:\n  {file_sha256}")

        source_record_count = count_source_rows(source_file)
        print(f"Source records detected: {source_record_count:,}")

        load_batch_id = register_validated_source(
            source_file=source_file,
            file_sha256=file_sha256,
            source_record_count=source_record_count,
        )

        print()
        print("ETL-004A.1 completed successfully.")
        print(f"Registered load batch ID: {load_batch_id}")

    except Exception as exc:
        print()
        print("ETL-004A.1 failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()