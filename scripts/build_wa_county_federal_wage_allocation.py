from __future__ import annotations

import csv
import json
from decimal import (
    Decimal,
    ROUND_FLOOR,
)
from pathlib import Path

from etl.common.db import get_connection


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
    / "federal_wage_county_allocation"
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


CONTROL_SQL = """
SELECT
    fiscal_year,
    allocated_wa_civilian_wage_dollars,
    allocated_wa_military_wage_dollars,
    allocated_wa_total_federal_wage_dollars,
    civilian_allocation_confidence,
    military_allocation_confidence,
    civilian_methodology_version,
    military_methodology_version
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2015 AND 2024
ORDER BY fiscal_year;
"""


METHOD = (
    "OMB_WA_CONTROL__BEA_CAINC6N_COUNTY__"
    "FFY_25PCT_PRIOR_CY_75PCT_CURRENT_CY"
)


def load_bea_rows(
    path: Path,
) -> list[dict]:

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

    if not isinstance(
        rows,
        list,
    ):
        raise RuntimeError(
            f"Results.Data is not a list: "
            f"{path}"
        )

    return rows


def decimal_bea_value(
    row: dict,
) -> Decimal:

    text = (
        str(row["DataValue"])
        .replace(",", "")
        .strip()
    )

    if text in {
        "",
        "(NA)",
        "--",
    }:
        raise RuntimeError(
            f"Non-numeric BEA value: {row}"
        )

    return Decimal(text)


def index_bea_rows(
    rows: list[dict],
) -> dict[
    tuple[int, str],
    dict,
]:

    indexed = {}

    for row in rows:

        key = (
            int(row["TimePeriod"]),
            row["GeoFips"],
        )

        if key in indexed:
            raise RuntimeError(
                f"Duplicate BEA "
                f"year/geography: {key}"
            )

        indexed[key] = row

    return indexed


def load_controls() -> dict[
    int,
    dict,
]:

    result = {}

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                CONTROL_SQL
            )

            rows = cur.fetchall()

            columns = [
                desc.name
                for desc in cur.description
            ]

    if len(rows) != 10:
        raise RuntimeError(
            "Expected 10 Washington "
            "wage-control rows; got "
            f"{len(rows)}."
        )

    for raw_row in rows:

        row = dict(
            zip(
                columns,
                raw_row,
            )
        )

        year = row["fiscal_year"]

        if year in result:
            raise RuntimeError(
                f"Duplicate control year: "
                f"{year}"
            )

        result[year] = row

    expected = set(
        range(
            2015,
            2025,
        )
    )

    if set(result) != expected:
        raise RuntimeError(
            "Washington control years "
            "are incomplete."
        )

    return result


def validate_bea_panel(
    family: str,
    indexed: dict,
) -> None:

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
                "WA state total missing."
            )

        county_keys = [
            key
            for key in indexed
            if (
                key[0] == year
                and key[1].startswith(
                    "53"
                )
                and key[1] != "53000"
            )
        ]

        if len(county_keys) != 39:
            raise RuntimeError(
                f"{family} {year}: "
                f"expected 39 counties; "
                f"got {len(county_keys)}."
            )

        county_sum = sum(
            (
                decimal_bea_value(
                    indexed[key]
                )
                for key in county_keys
            ),
            Decimal("0"),
        )

        state_total = (
            decimal_bea_value(
                indexed[state_key]
            )
        )

        if (
            county_sum
            != state_total
        ):
            raise RuntimeError(
                f"{family} {year}: "
                f"county sum "
                f"{county_sum} != "
                f"state total "
                f"{state_total}."
            )


