"""
Load raw USAspending Assistance Prime Transactions into PostgreSQL.

Repository-integrated version:
- Uses etl.common.db.get_connection
- Uses procurement.load_batch for provenance
- Loads immutable rows into assistance.raw_award_transaction
- Accepts a CSV, ZIP archive, or directory tree
- For ZIPs, loads only Assistance Prime Transaction CSV members
- Creates one load batch per CSV payload
- Hashes the exact CSV payload loaded
- Validates source row count against database row count
- Skips an identical source payload already completed

Examples
--------
Load all assistance archives recursively:

    python -m etl.loaders.load_usaspending_assistance_raw ^
      --source data\\raw\\usaspending\\assistance

Load one ZIP:

    python -m etl.loaders.load_usaspending_assistance_raw ^
      --source data\\raw\\usaspending\\assistance\\FY2020\\file.zip

Load one CSV:

    python -m etl.loaders.load_usaspending_assistance_raw ^
      --source path\\to\\Assistance_PrimeTransactions.csv ^
      --fiscal-year 2024
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from psycopg2.extras import execute_values

from etl.common.db import get_connection


DEFAULT_SOURCE = Path("data/raw/usaspending/assistance")

REQUIRED_COLUMNS = {
    "assistance_transaction_unique_key",
    "assistance_award_unique_key",
}

TRANSACTION_SCHEMA_MARKERS = {
    "assistance_transaction_unique_key",
    "assistance_award_unique_key",
    "federal_action_obligation",
    "action_date",
    "action_date_fiscal_year",
    "recipient_state_code",
    "cfda_number",
    "assistance_type_code",
    "disaster_emergency_fund_codes_for_overall_award",
    "outlayed_amount_from_COVID-19_supplementals_for_overall_award",
    "obligated_amount_from_COVID-19_supplementals_for_overall_award",
}

INSERT_PAGE_SIZE = 1_000


@dataclass(frozen=True)
class SourcePayload:
    source_file_label: str
    fiscal_year: int | None
    csv_bytes: bytes
    csv_sha256: str
    archive_sha256: str | None


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load raw USAspending Assistance Prime Transactions "
            "from a CSV, ZIP archive, or directory."
        )
    )

    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=(
            "CSV, ZIP, or directory containing USAspending Assistance data. "
            f"Default: {DEFAULT_SOURCE}"
        ),
    )

    parser.add_argument(
        "--fiscal-year",
        type=int,
        default=None,
        help=(
            "Optional fiscal-year override. Otherwise inferred from an "
            "FY#### path component."
        ),
    )

    return parser.parse_args()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def infer_fiscal_year(path: Path) -> int | None:
    for part in reversed(path.parts):
        upper = part.upper()

        if (
            upper.startswith("FY")
            and len(upper) == 6
            and upper[2:].isdigit()
        ):
            year = int(upper[2:])

            if 1900 <= year <= 2200:
                return year

    return None


def csv_header(csv_bytes: bytes) -> list[str]:
    text = io.TextIOWrapper(
        io.BytesIO(csv_bytes),
        encoding="utf-8-sig",
        newline="",
    )

    try:
        reader = csv.reader(text)

        try:
            return next(reader)
        except StopIteration:
            return []

    finally:
        text.close()


def is_assistance_transaction_csv(csv_bytes: bytes) -> bool:
    return TRANSACTION_SCHEMA_MARKERS.issubset(
        set(csv_header(csv_bytes))
    )


def discover_payloads(
    source: Path,
    *,
    fiscal_year_override: int | None,
) -> list[SourcePayload]:
    if not source.exists():
        raise FileNotFoundError(
            f"Source path not found: {source}"
        )

    if source.is_dir():
        paths = sorted(
            path
            for path in source.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".zip", ".csv"}
        )
    else:
        paths = [source]

    payloads: list[SourcePayload] = []

    for path in paths:
        fiscal_year = (
            fiscal_year_override
            if fiscal_year_override is not None
            else infer_fiscal_year(path)
        )

        suffix = path.suffix.lower()

        if suffix == ".csv":
            csv_bytes = path.read_bytes()

            if not is_assistance_transaction_csv(csv_bytes):
                print(
                    f"Skipping non-prime-transaction CSV: {path}"
                )
                continue

            payloads.append(
                SourcePayload(
                    source_file_label=str(path.resolve()),
                    fiscal_year=fiscal_year,
                    csv_bytes=csv_bytes,
                    csv_sha256=sha256_bytes(csv_bytes),
                    archive_sha256=None,
                )
            )

            continue

        if suffix == ".zip":
            archive_sha = sha256_file(path)

            with zipfile.ZipFile(path, "r") as zf:
                bad_member = zf.testzip()

                if bad_member is not None:
                    raise ValueError(
                        f"CRC failure in ZIP {path}: {bad_member}"
                    )

                matched_members = 0

                for info in zf.infolist():
                    if (
                        info.is_dir()
                        or not info.filename.lower().endswith(".csv")
                    ):
                        continue

                    csv_bytes = zf.read(info)

                    if not is_assistance_transaction_csv(csv_bytes):
                        continue

                    matched_members += 1

                    payloads.append(
                        SourcePayload(
                            source_file_label=(
                                f"{path.resolve()}::{info.filename}"
                            ),
                            fiscal_year=fiscal_year,
                            csv_bytes=csv_bytes,
                            csv_sha256=sha256_bytes(csv_bytes),
                            archive_sha256=archive_sha,
                        )
                    )

                if matched_members == 0:
                    print(
                        "Skipping ZIP with no Assistance Prime "
                        f"Transaction member: {path}"
                    )

    if not payloads:
        raise ValueError(
            "No USAspending Assistance Prime Transaction CSV payloads found."
        )

    return payloads


def clean_required(
    value: str | None,
    *,
    field_name: str,
    source_row_number: int,
) -> str:
    cleaned = (value or "").strip()

    if not cleaned:
        raise ValueError(
            f"Source row {source_row_number:,}: "
            f"{field_name} is blank."
        )

    return cleaned


def read_rows(
    csv_bytes: bytes,
) -> Iterator[tuple[int, str, str, str]]:
    text = io.TextIOWrapper(
        io.BytesIO(csv_bytes),
        encoding="utf-8-sig",
        newline="",
    )

    try:
        reader = csv.DictReader(text)

        fieldnames = set(reader.fieldnames or [])
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

    finally:
        text.close()


def find_completed_batch(
    cur,
    *,
    source_file: str,
    file_sha256: str,
) -> int | None:
    cur.execute(
        """
        SELECT load_batch_id
        FROM procurement.load_batch
        WHERE source_file = %s
          AND file_sha256 = %s
          AND load_status = 'COMPLETED'
        ORDER BY load_batch_id DESC
        LIMIT 1;
        """,
        (
            source_file,
            file_sha256,
        ),
    )

    row = cur.fetchone()

    return int(row[0]) if row else None


def create_load_batch(
    cur,
    *,
    payload: SourcePayload,
) -> int:
    notes = [
        "USAspending Assistance Prime Transactions raw ingestion.",
        "file_sha256 is the SHA-256 of the exact loaded CSV payload.",
    ]

    if payload.archive_sha256 is not None:
        notes.append(
            f"Containing ZIP SHA-256: {payload.archive_sha256}"
        )

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
            payload.source_file_label,
            payload.csv_sha256,
            payload.fiscal_year,
            payload.fiscal_year,
            "\n".join(notes),
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


def load_payload(
    payload: SourcePayload,
) -> int:
    conn = get_connection()
    load_batch_id: int | None = None
    source_record_count = 0

    try:
        with conn.cursor() as cur:
            existing_batch_id = find_completed_batch(
                cur,
                source_file=payload.source_file_label,
                file_sha256=payload.csv_sha256,
            )

            if existing_batch_id is not None:
                print(
                    "Already loaded; skipping "
                    f"batch {existing_batch_id}: "
                    f"{payload.source_file_label}"
                )

                return existing_batch_id

            load_batch_id = create_load_batch(
                cur,
                payload=payload,
            )

            # Preserve provenance before bulk insertion so a subsequent
            # failure remains visible in the audit trail.
            conn.commit()

            print("=" * 72)
            print(
                f"Load batch ID: {load_batch_id}"
            )
            print(
                f"Source: {payload.source_file_label}"
            )
            print(
                f"CSV SHA-256: {payload.csv_sha256}"
            )
            print(
                f"Fiscal year: {payload.fiscal_year}"
            )

            values: list[
                tuple[int, int, str, str, str]
            ] = []

            for (
                source_row_number,
                transaction_key,
                award_key,
                raw_record,
            ) in read_rows(payload.csv_bytes):
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
                        INSERT INTO assistance.raw_award_transaction (
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
                    INSERT INTO assistance.raw_award_transaction (
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

            if loaded_record_count != source_record_count:
                raise ValueError(
                    "Raw load count mismatch: "
                    f"source={source_record_count:,}, "
                    f"database={loaded_record_count:,}."
                )

            cur.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT
                        assistance_transaction_unique_key
                    FROM assistance.raw_award_transaction
                    WHERE load_batch_id = %s
                    GROUP BY
                        assistance_transaction_unique_key
                    HAVING COUNT(*) > 1
                ) AS duplicate_groups;
                """,
                (load_batch_id,),
            )

            duplicate_group_count = int(
                cur.fetchone()[0]
            )

            if duplicate_group_count:
                raise ValueError(
                    f"Raw batch contains "
                    f"{duplicate_group_count:,} duplicate "
                    "transaction-key group(s)."
                )

            mark_batch_completed(
                cur,
                load_batch_id=load_batch_id,
                source_record_count=source_record_count,
                loaded_record_count=loaded_record_count,
            )

        conn.commit()

        print(
            f"Completed batch {load_batch_id}: "
            f"{loaded_record_count:,} rows."
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


def main() -> int:
    args = parse_arguments()

    try:
        payloads = discover_payloads(
            args.source,
            fiscal_year_override=args.fiscal_year,
        )

        print("=" * 72)
        print("ETL-005B — RAW ASSISTANCE SOURCE DISCOVERY")
        print("=" * 72)
        print(
            "Prime-transaction payloads found . "
            f"{len(payloads):,}"
        )

        batch_ids: list[int] = []

        for payload in payloads:
            batch_ids.append(
                load_payload(payload)
            )

        print()
        print("=" * 72)
        print("ETL-005B — RAW ASSISTANCE LOAD COMPLETE")
        print("=" * 72)
        print(
            "Payloads processed ............... "
            f"{len(payloads):,}"
        )
        print(
            "Load batch IDs ................... "
            + ", ".join(
                str(batch_id)
                for batch_id in batch_ids
            )
        )
        print("=" * 72)

        return 0

    except Exception as exc:
        print()
        print("Raw Assistance ingestion failed.")
        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())