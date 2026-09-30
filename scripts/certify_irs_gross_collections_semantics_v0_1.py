"""
ETL-171C — IRS Gross Collections Semantic Certification v0.1
=============================================================

Certifies the Washington State semantic structure of official IRS
Data Book Table 1-5 gross-collections workbooks for FFY2015-FFY2024.

This certification:

1. Reads the preserved official IRS source workbooks.
2. Requires exactly one Washington row per fiscal year.
3. Requires the published numbered columns -1 through -11.
4. Applies one explicitly defined semantic map to those columns.
5. Preserves IRS source amounts in thousands of dollars.
6. Converts thousands to dollars only by explicit multiplication by 1,000.
7. Tests the nested individual/employment/estate-trust identity:
       -3 = -4 + -5 + -6 + -7 + -8
8. Tests the top-level gross-collections identity:
       -1 = -2 + -3 + -9 + -10 + -11
9. Reconciles IRS published Washington total (-1) against
   reporting.v_washington_revenue_summary.gross_collections_dollars.
10. Writes validation evidence only.

No economic-incidence allocation.
No Rockefeller allocation.
No refund adjustment.
No database writes.
No ledger authorization.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from unittest import result

import pandas as pd

from etl.db import get_connection


CERTIFICATION_ID = "IRS-GROSS-COLLECTIONS-SEMANTICS-v0.1"
PUBLICATION_PRECISION_TOLERANCE_DOLLARS = Decimal("2500")

START_YEAR = 2015
END_YEAR = 2024

SOURCE_DIR = Path(
    "data/raw/irs/gross_collections/source"
)

OUTPUT_DIR = Path(
    "data/raw/irs/gross_collections/validation/"
    "semantic_certification_v0_1"
)

EXTRACT_PATH = OUTPUT_DIR / "washington_semantic_extract.csv"
RECON_PATH = OUTPUT_DIR / "washington_reconciliation.csv"
SEMANTIC_MAP_PATH = OUTPUT_DIR / "semantic_map.json"
REPORT_PATH = OUTPUT_DIR / "certification_report.txt"

THOUSANDS_TO_DOLLARS = Decimal("1000")

# IRS columns are explicitly numbered -1 through -11 in row 5.
SEMANTIC_MAP = {
    "-1": "total_internal_revenue_collections",
    "-2": "business_income_taxes",
    "-3": (
        "individual_income_employment_estate_trust_total"
    ),
    "-4": "individual_income_tax_withheld_and_fica",
    "-5": "individual_income_tax_payments_and_seca",
    "-6": "unemployment_insurance_tax",
    "-7": "railroad_retirement_tax",
    "-8": "estate_and_trust_income_tax",
    "-9": "estate_tax",
    "-10": "gift_tax",
    "-11": "excise_taxes",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def fiscal_year_from_name(path: Path) -> int:
    match = re.search(
        r"irs_data_book_(20\d{2})_",
        path.name,
    )

    if not match:
        raise ValueError(
            f"Could not determine fiscal year from {path.name}"
        )

    return int(match.group(1))


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def to_decimal(value: Any) -> Decimal:
    if pd.isna(value):
        raise ValueError("Unexpected blank numeric IRS cell.")

    if isinstance(value, Decimal):
        return value

    text = str(value).strip().replace(",", "")

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"Could not parse IRS numeric value: {value!r}"
        ) from exc


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def read_source(path: Path) -> pd.DataFrame:
    engine = (
        "xlrd"
        if path.suffix.lower() == ".xls"
        else "openpyxl"
    )

    return pd.read_excel(
        path,
        sheet_name="Table 5",
        header=None,
        dtype=object,
        engine=engine,
    )


def locate_column_numbers(
    frame: pd.DataFrame,
) -> dict[str, int]:
    """
    Locate the IRS row containing -1 through -11 rather than assuming
    a physical row number.
    """

    required = set(SEMANTIC_MAP)

    candidates: list[dict[str, int]] = []

    for row_index in range(len(frame)):
        mapping: dict[str, int] = {}

        for column_index, value in enumerate(
            frame.iloc[row_index].tolist()
        ):
            text = normalize_text(value)

            if text in required:
                mapping[text] = column_index

        if required.issubset(mapping):
            candidates.append(mapping)

    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one IRS numbered-column row; "
            f"found {len(candidates)}."
        )

    mapping = candidates[0]

    ordered_indices = [
        mapping[f"-{number}"]
        for number in range(1, 12)
    ]

    if ordered_indices != sorted(ordered_indices):
        raise RuntimeError(
            "IRS numbered columns -1 through -11 are not "
            "in expected left-to-right order."
        )

    return mapping


def locate_washington_row(
    frame: pd.DataFrame,
) -> int:
    matches: list[int] = []

    for row_index in range(len(frame)):
        for value in frame.iloc[row_index].tolist():
            if normalize_text(value).lower() == "washington":
                matches.append(row_index)
                break

    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one Washington row; "
            f"found {len(matches)}."
        )

    return matches[0]


def extract_year(
    path: Path,
) -> dict[str, Any]:
    fiscal_year = fiscal_year_from_name(path)
    frame = read_source(path)

    column_map = locate_column_numbers(frame)
    washington_row = locate_washington_row(frame)

    result: dict[str, Any] = {
        "fiscal_year": fiscal_year,
        "source_file": path.name,
        "source_sha256": sha256_file(path),
        "source_units": "THOUSANDS_OF_DOLLARS",
        "dollar_conversion_factor": "1000",
    }

    values: dict[str, Decimal] = {}

    for column_number, semantic_name in SEMANTIC_MAP.items():
        column_index = column_map[column_number]

        value = to_decimal(
            frame.iloc[
                washington_row,
                column_index,
            ]
        )

        values[column_number] = value

        result[
            f"{semantic_name}_thousands"
        ] = decimal_text(value)

        result[
            f"{semantic_name}_dollars"
        ] = decimal_text(
            value * THOUSANDS_TO_DOLLARS
        )

    nested_sum = sum(
        (
            values["-4"],
            values["-5"],
            values["-6"],
            values["-7"],
            values["-8"],
        ),
        Decimal("0"),
    )

    nested_difference = (
        values["-3"] - nested_sum
    )

    top_level_sum = sum(
        (
            values["-2"],
            values["-3"],
            values["-9"],
            values["-10"],
            values["-11"],
        ),
        Decimal("0"),
    )

    top_level_difference = (
        values["-1"] - top_level_sum
    )

    result[
        "nested_component_sum_thousands"
    ] = decimal_text(nested_sum)

    result[
        "nested_identity_difference_thousands"
    ] = decimal_text(nested_difference)

    nested_difference_dollars = (
    nested_difference * THOUSANDS_TO_DOLLARS
    )

    result[
        "nested_identity_status"
    ] = (
        "EXACT_PASS"
        if nested_difference == 0
        else (
            "PUBLICATION_PRECISION_PASS"
            if abs(nested_difference_dollars)
            <= PUBLICATION_PRECISION_TOLERANCE_DOLLARS
            else "FAIL"
        )
    )

    result[
        "top_level_component_sum_thousands"
    ] = decimal_text(top_level_sum)

    result[
        "top_level_identity_difference_thousands"
    ] = decimal_text(top_level_difference)

    top_level_difference_dollars = (
        top_level_difference * THOUSANDS_TO_DOLLARS
    )

    result[
        "top_level_identity_status"
    ] = (
        "EXACT_PASS"
        if top_level_difference == 0
        else (
            "PUBLICATION_PRECISION_PASS"
            if abs(top_level_difference_dollars)
            <= PUBLICATION_PRECISION_TOLERANCE_DOLLARS
            else "FAIL"
        )
    )

    return result


def fetch_reporting_controls() -> dict[int, Decimal]:
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    fiscal_year,
                    gross_collections_dollars
                FROM reporting.v_washington_revenue_summary
                WHERE fiscal_year BETWEEN %s AND %s
                ORDER BY fiscal_year
                """,
                (
                    START_YEAR,
                    END_YEAR,
                ),
            )

            rows = cursor.fetchall()

    finally:
        connection.close()

    controls: dict[int, Decimal] = {}

    for fiscal_year, amount in rows:
        year = int(fiscal_year)

        if year in controls:
            raise RuntimeError(
                f"Duplicate reporting control for FY{year}."
            )

        controls[year] = Decimal(str(amount))

    expected = set(
        range(START_YEAR, END_YEAR + 1)
    )

    observed = set(controls)

    if observed != expected:
        raise RuntimeError(
            "Reporting control year universe mismatch. "
            f"Expected={sorted(expected)} "
            f"Observed={sorted(observed)}"
        )

    return controls


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        raise RuntimeError(
            f"Refusing to write empty CSV: {path}"
        )

    fieldnames = list(rows[0].keys())

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    print("=" * 104)
    print(
        "ETL-171C — IRS GROSS COLLECTIONS "
        "SEMANTIC CERTIFICATION v0.1"
    )
    print("=" * 104)
    print(f"Certification ID : {CERTIFICATION_ID}")
    print(f"Fiscal years     : {START_YEAR}-{END_YEAR}")
    print("Database writes  : NONE")
    print("Incidence model  : NONE")
    print("Ledger authority : NONE")
    print()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = sorted(
        [
            path
            for path in SOURCE_DIR.iterdir()
            if path.is_file()
            and path.suffix.lower() in {
                ".xls",
                ".xlsx",
            }
        ],
        key=fiscal_year_from_name,
    )

    observed_years = [
        fiscal_year_from_name(path)
        for path in files
    ]

    expected_years = list(
        range(START_YEAR, END_YEAR + 1)
    )

    if observed_years != expected_years:
        raise RuntimeError(
            "Source year universe mismatch. "
            f"Expected={expected_years}; "
            f"Observed={observed_years}"
        )

    extracted: list[dict[str, Any]] = []

    for path in files:
        year = fiscal_year_from_name(path)

        print(f"Extracting FY{year}...")

        row = extract_year(path)
        extracted.append(row)

        print(
            "  nested identity   : "
            f"{row['nested_identity_status']} "
            f"(difference="
            f"{row['nested_identity_difference_thousands']} "
            f"thousand)"
        )

        print(
            "  top-level identity: "
            f"{row['top_level_identity_status']} "
            f"(difference="
            f"{row['top_level_identity_difference_thousands']} "
            f"thousand)"
        )

    controls = fetch_reporting_controls()

    reconciliation_rows: list[dict[str, Any]] = []

    for row in extracted:
        year = int(row["fiscal_year"])

        source_total = Decimal(
            row[
                "total_internal_revenue_collections_dollars"
            ]
        )

        reporting_total = controls[year]

        difference = (
            source_total - reporting_total
        )

        reconciliation_rows.append(
            {
                "fiscal_year": year,
                "irs_source_total_dollars": decimal_text(
                    source_total
                ),
                "reporting_control_dollars": decimal_text(
                    reporting_total
                ),
                "difference_dollars": decimal_text(
                    difference
                ),
                "reconciliation_status": (
                    "PASS"
                    if difference == 0
                    else "FAIL"
                ),
            }
        )

    write_csv(
        EXTRACT_PATH,
        extracted,
    )

    write_csv(
        RECON_PATH,
        reconciliation_rows,
    )

    with SEMANTIC_MAP_PATH.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            {
                "certification_id": CERTIFICATION_ID,
                "source_table": (
                    "IRS Data Book Table 1-5 / Table 5"
                ),
                "source_units": (
                    "thousands of dollars"
                ),
                "semantic_map": SEMANTIC_MAP,
                "nested_identity": (
                    "-3 = -4 + -5 + -6 + -7 + -8"
                ),
                "top_level_identity": (
                    "-1 = -2 + -3 + -9 + -10 + -11"
                ),
                "accounting_authorization": "NONE",
                "economic_incidence_allocation": "NONE",
            },
            handle,
            indent=2,
        )

    acceptable_identity_statuses = {
        "EXACT_PASS",
        "PUBLICATION_PRECISION_PASS",
    }

    nested_pass = all(
        row["nested_identity_status"]
        in acceptable_identity_statuses
        for row in extracted
    )

    top_pass = all(
        row["top_level_identity_status"]
        in acceptable_identity_statuses
        for row in extracted
    )

    reporting_pass = all(
        row["reconciliation_status"] == "PASS"
        for row in reconciliation_rows
    )

    overall_pass = (
        nested_pass
        and top_pass
        and reporting_pass
    )

    report_lines = [
        "=" * 104,
        (
            "IRS GROSS COLLECTIONS "
            "SEMANTIC CERTIFICATION v0.1"
        ),
        "=" * 104,
        "",
        f"Certification ID : {CERTIFICATION_ID}",
        (
            f"Fiscal years     : "
            f"{START_YEAR}-{END_YEAR}"
        ),
        "Database writes  : NONE",
        "Incidence model  : NONE",
        "Ledger authority : NONE",
        "",
        "=" * 104,
        "ANNUAL VALIDATION",
        "=" * 104,
        "",
    ]

    for source_row, recon_row in zip(
        extracted,
        reconciliation_rows,
    ):
        year = source_row["fiscal_year"]

        report_lines.append(
            f"FY{year}: "
            f"nested={source_row['nested_identity_status']} | "
            f"top-level={source_row['top_level_identity_status']} | "
            f"reporting={recon_row['reconciliation_status']} | "
            f"reporting difference="
            f"${Decimal(recon_row['difference_dollars']):,.2f}"
        )

    report_lines.extend(
        [
            "",
            "=" * 104,
            "CERTIFICATION RESULT",
            "=" * 104,
            "",
            (
                "Nested IRS component reconciliation "
                f"2015-2024 : "
                f"{'PASS' if nested_pass else 'FAIL'}"
            ),
            (
                "Top-level IRS reconciliation "
                f"2015-2024      : "
                f"{'PASS' if top_pass else 'FAIL'}"
            ),
            (
                "Existing WCFFBP control "
                f"reconciliation : "
                f"{'PASS' if reporting_pass else 'FAIL'}"
            ),
            "",
            (
                "FINAL RESULT: "
                f"{'PASS' if overall_pass else 'FAIL'}"
            ),
            "",
            (
                "PASS certifies source semantics, arithmetic, "
                "units, and reproduction of the existing "
                "Washington gross-collections control only."
            ),
            (
                "PASS does NOT certify economic tax incidence, "
                "refund treatment, Rockefeller methodology, "
                "or final federal-receipts ledger inclusion."
            ),
        ]
    )

    REPORT_PATH.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 104)
    print("CERTIFICATION RESULT")
    print("=" * 104)
    print(
        "Nested IRS component identity : "
        f"{'PASS' if nested_pass else 'FAIL'}"
    )
    print(
        "Top-level IRS identity        : "
        f"{'PASS' if top_pass else 'FAIL'}"
    )
    print(
        "WCFFBP reporting reconciliation: "
        f"{'PASS' if reporting_pass else 'FAIL'}"
    )
    print()
    print(
        f"FINAL RESULT: "
        f"{'PASS' if overall_pass else 'FAIL'}"
    )
    print()
    print(f"Semantic extract : {EXTRACT_PATH}")
    print(f"Reconciliation   : {RECON_PATH}")
    print(f"Semantic map     : {SEMANTIC_MAP_PATH}")
    print(f"Report           : {REPORT_PATH}")

    if not overall_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()