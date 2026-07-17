"""
Load a CMS Medicaid Financial Management Report worksheet into:

    cms_raw.medicaid_mbes

The loader preserves every meaningful worksheet row, including:

- Primary Medical Assistance Program rows
- C-section reconciliation rows
- T-section reconciliation rows
- Control totals and subtotals
- Negative accounting adjustments
- Source footer metadata

The loader does not calculate the final Medicaid expenditure measure.
It creates a faithful, classified raw landing table that can be used by
the curated Medicaid ETL and validation scripts.

Example:

    python -m etl.loaders.load_medicaid_mbes_raw

Explicit source file:

    python -m etl.loaders.load_medicaid_mbes_raw `
        --source-file "data/raw/cms/medicaid_mbes/2024/extracted/FY 2024 FMR NET EXPENDITURES.xlsx" `
        --fiscal-year 2024
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values


LOGGER = logging.getLogger(__name__)

DEFAULT_SOURCE_FILE = Path(
    "data/raw/cms/medicaid_mbes/2024/extracted/"
    "FY 2024 FMR NET EXPENDITURES.xlsx"
)

DEFAULT_SHEET_NAME = "MAP - Washington"
DEFAULT_FISCAL_YEAR = 2024
DEFAULT_STATE_NAME = "Washington"

# Zero-based worksheet row containing the actual column headings.
HEADER_ROW_INDEX = 6

DATABASE_TABLE = "cms_raw.medicaid_mbes"

COLUMN_NAMES = [
    "service_category",
    "total_computable",
    "federal_share",
    "federal_share_medicaid",
    "federal_share_arra",
    "federal_share_covid",
    "state_share",
]

CONTROL_TOTAL_LABELS = {
    "total net expenditures",
    "c-total net",
    "t-total net expenditures",
}

ADJUSTMENT_KEYWORDS = (
    "rebate",
    "offset",
    "collection",
    "collections",
    "balance",
    "recoupment",
    "refund",
    "recoveries",
    "recovery",
)


@dataclass(frozen=True)
class MedicaidRawRow:
    fiscal_year: int
    state_name: str
    worksheet_name: str
    source_row_number: int
    service_category: str
    section_code: str
    row_type: str
    include_in_detail_reporting: bool
    total_computable: Optional[Decimal]
    federal_share: Optional[Decimal]
    federal_share_medicaid: Optional[Decimal]
    federal_share_arra: Optional[Decimal]
    federal_share_covid: Optional[Decimal]
    state_share: Optional[Decimal]
    source_file: str

    def as_insert_tuple(self) -> tuple:
        return (
            self.fiscal_year,
            self.state_name,
            self.worksheet_name,
            self.source_row_number,
            self.service_category,
            self.section_code,
            self.row_type,
            self.include_in_detail_reporting,
            self.total_computable,
            self.federal_share,
            self.federal_share_medicaid,
            self.federal_share_arra,
            self.federal_share_covid,
            self.state_share,
            self.source_file,
        )


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def first_environment_value(*names: str, default: Optional[str] = None) -> Optional[str]:
    for name in names:
        value = os.getenv(name)

        if value is not None and value.strip():
            return value.strip()

    return default


def get_connection():
    """
    Create a PostgreSQL connection using common .env variable names.

    Supported aliases include:

        DB_HOST or PGHOST
        DB_PORT or PGPORT
        DB_NAME, POSTGRES_DB, or PGDATABASE
        DB_USER, POSTGRES_USER, or PGUSER
        DB_PASSWORD, POSTGRES_PASSWORD, or PGPASSWORD
    """
    load_dotenv()

    host = first_environment_value(
        "DB_HOST",
        "POSTGRES_HOST",
        "PGHOST",
        default="localhost",
    )

    port = first_environment_value(
        "DB_PORT",
        "POSTGRES_PORT",
        "PGPORT",
        default="5432",
    )

    database = first_environment_value(
        "DB_NAME",
        "POSTGRES_DB",
        "PGDATABASE",
        default="wcffbp",
    )

    user = first_environment_value(
        "DB_USER",
        "POSTGRES_USER",
        "PGUSER",
        default="postgres",
    )

    password = first_environment_value(
        "DB_PASSWORD",
        "POSTGRES_PASSWORD",
        "PGPASSWORD",
    )

    if not password:
        raise RuntimeError(
            "Database password was not found. Set DB_PASSWORD, "
            "POSTGRES_PASSWORD, or PGPASSWORD in the .env file."
        )

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
    )


def normalize_source_path(source_file: Path) -> str:
    """
    Store a reproducible repository-relative path when possible.
    """
    resolved_source = source_file.resolve()
    repository_root = Path.cwd().resolve()

    try:
        return resolved_source.relative_to(repository_root).as_posix()
    except ValueError:
        return resolved_source.as_posix()


def parse_amount(value) -> Optional[Decimal]:
    """
    Convert a CMS worksheet value into Decimal.

    Handles:

    - Native Excel numeric values
    - Commas
    - Dollar signs
    - Parenthesized negative amounts
    - Explicit minus signs
    - Blank cells
    - N/A-style placeholders
    """
    if pd.isna(value):
        return None

    if isinstance(value, Decimal):
        return value

    if isinstance(value, bool):
        raise ValueError(f"Boolean value cannot be parsed as an amount: {value!r}")

    text = str(value).strip()

    if text.casefold() in {
        "",
        "nan",
        "none",
        "n/a",
        "na",
        "-",
        "--",
    }:
        return None

    parenthesized_negative = text.startswith("(") and text.endswith(")")

    normalized = (
        text.replace("$", "")
        .replace(",", "")
        .replace("(", "")
        .replace(")", "")
        .strip()
    )

    if not normalized:
        return None

    try:
        amount = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Unable to parse CMS amount: {value!r}") from exc

    if parenthesized_negative:
        amount = -abs(amount)

    return amount


def normalize_service_category(value) -> Optional[str]:
    if pd.isna(value):
        return None

    text = " ".join(str(value).split()).strip()

    if not text or text.casefold() in {"nan", "none"}:
        return None

    return text


def row_has_any_amount(row: pd.Series) -> bool:
    return any(row[column] is not None for column in COLUMN_NAMES[1:])


def determine_section(
    service_category: str,
    current_section: str,
) -> str:
    """
    Determine the accounting section while respecting worksheet order.

    Some rows embedded in the T section do not begin with "T-".
    Therefore, the current section is carried forward after a C or T
    section begins.
    """
    label = service_category.strip()

    if label.casefold().startswith("created on:"):
        return "FOOTER"

    if label.startswith("C-"):
        return "C"

    if label.startswith("T-"):
        return "T"

    return current_section


def classify_row_type(
    service_category: str,
    section_code: str,
    amount_values: Iterable[Optional[Decimal]],
) -> str:
    label = service_category.strip()
    label_lower = label.casefold()

    if section_code == "FOOTER" or label_lower.startswith("created on:"):
        return "FOOTER"

    if label_lower in CONTROL_TOTAL_LABELS:
        return "CONTROL_TOTAL"

    if label_lower.startswith("total "):
        return "SUBTOTAL"

    amounts = [value for value in amount_values if value is not None]
    contains_negative_amount = any(value < 0 for value in amounts)

    contains_adjustment_keyword = any(
        keyword in label_lower for keyword in ADJUSTMENT_KEYWORDS
    )

    if contains_negative_amount or contains_adjustment_keyword:
        return "ADJUSTMENT"

    return "DETAIL"


def should_include_in_detail_reporting(
    section_code: str,
    row_type: str,
) -> bool:
    """
    Only primary-section detail and adjustment rows are candidates for
    service-level expenditure reporting.

    Control totals, subtotals, C rows, T rows, and footer rows remain in
    the raw table but do not feed detail aggregation.
    """
    return (
        section_code == "PRIMARY"
        and row_type in {"DETAIL", "ADJUSTMENT"}
    )


def read_and_transform(
    source_file: Path,
    fiscal_year: int,
    state_name: str,
    worksheet_name: str,
) -> list[MedicaidRawRow]:
    if not source_file.exists():
        raise FileNotFoundError(f"Source workbook does not exist: {source_file}")

    LOGGER.info("Reading workbook: %s", source_file)
    LOGGER.info("Reading worksheet: %s", worksheet_name)

    raw = pd.read_excel(
        source_file,
        sheet_name=worksheet_name,
        header=HEADER_ROW_INDEX,
        dtype=object,
    )

    if raw.shape[1] < 7:
        raise ValueError(
            f"Expected at least seven worksheet columns; found {raw.shape[1]}."
        )

    dataframe = raw.iloc[:, :7].copy()
    dataframe.columns = COLUMN_NAMES

    source_path_text = normalize_source_path(source_file)

    transformed_rows: list[MedicaidRawRow] = []
    current_section = "PRIMARY"

    for dataframe_index, row in dataframe.iterrows():
        service_category = normalize_service_category(
            row["service_category"]
        )

        if service_category is None:
            continue

        parsed_amounts = {
            column: parse_amount(row[column])
            for column in COLUMN_NAMES[1:]
        }

        # Excel rows are one-based. The data row immediately following the
        # header is HEADER_ROW_INDEX + 2 in Excel.
        source_row_number = (
            int(dataframe_index)
            + HEADER_ROW_INDEX
            + 2
        )

        section_code = determine_section(
            service_category=service_category,
            current_section=current_section,
        )

        if section_code in {"C", "T"}:
            current_section = section_code

        row_type = classify_row_type(
            service_category=service_category,
            section_code=section_code,
            amount_values=parsed_amounts.values(),
        )

        # Exclude a completely empty non-footer row. CMS footer metadata is
        # intentionally preserved even though it has no financial amounts.
        if (
            not row_has_any_amount(
                pd.Series(
                    {
                        **{"service_category": service_category},
                        **parsed_amounts,
                    }
                )
            )
            and row_type != "FOOTER"
        ):
            LOGGER.debug(
                "Skipping empty row %s: %s",
                source_row_number,
                service_category,
            )
            continue

        transformed_rows.append(
            MedicaidRawRow(
                fiscal_year=fiscal_year,
                state_name=state_name,
                worksheet_name=worksheet_name,
                source_row_number=source_row_number,
                service_category=service_category,
                section_code=section_code,
                row_type=row_type,
                include_in_detail_reporting=should_include_in_detail_reporting(
                    section_code=section_code,
                    row_type=row_type,
                ),
                total_computable=parsed_amounts["total_computable"],
                federal_share=parsed_amounts["federal_share"],
                federal_share_medicaid=parsed_amounts[
                    "federal_share_medicaid"
                ],
                federal_share_arra=parsed_amounts["federal_share_arra"],
                federal_share_covid=parsed_amounts[
                    "federal_share_covid"
                ],
                state_share=parsed_amounts["state_share"],
                source_file=source_path_text,
            )
        )

    if not transformed_rows:
        raise ValueError("No Medicaid rows were produced from the worksheet.")

    return transformed_rows


def validate_transformed_rows(rows: list[MedicaidRawRow]) -> None:
    duplicate_source_rows: set[int] = set()
    seen_source_rows: set[int] = set()

    for row in rows:
        if row.source_row_number in seen_source_rows:
            duplicate_source_rows.add(row.source_row_number)

        seen_source_rows.add(row.source_row_number)

    if duplicate_source_rows:
        raise ValueError(
            "Duplicate source row numbers were produced: "
            f"{sorted(duplicate_source_rows)}"
        )

    control_rows = [
        row
        for row in rows
        if (
            row.section_code == "PRIMARY"
            and row.service_category.casefold()
            == "total net expenditures"
        )
    ]

    if len(control_rows) != 1:
        raise ValueError(
            "Expected exactly one PRIMARY 'Total Net Expenditures' row; "
            f"found {len(control_rows)}."
        )

    control_row = control_rows[0]

    if control_row.federal_share is None:
        raise ValueError(
            "The PRIMARY 'Total Net Expenditures' row has no federal share."
        )

    if control_row.total_computable is None:
        raise ValueError(
            "The PRIMARY 'Total Net Expenditures' row has no "
            "total-computable amount."
        )

    if control_row.state_share is None:
        raise ValueError(
            "The PRIMARY 'Total Net Expenditures' row has no state share."
        )

    if control_row.federal_share <= 0:
        raise ValueError(
            "The PRIMARY control-total federal share must be positive."
        )

    LOGGER.info(
        "Primary control total — total computable: %s",
        f"{control_row.total_computable:,.2f}",
    )
    LOGGER.info(
        "Primary control total — federal share: %s",
        f"{control_row.federal_share:,.2f}",
    )
    LOGGER.info(
        "Primary control total — state share: %s",
        f"{control_row.state_share:,.2f}",
    )


def load_rows(
    rows: list[MedicaidRawRow],
    replace_existing: bool = True,
) -> tuple[int, int]:
    if not rows:
        raise ValueError("No rows were supplied to the database loader.")

    first_row = rows[0]

    delete_sql = f"""
        DELETE FROM {DATABASE_TABLE}
        WHERE fiscal_year = %s
          AND state_name = %s
          AND worksheet_name = %s
          AND source_file = %s;
    """

    insert_sql = f"""
        INSERT INTO {DATABASE_TABLE} (
            fiscal_year,
            state_name,
            worksheet_name,
            source_row_number,
            service_category,
            section_code,
            row_type,
            include_in_detail_reporting,
            total_computable,
            federal_share,
            federal_share_medicaid,
            federal_share_arra,
            federal_share_covid,
            state_share,
            source_file
        )
        VALUES %s
        ON CONFLICT (
            fiscal_year,
            state_name,
            worksheet_name,
            source_row_number,
            source_file
        )
        DO UPDATE SET
            service_category = EXCLUDED.service_category,
            section_code = EXCLUDED.section_code,
            row_type = EXCLUDED.row_type,
            include_in_detail_reporting =
                EXCLUDED.include_in_detail_reporting,
            total_computable = EXCLUDED.total_computable,
            federal_share = EXCLUDED.federal_share,
            federal_share_medicaid =
                EXCLUDED.federal_share_medicaid,
            federal_share_arra = EXCLUDED.federal_share_arra,
            federal_share_covid = EXCLUDED.federal_share_covid,
            state_share = EXCLUDED.state_share,
            imported_at = CURRENT_TIMESTAMP;
    """

    deleted_count = 0

    connection = get_connection()

    try:
        with connection:
            with connection.cursor() as cursor:
                if replace_existing:
                    cursor.execute(
                        delete_sql,
                        (
                            first_row.fiscal_year,
                            first_row.state_name,
                            first_row.worksheet_name,
                            first_row.source_file,
                        ),
                    )

                    deleted_count = cursor.rowcount

                execute_values(
                    cursor,
                    insert_sql,
                    [row.as_insert_tuple() for row in rows],
                    page_size=500,
                )

        return deleted_count, len(rows)

    finally:
        connection.close()


def summarize_rows(rows: list[MedicaidRawRow]) -> None:
    section_counts: dict[str, int] = {}
    row_type_counts: dict[str, int] = {}

    for row in rows:
        section_counts[row.section_code] = (
            section_counts.get(row.section_code, 0) + 1
        )

        row_type_counts[row.row_type] = (
            row_type_counts.get(row.row_type, 0) + 1
        )

    reporting_rows = sum(
        1 for row in rows if row.include_in_detail_reporting
    )

    control_row = next(
        row
        for row in rows
        if (
            row.section_code == "PRIMARY"
            and row.service_category.casefold()
            == "total net expenditures"
        )
    )

    print()
    print("=" * 78)
    print("CMS MEDICAID MBES RAW LOAD SUMMARY")
    print("=" * 78)
    print(f"Fiscal year:                 {control_row.fiscal_year}")
    print(f"State:                       {control_row.state_name}")
    print(f"Worksheet:                   {control_row.worksheet_name}")
    print(f"Rows prepared:               {len(rows):,}")
    print(f"Detail-reporting candidates: {reporting_rows:,}")

    print("\nRows by section")
    print("-" * 78)

    for section_code in ("PRIMARY", "C", "T", "FOOTER"):
        print(
            f"{section_code:<28}"
            f"{section_counts.get(section_code, 0):>12,}"
        )

    print("\nRows by type")
    print("-" * 78)

    for row_type in (
        "DETAIL",
        "ADJUSTMENT",
        "SUBTOTAL",
        "CONTROL_TOTAL",
        "FOOTER",
    ):
        print(
            f"{row_type:<28}"
            f"{row_type_counts.get(row_type, 0):>12,}"
        )

    print("\nPrimary control total")
    print("-" * 78)
    print(
        f"{'Total computable':<28}"
        f"{control_row.total_computable:>20,.2f}"
    )
    print(
        f"{'Federal share':<28}"
        f"{control_row.federal_share:>20,.2f}"
    )
    print(
        f"{'State share':<28}"
        f"{control_row.state_share:>20,.2f}"
    )
    print("=" * 78)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load a CMS Medicaid Financial Management Report "
            "MAP worksheet into cms_raw.medicaid_mbes."
        )
    )

    parser.add_argument(
        "--source-file",
        type=Path,
        default=DEFAULT_SOURCE_FILE,
        help=(
            "Path to the CMS Medicaid Financial Management Report workbook."
        ),
    )

    parser.add_argument(
        "--fiscal-year",
        type=int,
        default=DEFAULT_FISCAL_YEAR,
        help="Federal fiscal year represented by the workbook.",
    )

    parser.add_argument(
        "--state-name",
        default=DEFAULT_STATE_NAME,
        help="State name represented by the selected worksheet.",
    )

    parser.add_argument(
        "--worksheet-name",
        default=DEFAULT_SHEET_NAME,
        help="Workbook worksheet to load.",
    )

    parser.add_argument(
        "--no-replace",
        action="store_true",
        help=(
            "Do not delete existing rows for the same source before loading. "
            "Rows will still be updated through the unique source-row key."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse, classify, and validate the workbook without loading it.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose diagnostic logging.",
    )

    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    configure_logging(verbose=args.verbose)

    try:
        rows = read_and_transform(
            source_file=args.source_file,
            fiscal_year=args.fiscal_year,
            state_name=args.state_name,
            worksheet_name=args.worksheet_name,
        )

        validate_transformed_rows(rows)
        summarize_rows(rows)

        if args.dry_run:
            LOGGER.info("Dry run completed. No database changes were made.")
            return 0

        deleted_count, loaded_count = load_rows(
            rows=rows,
            replace_existing=not args.no_replace,
        )

        LOGGER.info("Previously loaded rows deleted: %s", deleted_count)
        LOGGER.info("Rows loaded into %s: %s", DATABASE_TABLE, loaded_count)
        LOGGER.info("Medicaid MBES raw load completed successfully.")

        return 0

    except Exception:
        LOGGER.exception("Medicaid MBES raw load failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())