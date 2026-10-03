"""
ETL-174B-5Y-2
Acquire official HUD Voucher Management System (VMS) quarterly workbooks,
CY2022-CY2024.

PURPOSE
-------
Preserve immutable official-source VMS workbooks for subsequent read-only
profiling and reconciliation against USAspending Assistance Listing 14.871.

THIS SCRIPT DOES NOT:
    * parse VMS economic values,
    * classify HCV expenditures,
    * allocate expenditures to counties,
    * reconcile against USAspending,
    * write to PostgreSQL,
    * make any ledger or accounting-policy decision.

SOURCE
------
HUD Housing Voucher Program Support Division (PSD):
https://www.hud.gov/helping-americans/public-indian-housing-program-support-division

ETL checkpoint:
    ETL-174B-5Y-2
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Repository paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

RAW_ROOT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "hud"
    / "vms"
    / "quarterly"
)

MANIFEST_ROOT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "hud"
    / "vms"
    / "manifests"
)

SOURCE_PAGE = (
    "https://www.hud.gov/helping-americans/"
    "public-indian-housing-program-support-division"
)


# ---------------------------------------------------------------------------
# Official HUD files
# ---------------------------------------------------------------------------

FILES = [
    # CY2022
    (
        2022,
        1,
        "VMSJAN-MAR2022.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "VMSJAN-MAR2022.xlsx",
    ),
    (
        2022,
        2,
        "VMSAPR-JUN2022.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "VMSAPR-JUN2022.xlsx",
    ),
    (
        2022,
        3,
        "VMSJUL-SEP2022.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "VMSJUL-SEP%202022.xlsx",
    ),
    (
        2022,
        4,
        "Oct-Dec2022VMS.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "Oct-Dec2022VMS.xlsx",
    ),

    # CY2023
    (
        2023,
        1,
        "VMSJan-Mar2023.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "VMSJan-Mar2023.xlsx",
    ),
    (
        2023,
        2,
        "VMSAPR-JUN2023.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "VMSAPR-JUN%202023.xlsx",
    ),
    (
        2023,
        3,
        "VMSJul-Sep2023.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "VMSJul-Sep2023.xlsx",
    ),
    (
        2023,
        4,
        "VMSOct-Dec2023.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "VMSOct-Dec2023.xlsx",
    ),

    # CY2024
    (
        2024,
        1,
        "JAN-MAR_2024_VMS.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "JAN-MAR%202024%20VMS.xlsx",
    ),
    (
        2024,
        2,
        "VMSApr-Jun2024.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/images/"
        "VMSApr-Jun2024.xlsx",
    ),
    (
        2024,
        3,
        "VMSJul-Sep2024.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "VMSJul-Sep2024.xlsx",
    ),
    (
        2024,
        4,
        "VMSOct-Dec2024.xlsx",
        "https://www.hud.gov/sites/dfiles/PIH/documents/"
        "VMSOct-Dec2024.xlsx",
    ),
]


USER_AGENT = (
    "washington-county-federal-fiscal-balance/"
    "ETL-174B-5Y-2 "
    "(research acquisition; official HUD public data)"
)


@dataclass
class ManifestRow:
    calendar_year: int
    quarter: int
    source_page: str
    source_url: str
    local_path: str
    retrieval_utc: str
    http_status: int
    content_type: str
    content_length_header: str
    byte_count: int
    sha256: str
    disposition: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def is_probably_xlsx(data: bytes) -> bool:
    """
    Modern .xlsx files are ZIP containers and therefore normally begin PK.
    This guards against saving an HTML error page with an .xlsx extension.
    """
    return len(data) >= 4 and data[:2] == b"PK"


def download_file(
    year: int,
    quarter: int,
    filename: str,
    url: str,
) -> ManifestRow:

    year_dir = RAW_ROOT / f"CY{year}"
    year_dir.mkdir(parents=True, exist_ok=True)

    destination = year_dir / filename

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet,application/octet-stream,*/*"
            ),
        },
    )

    retrieval_utc = datetime.now(timezone.utc).isoformat()

    print(
        f"CY{year} Q{quarter}: {filename}",
        flush=True,
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            content_length = response.headers.get("Content-Length", "")
            data = response.read()

    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"HTTP {exc.code} acquiring {url}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Network error acquiring {url}: {exc}"
        ) from exc

    if status != 200:
        raise RuntimeError(
            f"Unexpected HTTP status {status}: {url}"
        )

    if not data:
        raise RuntimeError(
            f"HUD returned an empty response: {url}"
        )

    if not is_probably_xlsx(data):
        preview = data[:200].decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            "Response does not appear to be an XLSX ZIP container.\n"
            f"URL: {url}\n"
            f"Content-Type: {content_type}\n"
            f"First bytes: {preview!r}"
        )

    incoming_sha256 = sha256_bytes(data)

    if destination.exists():
        existing_sha256 = sha256_file(destination)

        if existing_sha256 != incoming_sha256:
            raise RuntimeError(
                "\nIMMUTABILITY FAILURE\n"
                "HUD returned bytes different from the already-preserved "
                "raw artifact.\n\n"
                f"File: {destination}\n"
                f"Existing SHA-256: {existing_sha256}\n"
                f"Incoming SHA-256: {incoming_sha256}\n\n"
                "The existing raw file has NOT been overwritten."
            )

        disposition = "EXISTING_IDENTICAL"

    else:
        destination.write_bytes(data)
        disposition = "DOWNLOADED"

    relative_path = destination.relative_to(REPO_ROOT)

    print(
        f"    {disposition:20s} "
        f"{len(data):>12,} bytes  "
        f"{incoming_sha256}",
        flush=True,
    )

    return ManifestRow(
        calendar_year=year,
        quarter=quarter,
        source_page=SOURCE_PAGE,
        source_url=url,
        local_path=str(relative_path),
        retrieval_utc=retrieval_utc,
        http_status=status,
        content_type=content_type,
        content_length_header=content_length,
        byte_count=len(data),
        sha256=incoming_sha256,
        disposition=disposition,
    )


def write_manifests(rows: list[ManifestRow]) -> tuple[Path, Path]:
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    csv_path = (
        MANIFEST_ROOT
        / f"hud_vms_2022_2024_manifest_{timestamp}.csv"
    )

    json_path = (
        MANIFEST_ROOT
        / f"hud_vms_2022_2024_manifest_{timestamp}.json"
    )

    fieldnames = list(asdict(rows[0]).keys())

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()

        for row in rows:
            writer.writerow(asdict(row))

    json_payload = {
        "etl_checkpoint": "ETL-174B-5Y-2",
        "purpose": (
            "Official HUD VMS quarterly workbook acquisition; "
            "CY2022-CY2024"
        ),
        "source_page": SOURCE_PAGE,
        "generated_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "artifact_count": len(rows),
        "artifacts": [
            asdict(row)
            for row in rows
        ],
    }

    json_path.write_text(
        json.dumps(
            json_payload,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return csv_path, json_path


def main() -> int:
    print("=" * 88)
    print("HUD VMS OFFICIAL WORKBOOK ACQUISITION")
    print("ETL-174B-5Y-2")
    print("=" * 88)
    print()
    print(f"Source : {SOURCE_PAGE}")
    print(f"Target : {RAW_ROOT}")
    print()
    print(
        "Scope  : CY2022-CY2024 quarterly VMS workbooks"
    )
    print(
        "Writes : raw files + provenance manifests ONLY"
    )
    print(
        "DB     : NO DATABASE WRITES"
    )
    print()

    rows: list[ManifestRow] = []

    try:
        for year, quarter, filename, url in FILES:
            row = download_file(
                year=year,
                quarter=quarter,
                filename=filename,
                url=url,
            )
            rows.append(row)

    except Exception as exc:
        print()
        print("=" * 88)
        print("ACQUISITION FAILED")
        print("=" * 88)
        print(str(exc))
        return 1

    csv_manifest, json_manifest = write_manifests(rows)

    expected = len(FILES)
    acquired = len(rows)

    distinct_hashes = len(
        {row.sha256 for row in rows}
    )

    total_bytes = sum(
        row.byte_count for row in rows
    )

    print()
    print("=" * 88)
    print("ACQUISITION CONTROL")
    print("=" * 88)
    print(
        f"Expected artifacts       : {expected}"
    )
    print(
        f"Validated artifacts      : {acquired}"
    )
    print(
        f"Distinct SHA-256 hashes  : {distinct_hashes}"
    )
    print(
        f"Total preserved bytes    : {total_bytes:,}"
    )
    print()
    print(
        f"CSV manifest  : "
        f"{csv_manifest.relative_to(REPO_ROOT)}"
    )
    print(
        f"JSON manifest : "
        f"{json_manifest.relative_to(REPO_ROOT)}"
    )
    print()

    if acquired != expected:
        print("RESULT: FAIL")
        return 1

    if distinct_hashes != expected:
        print(
            "RESULT: REVIEW REQUIRED "
            "(duplicate workbook hashes detected)"
        )
        return 2

    print("RESULT: PASS")
    print()
    print(
        "No VMS values were interpreted."
    )
    print(
        "No USAspending reconciliation was performed."
    )
    print(
        "No accounting or ledger decision was made."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())