def allocate_cents_exactly(
    control_dollars: Decimal,
    shares: dict[
        str,
        Decimal,
    ],
) -> dict[
    str,
    Decimal,
]:

    control_cents = (
        control_dollars
        * Decimal("100")
    )

    if (
        control_cents
        != control_cents.to_integral_value()
    ):
        raise RuntimeError(
            "Control amount has "
            "sub-cent precision: "
            f"{control_dollars}"
        )

    target_cents = int(
        control_cents
    )

    floors = {}
    remainders = {}

    for geo_fips, share in (
        shares.items()
    ):

        exact_cents = (
            Decimal(
                target_cents
            )
            * share
        )

        floor_cents = int(
            exact_cents.to_integral_value(
                rounding=ROUND_FLOOR
            )
        )

        floors[geo_fips] = (
            floor_cents
        )

        remainders[geo_fips] = (
            exact_cents
            - Decimal(
                floor_cents
            )
        )

    residual = (
        target_cents
        - sum(
            floors.values()
        )
    )

    if (
        residual < 0
        or residual > len(shares)
    ):
        raise RuntimeError(
            "Unexpected cent residual: "
            f"{residual}"
        )

    ranked = sorted(
        shares,
        key=lambda geo:
            (
                -remainders[geo],
                geo,
            ),
    )

    for geo_fips in (
        ranked[:residual]
    ):
        floors[geo_fips] += 1

    if (
        sum(floors.values())
        != target_cents
    ):
        raise RuntimeError(
            "Exact-cent allocation "
            "failed reconciliation."
        )

    return {
        geo_fips:
            (
                Decimal(cents)
                / Decimal("100")
            )
        for geo_fips, cents
        in floors.items()
    }


