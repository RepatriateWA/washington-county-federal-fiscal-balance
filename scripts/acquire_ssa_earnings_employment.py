from __future__ import annotations

import csv
import hashlib
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "ssa"
    / "earnings_employment"
    / "source"
)

VALIDATION_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "ssa"
    / "earnings_employment"
    / "validation"
)

MANIFEST_PATH = VALIDATION_DIR / "acquisition_manifest.csv"

START_YEAR = 2015
END_YEAR = 2023

BASE_URL = (
    "https://www.ssa.gov/policy/docs/statcomps/"
    "eedata_sc/{year}/eedata_sc{yy}.xlsx"
)

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/154.0 Safari/537.36"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def validate_xlsx(path: Path) -> None:
    with path.open("rb") as handle:
        signature = handle.read(4)

    if signature != b"PK\x03\x04":
        raise RuntimeError(
            f"{path.name}: invalid XLSX/ZIP signature "
            f"{signature!r}"
        )

    if not zipfile.is_zipfile(path):
        raise RuntimeError(
            f"{path.name}: file is not a valid ZIP/XLSX archive"
        )

    with zipfile.ZipFile(path, "r") as archive:
        names = set(archive.namelist())

        required = {
            "[Content_Types].xml",
            "xl/workbook.xml",
        }

        missing = required - names

        if missing:
            raise RuntimeError(
                f"{path.name}: missing XLSX members: "
                f"{sorted(missing)}"
            )


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet,"
                "application/octet-stream;q=0.9,*/*;q=0.8"
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=120,
        ) as response:
            data = response.read()

    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"HTTP {exc.code} downloading {url}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"URL error downloading {url}: {exc.reason}"
        ) from exc

    if not data:
        raise RuntimeError(
            f"Empty response downloading {url}"
        )

    destination.write_bytes(data)


def main() -> int:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    if MANIFEST_PATH.exists():
        raise RuntimeError(
            "Refusing silent overwrite of existing manifest:\n"
            f"{MANIFEST_PATH}"
        )

    rows: list[dict[str, str | int]] = []

    print("=" * 100)
    print(
        "SSA EARNINGS AND EMPLOYMENT DATA ACQUISITION "
        "- ETL-172E-3"
    )
    print("=" * 100)
    print()
    print(f"Years: {START_YEAR}-{END_YEAR}")
    print(f"Destination: {SOURCE_DIR.relative_to(REPO_ROOT)}")
    print()

    for year in range(START_YEAR, END_YEAR + 1):
        yy = str(year)[-2:]

        url = BASE_URL.format(
            year=year,
            yy=yy,
        )

        filename = f"eedata_sc{yy}.xlsx"
        destination = SOURCE_DIR / filename

        print("-" * 100)
        print(f"{year}: {url}")

        if destination.exists():
            raise RuntimeError(
                "Refusing silent overwrite of existing source file:\n"
                f"{destination}"
            )

        status = "ERROR"
        error_message = ""

        try:
            download(url, destination)
            validate_xlsx(destination)

            size_bytes = destination.stat().st_size
            sha256 = sha256_file(destination)

            status = "ACQUIRED"

            print(f"  file   : {filename}")
            print(f"  bytes  : {size_bytes:,}")
            print(f"  sha256 : {sha256}")
            print("  status : ACQUIRED")

        except Exception as exc:
            error_message = str(exc)

            if destination.exists():
                destination.unlink()

            size_bytes = 0
            sha256 = ""

            print(f"  status : ERROR")
            print(f"  error  : {error_message}")

        rows.append(
            {
                "data_year": year,
                "source_family": (
                    "SSA Earnings and Employment Data for "
                    "Workers Covered Under Social Security "
                    "and Medicare, by State and County"
                ),
                "source_url": url,
                "local_path": str(
                    destination.relative_to(REPO_ROOT)
                ),
                "format": "xlsx",
                "bytes": size_bytes,
                "sha256": sha256,
                "retrieved_utc": (
                    datetime.now(timezone.utc)
                    .isoformat(timespec="seconds")
                ),
                "oasdi_target_table": "Table 1",
                "hi_target_table": "Table 4",
                "known_source_limitation": (
                    "2015 HI state-level methodological flaw "
                    "documented by SSA"
                    if year == 2015
                    else ""
                ),
                "status": status,
                "error": error_message,
            }
        )

    fieldnames = [
        "data_year",
        "source_family",
        "source_url",
        "local_path",
        "format",
        "bytes",
        "sha256",
        "retrieved_utc",
        "oasdi_target_table",
        "hi_target_table",
        "known_source_limitation",
        "status",
        "error",
    ]

    with MANIFEST_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)

    acquired = sum(
        row["status"] == "ACQUIRED"
        for row in rows
    )

    errors = len(rows) - acquired

    print()
    print("=" * 100)
    print("ACQUISITION SUMMARY")
    print("=" * 100)
    print(f"Expected years : {len(rows)}")
    print(f"Acquired       : {acquired}")
    print(f"Errors         : {errors}")
    print(
        "Manifest       : "
        f"{MANIFEST_PATH.relative_to(REPO_ROOT)}"
    )

    if errors:
        print()
        print("ETL-172E-3 RESULT: FAIL")
        return 1

    print()
    print("ETL-172E-3 RESULT: PASS")
    print()
    print(
        "PASS certifies source acquisition and XLSX integrity only."
    )
    print(
        "PASS does NOT certify table semantics, Washington values, "
        "allocation shares, Rockefeller replication, or ledger use."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())