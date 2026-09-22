from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
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
    member_name: str,
):
    raw = zf.open(member_name, "r")

    return io.TextIOWrapper(
        raw,
        encoding="utf-8-sig",
        newline="",
    )


def read_location_lookup(
    zf: zipfile.ZipFile,
) -> dict[str, dict[str, str]]:

    with open_text_member(
        zf,
        "DTloc.txt",
    ) as f:
        reader = csv.DictReader(f)

        return {
            row["LOC"]: row
            for row in reader
        }


def read_agency_lookup(
    zf: zipfile.ZipFile,
) -> dict[str, dict[str, str]]:

    with open_text_member(
        zf,
        "DTagy.txt",
    ) as f:
        reader = csv.DictReader(f)

        return {
            row["AGYSUB"]: row
            for row in reader
        }


def is_us_state_or_dc(
    loc_row: dict[str, str] | None,
) -> bool:
    """
    Initial domestic state/DC denominator.

    OPM DTloc classifies locations using LOCTYP/LOCTYPT.
    For this first diagnostic we include only rows whose
    location type is 'United States'.

    We will separately inspect whether territories or other
    special locations require inclusion in the final
    Rockefeller-compatible denominator.
    """

    if not loc_row:
        return False

    return (
        loc_row.get("LOCTYPT", "")
        .strip()
        .upper()
        == "UNITED STATES"
    )


def is_washington(
    loc: str,
    loc_row: dict[str, str] | None,
) -> bool:

    if loc == "53":
        return True

    if not loc_row:
        return False

    text = (
        loc_row.get("LOCT", "")
        .strip()
        .upper()
    )

    return "WASHINGTON" in text


def population_flags(
    row: dict[str, str],
) -> dict[str, bool]:

    workstat = (
        row.get("WORKSTAT", "")
        .strip()
    )

    worksch = (
        row.get("WORKSCH", "")
        .strip()
        .upper()
    )

    return {
        "ALL": True,
        "WORKSTAT_1": (
            workstat == "1"
        ),
        "WORKSCH_F": (
            worksch == "F"
        ),
        "WORKSTAT_1_AND_WORKSCH_F": (
            workstat == "1"
            and worksch == "F"
        ),
    }


def numeric_int(
    value: str,
    field_name: str,
    row_number: int,
) -> int:

    text = str(value).strip()

    if not text:
        return 0

    try:
        return int(float(text))
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid {field_name} "
            f"at FACTDATA row {row_number}: "
            f"{value!r}"
        ) from exc


