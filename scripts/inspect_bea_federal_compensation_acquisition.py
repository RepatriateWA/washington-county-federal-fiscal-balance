from __future__ import annotations

import glob
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COUNTY_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "compensation"
    / "county"
)

STATE_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "compensation"
    / "state"
)


def latest(pattern: str) -> Path:
    files = sorted(glob.glob(pattern))

    if not files:
        raise RuntimeError(
            f"No files matched: {pattern}"
        )

    return Path(files[-1])


FILES = [
    (
        "CAINC6N Federal civilian",
        latest(
            str(
                COUNTY_DIR
                / "cainc6n_federal_civilian_2015_2024_retrieved_*.json"
            )
        ),
    ),
    (
        "CAINC6N Military",
        latest(
            str(
                COUNTY_DIR
                / "cainc6n_military_2015_2024_retrieved_*.json"
            )
        ),
    ),
    (
        "SAINC6N Federal civilian",
        latest(
            str(
                STATE_DIR
                / "sainc6n_federal_civilian_2015_2024_retrieved_*.json"
            )
        ),
    ),
    (
        "SAINC6N Military",
        latest(
            str(
                STATE_DIR
                / "sainc6n_military_2015_2024_retrieved_*.json"
            )
        ),
    ),
]


for label, path in FILES:

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        payload = json.load(f)

    rows = (
        payload
        .get("BEAAPI", {})
        .get("Results", {})
        .get("Data", [])
    )

    print()
    print("=" * 80)
    print(label)
    print("=" * 80)

    print(f"File: {path}")
    print(f"Rows: {len(rows)}")

    if not rows:
        continue

    print()
    print("Columns:")
    print(sorted(rows[0].keys()))

    geo_pairs = sorted(
        {
            (
                row.get("GeoFips"),
                row.get("GeoName"),
            )
            for row in rows
        }
    )

    years = sorted(
        {
            str(row.get("TimePeriod"))
            for row in rows
        }
    )

    line_codes = sorted(
        {
            str(row.get("LineCode"))
            for row in rows
        }
    )

    units = sorted(
        {
            str(row.get("UNIT_MULT"))
            + " | "
            + str(row.get("CL_UNIT"))
            for row in rows
        }
    )

    print()
    print(
        f"Distinct geographies: "
        f"{len(geo_pairs)}"
    )

    for geo_fips, geo_name in geo_pairs:
        print(
            f"  {geo_fips!r}  "
            f"{geo_name!r}"
        )

    print()
    print(
        "Years: "
        + ", ".join(years)
    )

    print(
        "Line codes: "
        + ", ".join(line_codes)
    )

    print("Units:")
    for unit in units:
        print(f"  {unit}")

    print()
    print("First 5 rows:")

    for row in rows[:5]:
        print(
            json.dumps(
                row,
                indent=2,
            )
        )