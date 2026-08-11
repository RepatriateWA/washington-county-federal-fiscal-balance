"""
Inventory USAspending assistance ZIP archives for the Washington County
Federal Fiscal Balance project.

Purpose
-------
Create a reproducible manifest of downloaded USAspending archives before
loading anything into PostgreSQL.

The script:
- Recursively finds .zip files under a supplied root directory.
- Records archive metadata and SHA-256 hashes.
- Inspects ZIP members without permanently extracting them.
- Identifies CSV members.
- Reads CSV headers and a small sample to infer schemas.
- Records row counts by streaming through CSVs (optional; enabled by default).
- Detects duplicate archives by SHA-256.
- Detects archives with identical member-name inventories.
- Writes CSV manifests plus a human-readable text report.

No database writes are performed.

Usage
-----
From the repository root:

    python -m scripts.inventory_usaspending_archives

Or specify a different root:

    python -m scripts.inventory_usaspending_archives ^
      --root data\\raw\\usaspending\\assistance

Use --skip-row-counts for a faster structural-only scan:

    python -m scripts.inventory_usaspending_archives --skip-row-counts
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = Path("data/raw/usaspending/assistance")
DEFAULT_OUTPUT = Path("data/processed/usaspending/inventory")


@dataclass
class ArchiveRecord:
    archive_path: str
    archive_name: str
    fiscal_year_folder: str | None
    archive_size_bytes: int
    archive_sha256: str
    member_count: int
    csv_member_count: int
    total_uncompressed_bytes: int
    bad_zip: bool
    error: str | None


@dataclass
class MemberRecord:
    archive_path: str
    archive_sha256: str
    fiscal_year_folder: str | None
    member_name: str
    member_size_bytes: int
    compressed_size_bytes: int
    compression_ratio: float | None
    is_csv: bool
    detected_encoding: str | None
    column_count: int | None
    columns_json: str | None
    row_count_excluding_header: int | None
    sample_rows_read: int | None
    error: str | None


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def infer_fiscal_year(path: Path) -> str | None:
    for part in reversed(path.parts):
        upper = part.upper()
        if upper.startswith("FY") and len(upper) >= 6:
            suffix = upper[2:]
            if suffix.isdigit() and len(suffix) == 4:
                return upper
    return None


def decode_header(raw: bytes) -> tuple[str, str]:
    """
    USAspending CSV exports are commonly UTF-8/UTF-8-SIG.
    Fall back conservatively if necessary.
    """
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    last_error = None
    for encoding in encodings:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise UnicodeDecodeError(
        "unknown", raw, 0, len(raw),
        f"Unable to decode bytes; last error: {last_error}"
    )


def inspect_csv_member(
    zf: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    count_rows: bool,
    sample_limit: int = 5,
) -> tuple[str | None, list[str] | None, int | None, int | None, str | None]:
    """
    Inspect one CSV member without extracting it to disk.

    Returns:
        encoding, columns, row_count, sample_rows_read, error
    """
    try:
        with zf.open(info, "r") as raw:
            # TextIOWrapper with utf-8-sig handles BOM safely.
            # Retry by reopening if another encoding is required.
            prefix = raw.read(65536)

        _, encoding = decode_header(prefix)

        with zf.open(info, "r") as raw:
            text = io.TextIOWrapper(raw, encoding=encoding, newline="", errors="strict")
            reader = csv.reader(text)

            try:
                header = next(reader)
            except StopIteration:
                return encoding, [], 0, 0, None

            columns = [c.strip() for c in header]

            row_count = 0
            sample_rows = 0
            for _row in reader:
                row_count += 1
                if sample_rows < sample_limit:
                    sample_rows += 1
                if not count_rows and sample_rows >= sample_limit:
                    break

            if not count_rows:
                row_count = None

            return encoding, columns, row_count, sample_rows, None

    except Exception as exc:
        return None, None, None, None, f"{type(exc).__name__}: {exc}"


def write_csv(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def canonical_member_signature(member_names: list[str]) -> str:
    normalized = sorted(name.replace("\\", "/").lower() for name in member_names)
    joined = "\n".join(normalized).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory USAspending ZIP archives before ETL."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Root directory containing USAspending ZIPs (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output directory for manifests (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--skip-row-counts",
        action="store_true",
        help="Skip full CSV row counts for a faster structural scan.",
    )
    args = parser.parse_args()

    root = args.root
    output = args.output
    count_rows = not args.skip_row_counts

    if not root.exists():
        print(f"ERROR: USAspending root does not exist: {root}", file=sys.stderr)
        return 2

    zip_paths = sorted(root.rglob("*.zip"))

    if not zip_paths:
        print(f"ERROR: No ZIP files found under: {root}", file=sys.stderr)
        return 3

    output.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("USASPENDING ARCHIVE INVENTORY")
    print("=" * 72)
    print(f"Root:       {root.resolve()}")
    print(f"ZIP files:  {len(zip_paths)}")
    print(f"Row counts: {'ENABLED' if count_rows else 'SKIPPED'}")
    print()

    archive_records: list[ArchiveRecord] = []
    member_records: list[MemberRecord] = []

    archive_to_members: dict[str, list[str]] = {}
    hash_to_archives: defaultdict[str, list[str]] = defaultdict(list)
    signature_to_archives: defaultdict[str, list[str]] = defaultdict(list)

    for index, archive_path in enumerate(zip_paths, start=1):
        rel = archive_path.relative_to(root)
        print(f"[{index}/{len(zip_paths)}] {rel}")

        archive_hash = sha256_file(archive_path)
        hash_to_archives[archive_hash].append(str(rel))
        fy = infer_fiscal_year(archive_path)

        member_names: list[str] = []
        archive_error = None
        bad_zip = False
        member_count = 0
        csv_member_count = 0
        total_uncompressed = 0

        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                bad_member = zf.testzip()
                if bad_member:
                    bad_zip = True
                    archive_error = f"CRC failure in member: {bad_member}"

                infos = [i for i in zf.infolist() if not i.is_dir()]
                member_count = len(infos)
                total_uncompressed = sum(i.file_size for i in infos)

                for info in infos:
                    member_names.append(info.filename)
                    is_csv = info.filename.lower().endswith(".csv")
                    if is_csv:
                        csv_member_count += 1

                    ratio = None
                    if info.file_size:
                        ratio = round(info.compress_size / info.file_size, 6)

                    encoding = None
                    columns = None
                    row_count = None
                    sample_rows = None
                    member_error = None

                    if is_csv:
                        (
                            encoding,
                            columns,
                            row_count,
                            sample_rows,
                            member_error,
                        ) = inspect_csv_member(
                            zf=zf,
                            info=info,
                            count_rows=count_rows,
                        )

                    member_records.append(
                        MemberRecord(
                            archive_path=str(rel),
                            archive_sha256=archive_hash,
                            fiscal_year_folder=fy,
                            member_name=info.filename,
                            member_size_bytes=info.file_size,
                            compressed_size_bytes=info.compress_size,
                            compression_ratio=ratio,
                            is_csv=is_csv,
                            detected_encoding=encoding,
                            column_count=len(columns) if columns is not None else None,
                            columns_json=json.dumps(columns, ensure_ascii=False)
                            if columns is not None
                            else None,
                            row_count_excluding_header=row_count,
                            sample_rows_read=sample_rows,
                            error=member_error,
                        )
                    )

        except zipfile.BadZipFile as exc:
            bad_zip = True
            archive_error = f"BadZipFile: {exc}"
        except Exception as exc:
            archive_error = f"{type(exc).__name__}: {exc}"

        archive_to_members[str(rel)] = member_names
        signature = canonical_member_signature(member_names)
        signature_to_archives[signature].append(str(rel))

        archive_records.append(
            ArchiveRecord(
                archive_path=str(rel),
                archive_name=archive_path.name,
                fiscal_year_folder=fy,
                archive_size_bytes=archive_path.stat().st_size,
                archive_sha256=archive_hash,
                member_count=member_count,
                csv_member_count=csv_member_count,
                total_uncompressed_bytes=total_uncompressed,
                bad_zip=bad_zip,
                error=archive_error,
            )
        )

    archive_rows = [asdict(r) for r in archive_records]
    member_rows = [asdict(r) for r in member_records]

    duplicate_hash_groups = [
        archives for archives in hash_to_archives.values() if len(archives) > 1
    ]
    duplicate_signature_groups = [
        archives for archives in signature_to_archives.values() if len(archives) > 1
    ]

    # Schema frequency across CSV members.
    schema_counter: Counter[str] = Counter()
    for row in member_rows:
        if row["is_csv"] and row["columns_json"]:
            schema_counter[row["columns_json"]] += 1

    schema_rows = []
    for schema_id, (columns_json, count) in enumerate(
        schema_counter.most_common(), start=1
    ):
        columns = json.loads(columns_json)
        schema_rows.append(
            {
                "schema_id": schema_id,
                "member_count": count,
                "column_count": len(columns),
                "columns_json": columns_json,
            }
        )

    write_csv(
        output / "archives.csv",
        archive_rows,
        fieldnames=list(asdict(archive_records[0]).keys()),
    )

    if member_rows:
        write_csv(
            output / "members.csv",
            member_rows,
            fieldnames=list(asdict(member_records[0]).keys()),
        )

    if schema_rows:
        write_csv(
            output / "schemas.csv",
            schema_rows,
            fieldnames=["schema_id", "member_count", "column_count", "columns_json"],
        )

    duplicate_rows = []
    for group_type, groups in (
        ("identical_sha256", duplicate_hash_groups),
        ("identical_member_inventory", duplicate_signature_groups),
    ):
        for group_number, archives in enumerate(groups, start=1):
            for archive in archives:
                duplicate_rows.append(
                    {
                        "group_type": group_type,
                        "group_number": group_number,
                        "archive_path": archive,
                    }
                )

    write_csv(
        output / "duplicate_groups.csv",
        duplicate_rows,
        fieldnames=["group_type", "group_number", "archive_path"],
    )

    report_path = output / "inventory_report.txt"
    generated = datetime.now(timezone.utc).isoformat()

    total_csvs = sum(r.csv_member_count for r in archive_records)
    bad_archives = sum(1 for r in archive_records if r.bad_zip or r.error)

    by_fy = Counter(r.fiscal_year_folder or "UNKNOWN" for r in archive_records)

    with report_path.open("w", encoding="utf-8") as report:
        report.write("USASPENDING ARCHIVE INVENTORY REPORT\n")
        report.write("=" * 72 + "\n\n")
        report.write(f"Generated UTC: {generated}\n")
        report.write(f"Root: {root.resolve()}\n")
        report.write(f"Archives: {len(archive_records)}\n")
        report.write(f"CSV members: {total_csvs}\n")
        report.write(f"Bad/error archives: {bad_archives}\n")
        report.write(f"Distinct CSV schemas: {len(schema_rows)}\n")
        report.write(
            f"Full row counts: {'YES' if count_rows else 'NO'}\n\n"
        )

        report.write("ARCHIVES BY FISCAL-YEAR FOLDER\n")
        report.write("-" * 72 + "\n")
        for fy, count in sorted(by_fy.items()):
            report.write(f"{fy}: {count}\n")

        report.write("\nEXACT DUPLICATE ARCHIVES (SHA-256)\n")
        report.write("-" * 72 + "\n")
        if not duplicate_hash_groups:
            report.write("None detected.\n")
        else:
            for i, group in enumerate(duplicate_hash_groups, start=1):
                report.write(f"Group {i}:\n")
                for archive in group:
                    report.write(f"  - {archive}\n")

        report.write("\nIDENTICAL MEMBER-INVENTORY GROUPS\n")
        report.write("-" * 72 + "\n")
        if not duplicate_signature_groups:
            report.write("None detected.\n")
        else:
            for i, group in enumerate(duplicate_signature_groups, start=1):
                report.write(f"Group {i}:\n")
                for archive in group:
                    report.write(f"  - {archive}\n")

        report.write("\nCSV SCHEMAS\n")
        report.write("-" * 72 + "\n")
        if not schema_rows:
            report.write("No CSV schemas detected.\n")
        else:
            for row in schema_rows:
                columns = json.loads(row["columns_json"])
                report.write(
                    f"Schema {row['schema_id']}: "
                    f"{row['member_count']} member(s), "
                    f"{row['column_count']} columns\n"
                )
                for column in columns:
                    report.write(f"  - {column}\n")
                report.write("\n")

        report.write("\nARCHIVE ERRORS\n")
        report.write("-" * 72 + "\n")
        errors = [r for r in archive_records if r.error]
        if not errors:
            report.write("None.\n")
        else:
            for r in errors:
                report.write(f"{r.archive_path}: {r.error}\n")

    print()
    print("Inventory complete.")
    print(f"  Archives manifest:  {output / 'archives.csv'}")
    print(f"  Members manifest:   {output / 'members.csv'}")
    print(f"  Schema manifest:    {output / 'schemas.csv'}")
    print(f"  Duplicate groups:   {output / 'duplicate_groups.csv'}")
    print(f"  Text report:        {report_path}")
    print()
    print("No database changes were made.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())