"""
ETL-202B.2 - USAspending procurement bulk acquisition.

Default: offline dry run.
--submit: submit request, poll, download ZIP and checksum.
No PostgreSQL access. Never overwrites an existing ZIP.
"""

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = "https://api.usaspending.gov/api/v2/bulk_download/awards/"

CONTRACT_CODES = [
    "A", "B", "C", "D",
    "IDV_A", "IDV_B", "IDV_B_A", "IDV_B_B",
    "IDV_B_C", "IDV_C", "IDV_D", "IDV_E",
]

def timestamp():
    return datetime.now(timezone.utc).isoformat()

def request_json(url, payload=None, attempts=4):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "WCFFBP-ETL-202B.2",
                },
                method="POST" if data is not None else "GET",
            )
            with urllib.request.urlopen(req, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read(1500).decode("utf-8", "replace")
            if exc.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(
                    f"HTTP {exc.code}: {detail}"
                ) from exc
            print(f"Retryable HTTP {exc.code}: {detail[:250]}")
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"Network attempt {attempt} failed: {exc}")

        if attempt < attempts:
            time.sleep(min(5 * (2 ** (attempt - 1)), 40))

    raise RuntimeError("API request failed after retries")

def write_json(path, obj):
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

def download_zip(url, destination):
    if destination.exists():
        raise FileExistsError(
            f"Refusing to overwrite: {destination}"
        )

    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists():
        raise FileExistsError(
            f"Partial download exists: {temporary}"
        )

    digest = hashlib.sha256()
    total = 0

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "WCFFBP-ETL-202B.2"}
        )
        with urllib.request.urlopen(req, timeout=180) as response:
            with temporary.open("xb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)

        import zipfile
        with zipfile.ZipFile(temporary) as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                raise RuntimeError(f"ZIP CRC failure: {bad_member}")

        temporary.rename(destination)
    except Exception:
        print(f"Download incomplete; inspect: {temporary}")
        raise

    return total, digest.hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fiscal-year", type=int, default=2019)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--max-polls", type=int, default=120)
    args = parser.parse_args()

    fy = args.fiscal_year
    if not 2015 <= fy <= 2019:
        parser.error("Pilot supports FY2015-FY2019")

    if args.poll_seconds < 1 or args.max_polls < 1:
        parser.error("Polling parameters must be positive")

    request_body = {
        "filters": {
            "prime_award_types": CONTRACT_CODES,
            "date_type": "action_date",
            "date_range": {
                "start_date": f"{fy-1}-10-01",
                "end_date": f"{fy}-09-30",
            },
            "place_of_performance_locations": [
                {"country": "USA", "state": "WA"}
            ],
        },
        "file_format": "csv",
    }

    root = Path(
        f"data/raw/usaspending/procurement/FY{fy}/api_bulk"
    )
    root.mkdir(parents=True, exist_ok=True)

    manifest_path = root / "request_manifest.json"

    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(
            encoding="utf-8"
        ))
        if existing.get("request_body") != request_body:
            raise RuntimeError(
                "Existing manifest differs; refusing replacement"
            )
    else:
        write_json(manifest_path, {
            "endpoint": ENDPOINT,
            "method": "POST",
            "request_body": request_body,
            "purpose": "Historical Washington procurement acquisition",
            "methodology_status": "PENDING_FILTER_PARITY_REVIEW",
        })

    print("=" * 72)
    print("ETL-202B.2 - USAspending Procurement Bulk Acquisition")
    print("=" * 72)
    print("UTC:", timestamp())
    print("FY:", fy)
    print("MODE:", "SUBMIT" if args.submit else "OFFLINE DRY RUN")
    print("MANIFEST:", manifest_path)
    print(json.dumps(request_body, indent=2))

    if not args.submit:
        print("DRY RUN PASS - no network request made")
        return

    print("Submitting request...")
    result = request_json(ENDPOINT, request_body)

    run_dir = root / datetime.now(
        timezone.utc
    ).strftime("run_%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir()

    write_json(run_dir / "submission_response.json", result)

    status_url = result.get("status_url")
    file_url = result.get("file_url")
    file_name = result.get("file_name")

    if not all((status_url, file_url, file_name)):
        raise RuntimeError(
            "Submission response missing required download fields"
        )

    for url in (status_url, file_url):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in (
            "api.usaspending.gov",
            "files.usaspending.gov",
        ):
            raise RuntimeError(f"Unexpected URL: {url}")

    if Path(file_name).name != file_name or not file_name.endswith(".zip"):
        raise RuntimeError("Unsafe or unexpected ZIP filename")

    completed = False

    for poll in range(1, args.max_polls + 1):
        status = request_json(status_url)
        write_json(run_dir / "latest_status.json", status)
        print(f"POLL {poll}:", json.dumps(status)[:800])

        state = str(status.get("status", "")).lower()

        if state in ("finished", "completed", "success"):
            completed = True
            break

        if state in ("failed", "error"):
            raise RuntimeError(f"Export failed: {status}")

        if poll < args.max_polls:
            time.sleep(args.poll_seconds)

    if not completed:
        raise RuntimeError(
            "Polling limit reached. Job may still be running. "
            "Inspect latest_status.json before resubmitting."
        )

    destination = run_dir / file_name
    size, checksum = download_zip(file_url, destination)

    write_json(run_dir / "download_evidence.json", {
        "acquired_utc": timestamp(),
        "file_name": file_name,
        "file_url": file_url,
        "size_bytes": size,
        "sha256": checksum,
        "zip_crc_test": "PASS",
        "database_writes": False,
        "methodology_status": "PENDING_VALIDATION",
    })

    print("DOWNLOAD PASS")
    print("ZIP:", destination)
    print("BYTES:", size)
    print("SHA256:", checksum)
    print("NO DATABASE WRITES")

if __name__ == "__main__":
    main()
