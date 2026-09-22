from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = (
    ROOT
    / "data"
    / "raw"
    / "opm"
    / "fedscope"
    / "employment"
    / "2016-09"
)

OUTPUT_DIR = (
    ROOT
    / "data"
    / "interim"
    / "opm"
)

OMB_NONMILITARY_FY2016 = 156_145_000_000


def find_latest_zip() -> Path:
    matches = sorted(
        SOURCE_DIR.glob(
            "opm_fedscope_employment_201609_"
            "raw_data_retrieved_*.zip"
        )
    )

    if not matches:
        raise RuntimeError(
            f"No FY2016 FedScope ZIP found under {SOURCE_DIR}"
        )

    return matches[-1]


def open_text_member(
    zf: zipfile.ZipFile,
    name: str,
):
    raw = zf.open(name, "r")

    return io.TextIOWrapper(
        raw,
        encoding="utf-8-sig",
        newline="",
    )


def read_locations(
    zf: zipfile.ZipFile,
) -> dict[str, dict[str, str]]:

    with open_text_member(
        zf,
        "DTloc.txt",
    ) as f:

        return {
            row["LOC"].strip(): row
            for row in csv.DictReader(f)
        }


def numeric_int(
    value: str,
    field: str,
    row_number: int,
) -> int:

    text = str(value).strip()

    if not text:
        return 0

    try:
        return int(float(text))

    except ValueError as exc:
        raise RuntimeError(
            f"Invalid {field} "
            f"at row {row_number}: "
            f"{value!r}"
        ) from exc


