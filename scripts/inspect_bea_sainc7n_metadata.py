from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


API_URL = "https://apps.bea.gov/api/data"

ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "wages"
    / "documentation"
)


def main() -> None:

    api_key = os.environ.get("BEA_API_KEY")

    if not api_key:
        raise RuntimeError(
            "BEA_API_KEY environment variable is not set."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    params = {
        "UserID": api_key,
        "method": "GetParameterValuesFiltered",
        "datasetname": "Regional",
        "TargetParameter": "LineCode",
        "TableName": "SAINC7N",
        "ResultFormat": "JSON",
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=120,
    )

    response.raise_for_status()

    payload = response.json()

    beaapi = payload.get(
        "BEAAPI",
        {},
    )

    if "Error" in beaapi:
        raise RuntimeError(
            "BEA API error:\n"
            + json.dumps(
                beaapi["Error"],
                indent=2,
            )
        )

    values = (
        beaapi
        .get("Results", {})
        .get("ParamValue", [])
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_path = (
        OUTPUT_DIR
        / (
            "sainc7n_linecode_metadata_"
            f"retrieved_{timestamp}.json"
        )
    )

    with output_path.open(
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

    print(
        f"Metadata file: {output_path}"
    )

    print(
        f"Line codes returned: {len(values)}"
    )

    print()
    print(
        "Federal / military matches:"
    )
    print("-" * 80)

    matches = []

    for item in values:

        desc = str(
            item.get("Desc", "")
        )

        desc_lower = desc.lower()

        if (
            "federal" in desc_lower
            or "military" in desc_lower
        ):
            matches.append(
                item
            )

    if not matches:
        print(
            "NONE FOUND"
        )

    for item in matches:

        print(
            json.dumps(
                item,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()