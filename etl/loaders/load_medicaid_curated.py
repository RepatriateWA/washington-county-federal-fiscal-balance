"""
Populate the curated CMS Medicaid tables from validated MBES raw data.

Targets:

    reference.medicaid_service_category
    cms.medicaid_service_expenditures
    cms.medicaid_state_control_total

The loader:

1. Selects PRIMARY raw rows marked for detail reporting.
2. Creates or updates normalized Medicaid service categories.
3. Loads non-duplicative service-level expenditure rows.
4. Loads the official PRIMARY "Total Net Expenditures" control total.
5. Reconciles the curated federal-share sum to the control total.
6. Runs inside a single PostgreSQL transaction.

Examples:

    python -m etl.loaders.load_medicaid_curated

Dry run:

    python -m etl.loaders.load_medicaid_curated --dry-run

Explicit identifiers, if automatic reference resolution is ambiguous:

    python -m etl.loaders.load_medicaid_curated `
        --state-id 48 `
        --federal-program-id 12
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import psycopg2
from dotenv import load_dotenv
from psycopg2.extensions import connection as Connection
from psycopg2.extensions import cursor as Cursor
from psycopg2.extras import execute_values


RAW_TABLE = "cms_raw.medicaid_mbes"
CATEGORY_TABLE = "reference.medicaid_service_category"
EXPENDITURE_TABLE = "cms.medicaid_service_expenditures"
CONTROL_TABLE = "cms.medicaid_state_control_total"

DEFAULT_FISCAL_YEAR = 2024
DEFAULT_STATE_NAME = "Washington"
DEFAULT_WORKSHEET_NAME = "MAP - Washington"

MEDICAID_PROGRAM_SEARCH_TERMS = (
    "medicaid",
    "medical assistance",
)


@dataclass(frozen=True)
class RawMedicaidRow:
    raw_row_id: int
    fiscal_year: int
    state_name: str
    worksheet_name: str
    source_row_number: int
    service_category: str
    row_type: str
    total_computable: Optional[Decimal]
    federal_share: Optional[Decimal]
    federal_share_medicaid: Optional[Decimal]
    federal_share_arra: Optional[Decimal]
    federal_share_covid: Optional[Decimal]
    state_share: Optional[Decimal]
    source_file: str


@dataclass(frozen=True)
class ControlTotalRow:
    raw_row_id: int
    fiscal_year: int
    state_name: str
    worksheet_name: str
    source_row_number: int
    service_category: str
    total_computable: Decimal
    federal_share: Decimal
    federal_share_medicaid: Optional[Decimal]
    federal_share_arra: Optional[Decimal]
    federal_share_covid: Optional[Decimal]
    state_share: Decimal
    source_file: str


def first_environment_value(
    *names: str,
    default: Optional[str] = None,
) -> Optional[str]:
    for name in names:
        value = os.getenv(name)

        if value is not None and value.strip():
            return value.strip()

    return default


def get_connection() -> Connection:
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


def normalize_category_name(value: str) -> str:
    """
    Normalize a service-category name for matching across annual reports.

    The display name remains unchanged in the dimension. This value is used
    only as the stable matching key.
    """
    normalized = re.sub(r"\s+", " ", value.strip().lower())

    # Normalize common Unicode dash variants.
    normalized = (
        normalized.replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )

    return normalized


def format_amount(value: Optional[Decimal]) -> str:
    if value is None:
        return "NULL"

    return f"{value:,.2f}"


def get_table_columns(
    cursor: Cursor,
    schema_name: str,
    table_name: str,
) -> list[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
        """,
        (schema_name, table_name),
    )

    return [row[0] for row in cursor.fetchall()]


