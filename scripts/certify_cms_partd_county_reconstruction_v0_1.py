#!/usr/bin/env python3
"""
CMS Medicare Part D county reconstruction certification v0.1.

READ-ONLY downstream certification of the frozen CMS Part D payment
reconstruction v0.3 artifacts.

This script DOES NOT:
  * reconstruct PMPM values,
  * impute suppressed/non-numeric enrollment,
  * assign dollars to no-exact-payment-match enrollment,
  * modify source artifacts,
  * write to the database, or
  * authorize ledger inclusion.

It certifies the county geography and county aggregation of dollars already
reconstructed by v0.3.

Certified upstream boundary retained:
  * Washington CPSC enrollment.
  * Exact same-year Contract + PBP PartDPlans payment match only.
  * No-exact-payment-match enrollment receives no reconstructed dollars.
  * Suppressed/non-numeric enrollment is not imputed.
  * CY2024 is Jan-Sep only.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path

getcontext().prec = 40

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE_DIR = (
    ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_partd"
    / "validation"
    / "partd_payment_reconstruction_v0_3"
)

DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_partd"
    / "validation"
    / "partd_county_reconstruction_v0_1"
)

DETAIL_NAME = "cms_partd_payment_reconstruction_detail_v0_3.csv"
MONTHLY_NAME = "cms_partd_payment_reconstruction_monthly_v0_3.csv"
ANNUAL_NAME = "cms_partd_payment_reconstruction_annual_v0_3.csv"

EXPECTED_YEARS = tuple(range(2015, 2025))

EXPECTED_MONTHS = {
    year: tuple(range(1, 10)) if year == 2024 else tuple(range(1, 13))
    for year in EXPECTED_YEARS
}

# Canonical Washington county-name -> Census county FIPS.
WA_COUNTIES = {
    "Adams": "53001",
    "Asotin": "53003",
    "Benton": "53005",
    "Chelan": "53007",
    "Clallam": "53009",
    "Clark": "53011",
    "Columbia": "53013",
    "Cowlitz": "53015",
    "Douglas": "53017",
    "Ferry": "53019",
    "Franklin": "53021",
    "Garfield": "53023",
    "Grant": "53025",
    "Grays Harbor": "53027",
    "Island": "53029",
    "Jefferson": "53031",
    "King": "53033",
    "Kitsap": "53035",
    "Kittitas": "53037",
    "Klickitat": "53039",
    "Lewis": "53041",
    "Lincoln": "53043",
    "Mason": "53045",
    "Okanogan": "53047",
    "Pacific": "53049",
    "Pend Oreille": "53051",
    "Pierce": "53053",
    "San Juan": "53055",
    "Skagit": "53057",
    "Skamania": "53059",
    "Snohomish": "53061",
    "Spokane": "53063",
    "Stevens": "53065",
    "Thurston": "53067",
    "Wahkiakum": "53069",
    "Walla Walla": "53071",
    "Whatcom": "53073",
    "Whitman": "53075",
    "Yakima": "53077",
}

REQUIRED_DETAIL = {
    "year",
    "month",
    "contract",
    "pbp",
    "county",
    "numeric_enrollment",
    "direct_subsidy_ra_pmpm",
    "reinsurance_pmpm",
    "lics_pmpm",
    "total_partd_pmpm",
    "direct_subsidy_ra_dollars",
    "reinsurance_dollars",
    "lics_dollars",
    "total_partd_dollars",
}

REQUIRED_MONTHLY = {
    "year",
    "month",
    "reconstructed_numeric_enrollment",
    "direct_subsidy_ra_dollars",
    "reinsurance_dollars",
    "lics_dollars",
    "total_partd_dollars",
}

REQUIRED_ANNUAL = {
    "year",
    "coverage",
    "reconstructed_numeric_enrollment",
    "direct_subsidy_ra_dollars",
    "reinsurance_dollars",
    "lics_dollars",
    "total_partd_dollars",
}

ZERO = Decimal("0")

# The detail identities should reproduce essentially exactly.  The tolerance
# protects only against harmless decimal serialization differences.
IDENTITY_TOL = Decimal("0.000001")

# Monthly/annual reconciliation is a dollar accounting check.  One cent is
# deliberately much tighter than any material ledger threshold.
RECON_TOL = Decimal("0.01")


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def dec(value: object, label: str) -> Decimal:
    s = clean(value).replace(",", "")
    if s == "":
        raise ValueError(f"Blank numeric value for {label}")

    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(
            f"Invalid Decimal for {label}: {value!r}"
        ) from exc


def integer(value: object, label: str) -> int:
    s = clean(value).replace(",", "")

    try:
        return int(s)
    except ValueError as exc:
        raise ValueError(
            f"Invalid integer for {label}: {value!r}"
        ) from exc


def read_rows(
    path: Path,
    required: set[str],
) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as fh:
        reader = csv.DictReader(fh)

        fields = set(reader.fieldnames or [])
        missing = sorted(required - fields)

        if missing:
            raise ValueError(
                f"{path.name} missing required columns: "
                + ", ".join(missing)
            )

        return list(reader)


def write_csv(
    path: Path,
    rows: list[dict],
    fields: list[str],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)


def money(value: Decimal) -> str:
    return f"{value:,.2f}"


def yesno(value: bool) -> str:
    return "PASS" if value else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    detail_path = source_dir / DETAIL_NAME
    monthly_path = source_dir / MONTHLY_NAME
    annual_path = source_dir / ANNUAL_NAME

    detail = read_rows(
        detail_path,
        REQUIRED_DETAIL,
    )

    monthly = read_rows(
        monthly_path,
        REQUIRED_MONTHLY,
    )

    annual = read_rows(
        annual_path,
        REQUIRED_ANNUAL,
    )

    checks: list[dict[str, str]] = []

    def check(
        name: str,
        passed: bool,
        evidence: str,
    ) -> None:
        checks.append(
            {
                "check": name,
                "status": yesno(passed),
                "evidence": evidence,
            }
        )

    # ------------------------------------------------------------------
    # Frozen upstream annual controls
    # ------------------------------------------------------------------

    annual_by_year: dict[int, dict[str, str]] = {}

    for row in annual:
        year = integer(
            row["year"],
            "annual.year",
        )

        if year in annual_by_year:
            raise ValueError(
                f"Duplicate annual control for CY{year}"
            )

        annual_by_year[year] = row

    # ------------------------------------------------------------------
    # Frozen upstream monthly controls
    # ------------------------------------------------------------------

    monthly_by_period: dict[
        tuple[int, int],
        dict[str, str],
    ] = {}

    for row in monthly:
        year = integer(
            row["year"],
            "monthly.year",
        )

        month = integer(
            row["month"],
            "monthly.month",
        )

        key = (year, month)

        if key in monthly_by_period:
            raise ValueError(
                f"Duplicate monthly control for "
                f"{year}-{month:02d}"
            )

        monthly_by_period[key] = row

    expected_periods = {
        (year, month)
        for year, months in EXPECTED_MONTHS.items()
        for month in months
    }

    actual_periods = set(monthly_by_period)

    check(
        "Annual controls exactly CY2015-CY2024",
        set(annual_by_year) == set(EXPECTED_YEARS),
        f"years={sorted(annual_by_year)}",
    )

    check(
        "Monthly control periods exactly Jan 2015-Sep 2024",
        actual_periods == expected_periods,
        (
            f"periods={len(actual_periods)} "
            f"expected={len(expected_periods)}"
        ),
    )

    # ------------------------------------------------------------------
    # Aggregate the already-reconstructed detail.
    #
    # This section DOES NOT reconstruct payment rates.
    # It merely validates arithmetic already present in v0.3 and
    # aggregates those existing reconstructed dollars by county.
    # ------------------------------------------------------------------

    observed_counties: set[str] = set()
    unknown_counties: set[str] = set()

    blank_county_rows = 0
    detail_periods: set[tuple[int, int]] = set()

    detail_rows = 0
    detail_enrollment = 0

    county_month = defaultdict(
        lambda: {
            "enrollment": 0,
            "direct": ZERO,
            "reinsurance": ZERO,
            "lics": ZERO,
            "total": ZERO,
            "rows": 0,
        }
    )

    county_year = defaultdict(
        lambda: {
            "enrollment": 0,
            "direct": ZERO,
            "reinsurance": ZERO,
            "lics": ZERO,
            "total": ZERO,
            "rows": 0,
            "months": set(),
        }
    )

    state_month = defaultdict(
        lambda: {
            "enrollment": 0,
            "direct": ZERO,
            "reinsurance": ZERO,
            "lics": ZERO,
            "total": ZERO,
        }
    )

    state_year = defaultdict(
        lambda: {
            "enrollment": 0,
            "direct": ZERO,
            "reinsurance": ZERO,
            "lics": ZERO,
            "total": ZERO,
        }
    )

    max_identity_diff = ZERO
    identity_failures = 0
    geography_failures = 0

    for row in detail:
        detail_rows += 1

        year = integer(
            row["year"],
            "detail.year",
        )

        month = integer(
            row["month"],
            "detail.month",
        )

        county = clean(
            row["county"]
        )

        enrollment = integer(
            row["numeric_enrollment"],
            "detail.numeric_enrollment",
        )

        direct_pmpm = dec(
            row["direct_subsidy_ra_pmpm"],
            "direct_subsidy_ra_pmpm",
        )

        reins_pmpm = dec(
            row["reinsurance_pmpm"],
            "reinsurance_pmpm",
        )

        lics_pmpm = dec(
            row["lics_pmpm"],
            "lics_pmpm",
        )

        total_pmpm = dec(
            row["total_partd_pmpm"],
            "total_partd_pmpm",
        )

        direct_d = dec(
            row["direct_subsidy_ra_dollars"],
            "direct_subsidy_ra_dollars",
        )

        reins_d = dec(
            row["reinsurance_dollars"],
            "reinsurance_dollars",
        )

        lics_d = dec(
            row["lics_dollars"],
            "lics_dollars",
        )

        total_d = dec(
            row["total_partd_dollars"],
            "total_partd_dollars",
        )

        # --------------------------------------------------------------
        # Geography
        # --------------------------------------------------------------

        if county == "":
            blank_county_rows += 1
            geography_failures += 1
            continue

        observed_counties.add(county)

        if county not in WA_COUNTIES:
            unknown_counties.add(county)
            geography_failures += 1
            continue

        period = (year, month)
        detail_periods.add(period)

        # --------------------------------------------------------------
        # Reconfirm frozen arithmetic identities.
        #
        # These checks do not change the reconstructed values.
        # --------------------------------------------------------------

        diffs = [
            abs(
                total_pmpm
                - (
                    direct_pmpm
                    + reins_pmpm
                    + lics_pmpm
                )
            ),
            abs(
                direct_d
                - Decimal(enrollment)
                * direct_pmpm
            ),
            abs(
                reins_d
                - Decimal(enrollment)
                * reins_pmpm
            ),
            abs(
                lics_d
                - Decimal(enrollment)
                * lics_pmpm
            ),
            abs(
                total_d
                - Decimal(enrollment)
                * total_pmpm
            ),
            abs(
                total_d
                - (
                    direct_d
                    + reins_d
                    + lics_d
                )
            ),
        ]

        local_max = max(diffs)

        max_identity_diff = max(
            max_identity_diff,
            local_max,
        )

        if local_max > IDENTITY_TOL:
            identity_failures += 1

        detail_enrollment += enrollment

        # --------------------------------------------------------------
        # County-month aggregation
        # --------------------------------------------------------------

        cm = county_month[
            (year, month, county)
        ]

        cm["enrollment"] += enrollment
        cm["direct"] += direct_d
        cm["reinsurance"] += reins_d
        cm["lics"] += lics_d
        cm["total"] += total_d
        cm["rows"] += 1

        # --------------------------------------------------------------
        # County-year aggregation
        # --------------------------------------------------------------

        cy = county_year[
            (year, county)
        ]

        cy["enrollment"] += enrollment
        cy["direct"] += direct_d
        cy["reinsurance"] += reins_d
        cy["lics"] += lics_d
        cy["total"] += total_d
        cy["rows"] += 1
        cy["months"].add(month)

        # --------------------------------------------------------------
        # State-month aggregation
        # --------------------------------------------------------------

        sm = state_month[
            (year, month)
        ]

        sm["enrollment"] += enrollment
        sm["direct"] += direct_d
        sm["reinsurance"] += reins_d
        sm["lics"] += lics_d
        sm["total"] += total_d

        # --------------------------------------------------------------
        # State-year aggregation
        # --------------------------------------------------------------

        sy = state_year[year]

        sy["enrollment"] += enrollment
        sy["direct"] += direct_d
        sy["reinsurance"] += reins_d
        sy["lics"] += lics_d
        sy["total"] += total_d

    # ------------------------------------------------------------------
    # Geography certification
    # ------------------------------------------------------------------

    check(
        "Exactly 39 canonical Washington counties observed",
        observed_counties == set(WA_COUNTIES),
        (
            f"observed={len(observed_counties)}; "
            f"missing="
            f"{sorted(set(WA_COUNTIES) - observed_counties)}; "
            f"extra="
            f"{sorted(observed_counties - set(WA_COUNTIES))}"
        ),
    )

    check(
        "No blank or unrecognized county geography",
        geography_failures == 0,
        (
            f"blank_rows={blank_county_rows}; "
            f"unknown_counties={sorted(unknown_counties)}"
        ),
    )

    check(
        "Detail periods stay within certified Jan 2015-Sep 2024 universe",
        detail_periods <= expected_periods,
        f"detail_periods={len(detail_periods)}",
    )

    check(
        "All reconstructed detail arithmetic identities preserved",
        identity_failures == 0,
        (
            f"detail_rows={detail_rows:,}; "
            f"failures={identity_failures:,}; "
            f"max_abs_difference={max_identity_diff}"
        ),
    )

    # ------------------------------------------------------------------
    # Reconcile county aggregation to frozen MONTHLY v0.3 controls.
    # ------------------------------------------------------------------

    monthly_recon_rows: list[dict] = []

    max_monthly_total_diff = ZERO
    max_monthly_enrollment_diff = 0
    monthly_failures = 0

    for year, month in sorted(expected_periods):
        control = monthly_by_period[
            (year, month)
        ]

        agg = state_month[
            (year, month)
        ]

        diffs = {
            "enrollment":
                agg["enrollment"]
                - integer(
                    control[
                        "reconstructed_numeric_enrollment"
                    ],
                    (
                        "monthly."
                        "reconstructed_numeric_enrollment"
                    ),
                ),

            "direct":
                agg["direct"]
                - dec(
                    control[
                        "direct_subsidy_ra_dollars"
                    ],
                    "monthly.direct",
                ),

            "reinsurance":
                agg["reinsurance"]
                - dec(
                    control[
                        "reinsurance_dollars"
                    ],
                    "monthly.reinsurance",
                ),

            "lics":
                agg["lics"]
                - dec(
                    control["lics_dollars"],
                    "monthly.lics",
                ),

            "total":
                agg["total"]
                - dec(
                    control["total_partd_dollars"],
                    "monthly.total",
                ),
        }

        max_monthly_enrollment_diff = max(
            max_monthly_enrollment_diff,
            abs(diffs["enrollment"]),
        )

        local_money_max = max(
            abs(diffs["direct"]),
            abs(diffs["reinsurance"]),
            abs(diffs["lics"]),
            abs(diffs["total"]),
        )

        max_monthly_total_diff = max(
            max_monthly_total_diff,
            local_money_max,
        )

        passed = (
            diffs["enrollment"] == 0
            and local_money_max <= RECON_TOL
        )

        if not passed:
            monthly_failures += 1

        monthly_recon_rows.append(
            {
                "year": year,
                "month": month,

                "county_sum_reconstructed_enrollment":
                    agg["enrollment"],

                "control_reconstructed_enrollment":
                    integer(
                        control[
                            "reconstructed_numeric_enrollment"
                        ],
                        (
                            "monthly."
                            "reconstructed_numeric_enrollment"
                        ),
                    ),

                "enrollment_difference":
                    diffs["enrollment"],

                "county_sum_total_partd_dollars":
                    str(agg["total"]),

                "control_total_partd_dollars":
                    clean(
                        control[
                            "total_partd_dollars"
                        ]
                    ),

                "total_dollar_difference":
                    str(diffs["total"]),

                "status":
                    yesno(passed),
            }
        )

    check(
        "County sums reconcile to every frozen v0.3 monthly control",
        monthly_failures == 0,
        (
            f"failures={monthly_failures}; "
            f"max_enrollment_difference="
            f"{max_monthly_enrollment_diff}; "
            f"max_component_or_total_dollar_difference="
            f"{max_monthly_total_diff}"
        ),
    )

    # ------------------------------------------------------------------
    # Reconcile county aggregation to frozen ANNUAL v0.3 controls.
    # ------------------------------------------------------------------

    annual_recon_rows: list[dict] = []

    max_annual_total_diff = ZERO
    max_annual_enrollment_diff = 0
    annual_failures = 0

    for year in EXPECTED_YEARS:
        control = annual_by_year[year]
        agg = state_year[year]

        enrollment_diff = (
            agg["enrollment"]
            - integer(
                control[
                    "reconstructed_numeric_enrollment"
                ],
                (
                    "annual."
                    "reconstructed_numeric_enrollment"
                ),
            )
        )

        money_diffs = {
            "direct":
                agg["direct"]
                - dec(
                    control[
                        "direct_subsidy_ra_dollars"
                    ],
                    "annual.direct",
                ),

            "reinsurance":
                agg["reinsurance"]
                - dec(
                    control[
                        "reinsurance_dollars"
                    ],
                    "annual.reinsurance",
                ),

            "lics":
                agg["lics"]
                - dec(
                    control["lics_dollars"],
                    "annual.lics",
                ),

            "total":
                agg["total"]
                - dec(
                    control[
                        "total_partd_dollars"
                    ],
                    "annual.total",
                ),
        }

        local_money_max = max(
            abs(value)
            for value in money_diffs.values()
        )

        max_annual_enrollment_diff = max(
            max_annual_enrollment_diff,
            abs(enrollment_diff),
        )

        max_annual_total_diff = max(
            max_annual_total_diff,
            local_money_max,
        )

        passed = (
            enrollment_diff == 0
            and local_money_max <= RECON_TOL
        )

        if not passed:
            annual_failures += 1

        annual_recon_rows.append(
            {
                "year":
                    year,

                "coverage":
                    clean(
                        control["coverage"]
                    ),

                "county_sum_reconstructed_enrollment":
                    agg["enrollment"],

                "control_reconstructed_enrollment":
                    integer(
                        control[
                            "reconstructed_numeric_enrollment"
                        ],
                        (
                            "annual."
                            "reconstructed_numeric_enrollment"
                        ),
                    ),

                "enrollment_difference":
                    enrollment_diff,

                "county_sum_direct_subsidy_ra_dollars":
                    str(agg["direct"]),

                "county_sum_reinsurance_dollars":
                    str(agg["reinsurance"]),

                "county_sum_lics_dollars":
                    str(agg["lics"]),

                "county_sum_total_partd_dollars":
                    str(agg["total"]),

                "control_total_partd_dollars":
                    clean(
                        control[
                            "total_partd_dollars"
                        ]
                    ),

                "total_dollar_difference":
                    str(
                        money_diffs["total"]
                    ),

                "status":
                    yesno(passed),
            }
        )

    check(
        "County sums reconcile to every frozen v0.3 annual control",
        annual_failures == 0,
        (
            f"failures={annual_failures}; "
            f"max_enrollment_difference="
            f"{max_annual_enrollment_diff}; "
            f"max_component_or_total_dollar_difference="
            f"{max_annual_total_diff}"
        ),
    )

    # ------------------------------------------------------------------
    # Statewide total preservation
    # ------------------------------------------------------------------

    statewide_total = sum(
        (
            state_year[year]["total"]
            for year in EXPECTED_YEARS
        ),
        ZERO,
    )

    annual_control_total = sum(
        (
            dec(
                annual_by_year[year][
                    "total_partd_dollars"
                ],
                "annual.total",
            )
            for year in EXPECTED_YEARS
        ),
        ZERO,
    )

    statewide_diff = (
        statewide_total
        - annual_control_total
    )

    check(
        "Statewide reconstructed total preserved",
        abs(statewide_diff) <= RECON_TOL,
        (
            f"county_sum=${money(statewide_total)}; "
            f"annual_control_sum="
            f"${money(annual_control_total)}; "
            f"difference={statewide_diff}"
        ),
    )

    # ------------------------------------------------------------------
    # County-year presence inventory.
    #
    # IMPORTANT:
    # Presence is descriptive, not a blanket completeness criterion.
    # An absent county-year is explicitly NOT interpreted as zero.
    # ------------------------------------------------------------------

    county_year_rows: list[dict] = []
    presence_rows: list[dict] = []

    absent_county_years: list[
        tuple[int, str]
    ] = []

    for year in EXPECTED_YEARS:
        expected_month_set = set(
            EXPECTED_MONTHS[year]
        )

        for county, fips in WA_COUNTIES.items():
            key = (
                year,
                county,
            )

            if key not in county_year:
                absent_county_years.append(
                    key
                )

                presence_rows.append(
                    {
                        "year":
                            year,

                        "county_fips":
                            fips,

                        "county":
                            county,

                        "status":
                            (
                                "ABSENT_FROM_"
                                "RECONSTRUCTED_DETAIL"
                            ),

                        "months_with_reconstructed_dollars":
                            0,

                        "expected_months_in_source_window":
                            len(
                                expected_month_set
                            ),

                        "interpretation":
                            (
                                "NOT_ZERO; requires upstream "
                                "enrollment/match classification "
                                "before any completeness inference"
                            ),
                    }
                )

                continue

            agg = county_year[key]

            months = sorted(
                agg["months"]
            )

            presence_rows.append(
                {
                    "year":
                        year,

                    "county_fips":
                        fips,

                    "county":
                        county,

                    "status":
                        "PRESENT",

                    "months_with_reconstructed_dollars":
                        len(months),

                    "expected_months_in_source_window":
                        len(
                            expected_month_set
                        ),

                    "interpretation":
                        (
                            "RECONSTRUCTED_"
                            "EXACT_MATCH_POPULATION_ONLY"
                        ),
                }
            )

            county_year_rows.append(
                {
                    "year":
                        year,

                    "coverage":
                        (
                            "JAN-SEP"
                            if year == 2024
                            else "JAN-DEC"
                        ),

                    "county_fips":
                        fips,

                    "county":
                        county,

                    "months_with_reconstructed_dollars":
                        len(months),

                    "detail_rows":
                        agg["rows"],

                    "reconstructed_numeric_enrollment":
                        agg["enrollment"],

                    "direct_subsidy_ra_dollars":
                        str(
                            agg["direct"]
                        ),

                    "reinsurance_dollars":
                        str(
                            agg["reinsurance"]
                        ),

                    "lics_dollars":
                        str(
                            agg["lics"]
                        ),

                    "total_partd_dollars":
                        str(
                            agg["total"]
                        ),

                    "dollar_status":
                        "RECONSTRUCTED",

                    "geography_basis":
                        (
                            "DIRECT_CPSC_"
                            "COUNTY_OF_RESIDENCE"
                        ),

                    "payment_match_basis":
                        (
                            "EXACT_SAME_YEAR_"
                            "CONTRACT_PBP"
                        ),

                    "coverage_status":
                        (
                            "PARTIAL_DOLLAR_"
                            "COVERAGE"
                        ),
                }
            )

    # Deliberately do NOT require all 39 counties in every year.
    check(
        "County-year absence inventory produced without zero imputation",
        True,
        (
            f"absent_county_years="
            f"{len(absent_county_years)}"
        ),
    )

    # ------------------------------------------------------------------
    # Temporal source-window certification
    # ------------------------------------------------------------------

    temporal_ok = True
    temporal_evidence = []

    for year in EXPECTED_YEARS:
        months = sorted(
            month
            for y, month in actual_periods
            if y == year
        )

        expected = list(
            EXPECTED_MONTHS[year]
        )

        ok = months == expected
        temporal_ok = temporal_ok and ok

        temporal_evidence.append(
            (
                f"CY{year}="
                f"{len(months)}m("
                f"{'JAN-SEP' if year == 2024 else 'JAN-DEC'}"
                f")"
            )
        )

    check(
        (
            "Certified source window is 12 months "
            "CY2015-CY2023 and Jan-Sep CY2024"
        ),
        temporal_ok,
        "; ".join(
            temporal_evidence
        ),
    )

    # ------------------------------------------------------------------
    # Overall certification result
    # ------------------------------------------------------------------

    overall = all(
        row["status"] == "PASS"
        for row in checks
    )

    # ------------------------------------------------------------------
    # Write evidence artifacts
    # ------------------------------------------------------------------

    write_csv(
        output_dir
        / "cms_partd_county_checks_v0_1.csv",
        checks,
        [
            "check",
            "status",
            "evidence",
        ],
    )

    write_csv(
        output_dir
        / "cms_partd_county_year_reconstruction_v0_1.csv",
        county_year_rows,
        [
            "year",
            "coverage",
            "county_fips",
            "county",
            "months_with_reconstructed_dollars",
            "detail_rows",
            "reconstructed_numeric_enrollment",
            "direct_subsidy_ra_dollars",
            "reinsurance_dollars",
            "lics_dollars",
            "total_partd_dollars",
            "dollar_status",
            "geography_basis",
            "payment_match_basis",
            "coverage_status",
        ],
    )

    write_csv(
        output_dir
        / "cms_partd_county_year_presence_v0_1.csv",
        presence_rows,
        [
            "year",
            "county_fips",
            "county",
            "status",
            "months_with_reconstructed_dollars",
            "expected_months_in_source_window",
            "interpretation",
        ],
    )

    write_csv(
        output_dir
        / "cms_partd_county_month_reconciliation_v0_1.csv",
        monthly_recon_rows,
        [
            "year",
            "month",
            "county_sum_reconstructed_enrollment",
            "control_reconstructed_enrollment",
            "enrollment_difference",
            "county_sum_total_partd_dollars",
            "control_total_partd_dollars",
            "total_dollar_difference",
            "status",
        ],
    )

    write_csv(
        output_dir
        / "cms_partd_county_annual_reconciliation_v0_1.csv",
        annual_recon_rows,
        [
            "year",
            "coverage",
            "county_sum_reconstructed_enrollment",
            "control_reconstructed_enrollment",
            "enrollment_difference",
            "county_sum_direct_subsidy_ra_dollars",
            "county_sum_reinsurance_dollars",
            "county_sum_lics_dollars",
            "county_sum_total_partd_dollars",
            "control_total_partd_dollars",
            "total_dollar_difference",
            "status",
        ],
    )

    # ------------------------------------------------------------------
    # Human-readable report
    # ------------------------------------------------------------------

    report = [
        (
            "CMS MEDICARE PART D COUNTY "
            "RECONSTRUCTION CERTIFICATION v0.1"
        ),
        "=" * 78,
        "",
        (
            "READ-ONLY downstream certification of "
            "frozen Part D reconstruction v0.3."
        ),
        (
            "No PMPM reconstruction, imputation, "
            "source modification, DB writes, "
            "or ledger inclusion."
        ),
        "",
        "BOUNDARY",
        "-" * 78,
        (
            "Dollar status       : "
            "RECONSTRUCTED"
        ),
        (
            "Geography basis     : "
            "DIRECT_CPSC_COUNTY_OF_RESIDENCE"
        ),
        (
            "Payment match basis : "
            "EXACT_SAME_YEAR_CONTRACT_PBP"
        ),
        (
            "Coverage status     : "
            "PARTIAL_DOLLAR_COVERAGE"
        ),
        (
            "CY2015-CY2023       : "
            "JAN-DEC source window"
        ),
        (
            "CY2024              : "
            "JAN-SEP source window"
        ),
        "",
        "IMPORTANT:",
        (
            "No-exact-payment-match enrollment "
            "receives no reconstructed dollars."
        ),
        (
            "Suppressed/non-numeric enrollment "
            "is not imputed."
        ),
        (
            "An absent county-year is NOT "
            "interpreted as zero."
        ),
        "",
        "SUMMARY",
        "-" * 78,
        (
            f"Detail rows                              : "
            f"{detail_rows:,}"
        ),
        (
            f"Distinct canonical WA counties          : "
            f"{len(observed_counties)}"
        ),
        (
            f"Blank county rows                        : "
            f"{blank_county_rows:,}"
        ),
        (
            f"Unknown county labels                    : "
            f"{len(unknown_counties):,}"
        ),
        (
            f"Reconstructed enrollment member-months  : "
            f"{detail_enrollment:,}"
        ),
        (
            f"Reconstructed Part D dollars             : "
            f"${money(statewide_total)}"
        ),
        (
            f"Absent county-years in reconstructed set : "
            f"{len(absent_county_years):,}"
        ),
        (
            f"Maximum detail arithmetic difference     : "
            f"{max_identity_diff}"
        ),
        (
            f"Maximum monthly reconciliation difference: "
            f"{max_monthly_total_diff}"
        ),
        (
            f"Maximum annual reconciliation difference : "
            f"{max_annual_total_diff}"
        ),
        "",
        "CHECKS",
        "-" * 78,
    ]

    for row in checks:
        report.append(
            (
                f"{row['status']:4} | "
                f"{row['check']} | "
                f"{row['evidence']}"
            )
        )

    report.extend(
        [
            "",
            "CERTIFICATION",
            "-" * 78,
            (
                "CMS-PARTD-COUNTY-CERT-v0.1 — "
                + (
                    "PASS / PARTIAL-DOLLAR COVERAGE"
                    if overall
                    else "FAIL"
                )
            ),
            "",
            "Interpretation:",
            (
                "County geography is taken directly "
                "from the Washington CPSC enrollment"
            ),
            (
                "record used by the frozen v0.3 "
                "reconstruction. County dollars are an"
            ),
            (
                "aggregation of already-reconstructed "
                "exact-match Contract+PBP dollars;"
            ),
            (
                "they are not a post hoc beneficiary-share "
                "allocation. This certification"
            ),
            (
                "does not expand v0.3 dollar coverage and "
                "does not authorize ledger inclusion."
            ),
        ]
    )

    report_path = (
        output_dir
        / "cms_partd_county_reconstruction_report_v0_1.txt"
    )

    report_path.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )

    print(
        "\n".join(report)
    )

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )