"""
ETL-172J-3C
Allocate Washington Specialized Remaining Federal Receipts

Components
----------
1. TRANSPORTATION_TRUST_FUND
   National control:
       Certified ETL-172I-2 OMB decomposition.

   Allocator:
       Certified ETL-172J-3B FHWA FE-221B Washington share of
       Highway Account payments attributable to highway users.

2. ALCOHOL
   National control:
       Certified ETL-172I-2 OMB decomposition.

   Allocator:
       Certified ETL-172J-3B NIAAA Washington share of
       all-beverage gallons of ethanol (absolute alcohol).

Timing
------
Transportation:
    FFY2015-FFY2024 -> same-year FHWA share.

Alcohol:
    FFY2015-FFY2023 -> same-year NIAAA share.
    FFY2024          -> NIAAA 2023 latest-available share.

Purpose
-------
Apply already-certified allocator methodologies to already-certified
national receipt controls and reduce the ETL-172J actionable work queue.

This script does NOT:
    - reinterpret the raw OMB workbook;
    - reinterpret raw FHWA or NIAAA source files;
    - extrapolate a 2024 NIAAA observation;
    - force reconciliation to IRS gross collections;
    - write to PostgreSQL;
    - authorize final-ledger inclusion.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]

I2_FILE = (
    ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "social_insurance_excise_decomposition_v0_1"
    / "national_social_insurance_excise_decomposition.csv"
)

J3B_DIR = (
    ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "specialized_receipt_allocator_profile_v0_1"
)

FHWA_FILE = J3B_DIR / "fhwa_allocator_extract.csv"
NIAAA_FILE = J3B_DIR / "niaaa_allocator_extract.csv"
J3B_CERTIFICATION_FILE = J3B_DIR / "certification.json"

J2_QUEUE_FILE = (
    ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "washington_population_receipts_v0_1"
    / "remaining_receipts_work_queue_after_j2.csv"
)

OUTPUT_DIR = (
    ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "washington_specialized_receipts_v0_1"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

CONTROL_FILE = (
    OUTPUT_DIR
    / "specialized_receipt_national_controls.csv"
)

TIMING_FILE = (
    OUTPUT_DIR
    / "specialized_receipt_allocator_timing.csv"
)

ALLOCATION_FILE = (
    OUTPUT_DIR
    / "washington_specialized_receipts_allocation.csv"
)

ANNUAL_FILE = (
    OUTPUT_DIR
    / "washington_specialized_receipts_annual_summary.csv"
)

QUEUE_FILE = (
    OUTPUT_DIR
    / "remaining_receipts_work_queue_after_j3.csv"
)

CERTIFICATION_JSON = (
    OUTPUT_DIR
    / "certification.json"
)

CERTIFICATION_REPORT = (
    OUTPUT_DIR
    / "certification_report.txt"
)

YEARS = list(range(2015, 2025))

COMPONENTS = [
    "TRANSPORTATION_TRUST_FUND",
    "ALCOHOL",
]


# =============================================================================
# HELPERS
# =============================================================================

def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required certified input not found: {path}"
        )


def pass_fail(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


def finite_number(value) -> float:
    result = float(value)

    if not math.isfinite(result):
        raise ValueError(
            f"Expected finite numeric value; received {value!r}"
        )

    return result


def write_csv(
    path: Path,
    rows: list[dict],
    fieldnames: list[str],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


# =============================================================================
# UPSTREAM CERTIFICATION
# =============================================================================

def validate_j3b_certification() -> dict:
    require_file(J3B_CERTIFICATION_FILE)

    certification = json.loads(
        J3B_CERTIFICATION_FILE.read_text(
            encoding="utf-8"
        )
    )

    if certification.get("result") != "PASS":
        raise ValueError(
            "ETL-172J-3B certification is not PASS."
        )

    checks = certification.get(
        "checks",
        {},
    )

    failed = {
        name: status
        for name, status in checks.items()
        if status != "PASS"
    }

    if failed:
        raise ValueError(
            "ETL-172J-3B contains non-PASS certification checks: "
            f"{failed}"
        )

    return certification


# =============================================================================
# I-2 NATIONAL CONTROLS
# =============================================================================

def load_national_controls() -> pd.DataFrame:
    require_file(I2_FILE)

    df = pd.read_csv(I2_FILE)

    required = {
        "fiscal_year",
        "major_category",
        "component_code",
        "component_label",
        "amount_millions",
        "amount_dollars",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "ETL-172I-2 decomposition missing required columns: "
            f"{sorted(missing)}"
        )

    subset = df[
        df["component_code"].isin(COMPONENTS)
    ].copy()

    subset["fiscal_year"] = (
        subset["fiscal_year"].astype(int)
    )

    subset = subset[
        subset["fiscal_year"].isin(YEARS)
    ].copy()

    counts = (
        subset.groupby(
            ["fiscal_year", "component_code"]
        )
        .size()
    )

    expected_index = pd.MultiIndex.from_product(
        [YEARS, COMPONENTS],
        names=[
            "fiscal_year",
            "component_code",
        ],
    )

    counts = counts.reindex(
        expected_index,
        fill_value=0,
    )

    if not (counts == 1).all():
        bad = counts[counts != 1]

        raise ValueError(
            "Expected exactly one I-2 row per year/component. "
            f"Bad coverage:\n{bad}"
        )

    if not (
        subset["major_category"]
        == "EXCISE_TAXES"
    ).all():
        raise ValueError(
            "Specialized J-3 controls are not all classified "
            "as EXCISE_TAXES in certified I-2."
        )

    for _, row in subset.iterrows():
        millions = finite_number(
            row["amount_millions"]
        )

        dollars = finite_number(
            row["amount_dollars"]
        )

        if abs(
            dollars
            - millions * 1_000_000.0
        ) > 0.01:
            raise ValueError(
                "I-2 amount_millions / amount_dollars identity "
                f"failed for {row['fiscal_year']} "
                f"{row['component_code']}."
            )

    return subset.sort_values(
        ["fiscal_year", "component_code"]
    ).reset_index(drop=True)


# =============================================================================
# CERTIFIED ALLOCATORS
# =============================================================================

def load_fhwa() -> pd.DataFrame:
    require_file(FHWA_FILE)

    df = pd.read_csv(FHWA_FILE)

    required = {
        "fiscal_year",
        "washington_payments_thousands",
        "us_grand_total_payments_thousands",
        "washington_share",
        "washington_share_pct",
        "source_scope",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "J-3B FHWA extract missing columns: "
            f"{sorted(missing)}"
        )

    df["fiscal_year"] = (
        df["fiscal_year"].astype(int)
    )

    df = df[
        df["fiscal_year"].isin(YEARS)
    ].copy()

    if len(df) != 10:
        raise ValueError(
            f"Expected 10 FHWA study-period rows; found {len(df)}."
        )

    if df["fiscal_year"].duplicated().any():
        raise ValueError(
            "Duplicate FHWA fiscal-year rows."
        )

    if set(df["fiscal_year"]) != set(YEARS):
        raise ValueError(
            "FHWA extract does not contain exactly FFY2015-FFY2024."
        )

    for _, row in df.iterrows():
        wa = finite_number(
            row["washington_payments_thousands"]
        )

        us = finite_number(
            row["us_grand_total_payments_thousands"]
        )

        share = finite_number(
            row["washington_share"]
        )

        if us <= 0:
            raise ValueError(
                "FHWA U.S. denominator must be positive."
            )

        calculated = wa / us

        if abs(calculated - share) > 1e-12:
            raise ValueError(
                "Certified FHWA share does not reproduce from "
                f"numerator/denominator for {row['fiscal_year']}."
            )

    return df.sort_values(
        "fiscal_year"
    ).reset_index(drop=True)


def load_niaaa() -> pd.DataFrame:
    require_file(NIAAA_FILE)

    df = pd.read_csv(NIAAA_FILE)

    required = {
        "calendar_year",
        "washington_geography_id",
        "us_geography_id",
        "beverage_type",
        "beverage_label",
        "washington_ethanol_gallons",
        "us_ethanol_gallons",
        "washington_share",
        "washington_share_pct",
        "allocator_measure",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "J-3B NIAAA extract missing columns: "
            f"{sorted(missing)}"
        )

    df["calendar_year"] = (
        df["calendar_year"].astype(int)
    )

    if len(df) != 9:
        raise ValueError(
            f"Expected 9 NIAAA rows for 2015-2023; found {len(df)}."
        )

    if df["calendar_year"].duplicated().any():
        raise ValueError(
            "Duplicate NIAAA calendar-year rows."
        )

    if set(df["calendar_year"]) != set(range(2015, 2024)):
        raise ValueError(
            "NIAAA extract does not contain exactly 2015-2023."
        )

    if not (
        df["washington_geography_id"].astype(int)
        == 53
    ).all():
        raise ValueError(
            "NIAAA Washington geography is not consistently 53."
        )

    if not (
        df["us_geography_id"].astype(int)
        == 99
    ).all():
        raise ValueError(
            "NIAAA United States geography is not consistently 99."
        )

    if not (
        df["beverage_type"].astype(int)
        == 4
    ).all():
        raise ValueError(
            "NIAAA allocator is not consistently beverage type 4."
        )

    for _, row in df.iterrows():
        wa = finite_number(
            row["washington_ethanol_gallons"]
        )

        us = finite_number(
            row["us_ethanol_gallons"]
        )

        share = finite_number(
            row["washington_share"]
        )

        if us <= 0:
            raise ValueError(
                "NIAAA U.S. denominator must be positive."
            )

        calculated = wa / us

        if abs(calculated - share) > 1e-12:
            raise ValueError(
                "Certified NIAAA share does not reproduce from "
                f"numerator/denominator for {row['calendar_year']}."
            )

    return df.sort_values(
        "calendar_year"
    ).reset_index(drop=True)


# =============================================================================
# TIMING MAP
# =============================================================================

def build_timing_map(
    fhwa: pd.DataFrame,
    niaaa: pd.DataFrame,
) -> list[dict]:
    fhwa_lookup = {
        int(row["fiscal_year"]): row
        for _, row in fhwa.iterrows()
    }

    niaaa_lookup = {
        int(row["calendar_year"]): row
        for _, row in niaaa.iterrows()
    }

    rows = []

    for fiscal_year in YEARS:
        fhwa_row = fhwa_lookup[fiscal_year]

        rows.append(
            {
                "fiscal_year": fiscal_year,
                "component_code":
                    "TRANSPORTATION_TRUST_FUND",
                "allocator_source": "FHWA_FE_221B",
                "allocator_source_year": fiscal_year,
                "allocator_timing_status":
                    "CONTEMPORANEOUS_SHARE",
                "allocator_share":
                    finite_number(
                        fhwa_row["washington_share"]
                    ),
                "allocator_numerator":
                    finite_number(
                        fhwa_row[
                            "washington_payments_thousands"
                        ]
                    ),
                "allocator_denominator":
                    finite_number(
                        fhwa_row[
                            "us_grand_total_payments_thousands"
                        ]
                    ),
                "allocator_units":
                    "THOUSANDS_OF_DOLLARS",
            }
        )

        alcohol_source_year = (
            fiscal_year
            if fiscal_year <= 2023
            else 2023
        )

        niaaa_row = niaaa_lookup[
            alcohol_source_year
        ]

        alcohol_status = (
            "CONTEMPORANEOUS_SHARE"
            if fiscal_year <= 2023
            else "LATEST_AVAILABLE_SHARE"
        )

        rows.append(
            {
                "fiscal_year": fiscal_year,
                "component_code": "ALCOHOL",
                "allocator_source":
                    "NIAAA_APPARENT_ALCOHOL_CONSUMPTION",
                "allocator_source_year":
                    alcohol_source_year,
                "allocator_timing_status":
                    alcohol_status,
                "allocator_share":
                    finite_number(
                        niaaa_row["washington_share"]
                    ),
                "allocator_numerator":
                    finite_number(
                        niaaa_row[
                            "washington_ethanol_gallons"
                        ]
                    ),
                "allocator_denominator":
                    finite_number(
                        niaaa_row[
                            "us_ethanol_gallons"
                        ]
                    ),
                "allocator_units":
                    "GALLONS_OF_ETHANOL_ABSOLUTE_ALCOHOL",
            }
        )

    return rows


# =============================================================================
# ALLOCATION
# =============================================================================

def allocate_receipts(
    controls: pd.DataFrame,
    timing_rows: list[dict],
) -> list[dict]:
    control_lookup = {
        (
            int(row["fiscal_year"]),
            str(row["component_code"]),
        ): row
        for _, row in controls.iterrows()
    }

    rows = []

    for timing in timing_rows:
        year = int(
            timing["fiscal_year"]
        )

        component = str(
            timing["component_code"]
        )

        control = control_lookup[
            (year, component)
        ]

        national_millions = finite_number(
            control["amount_millions"]
        )

        national_dollars = finite_number(
            control["amount_dollars"]
        )

        share = finite_number(
            timing["allocator_share"]
        )

        washington_dollars = (
            national_dollars * share
        )

        rows.append(
            {
                "fiscal_year": year,
                "component_code": component,
                "component_label":
                    control["component_label"],
                "national_control_millions":
                    national_millions,
                "national_control_dollars":
                    national_dollars,
                "allocator_source":
                    timing["allocator_source"],
                "allocator_source_year":
                    timing["allocator_source_year"],
                "allocator_timing_status":
                    timing["allocator_timing_status"],
                "allocator_numerator":
                    timing["allocator_numerator"],
                "allocator_denominator":
                    timing["allocator_denominator"],
                "allocator_units":
                    timing["allocator_units"],
                "washington_share":
                    share,
                "washington_share_pct":
                    share * 100.0,
                "washington_allocated_dollars":
                    washington_dollars,
                "accounting_control_source":
                    "ETL_172I_2_OMB",
                "allocation_status":
                    "ALLOCATED_METHOD_CERTIFIED",
            }
        )

    return rows


# =============================================================================
# J-2 QUEUE
# =============================================================================

def load_j2_queue() -> tuple[pd.DataFrame, dict[str, str]]:
    require_file(J2_QUEUE_FILE)

    df = pd.read_csv(J2_QUEUE_FILE)

    if "fiscal_year" not in df.columns:
        raise ValueError(
            "J-2 queue missing fiscal_year."
        )

    df["fiscal_year"] = (
        df["fiscal_year"].astype(int)
    )

    if len(df) != 10:
        raise ValueError(
            f"Expected 10 J-2 queue rows; found {len(df)}."
        )

    if set(df["fiscal_year"]) != set(YEARS):
        raise ValueError(
            "J-2 queue does not contain exactly FFY2015-FFY2024."
        )

    if df["fiscal_year"].duplicated().any():
        raise ValueError(
            "J-2 queue contains duplicate fiscal years."
        )

    # Use exact post-J2 fields if present. This is intentionally
    # explicit enough to avoid reopening pre-J2 balances.
    candidate_sets = {
        "actionable": [
            "actionable_unfinished_millions_after_j2",
        ],
        "documented": [
            "allocator_method_documented_millions_after_j2",
        ],
        "method_review": [
            "method_change_review_millions",
        ],
        "withhold": [
            "withhold_unresolved_millions",
        ],
        "unallocable": [
            "intentionally_unallocable_millions",
        ],
    }

    field_map = {}

    for logical_name, candidates in candidate_sets.items():
        matches = [
            column
            for column in candidates
            if column in df.columns
        ]

        if len(matches) != 1:
            raise ValueError(
                f"J-2 queue {logical_name}: expected exactly one "
                f"matching certified post-J2 field from {candidates}; "
                f"found {matches}. "
                f"Available columns: {list(df.columns)}"
            )

        field_map[logical_name] = matches[0]

    return df, field_map


def reduce_queue(
    j2_queue: pd.DataFrame,
    field_map: dict[str, str],
    allocations: list[dict],
) -> list[dict]:
    closed_by_year: dict[int, float] = {
        year: 0.0
        for year in YEARS
    }

    for row in allocations:
        year = int(
            row["fiscal_year"]
        )

        closed_by_year[year] += finite_number(
            row["national_control_millions"]
        )

    rows = []

    for _, source in j2_queue.iterrows():
        year = int(
            source["fiscal_year"]
        )

        actionable_before = finite_number(
            source[
                field_map["actionable"]
            ]
        )

        documented_before = finite_number(
            source[
                field_map["documented"]
            ]
        )

        method_review = finite_number(
            source[
                field_map["method_review"]
            ]
        )

        withhold = finite_number(
            source[
                field_map["withhold"]
            ]
        )

        unallocable = finite_number(
            source[
                field_map["unallocable"]
            ]
        )

        closed = closed_by_year[year]

        documented_after = (
            documented_before - closed
        )

        actionable_after = (
            actionable_before - closed
        )

        if documented_after < -0.000001:
            raise ValueError(
                f"J-3 closes more documented-method receipts than "
                f"remain in J-2 for {year}: "
                f"{documented_before} - {closed} "
                f"= {documented_after}"
            )

        if actionable_after < -0.000001:
            raise ValueError(
                f"J-3 closes more actionable receipts than remain "
                f"in J-2 for {year}."
            )

        # Normalize tiny floating residuals.
        if abs(documented_after) < 0.000001:
            documented_after = 0.0

        if abs(actionable_after) < 0.000001:
            actionable_after = 0.0

        rows.append(
            {
                "fiscal_year": year,
                "actionable_unfinished_before_j3_millions":
                    actionable_before,
                "allocator_method_documented_before_j3_millions":
                    documented_before,
                "j3_national_control_closed_millions":
                    closed,
                "allocator_method_documented_after_j3_millions":
                    documented_after,
                "actionable_unfinished_after_j3_millions":
                    actionable_after,
                "method_change_review_millions":
                    method_review,
                "withhold_unresolved_millions":
                    withhold,
                "intentionally_unallocable_millions":
                    unallocable,
            }
        )

    return rows


# =============================================================================
# CERTIFICATION
# =============================================================================

def certify(
    controls: pd.DataFrame,
    timing_rows: list[dict],
    allocations: list[dict],
    queue_rows: list[dict],
) -> dict[str, str]:
    checks: dict[str, str] = {}

    checks["j3b_upstream_certification"] = "PASS"

    checks["national_control_year_component_coverage"] = pass_fail(
        len(controls) == 20
        and set(
            zip(
                controls["fiscal_year"].astype(int),
                controls["component_code"],
            )
        )
        == {
            (year, component)
            for year in YEARS
            for component in COMPONENTS
        }
    )

    checks["allocator_timing_coverage"] = pass_fail(
        len(timing_rows) == 20
    )

    transportation_timing_ok = all(
        int(row["allocator_source_year"])
        == int(row["fiscal_year"])
        and row["allocator_timing_status"]
        == "CONTEMPORANEOUS_SHARE"
        for row in timing_rows
        if row["component_code"]
        == "TRANSPORTATION_TRUST_FUND"
    )

    checks["fhwa_timing_policy"] = pass_fail(
        transportation_timing_ok
    )

    alcohol_timing_ok = True

    for row in timing_rows:
        if row["component_code"] != "ALCOHOL":
            continue

        year = int(
            row["fiscal_year"]
        )

        source_year = int(
            row["allocator_source_year"]
        )

        status = row[
            "allocator_timing_status"
        ]

        if year <= 2023:
            if not (
                source_year == year
                and status
                == "CONTEMPORANEOUS_SHARE"
            ):
                alcohol_timing_ok = False
        else:
            if not (
                year == 2024
                and source_year == 2023
                and status
                == "LATEST_AVAILABLE_SHARE"
            ):
                alcohol_timing_ok = False

    checks["niaaa_timing_policy"] = pass_fail(
        alcohol_timing_ok
    )

    checks["washington_allocation"] = pass_fail(
        len(allocations) == 20
        and all(
            abs(
                finite_number(
                    row["washington_allocated_dollars"]
                )
                - (
                    finite_number(
                        row["national_control_dollars"]
                    )
                    * finite_number(
                        row["washington_share"]
                    )
                )
            )
            < 0.01
            for row in allocations
        )
    )

    queue_identity_ok = True

    for row in queue_rows:
        before = finite_number(
            row[
                "actionable_unfinished_before_j3_millions"
            ]
        )

        closed = finite_number(
            row[
                "j3_national_control_closed_millions"
            ]
        )

        after = finite_number(
            row[
                "actionable_unfinished_after_j3_millions"
            ]
        )

        documented_after = finite_number(
            row[
                "allocator_method_documented_after_j3_millions"
            ]
        )

        method_review = finite_number(
            row["method_change_review_millions"]
        )

        withhold = finite_number(
            row["withhold_unresolved_millions"]
        )

        if abs(
            before - closed - after
        ) > 0.000001:
            queue_identity_ok = False

        if abs(
            after
            - (
                documented_after
                + method_review
                + withhold
            )
        ) > 0.000001:
            queue_identity_ok = False

    checks["j2_work_queue_reduction"] = pass_fail(
        queue_identity_ok
    )

    # Strong finish-line guard:
    # J-3 should exhaust every remaining
    # ALLOCATOR_METHOD_DOCUMENTED national dollar.
    checks[
        "allocator_method_documented_queue_closed"
    ] = pass_fail(
        all(
            abs(
                finite_number(
                    row[
                        "allocator_method_documented_after_j3_millions"
                    ]
                )
            )
            < 0.000001
            for row in queue_rows
        )
    )

    # 2024 should now consist solely of method-review and/or
    # explicit withholding, with no documented-method residual.
    row_2024 = next(
        row
        for row in queue_rows
        if int(row["fiscal_year"]) == 2024
    )

    checks["ffy2024_expected_queue_structure"] = pass_fail(
        abs(
            finite_number(
                row_2024[
                    "allocator_method_documented_after_j3_millions"
                ]
            )
        )
        < 0.000001
        and abs(
            finite_number(
                row_2024[
                    "actionable_unfinished_after_j3_millions"
                ]
            )
            - (
                finite_number(
                    row_2024[
                        "method_change_review_millions"
                    ]
                )
                + finite_number(
                    row_2024[
                        "withhold_unresolved_millions"
                    ]
                )
            )
        )
        < 0.000001
    )

    checks["irs_forced_reconciliation_boundary"] = "PASS"
    checks["database_write_boundary"] = "PASS"
    checks["final_ledger_boundary"] = "PASS"

    return checks


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    for path in [
        I2_FILE,
        FHWA_FILE,
        NIAAA_FILE,
        J3B_CERTIFICATION_FILE,
        J2_QUEUE_FILE,
    ]:
        require_file(path)

    validate_j3b_certification()

    controls = load_national_controls()
    fhwa = load_fhwa()
    niaaa = load_niaaa()

    timing_rows = build_timing_map(
        fhwa,
        niaaa,
    )

    allocations = allocate_receipts(
        controls,
        timing_rows,
    )

    j2_queue, field_map = load_j2_queue()

    queue_rows = reduce_queue(
        j2_queue,
        field_map,
        allocations,
    )

    # -------------------------------------------------------------------------
    # OUTPUTS
    # -------------------------------------------------------------------------

    control_rows = []

    for _, row in controls.iterrows():
        control_rows.append(
            {
                "fiscal_year":
                    int(row["fiscal_year"]),
                "component_code":
                    row["component_code"],
                "component_label":
                    row["component_label"],
                "national_control_millions":
                    finite_number(
                        row["amount_millions"]
                    ),
                "national_control_dollars":
                    finite_number(
                        row["amount_dollars"]
                    ),
                "source":
                    "ETL_172I_2_CERTIFIED_DECOMPOSITION",
            }
        )

    write_csv(
        CONTROL_FILE,
        control_rows,
        [
            "fiscal_year",
            "component_code",
            "component_label",
            "national_control_millions",
            "national_control_dollars",
            "source",
        ],
    )

    write_csv(
        TIMING_FILE,
        timing_rows,
        [
            "fiscal_year",
            "component_code",
            "allocator_source",
            "allocator_source_year",
            "allocator_timing_status",
            "allocator_share",
            "allocator_numerator",
            "allocator_denominator",
            "allocator_units",
        ],
    )

    write_csv(
        ALLOCATION_FILE,
        allocations,
        [
            "fiscal_year",
            "component_code",
            "component_label",
            "national_control_millions",
            "national_control_dollars",
            "allocator_source",
            "allocator_source_year",
            "allocator_timing_status",
            "allocator_numerator",
            "allocator_denominator",
            "allocator_units",
            "washington_share",
            "washington_share_pct",
            "washington_allocated_dollars",
            "accounting_control_source",
            "allocation_status",
        ],
    )

    annual_rows = []

    for year in YEARS:
        selected = [
            row
            for row in allocations
            if int(row["fiscal_year"]) == year
        ]

        transport = next(
            row
            for row in selected
            if row["component_code"]
            == "TRANSPORTATION_TRUST_FUND"
        )

        alcohol = next(
            row
            for row in selected
            if row["component_code"]
            == "ALCOHOL"
        )

        total_national_millions = sum(
            finite_number(
                row["national_control_millions"]
            )
            for row in selected
        )

        total_wa_dollars = sum(
            finite_number(
                row["washington_allocated_dollars"]
            )
            for row in selected
        )

        queue = next(
            row
            for row in queue_rows
            if int(row["fiscal_year"]) == year
        )

        annual_rows.append(
            {
                "fiscal_year": year,
                "transport_national_control_millions":
                    finite_number(
                        transport[
                            "national_control_millions"
                        ]
                    ),
                "transport_washington_share":
                    finite_number(
                        transport[
                            "washington_share"
                        ]
                    ),
                "transport_washington_dollars":
                    finite_number(
                        transport[
                            "washington_allocated_dollars"
                        ]
                    ),
                "alcohol_national_control_millions":
                    finite_number(
                        alcohol[
                            "national_control_millions"
                        ]
                    ),
                "alcohol_allocator_source_year":
                    int(
                        alcohol[
                            "allocator_source_year"
                        ]
                    ),
                "alcohol_allocator_timing_status":
                    alcohol[
                        "allocator_timing_status"
                    ],
                "alcohol_washington_share":
                    finite_number(
                        alcohol[
                            "washington_share"
                        ]
                    ),
                "alcohol_washington_dollars":
                    finite_number(
                        alcohol[
                            "washington_allocated_dollars"
                        ]
                    ),
                "j3_national_control_closed_millions":
                    total_national_millions,
                "j3_washington_allocated_dollars":
                    total_wa_dollars,
                "actionable_unfinished_after_j3_millions":
                    finite_number(
                        queue[
                            "actionable_unfinished_after_j3_millions"
                        ]
                    ),
            }
        )

    write_csv(
        ANNUAL_FILE,
        annual_rows,
        [
            "fiscal_year",
            "transport_national_control_millions",
            "transport_washington_share",
            "transport_washington_dollars",
            "alcohol_national_control_millions",
            "alcohol_allocator_source_year",
            "alcohol_allocator_timing_status",
            "alcohol_washington_share",
            "alcohol_washington_dollars",
            "j3_national_control_closed_millions",
            "j3_washington_allocated_dollars",
            "actionable_unfinished_after_j3_millions",
        ],
    )

    write_csv(
        QUEUE_FILE,
        queue_rows,
        [
            "fiscal_year",
            "actionable_unfinished_before_j3_millions",
            "allocator_method_documented_before_j3_millions",
            "j3_national_control_closed_millions",
            "allocator_method_documented_after_j3_millions",
            "actionable_unfinished_after_j3_millions",
            "method_change_review_millions",
            "withhold_unresolved_millions",
            "intentionally_unallocable_millions",
        ],
    )

    checks = certify(
        controls,
        timing_rows,
        allocations,
        queue_rows,
    )

    overall = (
        "PASS"
        if all(
            status == "PASS"
            for status in checks.values()
        )
        else "FAIL"
    )

    certification = {
        "etl": "ETL-172J-3C",
        "result": overall,
        "methodology": {
            "transportation":
                "OMB national TRANSPORTATION_TRUST_FUND control "
                "allocated using contemporaneous FHWA FE-221B "
                "Washington share of Highway Account payments.",
            "alcohol_2015_2023":
                "OMB national ALCOHOL control allocated using "
                "same-year NIAAA Washington share of all-beverage "
                "gallons of ethanol (absolute alcohol).",
            "alcohol_2024":
                "OMB FFY2024 ALCOHOL control allocated using "
                "NIAAA 2023 LATEST_AVAILABLE_SHARE; no extrapolated "
                "2024 NIAAA observation.",
        },
        "boundaries": {
            "raw_omb_reinterpretation": False,
            "raw_fhwa_reinterpretation": False,
            "raw_niaaa_reinterpretation": False,
            "irs_forced_reconciliation": False,
            "database_writes": False,
            "final_ledger_authorization": False,
        },
        "checks": checks,
        "outputs": {
            "controls":
                str(CONTROL_FILE.relative_to(ROOT)),
            "timing":
                str(TIMING_FILE.relative_to(ROOT)),
            "allocation":
                str(ALLOCATION_FILE.relative_to(ROOT)),
            "annual":
                str(ANNUAL_FILE.relative_to(ROOT)),
            "queue":
                str(QUEUE_FILE.relative_to(ROOT)),
        },
    }

    CERTIFICATION_JSON.write_text(
        json.dumps(
            certification,
            indent=2,
        ),
        encoding="utf-8",
    )

    # -------------------------------------------------------------------------
    # CONSOLE / REPORT
    # -------------------------------------------------------------------------

    lines = []

    lines.append("=" * 128)
    lines.append(
        "WASHINGTON SPECIALIZED REMAINING RECEIPTS - ETL-172J-3C"
    )
    lines.append("=" * 128)
    lines.append("")
    lines.append("ANNUAL ALLOCATION")
    lines.append("-" * 128)
    lines.append(
        f"{'FFY':<6}"
        f"{'TRAN CTRL':>13}"
        f"{'TRAN WA %':>12}"
        f"{'ALC CTRL':>12}"
        f"{'ALC WA %':>11}"
        f"{'ALC SRC':>10}"
        f"{'J3 CLOSED':>13}"
        f"{'WA ALLOC $B':>14}"
        f"{'QUEUE LEFT':>14}"
    )

    for row in annual_rows:
        lines.append(
            f"{int(row['fiscal_year']):<6}"
            f"{float(row['transport_national_control_millions']):>13,.0f}"
            f"{float(row['transport_washington_share']) * 100:>11.4f}%"
            f"{float(row['alcohol_national_control_millions']):>12,.0f}"
            f"{float(row['alcohol_washington_share']) * 100:>10.4f}%"
            f"{int(row['alcohol_allocator_source_year']):>10}"
            f"{float(row['j3_national_control_closed_millions']):>13,.0f}"
            f"{float(row['j3_washington_allocated_dollars']) / 1e9:>14.3f}"
            f"{float(row['actionable_unfinished_after_j3_millions']):>14,.0f}"
        )

    lines.append("")
    lines.append("CERTIFICATION")
    lines.append("-" * 128)

    for name, status in checks.items():
        lines.append(
            f"{name:<76}: {status}"
        )

    lines.append("")
    lines.append(
        f"Controls   : {CONTROL_FILE.relative_to(ROOT)}"
    )
    lines.append(
        f"Timing     : {TIMING_FILE.relative_to(ROOT)}"
    )
    lines.append(
        f"Allocation : {ALLOCATION_FILE.relative_to(ROOT)}"
    )
    lines.append(
        f"Annual     : {ANNUAL_FILE.relative_to(ROOT)}"
    )
    lines.append(
        f"Queue      : {QUEUE_FILE.relative_to(ROOT)}"
    )
    lines.append(
        f"JSON       : {CERTIFICATION_JSON.relative_to(ROOT)}"
    )
    lines.append(
        f"Report     : {CERTIFICATION_REPORT.relative_to(ROOT)}"
    )

    lines.append("")
    lines.append(
        f"ETL-172J-3C RESULT: {overall}"
    )
    lines.append("")

    report = "\n".join(lines)

    CERTIFICATION_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print(report)


if __name__ == "__main__":
    main()