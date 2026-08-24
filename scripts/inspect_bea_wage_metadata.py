from __future__ import annotations

import json
import os
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

TABLES = [
    "CAINC7N",
    "SAINC7N",
]


def get_api_key() -> str:
    api_key = os.environ.get("BEA_API_KEY")

    if not api_key:
        raise RuntimeError(
            "BEA_API_KEY environment variable is not set."
        )

    return api_key


def request_metadata(
    api_key: str,
    table_name: str,
) -> dict:

    params = {
        "UserID": api_key,
        "method": "GetParameterValuesFiltered",
        "datasetname": "Regional",
        "TargetParameter": "LineCode",
        "TableName": table_name,
        "ResultFormat": "JSON",
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=120,
    )

    response.raise_for_status()

    payload = response.json()

    beaapi = payload.get("BEAAPI", {})

    if "Error" in beaapi:
        raise RuntimeError(
            f"BEA API error for {table_name}:\n"
            + json.dumps(
                beaapi["Error"],
                indent=2,
            )
        )

    return payload


def find_federal_lines(
    payload: dict,
) -> list[dict]:

    values = (
        payload
        .get("BEAAPI", {})
        .get("Results", {})
        .get("ParamValue", [])
    )

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
            matches.append(item)

    return matches


def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    api_key = get_api_key()

    for table_name in TABLES:

        print()
        print("=" * 80)
        print(table_name)
        print("=" * 80)

        payload = request_metadata(
            api_key,
            table_name,
        )

        output_path = (
            OUTPUT_DIR
            / f"{table_name.lower()}_linecode_metadata.json"
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

        matches = find_federal_lines(
            payload
        )

        print(
            f"Metadata saved: {output_path}"
        )

        print(
            f"Federal/military matches: "
            f"{len(matches)}"
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