"""
ETL-202B.1
Historical USAspending procurement archive inventory.

READ ONLY:
- No database connections
- No downloads
- No file modifications
- No archive extraction

Searches the repository's data/raw/usaspending tree.
"""

from pathlib import Path
import csv
import hashlib
import zipfile
from datetime import datetime, timezone

ROOT = Path("data/raw/usaspending")
TARGET_YEARS = range(2015, 2020)

EXTENSIONS = {".csv", ".zip", ".xlsx", ".xls"}

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024), b""
        ):
            digest.update(chunk)
    return digest.hexdigest()

def classify(path):
    name = str(path).lower()

    year_matches = [
        year for year in TARGET_YEARS
        if str(year) in name
    ]

    if "transactionhistory" in name.lower():
        category = "CONTRACT_HISTORY"
    elif "primetransactions" in name.lower():
        category = "PRIME_TRANSACTIONS"
    elif "contracts" in name.lower():
        category = "CONTRACTS_OTHER"
    else:
        category = "OTHER"

    return category, year_matches

def inspect_zip(path):
    members = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if not info.is_dir():
                members.append(
                    (
                        info.filename,
                        info.file_size,
                        info.CRC,
                    )
                )
    return members

def main():
    print("=" * 78)
    print("ETL-202B.1 HISTORICAL PROCUREMENT ARCHIVE INVENTORY")
    print("=" * 78)
    print("Generated UTC:",
          datetime.now(timezone.utc).isoformat())
    print("Root:", ROOT.resolve())
    print("Target fiscal years: 2015-2019")
    print("Mode: READ ONLY")
    print()

    if not ROOT.exists():
        print("ERROR: Source directory not found.")
        raise SystemExit(1)

    files = sorted(
        (
            path for path in ROOT.rglob("*")
            if path.is_file()
            and path.suffix.lower() in EXTENSIONS
        ),
        key=lambda p: str(p).lower(),
    )

    print("Total candidate files:", len(files))
    print()

    target_candidates = []
    contract_histories = []
    inventory_errors = []

    for path in files:
        category, years = classify(path)

        if category == "CONTRACT_HISTORY":
            contract_histories.append(path)

        if not years:
            continue

        target_candidates.append(path)

        print("-" * 78)
        print("FILE:", path)
        print("CATEGORY:", category)
        print("YEARS IN PATH:", years)
        print("SIZE_BYTES:", path.stat().st_size)

        try:
            print("SHA256:", sha256_file(path))

            if path.suffix.lower() == ".zip":
                members = inspect_zip(path)
                print("ZIP_MEMBERS:", len(members))

                for member, size, crc in members:
                    print(
                        "  MEMBER:",
                        member,
                        "SIZE:",
                        size,
                        "CRC:",
                        crc,
                    )

        except Exception as exc:
            inventory_errors.append((str(path), str(exc)))
            print("INSPECTION_ERROR:", exc)

    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print("All candidate files:", len(files))
    print("Files with target years in path:",
          len(target_candidates))
    print("Contract-history files:",
          len(contract_histories))
    print("Inspection errors:",
          len(inventory_errors))

    print()
    print("TARGET-YEAR FILE COUNTS")

    for year in TARGET_YEARS:
        matches = [
            path for path in target_candidates
            if year in classify(path)[1]
        ]
        print(f"FY{year}: {len(matches)}")

    print()
    print("IMPORTANT:")
    print(
        "Filename-year matches are discovery hints, "
        "not proof of fiscal-year coverage."
    )
    print(
        "Files without target years in their paths "
        "may still contain historical transactions."
    )

    if inventory_errors:
        raise SystemExit(2)

    print()
    print("ETL-202B.1 INVENTORY COMPLETED")

if __name__ == "__main__":
    main()
