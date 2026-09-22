from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


API_URL = "https://apps.bea.gov/api/data"

ROOT = Path(__file__).resolve().parents[1]

RAW_ROOT = ROOT / "data" / "raw" / "bea" / "compensation"

COUNTY_DIR = RAW_ROOT / "county"
STATE_DIR = RAW_ROOT / "state"
METADATA_DIR = RAW_ROOT / "documentation"

YEARS = ",".join(str(year) for year in range(2015, 2025))


# ============================================================================
# Authoritative BEA Regional table/line definitions
#
# CAINC6N / SAINC6N:
#
#     2001 = Government and government enterprises compensation:
#            Federal civilian
#
#     2002 = Government and government enterprises compensation:
#            Military
#
# These values were confirmed from the BEA Regional API metadata before
# acquisition.
# ============================================================================

REQUESTS = [
    {
        "name": "cainc6n_federal_civilian_2015_2024",
        "table": "CAINC6N",
        "line_code": "2001",
        "geo_fips": "WA",
        "output_dir": COUNTY_DIR,
    },
    {
        "name": "cainc6n_military_2015_2024",
        "table": "CAINC6N",
        "line_code": "2002",
        "geo_fips": "WA",
        "output_dir": COUNTY_DIR,
    },
    {
        "name": "sainc6n_federal_civilian_2015_2024",
        "table": "SAINC6N",
        "line_code": "2001",
        "geo_fips": "53000",
        "output_dir": STATE_DIR,
    },
    {
        "name": "sainc6n_military_2015_2024",
        "table": "SAINC6N",
        "line_code": "2002",
        "geo_fips": "53000",
        "output_dir": STATE_DIR,
    },
    {
        "name": "sainc6n_federal_civilian_all_states_2015_2024",
        "table": "SAINC6N",
        "line_code": "2001",
        "geo_fips": "STATE",
        "output_dir": STATE_DIR,
    },
    {
        "name": "sainc6n_military_all_states_2015_2024",
        "table": "SAINC6N",
        "line_code": "2002",
        "geo_fips": "STATE",
        "output_dir": STATE_DIR,
    },
    {
        "name": "cainc6n_federal_civilian_2014",
        "table": "CAINC6N",
        "line_code": "2001",
        "geo_fips": "WA",
        "years": "2014",
        "output_dir": COUNTY_DIR,
    },
    {
        "name": "cainc6n_military_2014",
        "table": "CAINC6N",
        "line_code": "2002",
        "geo_fips": "WA",
        "years": "2014",
        "output_dir": COUNTY_DIR,
    },
]

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def ensure_directories() -> None:
    for directory in (
        COUNTY_DIR,
        STATE_DIR,
        METADATA_DIR,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def get_api_key() -> str:
    api_key = os.environ.get("BEA_API_KEY")

    if not api_key:
        print(
            "ERROR: BEA_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    return api_key


def extract_bea_error(payload: dict) -> object | None:
    """
    Return a BEA API error object if one is present.

    BEA errors may occur directly under:

        BEAAPI.Error

    rather than beneath:

        BEAAPI.Results.Error

    Both locations are checked defensively.
    """

    beaapi = payload.get("BEAAPI", {})

    if "Error" in beaapi:
        return beaapi["Error"]

    results = beaapi.get("Results")

    if isinstance(results, dict) and "Error" in results:
        return results["Error"]

    return None


def request_bea(
    params: dict[str, str],
    *,
    require_data: bool = False,
) -> dict:

    response = requests.get(
        API_URL,
        params=params,
        timeout=120,
    )

    response.raise_for_status()

    payload = response.json()

    error = extract_bea_error(payload)

    if error is not None:
        raise RuntimeError(
            "BEA API returned an error:\n"
            + json.dumps(
                error,
                indent=2,
            )
        )

    if require_data:
        results = (
            payload
            .get("BEAAPI", {})
            .get("Results", {})
        )

        data_rows = results.get("Data")

        if not isinstance(data_rows, list):
            raise RuntimeError(
                "BEA API response did not contain "
                "BEAAPI.Results.Data as a list."
            )

        if len(data_rows) == 0:
            raise RuntimeError(
                "BEA API returned zero data rows "
                "for a request that requires data."
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


def acquire_data(
    api_key: str,
) -> list[dict]:

    manifest_rows = []

    for request_spec in REQUESTS:

        params = {
            "UserID": api_key,
            "method": "GetData",
            "datasetname": "Regional",
            "TableName": request_spec["table"],
            "LineCode": request_spec["line_code"],
            "Year": request_spec.get(
                "years",
                YEARS,
            ),
            "GeoFips": request_spec["geo_fips"],
            "ResultFormat": "JSON",
        }

        print(
            f"Requesting {request_spec['table']} "
            f"line {request_spec['line_code']} "
            f"GeoFips={request_spec['geo_fips']}..."
        )

        payload = request_bea(
            params,
            require_data=True,
        )

        retrieved_at = datetime.now(
            timezone.utc
        )

        timestamp = retrieved_at.strftime(
            "%Y%m%dT%H%M%SZ"
        )

        filename = (
            f"{request_spec['name']}"
            f"_retrieved_{timestamp}.json"
        )

        output_path = (
            request_spec["output_dir"]
            / filename
        )

        write_json(
            output_path,
            payload,
        )

        checksum = sha256_file(
            output_path
        )

        results = (
            payload
            .get("BEAAPI", {})
            .get("Results", {})
        )

        data_rows = results["Data"]

        manifest_rows.append(
            {
                "retrieved_utc":
                    retrieved_at.isoformat(),

                "dataset":
                    "Regional",

                "table_name":
                    request_spec["table"],

                "line_code":
                    request_spec["line_code"],

                "geo_fips":
                    request_spec["geo_fips"],

                "years":
                    request_spec.get(
                        "years",
                        YEARS,
                    ),

                "row_count":
                    len(data_rows),

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
            f"  Rows:  {len(data_rows)}"
        )

        print(
            f"  SHA256: {checksum}"
        )

    return manifest_rows


def acquire_metadata(
    api_key: str,
) -> dict:

    params = {
        "UserID": api_key,
        "method":
            "GetParameterValuesFiltered",
        "datasetname":
            "Regional",
        "TargetParameter":
            "LineCode",
        "TableName":
            "CAINC6N",
        "ResultFormat":
            "JSON",
    }

    print(
        "Requesting CAINC6N "
        "LineCode metadata..."
    )

    return request_bea(
        params,
        require_data=False,
    )


def validate_manifest(
    manifest_rows: list[dict],
) -> None:

    expected_acquisitions = len(REQUESTS)

    if len(manifest_rows) != expected_acquisitions:
        raise RuntimeError(
            f"Expected {expected_acquisitions} successful BEA "
            f"data acquisitions; got "
            f"{len(manifest_rows)}."
        )

    for row in manifest_rows:
        if row["row_count"] <= 0:
            raise RuntimeError(
                "Manifest contains a zero-row "
                f"request: {row}"
            )


def main() -> None:

    ensure_directories()

    api_key = get_api_key()

    manifest_rows = acquire_data(
        api_key
    )

    validate_manifest(
        manifest_rows
    )

    metadata = acquire_metadata(
        api_key
    )

    timestamp = (
        datetime.now(timezone.utc)
        .strftime("%Y%m%dT%H%M%SZ")
    )

    metadata_path = (
        METADATA_DIR
        / (
            "cainc6n_linecode_metadata_"
            f"retrieved_{timestamp}.json"
        )
    )

    write_json(
        metadata_path,
        metadata,
    )

    manifest_path = (
        RAW_ROOT
        / (
            "bea_compensation_"
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
                "WCFFBP federal civilian "
                "and military compensation "
                "source acquisition"
            ),

        "requests":
            manifest_rows,

        "metadata_file":
            str(
                metadata_path.relative_to(
                    ROOT
                )
            ),

        "metadata_sha256":
            sha256_file(
                metadata_path
            ),

        "line_code_evidence": {
            "2001":
                "Federal civilian compensation",
            "2002":
                "Military compensation",
        },
    }

    write_json(
        manifest_path,
        manifest,
    )

    print()
    print("=" * 72)
    print(
        "BEA COMPENSATION "
        "ACQUISITION COMPLETE"
    )
    print("=" * 72)

    print(
        f"Manifest: {manifest_path}"
    )

    print(
        f"Requests: {len(manifest_rows)}"
    )


if __name__ == "__main__":
    main()