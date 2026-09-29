"""
CMS Medicare Accounting Boundary Certification v0.1
====================================================

Purpose
-------
Certify the accounting boundary for the principal Washington Medicare
federal-inflow streams after completion of the underlying source,
reconstruction, geography, overlap, and additivity work.

Principal core identity
-----------------------
For Washington and county c:

    CORE_MEDICARE = ORIGINAL_MEDICARE_FFS + PART_C + PART_D

This certification does NOT claim that CORE_MEDICARE is a complete measure
of every Medicare-related federal expenditure.

It explicitly preserves separately evaluated streams:

    MSSP  -> EXCLUDE_DUPLICATE
    RDS   -> WITHHOLD_UNRESOLVED
    MFFS  -> WITHHOLD_UNRESOLVED

Methodological boundary
-----------------------
READ ONLY.

This script does NOT:
    * reconstruct any Medicare payment,
    * impute suppressed enrollment,
    * fill unmatched Part D payment cells,
    * allocate unresolved programs,
    * extrapolate CY2024,
    * scale Washington to Trustees controls,
    * convert CY to FFY,
    * modify source artifacts,
    * write to PostgreSQL,
    * authorize a final federal-inflow ledger.

The purpose is narrower:

    Determine whether the three principal Medicare streams may be treated
    as additive within a common accounting boundary, while preserving all
    known coverage and timing qualifications.

Expected result
---------------
CY2015-CY2023:
    CORE_ACCOUNTING_BOUNDARY_CERTIFIED
    PARTIAL_DOLLAR_COVERAGE because Part D remains partial-dollar coverage.

CY2024:
    ACCOUNTING_STRUCTURE_CERTIFIED_ANNUAL_TOTAL_INCOMPLETE
    because Part C and Part D contain Jan-Sep only.

MSSP:
    EXCLUDE_DUPLICATE

RDS:
    WITHHOLD_UNRESOLVED

MFFS:
    WITHHOLD_UNRESOLVED
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


getcontext().prec = 40


REPO_ROOT = Path(__file__).resolve().parents[1]


INTEGRATION_PROFILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare"
    / "validation"
    / "accounting_integration_v0_1"
    / "cms_medicare_core_annual_profile_v0_1.csv"
)


ADDITIVITY_MATRIX = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare"
    / "validation"
    / "payment_stream_additivity_v0_1"
    / "cms_medicare_payment_stream_overlap_matrix_v0_1.csv"
)


ADDITIVITY_CHECKS = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare"
    / "validation"
    / "payment_stream_additivity_v0_1"
    / "cms_medicare_payment_stream_additivity_checks_v0_1.csv"
)


RDS_MATRIX = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_rds"
    / "validation"
    / "rds_semantic_additivity_v0_1"
    / "cms_rds_overlap_matrix_v0_1.csv"
)


MFFS_MATRIX = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_mffs"
    / "washington"
    / "validation"
    / "ffs_overlap_v0_2"
    / "cms_wa_mffs_ffs_overlap_matrix_v0_1.csv"
)


OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare"
    / "validation"
    / "accounting_boundary_v0_1"
)


EXPECTED_YEARS = list(range(2015, 2025))

METHODOLOGY_VERSION = "CMS-MEDICARE-ACCOUNTING-BOUNDARY-v0.1"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required artifact not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, str]],
    fieldnames: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def decimal_value(value: str | None, label: str) -> Decimal:
    text = normalize(value)

    if text == "":
        raise ValueError(f"Blank numeric value: {label}")

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"Invalid numeric value for {label}: {value!r}"
        ) from exc


def int_value(value: str | None, label: str) -> int:
    value_decimal = decimal_value(value, label)

    if value_decimal != value_decimal.to_integral_value():
        raise ValueError(
            f"Non-integral value for {label}: {value!r}"
        )

    return int(value_decimal)


def money_text(value: Decimal) -> str:
    return f"{value:,.2f}"


def pass_fail(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


def require_columns(
    rows: list[dict[str, str]],
    required: set[str],
    source_name: str,
) -> None:
    if not rows:
        raise ValueError(f"{source_name}: no rows found")

    actual = set(rows[0].keys())
    missing = sorted(required - actual)

    if missing:
        raise ValueError(
            f"{source_name}: missing required columns: {missing}. "
            f"Available columns: {sorted(actual)}"
        )


def all_text(rows: list[dict[str, str]]) -> str:
    values: list[str] = []

    for row in rows:
        for value in row.values():
            if value is not None:
                values.append(str(value))

    return " ".join(values).upper()


def find_terms(
    text: str,
    terms: list[str],
) -> list[str]:
    return [
        term
        for term in terms
        if term.upper() in text
    ]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    integration = read_csv(INTEGRATION_PROFILE)
    additivity_matrix = read_csv(ADDITIVITY_MATRIX)
    additivity_checks = read_csv(ADDITIVITY_CHECKS)
    rds_matrix = read_csv(RDS_MATRIX)
    mffs_matrix = read_csv(MFFS_MATRIX)

    require_columns(
        integration,
        {
            "year",
            "original_medicare_actual_ffs_dollars",
            "partc_reconstructed_dollars",
            "partd_reconstructed_dollars",
            "core_medicare_sum_dollars",
            "partc_months_processed",
            "partc_year_completeness",
            "partd_coverage_status",
            "combined_period_status",
            "ledger_status",
        },
        "Medicare accounting integration profile",
    )

    #
    # We deliberately do not hard-code the schemas of the earlier overlap
    # artifacts here. They were produced by frozen certification scripts at
    # different stages and may use different field names.
    #
    # Instead, this boundary certification verifies:
    #   1. the artifacts are non-empty,
    #   2. their certification vocabulary contains the required stream and
    #      disposition concepts,
    #   3. the frozen additivity check artifact contains no FAIL status.
    #
    # This avoids silently rewriting historical certification artifacts.
    #

    additivity_matrix_text = all_text(additivity_matrix)
    additivity_checks_text = all_text(additivity_checks)
    rds_text = all_text(rds_matrix)
    mffs_text = all_text(mffs_matrix)

    checks: list[dict[str, str]] = []

    def add_check(
        check_id: str,
        description: str,
        condition: bool,
        detail: str,
    ) -> None:
        checks.append(
            {
                "check_id": check_id,
                "description": description,
                "status": pass_fail(condition),
                "detail": detail,
            }
        )

    #
    # Integration universe
    #

    years = [
        int_value(row["year"], "integration.year")
        for row in integration
    ]

    add_check(
        "INTEGRATION_YEAR_UNIVERSE",
        "Integration profile exactly covers CY2015-CY2024",
        sorted(years) == EXPECTED_YEARS
        and len(years) == len(EXPECTED_YEARS),
        f"years={sorted(years)}",
    )

    add_check(
        "INTEGRATION_UNIQUE_YEARS",
        "Integration profile has one row per year",
        len(set(years)) == len(years),
        f"rows={len(years)} distinct_years={len(set(years))}",
    )

    #
    # Re-test the arithmetic identity rather than trusting the prior output.
    #

    max_identity_diff = Decimal("0")

    for row in integration:
        year = int_value(row["year"], "integration.year")

        om = decimal_value(
            row["original_medicare_actual_ffs_dollars"],
            f"{year}.OM",
        )

        partc = decimal_value(
            row["partc_reconstructed_dollars"],
            f"{year}.PartC",
        )

        partd = decimal_value(
            row["partd_reconstructed_dollars"],
            f"{year}.PartD",
        )

        reported = decimal_value(
            row["core_medicare_sum_dollars"],
            f"{year}.core",
        )

        diff = abs((om + partc + partd) - reported)

        if diff > max_identity_diff:
            max_identity_diff = diff

    add_check(
        "CORE_ARITHMETIC_IDENTITY",
        "OM + Part C + Part D reproduces the reported core Medicare sum",
        max_identity_diff <= Decimal("0.01"),
        f"max_abs_difference=${money_text(max_identity_diff)}",
    )

    #
    # Frozen payment-stream additivity evidence.
    #

    required_core_terms = [
        "ORIGINAL",
        "PART C",
        "PART D",
    ]

    core_terms_found = find_terms(
        additivity_matrix_text,
        required_core_terms,
    )

    #
    # Historical artifacts may use FFS rather than ORIGINAL MEDICARE.
    #
    ffs_present = "FFS" in additivity_matrix_text

    om_present = (
        "ORIGINAL" in core_terms_found
        or ffs_present
    )

    partc_present = (
        "PART C" in core_terms_found
        or "PART_C" in additivity_matrix_text
        or "PARTC" in additivity_matrix_text
    )

    partd_present = (
        "PART D" in core_terms_found
        or "PART_D" in additivity_matrix_text
        or "PARTD" in additivity_matrix_text
    )

    add_check(
        "ADDITIVITY_CORE_STREAMS_PRESENT",
        "Frozen additivity matrix identifies OM/FFS, Part C, and Part D",
        om_present and partc_present and partd_present,
        (
            f"om_or_ffs={om_present}; "
            f"partc={partc_present}; "
            f"partd={partd_present}"
        ),
    )

    fail_token_present = (
        "FAIL" in additivity_checks_text
    )

    add_check(
        "ADDITIVITY_CHECKS_NO_FAIL",
        "Frozen payment-stream additivity checks contain no FAIL result",
        not fail_token_present,
        (
            f"rows={len(additivity_checks)}; "
            f"FAIL_token_present={fail_token_present}"
        ),
    )

    additive_language_present = (
        "ADDITIVE" in additivity_matrix_text
    )

    add_check(
        "ADDITIVITY_DISPOSITION_PRESENT",
        "Frozen overlap matrix contains an additive disposition",
        additive_language_present,
        f"ADDITIVE_token_present={additive_language_present}",
    )

    #
    # Known separately evaluated streams.
    #

       #
    # RDS frozen additivity evidence.
    #
    # The certified RDS overlap matrix evaluates RDS pairwise against
    # Original Medicare/FFS, Part C, and Part D.  The accounting-boundary
    # requirement is:
    #
    #   * exactly three evaluated pairwise relationships,
    #   * payment_stream_overlap = NO for every relationship,
    #   * classification = ADDITIVE for every relationship.
    #
    # Geographic allocatability is deliberately NOT tested here.  The
    # separate RDS certification concluded that Washington incidence
    # remains unresolved / NOT_YET_WA_ALLOCATABLE, which is why RDS is
    # withheld from the Washington core rather than included or treated
    # as zero.
    #

    require_columns(
        rds_matrix,
        {
            "stream_a",
            "stream_b",
            "payment_stream_overlap",
            "classification",
        },
        "RDS semantic additivity matrix",
    )

    expected_rds_counterparts = {
        "MEDICARE_PART_D",
        "ORIGINAL_MEDICARE_FFS",
        "MEDICARE_PART_C",
    }

    rds_counterparts = {
        normalize(row["stream_b"]).upper()
        for row in rds_matrix
        if normalize(row["stream_a"]).upper()
        == "RETIREE_DRUG_SUBSIDY"
    }

    rds_pair_count_ok = (
        len(rds_matrix) == 3
        and rds_counterparts == expected_rds_counterparts
    )

    rds_no_payment_overlap = all(
        normalize(row["payment_stream_overlap"]).upper() == "NO"
        for row in rds_matrix
    )

    rds_all_additive = all(
        normalize(row["classification"]).upper() == "ADDITIVE"
        for row in rds_matrix
    )

    rds_additive_in_principle = (
        rds_pair_count_ok
        and rds_no_payment_overlap
        and rds_all_additive
    )

    add_check(
        "RDS_SEPARATE_STREAM_EVIDENCE",
        (
            "Frozen RDS matrix establishes RDS as economically "
            "additive to OM/FFS, Part C, and Part D"
        ),
        rds_additive_in_principle,
        (
            f"pair_count={len(rds_matrix)}; "
            f"counterparts={sorted(rds_counterparts)}; "
            f"all_payment_stream_overlap_NO={rds_no_payment_overlap}; "
            f"all_classification_ADDITIVE={rds_all_additive}"
        ),
    )

    mffs_additive_in_principle = (
        "ADDITIVE_IN_PRINCIPLE" in mffs_text
        or (
            "ADDITIVE" in mffs_text
            and "OVERLAP" in mffs_text
        )
    )

    add_check(
        "MFFS_SEPARATE_STREAM_EVIDENCE",
        "Frozen MFFS artifact supports separate/additive-in-principle treatment",
        mffs_additive_in_principle,
        (
            "expected additive-in-principle or equivalent "
            "economic-overlap disposition"
        ),
    )

    #
    # Coverage/timing boundary.
    #

    rows_by_year = {
        int_value(row["year"], "integration.year"): row
        for row in integration
    }

    complete_2015_2023 = all(
        normalize(rows_by_year[year]["combined_period_status"])
        == "COMPLETE_CALENDAR_YEAR_WINDOW"
        for year in range(2015, 2024)
    )

    add_check(
        "CORE_2015_2023_FULL_YEAR_WINDOW",
        "CY2015-CY2023 have complete calendar-year time windows",
        complete_2015_2023,
        "expected COMPLETE_CALENDAR_YEAR_WINDOW",
    )

    partd_partial_all_years = all(
        normalize(row["partd_coverage_status"])
        == "PARTIAL_DOLLAR_COVERAGE"
        for row in integration
    )

    add_check(
        "PARTD_PARTIAL_COVERAGE_PRESERVED",
        "Part D partial-dollar coverage is preserved in every integration year",
        partd_partial_all_years,
        "expected PARTIAL_DOLLAR_COVERAGE for all rows",
    )

    row_2024 = rows_by_year.get(2024)

    partial_2024 = (
        row_2024 is not None
        and normalize(row_2024["combined_period_status"])
        == "MIXED_2024_PARTIAL_PARTC_PARTD"
        and int_value(
            row_2024["partc_months_processed"],
            "2024.partc_months_processed",
        )
        == 9
    )

    add_check(
        "CY2024_PARTIAL_PRESERVED",
        "CY2024 remains incomplete because Part C and Part D are Jan-Sep",
        partial_2024,
        (
            "expected MIXED_2024_PARTIAL_PARTC_PARTD "
            "and Part C months=9"
        ),
    )

    no_prior_ledger_authorization = all(
        normalize(row["ledger_status"])
        == "NOT_YET_AUTHORIZED"
        for row in integration
    )

    add_check(
        "PRIOR_LEDGER_STATUS_PRESERVED",
        "Input integration profile had not authorized ledger inclusion",
        no_prior_ledger_authorization,
        "expected NOT_YET_AUTHORIZED for every input row",
    )

    #
    # Build annual accounting-boundary artifact.
    #

    annual_rows: list[dict[str, str]] = []

    for year in EXPECTED_YEARS:
        row = rows_by_year[year]

        om = decimal_value(
            row["original_medicare_actual_ffs_dollars"],
            f"{year}.OM",
        )

        partc = decimal_value(
            row["partc_reconstructed_dollars"],
            f"{year}.PartC",
        )

        partd = decimal_value(
            row["partd_reconstructed_dollars"],
            f"{year}.PartD",
        )

        core = om + partc + partd

        if year <= 2023:
            boundary_status = "CORE_ACCOUNTING_BOUNDARY_CERTIFIED"
            annual_completeness = (
                "FULL_YEAR_WINDOW_PARTD_PARTIAL_DOLLAR_COVERAGE"
            )
        else:
            boundary_status = (
                "ACCOUNTING_STRUCTURE_CERTIFIED_ANNUAL_TOTAL_INCOMPLETE"
            )
            annual_completeness = (
                "PARTC_PARTD_JAN_SEP_ONLY;"
                "PARTD_PARTIAL_DOLLAR_COVERAGE"
            )

        annual_rows.append(
            {
                "year": str(year),
                "original_medicare_ffs_dollars": str(om),
                "partc_dollars": str(partc),
                "partd_dollars": str(partd),
                "core_medicare_dollars": str(core),
                "core_identity": (
                    "ORIGINAL_MEDICARE_FFS+PART_C+PART_D"
                ),
                "payment_stream_additivity": "CERTIFIED_ADDITIVE",
                "partd_coverage_status": "PARTIAL_DOLLAR_COVERAGE",
                "annual_completeness": annual_completeness,
                "accounting_boundary_status": boundary_status,
                "mssp_treatment": "EXCLUDE_DUPLICATE",
                "rds_treatment": "WITHHOLD_UNRESOLVED",
                "mffs_treatment": "WITHHOLD_UNRESOLVED",
                "trustees_treatment": (
                    "DIAGNOSTIC_CONTROL_NOT_SCALING_TARGET"
                ),
                "ffy_conversion_status": "NOT_AUTHORIZED",
                "final_ledger_status": "NOT_YET_AUTHORIZED",
                "methodology_version": METHODOLOGY_VERSION,
            }
        )

    #
    # Stream disposition artifact.
    #

    stream_rows = [
        {
            "stream": "ORIGINAL_MEDICARE_FFS",
            "core_status": "INCLUDE_IN_CORE",
            "dollar_status": "OBSERVED_ACTUAL",
            "geography_status": "DIRECT_COUNTY",
            "coverage_status": "CERTIFIED_SOURCE_SCOPE",
            "overlap_treatment": "ADDITIVE_CORE_STREAM",
            "principal_limitation": (
                "YEAR_TIMING_LABEL_PRESERVED;"
                "NO_FFY_CONVERSION_AUTHORIZED"
            ),
        },
        {
            "stream": "PART_C",
            "core_status": "INCLUDE_IN_CORE",
            "dollar_status": "RECONSTRUCTED",
            "geography_status": "DIRECT_CPSC_COUNTY_GEOGRAPHY",
            "coverage_status": (
                "CERTIFIED_HMO_HMOPOS_PLUS_LOCAL_PPO_SCOPE"
            ),
            "overlap_treatment": "ADDITIVE_CORE_STREAM",
            "principal_limitation": (
                "CY2024_JAN_SEP_ONLY;"
                "SUPPRESSED_NONNUMERIC_ENROLLMENT_NOT_IMPUTED"
            ),
        },
        {
            "stream": "PART_D",
            "core_status": "INCLUDE_IN_CORE",
            "dollar_status": "RECONSTRUCTED",
            "geography_status": "DIRECT_CPSC_COUNTY_GEOGRAPHY",
            "coverage_status": "PARTIAL_DOLLAR_COVERAGE",
            "overlap_treatment": "ADDITIVE_CORE_STREAM",
            "principal_limitation": (
                "EXACT_SAME_YEAR_CONTRACT_PBP_MATCH_ONLY;"
                "UNMATCHED_DOLLARS_NOT_IMPUTED;"
                "CY2024_JAN_SEP_ONLY"
            ),
        },
        {
            "stream": "MSSP_EARNSAVELOSS",
            "core_status": "OUTSIDE_CORE",
            "dollar_status": "OBSERVED_PROGRAM_DOLLARS",
            "geography_status": "NOT_USED_FOR_CORE",
            "coverage_status": "SEPARATELY_CERTIFIED",
            "overlap_treatment": "EXCLUDE_DUPLICATE",
            "principal_limitation": (
                "OVERLAPS_PRINCIPAL_CMS_NATIVE_MEDICARE_ACCOUNTING"
            ),
        },
        {
            "stream": "RDS",
            "core_status": "OUTSIDE_CORE",
            "dollar_status": "FEDERAL_EXPENDITURE_OBSERVED",
            "geography_status": "WA_BENEFICIARY_INCIDENCE_ONLY",
            "coverage_status": "ADDITIVE_IN_PRINCIPLE",
            "overlap_treatment": "WITHHOLD_UNRESOLVED",
            "principal_limitation": (
                "WA_AND_COUNTY_PAYMENT_DOLLAR_INCIDENCE_UNRESOLVED"
            ),
        },
        {
            "stream": "WASHINGTON_MFFS",
            "core_status": "OUTSIDE_CORE",
            "dollar_status": "FEDERAL_EXPENDITURE_OBSERVED",
            "geography_status": "WA_STATE_INCIDENCE_OBSERVED",
            "coverage_status": "ADDITIVE_IN_PRINCIPLE",
            "overlap_treatment": "WITHHOLD_UNRESOLVED",
            "principal_limitation": (
                "ANNUAL_FFY_CASH_TIMING_AND_COUNTY_DOLLAR_INCIDENCE_UNRESOLVED"
            ),
        },
    ]

    #
    # Overall certification.
    #

    overall_pass = all(
        row["status"] == "PASS"
        for row in checks
    )

    annual_path = (
        OUTPUT_DIR
        / "cms_medicare_accounting_boundary_annual_v0_1.csv"
    )

    stream_path = (
        OUTPUT_DIR
        / "cms_medicare_stream_disposition_v0_1.csv"
    )

    checks_path = (
        OUTPUT_DIR
        / "cms_medicare_accounting_boundary_checks_v0_1.csv"
    )

    report_path = (
        OUTPUT_DIR
        / "cms_medicare_accounting_boundary_report_v0_1.txt"
    )

    write_csv(
        annual_path,
        annual_rows,
        [
            "year",
            "original_medicare_ffs_dollars",
            "partc_dollars",
            "partd_dollars",
            "core_medicare_dollars",
            "core_identity",
            "payment_stream_additivity",
            "partd_coverage_status",
            "annual_completeness",
            "accounting_boundary_status",
            "mssp_treatment",
            "rds_treatment",
            "mffs_treatment",
            "trustees_treatment",
            "ffy_conversion_status",
            "final_ledger_status",
            "methodology_version",
        ],
    )

    write_csv(
        stream_path,
        stream_rows,
        [
            "stream",
            "core_status",
            "dollar_status",
            "geography_status",
            "coverage_status",
            "overlap_treatment",
            "principal_limitation",
        ],
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

    #
    # Human-readable report.
    #

    lines: list[str] = []

    lines.append(
        "CMS MEDICARE ACCOUNTING BOUNDARY CERTIFICATION v0.1"
    )
    lines.append("=" * 100)
    lines.append("")
    lines.append("READ-ONLY CERTIFICATION")
    lines.append("")
    lines.append(
        "No reconstruction, imputation, extrapolation, scaling, "
        "CY-to-FFY conversion, DB writes, or final-ledger inclusion."
    )
    lines.append("")
    lines.append("CORE ACCOUNTING IDENTITY")
    lines.append("-" * 100)
    lines.append(
        "CORE_MEDICARE = ORIGINAL_MEDICARE_FFS + PART_C + PART_D"
    )
    lines.append("")
    lines.append("ANNUAL ACCOUNTING BOUNDARY")
    lines.append("-" * 100)

    for row in annual_rows:
        lines.append(
            f"{row['year']}  "
            f"CORE=${money_text(Decimal(row['core_medicare_dollars']))}  "
            f"{row['accounting_boundary_status']}  "
            f"{row['annual_completeness']}"
        )

    lines.append("")
    lines.append("STREAM DISPOSITIONS")
    lines.append("-" * 100)

    for row in stream_rows:
        lines.append(
            f"{row['stream']:24s} "
            f"{row['core_status']:15s} "
            f"{row['overlap_treatment']}"
        )

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
    lines.append("ACCOUNTING INTERPRETATION")
    lines.append("-" * 100)
    lines.append(
        "Original Medicare/FFS, Part C, and Part D are certified as "
        "additive payment streams within the defined core Medicare "
        "accounting boundary."
    )
    lines.append(
        "Beneficiary overlap does not imply payment-dollar overlap."
    )
    lines.append(
        "The core boundary is not asserted to contain every "
        "Medicare-related federal expenditure."
    )
    lines.append(
        "MSSP EarnSaveLoss is excluded as duplicate under the separately "
        "certified overlap policy."
    )
    lines.append(
        "RDS and Washington MFFS are additive in principle but remain "
        "withheld because their Washington/county dollar incidence or "
        "annual timing is unresolved."
    )
    lines.append(
        "Trustees evidence is diagnostic accounting evidence and is not "
        "used to scale or force-balance Washington reconstructed dollars."
    )
    lines.append(
        "CY2015-CY2023 have complete calendar-year time windows, but "
        "Part D retains PARTIAL_DOLLAR_COVERAGE."
    )
    lines.append(
        "CY2024 is not a complete annual core Medicare dollar total "
        "because Part C and Part D contain Jan-Sep only."
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
            "CORE MEDICARE ACCOUNTING BOUNDARY: CERTIFIED"
        )
        lines.append(
            "FINAL FEDERAL-INFLOW LEDGER INCLUSION: NOT YET AUTHORIZED"
        )
    else:
        lines.append(
            f"{METHODOLOGY_VERSION} — FAIL"
        )
        lines.append("")
        lines.append(
            "CORE MEDICARE ACCOUNTING BOUNDARY: NOT CERTIFIED"
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