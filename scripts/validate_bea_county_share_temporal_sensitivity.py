from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]

COUNTY_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "compensation"
    / "county"
)

EVIDENCE_DIR = (
    ROOT
    / "evidence"
    / "bea"
    / "federal_wage_geographic_proxy"
)

FILES = {
    "FEDERAL_CIVILIAN": {
        "2014": (
            COUNTY_DIR
            / (
                "cainc6n_federal_civilian_2014_"
                "retrieved_20260914T014619Z.json"
            )
        ),
        "2015_2024": (
            COUNTY_DIR
            / (
                "cainc6n_federal_civilian_2015_2024_"
                "retrieved_20260914T014616Z.json"
            )
        ),
    },
    "MILITARY": {
        "2014": (
            COUNTY_DIR
            / (
                "cainc6n_military_2014_"
                "retrieved_20260914T014620Z.json"
            )
        ),
        "2015_2024": (
            COUNTY_DIR
            / (
                "cainc6n_military_2015_2024_"
                "retrieved_20260914T014616Z.json"
            )
        ),
    },
}


def load_rows(path: Path) -> list[dict]:

    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    rows = (
        payload
        ["BEAAPI"]
        ["Results"]
        ["Data"]
    )

    if not isinstance(rows, list):
        raise RuntimeError(
            f"Results.Data is not a list: {path}"
        )

    return rows


def numeric_value(row: dict) -> float:

    value = (
        str(row["DataValue"])
        .replace(",", "")
        .strip()
    )

    if value in {
        "",
        "(NA)",
        "--",
    }:
        raise RuntimeError(
            f"Non-numeric BEA value: {row}"
        )

    return float(value)


def index_rows(
    rows: list[dict],
) -> dict[tuple[int, str], dict]:

    result = {}

    for row in rows:

        key = (
            int(row["TimePeriod"]),
            row["GeoFips"],
        )

        if key in result:
            raise RuntimeError(
                f"Duplicate year/geography: {key}"
            )

        result[key] = row

    return result


def pearson(
    xs: list[float],
    ys: list[float],
) -> float:

    x_mean = mean(xs)
    y_mean = mean(ys)

    numerator = sum(
        (x - x_mean)
        * (y - y_mean)
        for x, y in zip(xs, ys)
    )

    denominator = math.sqrt(
        sum(
            (x - x_mean) ** 2
            for x in xs
        )
        *
        sum(
            (y - y_mean) ** 2
            for y in ys
        )
    )

    if denominator == 0:
        raise RuntimeError(
            "Zero variance in Pearson input."
        )

    return numerator / denominator


