from __future__ import annotations

import glob
import json
from collections import defaultdict
from decimal import Decimal
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


DATASETS = [
    {
        "label": "FEDERAL_CIVILIAN_COMPENSATION",
        "county_file": latest(
            str(
                COUNTY_DIR
                / "cainc6n_federal_civilian_2015_2024_retrieved_*.json"
            )
        ),
        "state_file": latest(
            str(
                STATE_DIR
                / "sainc6n_federal_civilian_2015_2024_retrieved_*.json"
            )
        ),
        "county_code": "CAINC6N-2001",
        "state_code": "SAINC6N-2001",
    },
    {
        "label": "MILITARY_COMPENSATION",
        "county_file": latest(
            str(
                COUNTY_DIR
                / "cainc6n_military_2015_2024_retrieved_*.json"
            )
        ),
        "state_file": latest(
            str(
                STATE_DIR
                / "sainc6n_military_2015_2024_retrieved_*.json"
            )
        ),
        "county_code": "CAINC6N-2002",
        "state_code": "SAINC6N-2002",
    },
]


def load_rows(path: Path) -> list[dict]:
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

    if not rows:
        raise RuntimeError(
            f"No BEA data rows found in {path}"
        )

    return rows


def parse_value(row: dict) -> Decimal:
    raw = str(
        row.get("DataValue", "")
    ).strip()

    if raw in {
        "",
        "(NA)",
        "(D)",
        "(L)",
        "NA",
        "N/A",
    }:
        raise ValueError(
            "Non-numeric or suppressed DataValue "
            f"for {row.get('GeoFips')} "
            f"{row.get('TimePeriod')}: {raw!r}"
        )

    raw = raw.replace(",", "")

    value = Decimal(raw)

    unit_mult = int(
        row.get("UNIT_MULT", "0")
    )

    return value * (
        Decimal(10) ** unit_mult
    )


def reconcile_dataset(spec: dict) -> None:
    county_rows = load_rows(
        spec["county_file"]
    )

    state_rows = load_rows(
        spec["state_file"]
    )

    print()
    print("=" * 100)
    print(spec["label"])
    print("=" * 100)

    # ------------------------------------------------------------
    # Validate expected series identity.
    # ------------------------------------------------------------

    county_codes = {
        row.get("Code")
        for row in county_rows
    }

    state_codes = {
        row.get("Code")
        for row in state_rows
    }

    if county_codes != {
        spec["county_code"]
    }:
        raise RuntimeError(
            "Unexpected county series codes: "
            f"{county_codes}"
        )

    if state_codes != {
        spec["state_code"]
    }:
        raise RuntimeError(
            "Unexpected state series codes: "
            f"{state_codes}"
        )

    # ------------------------------------------------------------
    # Separate county rows from embedded WA aggregate.
    # ------------------------------------------------------------

    county_detail = [
        row
        for row in county_rows
        if row["GeoFips"] != "53000"
    ]

    county_state_control = [
        row
        for row in county_rows
        if row["GeoFips"] == "53000"
    ]

    # ------------------------------------------------------------
    # Validate geography counts.
    # ------------------------------------------------------------

    distinct_counties = {
        row["GeoFips"]
        for row in county_detail
    }

    years = sorted(
        {
            int(row["TimePeriod"])
            for row in county_rows
        }
    )

    print(
        f"Distinct counties: "
        f"{len(distinct_counties)}"
    )

    print(
        "Years: "
        + ", ".join(
            str(year)
            for year in years
        )
    )

    if len(distinct_counties) != 39:
        raise RuntimeError(
            "Expected 39 Washington counties; "
            f"found {len(distinct_counties)}."
        )

    # ------------------------------------------------------------
    # Build annual controls.
    # ------------------------------------------------------------

    county_sum_by_year = defaultdict(
        Decimal
    )

    for row in county_detail:
        year = int(
            row["TimePeriod"]
        )

        county_sum_by_year[year] += (
            parse_value(row)
        )

    embedded_state_by_year = {
        int(row["TimePeriod"]):
            parse_value(row)
        for row in county_state_control
    }

    sainc_state_by_year = {
        int(row["TimePeriod"]):
            parse_value(row)
        for row in state_rows
    }

    # ------------------------------------------------------------
    # Print annual reconciliation.
    # ------------------------------------------------------------

    print()
    print(
        f"{'Year':<6}"
        f"{'39-county sum':>20}"
        f"{'CAINC WA':>20}"
        f"{'SAINC WA':>20}"
        f"{'County-State diff':>20}"
        f"{'Pct diff':>14}"
    )

    print("-" * 100)

    max_abs_diff = Decimal(0)

    for year in years:

        county_sum = (
            county_sum_by_year[year]
        )

        cainc_state = (
            embedded_state_by_year[year]
        )

        sainc_state = (
            sainc_state_by_year[year]
        )

        # Independent CAINC6N vs SAINC6N state-control test.
        if cainc_state != sainc_state:
            raise RuntimeError(
                f"{year}: CAINC6N Washington "
                f"aggregate {cainc_state} does not "
                f"equal SAINC6N Washington "
                f"control {sainc_state}."
            )

        diff = (
            county_sum
            - sainc_state
        )

        abs_diff = abs(diff)

        max_abs_diff = max(
            max_abs_diff,
            abs_diff,
        )

        if sainc_state != 0:
            pct_diff = (
                diff
                / sainc_state
                * Decimal(100)
            )
        else:
            pct_diff = Decimal(0)

        print(
            f"{year:<6}"
            f"${county_sum:>19,.0f}"
            f"${cainc_state:>19,.0f}"
            f"${sainc_state:>19,.0f}"
            f"${diff:>19,.0f}"
            f"{pct_diff:>13.6f}%"
        )

    print()
    print(
        "CAINC6N WA aggregate "
        "vs SAINC6N WA state control: "
        "EXACT MATCH for all years."
    )

    print(
        "Maximum absolute difference between "
        "39-county sum and WA state control: "
        f"${max_abs_diff:,.0f}"
    )


def main() -> None:
    for spec in DATASETS:
        reconcile_dataset(spec)


if __name__ == "__main__":
    main()