def main() -> None:

    source = find_latest_zip()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 80)
    print(
        "OPM FEDSCOPE FY2016 CIVILIAN WAGE "
        "ALLOCATION DIAGNOSTIC"
    )
    print("=" * 80)
    print(f"Source: {source}")
    print()

    metrics = defaultdict(
        lambda: {
            "us_employment": 0,
            "wa_employment": 0,
            "us_salary_mass": 0,
            "wa_salary_mass": 0,
        }
    )

    excluded_location_counts = defaultdict(int)
    excluded_location_employment = defaultdict(int)

    postal_agencies: dict[
        str,
        dict[str, str],
    ] = {}

    postal = {
        "all_employment": 0,
        "all_salary_mass": 0,
        "wa_employment": 0,
        "wa_salary_mass": 0,
    }

    with zipfile.ZipFile(
        source,
        "r",
    ) as zf:

        locations = read_location_lookup(zf)
        agencies = read_agency_lookup(zf)

        print("LOCATION LOOKUP")
        print("-" * 80)
        print(
            f"Location codes: "
            f"{len(locations):,}"
        )

        wa_lookup = locations.get("53")

        print(
            "Washington LOC=53: "
            f"{wa_lookup}"
        )
        print()

        print("POSTAL AGENCY LOOKUP SEARCH")
        print("-" * 80)

        for code, row in agencies.items():

            searchable = " ".join(
                [
                    row.get(
                        "AGYT", ""
                    ),
                    row.get(
                        "AGYSUBT", ""
                    ),
                ]
            ).upper()

            if (
                "POSTAL" in searchable
                or "USPS" in searchable
            ):
                postal_agencies[
                    code
                ] = row

                print(
                    f"{code}: "
                    f"{row.get('AGYT', '')} | "
                    f"{row.get('AGYSUBT', '')}"
                )

        if not postal_agencies:
            print(
                "No agency/subagency containing "
                "'POSTAL' or 'USPS' found."
            )

        print()

        fact_name = (
            "FACTDATA_SEP2016.TXT"
        )

        with open_text_member(
            zf,
            fact_name,
        ) as f:

            reader = csv.DictReader(f)

            required_fields = {
                "AGYSUB",
                "LOC",
                "WORKSCH",
                "WORKSTAT",
                "EMPLOYMENT",
                "SALARY",
                "DATECODE",
            }

            missing = (
                required_fields
                - set(
                    reader.fieldnames
                    or []
                )
            )

            if missing:
                raise RuntimeError(
                    "FACTDATA missing fields: "
                    f"{sorted(missing)}"
                )

            row_count = 0
            total_employment = 0

            for row_number, row in enumerate(
                reader,
                start=2,
            ):

                row_count += 1

                datecode = (
                    row["DATECODE"]
                    .strip()
                )

                if datecode != "201609":
                    raise RuntimeError(
                        "Unexpected DATECODE "
                        f"{datecode!r} "
                        f"at row {row_number}"
                    )

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

                total_employment += employment

                loc = (
                    row["LOC"]
                    .strip()
                )

                loc_row = (
                    locations.get(loc)
                )

                domestic = (
                    is_us_state_or_dc(
                        loc_row
                    )
                )

                wa = (
                    is_washington(
                        loc,
                        loc_row,
                    )
                )

                if not domestic:

                    loc_type = (
                        loc_row.get(
                            "LOCTYPT",
                            "UNKNOWN",
                        )
                        if loc_row
                        else "UNMAPPED"
                    )

                    excluded_location_counts[
                        loc_type
                    ] += 1

                    excluded_location_employment[
                        loc_type
                    ] += employment

                if domestic:

                    flags = population_flags(
                        row
                    )

                    for (
                        population,
                        include,
                    ) in flags.items():

                        if not include:
                            continue

                        metrics[
                            population
                        ][
                            "us_employment"
                        ] += employment

                        metrics[
                            population
                        ][
                            "us_salary_mass"
                        ] += salary_mass

                        if wa:

                            metrics[
                                population
                            ][
                                "wa_employment"
                            ] += employment

                            metrics[
                                population
                            ][
                                "wa_salary_mass"
                            ] += salary_mass

                agysub = (
                    row["AGYSUB"]
                    .strip()
                )

                if (
                    agysub
                    in postal_agencies
                ):

                    postal[
                        "all_employment"
                    ] += employment

                    postal[
                        "all_salary_mass"
                    ] += salary_mass

                    if wa:

                        postal[
                            "wa_employment"
                        ] += employment

                        postal[
                            "wa_salary_mass"
                        ] += salary_mass

    print("FACT TABLE")
    print("-" * 80)
    print(
        f"Rows read: "
        f"{row_count:,}"
    )
    print(
        f"Total employment represented: "
        f"{total_employment:,}"
    )
    print()

    print("ALLOCATION DIAGNOSTIC")
    print("-" * 80)

    header = (
        f"{'POPULATION':32s}"
        f"{'US EMP':>12s}"
        f"{'WA EMP':>10s}"
        f"{'EMP %':>10s}"
        f"{'US SALARY MASS':>20s}"
        f"{'WA SALARY MASS':>18s}"
        f"{'SALARY %':>11s}"
        f"{'OMB->WA $B':>13s}"
    )

    print(header)
    print("-" * len(header))

    output_rows = []

    population_order = [
        "ALL",
        "WORKSTAT_1",
        "WORKSCH_F",
        "WORKSTAT_1_AND_WORKSCH_F",
    ]

    for population in population_order:

        m = metrics[
            population
        ]

        us_emp = (
            m["us_employment"]
        )

        wa_emp = (
            m["wa_employment"]
        )

        us_salary_mass = (
            m["us_salary_mass"]
        )

        wa_salary_mass = (
            m["wa_salary_mass"]
        )

        employment_share = (
            wa_emp / us_emp
            if us_emp
            else 0.0
        )

        salary_share = (
            wa_salary_mass
            / us_salary_mass
            if us_salary_mass
            else 0.0
        )

        allocated = (
            OMB_NONMILITARY_FY2016
            * salary_share
        )

        print(
            f"{population:32s}"
            f"{us_emp:12,d}"
            f"{wa_emp:10,d}"
            f"{employment_share * 100:9.4f}%"
            f"{us_salary_mass:20,d}"
            f"{wa_salary_mass:18,d}"
            f"{salary_share * 100:10.4f}%"
            f"{allocated / 1e9:12.3f}"
        )

        output_rows.append(
            {
                "population":
                    population,
                "us_employment":
                    us_emp,
                "wa_employment":
                    wa_emp,
                "wa_employment_share":
                    employment_share,
                "us_salary_mass":
                    us_salary_mass,
                "wa_salary_mass":
                    wa_salary_mass,
                "wa_salary_share":
                    salary_share,
                "omb_nonmilitary_control_dollars":
                    OMB_NONMILITARY_FY2016,
                "omb_allocated_wa_dollars":
                    round(allocated),
            }
        )

    print()
    print("POSTAL DIAGNOSTIC")
    print("-" * 80)

    print(
        f"Postal agency codes found: "
        f"{len(postal_agencies)}"
    )

    print(
        f"Postal employment: "
        f"{postal['all_employment']:,}"
    )

    print(
        f"Postal salary mass: "
        f"${postal['all_salary_mass']:,}"
    )

    print(
        f"WA postal employment: "
        f"{postal['wa_employment']:,}"
    )

    print(
        f"WA postal salary mass: "
        f"${postal['wa_salary_mass']:,}"
    )

    print()
    print("EXCLUDED LOCATION TYPES")
    print("-" * 80)

    if not excluded_location_counts:

        print(
            "None."
        )

    else:

        for loc_type in sorted(
            excluded_location_counts
        ):

            print(
                f"{loc_type}: "
                f"{excluded_location_counts[loc_type]:,} "
                f"fact rows; "
                f"{excluded_location_employment[loc_type]:,} "
                f"employment"
            )

    output_path = (
        OUTPUT_DIR
        / (
            "opm_fedscope_fy2016_"
            "civilian_allocation_diagnostic.csv"
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
    print("=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)
    print(
        f"Output: {output_path}"
    )


if __name__ == "__main__":
    main()