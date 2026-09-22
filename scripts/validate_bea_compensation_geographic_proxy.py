from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]

COMP_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "compensation"
    / "state"
)

WAGE_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bea"
    / "wages"
    / "state"
)

EVIDENCE_DIR = (
    ROOT
    / "evidence"
    / "bea"
    / "federal_wage_geographic_proxy"
)

FILES = {
    "FEDERAL_CIVILIAN": {
        "compensation": (
            COMP_DIR
            / (
                "sainc6n_federal_civilian_all_states_"
                "2015_2024_retrieved_20260913T225514Z.json"
            )
        ),
        "wages": (
            WAGE_DIR
            / (
                "sainc7n_federal_civilian_wages_all_states_"
                "2015_2024_retrieved_20260914T000138Z.json"
            )
        ),
    },
    "MILITARY": {
        "compensation": (
            COMP_DIR
            / (
                "sainc6n_military_all_states_"
                "2015_2024_retrieved_20260913T225515Z.json"
            )
        ),
        "wages": (
            WAGE_DIR
            / (
                "sainc7n_military_wages_all_states_"
                "2015_2024_retrieved_20260914T000138Z.json"
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


def is_state_equivalent(
    geo_fips: str,
) -> bool:

    # Current SAINC6N/SAINC7N STATE response:
    #
    # 00000       United States
    # 01000-56000 50 states + District of Columbia
    # 91000-98000 BEA regions
    #
    # Keep only the 51 state-equivalent jurisdictions.

    value = int(geo_fips)

    return (
        value != 0
        and value < 90000
    )


def pearson(
    xs: list[float],
    ys: list[float],
) -> float:

    if len(xs) != len(ys):

        raise RuntimeError(
            "Pearson inputs differ in length."
        )

    if len(xs) < 2:

        raise RuntimeError(
            "Pearson correlation requires "
            "at least two observations."
        )

    x_mean = mean(xs)
    y_mean = mean(ys)

    numerator = sum(
        (x - x_mean)
        * (y - y_mean)
        for x, y in zip(
            xs,
            ys,
        )
    )

    x_ss = sum(
        (x - x_mean) ** 2
        for x in xs
    )

    y_ss = sum(
        (y - y_mean) ** 2
        for y in ys
    )

    denominator = math.sqrt(
        x_ss * y_ss
    )

    if denominator == 0:

        raise RuntimeError(
            "Zero variance in Pearson input."
        )

    return numerator / denominator


def index_rows(
    rows: list[dict],
) -> dict[tuple[str, str], dict]:

    result = {}

    for row in rows:

        key = (
            row["TimePeriod"],
            row["GeoFips"],
        )

        if key in result:

            raise RuntimeError(
                f"Duplicate year/geography: {key}"
            )

        result[key] = row

    return result


def validate_source_pair(
    family: str,
    comp_rows: list[dict],
    wage_rows: list[dict],
) -> None:

    if len(comp_rows) != 600:

        raise RuntimeError(
            f"{family}: expected 600 "
            "compensation rows, got "
            f"{len(comp_rows)}."
        )

    if len(wage_rows) != 600:

        raise RuntimeError(
            f"{family}: expected 600 "
            "wage rows, got "
            f"{len(wage_rows)}."
        )

    comp_keys = {
        (
            row["TimePeriod"],
            row["GeoFips"],
        )
        for row in comp_rows
    }

    wage_keys = {
        (
            row["TimePeriod"],
            row["GeoFips"],
        )
        for row in wage_rows
    }

    if comp_keys != wage_keys:

        missing_wage = sorted(
            comp_keys - wage_keys
        )

        missing_comp = sorted(
            wage_keys - comp_keys
        )

        raise RuntimeError(
            f"{family}: geography/year keys "
            "do not match.\n"
            f"Missing wages: {missing_wage}\n"
            f"Missing compensation: "
            f"{missing_comp}"
        )


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

        comp_rows = load_rows(
            paths["compensation"]
        )

        wage_rows = load_rows(
            paths["wages"]
        )

        validate_source_pair(
            family,
            comp_rows,
            wage_rows,
        )

        comp = index_rows(
            comp_rows
        )

        wage = index_rows(
            wage_rows
        )

        years = sorted(
            {
                row["TimePeriod"]
                for row in comp_rows
            }
        )

        if years != [
            str(year)
            for year in range(
                2015,
                2025,
            )
        ]:

            raise RuntimeError(
                f"{family}: unexpected years "
                f"{years}"
            )

        for year in years:

            us_key = (
                year,
                "00000",
            )

            comp_us = numeric_value(
                comp[us_key]
            )

            wage_us = numeric_value(
                wage[us_key]
            )

            state_keys = sorted(
                key
                for key in comp
                if (
                    key[0] == year
                    and is_state_equivalent(
                        key[1]
                    )
                )
            )

            if len(state_keys) != 51:

                raise RuntimeError(
                    f"{family} {year}: "
                    f"expected 51 state-equivalent "
                    f"jurisdictions, got "
                    f"{len(state_keys)}."
                )

            comp_state_total = sum(
                numeric_value(
                    comp[key]
                )
                for key in state_keys
            )

            wage_state_total = sum(
                numeric_value(
                    wage[key]
                )
                for key in state_keys
            )

            comp_us_shares = []
            wage_us_shares = []

            comp_norm_shares = []
            wage_norm_shares = []

            year_detail = []

            for key in state_keys:

                comp_row = comp[key]
                wage_row = wage[key]

                comp_value = numeric_value(
                    comp_row
                )

                wage_value = numeric_value(
                    wage_row
                )

                comp_us_share = (
                    comp_value
                    / comp_us
                )

                wage_us_share = (
                    wage_value
                    / wage_us
                )

                comp_norm_share = (
                    comp_value
                    / comp_state_total
                )

                wage_norm_share = (
                    wage_value
                    / wage_state_total
                )

                us_diff = (
                    comp_us_share
                    - wage_us_share
                )

                norm_diff = (
                    comp_norm_share
                    - wage_norm_share
                )

                wage_share_ratio = (
                    comp_norm_share
                    / wage_norm_share
                    if wage_norm_share != 0
                    else None
                )

                record = {
                    "family":
                        family,

                    "year":
                        int(year),

                    "geo_fips":
                        key[1],

                    "geo_name":
                        comp_row["GeoName"],

                    "compensation_value_thousands":
                        comp_value,

                    "wage_value_thousands":
                        wage_value,

                    "comp_us_share":
                        comp_us_share,

                    "wage_us_share":
                        wage_us_share,

                    "us_share_difference":
                        us_diff,

                    "us_share_abs_error":
                        abs(us_diff),

                    "comp_51_share":
                        comp_norm_share,

                    "wage_51_share":
                        wage_norm_share,

                    "normalized_share_difference":
                        norm_diff,

                    "normalized_share_abs_error":
                        abs(norm_diff),

                    "comp_to_wage_normalized_share_ratio":
                        wage_share_ratio,
                }

                detail_rows.append(
                    record
                )

                year_detail.append(
                    record
                )

                comp_us_shares.append(
                    comp_us_share
                )

                wage_us_shares.append(
                    wage_us_share
                )

                comp_norm_shares.append(
                    comp_norm_share
                )

                wage_norm_shares.append(
                    wage_norm_share
                )

            worst_us = max(
                year_detail,
                key=lambda r:
                    r["us_share_abs_error"],
            )

            worst_norm = max(
                year_detail,
                key=lambda r:
                    r[
                        "normalized_share_abs_error"
                    ],
            )

            washington = next(
                row
                for row in year_detail
                if row["geo_fips"]
                == "53000"
            )

            us_mae = mean(
                row["us_share_abs_error"]
                for row in year_detail
            )

            norm_mae = mean(
                row[
                    "normalized_share_abs_error"
                ]
                for row in year_detail
            )

            # Total variation distance between
            # the two 51-jurisdiction geographic
            # distributions.
            tvd = (
                0.5
                * sum(
                    row[
                        "normalized_share_abs_error"
                    ]
                    for row in year_detail
                )
            )

            summary = {
                "family":
                    family,

                "year":
                    int(year),

                "jurisdictions":
                    51,

                "pearson_us_share":
                    pearson(
                        comp_us_shares,
                        wage_us_shares,
                    ),

                "pearson_51_normalized_share":
                    pearson(
                        comp_norm_shares,
                        wage_norm_shares,
                    ),

                "mean_abs_us_share_error_pp":
                    us_mae * 100,

                "mean_abs_normalized_share_error_pp":
                    norm_mae * 100,

                "total_variation_distance":
                    tvd,

                "max_abs_us_share_error_pp":
                    worst_us[
                        "us_share_abs_error"
                    ] * 100,

                "max_abs_us_share_error_geo":
                    worst_us[
                        "geo_name"
                    ],

                "max_abs_normalized_share_error_pp":
                    worst_norm[
                        "normalized_share_abs_error"
                    ] * 100,

                "max_abs_normalized_share_error_geo":
                    worst_norm[
                        "geo_name"
                    ],

                "wa_comp_us_share":
                    washington[
                        "comp_us_share"
                    ],

                "wa_wage_us_share":
                    washington[
                        "wage_us_share"
                    ],

                "wa_us_share_error_pp":
                    washington[
                        "us_share_difference"
                    ] * 100,

                "wa_comp_51_share":
                    washington[
                        "comp_51_share"
                    ],

                "wa_wage_51_share":
                    washington[
                        "wage_51_share"
                    ],

                "wa_normalized_share_error_pp":
                    washington[
                        "normalized_share_difference"
                    ] * 100,

                "wa_comp_to_wage_normalized_share_ratio":
                    washington[
                        "comp_to_wage_normalized_share_ratio"
                    ],

                "comp_state_sum_as_share_of_us":
                    comp_state_total
                    / comp_us,

                "wage_state_sum_as_share_of_us":
                    wage_state_total
                    / wage_us,
            }

            summary_rows.append(
                summary
            )

            print(
                f"{year}: "
                f"r={summary['pearson_51_normalized_share']:.8f}  "
                f"TVD={summary['total_variation_distance']:.6f}  "
                f"MAE={summary['mean_abs_normalized_share_error_pp']:.4f} pp  "
                f"MAX={summary['max_abs_normalized_share_error_pp']:.4f} pp "
                f"({summary['max_abs_normalized_share_error_geo']})  "
                f"WA={summary['wa_normalized_share_error_pp']:+.4f} pp"
            )

    detail_path = (
        EVIDENCE_DIR
        / "bea_compensation_vs_wage_share_detail.csv"
    )

    summary_path = (
        EVIDENCE_DIR
        / "bea_compensation_vs_wage_share_summary.csv"
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
    print("VALIDATION COMPLETE")
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