def main() -> None:

    source = find_latest_zip()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 84)
    print(
        "OPM FY2016 CIVILIAN WAGE "
        "GEOGRAPHIC DENOMINATOR DIAGNOSTIC"
    )
    print("=" * 84)

    print(f"Source: {source}")
    print()

    numerators = {
        "wa_employment": 0,
        "wa_salary_mass": 0,
    }

    denominators = {
        "STATES_DC": {
            "employment": 0,
            "salary_mass": 0,
        },
        "STATES_DC_TERRITORIES": {
            "employment": 0,
            "salary_mass": 0,
        },
        "ALL_LOCATIONS": {
            "employment": 0,
            "salary_mass": 0,
        },
    }

    location_type_totals = {}

    with zipfile.ZipFile(
        source,
        "r",
    ) as zf:

        locations = read_locations(zf)

        with open_text_member(
            zf,
            "FACTDATA_SEP2016.TXT",
        ) as f:

            reader = csv.DictReader(f)

            for row_number, row in enumerate(
                reader,
                start=2,
            ):

                # Rockefeller-compatible candidate population:
                # OPM Non-Seasonal Full Time Permanent.
                if (
                    row["WORKSTAT"]
                    .strip()
                    != "1"
                ):
                    continue

                employment = numeric_int(
                    row["EMPLOYMENT"],
                    "EMPLOYMENT",
                    row_number,
                )

                salary = numeric_int(
                    row["SALARY"],
                    "SALARY",
                    row_number,
                )

                salary_mass = (
                    employment
                    * salary
                )

                loc = (
                    row["LOC"]
                    .strip()
                )

                loc_row = (
                    locations.get(loc)
                )

                if loc_row:
                    loc_type = (
                        loc_row
                        .get(
                            "LOCTYPT",
                            "UNKNOWN",
                        )
                        .strip()
                    )
                else:
                    loc_type = "UNMAPPED"

                if (
                    loc_type
                    not in location_type_totals
                ):
                    location_type_totals[
                        loc_type
                    ] = {
                        "employment": 0,
                        "salary_mass": 0,
                    }

                location_type_totals[
                    loc_type
                ][
                    "employment"
                ] += employment

                location_type_totals[
                    loc_type
                ][
                    "salary_mass"
                ] += salary_mass

                # Denominator 3:
                # complete OPM universe.
                denominators[
                    "ALL_LOCATIONS"
                ][
                    "employment"
                ] += employment

                denominators[
                    "ALL_LOCATIONS"
                ][
                    "salary_mass"
                ] += salary_mass

                # OPM's United States location class:
                # states/DC in our current reconstruction.
                if (
                    loc_type.upper()
                    == "UNITED STATES"
                ):

                    denominators[
                        "STATES_DC"
                    ][
                        "employment"
                    ] += employment

                    denominators[
                        "STATES_DC"
                    ][
                        "salary_mass"
                    ] += salary_mass

                    denominators[
                        "STATES_DC_TERRITORIES"
                    ][
                        "employment"
                    ] += employment

                    denominators[
                        "STATES_DC_TERRITORIES"
                    ][
                        "salary_mass"
                    ] += salary_mass

                elif (
                    loc_type.upper()
                    == "U.S. TERRITORIES"
                ):

                    denominators[
                        "STATES_DC_TERRITORIES"
                    ][
                        "employment"
                    ] += employment

                    denominators[
                        "STATES_DC_TERRITORIES"
                    ][
                        "salary_mass"
                    ] += salary_mass

                # Washington numerator is invariant.
                if loc == "53":

                    numerators[
                        "wa_employment"
                    ] += employment

                    numerators[
                        "wa_salary_mass"
                    ] += salary_mass

    print("WORKSTAT=1 LOCATION-TYPE TOTALS")
    print("-" * 84)

    for loc_type in sorted(
        location_type_totals
    ):

        m = location_type_totals[
            loc_type
        ]

        print(
            f"{loc_type:25s} "
            f"employment={m['employment']:10,d}  "
            f"salary_mass=${m['salary_mass']:16,d}"
        )

    print()
    print("WASHINGTON NUMERATOR")
    print("-" * 84)

    print(
        f"WA employment: "
        f"{numerators['wa_employment']:,}"
    )

    print(
        f"WA salary mass: "
        f"${numerators['wa_salary_mass']:,}"
    )

    print()
    print("DENOMINATOR COMPARISON")
    print("-" * 84)

    header = (
        f"{'DENOMINATOR':28s}"
        f"{'DENOM EMP':>12s}"
        f"{'WA EMP %':>11s}"
        f"{'DENOM SALARY MASS':>21s}"
        f"{'WA SAL %':>11s}"
        f"{'OMB->WA $B':>13s}"
    )

    print(header)
    print("-" * len(header))

    output_rows = []

    for name in (
        "STATES_DC",
        "STATES_DC_TERRITORIES",
        "ALL_LOCATIONS",
    ):

        m = denominators[name]

        employment_share = (
            numerators[
                "wa_employment"
            ]
            / m["employment"]
        )

        salary_share = (
            numerators[
                "wa_salary_mass"
            ]
            / m["salary_mass"]
        )

        allocated = (
            OMB_NONMILITARY_FY2016
            * salary_share
        )

        print(
            f"{name:28s}"
            f"{m['employment']:12,d}"
            f"{employment_share * 100:10.4f}%"
            f"{m['salary_mass']:21,d}"
            f"{salary_share * 100:10.4f}%"
            f"{allocated / 1e9:12.3f}"
        )

        output_rows.append(
            {
                "fiscal_year": 2016,
                "population":
                    "WORKSTAT_1",
                "denominator":
                    name,
                "denominator_employment":
                    m["employment"],
                "wa_employment":
                    numerators[
                        "wa_employment"
                    ],
                "wa_employment_share":
                    employment_share,
                "denominator_salary_mass":
                    m["salary_mass"],
                "wa_salary_mass":
                    numerators[
                        "wa_salary_mass"
                    ],
                "wa_salary_share":
                    salary_share,
                "omb_nonmilitary_control_dollars":
                    OMB_NONMILITARY_FY2016,
                "omb_allocated_wa_dollars":
                    round(allocated),
            }
        )

    output_path = (
        OUTPUT_DIR
        / (
            "opm_fedscope_fy2016_"
            "geographic_denominator_"
            "diagnostic.csv"
        )
    )

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(
                output_rows[0].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(
            output_rows
        )

    print()
    print("=" * 84)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 84)
    print(
        f"Output: {output_path}"
    )


if __name__ == "__main__":
    main()