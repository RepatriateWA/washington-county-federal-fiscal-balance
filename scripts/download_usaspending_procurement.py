from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


API_ROOT = "https://api.usaspending.gov/api/v2"

# USAspending contract award-type codes.
# These represent Contracts, not Contract IDVs.
CONTRACT_AWARD_TYPE_CODES = ["A", "B", "C", "D"]

REPO_ROOT = Path(__file__).resolve().parents[1]


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "WCFFBP-USAspending-Acquisition/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"USAspending HTTP {exc.code} from {url}\n{body}"
        ) from exc


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "WCFFBP-USAspending-Acquisition/1.0",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"USAspending HTTP {exc.code} from {url}\n{body}"
        ) from exc


def download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "WCFFBP-USAspending-Acquisition/1.0",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=600) as response:
        with destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)

                if not chunk:
                    break

                output.write(chunk)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def fiscal_year_dates(fiscal_year: int) -> tuple[str, str]:
    return (
        f"{fiscal_year - 1}-10-01",
        f"{fiscal_year}-09-30",
    )


def build_filters(fiscal_year: int) -> dict[str, Any]:
    start_date, end_date = fiscal_year_dates(fiscal_year)

    return {
        "time_period": [
            {
                "start_date": start_date,
                "end_date": end_date,
            }
        ],
        "award_type_codes": CONTRACT_AWARD_TYPE_CODES,
        "place_of_performance_locations": [
            {
                "country": "USA",
                "state": "WA",
            }
        ],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def normalize_status_url(status_url: str) -> str:
    if status_url.startswith("http://") or status_url.startswith("https://"):
        return status_url

    if status_url.startswith("/"):
        return f"https://api.usaspending.gov{status_url}"

    return f"{API_ROOT.rstrip('/')}/{status_url.lstrip('/')}"


def extract_status_url(response: dict[str, Any]) -> str | None:
    candidates = [
        response.get("status_url"),
        response.get("status_url_with_query"),
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return normalize_status_url(candidate.strip())

    return None


def extract_status_value(response: dict[str, Any]) -> str | None:
    candidates = [
        response.get("status"),
        response.get("download_status"),
        response.get("state"),
    ]

    for candidate in candidates:
        if candidate is not None:
            return str(candidate).strip().lower()

    return None


def extract_file_url(response: dict[str, Any]) -> str | None:
    direct_candidates = [
        response.get("file_url"),
        response.get("download_url"),
        response.get("url"),
    ]

    for candidate in direct_candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    file_object = response.get("file")

    if isinstance(file_object, dict):
        for key in ("url", "file_url", "download_url"):
            candidate = file_object.get(key)

            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

    return None


def choose_archive_name(file_url: str, fiscal_year: int) -> str:
    parsed = urllib.parse.urlparse(file_url)
    candidate = Path(parsed.path).name

    if candidate.lower().endswith(".zip"):
        return candidate

    return f"USAspending_Procurement_FY{fiscal_year}.zip"


def write_zip_inventory(
    zip_path: Path,
    inventory_path: Path,
) -> list[str]:
    inventory_lines: list[str] = []

    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            inventory_lines.append(
                f"{member.filename}\t{member.file_size}"
            )

    inventory_path.write_text(
        "\n".join(inventory_lines) + "\n",
        encoding="utf-8",
    )

    return inventory_lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire Washington USAspending contract prime transactions "
            "with preserved acquisition provenance."
        )
    )

    parser.add_argument(
        "--fiscal-year",
        type=int,
        required=True,
        help="Federal fiscal year to acquire.",
    )

    parser.add_argument(
        "--expected-count",
        type=int,
        default=None,
        help=(
            "Independent expected transaction count. "
            "The script stops if the API count differs."
        ),
    )

    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run the count validation only; do not request a download.",
    )

    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=20,
        help="Seconds between download-status polls. Default: 20.",
    )

    parser.add_argument(
        "--max-polls",
        type=int,
        default=180,
        help="Maximum number of status polls. Default: 180.",
    )

    args = parser.parse_args()

    fiscal_year = args.fiscal_year
    filters = build_filters(fiscal_year)

    target_dir = (
        REPO_ROOT
        / "data"
        / "raw"
        / "usaspending"
        / "procurement"
        / f"FY{fiscal_year}"
    )

    target_dir.mkdir(parents=True, exist_ok=True)

    request_payload = {
        "filters": filters,
        "file_format": "csv",
    }

    print("=" * 88)
    print("WCFFBP - USASPENDING PROCUREMENT ACQUISITION")
    print("=" * 88)
    print()
    print(f"Federal fiscal year .............. FY{fiscal_year}")
    print("Award population ................. Contracts")
    print("Record level ..................... Prime Transactions")
    print("Place of performance ............. Washington")
    print("Recipient-location filter ........ NONE")
    print()

    request_path = target_dir / "acquisition_request.json"

    write_json(
        request_path,
        request_payload,
    )

    print(f"Request provenance written ....... {request_path}")
    print()

    # ==================================================================
    # 1. PREFLIGHT COUNT
    # ==================================================================

    count_url = f"{API_ROOT}/download/count/"

    print("Requesting USAspending preflight count...")

    count_response = post_json(
        count_url,
        request_payload,
    )

    count_response_path = target_dir / "count_response.json"

    write_json(
        count_response_path,
        count_response,
    )

    print()
    print("USAspending count response:")
    print(json.dumps(count_response, indent=2))
    print()

    print(f"Count response preserved ......... {count_response_path}")

    observed_count = count_response.get(
        "calculated_transaction_count"
    )

    if not isinstance(observed_count, int):
        raise RuntimeError(
            "USAspending count response did not contain an integer "
            "'calculated_transaction_count'."
        )

    if count_response.get("transaction_rows_gt_limit") is True:
        raise RuntimeError(
            "USAspending reports that the requested transaction population "
            "exceeds the download limit."
        )

    if args.expected_count is not None:
        if observed_count != args.expected_count:
            raise RuntimeError(
                "USAspending transaction count does not match expected count. "
                f"Expected {args.expected_count:,}; "
                f"observed {observed_count:,}."
            )

        print(
            "Expected-count validation ......... PASS "
            f"({observed_count:,})"
        )

    if args.preflight_only:
        print()
        print("=" * 88)
        print("PREFLIGHT COMPLETE - NO DOWNLOAD REQUESTED")
        print("=" * 88)
        return

    # ==================================================================
    # 2. SUBMIT TRANSACTION DOWNLOAD
    # ==================================================================

    download_url = f"{API_ROOT}/download/transactions/"

    print()
    print("Submitting USAspending transaction download request...")

    download_response = post_json(
        download_url,
        request_payload,
    )

    download_response_path = (
        target_dir / "download_response.json"
    )

    write_json(
        download_response_path,
        download_response,
    )

    print()
    print("USAspending download response:")
    print(json.dumps(download_response, indent=2))
    print()

    print(
        f"Download response preserved ...... "
        f"{download_response_path}"
    )

    status_url = extract_status_url(download_response)

    if status_url is None:
        raise RuntimeError(
            "USAspending download response did not contain a status URL.\n"
            + json.dumps(download_response, indent=2)
        )

    print(f"Status URL ....................... {status_url}")

    # ==================================================================
    # 3. POLL DOWNLOAD STATUS
    # ==================================================================

    completed_statuses = {
        "finished",
        "complete",
        "completed",
        "ready",
        "success",
        "successful",
    }

    failed_statuses = {
        "failed",
        "error",
        "cancelled",
        "canceled",
    }

    final_status: dict[str, Any] | None = None

    print()
    print("Polling USAspending download status...")

    for poll_number in range(1, args.max_polls + 1):
        status_response = get_json(status_url)

        status_path = (
            target_dir
            / f"status_response_{poll_number:03d}.json"
        )

        write_json(
            status_path,
            status_response,
        )

        status_value = extract_status_value(
            status_response
        )

        file_url = extract_file_url(
            status_response
        )

        print(
            f"Poll {poll_number:03d} "
            f"status .................... {status_value}"
        )

        # If USAspending gives us a file URL, the job is usable even if
        # the status label changes in a future API version.
        if status_value in completed_statuses:
            final_status = status_response
            break

        if status_value in failed_statuses:
            raise RuntimeError(
                "USAspending download generation failed.\n"
                + json.dumps(status_response, indent=2)
            )

        if poll_number == args.max_polls:
            raise TimeoutError(
                "USAspending download did not complete within "
                f"{args.max_polls} polls."
            )

        time.sleep(args.poll_seconds)

    if final_status is None:
        raise RuntimeError(
            "USAspending polling ended without a final status response."
        )

    final_status_path = (
        target_dir / "status_response_final.json"
    )

    write_json(
        final_status_path,
        final_status,
    )

    file_url = extract_file_url(
        final_status
    )

    if file_url is None:
        raise RuntimeError(
            "USAspending completed the download job but no file URL "
            "was found in the final status response.\n"
            + json.dumps(final_status, indent=2)
        )

    print()
    print(f"Download URL ..................... {file_url}")

    # ==================================================================
    # 4. DOWNLOAD ORIGINAL ZIP UNTOUCHED
    # ==================================================================

    archive_name = choose_archive_name(
        file_url,
        fiscal_year,
    )

    zip_path = target_dir / archive_name

    if zip_path.exists():
        raise FileExistsError(
            "Refusing to overwrite an existing raw USAspending archive:\n"
            f"  {zip_path}"
        )

    print(
        f"Downloading archive to ........... "
        f"{zip_path}"
    )

    download_file(
        file_url,
        zip_path,
    )

    print("Archive download .................. COMPLETE")

    # ==================================================================
    # 5. SHA-256
    # ==================================================================

    archive_sha256 = sha256_file(
        zip_path
    )

    sha_path = target_dir / "SHA256.txt"

    sha_path.write_text(
        f"{archive_sha256}  {zip_path.name}\n",
        encoding="utf-8",
    )

    print(
        f"Archive SHA-256 ................... "
        f"{archive_sha256}"
    )

    print(
        f"SHA-256 manifest ................. "
        f"{sha_path}"
    )

    # ==================================================================
    # 6. ZIP INVENTORY
    # ==================================================================

    inventory_path = (
        target_dir / "ZIP_INVENTORY.txt"
    )

    inventory_lines = write_zip_inventory(
        zip_path,
        inventory_path,
    )

    print()
    print("Archive contents:")

    for line in inventory_lines:
        print(f"  {line}")

    print()
    print(
        f"ZIP inventory ..................... "
        f"{inventory_path}"
    )

    # ==================================================================
    # 7. ACQUISITION SUMMARY
    # ==================================================================

    summary = {
        "fiscal_year": fiscal_year,
        "expected_transaction_count": args.expected_count,
        "observed_transaction_count": observed_count,
        "archive_name": zip_path.name,
        "archive_sha256": archive_sha256,
        "archive_path": str(zip_path),
        "request_path": str(request_path),
        "count_response_path": str(count_response_path),
        "download_response_path": str(download_response_path),
        "final_status_path": str(final_status_path),
        "zip_inventory_path": str(inventory_path),
        "filters": filters,
    }

    summary_path = (
        target_dir / "acquisition_summary.json"
    )

    write_json(
        summary_path,
        summary,
    )

    print(
        f"Acquisition summary ............... "
        f"{summary_path}"
    )

    print()
    print("=" * 88)
    print("PROCUREMENT ACQUISITION COMPLETE")
    print("=" * 88)


if __name__ == "__main__":
    main()