def main() -> None:

    EVIDENCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    controls = load_controls()

    long_rows = []
    reconciliation_rows = []

    # Used later to construct one
    # civilian+military row per county/year.
    wide_index = {}

    for family, paths in (
        FILES.items()
    ):

        print()
        print("=" * 78)
        print(family)
        print("=" * 78)

        rows = (
            load_bea_rows(
                paths["2014"]
            )
            + load_bea_rows(
                paths["2015_2024"]
            )
        )

        indexed = index_bea_rows(
            rows
        )

        validate_bea_panel(
            family,
            indexed,
        )

        for fiscal_year in range(
            2015,
            2025,
        ):

            prior_year = (
                fiscal_year - 1
            )

            current_state = (
                decimal_bea_value(
                    indexed[
                        (
                            fiscal_year,
                            "53000",
                        )
                    ]
                )
            )

            prior_state = (
                decimal_bea_value(
                    indexed[
                        (
                            prior_year,
                            "53000",
                        )
                    ]
                )
            )

            ffy_proxy_state = (
                Decimal("0.25")
                * prior_state
                + Decimal("0.75")
                * current_state
            )

            county_keys = sorted(
                key
                for key in indexed
                if (
                    key[0]
                    == fiscal_year
                    and key[1].startswith(
                        "53"
                    )
                    and key[1]
                    != "53000"
                )
            )

            shares = {}
            county_metadata = {}

            for key in county_keys:

                geo_fips = key[1]

                current_row = indexed[
                    (
                        fiscal_year,
                        geo_fips,
                    )
                ]

                prior_row = indexed[
                    (
                        prior_year,
                        geo_fips,
                    )
                ]

                current_value = (
                    decimal_bea_value(
                        current_row
                    )
                )

                prior_value = (
                    decimal_bea_value(
                        prior_row
                    )
                )

                ffy_proxy_value = (
                    Decimal("0.25")
                    * prior_value
                    + Decimal("0.75")
                    * current_value
                )

                share = (
                    ffy_proxy_value
                    / ffy_proxy_state
                )

                shares[
                    geo_fips
                ] = share

                county_metadata[
                    geo_fips
                ] = {
                    "geo_name":
                        current_row[
                            "GeoName"
                        ],

                    "prior_cy_compensation_thousands":
                        prior_value,

                    "current_cy_compensation_thousands":
                        current_value,

                    "ffy_proxy_compensation_thousands":
                        ffy_proxy_value,
                }

            share_sum = sum(
                shares.values(),
                Decimal("0"),
            )

            share_error = abs(
                share_sum
                - Decimal("1")
            )

            if (
                share_error
                > Decimal(
                    "0.000000000001"
                )
            ):
                raise RuntimeError(
                    f"{family} "
                    f"{fiscal_year}: "
                    f"county shares sum to "
                    f"{share_sum}"
                )

            control = (
                controls[
                    fiscal_year
                ]
            )

            if (
                family
                == "FEDERAL_CIVILIAN"
            ):

                control_dollars = (
                    Decimal(
                        control[
                            "allocated_wa_"
                            "civilian_wage_"
                            "dollars"
                        ]
                    )
                )

                confidence = (
                    control[
                        "civilian_"
                        "allocation_"
                        "confidence"
                    ]
                )

                state_methodology = (
                    control[
                        "civilian_"
                        "methodology_"
                        "version"
                    ]
                )

            elif (
                family
                == "MILITARY"
            ):

                control_dollars = (
                    Decimal(
                        control[
                            "allocated_wa_"
                            "military_wage_"
                            "dollars"
                        ]
                    )
                )

                confidence = (
                    control[
                        "military_"
                        "allocation_"
                        "confidence"
                    ]
                )

                state_methodology = (
                    control[
                        "military_"
                        "methodology_"
                        "version"
                    ]
                )

            else:
                raise RuntimeError(
                    f"Unexpected family: "
                    f"{family}"
                )

            allocations = (
                allocate_cents_exactly(
                    control_dollars,
                    shares,
                )
            )

            allocated_sum = sum(
                allocations.values(),
                Decimal("0"),
            )

            residual = (
                allocated_sum
                - control_dollars
            )

            if residual != 0:
                raise RuntimeError(
                    f"{family} "
                    f"{fiscal_year}: "
                    "county allocations "
                    "do not reconcile "
                    f"to WA control: "
                    f"{residual}"
                )

            for geo_fips in sorted(
                shares
            ):

                meta = (
                    county_metadata[
                        geo_fips
                    ]
                )

                allocation = (
                    allocations[
                        geo_fips
                    ]
                )

                row = {
                    "fiscal_year":
                        fiscal_year,

                    "wage_family":
                        family,

                    "county_fips":
                        geo_fips,

                    "county_name":
                        meta[
                            "geo_name"
                        ],

                    "wa_control_dollars":
                        control_dollars,

                    "prior_calendar_year":
                        prior_year,

                    "current_calendar_year":
                        fiscal_year,

                    "prior_cy_bea_compensation_thousands":
                        meta[
                            "prior_cy_compensation_thousands"
                        ],

                    "current_cy_bea_compensation_thousands":
                        meta[
                            "current_cy_compensation_thousands"
                        ],

                    "ffy_proxy_bea_compensation_thousands":
                        meta[
                            "ffy_proxy_compensation_thousands"
                        ],

                    "ffy_aligned_county_share":
                        shares[
                            geo_fips
                        ],

                    "allocated_county_wage_dollars":
                        allocation,

                    "state_allocation_confidence":
                        confidence,

                    "state_methodology_version":
                        state_methodology,

                    "county_allocation_method":
                        METHOD,

                    "prior_year_weight":
                        Decimal("0.25"),

                    "current_year_weight":
                        Decimal("0.75"),
                }

                long_rows.append(
                    row
                )

                wide_key = (
                    fiscal_year,
                    geo_fips,
                )

                if (
                    wide_key
                    not in wide_index
                ):
                    wide_index[
                        wide_key
                    ] = {
                        "fiscal_year":
                            fiscal_year,

                        "county_fips":
                            geo_fips,

                        "county_name":
                            meta[
                                "geo_name"
                            ],
                    }

                if (
                    family
                    == "FEDERAL_CIVILIAN"
                ):
                    wide_index[
                        wide_key
                    ][
                        "civilian_wage_dollars"
                    ] = allocation

                    wide_index[
                        wide_key
                    ][
                        "civilian_county_share"
                    ] = shares[
                        geo_fips
                    ]

                else:
                    wide_index[
                        wide_key
                    ][
                        "military_wage_dollars"
                    ] = allocation

                    wide_index[
                        wide_key
                    ][
                        "military_county_share"
                    ] = shares[
                        geo_fips
                    ]

            reconciliation_rows.append(
                {
                    "fiscal_year":
                        fiscal_year,

                    "wage_family":
                        family,

                    "county_count":
                        len(
                            allocations
                        ),

                    "county_share_sum":
                        share_sum,

                    "wa_control_dollars":
                        control_dollars,

                    "county_allocation_sum_dollars":
                        allocated_sum,

                    "reconciliation_residual_dollars":
                        residual,

                    "state_allocation_confidence":
                        confidence,

                    "state_methodology_version":
                        state_methodology,

                    "county_allocation_method":
                        METHOD,
                }
            )

            print(
                f"{fiscal_year}: "
                f"counties="
                f"{len(allocations)}  "
                f"control="
                f"${control_dollars:,.2f}  "
                f"allocated="
                f"${allocated_sum:,.2f}  "
                f"residual="
                f"${residual:,.2f}"
            )

    if len(long_rows) != 780:
        raise RuntimeError(
            "Expected 780 long-format "
            f"county allocations; got "
            f"{len(long_rows)}."
        )

    if (
        len(reconciliation_rows)
        != 20
    ):
        raise RuntimeError(
            "Expected 20 reconciliation "
            f"rows; got "
            f"{len(reconciliation_rows)}."
        )

    wide_rows = []

    for key in sorted(
        wide_index
    ):

        row = (
            wide_index[
                key
            ]
        )

        if (
            "civilian_wage_dollars"
            not in row
            or "military_wage_dollars"
            not in row
        ):
            raise RuntimeError(
                f"Incomplete combined "
                f"county row: {key}"
            )

        row[
            "total_federal_wage_dollars"
        ] = (
            row[
                "civilian_wage_dollars"
            ]
            + row[
                "military_wage_dollars"
            ]
        )

        wide_rows.append(
            row
        )

    if len(wide_rows) != 390:
        raise RuntimeError(
            "Expected 390 combined "
            f"county-year rows; got "
            f"{len(wide_rows)}."
        )

    long_path = (
        EVIDENCE_DIR
        / (
            "wa_county_federal_"
            "wage_allocation_long.csv"
        )
    )

    wide_path = (
        EVIDENCE_DIR
        / (
            "wa_county_federal_"
            "wage_allocation_combined.csv"
        )
    )

    reconciliation_path = (
        EVIDENCE_DIR
        / (
            "wa_county_federal_"
            "wage_allocation_"
            "reconciliation.csv"
        )
    )

    with long_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=(
                long_rows[
                    0
                ].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(
            long_rows
        )

    with wide_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=(
                wide_rows[
                    0
                ].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(
            wide_rows
        )

    with reconciliation_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=(
                reconciliation_rows[
                    0
                ].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(
            reconciliation_rows
        )

    print()
    print("=" * 78)
    print(
        "WASHINGTON COUNTY FEDERAL "
        "WAGE ALLOCATION COMPLETE"
    )
    print("=" * 78)

    print(
        f"Long allocation rows: "
        f"{len(long_rows)}"
    )

    print(
        f"Combined county-year rows: "
        f"{len(wide_rows)}"
    )

    print(
        f"Reconciliation rows: "
        f"{len(reconciliation_rows)}"
    )

    print(
        f"Long: {long_path}"
    )

    print(
        f"Combined: {wide_path}"
    )

    print(
        "Reconciliation: "
        f"{reconciliation_path}"
    )


if __name__ == "__main__":
    main()