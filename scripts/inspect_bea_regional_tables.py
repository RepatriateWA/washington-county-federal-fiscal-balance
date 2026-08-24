from __future__ import annotations

import json
import os

import requests


API_URL = "https://apps.bea.gov/api/data"


def main() -> None:

    api_key = os.environ.get("BEA_API_KEY")

    if not api_key:
        raise RuntimeError(
            "BEA_API_KEY environment variable is not set."
        )

    params = {
        "UserID": api_key,
        "method": "GetParameterValues",
        "datasetname": "Regional",
        "ParameterName": "TableName",
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

    print(
        f"Regional tables returned: {len(values)}"
    )

    print()
    print("Potential wage/earnings tables:")
    print("-" * 80)

    matches = []

    for item in values:

        key = str(
            item.get("Key", "")
        )

        desc = str(
            item.get("Desc", "")
        )

        text = (
            key + " " + desc
        ).lower()

        if any(
            term in text
            for term in (
                "wage",
                "salary",
                "salaries",
                "earning",
                "compensation",
                "income by major component",
            )
        ):
            matches.append(item)

    for item in matches:
        print(
            f"{item.get('Key')!r}"
            f"  {item.get('Desc')!r}"
        )

    print()
    print("All CAINC tables:")
    print("-" * 80)

    for item in values:

        key = str(
            item.get("Key", "")
        )

        if key.startswith("CAINC"):
            print(
                f"{key!r}"
                f"  {item.get('Desc')!r}"
            )

    print()
    print("All SAINC tables:")
    print("-" * 80)

    for item in values:

        key = str(
            item.get("Key", "")
        )

        if key.startswith("SAINC"):
            print(
                f"{key!r}"
                f"  {item.get('Desc')!r}"
            )


if __name__ == "__main__":
    main()