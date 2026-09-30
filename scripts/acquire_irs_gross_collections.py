"""
ETL-171A — Acquire IRS Gross Collections by Type of Tax and State
================================================================

Purpose
-------
Acquire and preserve the official IRS Data Book Table 1-5 spreadsheets:

    Gross collections, by type of tax and state and fiscal year

for Federal Fiscal Years 2015 through 2024.

Source landing page
-------------------
https://www.irs.gov/statistics/soi-tax-stats-gross-collections-by-type-of-tax-and-state-irs-data-book-table-1-5

Methodological rules
--------------------
* Download only from the official IRS source page / IRS-hosted files.
* Preserve source bytes unchanged.
* Do not interpret spreadsheet contents.
* Do not write to PostgreSQL.
* Do not overwrite an existing source file silently.
* Record source URL, retrieval timestamp, byte count, and SHA-256.
* Preserve the IRS fiscal-year label exactly.

Expected source formats
-----------------------
2015-2018 : XLS
2019-2024 : XLSX

Output
------
data/raw/irs/gross_collections/source/
data/raw/irs/gross_collections/validation/acquisition_manifest.csv
"""

from __future__ import annotations

import csv
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


START_YEAR = 2015
END_YEAR = 2024

LANDING_URL = (
    "https://www.irs.gov/statistics/"
    "soi-tax-stats-gross-collections-by-type-of-tax-and-state-"
    "irs-data-book-table-1-5"
)

SOURCE_DIR = Path(
    "data/raw/irs/gross_collections/source"
)

VALIDATION_DIR = Path(
    "data/raw/irs/gross_collections/validation"
)

MANIFEST_PATH = VALIDATION_DIR / "acquisition_manifest.csv"

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; WCFFBP-Research/1.0; "
    "+https://github.com/)"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def fetch_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )

    with urlopen(request, timeout=120) as response:
        final_url = response.geturl()

        parsed = urlparse(final_url)

        if not (
            parsed.netloc.lower().endswith("irs.gov")
            or parsed.netloc.lower().endswith("eitc.irs.gov")
        ):
            raise RuntimeError(
                f"Refusing non-IRS download destination: {final_url}"
            )

        return response.read()


def fetch_text(url: str) -> str:
    data = fetch_bytes(url)

    return data.decode(
        "utf-8",
        errors="replace",
    )


