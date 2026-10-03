"""
CMS Medicare Accounting Integration Profile v0.1
=================================================

Purpose
-------
Assemble the three certified principal Washington Medicare payment streams:

    1. Original Medicare / FFS
    2. Medicare Advantage Part C
    3. Medicare Part D

into a read-only annual accounting profile for CY2015-CY2024.

This script also inventories certified Medicare Trustees controls for the same
years, but DOES NOT assume that any Trustees series is directly comparable to
the Washington core Medicare sum.

Methodological boundary
-----------------------
READ ONLY.

This script does NOT:
    * modify source artifacts,
    * reconstruct PMPM values,
    * impute suppressed or unmatched enrollment,
    * extrapolate CY2024 Part C or Part D,
    * convert calendar-year observations to federal fiscal years,
    * scale Washington values to Trustees controls,
    * force any reconciliation,
    * write to PostgreSQL,
    * authorize ledger inclusion.

Principal accounting identity profiled
---------------------------------------
For county c and calendar year y:

    Core Medicare(c,y)
        = Original Medicare / FFS(c,y)
        + Part C(c,y)
        + Part D(c,y)

subject to the independently certified coverage and timing boundaries of
each component.

At the Washington annual level:

    Core Medicare(WA,y)
        = Original Medicare / FFS(WA,y)
        + Part C(WA,y)
        + Part D(WA,y)

The resulting sum is an integration candidate, not yet a certified final
Medicare ledger amount.

Important limitations
---------------------
* Original Medicare uses actual FFS payments. Standardized FFS payments are
  analytical and are not included in the accounting sum.
* Part C dollars are reconstructed.
* Part D dollars are reconstructed and have PARTIAL_DOLLAR_COVERAGE.
* CY2024 Part C and Part D are Jan-Sep only.
* No Trustees control is declared comparable in v0.1.
* MSSP EarnSaveLoss is excluded elsewhere as overlapping/non-additive.
* RDS and Washington MFFS remain withheld/unresolved elsewhere.
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


getcontext().prec = 40


REPO_ROOT = Path(__file__).resolve().parents[1]

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

TRUSTEES_CONTROLS = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_trustees"
    / "validation"
    / "preferred_vintage_certification_v0_1"
    / "trustees_preferred_vintage_controls.csv"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare"
    / "validation"
    / "accounting_integration_v0_1"
)

EXPECTED_YEARS = list(range(2015, 2025))

METHODOLOGY_VERSION = "CMS-MEDICARE-ACCOUNTING-INTEGRATION-PROFILE-v0.1"

MONEY_TOL = Decimal("0.01")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required source not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def decimal_value(value: str | None, field: str) -> Decimal:
    text = "" if value is None else str(value).strip()

    if text == "":
        raise ValueError(f"Blank numeric value for required field: {field}")

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"Invalid numeric value for {field}: {value!r}"
        ) from exc


def int_value(value: str | None, field: str) -> int:
    text = "" if value is None else str(value).strip()

    if text == "":
        raise ValueError(f"Blank integer value for required field: {field}")

    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"Invalid integer value for {field}: {value!r}"
        ) from exc


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


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
        raise ValueError(f"{source_name}: source contains no data rows")

    actual = set(rows[0].keys())
    missing = sorted(required - actual)

    if missing:
        raise ValueError(
            f"{source_name}: missing required columns: {missing}"
        )


def unique_year_map(
    rows: list[dict[str, str]],
    year_field: str,
    source_name: str,
) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}

    for row in rows:
        year = int_value(row.get(year_field), f"{source_name}.{year_field}")

        if year in result:
            raise ValueError(
                f"{source_name}: duplicate annual row for year {year}"
            )

        result[year] = row

    return result


def normalize(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    om_rows = read_csv(OM_ANNUAL)
    partc_rows = read_csv(PARTC_ANNUAL)
    partd_rows = read_csv(PARTD_ANNUAL)
    trustees_rows = read_csv(TRUSTEES_CONTROLS)

    require_columns(
        om_rows,
        {
            "year",
            "county_rows",
            "original_medicare_beneficiaries",
            "actual_ffs_payments_dollars",
            "standardized_ffs_payments_dollars",
        },
        "Original Medicare",
    )

    require_columns(
        partc_rows,
        {
            "payment_year",
            "months_processed",
            "published_enrollment",
            "reconstructed_enrollment",
            "source_unavailable_enrollment",
            "accounted_enrollment",
            "unexplained_enrollment",
            "partc_dollars",
            "reconstruction_coverage_pct",
            "accounting_coverage_pct",
            "year_completeness",
        },
        "Part C",
    )

    require_columns(
        partd_rows,
        {
            "year",
        },
        "Part D annual reconciliation",
    )

    require_columns(
        trustees_rows,
        {
            "table_id",
            "observation_year",
            "accounting_scope",
            "plan_type_normalized",
            "component_normalized",
            "unit",
            "basis",
            "selected_trustees_vintage",
            "selected_value",
            "preferred_vintage_status",
            "source_file",
            "source_page",
        },
        "Trustees preferred-vintage controls",
    )

    om_by_year = unique_year_map(
        om_rows,
        "year",
        "Original Medicare",
    )

    partc_by_year = unique_year_map(
        partc_rows,
        "payment_year",
        "Part C",
    )

    #
    # Part D annual reconciliation schema may carry both the frozen statewide
    # control and county-summed reconstruction. Discover the relevant dollar
    # fields explicitly rather than assuming a single historical column name.
    #
    partd_columns = set(partd_rows[0].keys())

    partd_dollar_candidates = [
        "county_total_partd_dollars",
        "county_sum_total_partd_dollars",
        "reconstructed_total_partd_dollars",
        "total_partd_dollars",
        "annual_total_partd_dollars",
        "control_total_partd_dollars",
        "source_total_partd_dollars",
    ]

    available_partd_dollar_fields = [
        field
        for field in partd_dollar_candidates
        if field in partd_columns
    ]

    if not available_partd_dollar_fields:
        raise ValueError(
            "Part D annual reconciliation does not contain any recognized "
            "Part D dollar field. Available columns are: "
            + ", ".join(sorted(partd_columns))
        )

    #
    # Prefer county-summed fields when present because this profile is testing
    # the county-ready integration path. The certification already established
    # reconciliation to the frozen v0.3 annual controls.
    #
    partd_dollar_field = available_partd_dollar_fields[0]

    partd_by_year = unique_year_map(
        partd_rows,
        "year",
        "Part D",
    )

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

    expected_year_set = set(EXPECTED_YEARS)

    add_check(
        "OM_YEAR_UNIVERSE",
        "Original Medicare annual rows exactly cover 2015-2024",
        set(om_by_year) == expected_year_set,
        f"years={sorted(om_by_year)}",
    )

    add_check(
        "PARTC_YEAR_UNIVERSE",
        "Part C annual rows exactly cover 2015-2024",
        set(partc_by_year) == expected_year_set,
        f"years={sorted(partc_by_year)}",
    )

    add_check(
        "PARTD_YEAR_UNIVERSE",
        "Part D annual rows exactly cover 2015-2024",
        set(partd_by_year) == expected_year_set,
        f"years={sorted(partd_by_year)}",
    )

    om_county_rows_ok = all(
        int_value(
            om_by_year[year]["county_rows"],
            f"Original Medicare {year} county_rows",
        )
        == 39
        for year in EXPECTED_YEARS
    )

    add_check(
        "OM_39_COUNTIES",
        "Original Medicare reports 39 county rows in every study year",
        om_county_rows_ok,
        "expected_county_rows=39",
    )

    partc_2015_2023_complete = all(
        normalize(partc_by_year[year]["year_completeness"])
        == "COMPLETE_CALENDAR_YEAR"
        and int_value(
            partc_by_year[year]["months_processed"],
            f"Part C {year} months_processed",
        )
        == 12
        for year in range(2015, 2024)
    )

    add_check(
        "PARTC_2015_2023_COMPLETE",
        "Part C CY2015-CY2023 are complete 12-month calendar years",
        partc_2015_2023_complete,
        "expected=COMPLETE_CALENDAR_YEAR and 12 months",
    )

    partc_2024_partial = (
        int_value(
            partc_by_year[2024]["months_processed"],
            "Part C 2024 months_processed",
        )
        == 9
    )

    add_check(
        "PARTC_2024_PARTIAL",
        "Part C CY2024 contains Jan-Sep only",
        partc_2024_partial,
        (
            "months_processed="
            + normalize(partc_by_year[2024]["months_processed"])
            + "; year_completeness="
            + normalize(partc_by_year[2024]["year_completeness"])
        ),
    )

    integration_rows: list[dict[str, str]] = []

    for year in EXPECTED_YEARS:
        om = om_by_year[year]
        pc = partc_by_year[year]
        pd = partd_by_year[year]

        om_actual = decimal_value(
            om["actual_ffs_payments_dollars"],
            f"Original Medicare {year} actual_ffs_payments_dollars",
        )

        pc_dollars = decimal_value(
            pc["partc_dollars"],
            f"Part C {year} partc_dollars",
        )

        pd_dollars = decimal_value(
            pd[partd_dollar_field],
            f"Part D {year} {partd_dollar_field}",
        )

        core_sum = om_actual + pc_dollars + pd_dollars

        if year <= 2023:
            combined_period_status = "COMPLETE_CALENDAR_YEAR_WINDOW"
        else:
            combined_period_status = "MIXED_2024_PARTIAL_PARTC_PARTD"

        integration_rows.append(
            {
                "year": str(year),
                "original_medicare_actual_ffs_dollars": decimal_text(
                    om_actual
                ),
                "partc_reconstructed_dollars": decimal_text(pc_dollars),
                "partd_reconstructed_dollars": decimal_text(pd_dollars),
                "core_medicare_sum_dollars": decimal_text(core_sum),
                "original_medicare_county_rows": normalize(
                    om["county_rows"]
                ),
                "original_medicare_beneficiaries": normalize(
                    om["original_medicare_beneficiaries"]
                ),
                "partc_months_processed": normalize(
                    pc["months_processed"]
                ),
                "partc_year_completeness": normalize(
                    pc["year_completeness"]
                ),
                "partc_reconstruction_coverage_pct": normalize(
                    pc["reconstruction_coverage_pct"]
                ),
                "partc_accounting_coverage_pct": normalize(
                    pc["accounting_coverage_pct"]
                ),
                "partd_dollar_source_field": partd_dollar_field,
                "partd_coverage_status": (
                    "PARTIAL_DOLLAR_COVERAGE"
                ),
                "combined_period_status": combined_period_status,
                "timing_basis_status": (
                    "CALENDAR_YEAR_LABELS_PRESERVED;"
                    "FFY_CONVERSION_NOT_AUTHORIZED"
                ),
                "ledger_status": "NOT_YET_AUTHORIZED",
                "methodology_version": METHODOLOGY_VERSION,
            }
        )

    #
    # Trustees inventory
    #
    trustees_inventory: list[dict[str, str]] = []

    for row in trustees_rows:
        try:
            observation_year = int_value(
                row["observation_year"],
                "Trustees observation_year",
            )
        except ValueError:
            continue

        if observation_year not in expected_year_set:
            continue

        trustees_inventory.append(
            {
                "observation_year": str(observation_year),
                "table_id": normalize(row["table_id"]),
                "accounting_scope": normalize(row["accounting_scope"]),
                "plan_type_normalized": normalize(
                    row["plan_type_normalized"]
                ),
                "component_normalized": normalize(
                    row["component_normalized"]
                ),
                "unit": normalize(row["unit"]),
                "basis": normalize(row["basis"]),
                "selected_trustees_vintage": normalize(
                    row["selected_trustees_vintage"]
                ),
                "selected_value": normalize(row["selected_value"]),
                "preferred_vintage_status": normalize(
                    row["preferred_vintage_status"]
                ),
                "source_file": normalize(row["source_file"]),
                "source_page": normalize(row["source_page"]),
                "comparability_status": "UNRESOLVED",
                "comparison_performed": "NO",
                "comparison_difference": "",
                "methodology_version": METHODOLOGY_VERSION,
            }
        )

    trustees_inventory.sort(
        key=lambda row: (
            int(row["observation_year"]),
            row["table_id"],
            row["accounting_scope"],
            row["plan_type_normalized"],
            row["component_normalized"],
            row["basis"],
        )
    )

    add_check(
        "TRUSTEES_ROWS_PRESENT",
        "Certified Trustees preferred-vintage rows exist for study years",
        len(trustees_inventory) > 0,
        f"study_year_rows={len(trustees_inventory)}",
    )

    add_check(
        "TRUSTEES_COMPARISON_WITHHELD",
        "v0.1 performs no forced Trustees reconciliation",
        all(
            row["comparison_performed"] == "NO"
            and row["comparability_status"] == "UNRESOLVED"
            for row in trustees_inventory
        ),
        "all Trustees rows retained as UNRESOLVED for comparability",
    )

    add_check(
        "NO_2024_EXTRAPOLATION",
        "CY2024 Part C and Part D are not extrapolated to 12 months",
        True,
        "source values are consumed exactly as certified",
    )

    add_check(
        "NO_FFY_CONVERSION",
        "No calendar-year to federal-fiscal-year conversion is performed",
        True,
        "source year labels preserved",
    )

    add_check(
        "NO_LEDGER_AUTHORIZATION",
        "Integration profile does not authorize ledger inclusion",
        all(
            row["ledger_status"] == "NOT_YET_AUTHORIZED"
            for row in integration_rows
        ),
        "all annual integration rows remain NOT_YET_AUTHORIZED",
    )

    overall_pass = all(row["status"] == "PASS" for row in checks)

    integration_path = (
        OUTPUT_DIR / "cms_medicare_core_annual_profile_v0_1.csv"
    )

    trustees_path = (
        OUTPUT_DIR / "cms_medicare_trustees_control_inventory_v0_1.csv"
    )

    checks_path = (
        OUTPUT_DIR / "cms_medicare_accounting_integration_checks_v0_1.csv"
    )

    report_path = (
        OUTPUT_DIR / "cms_medicare_accounting_integration_report_v0_1.txt"
    )

    write_csv(
        integration_path,
        integration_rows,
        [
            "year",
            "original_medicare_actual_ffs_dollars",
            "partc_reconstructed_dollars",
            "partd_reconstructed_dollars",
            "core_medicare_sum_dollars",
            "original_medicare_county_rows",
            "original_medicare_beneficiaries",
            "partc_months_processed",
            "partc_year_completeness",
            "partc_reconstruction_coverage_pct",
            "partc_accounting_coverage_pct",
            "partd_dollar_source_field",
            "partd_coverage_status",
            "combined_period_status",
            "timing_basis_status",
            "ledger_status",
            "methodology_version",
        ],
    )

    write_csv(
        trustees_path,
        trustees_inventory,
        [
            "observation_year",
            "table_id",
            "accounting_scope",
            "plan_type_normalized",
            "component_normalized",
            "unit",
            "basis",
            "selected_trustees_vintage",
            "selected_value",
            "preferred_vintage_status",
            "source_file",
            "source_page",
            "comparability_status",
            "comparison_performed",
            "comparison_difference",
            "methodology_version",
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

    lines: list[str] = []

    lines.append(
        "CMS MEDICARE ACCOUNTING INTEGRATION PROFILE v0.1"
    )
    lines.append("=" * 100)
    lines.append("")
    lines.append("READ-ONLY ACCOUNTING INTEGRATION PROFILE")
    lines.append("")
    lines.append(
        "No source modification, imputation, extrapolation, scaling, "
        "FFY conversion, DB writes, or ledger inclusion."
    )
    lines.append("")
    lines.append("PRINCIPAL STREAMS")
    lines.append("-" * 100)
    lines.append(
        "Original Medicare / FFS : actual FFS payments"
    )
    lines.append(
        "Part C                  : certified reconstructed dollars"
    )
    lines.append(
        "Part D                  : certified reconstructed dollars; "
        "PARTIAL_DOLLAR_COVERAGE"
    )
    lines.append("")
    lines.append("ANNUAL WASHINGTON PROFILE")
    lines.append("-" * 100)

    for row in integration_rows:
        lines.append(
            f"{row['year']}  "
            f"OM=${money_text(Decimal(row['original_medicare_actual_ffs_dollars']))}  "
            f"PartC=${money_text(Decimal(row['partc_reconstructed_dollars']))}  "
            f"PartD=${money_text(Decimal(row['partd_reconstructed_dollars']))}  "
            f"CORE=${money_text(Decimal(row['core_medicare_sum_dollars']))}  "
            f"{row['combined_period_status']}"
        )

    lines.append("")
    lines.append("TRUSTEES CONTROL INVENTORY")
    lines.append("-" * 100)
    lines.append(
        f"Certified preferred-vintage study-year rows: "
        f"{len(trustees_inventory):,}"
    )
    lines.append(
        "Comparability status: UNRESOLVED"
    )
    lines.append(
        "No Trustees difference or scaling factor is calculated in v0.1."
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
    lines.append("INTERPRETATION")
    lines.append("-" * 100)
    lines.append(
        "The three principal Washington Medicare streams are assembled "
        "without changing their certified source values."
    )
    lines.append(
        "The resulting core Medicare sum is an accounting-integration "
        "candidate, not yet a certified final ledger value."
    )
    lines.append(
        "Trustees controls are retained separately because accounting "
        "scope, component, basis, and timing comparability must be "
        "established before reconciliation."
    )
    lines.append(
        "CY2024 must not be interpreted as a complete three-stream annual "
        "total because Part C and Part D contain Jan-Sep only."
    )
    lines.append(
        "Part D remains partial-dollar coverage in every year represented "
        "by the frozen reconstruction."
    )
    lines.append("")
    lines.append("CERTIFICATION RESULT")
    lines.append("-" * 100)

    if overall_pass:
        lines.append(
            f"{METHODOLOGY_VERSION} — PASS / "
            "INTEGRATION PROFILE ONLY"
        )
    else:
        lines.append(
            f"{METHODOLOGY_VERSION} — FAIL"
        )

    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))

    if not overall_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()