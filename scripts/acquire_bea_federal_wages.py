from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


API_URL = "https://apps.bea.gov/api/data"

ROOT = Path(__file__).resolve().parents[1]

RAW_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "wages"
)

STATE_DIR = RAW_ROOT / "state"

YEARS = ",".join(
    str(year)
    for year in range(2015, 2025)
)

REQUESTS = [
    {
        "name":
            "sainc7n_federal_civilian_wages_2015_2024",

        "table":
            "SAINC7N",

        "line_code":
            "2001",

        "geo_fips":
            "53000",
    },
    {
        "name":
            "sainc7n_military_wages_2015_2024",

        "table":
            "SAINC7N",

        "line_code":
            "2002",

        "geo_fips":
            "53000",
    },
]


def sha256_file(path: Path) -> str:

    digest = hashlib.sha256()

    with path.open("rb") as f:

        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def get_api_key() -> str:

    api_key = os.environ.get(
        "BEA_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "BEA_API_KEY environment variable "
            "is not set."
        )

    return api_key


def extract_bea_error(
    payload: dict,
) -> object | None:

    beaapi = payload.get(
        "BEAAPI",
        {},
    )

    if "Error" in beaapi:
        return beaapi["Error"]

    results = beaapi.get(
        "Results"
    )

    if (
        isinstance(results, dict)
        and "Error" in results
    ):
        return results["Error"]

    return None


def request_bea(
    api_key: str,
    spec: dict,
) -> dict:

    params = {
        "UserID":
            api_key,

        "method":
            "GetData",

        "datasetname":
            "Regional",

        "TableName":
            spec["table"],

        "LineCode":
            spec["line_code"],

        "Year":
            YEARS,

        "GeoFips":
            spec["geo_fips"],

        "ResultFormat":
            "JSON",
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=120,
    )

    response.raise_for_status()

    payload = response.json()

    error = extract_bea_error(
        payload
    )

    if error is not None:

        raise RuntimeError(
            "BEA API returned an error:\n"
            + json.dumps(
                error,
                indent=2,
            )
        )

    rows = (
        payload
        .get("BEAAPI", {})
        .get("Results", {})
        .get("Data")
    )

    if not isinstance(
        rows,
        list,
    ):
        raise RuntimeError(
            "BEA response does not contain "
            "Results.Data as a list."
        )

    if len(rows) == 0:
        raise RuntimeError(
            "BEA returned zero data rows."
        )

    return payload


def write_json(
    path: Path,
    payload: dict,
) -> None:

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False,
        )

        f.write("\n")


def main() -> None:

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    api_key = get_api_key()

    manifest_rows = []

    for spec in REQUESTS:

        print(
            f"Requesting "
            f"{spec['table']} "
            f"line {spec['line_code']} "
            f"GeoFips={spec['geo_fips']}..."
        )

        payload = request_bea(
            api_key,
            spec,
        )

        rows = (
            payload
            ["BEAAPI"]
            ["Results"]
            ["Data"]
        )

        retrieved_at = datetime.now(
            timezone.utc
        )

        timestamp = (
            retrieved_at.strftime(
                "%Y%m%dT%H%M%SZ"
            )
        )

        output_path = (
            STATE_DIR
            / (
                f"{spec['name']}"
                f"_retrieved_{timestamp}.json"
            )
        )

        write_json(
            output_path,
            payload,
        )

        checksum = sha256_file(
            output_path
        )

        manifest_rows.append(
            {
                "retrieved_utc":
                    retrieved_at.isoformat(),

                "dataset":
                    "Regional",

                "table_name":
                    spec["table"],

                "line_code":
                    spec["line_code"],

                "geo_fips":
                    spec["geo_fips"],

                "years":
                    YEARS,

                "row_count":
                    len(rows),

                "file":
                    str(
                        output_path.relative_to(
                            ROOT
                        )
                    ),

                "sha256":
                    checksum,
            }
        )

        print(
            f"  Saved: {output_path}"
        )

        print(
            f"  Rows:  {len(rows)}"
        )

        print(
            f"  SHA256: {checksum}"
        )

    # ------------------------------------------------------------------------
    # Hard acquisition controls
    # ------------------------------------------------------------------------

    if len(
        manifest_rows
    ) != 2:

        raise RuntimeError(
            "Expected two successful "
            "SAINC7N acquisitions."
        )

    for item in manifest_rows:

        if item["row_count"] != 10:

            raise RuntimeError(
                "Expected 10 annual observations "
                f"for {item['table_name']}-"
                f"{item['line_code']}; "
                f"received {item['row_count']}."
            )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    manifest_path = (
        RAW_ROOT
        / (
            "bea_federal_wages_"
            "acquisition_manifest_"
            f"{timestamp}.json"
        )
    )

    manifest = {
        "generated_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "purpose":
            (
                "WCFFBP BEA Washington "
                "federal civilian and military "
                "wages-and-salaries acquisition"
            ),

        "reference_period_type":
            "CALENDAR_YEAR",

        "geography":
            "WASHINGTON_STATE",

        "requests":
            manifest_rows,

        "line_code_evidence": {
            "2001":
                (
                    "Govt. and govt. enterprises "
                    "wages and salaries: "
                    "Federal civilian"
                ),

            "2002":
                (
                    "Govt. and govt. enterprises "
                    "wages and salaries: Military"
                ),
        },

        "methodology_note":
            (
                "SAINC7N wages and salaries are "
                "preserved as BEA calendar-year "
                "economic observations. They are "
                "not themselves WCFFBP federal "
                "fiscal-year accounting controls."
            ),
    }

    write_json(
        manifest_path,
        manifest,
    )

    print()
    print("=" * 72)

    print(
        "BEA FEDERAL WAGES "
        "ACQUISITION COMPLETE"
    )

    print("=" * 72)

    print(
        f"Manifest: {manifest_path}"
    )

    print(
        f"Requests: {len(manifest_rows)}"
    )

    print(
        "Expected observations: 20"
    )


if __name__ == "__main__":
    main()