from __future__ import annotations

import csv
import hashlib
import json
import sys
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any

import openpyxl


# =============================================================================
# ETL-172I-1
# OMB FEDERAL RECEIPTS UNIVERSE INVENTORY
#
# Purpose:
#   Establish and certify the complete top-level federal receipts universe
#   for FFY2015-FFY2024 from OMB Historical Table 2.1.
#
# Source:
#   OMB Historical Table 2.1
#   Receipts by Source
#
# Top-level accounting identity:
#
#   Total Receipts =
#       Individual Income Taxes
#     + Corporation Income Taxes
#     + Social Insurance and Retirement Receipts
#     + Excise Taxes
#     + Other
#
# Nested identities:
#
#   Social Insurance and Retirement Receipts Total =
#       On-Budget + Off-Budget
#
#   Total Receipts =
#       On-Budget + Off-Budget
#
# This step establishes the national accounting universe only.
#
# It does NOT:
#   - allocate receipts to Washington;
#   - calculate Washington completeness percentages;
#   - decompose Social Insurance and Retirement Receipts;
#   - decompose Other receipts;
#   - reconstruct Excise Taxes;
#   - perform Rockefeller replication;
#   - reconcile to IRS gross collections;
#   - write to PostgreSQL;
#   - authorize final ledger inclusion.
# =============================================================================


getcontext().prec = 50


REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "source"
    / "BUDGET-2027-TAB-3-1.xlsx"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "federal_receipts_universe_v0_1"
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "national_federal_receipts_universe.csv"
)

OUTPUT_JSON = (
    OUTPUT_DIR
    / "certification.json"
)

OUTPUT_REPORT = (
    OUTPUT_DIR
    / "certification_report.txt"
)


SHEET_NAME = "Table"

TARGET_YEARS = list(range(2015, 2025))

EXPECTED_TITLE = (
    "Table 2.1 - RECEIPTS BY SOURCE:  1934 - 2031"
)

EXPECTED_UNITS = "(in millions of dollars)"

MILLIONS_TO_DOLLARS = Decimal("1000000")

# The source rows were independently inspected:
# FY2015 = row 87
# ...
# FY2024 = row 96.
#
# The script nevertheless verifies the year in column A rather than
# trusting the physical row number alone.
EXPECTED_SOURCE_ROWS = {
    year: 87 + (year - 2015)
    for year in TARGET_YEARS
}