def discover_year_links(html: str) -> dict[int, str]:
    """
    Discover 2015-2024 spreadsheet links from the official IRS landing page.

    The page may use relative or absolute href values. We search anchor tags
    whose visible text contains the target year and XLS/XLSX.
    """

    anchor_pattern = re.compile(
        r"""
        <a
        [^>]*?
        href=["'](?P<href>[^"']+)["']
        [^>]*?>
        (?P<label>.*?)
        </a>
        """,
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    tag_pattern = re.compile(r"<[^>]+>")

    discovered: dict[int, str] = {}

    for match in anchor_pattern.finditer(html):
        href = match.group("href")
        raw_label = match.group("label")
        label = tag_pattern.sub(" ", raw_label)
        label = re.sub(r"\s+", " ", label).strip()

        for year in range(START_YEAR, END_YEAR + 1):
            if str(year) not in label:
                continue

            label_upper = label.upper()

            if "XLS" not in label_upper:
                continue

            resolved = urljoin(
                LANDING_URL,
                href,
            )

            discovered[year] = resolved

    return discovered


def expected_extension(year: int) -> str:
    if 2015 <= year <= 2018:
        return ".xls"

    return ".xlsx"


def output_filename(year: int) -> str:
    extension = expected_extension(year)

    return (
        f"irs_data_book_{year}_"
        f"table_1_5_gross_collections_by_type_and_state"
        f"{extension}"
    )


def validate_file_signature(
    *,
    year: int,
    data: bytes,
) -> None:
    """
    Perform only a coarse container-format check.

    XLS legacy files normally begin with the OLE Compound File signature:
        D0 CF 11 E0 A1 B1 1A E1

    XLSX files are ZIP containers and normally begin:
        PK

    This is not semantic spreadsheet validation.
    """

    extension = expected_extension(year)

    if extension == ".xls":
        ole_signature = bytes.fromhex(
            "D0CF11E0A1B11AE1"
        )

        if not data.startswith(ole_signature):
            raise RuntimeError(
                f"FY{year}: downloaded content does not have "
                f"the expected XLS/OLE signature."
            )

    elif extension == ".xlsx":
        if not data.startswith(b"PK"):
            raise RuntimeError(
                f"FY{year}: downloaded content does not have "
                f"the expected XLSX/ZIP signature."
            )


def write_source_file(
    *,
    path: Path,
    data: bytes,
) -> str:
    """
    Write a source file without silently overwriting evidence.

    If the file already exists:
      * identical SHA-256 -> preserve existing file and return EXISTING_IDENTICAL
      * different SHA-256 -> abort
    """

    new_sha256 = sha256_bytes(data)

    if path.exists():
        existing_sha256 = sha256_file(path)

        if existing_sha256 == new_sha256:
            return "EXISTING_IDENTICAL"

        raise RuntimeError(
            "\n".join(
                [
                    f"Refusing to overwrite existing source: {path}",
                    f"Existing SHA-256: {existing_sha256}",
                    f"Remote SHA-256  : {new_sha256}",
                ]
            )
        )

    path.write_bytes(data)

    written_sha256 = sha256_file(path)

    if written_sha256 != new_sha256:
        raise RuntimeError(
            f"Post-write SHA-256 mismatch for {path}"
        )

    return "DOWNLOADED"


def write_manifest(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "fiscal_year",
        "table_id",
        "source_title",
        "landing_page_url",
        "source_file_url",
        "local_path",
        "file_format",
        "byte_count",
        "sha256",
        "retrieved_utc",
        "acquisition_status",
    ]

    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = MANIFEST_PATH.with_suffix(".csv.tmp")

    with temp_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    temp_path.replace(MANIFEST_PATH)


def main() -> int:
    print("=" * 88)
    print(
        "ETL-171A — IRS GROSS COLLECTIONS SOURCE ACQUISITION"
    )
    print("=" * 88)
    print(f"Landing page : {LANDING_URL}")
    print(
        f"Fiscal years : {START_YEAR}-{END_YEAR}"
    )
    print(f"Source dir   : {SOURCE_DIR}")
    print(f"Manifest     : {MANIFEST_PATH}")
    print("Database writes: NONE")
    print()

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Retrieving official IRS landing page...")

    html = fetch_text(LANDING_URL)

    links = discover_year_links(html)

    expected_years = set(
        range(START_YEAR, END_YEAR + 1)
    )

    discovered_years = set(links)

    missing_years = sorted(
        expected_years - discovered_years
    )

    if missing_years:
        raise RuntimeError(
            "IRS landing-page discovery failed. "
            f"Missing fiscal years: {missing_years}"
        )

    print(
        f"Discovered {len(links)} required annual source links."
    )
    print()

    manifest_rows: list[dict[str, str]] = []

    retrieval_time = datetime.now(
        timezone.utc
    ).isoformat()

    for year in range(
        START_YEAR,
        END_YEAR + 1,
    ):
        source_url = links[year]

        filename = output_filename(year)

        destination = SOURCE_DIR / filename

        print(f"FY{year}")
        print(f"  URL  : {source_url}")
        print(f"  FILE : {destination}")

        data = fetch_bytes(source_url)

        validate_file_signature(
            year=year,
            data=data,
        )

        status = write_source_file(
            path=destination,
            data=data,
        )

        digest = sha256_bytes(data)

        print(
            f"  BYTES: {len(data):,}"
        )
        print(
            f"  SHA  : {digest}"
        )
        print(
            f"  STATUS: {status}"
        )
        print()

        manifest_rows.append(
            {
                "fiscal_year": str(year),
                "table_id": "IRS_DATA_BOOK_TABLE_1_5",
                "source_title": (
                    "Gross collections, by type of tax "
                    "and state and fiscal year"
                ),
                "landing_page_url": LANDING_URL,
                "source_file_url": source_url,
                "local_path": destination.as_posix(),
                "file_format": (
                    expected_extension(year)
                    .lstrip(".")
                    .upper()
                ),
                "byte_count": str(len(data)),
                "sha256": digest,
                "retrieved_utc": retrieval_time,
                "acquisition_status": status,
            }
        )

    write_manifest(manifest_rows)

    print("=" * 88)
    print("ETL-171A ACQUISITION COMPLETE")
    print("=" * 88)
    print(
        f"Annual files preserved : "
        f"{len(manifest_rows)}"
    )
    print(
        f"Fiscal-year coverage   : "
        f"{START_YEAR}-{END_YEAR}"
    )
    print(
        f"Manifest               : "
        f"{MANIFEST_PATH}"
    )
    print("Database writes        : NONE")
    print("Spreadsheet parsing    : NONE")
    print("Accounting changes     : NONE")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("ETL-171A FAILED")
        print("=" * 88)
        print(str(exc))
        raise