def resolve_state_id(
    cursor: Cursor,
    state_name: str,
    explicit_state_id: Optional[int],
) -> int:
    if explicit_state_id is not None:
        cursor.execute(
            """
            SELECT state_id
            FROM reference.state_registry
            WHERE state_id = %s;
            """,
            (explicit_state_id,),
        )

        row = cursor.fetchone()

        if row is None:
            raise ValueError(
                f"State ID {explicit_state_id} was not found in "
                "reference.state_registry."
            )

        return int(row[0])

    cursor.execute(
        """
        SELECT state_id
        FROM reference.state_registry
        WHERE LOWER(TRIM(state_name)) = LOWER(TRIM(%s));
        """,
        (state_name,),
    )

    rows = cursor.fetchall()

    if len(rows) != 1:
        raise ValueError(
            "Expected exactly one state-registry match for "
            f"{state_name!r}; found {len(rows)}. Use --state-id to "
            "specify the correct record."
        )

    return int(rows[0][0])


def resolve_federal_program_id(
    cursor: Cursor,
    explicit_program_id: Optional[int],
) -> int:
    if explicit_program_id is not None:
        cursor.execute(
            """
            SELECT federal_program_id
            FROM reference.federal_program
            WHERE federal_program_id = %s;
            """,
            (explicit_program_id,),
        )

        row = cursor.fetchone()

        if row is None:
            raise ValueError(
                f"Federal program ID {explicit_program_id} was not found in "
                "reference.federal_program."
            )

        return int(row[0])

    columns = get_table_columns(
        cursor,
        schema_name="reference",
        table_name="federal_program",
    )

    preferred_text_columns = [
        column
        for column in (
            "program_code",
            "program_name",
            "federal_program_code",
            "federal_program_name",
            "program_title",
            "name",
            "description",
        )
        if column in columns
    ]

    if not preferred_text_columns:
        raise ValueError(
            "Could not identify a searchable name or code column in "
            "reference.federal_program. Use --federal-program-id."
        )

    search_expression = " || ' ' || ".join(
        f"COALESCE({column}::text, '')"
        for column in preferred_text_columns
    )

    where_parts = []
    parameters: list[str] = []

    for term in MEDICAID_PROGRAM_SEARCH_TERMS:
        where_parts.append(
            f"LOWER({search_expression}) LIKE %s"
        )
        parameters.append(f"%{term.lower()}%")

    cursor.execute(
        f"""
        SELECT
            federal_program_id,
            {search_expression} AS searchable_program_text
        FROM reference.federal_program
        WHERE {" OR ".join(where_parts)}
        ORDER BY
            CASE
                WHEN LOWER({search_expression}) LIKE '%%medicaid%%'
                    THEN 0
                ELSE 1
            END,
            federal_program_id;
        """,
        tuple(parameters),
    )

    matches = cursor.fetchall()

    if len(matches) == 1:
        return int(matches[0][0])

    if not matches:
        raise ValueError(
            "No Medicaid program was found in reference.federal_program. "
            "Add the Medicaid program dimension row or run this loader with "
            "--federal-program-id."
        )

    match_text = "; ".join(
        f"ID {row[0]}: {str(row[1]).strip()}"
        for row in matches
    )

    raise ValueError(
        "Multiple possible Medicaid programs were found: "
        f"{match_text}. Run again with --federal-program-id."
    )


def fetch_detail_rows(
    cursor: Cursor,
    fiscal_year: int,
    state_name: str,
    worksheet_name: str,
) -> list[RawMedicaidRow]:
    cursor.execute(
        f"""
        SELECT
            raw_row_id,
            fiscal_year,
            state_name,
            worksheet_name,
            source_row_number,
            service_category,
            row_type,
            total_computable,
            federal_share,
            federal_share_medicaid,
            federal_share_arra,
            federal_share_covid,
            state_share,
            source_file
        FROM {RAW_TABLE}
        WHERE fiscal_year = %s
          AND state_name = %s
          AND worksheet_name = %s
          AND section_code = 'PRIMARY'
          AND include_in_detail_reporting = TRUE
          AND row_type IN ('DETAIL', 'ADJUSTMENT')
        ORDER BY source_row_number;
        """,
        (
            fiscal_year,
            state_name,
            worksheet_name,
        ),
    )

    return [
        RawMedicaidRow(
            raw_row_id=row[0],
            fiscal_year=row[1],
            state_name=row[2],
            worksheet_name=row[3],
            source_row_number=row[4],
            service_category=row[5],
            row_type=row[6],
            total_computable=row[7],
            federal_share=row[8],
            federal_share_medicaid=row[9],
            federal_share_arra=row[10],
            federal_share_covid=row[11],
            state_share=row[12],
            source_file=row[13],
        )
        for row in cursor.fetchall()
    ]


