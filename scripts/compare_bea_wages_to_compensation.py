from __future__ import annotations

import glob
import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COMP_STATE_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "compensation"
    / "state"
)

WAGE_STATE_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "wages"
    / "state"
)


def latest(pattern: str) -> Path:

    files = sorted(
        glob.glob(pattern)
    )

    if not files:
        raise RuntimeError(
            f"No files matched: {pattern}"
        )

    return Path(files[-1])


SERIES = [
    {
        "family":
            "FEDERAL_CIVILIAN",

        "compensation_file":
            latest(
                str(
                    COMP_STATE_DIR
                    / (
                        "sainc6n_federal_civilian_"
                        "2015_2024_retrieved_*.json"
                    )
                )
            ),

        "wages_file":
            latest(
                str(
                    WAGE_STATE_DIR
                    / (
                        "sainc7n_federal_civilian_wages_"
                        "2015_2024_retrieved_*.json"
                    )
                )
            ),
    },
    {
        "family":
            "MILITARY",

        "compensation_file":
            latest(
                str(
                    COMP_STATE_DIR
                    / (
                        "sainc6n_military_"
                        "2015_2024_retrieved_*.json"
                    )
                )
            ),

        "wages_file":
            latest(
                str(
                    WAGE_STATE_DIR
                    / (
                        "sainc7n_military_wages_"
                        "2015_2024_retrieved_*.json"
                    )
                )
            ),
    },
]


def load_rows(
    path: Path,
) -> list[dict]:

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
            f"No data rows in {path}"
        )

    return rows


def dollars(
    row: dict,
) -> Decimal:

    raw = str(
        row["DataValue"]
    ).replace(
        ",",
        "",
    )

    value = Decimal(raw)

    multiplier = int(
        row["UNIT_MULT"]
    )

    return (
        value
        * (
            Decimal(10)
            ** multiplier
        )
    )


def by_year(
    rows: list[dict],
) -> dict[int, Decimal]:

    result = {}

    for row in rows:

        geo_fips = str(
            row["GeoFips"]
        ).strip()

        if geo_fips != "53000":
            raise RuntimeError(
                "Expected Washington state "
                f"GeoFips 53000; found "
                f"{geo_fips}."
            )

        year = int(
            row["TimePeriod"]
        )

        if year in result:
            raise RuntimeError(
                f"Duplicate year: {year}"
            )

        result[year] = dollars(
            row
        )

    return result


def main() -> None:

    for spec in SERIES:

        compensation = by_year(
            load_rows(
                spec["compensation_file"]
            )
        )

        wages = by_year(
            load_rows(
                spec["wages_file"]
            )
        )

        if (
            set(compensation)
            != set(wages)
        ):
            raise RuntimeError(
                f"Year mismatch for "
                f"{spec['family']}"
            )

        print()
        print("=" * 110)
        print(spec["family"])
        print("=" * 110)

        print(
            f"{'Year':<6}"
            f"{'Compensation':>20}"
            f"{'Wages':>20}"
            f"{'Supplements':>20}"
            f"{'Wage share':>14}"
            f"{'Supplement share':>18}"
        )

        print("-" * 110)

        wage_shares = []

        supplement_shares = []

        for year in sorted(
            compensation
        ):

            comp = compensation[
                year
            ]

            wage = wages[
                year
            ]

            supplement = (
                comp - wage
            )

            wage_share = (
                wage
                / comp
                * Decimal(100)
            )

            supplement_share = (
                supplement
                / comp
                * Decimal(100)
            )

            wage_shares.append(
                wage_share
            )

            supplement_shares.append(
                supplement_share
            )

            print(
                f"{year:<6}"
                f"${comp:>19,.0f}"
                f"${wage:>19,.0f}"
                f"${supplement:>19,.0f}"
                f"{wage_share:>13.4f}%"
                f"{supplement_share:>17.4f}%"
            )

        print()
        print(
            "Wage-share range: "
            f"{min(wage_shares):.4f}% "
            f"to "
            f"{max(wage_shares):.4f}%"
        )

        print(
            "Supplement-share range: "
            f"{min(supplement_shares):.4f}% "
            f"to "
            f"{max(supplement_shares):.4f}%"
        )

        print()
        print(
            "Compensation source:"
        )

        print(
            f"  {spec['compensation_file']}"
        )

        print(
            "Wages source:"
        )

        print(
            f"  {spec['wages_file']}"
        )


if __name__ == "__main__":
    main()