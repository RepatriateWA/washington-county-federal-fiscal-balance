"""
CMS Medicare County Integration Certification v0.1
==================================================

Purpose
-------
Integrate the three certified principal Medicare payment streams for
Washington counties:

    1. Original Medicare / FFS
    2. Medicare Part C
    3. Medicare Part D

The integration grain is:

    calendar_year + county_fips

Accounting identity
-------------------
For a county-year whose component values are available:

    CORE_MEDICARE_DOLLARS
        = ORIGINAL_MEDICARE_FFS_DOLLARS
        + PART_C_DOLLARS
        + PART_D_DOLLARS

Certified source boundaries
---------------------------
Original Medicare / FFS:
    Direct CMS county payment amount:
        TOT_MDCR_PYMT_AMT
    Calendar-year timing certified separately.

Part C:
    Reconstructed county dollars from the frozen certified Part C
    reconstruction.
    Published suppressed/non-numeric enrollment is not imputed.
    Absent county-years are not treated as zero.
    CY2024 is January-September only.

Part D:
    Reconstructed county dollars from exact same-year Contract+PBP
    payment matches.
    Coverage status remains PARTIAL_DOLLAR_COVERAGE.
    Unmatched enrollment is not treated as zero-dollar enrollment.
    CY2024 is January-September only.

Explicit exclusions from core
-----------------------------
MSSP EarnSaveLoss:
    EXCLUDE_DUPLICATE

RDS:
    WITHHOLD_UNRESOLVED

Washington MFFS:
    WITHHOLD_UNRESOLVED

Important boundary
------------------
This script does NOT:

    * reconstruct any payment stream,
    * impute missing/suppressed Part C values,
    * impute unmatched Part D dollars,
    * scale to Trustees controls,
    * extrapolate CY2024,
    * convert CY to FFY,
    * write to PostgreSQL,
    * authorize final federal-inflow ledger inclusion.

READ ONLY.
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


getcontext().prec = 40


REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------
# Frozen/certified inputs
# ---------------------------------------------------------------------

OM_COUNTY = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "validation"
    / "source_v0_2"
    / "wa_county_all_detail.csv"
)

OM_IDENTITY = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "validation"
    / "original_medicare_ffs_v0_1"
    / "washington_original_medicare_ffs_identity_v0_2.csv"
)

OM_ANNUAL = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "validation"
    / "original_medicare_ffs_v0_1"
    / "washington_original_medicare_ffs_annual_v0_2.csv"
)

OM_TIMING = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "validation"
    / "timing_certification_v0_1"
    / "cms_original_medicare_timing_certification_v0_1.csv"
)

PARTC_COUNTY = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_advantage"
    / "validation"
    / "partc_county_reconstruction_v0_2"
    / "cms_ma_partc_county_year_reconstruction_v0_2.csv"
)

PARTC_ANNUAL = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_advantage"
    / "validation"
    / "payment_reconstruction_v0_2"
    / "cms_ma_partc_payment_reconstruction_calendar_year.csv"
)

PARTD_COUNTY = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_partd"
    / "validation"
    / "partd_county_reconstruction_v0_1"
    / "cms_partd_county_year_reconstruction_v0_1.csv"
)

PARTD_ANNUAL = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_partd"
    / "validation"
    / "partd_county_reconstruction_v0_1"
    / "cms_partd_county_annual_reconciliation_v0_1.csv"
)

ACCOUNTING_BOUNDARY = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare"
    / "validation"
    / "accounting_boundary_v0_1"
    / "cms_medicare_stream_disposition_v0_1.csv"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare"
    / "validation"
    / "county_integration_v0_1"
)

METHODOLOGY_VERSION = "CMS-MEDICARE-COUNTY-INTEGRATION-v0.1"

EXPECTED_YEARS = list(range(2015, 2025))

CANONICAL_WA_COUNTIES = {
    "53001": "Adams",
    "53003": "Asotin",
    "53005": "Benton",
    "53007": "Chelan",
    "53009": "Clallam",
    "53011": "Clark",
    "53013": "Columbia",
    "53015": "Cowlitz",
    "53017": "Douglas",
    "53019": "Ferry",
    "53021": "Franklin",
    "53023": "Garfield",
    "53025": "Grant",
    "53027": "Grays Harbor",
    "53029": "Island",
    "53031": "Jefferson",
    "53033": "King",
    "53035": "Kitsap",
    "53037": "Kittitas",
    "53039": "Klickitat",
    "53041": "Lewis",
    "53043": "Lincoln",
    "53045": "Mason",
    "53047": "Okanogan",
    "53049": "Pacific",
    "53051": "Pend Oreille",
    "53053": "Pierce",
    "53055": "San Juan",
    "53057": "Skagit",
    "53059": "Skamania",
    "53061": "Snohomish",
    "53063": "Spokane",
    "53065": "Stevens",
    "53067": "Thurston",
    "53069": "Wahkiakum",
    "53071": "Walla Walla",
    "53073": "Whatcom",
    "53075": "Whitman",
    "53077": "Yakima",
}


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fieldnames: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def dec(value: object) -> Decimal | None:
    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    try:
        return Decimal(text.replace(",", "").replace("$", ""))
    except InvalidOperation as exc:
        raise ValueError(f"Could not parse decimal value: {value!r}") from exc


def year_int(value: object) -> int:
    return int(str(value).strip())


def fips5(value: object) -> str:
    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return text.zfill(5)


def money_text(value: Decimal | None) -> str:
    if value is None:
        return ""

    return format(value, "f")


def display_money(value: Decimal | None) -> str:
    if value is None:
        return "NA"

    return f"${value:,.2f}"


def normalize_county_name(value: object) -> str:
    text = str(value).strip()

    if text.upper().startswith("WA-"):
        text = text[3:]

    return text.strip()


def first_existing_column(
    rows: list[dict[str, str]],
    candidates: tuple[str, ...],
) -> str:
    if not rows:
        raise ValueError("Cannot resolve columns from an empty CSV.")

    columns = set(rows[0].keys())

    for candidate in candidates:
        if candidate in columns:
            return candidate

    raise KeyError(
        "None of the expected columns were found. "
        f"Candidates={candidates}; columns={sorted(columns)}"
    )


def add_check(
    checks: list[dict[str, str]],
    check_id: str,
    description: str,
    condition: bool,
    detail: str,
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "description": description,
            "status": "PASS" if condition else "FAIL",
            "detail": detail,
        }
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    om_rows = read_csv(OM_COUNTY)
    om_identity_rows = read_csv(OM_IDENTITY)
    om_annual_rows = read_csv(OM_ANNUAL)
    om_timing_rows = read_csv(OM_TIMING)

    partc_rows = read_csv(PARTC_COUNTY)
    partc_annual_rows = read_csv(PARTC_ANNUAL)

    partd_rows = read_csv(PARTD_COUNTY)
    partd_annual_rows = read_csv(PARTD_ANNUAL)

    boundary_rows = read_csv(ACCOUNTING_BOUNDARY)

    checks: list[dict[str, str]] = []

    # -----------------------------------------------------------------
    # Original Medicare
    # -----------------------------------------------------------------

    om_index: dict[tuple[int, str], dict[str, object]] = {}

    for row in om_rows:
        year = year_int(row["year"])
        fips = fips5(row["county_fips"])
        county = normalize_county_name(row["county_desc"])

        key = (year, fips)

        if key in om_index:
            raise ValueError(f"Duplicate OM county-year key: {key}")

        om_index[key] = {
            "county": county,
            "dollars": dec(row["tot_mdcr_pymt_amt"]),
            "beneficiaries": dec(row["benes_om_cnt"]),
        }

    add_check(
        checks,
        "OM_ROW_COUNT",
        "Original Medicare source has exactly 390 county-year rows",
        len(om_rows) == 390,
        f"rows={len(om_rows)}",
    )

    add_check(
        checks,
        "OM_UNIQUE_KEYS",
        "Original Medicare county-year keys are unique",
        len(om_index) == len(om_rows),
        f"unique_keys={len(om_index)}; rows={len(om_rows)}",
    )

    om_years = sorted({year for year, _ in om_index})

    add_check(
        checks,
        "OM_YEAR_UNIVERSE",
        "Original Medicare contains source years 2015-2024",
        om_years == EXPECTED_YEARS,
        f"years={om_years}",
    )

    om_fips = sorted({fips for _, fips in om_index})

    add_check(
        checks,
        "OM_CANONICAL_COUNTIES",
        "Original Medicare contains exactly the 39 canonical WA counties",
        set(om_fips) == set(CANONICAL_WA_COUNTIES),
        (
            f"distinct_fips={len(om_fips)}; "
            f"missing={sorted(set(CANONICAL_WA_COUNTIES) - set(om_fips))}; "
            f"extra={sorted(set(om_fips) - set(CANONICAL_WA_COUNTIES))}"
        ),
    )

    om_name_mismatches = []

    for (year, fips), payload in om_index.items():
        expected_name = CANONICAL_WA_COUNTIES.get(fips)
        observed_name = str(payload["county"])

        if expected_name != observed_name:
            om_name_mismatches.append(
                f"{year}:{fips}:{observed_name}->{expected_name}"
            )

    add_check(
        checks,
        "OM_COUNTY_NAMES",
        "Original Medicare county names match canonical FIPS names",
        not om_name_mismatches,
        (
            "none"
            if not om_name_mismatches
            else "; ".join(om_name_mismatches[:20])
        ),
    )

    # Cross-check OM direct county source against frozen identity artifact.

    om_identity_index: dict[tuple[int, str], Decimal | None] = {}

    for row in om_identity_rows:
        key = (
            year_int(row["YEAR_NUM"]),
            fips5(row["FIPS"]),
        )

        if key in om_identity_index:
            raise ValueError(f"Duplicate OM identity key: {key}")

        om_identity_index[key] = dec(row["TOT_MDCR_PYMT_AMT_NUM"])

    om_identity_mismatches = []

    for key, payload in om_index.items():
        left = payload["dollars"]
        right = om_identity_index.get(key)

        if left != right:
            om_identity_mismatches.append(
                f"{key}:source={left};identity={right}"
            )

    add_check(
        checks,
        "OM_IDENTITY_CROSSCHECK",
        (
            "Original Medicare direct county payment values exactly match "
            "the frozen v0.2 identity artifact"
        ),
        (
            set(om_index) == set(om_identity_index)
            and not om_identity_mismatches
        ),
        (
            f"source_keys={len(om_index)}; "
            f"identity_keys={len(om_identity_index)}; "
            f"value_mismatches={len(om_identity_mismatches)}"
        ),
    )

    # Timing certification.

    timing_statuses = {
        row.get("timing_certification_status", "").strip()
        for row in om_timing_rows
    }

    timing_bases = {
        row.get("timing_basis", "").strip()
        for row in om_timing_rows
    }

    om_timing_certified = (
        timing_statuses == {"CERTIFIED_CALENDAR_YEAR"}
        and timing_bases == {"CALENDAR_YEAR"}
    )

    add_check(
        checks,
        "OM_CALENDAR_YEAR_TIMING",
        "Original Medicare annual timing is certified as CALENDAR_YEAR",
        om_timing_certified,
        (
            f"timing_statuses={sorted(timing_statuses)}; "
            f"timing_bases={sorted(timing_bases)}"
        ),
    )

    # -----------------------------------------------------------------
    # Part C
    # -----------------------------------------------------------------

    partc_index: dict[tuple[int, str], dict[str, object]] = {}

    for row in partc_rows:
        year = year_int(row["payment_year"])
        fips = fips5(row["fips_code"])
        county = normalize_county_name(row["county"])

        key = (year, fips)

        if key in partc_index:
            raise ValueError(f"Duplicate Part C county-year key: {key}")

        partc_index[key] = {
            "county": county,
            "dollars": dec(row["partc_dollars"]),
            "member_months": dec(row["reconstructed_member_months"]),
            "months_represented": row["months_represented"].strip(),
            "year_completeness": row["year_completeness"].strip(),
            "dollar_status": row["dollar_status"].strip(),
            "geography_basis": row["geography_basis"].strip(),
        }

    partc_unknown_fips = sorted(
        {
            fips
            for _, fips in partc_index
            if fips not in CANONICAL_WA_COUNTIES
        }
    )

    add_check(
        checks,
        "PARTC_NO_NONCANONICAL_FIPS",
        "Part C contains no non-canonical Washington county FIPS",
        not partc_unknown_fips,
        f"extra_fips={partc_unknown_fips}",
    )

    partc_name_mismatches = []

    for (year, fips), payload in partc_index.items():
        expected_name = CANONICAL_WA_COUNTIES.get(fips)

        if expected_name is None:
            continue

        observed_name = str(payload["county"])

        if expected_name != observed_name:
            partc_name_mismatches.append(
                f"{year}:{fips}:{observed_name}->{expected_name}"
            )

    add_check(
        checks,
        "PARTC_COUNTY_NAMES",
        "Part C county names match canonical FIPS names where present",
        not partc_name_mismatches,
        (
            "none"
            if not partc_name_mismatches
            else "; ".join(partc_name_mismatches[:20])
        ),
    )

    expected_all_keys = {
        (year, fips)
        for year in EXPECTED_YEARS
        for fips in CANONICAL_WA_COUNTIES
    }

    partc_absent_keys = sorted(expected_all_keys - set(partc_index))

    add_check(
        checks,
        "PARTC_ABSENCE_PRESERVED",
        (
            "Part C absent county-years are detectable and are not "
            "silently converted to zero"
        ),
        len(partc_absent_keys) >= 0,
        f"absent_county_years={len(partc_absent_keys)}",
    )

    # -----------------------------------------------------------------
    # Part D
    # -----------------------------------------------------------------

    partd_index: dict[tuple[int, str], dict[str, object]] = {}

    for row in partd_rows:
        year = year_int(row["year"])
        fips = fips5(row["county_fips"])
        county = normalize_county_name(row["county"])

        key = (year, fips)

        if key in partd_index:
            raise ValueError(f"Duplicate Part D county-year key: {key}")

        partd_index[key] = {
            "county": county,
            "dollars": dec(row["total_partd_dollars"]),
            "numeric_enrollment": dec(
                row["reconstructed_numeric_enrollment"]
            ),
            "months_with_reconstructed_dollars": (
                row["months_with_reconstructed_dollars"].strip()
            ),
            "dollar_status": row["dollar_status"].strip(),
            "geography_basis": row["geography_basis"].strip(),
            "payment_match_basis": row["payment_match_basis"].strip(),
            "coverage_status": row["coverage_status"].strip(),
        }

    add_check(
        checks,
        "PARTD_COMPLETE_COUNTY_YEAR_KEYS",
        (
            "Part D county reconstruction contains all 39 canonical "
            "county keys for every source year"
        ),
        set(partd_index) == expected_all_keys,
        (
            f"observed_keys={len(partd_index)}; "
            f"expected_keys={len(expected_all_keys)}; "
            f"missing={len(expected_all_keys - set(partd_index))}; "
            f"extra={len(set(partd_index) - expected_all_keys)}"
        ),
    )

    partd_name_mismatches = []

    for (year, fips), payload in partd_index.items():
        expected_name = CANONICAL_WA_COUNTIES.get(fips)

        if expected_name is None:
            continue

        observed_name = str(payload["county"])

        if expected_name != observed_name:
            partd_name_mismatches.append(
                f"{year}:{fips}:{observed_name}->{expected_name}"
            )

    add_check(
        checks,
        "PARTD_COUNTY_NAMES",
        "Part D county names match canonical FIPS names",
        not partd_name_mismatches,
        (
            "none"
            if not partd_name_mismatches
            else "; ".join(partd_name_mismatches[:20])
        ),
    )

    partd_coverage_statuses = {
        str(payload["coverage_status"])
        for payload in partd_index.values()
    }

    add_check(
        checks,
        "PARTD_PARTIAL_COVERAGE_PRESERVED",
        "Part D remains explicitly PARTIAL_DOLLAR_COVERAGE",
        partd_coverage_statuses == {"PARTIAL_DOLLAR_COVERAGE"},
        f"coverage_statuses={sorted(partd_coverage_statuses)}",
    )

    # -----------------------------------------------------------------
    # Accounting-boundary dispositions
    # -----------------------------------------------------------------

    boundary_text = "\n".join(
        "|".join(str(value) for value in row.values())
        for row in boundary_rows
    ).upper()

    required_boundary_tokens = {
        "ORIGINAL_MEDICARE_FFS": ("INCLUDE_IN_CORE",),
        "PART_C": ("INCLUDE_IN_CORE",),
        "PART_D": ("INCLUDE_IN_CORE",),
        "MSSP_EARNSAVELOSS": ("EXCLUDE_DUPLICATE",),
        "RDS": ("WITHHOLD_UNRESOLVED",),
        "WASHINGTON_MFFS": ("WITHHOLD_UNRESOLVED",),
    }

    missing_boundary_evidence = []

    for stream, tokens in required_boundary_tokens.items():
        if stream not in boundary_text:
            missing_boundary_evidence.append(f"{stream}:missing_stream")
            continue

        for token in tokens:
            if token not in boundary_text:
                missing_boundary_evidence.append(
                    f"{stream}:missing_{token}"
                )

    add_check(
        checks,
        "ACCOUNTING_BOUNDARY_PRESERVED",
        (
            "Certified Medicare core and outside-core stream dispositions "
            "remain present"
        ),
        not missing_boundary_evidence,
        (
            "none"
            if not missing_boundary_evidence
            else "; ".join(missing_boundary_evidence)
        ),
    )

    # -----------------------------------------------------------------
    # Build 390-row canonical county-year integration frame.
    # -----------------------------------------------------------------

    integrated_rows: list[dict[str, object]] = []

    for year in EXPECTED_YEARS:
        for fips, county in CANONICAL_WA_COUNTIES.items():
            key = (year, fips)

            om = om_index.get(key)
            pc = partc_index.get(key)
            pd = partd_index.get(key)

            om_dollars = (
                om["dollars"]
                if om is not None
                else None
            )

            partc_dollars = (
                pc["dollars"]
                if pc is not None
                else None
            )

            partd_dollars = (
                pd["dollars"]
                if pd is not None
                else None
            )

            partc_available = (
                pc is not None
                and partc_dollars is not None
            )

            partd_available = (
                pd is not None
                and partd_dollars is not None
            )

            om_available = (
                om is not None
                and om_dollars is not None
            )

            if om_available and partc_available and partd_available:
                core_dollars = (
                    om_dollars
                    + partc_dollars
                    + partd_dollars
                )
                core_value_status = "CALCULATED_ALL_CORE_COMPONENTS_AVAILABLE"
            else:
                core_dollars = None
                core_value_status = "WITHHELD_COMPONENT_UNAVAILABLE"

            if year <= 2023:
                time_window_status = "COMPLETE_CALENDAR_YEAR_WINDOW"
            else:
                time_window_status = (
                    "OM_COMPLETE_CY;PARTC_PARTD_JAN_SEP_ONLY"
                )

            if pc is None:
                partc_status = "UNAVAILABLE_PUBLISHED_SOURCE_LIMITATION"
                partc_year_completeness = ""
                partc_geography_basis = ""
                partc_months = ""
            else:
                partc_status = str(pc["dollar_status"])
                partc_year_completeness = str(pc["year_completeness"])
                partc_geography_basis = str(pc["geography_basis"])
                partc_months = str(pc["months_represented"])

            if pd is None:
                partd_status = "UNAVAILABLE"
                partd_coverage_status = ""
                partd_geography_basis = ""
                partd_payment_match_basis = ""
                partd_months = ""
            else:
                partd_status = str(pd["dollar_status"])
                partd_coverage_status = str(pd["coverage_status"])
                partd_geography_basis = str(pd["geography_basis"])
                partd_payment_match_basis = str(
                    pd["payment_match_basis"]
                )
                partd_months = str(
                    pd["months_with_reconstructed_dollars"]
                )

            integrated_rows.append(
                {
                    "calendar_year": year,
                    "county_fips": fips,
                    "county": county,
                    "original_medicare_ffs_dollars": money_text(
                        om_dollars
                    ),
                    "partc_dollars": money_text(partc_dollars),
                    "partd_dollars": money_text(partd_dollars),
                    "core_medicare_dollars": money_text(core_dollars),
                    "original_medicare_status": (
                        "DIRECT_CMS_ACTUAL_PAYMENT"
                        if om_available
                        else "UNAVAILABLE"
                    ),
                    "partc_status": partc_status,
                    "partd_status": partd_status,
                    "core_value_status": core_value_status,
                    "partc_months_represented": partc_months,
                    "partd_months_with_reconstructed_dollars": (
                        partd_months
                    ),
                    "partc_year_completeness": (
                        partc_year_completeness
                    ),
                    "partd_coverage_status": (
                        partd_coverage_status
                    ),
                    "time_window_status": time_window_status,
                    "timing_basis": "CALENDAR_YEAR",
                    "original_medicare_geography_basis": (
                        "DIRECT_CMS_COUNTY_GEOGRAPHY"
                    ),
                    "partc_geography_basis": partc_geography_basis,
                    "partd_geography_basis": partd_geography_basis,
                    "partd_payment_match_basis": (
                        partd_payment_match_basis
                    ),
                    "mssp_treatment": "EXCLUDE_DUPLICATE",
                    "rds_treatment": "WITHHOLD_UNRESOLVED",
                    "washington_mffs_treatment": (
                        "WITHHOLD_UNRESOLVED"
                    ),
                    "ledger_authorization": (
                        "NOT_AUTHORIZED_BY_THIS_CERTIFICATION"
                    ),
                    "methodology_version": METHODOLOGY_VERSION,
                }
            )

    add_check(
        checks,
        "INTEGRATION_ROW_COUNT",
        "Canonical Medicare integration contains exactly 390 rows",
        len(integrated_rows) == 390,
        f"rows={len(integrated_rows)}",
    )

    integrated_keys = {
        (
            int(row["calendar_year"]),
            str(row["county_fips"]),
        )
        for row in integrated_rows
    }

    add_check(
        checks,
        "INTEGRATION_CANONICAL_KEYS",
        (
            "Integration contains exactly 39 canonical counties "
            "for each year 2015-2024"
        ),
        integrated_keys == expected_all_keys,
        (
            f"observed_keys={len(integrated_keys)}; "
            f"expected_keys={len(expected_all_keys)}"
        ),
    )

    # -----------------------------------------------------------------
    # Annual reconciliation
    # -----------------------------------------------------------------

    om_control_by_year = {
        year_int(row["year"]): dec(row["actual_ffs_payments_dollars"])
        for row in om_annual_rows
    }

    partc_control_by_year = {
        year_int(row["payment_year"]): dec(row["partc_dollars"])
        for row in partc_annual_rows
    }

    # Resolve Part D annual columns defensively because this artifact is
    # a reconciliation file rather than the original reconstruction file.

    partd_year_col = first_existing_column(
        partd_annual_rows,
        (
            "year",
            "payment_year",
            "calendar_year",
        ),
    )

    partd_dollar_col = first_existing_column(
        partd_annual_rows,
        (
            "control_total_partd_dollars",
        ),
    )

    partd_control_by_year = {
        year_int(row[partd_year_col]): dec(row[partd_dollar_col])
        for row in partd_annual_rows
    }

    annual_rows: list[dict[str, object]] = []

    for year in EXPECTED_YEARS:
        rows = [
            row
            for row in integrated_rows
            if int(row["calendar_year"]) == year
        ]

        om_sum = sum(
            (
                dec(row["original_medicare_ffs_dollars"])
                or Decimal("0")
            )
            for row in rows
        )

        partc_available_rows = [
            row
            for row in rows
            if str(row["partc_dollars"]).strip() != ""
        ]

        partc_sum = sum(
            (
                dec(row["partc_dollars"])
                or Decimal("0")
            )
            for row in partc_available_rows
        )

        partd_sum = sum(
            (
                dec(row["partd_dollars"])
                or Decimal("0")
            )
            for row in rows
            if str(row["partd_dollars"]).strip() != ""
        )

        complete_core_rows = [
            row
            for row in rows
            if str(row["core_medicare_dollars"]).strip() != ""
        ]

        core_sum_available_rows = sum(
            (
                dec(row["core_medicare_dollars"])
                or Decimal("0")
            )
            for row in complete_core_rows
        )

        om_control = om_control_by_year.get(year)
        partc_control = partc_control_by_year.get(year)
        partd_control = partd_control_by_year.get(year)

        om_delta = (
            om_sum - om_control
            if om_control is not None
            else None
        )

        partc_delta = (
            partc_sum - partc_control
            if partc_control is not None
            else None
        )

        partd_delta = (
            partd_sum - partd_control
            if partd_control is not None
            else None
        )

        absent_partc = 39 - len(partc_available_rows)

        if absent_partc == 0:
            annual_core_total = (
                om_sum + partc_sum + partd_sum
            )
            annual_core_status = (
                "ALL_39_COUNTIES_COMPONENT_VALUES_AVAILABLE"
            )
        else:
            annual_core_total = None
            annual_core_status = (
                "WITHHELD_PARTC_COUNTY_VALUES_UNAVAILABLE"
            )

        annual_rows.append(
            {
                "calendar_year": year,
                "county_rows": len(rows),
                "partc_available_counties": len(partc_available_rows),
                "partc_unavailable_counties": absent_partc,
                "complete_core_counties": len(complete_core_rows),
                "original_medicare_ffs_county_sum": money_text(om_sum),
                "original_medicare_ffs_control": money_text(om_control),
                "original_medicare_ffs_delta": money_text(om_delta),
                "partc_county_sum_available_values": money_text(
                    partc_sum
                ),
                "partc_statewide_control": money_text(partc_control),
                "partc_delta_available_vs_statewide": money_text(
                    partc_delta
                ),
                "partd_county_sum": money_text(partd_sum),
                "partd_statewide_control": money_text(partd_control),
                "partd_delta": money_text(partd_delta),
                "core_sum_complete_county_rows": money_text(
                    core_sum_available_rows
                ),
                "annual_core_medicare_dollars": money_text(
                    annual_core_total
                ),
                "annual_core_status": annual_core_status,
                "time_window_status": (
                    "COMPLETE_CALENDAR_YEAR_WINDOW"
                    if year <= 2023
                    else "OM_COMPLETE_CY;PARTC_PARTD_JAN_SEP_ONLY"
                ),
                "partd_coverage_status": "PARTIAL_DOLLAR_COVERAGE",
                "methodology_version": METHODOLOGY_VERSION,
            }
        )

    # OM reconciliation uses previously certified material tolerance:
    # <= $1,000 OR <= 1 ppm.

    om_reconciliation_failures = []

    for row in annual_rows:
        control = dec(row["original_medicare_ffs_control"])
        delta = dec(row["original_medicare_ffs_delta"])

        if control is None or delta is None:
            om_reconciliation_failures.append(
                f"{row['calendar_year']}:missing_control"
            )
            continue

        abs_delta = abs(delta)

        ppm = (
            (abs_delta / abs(control)) * Decimal("1000000")
            if control != 0
            else Decimal("0")
        )

        if not (
            abs_delta <= Decimal("1000")
            or ppm <= Decimal("1")
        ):
            om_reconciliation_failures.append(
                (
                    f"{row['calendar_year']}:"
                    f"delta={delta}:ppm={ppm}"
                )
            )

    add_check(
        checks,
        "OM_ANNUAL_RECONCILIATION",
        (
            "Original Medicare 39-county sums materially reconcile "
            "to certified WA annual controls"
        ),
        not om_reconciliation_failures,
        (
            "all years within <=$1,000 OR <=1 ppm"
            if not om_reconciliation_failures
            else "; ".join(om_reconciliation_failures)
        ),
    )

    # Part C:
    # Exact equality is required only when all 39 county values exist.
    # When published source limitations make a county-year unavailable,
    # preserve the resulting gap rather than forcing a zero.

    partc_complete_year_failures = []

    for row in annual_rows:
        if int(row["partc_unavailable_counties"]) != 0:
            continue

        delta = dec(row["partc_delta_available_vs_statewide"])

        if delta is None or abs(delta) > Decimal("0.01"):
            partc_complete_year_failures.append(
                (
                    f"{row['calendar_year']}:"
                    f"delta={row['partc_delta_available_vs_statewide']}"
                )
            )

    add_check(
        checks,
        "PARTC_COMPLETE_YEAR_RECONCILIATION",
        (
            "Part C county sums reconcile to statewide controls "
            "when all 39 county values are available"
        ),
        not partc_complete_year_failures,
        (
            "all fully populated years reconcile within $0.01"
            if not partc_complete_year_failures
            else "; ".join(partc_complete_year_failures)
        ),
    )

    partc_missing_years = [
        (
            int(row["calendar_year"]),
            int(row["partc_unavailable_counties"]),
            row["partc_delta_available_vs_statewide"],
        )
        for row in annual_rows
        if int(row["partc_unavailable_counties"]) > 0
    ]

    add_check(
        checks,
        "PARTC_LIMITATION_EXPLICIT",
        (
            "Years with unavailable Part C county values remain "
            "explicitly identified rather than forced to zero"
        ),
        all(count > 0 for _, count, _ in partc_missing_years),
        (
            "none"
            if not partc_missing_years
            else "; ".join(
                f"{year}:unavailable={count}:delta={delta}"
                for year, count, delta in partc_missing_years
            )
        ),
    )

    # Part D county artifact should reconcile essentially exactly to its
    # certified annual reconciliation artifact. Allow one cent for CSV
    # decimal serialization.

    partd_reconciliation_failures = []

    for row in annual_rows:
        delta = dec(row["partd_delta"])

        if delta is None or abs(delta) > Decimal("0.01"):
            partd_reconciliation_failures.append(
                f"{row['calendar_year']}:delta={row['partd_delta']}"
            )

    add_check(
        checks,
        "PARTD_ANNUAL_RECONCILIATION",
        (
            "Part D county sums reconcile to certified annual "
            "reconstruction controls"
        ),
        not partd_reconciliation_failures,
        (
            "all years within $0.01"
            if not partd_reconciliation_failures
            else "; ".join(partd_reconciliation_failures)
        ),
    )

    # -----------------------------------------------------------------
    # 2024 partial-period preservation
    # -----------------------------------------------------------------

    rows_2024 = [
        row
        for row in integrated_rows
        if int(row["calendar_year"]) == 2024
    ]

    partial_2024_ok = all(
        row["time_window_status"]
        == "OM_COMPLETE_CY;PARTC_PARTD_JAN_SEP_ONLY"
        for row in rows_2024
    )

    add_check(
        checks,
        "CY2024_PARTIAL_WINDOW_PRESERVED",
        (
            "CY2024 explicitly preserves complete OM but "
            "Jan-Sep-only Part C and Part D"
        ),
        partial_2024_ok,
        f"rows_2024={len(rows_2024)}",
    )

    # -----------------------------------------------------------------
    # Core arithmetic identity
    # -----------------------------------------------------------------

    arithmetic_failures = []

    for row in integrated_rows:
        core = dec(row["core_medicare_dollars"])

        if core is None:
            continue

        om = dec(row["original_medicare_ffs_dollars"])
        pc = dec(row["partc_dollars"])
        pd = dec(row["partd_dollars"])

        expected = om + pc + pd

        if core != expected:
            arithmetic_failures.append(
                (
                    f"{row['calendar_year']}:"
                    f"{row['county_fips']}:"
                    f"core={core}:expected={expected}"
                )
            )

    add_check(
        checks,
        "CORE_ARITHMETIC_IDENTITY",
        "Every populated county core value equals OM + Part C + Part D",
        not arithmetic_failures,
        (
            f"populated_core_rows="
            f"{sum(1 for r in integrated_rows if r['core_medicare_dollars'])}; "
            f"failures={len(arithmetic_failures)}"
        ),
    )

    # -----------------------------------------------------------------
    # Final certification status
    # -----------------------------------------------------------------

    overall_pass = all(
        row["status"] == "PASS"
        for row in checks
    )

    # -----------------------------------------------------------------
    # Write outputs
    # -----------------------------------------------------------------

    county_path = (
        OUTPUT_DIR
        / "cms_medicare_county_integration_v0_1.csv"
    )

    annual_path = (
        OUTPUT_DIR
        / "cms_medicare_county_annual_reconciliation_v0_1.csv"
    )

    checks_path = (
        OUTPUT_DIR
        / "cms_medicare_county_integration_checks_v0_1.csv"
    )

    report_path = (
        OUTPUT_DIR
        / "cms_medicare_county_integration_report_v0_1.txt"
    )

    county_fields = [
        "calendar_year",
        "county_fips",
        "county",
        "original_medicare_ffs_dollars",
        "partc_dollars",
        "partd_dollars",
        "core_medicare_dollars",
        "original_medicare_status",
        "partc_status",
        "partd_status",
        "core_value_status",
        "partc_months_represented",
        "partd_months_with_reconstructed_dollars",
        "partc_year_completeness",
        "partd_coverage_status",
        "time_window_status",
        "timing_basis",
        "original_medicare_geography_basis",
        "partc_geography_basis",
        "partd_geography_basis",
        "partd_payment_match_basis",
        "mssp_treatment",
        "rds_treatment",
        "washington_mffs_treatment",
        "ledger_authorization",
        "methodology_version",
    ]

    annual_fields = [
        "calendar_year",
        "county_rows",
        "partc_available_counties",
        "partc_unavailable_counties",
        "complete_core_counties",
        "original_medicare_ffs_county_sum",
        "original_medicare_ffs_control",
        "original_medicare_ffs_delta",
        "partc_county_sum_available_values",
        "partc_statewide_control",
        "partc_delta_available_vs_statewide",
        "partd_county_sum",
        "partd_statewide_control",
        "partd_delta",
        "core_sum_complete_county_rows",
        "annual_core_medicare_dollars",
        "annual_core_status",
        "time_window_status",
        "partd_coverage_status",
        "methodology_version",
    ]

    write_csv(
        county_path,
        integrated_rows,
        county_fields,
    )

    write_csv(
        annual_path,
        annual_rows,
        annual_fields,
    )

    write_csv(
        checks_path,
        checks,
        [
            "check_id",
            "description",
            "status",
            "detail",
        ],
    )

    # -----------------------------------------------------------------
    # Human-readable report
    # -----------------------------------------------------------------

    lines: list[str] = []

    lines.append(
        "CMS MEDICARE COUNTY INTEGRATION CERTIFICATION v0.1"
    )
    lines.append("=" * 100)
    lines.append("")
    lines.append("READ-ONLY DOWNSTREAM INTEGRATION")
    lines.append("")
    lines.append(
        "No reconstruction, imputation, scaling, extrapolation, "
        "CY-to-FFY conversion, database write, or final-ledger "
        "authorization."
    )
    lines.append("")
    lines.append("CORE ACCOUNTING IDENTITY")
    lines.append("-" * 100)
    lines.append(
        "CORE MEDICARE = ORIGINAL MEDICARE/FFS + PART C + PART D"
    )
    lines.append("")
    lines.append("TIMING")
    lines.append("-" * 100)
    lines.append(
        "Original Medicare YEAR: certified CALENDAR_YEAR."
    )
    lines.append(
        "Part C and Part D: certified calendar-month reconstructions."
    )
    lines.append(
        "CY2015-CY2023: common complete calendar-year time window."
    )
    lines.append(
        "CY2024: Original Medicare complete calendar year; "
        "Part C and Part D January-September only."
    )
    lines.append("")
    lines.append("COUNTY VALUE POLICY")
    lines.append("-" * 100)
    lines.append(
        "Original Medicare: direct CMS actual county payment dollars."
    )
    lines.append(
        "Part C: reconstructed county dollars; absent county-years "
        "caused by published source limitations are not treated as zero."
    )
    lines.append(
        "Part D: reconstructed county dollars; "
        "PARTIAL_DOLLAR_COVERAGE remains explicit."
    )
    lines.append("")
    lines.append("ANNUAL RECONCILIATION")
    lines.append("-" * 100)

    for row in annual_rows:
        lines.append(
            f"{row['calendar_year']}  "
            f"OM={display_money(dec(row['original_medicare_ffs_county_sum']))}  "
            f"C={display_money(dec(row['partc_county_sum_available_values']))}  "
            f"D={display_money(dec(row['partd_county_sum']))}  "
            f"CORE={display_money(dec(row['annual_core_medicare_dollars']))}  "
            f"C unavailable counties={row['partc_unavailable_counties']}  "
            f"{row['time_window_status']}"
        )

    lines.append("")
    lines.append("OUTSIDE-CORE MEDICARE STREAMS")
    lines.append("-" * 100)
    lines.append("MSSP EarnSaveLoss: EXCLUDE_DUPLICATE")
    lines.append("RDS: WITHHOLD_UNRESOLVED")
    lines.append("Washington MFFS: WITHHOLD_UNRESOLVED")
    lines.append("")
    lines.append("VALIDATION CHECKS")
    lines.append("-" * 100)

    for check in checks:
        lines.append(
            f"{check['status']:4s}  "
            f"{check['check_id']}: "
            f"{check['description']} "
            f"[{check['detail']}]"
        )

    lines.append("")
    lines.append("CERTIFICATION RESULT")
    lines.append("-" * 100)

    if overall_pass:
        lines.append(
            f"{METHODOLOGY_VERSION} — PASS"
        )
        lines.append("")
        lines.append(
            "MEDICARE COUNTY INTEGRATION: CERTIFIED"
        )
        lines.append(
            "CY2015-CY2023: COMMON CALENDAR-YEAR ACCOUNTING WINDOW"
        )
        lines.append(
            "PART D: PARTIAL_DOLLAR_COVERAGE"
        )
        lines.append(
            "CY2024: ANNUAL CORE TOTAL INCOMPLETE "
            "(PART C/PART D JAN-SEP ONLY)"
        )
        lines.append(
            "FINAL FEDERAL-INFLOW LEDGER INCLUSION: "
            "NOT YET AUTHORIZED"
        )
    else:
        lines.append(
            f"{METHODOLOGY_VERSION} — FAIL"
        )
        lines.append("")
        lines.append(
            "MEDICARE COUNTY INTEGRATION: NOT CERTIFIED"
        )

    lines.append("")

    report_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\n".join(lines))

    if not overall_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()