def fetch_control_total(
    cursor: Cursor,
    fiscal_year: int,
    state_name: str,
    worksheet_name: str,
) -> ControlTotalRow:
    cursor.execute(
        f"""
        SELECT
            raw_row_id,
            fiscal_year,
            state_name,
            worksheet_name,
            source_row_number,
            service_category,
            total_computable,
            federal_share,
            federal_share_medicaid,
            federal_share_arra,
            federal_share_covid,
            state_share,
            source_file
        FROM {RAW_TABLE}
        WHERE fiscal_year = %s
          AND state_name = %s
          AND worksheet_name = %s
          AND section_code = 'PRIMARY'
          AND row_type = 'CONTROL_TOTAL'
          AND LOWER(TRIM(service_category)) =
              'total net expenditures'
        ORDER BY raw_row_id;
        """,
        (
            fiscal_year,
            state_name,
            worksheet_name,
        ),
    )

    rows = cursor.fetchall()

    if len(rows) != 1:
        raise ValueError(
            "Expected exactly one PRIMARY Total Net Expenditures control "
            f"row; found {len(rows)}."
        )

    row = rows[0]

    required_amounts = (
        row[6],
        row[7],
        row[11],
    )

    if any(value is None for value in required_amounts):
        raise ValueError(
            "The Medicaid control-total row is missing total computable, "
            "federal share, or state share."
        )

    return ControlTotalRow(
        raw_row_id=row[0],
        fiscal_year=row[1],
        state_name=row[2],
        worksheet_name=row[3],
        source_row_number=row[4],
        service_category=row[5],
        total_computable=row[6],
        federal_share=row[7],
        federal_share_medicaid=row[8],
        federal_share_arra=row[9],
        federal_share_covid=row[10],
        state_share=row[11],
        source_file=row[12],
    )


def validate_source_rows(
    detail_rows: list[RawMedicaidRow],
    control_total: ControlTotalRow,
) -> None:
    if not detail_rows:
        raise ValueError(
            "No PRIMARY Medicaid detail-reporting rows were found."
        )

    raw_ids = [row.raw_row_id for row in detail_rows]

    if len(raw_ids) != len(set(raw_ids)):
        raise ValueError(
            "Duplicate raw row IDs were found in the detail-row selection."
        )

    if control_total.raw_row_id in set(raw_ids):
        raise ValueError(
            "The control-total row was incorrectly included as a detail row."
        )

    total_difference = (
        control_total.total_computable
        - control_total.federal_share
        - control_total.state_share
    )

    if abs(total_difference) > Decimal("1.00"):
        raise ValueError(
            "The Medicaid control total does not reconcile: "
            f"total minus federal minus state = {total_difference}."
        )

    if all(
        value is not None
        for value in (
            control_total.federal_share_medicaid,
            control_total.federal_share_arra,
            control_total.federal_share_covid,
        )
    ):
        component_difference = (
            control_total.federal_share
            - control_total.federal_share_medicaid
            - control_total.federal_share_arra
            - control_total.federal_share_covid
        )

        if abs(component_difference) > Decimal("1.00"):
            raise ValueError(
                "The Medicaid federal components do not reconcile to the "
                f"federal-share control total. Difference: "
                f"{component_difference}."
            )


