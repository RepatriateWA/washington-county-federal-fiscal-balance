from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_ROOT = "https://api.usaspending.gov/api/v2"

# Contract award types only, excluding Contract IDVs.
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
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"USAspending HTTP {exc.code} from {url}\n{body}"
        ) from exc


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def fiscal_year_dates(
    fiscal_year: int,
) -> tuple[str, str]:
    return (
        f"{fiscal_year - 1}-10-01",
        f"{fiscal_year}-09-30",
    )


def build_filters(
    fiscal_year: int,
) -> dict[str, Any]:
    start_date, end_date = fiscal_year_dates(
        fiscal_year
    )

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Probe the USAspending contract-specific download endpoint "
            "for Washington procurement."
        )
    )

    parser.add_argument(
        "--fiscal-year",
        type=int,
        required=True,
        help="Federal fiscal year to test.",
    )

    args = parser.parse_args()

    fiscal_year = args.fiscal_year

    target_dir = (
        REPO_ROOT
        / "data"
        / "raw"
        / "usaspending"
        / "procurement"
        / f"FY{fiscal_year}"
        / "contract_download_probe"
    )

    target_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    filters = build_filters(
        fiscal_year
    )

    payload = {
        "filters": filters,
        "file_format": "csv",
    }

    request_path = (
        target_dir
        / "contract_download_request.json"
    )

    write_json(
        request_path,
        payload,
    )

    print("=" * 88)
    print("USASPENDING CONTRACT-SPECIFIC DOWNLOAD PROBE")
    print("=" * 88)
    print()
    print(
        f"Federal fiscal year .............. FY{fiscal_year}"
    )
    print(
        "Award types ...................... A, B, C, D"
    )
    print(
        "Place of performance ............. Washington"
    )
    print(
        "Recipient-location filter ........ NONE"
    )
    print()
    print(
        f"Request preserved ................ {request_path}"
    )
    print()

    url = (
        f"{API_ROOT}/download/contract/"
    )

    print(
        "Submitting contract-specific download request..."
    )

    response = post_json(
        url,
        payload,
    )

    response_path = (
        target_dir
        / "contract_download_response.json"
    )

    write_json(
        response_path,
        response,
    )

    print()
    print("USAspending response:")
    print(
        json.dumps(
            response,
            indent=2,
        )
    )
    print()
    print(
        f"Response preserved ............... {response_path}"
    )
    print()
    print("=" * 88)
    print("CONTRACT DOWNLOAD PROBE COMPLETE")
    print("=" * 88)


if __name__ == "__main__":
    main()