def main() -> None:

    EVIDENCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    detail_rows = []
    summary_rows = []

    for family, paths in FILES.items():

        print()
        print("=" * 78)
        print(family)
        print("=" * 78)

        rows = (
            load_rows(paths["2014"])
            + load_rows(paths["2015_2024"])
        )

        indexed = index_rows(rows)

        expected_years = set(
            range(2014, 2025)
        )

        observed_years = {
            year
            for year, _ in indexed
        }

        if observed_years != expected_years:
            raise RuntimeError(
                f"{family}: unexpected years "
                f"{sorted(observed_years)}"
            )

        for year in range(
            2014,
            2025,
        ):

            state_key = (
                year,
                "53000",
            )

            if state_key not in indexed:
                raise RuntimeError(
                    f"{family} {year}: "
                    "Washington state total missing."
                )

            county_keys = sorted(
                key
                for key in indexed
                if (
                    key[0] == year
                    and key[1].startswith("53")
                    and key[1] != "53000"
                )
            )

            if len(county_keys) != 39:
                raise RuntimeError(
                    f"{family} {year}: expected "
                    f"39 counties, got "
                    f"{len(county_keys)}."
                )

            county_sum = sum(
                numeric_value(
                    indexed[key]
                )
                for key in county_keys
            )

            state_total = numeric_value(
                indexed[state_key]
            )

            if county_sum != state_total:
                raise RuntimeError(
                    f"{family} {year}: county "
                    f"sum {county_sum} does not "
                    f"equal WA state total "
                    f"{state_total}."
                )

        for year in range(
            2015,
            2025,
        ):

            prior_year = year - 1

            current_state = numeric_value(
                indexed[
                    (
                        year,
                        "53000",
                    )
                ]
            )

            prior_state = numeric_value(
                indexed[
                    (
                        prior_year,
                        "53000",
                    )
                ]
            )

            ffy_proxy_state = (
                0.25 * prior_state
                + 0.75 * current_state
            )

            current_shares = []
            proxy_shares = []
            year_detail = []

            county_keys = sorted(
                key
                for key in indexed
                if (
                    key[0] == year
                    and key[1].startswith("53")
                    and key[1] != "53000"
                )
            )

            for key in county_keys:

                geo_fips = key[1]

                current_row = indexed[
                    (
                        year,
                        geo_fips,
                    )
                ]

                prior_row = indexed[
                    (
                        prior_year,
                        geo_fips,
                    )
                ]

                current_value = numeric_value(
                    current_row
                )

                prior_value = numeric_value(
                    prior_row
                )

                cy_share = (
                    current_value
                    / current_state
                )

                ffy_proxy_value = (
                    0.25 * prior_value
                    + 0.75 * current_value
                )

                ffy_proxy_share = (
                    ffy_proxy_value
                    / ffy_proxy_state
                )

                difference = (
                    cy_share
                    - ffy_proxy_share
                )

                record = {
                    "family":
                        family,

                    "fiscal_year":
                        year,

                    "geo_fips":
                        geo_fips,

                    "geo_name":
                        current_row["GeoName"],

                    "prior_cy_compensation_thousands":
                        prior_value,

                    "current_cy_compensation_thousands":
                        current_value,

                    "cy_current_share":
                        cy_share,

                    "ffy_25_75_proxy_share":
                        ffy_proxy_share,

                    "share_difference":
                        difference,

                    "share_abs_error":
                        abs(difference),

                    "share_error_percentage_points":
                        difference * 100,

                    "abs_error_percentage_points":
                        abs(difference) * 100,

                    # Useful scale-free interpretation:
                    # allocation difference for each
                    # $1 billion of WA control.
                    "allocation_difference_per_1b_control":
                        difference
                        * 1_000_000_000,
                }

                detail_rows.append(
                    record
                )

                year_detail.append(
                    record
                )

                current_shares.append(
                    cy_share
                )

                proxy_shares.append(
                    ffy_proxy_share
                )

            worst = max(
                year_detail,
                key=lambda r:
                    r["share_abs_error"],
            )

            mae = mean(
                row["share_abs_error"]
                for row in year_detail
            )

            tvd = (
                0.5
                * sum(
                    row["share_abs_error"]
                    for row in year_detail
                )
            )

            summary = {
                "family":
                    family,

                "fiscal_year":
                    year,

                "counties":
                    39,

                "pearson_cy_vs_ffy_proxy":
                    pearson(
                        current_shares,
                        proxy_shares,
                    ),

                "mean_abs_error_percentage_points":
                    mae * 100,

                "total_variation_distance":
                    tvd,

                "max_abs_error_percentage_points":
                    worst[
                        "abs_error_percentage_points"
                    ],

                "max_abs_error_county":
                    worst["geo_name"],

                "max_allocation_difference_per_1b_control":
                    worst[
                        "allocation_difference_per_1b_control"
                    ],

                "current_share_sum":
                    sum(current_shares),

                "ffy_proxy_share_sum":
                    sum(proxy_shares),
            }

            summary_rows.append(
                summary
            )

            print(
                f"{year}: "
                f"r="
                f"{summary['pearson_cy_vs_ffy_proxy']:.8f}  "
                f"TVD="
                f"{summary['total_variation_distance']:.6f}  "
                f"MAE="
                f"{summary['mean_abs_error_percentage_points']:.4f} pp  "
                f"MAX="
                f"{summary['max_abs_error_percentage_points']:.4f} pp "
                f"({summary['max_abs_error_county']})  "
                f"MAX/$1B="
                f"${abs(summary['max_allocation_difference_per_1b_control']):,.0f}"
            )

    detail_path = (
        EVIDENCE_DIR
        / (
            "bea_county_share_"
            "temporal_sensitivity_detail.csv"
        )
    )

    summary_path = (
        EVIDENCE_DIR
        / (
            "bea_county_share_"
            "temporal_sensitivity_summary.csv"
        )
    )

    with detail_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=detail_rows[0].keys(),
        )

        writer.writeheader()
        writer.writerows(
            detail_rows
        )

    with summary_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=summary_rows[0].keys(),
        )

        writer.writeheader()
        writer.writerows(
            summary_rows
        )

    print()
    print("=" * 78)
    print("TEMPORAL SENSITIVITY VALIDATION COMPLETE")
    print("=" * 78)

    print(
        f"Detail rows: {len(detail_rows)}"
    )

    print(
        f"Summary rows: {len(summary_rows)}"
    )

    print(
        f"Detail: {detail_path}"
    )

    print(
        f"Summary: {summary_path}"
    )


if __name__ == "__main__":
    main()