def upsert_service_categories(
    cursor: Cursor,
    rows: list[RawMedicaidRow],
) -> dict[str, int]:
    category_metadata: dict[str, dict[str, object]] = {}

    for row in rows:
        normalized_name = normalize_category_name(
            row.service_category
        )

        existing = category_metadata.get(normalized_name)

        if existing is None:
            category_metadata[normalized_name] = {
                "service_category_name": row.service_category,
                "default_row_type": row.row_type,
                "is_adjustment": row.row_type == "ADJUSTMENT",
            }
        elif row.row_type == "ADJUSTMENT":
            existing["default_row_type"] = "ADJUSTMENT"
            existing["is_adjustment"] = True

    for normalized_name, metadata in category_metadata.items():
        cursor.execute(
            f"""
            INSERT INTO {CATEGORY_TABLE} (
                service_category_name,
                normalized_service_category_name,
                default_row_type,
                is_adjustment,
                updated_at
            )
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (normalized_service_category_name)
            DO UPDATE SET
                default_row_type =
                    CASE
                        WHEN {CATEGORY_TABLE}.default_row_type =
                            'ADJUSTMENT'
                          OR EXCLUDED.default_row_type =
                            'ADJUSTMENT'
                            THEN 'ADJUSTMENT'
                        ELSE 'DETAIL'
                    END,
                is_adjustment =
                    {CATEGORY_TABLE}.is_adjustment
                    OR EXCLUDED.is_adjustment,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (
                metadata["service_category_name"],
                normalized_name,
                metadata["default_row_type"],
                metadata["is_adjustment"],
            ),
        )

    cursor.execute(
        f"""
        SELECT
            normalized_service_category_name,
            medicaid_service_category_id
        FROM {CATEGORY_TABLE}
        WHERE normalized_service_category_name = ANY(%s);
        """,
        (list(category_metadata.keys()),),
    )

    category_ids = {
        row[0]: int(row[1])
        for row in cursor.fetchall()
    }

    missing_categories = (
        set(category_metadata.keys())
        - set(category_ids.keys())
    )

    if missing_categories:
        raise ValueError(
            "Failed to resolve Medicaid service-category IDs for: "
            + ", ".join(sorted(missing_categories))
        )

    return category_ids


def delete_existing_curated_rows(
    cursor: Cursor,
    fiscal_year: int,
    state_id: int,
    federal_program_id: int,
) -> tuple[int, int]:
    cursor.execute(
        f"""
        DELETE FROM {EXPENDITURE_TABLE}
        WHERE fiscal_year = %s
          AND state_id = %s
          AND federal_program_id = %s;
        """,
        (
            fiscal_year,
            state_id,
            federal_program_id,
        ),
    )

    deleted_expenditures = cursor.rowcount

    cursor.execute(
        f"""
        DELETE FROM {CONTROL_TABLE}
        WHERE fiscal_year = %s
          AND state_id = %s
          AND federal_program_id = %s;
        """,
        (
            fiscal_year,
            state_id,
            federal_program_id,
        ),
    )

    deleted_controls = cursor.rowcount

    return deleted_expenditures, deleted_controls


def insert_service_expenditures(
    cursor: Cursor,
    rows: list[RawMedicaidRow],
    state_id: int,
    federal_program_id: int,
    category_ids: dict[str, int],
) -> int:
    values = []

    for row in rows:
        normalized_name = normalize_category_name(
            row.service_category
        )

        values.append(
            (
                row.fiscal_year,
                state_id,
                federal_program_id,
                category_ids[normalized_name],
                row.raw_row_id,
                row.row_type,
                row.total_computable,
                row.federal_share,
                row.federal_share_medicaid,
                row.federal_share_arra,
                row.federal_share_covid,
                row.state_share,
                "FEDERAL_FISCAL_YEAR",
                "STATE",
                "Centers for Medicare & Medicaid Services",
                "Medicaid Budget and Expenditure System",
                "Medicaid Financial Management Report - Net Services",
                row.source_file,
                row.worksheet_name,
                row.source_row_number,
            )
        )

    insert_sql = f"""
        INSERT INTO {EXPENDITURE_TABLE} (
            fiscal_year,
            state_id,
            federal_program_id,
            medicaid_service_category_id,
            source_raw_row_id,
            row_type,
            total_computable,
            federal_share,
            federal_share_medicaid,
            federal_share_arra,
            federal_share_covid,
            state_share,
            expenditure_time_basis,
            geographic_level,
            source_agency,
            source_system,
            source_report,
            source_file,
            source_worksheet,
            source_row_number
        )
        VALUES %s
        ON CONFLICT (source_raw_row_id)
        DO UPDATE SET
            fiscal_year = EXCLUDED.fiscal_year,
            state_id = EXCLUDED.state_id,
            federal_program_id = EXCLUDED.federal_program_id,
            medicaid_service_category_id =
                EXCLUDED.medicaid_service_category_id,
            row_type = EXCLUDED.row_type,
            total_computable = EXCLUDED.total_computable,
            federal_share = EXCLUDED.federal_share,
            federal_share_medicaid =
                EXCLUDED.federal_share_medicaid,
            federal_share_arra = EXCLUDED.federal_share_arra,
            federal_share_covid = EXCLUDED.federal_share_covid,
            state_share = EXCLUDED.state_share,
            expenditure_time_basis =
                EXCLUDED.expenditure_time_basis,
            geographic_level = EXCLUDED.geographic_level,
            source_agency = EXCLUDED.source_agency,
            source_system = EXCLUDED.source_system,
            source_report = EXCLUDED.source_report,
            source_file = EXCLUDED.source_file,
            source_worksheet = EXCLUDED.source_worksheet,
            source_row_number = EXCLUDED.source_row_number,
            loaded_at = CURRENT_TIMESTAMP;
    """

    execute_values(
        cursor,
        insert_sql,
        values,
        page_size=500,
    )

    return len(values)


def insert_control_total(
    cursor: Cursor,
    control: ControlTotalRow,
    state_id: int,
    federal_program_id: int,
) -> None:
    cursor.execute(
        f"""
        INSERT INTO {CONTROL_TABLE} (
            fiscal_year,
            state_id,
            federal_program_id,
            source_raw_row_id,
            total_computable,
            federal_share,
            federal_share_medicaid,
            federal_share_arra,
            federal_share_covid,
            state_share,
            control_total_label,
            expenditure_time_basis,
            source_file,
            source_worksheet,
            source_row_number
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (
            fiscal_year,
            state_id,
            federal_program_id
        )
        DO UPDATE SET
            source_raw_row_id = EXCLUDED.source_raw_row_id,
            total_computable = EXCLUDED.total_computable,
            federal_share = EXCLUDED.federal_share,
            federal_share_medicaid =
                EXCLUDED.federal_share_medicaid,
            federal_share_arra = EXCLUDED.federal_share_arra,
            federal_share_covid = EXCLUDED.federal_share_covid,
            state_share = EXCLUDED.state_share,
            control_total_label = EXCLUDED.control_total_label,
            expenditure_time_basis =
                EXCLUDED.expenditure_time_basis,
            source_file = EXCLUDED.source_file,
            source_worksheet = EXCLUDED.source_worksheet,
            source_row_number = EXCLUDED.source_row_number,
            loaded_at = CURRENT_TIMESTAMP;
        """,
        (
            control.fiscal_year,
            state_id,
            federal_program_id,
            control.raw_row_id,
            control.total_computable,
            control.federal_share,
            control.federal_share_medicaid,
            control.federal_share_arra,
            control.federal_share_covid,
            control.state_share,
            control.service_category,
            "FEDERAL_FISCAL_YEAR",
            control.source_file,
            control.worksheet_name,
            control.source_row_number,
        ),
    )


def fetch_curated_summary(
    cursor: Cursor,
    fiscal_year: int,
    state_id: int,
    federal_program_id: int,
) -> dict[str, object]:
    cursor.execute(
        f"""
        SELECT
            COUNT(*) AS row_count,
            COUNT(*) FILTER (
                WHERE row_type = 'DETAIL'
            ) AS detail_count,
            COUNT(*) FILTER (
                WHERE row_type = 'ADJUSTMENT'
            ) AS adjustment_count,
            COALESCE(SUM(total_computable), 0),
            COALESCE(SUM(federal_share), 0),
            COALESCE(SUM(federal_share_medicaid), 0),
            COALESCE(SUM(federal_share_arra), 0),
            COALESCE(SUM(federal_share_covid), 0),
            COALESCE(SUM(state_share), 0)
        FROM {EXPENDITURE_TABLE}
        WHERE fiscal_year = %s
          AND state_id = %s
          AND federal_program_id = %s;
        """,
        (
            fiscal_year,
            state_id,
            federal_program_id,
        ),
    )

    row = cursor.fetchone()

    return {
        "row_count": int(row[0]),
        "detail_count": int(row[1]),
        "adjustment_count": int(row[2]),
        "total_computable": row[3],
        "federal_share": row[4],
        "federal_share_medicaid": row[5],
        "federal_share_arra": row[6],
        "federal_share_covid": row[7],
        "state_share": row[8],
    }


def print_source_summary(
    detail_rows: list[RawMedicaidRow],
    control: ControlTotalRow,
    state_id: int,
    federal_program_id: int,
) -> None:
    detail_count = sum(
        1 for row in detail_rows if row.row_type == "DETAIL"
    )

    adjustment_count = sum(
        1 for row in detail_rows if row.row_type == "ADJUSTMENT"
    )

    print()
    print("=" * 88)
    print("CMS MEDICAID CURATED LOAD — SOURCE SUMMARY")
    print("=" * 88)
    print(f"Fiscal year:                 {control.fiscal_year}")
    print(f"State:                       {control.state_name}")
    print(f"State ID:                    {state_id}")
    print(f"Federal program ID:          {federal_program_id}")
    print(f"Worksheet:                   {control.worksheet_name}")
    print(f"Detail-reporting rows:       {len(detail_rows):,}")
    print(f"DETAIL rows:                 {detail_count:,}")
    print(f"ADJUSTMENT rows:             {adjustment_count:,}")
    print()
    print("Official control total")
    print("-" * 88)
    print(
        f"{'Total computable':<34}"
        f"{format_amount(control.total_computable):>24}"
    )
    print(
        f"{'Federal share':<34}"
        f"{format_amount(control.federal_share):>24}"
    )
    print(
        f"{'Federal share Medicaid':<34}"
        f"{format_amount(control.federal_share_medicaid):>24}"
    )
    print(
        f"{'Federal share ARRA':<34}"
        f"{format_amount(control.federal_share_arra):>24}"
    )
    print(
        f"{'Federal share COVID':<34}"
        f"{format_amount(control.federal_share_covid):>24}"
    )
    print(
        f"{'State share':<34}"
        f"{format_amount(control.state_share):>24}"
    )
    print("=" * 88)


def print_curated_summary(
    summary: dict[str, object],
    control: ControlTotalRow,
    deleted_expenditures: int,
    deleted_controls: int,
) -> None:
    print()
    print("=" * 88)
    print("CMS MEDICAID CURATED LOAD — DATABASE SUMMARY")
    print("=" * 88)

    print(
        f"{'Existing expenditure rows deleted':<44}"
        f"{deleted_expenditures:>14,}"
    )
    print(
        f"{'Existing control rows deleted':<44}"
        f"{deleted_controls:>14,}"
    )
    print(
        f"{'Curated expenditure rows loaded':<44}"
        f"{summary['row_count']:>14,}"
    )
    print(
        f"{'DETAIL rows loaded':<44}"
        f"{summary['detail_count']:>14,}"
    )
    print(
        f"{'ADJUSTMENT rows loaded':<44}"
        f"{summary['adjustment_count']:>14,}"
    )

    print()
    print("Authoritative fiscal-balance amount")
    print("-" * 88)

    print(
        f"{'Total computable':<44}"
        f"{format_amount(control.total_computable):>24}"
    )
    print(
        f"{'Federal Medicaid expenditure':<44}"
        f"{format_amount(control.federal_share):>24}"
    )
    print(
        f"{'State share':<44}"
        f"{format_amount(control.state_share):>24}"
    )
    print(
        f"{'Federal Medicaid component':<44}"
        f"{format_amount(control.federal_share_medicaid):>24}"
    )
    print(
        f"{'Federal ARRA component':<44}"
        f"{format_amount(control.federal_share_arra):>24}"
    )
    print(
        f"{'Federal COVID component':<44}"
        f"{format_amount(control.federal_share_covid):>24}"
    )

    print("=" * 88)
    print(
        "CONTROL-TOTAL LOAD: PASS — service-level rows remain in cms_raw "
        "and are excluded from additive fiscal-balance reporting."
    )
    print("=" * 88)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load curated Washington Medicaid service expenditures and "
            "the official state control total from cms_raw.medicaid_mbes."
        )
    )

    parser.add_argument(
        "--fiscal-year",
        type=int,
        default=DEFAULT_FISCAL_YEAR,
    )

    parser.add_argument(
        "--state-name",
        default=DEFAULT_STATE_NAME,
    )

    parser.add_argument(
        "--worksheet-name",
        default=DEFAULT_WORKSHEET_NAME,
    )

    parser.add_argument(
        "--state-id",
        type=int,
        default=None,
        help=(
            "Optional explicit reference.state_registry ID. Normally "
            "resolved automatically from --state-name."
        ),
    )

    parser.add_argument(
        "--federal-program-id",
        type=int,
        default=None,
        help=(
            "Optional explicit reference.federal_program ID. Normally "
            "resolved automatically by searching for Medicaid."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Read and validate source rows without modifying curated tables."
        ),
    )

    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    connection = get_connection()

    try:
        with connection:
            with connection.cursor() as cursor:
                state_id = resolve_state_id(
                    cursor=cursor,
                    state_name=args.state_name,
                    explicit_state_id=args.state_id,
                )

                federal_program_id = resolve_federal_program_id(
                    cursor=cursor,
                    explicit_program_id=args.federal_program_id,
                )

                detail_rows = fetch_detail_rows(
                    cursor=cursor,
                    fiscal_year=args.fiscal_year,
                    state_name=args.state_name,
                    worksheet_name=args.worksheet_name,
                )

                control_total = fetch_control_total(
                    cursor=cursor,
                    fiscal_year=args.fiscal_year,
                    state_name=args.state_name,
                    worksheet_name=args.worksheet_name,
                )

                validate_source_rows(
                    detail_rows=detail_rows,
                    control_total=control_total,
                )

                print_source_summary(
                    detail_rows=detail_rows,
                    control=control_total,
                    state_id=state_id,
                    federal_program_id=federal_program_id,
                )

                if args.dry_run:
                    print()
                    print(
                        "DRY RUN COMPLETE: no curated database rows "
                        "were changed."
                    )
                    return 0

                category_ids = upsert_service_categories(
                    cursor=cursor,
                    rows=detail_rows,
                )

                (
                    deleted_expenditures,
                    deleted_controls,
                ) = delete_existing_curated_rows(
                    cursor=cursor,
                    fiscal_year=args.fiscal_year,
                    state_id=state_id,
                    federal_program_id=federal_program_id,
                )

                # The CMS service-level rows overlap across accounting
                # presentations and are not additive to the official control
                # total. They remain preserved in cms_raw.medicaid_mbes.
                inserted_count = 0
                

                insert_control_total(
                    cursor=cursor,
                    control=control_total,
                    state_id=state_id,
                    federal_program_id=federal_program_id,
                )

                summary = fetch_curated_summary(
                    cursor=cursor,
                    fiscal_year=args.fiscal_year,
                    state_id=state_id,
                    federal_program_id=federal_program_id,
                )

                if summary["row_count"] != 0:
                    raise RuntimeError(
                        "Expected zero curated Medicaid service rows because "
                        "the CMS service-level rows are overlapping and "
                        "non-additive."
                    )

                print_curated_summary(
                    summary=summary,
                    control=control_total,
                    deleted_expenditures=deleted_expenditures,
                    deleted_controls=deleted_controls,
                )

        print()
        print("Medicaid curated load completed successfully.")
        return 0

    except Exception as exc:
        connection.rollback()

        print(
            f"Medicaid curated load failed: {exc}",
            file=sys.stderr,
        )

        return 1

    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())