EXPECTED_HEADERS = {
    "A3": "Fiscal Year",
    "B3": "Individual Income Taxes",
    "C3": "Corporation Income Taxes (1)",
    "D3": "Social Insurance and Retirement Receipts (2)",
    "D4": "Total",
    "E4": "(On - Budget)",
    "F4": "(Off - Budget)",
    "G3": "Excise Taxes (2)",
    "H3": "Other (3)",
    "I3": "Total Receipts",
    "I4": "Total",
    "J4": "(On - Budget)",
    "K4": "(Off - Budget)",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest().upper()


def decimal_from_cell(
    value: Any,
    *,
    context: str,
) -> Decimal:
    if value is None:
        raise RuntimeError(
            "NUMERIC SOURCE FAILURE\n"
            f"{context}: NULL"
        )

    text = (
        str(value)
        .strip()
        .replace(",", "")
    )

    if not text:
        raise RuntimeError(
            "NUMERIC SOURCE FAILURE\n"
            f"{context}: blank"
        )

    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise RuntimeError(
            "NUMERIC SOURCE FAILURE\n"
            f"{context}: {value!r}"
        ) from exc

    if not result.is_finite():
        raise RuntimeError(
            "NUMERIC SOURCE FAILURE\n"
            f"{context}: non-finite"
        )

    return result


def plain_decimal(
    value: Decimal,
) -> str:
    return format(value, "f")


def millions_to_dollars(
    value: Decimal,
) -> Decimal:
    return (
        value
        * MILLIONS_TO_DOLLARS
    )


def load_workbook() -> tuple[Any, Any]:
    if not SOURCE_FILE.exists():
        raise RuntimeError(
            "OMB SOURCE FILE NOT FOUND\n"
            f"{SOURCE_FILE.relative_to(REPO_ROOT)}"
        )

    workbook = openpyxl.load_workbook(
        SOURCE_FILE,
        data_only=True,
        read_only=False,
    )

    if SHEET_NAME not in workbook.sheetnames:
        raise RuntimeError(
            "OMB SOURCE SHEET FAILURE\n"
            f"Expected sheet: {SHEET_NAME}\n"
            f"Observed sheets: {workbook.sheetnames}"
        )

    return (
        workbook,
        workbook[SHEET_NAME],
    )


def certify_structure(
    sheet: Any,
) -> dict[str, Any]:
    observed_title = sheet["A1"].value
    observed_units = sheet["A2"].value

    if observed_title != EXPECTED_TITLE:
        raise RuntimeError(
            "OMB TITLE CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_TITLE!r}\n"
            f"Observed: {observed_title!r}"
        )

    if observed_units != EXPECTED_UNITS:
        raise RuntimeError(
            "OMB UNIT CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_UNITS!r}\n"
            f"Observed: {observed_units!r}"
        )

    for coordinate, expected in EXPECTED_HEADERS.items():
        observed = sheet[coordinate].value

        if observed != expected:
            raise RuntimeError(
                "OMB HEADER CERTIFICATION FAILURE\n"
                f"Cell     : {coordinate}\n"
                f"Expected : {expected!r}\n"
                f"Observed : {observed!r}"
            )

    expected_merged = {
        "D3:F3",
        "I3:K3",
    }

    observed_merged = {
        str(cell_range)
        for cell_range
        in sheet.merged_cells.ranges
    }

    missing_merged = (
        expected_merged
        - observed_merged
    )

    if missing_merged:
        raise RuntimeError(
            "OMB MERGED-HEADER CERTIFICATION FAILURE\n"
            f"Missing: {sorted(missing_merged)}"
        )

    return {
        "title": "PASS",
        "units": "PASS",
        "headers": "PASS",
        "merged_headers": "PASS",
    }


def extract_rows(
    sheet: Any,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    for fiscal_year in TARGET_YEARS:
        source_row = EXPECTED_SOURCE_ROWS[
            fiscal_year
        ]

        observed_year = sheet.cell(
            source_row,
            1,
        ).value

        try:
            observed_year_int = int(
                observed_year
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise RuntimeError(
                "OMB FISCAL-YEAR SOURCE FAILURE\n"
                f"Row {source_row}: {observed_year!r}"
            ) from exc

        if observed_year_int != fiscal_year:
            raise RuntimeError(
                "OMB FISCAL-YEAR ROW-MAPPING FAILURE\n"
                f"Source row : {source_row}\n"
                f"Expected   : {fiscal_year}\n"
                f"Observed   : {observed_year_int}"
            )

        individual = decimal_from_cell(
            sheet.cell(
                source_row,
                2,
            ).value,
            context=(
                f"FFY{fiscal_year} "
                "Individual Income Taxes"
            ),
        )

        corporation = decimal_from_cell(
            sheet.cell(
                source_row,
                3,
            ).value,
            context=(
                f"FFY{fiscal_year} "
                "Corporation Income Taxes"
            ),
        )

        social_total = decimal_from_cell(
            sheet.cell(
                source_row,
                4,
            ).value,
            context=(
                f"FFY{fiscal_year} "
                "Social Insurance Total"
            ),
        )

        social_on_budget = decimal_from_cell(
            sheet.cell(
                source_row,
                5,
            ).value,
            context=(
                f"FFY{fiscal_year} "
                "Social Insurance On-Budget"
            ),
        )

        social_off_budget = decimal_from_cell(
            sheet.cell(
                source_row,
                6,
            ).value,
            context=(
                f"FFY{fiscal_year} "
                "Social Insurance Off-Budget"
            ),
        )

        excise = decimal_from_cell(
            sheet.cell(
                source_row,
                7,
            ).value,
            context=(
                f"FFY{fiscal_year} "
                "Excise Taxes"
            ),
        )

        other = decimal_from_cell(
            sheet.cell(
                source_row,
                8,
            ).value,
            context=(
                f"FFY{fiscal_year} Other"
            ),
        )

        total = decimal_from_cell(
            sheet.cell(
                source_row,
                9,
            ).value,
            context=(
                f"FFY{fiscal_year} "
                "Total Receipts"
            ),
        )

        total_on_budget = decimal_from_cell(
            sheet.cell(
                source_row,
                10,
            ).value,
            context=(
                f"FFY{fiscal_year} "
                "Total On-Budget"
            ),
        )

        total_off_budget = decimal_from_cell(
            sheet.cell(
                source_row,
                11,
            ).value,
            context=(
                f"FFY{fiscal_year} "
                "Total Off-Budget"
            ),
        )

        social_component_sum = (
            social_on_budget
            + social_off_budget
        )

        social_difference = (
            social_total
            - social_component_sum
        )

        top_level_component_sum = (
            individual
            + corporation
            + social_total
            + excise
            + other
        )

        top_level_difference = (
            total
            - top_level_component_sum
        )

        budget_status_sum = (
            total_on_budget
            + total_off_budget
        )

        budget_status_difference = (
            total
            - budget_status_sum
        )

        if social_difference != 0:
            raise RuntimeError(
                "SOCIAL INSURANCE IDENTITY FAILURE\n"
                f"FFY{fiscal_year}\n"
                f"Total       : {social_total}\n"
                f"On-Budget   : {social_on_budget}\n"
                f"Off-Budget  : {social_off_budget}\n"
                f"Difference  : {social_difference}"
            )

        if top_level_difference != 0:
            raise RuntimeError(
                "TOP-LEVEL RECEIPTS IDENTITY FAILURE\n"
                f"FFY{fiscal_year}\n"
                f"Total       : {total}\n"
                f"Components  : {top_level_component_sum}\n"
                f"Difference  : {top_level_difference}"
            )

        if budget_status_difference != 0:
            raise RuntimeError(
                "TOTAL BUDGET-STATUS IDENTITY FAILURE\n"
                f"FFY{fiscal_year}\n"
                f"Total       : {total}\n"
                f"On-Budget   : {total_on_budget}\n"
                f"Off-Budget  : {total_off_budget}\n"
                f"Difference  : {budget_status_difference}"
            )

        output.append(
            {
                "fiscal_year": fiscal_year,
                "source_row": source_row,
                "source_units": (
                    "Millions of dollars"
                ),
                "dollar_conversion_factor": (
                    "1000000"
                ),

                "individual_income_taxes_millions": (
                    plain_decimal(
                        individual
                    )
                ),
                "individual_income_taxes_dollars": (
                    plain_decimal(
                        millions_to_dollars(
                            individual
                        )
                    )
                ),

                "corporation_income_taxes_millions": (
                    plain_decimal(
                        corporation
                    )
                ),
                "corporation_income_taxes_dollars": (
                    plain_decimal(
                        millions_to_dollars(
                            corporation
                        )
                    )
                ),

                "social_insurance_retirement_total_millions": (
                    plain_decimal(
                        social_total
                    )
                ),
                "social_insurance_retirement_total_dollars": (
                    plain_decimal(
                        millions_to_dollars(
                            social_total
                        )
                    )
                ),

                "social_insurance_retirement_on_budget_millions": (
                    plain_decimal(
                        social_on_budget
                    )
                ),
                "social_insurance_retirement_off_budget_millions": (
                    plain_decimal(
                        social_off_budget
                    )
                ),

                "excise_taxes_millions": (
                    plain_decimal(
                        excise
                    )
                ),
                "excise_taxes_dollars": (
                    plain_decimal(
                        millions_to_dollars(
                            excise
                        )
                    )
                ),

                "other_receipts_millions": (
                    plain_decimal(
                        other
                    )
                ),
                "other_receipts_dollars": (
                    plain_decimal(
                        millions_to_dollars(
                            other
                        )
                    )
                ),

                "total_receipts_millions": (
                    plain_decimal(
                        total
                    )
                ),
                "total_receipts_dollars": (
                    plain_decimal(
                        millions_to_dollars(
                            total
                        )
                    )
                ),

                "total_on_budget_millions": (
                    plain_decimal(
                        total_on_budget
                    )
                ),
                "total_off_budget_millions": (
                    plain_decimal(
                        total_off_budget
                    )
                ),

                "social_nested_component_sum_millions": (
                    plain_decimal(
                        social_component_sum
                    )
                ),
                "social_nested_identity_difference_millions": (
                    plain_decimal(
                        social_difference
                    )
                ),
                "social_nested_identity_status": (
                    "PASS"
                ),

                "top_level_component_sum_millions": (
                    plain_decimal(
                        top_level_component_sum
                    )
                ),
                "top_level_identity_difference_millions": (
                    plain_decimal(
                        top_level_difference
                    )
                ),
                "top_level_identity_status": (
                    "PASS"
                ),

                "budget_status_sum_millions": (
                    plain_decimal(
                        budget_status_sum
                    )
                ),
                "budget_status_identity_difference_millions": (
                    plain_decimal(
                        budget_status_difference
                    )
                ),
                "budget_status_identity_status": (
                    "PASS"
                ),

                # Status here describes only the WCFFBP
                # reconstruction work completed to date.
                "individual_income_reconstruction_status": (
                    "RECONSTRUCTED_ECONOMIC_INCIDENCE"
                ),
                "corporation_income_reconstruction_status": (
                    "RECONSTRUCTED_ECONOMIC_INCIDENCE"
                ),
                "social_insurance_reconstruction_status": (
                    "PARTIAL"
                ),
                "excise_reconstruction_status": (
                    "NOT_YET_RECONSTRUCTED"
                ),
                "other_reconstruction_status": (
                    "NOT_YET_DECOMPOSED"
                ),
                "washington_allocation_status": (
                    "NOT_PERFORMED_IN_ETL_172I_1"
                ),
                "ledger_status": (
                    "INVENTORY_ONLY"
                ),
            }
        )

    return output


def certify_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(rows) != 10:
        raise RuntimeError(
            "OUTPUT OBSERVATION COUNT FAILURE\n"
            f"Expected 10; found {len(rows)}"
        )

    years = [
        int(row["fiscal_year"])
        for row in rows
    ]

    if years != TARGET_YEARS:
        raise RuntimeError(
            "OUTPUT FISCAL-YEAR COVERAGE FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {years}"
        )

    if len(set(years)) != 10:
        raise RuntimeError(
            "OUTPUT FISCAL-YEAR UNIQUENESS FAILURE"
        )

    for row in rows:
        year = int(
            row["fiscal_year"]
        )

        if (
            row[
                "social_nested_identity_status"
            ]
            != "PASS"
        ):
            raise RuntimeError(
                "SOCIAL IDENTITY STATUS FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "top_level_identity_status"
            ]
            != "PASS"
        ):
            raise RuntimeError(
                "TOP-LEVEL IDENTITY STATUS FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "budget_status_identity_status"
            ]
            != "PASS"
        ):
            raise RuntimeError(
                "BUDGET-STATUS IDENTITY FAILURE\n"
                f"FFY{year}"
            )

        if (
            row[
                "washington_allocation_status"
            ]
            != "NOT_PERFORMED_IN_ETL_172I_1"
        ):
            raise RuntimeError(
                "WASHINGTON ALLOCATION BOUNDARY FAILURE\n"
                f"FFY{year}"
            )

        if (
            row["ledger_status"]
            != "INVENTORY_ONLY"
        ):
            raise RuntimeError(
                "LEDGER BOUNDARY FAILURE\n"
                f"FFY{year}"
            )

    return {
        "expected_observations": 10,
        "actual_observations": 10,
        "fiscal_year_coverage": "PASS",
        "fiscal_year_uniqueness": "PASS",
        "source_row_mapping": "PASS",
        "source_units": "PASS",
        "million_to_dollar_conversion": "PASS",
        "social_insurance_nested_identity": "PASS",
        "top_level_receipts_identity": "PASS",
        "total_budget_status_identity": "PASS",
        "washington_allocation_boundary": "PASS",
        "social_decomposition_boundary": "PASS",
        "other_decomposition_boundary": "PASS",
        "rockefeller_replication_boundary": "PASS",
        "irs_reconciliation_boundary": "PASS",
        "database_write_boundary": "PASS",
        "ledger_boundary": "PASS",
    }


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        raise RuntimeError(
            "Refusing to write empty output."
        )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(
                rows[0].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(rows)


def build_report(
    *,
    source_sha256: str,
    structure: dict[str, Any],
    rows: list[dict[str, Any]],
    certification: dict[str, Any],
) -> str:
    lines: list[str] = [
        "=" * 100,
        (
            "OMB FEDERAL RECEIPTS UNIVERSE INVENTORY "
            "- ETL-172I-1"
        ),
        "=" * 100,
        "",
        "SOURCE",
        "-" * 100,
        (
            "File   : "
            f"{SOURCE_FILE.relative_to(REPO_ROOT)}"
        ),
        (
            "SHA256 : "
            f"{source_sha256}"
        ),
        (
            "Sheet  : Table"
        ),
        (
            "Title  : "
            f"{EXPECTED_TITLE}"
        ),
        (
            "Units  : "
            f"{EXPECTED_UNITS}"
        ),
        "",
        "SOURCE STRUCTURE",
        "-" * 100,
        (
            "B : Individual Income Taxes"
        ),
        (
            "C : Corporation Income Taxes"
        ),
        (
            "D : Social Insurance and Retirement Receipts - Total"
        ),
        (
            "E : Social Insurance and Retirement Receipts - On-Budget"
        ),
        (
            "F : Social Insurance and Retirement Receipts - Off-Budget"
        ),
        (
            "G : Excise Taxes"
        ),
        (
            "H : Other"
        ),
        (
            "I : Total Receipts"
        ),
        (
            "J : Total Receipts - On-Budget"
        ),
        (
            "K : Total Receipts - Off-Budget"
        ),
        "",
        "CERTIFIED IDENTITIES",
        "-" * 100,
        (
            "Social Insurance Total = "
            "Social Insurance On-Budget + Off-Budget"
        ),
        (
            "Total Receipts = Individual Income Taxes "
            "+ Corporation Income Taxes "
            "+ Social Insurance and Retirement Receipts "
            "+ Excise Taxes + Other"
        ),
        (
            "Total Receipts = "
            "Total On-Budget + Total Off-Budget"
        ),
        "",
        "NATIONAL FEDERAL RECEIPTS UNIVERSE",
        "-" * 100,
        (
            f"{'FFY':<7}"
            f"{'INDIVIDUAL':>16}"
            f"{'CORPORATE':>14}"
            f"{'SOCIAL':>14}"
            f"{'EXCISE':>12}"
            f"{'OTHER':>12}"
            f"{'TOTAL':>16}"
        ),
        "-" * 100,
    ]

    for row in rows:
        individual = Decimal(
            row[
                "individual_income_taxes_millions"
            ]
        )

        corporation = Decimal(
            row[
                "corporation_income_taxes_millions"
            ]
        )

        social = Decimal(
            row[
                "social_insurance_retirement_total_millions"
            ]
        )

        excise = Decimal(
            row[
                "excise_taxes_millions"
            ]
        )

        other = Decimal(
            row[
                "other_receipts_millions"
            ]
        )

        total = Decimal(
            row[
                "total_receipts_millions"
            ]
        )

        lines.append(
            f"{row['fiscal_year']:<7}"
            f"{individual:>16,.0f}"
            f"{corporation:>14,.0f}"
            f"{social:>14,.0f}"
            f"{excise:>12,.0f}"
            f"{other:>12,.0f}"
            f"{total:>16,.0f}"
        )

    lines.extend(
        [
            "",
            "CURRENT WCFFBP RECONSTRUCTION STATUS",
            "-" * 100,
            (
                "Individual Income Taxes                 : "
                "RECONSTRUCTED_ECONOMIC_INCIDENCE"
            ),
            (
                "Corporation Income Taxes                : "
                "RECONSTRUCTED_ECONOMIC_INCIDENCE"
            ),
            (
                "Social Insurance and Retirement Receipts: "
                "PARTIAL"
            ),
            (
                "Excise Taxes                            : "
                "NOT_YET_RECONSTRUCTED"
            ),
            (
                "Other                                   : "
                "NOT_YET_DECOMPOSED"
            ),
            "",
            "CERTIFICATION",
            "-" * 100,
        ]
    )

    for key, value in structure.items():
        lines.append(
            f"{'structure_' + key:<44}: {value}"
        )

    for key, value in certification.items():
        lines.append(
            f"{key:<44}: {value}"
        )

    lines.extend(
        [
            "",
            "BOUNDARY",
            "-" * 100,
            (
                "ETL-172I-1 establishes the national federal "
                "receipts accounting universe only."
            ),
            (
                "It does not calculate Washington receipts "
                "or Washington reconstruction completeness."
            ),
            (
                "Social Insurance and Retirement Receipts "
                "remain to be decomposed against the already "
                "reconstructed OASI, DI, and Medicare HI controls."
            ),
            (
                "Other receipts remain to be decomposed before "
                "allocability can be classified."
            ),
            (
                "No final receipts-ledger inclusion is authorized."
            ),
            "",
            "ETL-172I-1 RESULT: PASS",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 100)
    print(
        "OMB FEDERAL RECEIPTS UNIVERSE INVENTORY "
        "- ETL-172I-1"
    )
    print("=" * 100)
    print()
    print(
        "National accounting-universe certification only. "
        "No Washington allocation."
    )
    print()

    source_sha256 = sha256_file(
        SOURCE_FILE
    )

    workbook, sheet = load_workbook()

    structure = certify_structure(
        sheet
    )

    rows = extract_rows(
        sheet
    )

    certification = certify_rows(
        rows
    )

    write_csv(
        OUTPUT_CSV,
        rows,
    )

    payload = {
        "etl_step": "ETL-172I-1",
        "result": "PASS",
        "artifact_type": (
            "OMB_NATIONAL_FEDERAL_RECEIPTS_UNIVERSE"
        ),
        "source": {
            "file": str(
                SOURCE_FILE.relative_to(
                    REPO_ROOT
                )
            ),
            "sha256": source_sha256,
            "sheet": SHEET_NAME,
            "title": EXPECTED_TITLE,
            "units": EXPECTED_UNITS,
        },
        "top_level_accounting_identity": (
            "Total Receipts = Individual Income Taxes "
            "+ Corporation Income Taxes "
            "+ Social Insurance and Retirement Receipts "
            "+ Excise Taxes + Other"
        ),
        "nested_identities": [
            (
                "Social Insurance and Retirement Receipts "
                "= On-Budget + Off-Budget"
            ),
            (
                "Total Receipts = "
                "On-Budget + Off-Budget"
            ),
        ],
        "current_reconstruction_status": {
            "individual_income_taxes": (
                "RECONSTRUCTED_ECONOMIC_INCIDENCE"
            ),
            "corporation_income_taxes": (
                "RECONSTRUCTED_ECONOMIC_INCIDENCE"
            ),
            "social_insurance_and_retirement_receipts": (
                "PARTIAL"
            ),
            "excise_taxes": (
                "NOT_YET_RECONSTRUCTED"
            ),
            "other": (
                "NOT_YET_DECOMPOSED"
            ),
        },
        "structure_certification": (
            structure
        ),
        "certification": certification,
        "methodological_boundaries": {
            "washington_allocation_performed": False,
            "washington_completeness_calculated": False,
            "social_insurance_decomposed": False,
            "other_receipts_decomposed": False,
            "excise_receipts_reconstructed": False,
            "rockefeller_replication": False,
            "irs_gross_collections_reconciliation": False,
            "database_writes": False,
            "final_ledger_inclusion_authorized": False,
        },
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        source_sha256=source_sha256,
        structure=structure,
        rows=rows,
        certification=certification,
    )

    OUTPUT_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    workbook.close()

    print("SOURCE")
    print("-" * 100)
    print(
        "File   : "
        f"{SOURCE_FILE.relative_to(REPO_ROOT)}"
    )
    print(
        "SHA256 : "
        f"{source_sha256}"
    )
    print()

    print("NATIONAL FEDERAL RECEIPTS UNIVERSE")
    print("-" * 100)
    print(
        f"{'FFY':<7}"
        f"{'INDIVIDUAL':>16}"
        f"{'CORPORATE':>14}"
        f"{'SOCIAL':>14}"
        f"{'EXCISE':>12}"
        f"{'OTHER':>12}"
        f"{'TOTAL':>16}"
    )

    for row in rows:
        individual = Decimal(
            row[
                "individual_income_taxes_millions"
            ]
        )

        corporation = Decimal(
            row[
                "corporation_income_taxes_millions"
            ]
        )

        social = Decimal(
            row[
                "social_insurance_retirement_total_millions"
            ]
        )

        excise = Decimal(
            row[
                "excise_taxes_millions"
            ]
        )

        other = Decimal(
            row[
                "other_receipts_millions"
            ]
        )

        total = Decimal(
            row[
                "total_receipts_millions"
            ]
        )

        print(
            f"{row['fiscal_year']:<7}"
            f"{individual:>16,.0f}"
            f"{corporation:>14,.0f}"
            f"{social:>14,.0f}"
            f"{excise:>12,.0f}"
            f"{other:>12,.0f}"
            f"{total:>16,.0f}"
        )

    print()
    print("CERTIFIED IDENTITIES")
    print("-" * 100)
    print(
        "Social Insurance Total = "
        "On-Budget + Off-Budget              PASS"
    )
    print(
        "Total = Individual + Corporate + "
        "Social + Excise + Other         PASS"
    )
    print(
        "Total = On-Budget + Off-Budget"
        "                                  PASS"
    )

    print()
    print("CURRENT RECONSTRUCTION STATUS")
    print("-" * 100)
    print(
        "Individual Income Taxes                 "
        "RECONSTRUCTED_ECONOMIC_INCIDENCE"
    )
    print(
        "Corporation Income Taxes                "
        "RECONSTRUCTED_ECONOMIC_INCIDENCE"
    )
    print(
        "Social Insurance and Retirement Receipts "
        "PARTIAL"
    )
    print(
        "Excise Taxes                            "
        "NOT_YET_RECONSTRUCTED"
    )
    print(
        "Other                                   "
        "NOT_YET_DECOMPOSED"
    )

    print()
    print("CERTIFICATION")
    print("-" * 100)

    for key, value in certification.items():
        print(
            f"{key:<44}: {value}"
        )

    print()
    print(
        "Output : "
        f"{OUTPUT_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        "JSON   : "
        f"{OUTPUT_JSON.relative_to(REPO_ROOT)}"
    )
    print(
        "Report : "
        f"{OUTPUT_REPORT.relative_to(REPO_ROOT)}"
    )
    print()
    print(
        "ETL-172I-1 RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )