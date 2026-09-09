"""
Acquire USAspending Assistance Prime Transaction archives for Washington.

Scope
-----
- Washington State by place of performance
- Federal fiscal year by ACTION DATE
- Assistance prime-award types only
- FFY2015-2019 and FFY2024 by default
- Immutable raw ZIP preservation
- SHA-256 checksum
- Request/response/agency provenance JSON
- ZIP integrity and Assistance Prime Transaction schema validation

Run
---
    python -m scripts.acquire_usaspending_assistance

Optional:
    python -m scripts.acquire_usaspending_assistance --years 2024
    python -m scripts.acquire_usaspending_assistance --years 2015 2016
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import time
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests


API_URL = "https://api.usaspending.gov/api/v2/bulk_download/awards/"
AGENCY_LIST_URL = (
    "https://api.usaspending.gov/api/v2/"
    "bulk_download/list_agencies/"
)

DEFAULT_ROOT = Path("data/raw/usaspending/assistance")

DEFAULT_YEARS = [2015, 2016, 2017, 2018, 2019, 2024]

ASSISTANCE_PRIME_AWARD_TYPES = [
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
    "-1",
]

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

POLL_SECONDS = 30
MAX_POLL_SECONDS = 6 * 60 * 60
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire USAspending Assistance Prime Transactions for "
            "Washington State by place of performance."
        )
    )

    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=DEFAULT_YEARS,
        help=(
            "Federal fiscal years to acquire. "
            f"Default: {' '.join(map(str, DEFAULT_YEARS))}"
        ),
    )

    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Raw assistance root. Default: {DEFAULT_ROOT}",
    )

    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=POLL_SECONDS,
        help=f"Status polling interval. Default: {POLL_SECONDS} seconds",
    )

    return parser.parse_args()


def fiscal_year_date_range(fiscal_year: int) -> tuple[str, str]:
    start = date(fiscal_year - 1, 10, 1)
    end = date(fiscal_year, 9, 30)
    return start.isoformat(), end.isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(
            lambda: file.read(DOWNLOAD_CHUNK_SIZE),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite provenance artifact: {path}"
        )

    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def fetch_award_agencies(
    session: requests.Session,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    response = session.post(
        AGENCY_LIST_URL,
        json={"type": "award_agencies"},
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            "USAspending award-agency discovery failed: "
            f"HTTP {response.status_code}\n"
            f"{response.text[:5000]}"
        )

    result = response.json()

    agencies_root = result.get("agencies", {})

    source_agencies = (
        agencies_root.get("cfo_agencies", [])
        + agencies_root.get("other_agencies", [])
    )

    if not source_agencies:
        raise RuntimeError(
            "USAspending returned no top-tier award agencies."
        )

    names = sorted(
        {
            str(agency["name"]).strip()
            for agency in source_agencies
            if str(agency.get("name", "")).strip()
        }
    )

    if not names:
        raise RuntimeError(
            "USAspending award-agency response contained "
            "no usable agency names."
        )

    bulk_agencies = [
        {
            "name": name,
            "tier": "toptier",
            "type": "awarding",
        }
        for name in names
    ]

    return bulk_agencies, result


def build_request(
    fiscal_year: int,
    agencies: list[dict[str, str]],
) -> dict[str, Any]:
    start_date, end_date = fiscal_year_date_range(fiscal_year)

    return {
        "filters": {
            "agencies": agencies,
            "prime_award_types": ASSISTANCE_PRIME_AWARD_TYPES,
            "date_type": "action_date",
            "date_range": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "place_of_performance_locations": [
                {
                    "country": "USA",
                    "state": "WA",
                }
            ],
        },
        "file_format": "csv",
    }


def request_download(
    session: requests.Session,
    fiscal_year: int,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    print(f"Submitting USAspending request for FFY{fiscal_year}...")

    response = session.post(
        API_URL,
        json=request_payload,
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            f"USAspending request failed for FFY{fiscal_year}: "
            f"HTTP {response.status_code}\n"
            f"{response.text[:5000]}"
        )

    result = response.json()

    required = {
        "status_url",
        "file_name",
        "file_url",
    }

    missing = required - set(result)

    if missing:
        raise RuntimeError(
            f"USAspending response for FFY{fiscal_year} "
            f"is missing required field(s): {sorted(missing)}\n"
            f"{json.dumps(result, indent=2)}"
        )

    return result


def poll_download(
    session: requests.Session,
    *,
    fiscal_year: int,
    status_url: str,
    poll_seconds: int,
) -> dict[str, Any]:
    """
    Poll a USAspending bulk-download job until it reaches a terminal state.

    Important:
    - "ready" is NOT treated as complete.
    - USAspending may report "ready" while the generated ZIP is still being
      prepared for download.
    - Only "finished" is treated as successful completion.
    - "failed" and "error" are terminal failures.
    """

    print(f"Waiting for FFY{fiscal_year} bulk download...")

    started = time.monotonic()
    last_status = None

    while True:
        response = session.get(
            status_url,
            timeout=120,
        )

        if not response.ok:
            raise RuntimeError(
                f"Status request failed for FFY{fiscal_year}: "
                f"HTTP {response.status_code}\n"
                f"{response.text[:5000]}"
            )

        status_result = response.json()

        status = str(
            status_result.get("status", "")
        ).strip().lower()

        if status != last_status:
            print(
                f"FFY{fiscal_year} download status: "
                f"{status or '<blank>'}"
            )

            # Print useful progress metadata when USAspending provides it.
            total_rows = status_result.get("total_rows")
            total_size = status_result.get("total_size")
            seconds_elapsed = status_result.get("seconds_elapsed")
            message = status_result.get("message")

            if total_rows is not None:
                print(
                    f"FFY{fiscal_year} total rows: "
                    f"{total_rows:,}"
                    if isinstance(total_rows, int)
                    else f"FFY{fiscal_year} total rows: {total_rows}"
                )

            if total_size is not None:
                print(
                    f"FFY{fiscal_year} total size: "
                    f"{total_size}"
                )

            if seconds_elapsed is not None:
                print(
                    f"FFY{fiscal_year} seconds elapsed: "
                    f"{seconds_elapsed}"
                )

            if message:
                print(
                    f"FFY{fiscal_year} message: "
                    f"{message}"
                )

            last_status = status

        # USAspending's generated-download host may still return a waiting
        # page while status == "ready". Do not attempt the ZIP download until
        # the status endpoint reports "finished".
        if status == "finished":
            return status_result

        if status in {
            "failed",
            "error",
        }:
            raise RuntimeError(
                f"USAspending download generation failed "
                f"for FFY{fiscal_year}:\n"
                f"{json.dumps(status_result, indent=2)}"
            )

        elapsed = time.monotonic() - started

        if elapsed > MAX_POLL_SECONDS:
            raise TimeoutError(
                f"Timed out waiting for FFY{fiscal_year} "
                f"after {elapsed / 3600:.1f} hours.\n"
                f"Last status: {status or '<blank>'}\n"
                f"Last response:\n"
                f"{json.dumps(status_result, indent=2)}"
            )

        time.sleep(poll_seconds)


def download_file(
    session: requests.Session,
    *,
    file_url: str,
    target: Path,
) -> None:
    if target.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing raw artifact: {target}"
        )

    partial = target.with_suffix(
        target.suffix + ".partial"
    )

    if partial.exists():
        raise FileExistsError(
            f"Partial download already exists; inspect before retrying: "
            f"{partial}"
        )

    print(f"Downloading: {file_url}")
    print(f"Target:      {target}")

    response = session.get(
        file_url,
        stream=True,
        timeout=(60, 600),
    )

    response.raise_for_status()

    with partial.open("wb") as file:
        for chunk in response.iter_content(
            chunk_size=DOWNLOAD_CHUNK_SIZE
        ):
            if chunk:
                file.write(chunk)

    partial.replace(target)


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


def validate_archive(
    path: Path,
    *,
    fiscal_year: int,
) -> dict[str, Any]:
    print(f"Validating ZIP: {path.name}")

    with zipfile.ZipFile(path, "r") as zf:
        bad_member = zf.testzip()

        if bad_member is not None:
            raise RuntimeError(
                f"CRC failure in FFY{fiscal_year} ZIP: "
                f"{bad_member}"
            )

        members = [
            info
            for info in zf.infolist()
            if not info.is_dir()
        ]

        csv_members = [
            info
            for info in members
            if info.filename.lower().endswith(".csv")
        ]

        assistance_prime_members: list[str] = []

        for info in csv_members:
            with zf.open(info, "r") as member_file:
                first_line = member_file.readline()

            header = set(
                csv_header(first_line)
            )

            if TRANSACTION_SCHEMA_MARKERS.issubset(header):
                assistance_prime_members.append(
                    info.filename
                )

        if not assistance_prime_members:
            raise RuntimeError(
                f"FFY{fiscal_year} archive contains no CSV "
                "matching the WCFFBP Assistance Prime "
                "Transaction schema."
            )

        return {
            "zip_member_count": len(members),
            "csv_member_count": len(csv_members),
            "assistance_prime_transaction_members": (
                assistance_prime_members
            ),
        }


def write_sha256_file(
    *,
    directory: Path,
    filename: str,
    digest: str,
) -> None:
    checksum_path = directory / "SHA256.txt"
    entry = f"{digest}  {filename}\n"

    if checksum_path.exists():
        existing = checksum_path.read_text(
            encoding="utf-8"
        )

        if filename in existing:
            raise FileExistsError(
                f"Checksum entry already exists for {filename}"
            )

        with checksum_path.open(
            "a",
            encoding="utf-8",
            newline="\n",
        ) as file:
            file.write(entry)

    else:
        checksum_path.write_text(
            entry,
            encoding="utf-8",
            newline="\n",
        )


def acquire_year(
    session: requests.Session,
    *,
    fiscal_year: int,
    root: Path,
    poll_seconds: int,
    agencies: list[dict[str, str]],
    agency_response: dict[str, Any],
) -> None:
    fy_directory = root / f"FY{fiscal_year}"

    fy_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing_zips = sorted(
        fy_directory.glob("*.zip")
    )

    if existing_zips:
        raise FileExistsError(
            f"FFY{fiscal_year} already contains raw ZIP(s): "
            + ", ".join(
                path.name
                for path in existing_zips
            )
        )

    agency_path = (
        fy_directory
        / f"usaspending_award_agencies_FY{fiscal_year}.json"
    )

    write_json(
        agency_path,
        {
            "retrieved_utc": utc_now_iso(),
            "request": {
                "type": "award_agencies",
            },
            "response": agency_response,
            "derived_bulk_filter": agencies,
            "derived_bulk_filter_count": len(agencies),
        },
    )

    request_payload = build_request(
        fiscal_year,
        agencies,
    )

    request_path = (
        fy_directory
        / f"usaspending_assistance_request_FY{fiscal_year}.json"
    )

    write_json(
        request_path,
        {
            "created_utc": utc_now_iso(),
            "endpoint": API_URL,
            "payload": request_payload,
        },
    )

    initial_response = request_download(
        session,
        fiscal_year,
        request_payload,
    )

    response_path = (
        fy_directory
        / f"usaspending_assistance_response_FY{fiscal_year}.json"
    )

    write_json(
        response_path,
        {
            "received_utc": utc_now_iso(),
            "response": initial_response,
        },
    )

    status_result = poll_download(
        session,
        fiscal_year=fiscal_year,
        status_url=initial_response["status_url"],
        poll_seconds=poll_seconds,
    )

    status_path = (
        fy_directory
        / f"usaspending_assistance_status_FY{fiscal_year}.json"
    )

    write_json(
        status_path,
        {
            "received_utc": utc_now_iso(),
            "response": status_result,
        },
    )

    file_url = (
        status_result.get("file_url")
        or initial_response["file_url"]
    )

    api_filename = (
        status_result.get("file_name")
        or initial_response["file_name"]
    )

    target = (
        fy_directory
        / str(api_filename)
    )

    download_file(
        session,
        file_url=file_url,
        target=target,
    )

    archive_sha256 = sha256_file(
        target
    )

    validation = validate_archive(
        target,
        fiscal_year=fiscal_year,
    )

    write_sha256_file(
        directory=fy_directory,
        filename=target.name,
        digest=archive_sha256,
    )

    start_date, end_date = fiscal_year_date_range(
        fiscal_year
    )

    acquisition_manifest = {
        "manifest_created_utc": utc_now_iso(),
        "fiscal_year": fiscal_year,
        "geographic_rule": (
            "prime award transaction place of performance = Washington"
        ),
        "state_code": "WA",
        "state_fips": "53",
        "date_type": "action_date",
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "prime_award_types": (
            ASSISTANCE_PRIME_AWARD_TYPES
        ),
        "agency_filter_count": len(agencies),
        "agency_filter": agencies,
        "archive_filename": target.name,
        "archive_sha256": archive_sha256,
        "api_request": request_payload,
        "api_initial_response": initial_response,
        "api_final_status": status_result,
        "validation": validation,
    }

    manifest_path = (
        fy_directory
        / f"usaspending_assistance_manifest_FY{fiscal_year}.json"
    )

    write_json(
        manifest_path,
        acquisition_manifest,
    )

    print()
    print("=" * 78)
    print(
        f"FFY{fiscal_year} ACQUISITION COMPLETE"
    )
    print("=" * 78)
    print(f"Archive ..... {target}")
    print(f"SHA-256 ..... {archive_sha256}")
    print(
        "Prime CSV ... "
        + ", ".join(
            validation[
                "assistance_prime_transaction_members"
            ]
        )
    )
    print("=" * 78)


def main() -> int:
    args = parse_arguments()

    years = sorted(
        set(args.years)
    )

    invalid = [
        year
        for year in years
        if year < 2000 or year > 2200
    ]

    if invalid:
        raise ValueError(
            f"Invalid fiscal year(s): {invalid}"
        )

    if args.poll_seconds < 1:
        raise ValueError(
            "--poll-seconds must be at least 1."
        )

    print("=" * 78)
    print(
        "USASPENDING WASHINGTON ASSISTANCE ACQUISITION"
    )
    print("=" * 78)
    print(
        "Fiscal years ........ "
        + ", ".join(map(str, years))
    )
    print(
        "Geography ........... Washington place of performance"
    )
    print(
        "Date basis .......... action_date"
    )
    print(
        "Award scope ......... assistance prime transactions"
    )
    print(
        "Subawards ........... not requested"
    )
    print("=" * 78)

    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": (
                    "WCFFBP/1.0 "
                    "(Washington County Federal Fiscal Balance)"
                ),
                "Accept": "application/json",
            }
        )

        print(
            "Discovering current USAspending award agencies..."
        )

        agencies, agency_response = fetch_award_agencies(
            session
        )

        print(
            "Top-tier award agencies ... "
            f"{len(agencies):,}"
        )

        for fiscal_year in years:
            acquire_year(
                session,
                fiscal_year=fiscal_year,
                root=args.root,
                poll_seconds=args.poll_seconds,
                agencies=agencies,
                agency_response=agency_response,
            )

    print()
    print("=" * 78)
    print("ALL REQUESTED ACQUISITIONS COMPLETE")
    print("=" * 78)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
