from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from etl.db import get_connection


LOADER_NAME = "etl.loaders.chip_cms21"
LOADER_VERSION = "1.0.0"


@dataclass(frozen=True)
class WorksheetSpec:
    sheet_name: str
    worksheet_type: str
    header_row_excel: int = 7


@dataclass(frozen=True)
class Cms21Config:
    fiscal_year: int
    state_fips: str
    state_abbreviation: str
    state_name: str
    worksheets: tuple[WorksheetSpec, ...]


@dataclass
class LoadSummary:
    load_batch_id: int
    raw_rows: int = 0
    curated_rows: int = 0
    control_totals: int = 0


def washington_config(fiscal_year: int) -> Cms21Config:
    """
    Standard Washington CMS-21 workbook configuration.

    This configuration can be adjusted later if CMS changes worksheet
    names or header locations in a particular fiscal year.
    """
    return Cms21Config(
        fiscal_year=fiscal_year,
        state_fips="53",
        state_abbreviation="WA",
        state_name="Washington",
        worksheets=(
            WorksheetSpec(
                sheet_name="CHIP - Washington",
                worksheet_type="CHIP",
            ),
            WorksheetSpec(
                sheet_name="MCHIP - Washington",
                worksheet_type="MCHIP",
            ),
            WorksheetSpec(
                sheet_name="MCHIP 20% - Washington",
                worksheet_type="MCHIP_20_PERCENT",
            ),
        ),
    )


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def is_blank(value: Any) -> bool:
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass

    return isinstance(value, str) and not value.strip()


def raw_text(value: Any) -> str | None:
    """
    Preserve a readable representation of the source cell for the raw layer.
    """
    if is_blank(value):
        return None

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value).strip()


def normalize_label(value: Any) -> str:
    if is_blank(value):
        return ""

    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_service_category(value: Any) -> str:
    """
    Produce a stable analytical label without destroying the source label.
    """
    text = raw_text(value)

    if text is None:
        return ""

    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_integer(value: Any) -> int:
    """
    Parse CMS financial cells into whole-dollar integers.

    Supported forms include:
      1,234
      $1,234
      (1,234)
      -1,234
      blank / dash / em dash
      numeric Excel cells
    """
    if is_blank(value):
        return 0

    if isinstance(value, bool):
        raise ValueError(f"Boolean value is not a valid financial amount: {value!r}")

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if math.isnan(value):
            return 0

        if not value.is_integer():
            raise ValueError(
                f"Expected whole-dollar CMS value but found decimal: {value!r}"
            )

        return int(value)

    text = str(value).strip()

    if text in {"", "-", "—", "–", "--"}:
        return 0

    negative = text.startswith("(") and text.endswith(")")

    if negative:
        text = text[1:-1].strip()

    text = (
        text.replace("$", "")
        .replace(",", "")
        .replace("*", "")
        .replace("\u00a0", "")
        .strip()
    )

    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Unable to parse financial value: {value!r}") from exc

    if amount != amount.to_integral_value():
        raise ValueError(
            f"Expected whole-dollar CMS value but found decimal: {value!r}"
        )

    parsed = int(amount)

    return -parsed if negative else parsed


def identify_row_type(service_category: str) -> tuple[str, bool]:
    """
    Classify CMS-21 service-category rows.

    Known FY2015 control-total labels include:
      Total
      C-Total Net
      T-Total Net Expenditures
    """
    normalized = normalize_label(service_category)

    # Remove common CMS prefixes such as C- and T-.
    classification_label = re.sub(
        r"^[a-z]\s*-\s*",
        "",
        normalized,
    ).strip()

    if "subtotal" in classification_label:
        return "SUBTOTAL", False

    control_total_labels = {
        "total",
        "grand total",
        "total net",
        "total net expenditures",
        "net expenditures total",
    }

    if classification_label in control_total_labels:
        return "CONTROL_TOTAL", True

    return "DETAIL", False


def find_column(header_values: Iterable[Any], expected_name: str) -> int:
    expected = normalize_label(expected_name)

    for column_index, value in enumerate(header_values):
        if normalize_label(value) == expected:
            return column_index

    available = [
        raw_text(value)
        for value in header_values
        if raw_text(value) is not None
    ]

    raise ValueError(
        f"Required column {expected_name!r} was not found. "
        f"Available header values: {available}"
    )


def read_worksheet_rows(
    workbook_path: Path,
    worksheet: WorksheetSpec,
) -> list[dict[str, Any]]:
    frame = pd.read_excel(
        workbook_path,
        sheet_name=worksheet.sheet_name,
        header=None,
        dtype=object,
        engine="openpyxl",
    )

    header_index = worksheet.header_row_excel - 1

    if header_index >= len(frame):
        raise ValueError(
            f"{worksheet.sheet_name}: header row "
            f"{worksheet.header_row_excel} is outside the worksheet."
        )

    header_values = frame.iloc[header_index].tolist()

    service_column = find_column(header_values, "Service Category")
    total_column = find_column(header_values, "Total Computable")
    federal_column = find_column(header_values, "Federal Share")
    state_column = find_column(header_values, "State Share")

    rows: list[dict[str, Any]] = []

    for dataframe_index in range(header_index + 1, len(frame)):
        excel_row = dataframe_index + 1

        service_value = frame.iat[dataframe_index, service_column]
        total_value = frame.iat[dataframe_index, total_column]
        federal_value = frame.iat[dataframe_index, federal_column]
        state_value = frame.iat[dataframe_index, state_column]

        if (
            is_blank(service_value)
            and is_blank(total_value)
            and is_blank(federal_value)
            and is_blank(state_value)
        ):
            continue

        if is_blank(service_value):
            raise ValueError(
                f"{worksheet.sheet_name} row {excel_row}: "
                "financial values were present without a service category."
            )

        service_category_source = raw_text(service_value)

        if service_category_source is None:
            continue

        total_computable = parse_integer(total_value)
        federal_share = parse_integer(federal_value)
        state_share = parse_integer(state_value)

        if total_computable != federal_share + state_share:
            raise ValueError(
                f"{worksheet.sheet_name} row {excel_row}: accounting identity "
                f"failed. Total={total_computable:,}; "
                f"Federal={federal_share:,}; State={state_share:,}."
            )

        row_type, is_control_total = identify_row_type(
            service_category_source
        )

        is_financing_adjustment = (
            worksheet.worksheet_type == "MCHIP_20_PERCENT"
        )
        is_additive_expenditure = not is_financing_adjustment

        rows.append(
            {
                "source_row": excel_row,
                "raw_service_category": raw_text(service_value),
                "raw_total_computable": raw_text(total_value),
                "raw_federal_share": raw_text(federal_value),
                "raw_state_share": raw_text(state_value),
                "service_category_source": service_category_source,
                "service_category_normalized": normalize_service_category(
                    service_category_source
                ),
                "total_computable": total_computable,
                "federal_share": federal_share,
                "state_share": state_share,
                "row_type": row_type,
                "is_control_total": is_control_total,
                "is_financing_adjustment": is_financing_adjustment,
                "is_additive_expenditure": is_additive_expenditure,
            }
        )

    if not rows:
        raise ValueError(
            f"No data rows were found in worksheet {worksheet.sheet_name!r}."
        )

    return rows


def remove_existing_batch(
    cursor,
    config: Cms21Config,
    workbook_path: Path,
) -> None:
    cursor.execute(
        """
        SELECT load_batch_id
        FROM chip.cms21_load_batch
        WHERE fiscal_year = %s
          AND source_workbook = %s
          AND source_file_name = %s;
        """,
        (
            config.fiscal_year,
            workbook_path.as_posix(),
            workbook_path.name,
        ),
    )

    existing = cursor.fetchone()

    if existing is None:
        return

    load_batch_id = existing[0]

    cursor.execute(
        """
        DELETE FROM chip.cms21_expenditure
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    cursor.execute(
        """
        DELETE FROM chip.cms21_raw_row
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    cursor.execute(
        """
        DELETE FROM chip.cms21_load_batch
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )


def create_load_batch(
    cursor,
    config: Cms21Config,
    workbook_path: Path,
    notes: str | None,
) -> int:
    cursor.execute(
        """
        INSERT INTO chip.cms21_load_batch (
            fiscal_year,
            source_workbook,
            source_file_name,
            source_file_sha256,
            loader_name,
            loader_version,
            notes
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING load_batch_id;
        """,
        (
            config.fiscal_year,
            workbook_path.as_posix(),
            workbook_path.name,
            calculate_sha256(workbook_path),
            LOADER_NAME,
            LOADER_VERSION,
            notes,
        ),
    )

    return cursor.fetchone()[0]


def insert_raw_row(
    cursor,
    load_batch_id: int,
    config: Cms21Config,
    worksheet: WorksheetSpec,
    row: dict[str, Any],
) -> int:
    cursor.execute(
        """
        INSERT INTO chip.cms21_raw_row (
            load_batch_id,
            fiscal_year,
            state_fips,
            state_abbreviation,
            state_name,
            worksheet_type,
            source_sheet,
            source_row,
            raw_service_category,
            raw_total_computable,
            raw_federal_share,
            raw_state_share
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        RETURNING raw_row_id;
        """,
        (
            load_batch_id,
            config.fiscal_year,
            config.state_fips,
            config.state_abbreviation,
            config.state_name,
            worksheet.worksheet_type,
            worksheet.sheet_name,
            row["source_row"],
            row["raw_service_category"],
            row["raw_total_computable"],
            row["raw_federal_share"],
            row["raw_state_share"],
        ),
    )

    return cursor.fetchone()[0]


def insert_curated_row(
    cursor,
    raw_row_id: int,
    load_batch_id: int,
    config: Cms21Config,
    workbook_path: Path,
    worksheet: WorksheetSpec,
    row: dict[str, Any],
) -> None:
    cursor.execute(
        """
        INSERT INTO chip.cms21_expenditure (
            raw_row_id,
            load_batch_id,
            fiscal_year,
            state_fips,
            state_abbreviation,
            state_name,
            worksheet_type,
            service_category_source,
            service_category_normalized,
            total_computable,
            federal_share,
            state_share,
            row_type,
            is_control_total,
            is_financing_adjustment,
            is_additive_expenditure,
            source_workbook,
            source_sheet,
            source_row
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        );
        """,
        (
            raw_row_id,
            load_batch_id,
            config.fiscal_year,
            config.state_fips,
            config.state_abbreviation,
            config.state_name,
            worksheet.worksheet_type,
            row["service_category_source"],
            row["service_category_normalized"],
            row["total_computable"],
            row["federal_share"],
            row["state_share"],
            row["row_type"],
            row["is_control_total"],
            row["is_financing_adjustment"],
            row["is_additive_expenditure"],
            workbook_path.as_posix(),
            worksheet.sheet_name,
            row["source_row"],
        ),
    )


def validate_loaded_batch(cursor, load_batch_id: int) -> None:
    cursor.execute(
        """
        SELECT
            worksheet_type,
            COUNT(*) AS curated_rows,
            COUNT(*) FILTER (WHERE is_control_total) AS control_total_rows
        FROM chip.cms21_expenditure
        WHERE load_batch_id = %s
        GROUP BY worksheet_type
        ORDER BY worksheet_type;
        """,
        (load_batch_id,),
    )

    worksheet_results = cursor.fetchall()

    expected_types = {"CHIP", "MCHIP", "MCHIP_20_PERCENT"}
    actual_types = {row[0] for row in worksheet_results}

    if actual_types != expected_types:
        raise ValueError(
            f"Worksheet-type validation failed. "
            f"Expected {expected_types}; found {actual_types}."
        )

    for worksheet_type, _row_count, control_total_count in worksheet_results:
        if control_total_count != 1:
            raise ValueError(
                f"{worksheet_type}: expected exactly one control total; "
                f"found {control_total_count}."
            )

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM chip.cms21_expenditure
        WHERE load_batch_id = %s
          AND total_computable <> federal_share + state_share;
        """,
        (load_batch_id,),
    )

    identity_failures = cursor.fetchone()[0]

    if identity_failures:
        raise ValueError(
            f"Accounting identity failed for {identity_failures} curated rows."
        )


def load_cms21_workbook(
    workbook_path: Path,
    config: Cms21Config,
    *,
    replace: bool = False,
    notes: str | None = None,
) -> LoadSummary:
    workbook_path = Path(workbook_path)

    if not workbook_path.exists():
        raise FileNotFoundError(f"CMS-21 workbook not found: {workbook_path}")

    if workbook_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError(
            "The generic CMS-21 loader currently supports .xlsx and .xlsm files."
        )

    parsed_worksheets: list[
        tuple[WorksheetSpec, list[dict[str, Any]]]
    ] = []

    for worksheet in config.worksheets:
        rows = read_worksheet_rows(workbook_path, worksheet)
        parsed_worksheets.append((worksheet, rows))

    conn = get_connection()

    try:
        cursor = conn.cursor()

        if replace:
            remove_existing_batch(cursor, config, workbook_path)

        load_batch_id = create_load_batch(
            cursor,
            config,
            workbook_path,
            notes,
        )

        summary = LoadSummary(load_batch_id=load_batch_id)

        for worksheet, rows in parsed_worksheets:
            for row in rows:
                raw_row_id = insert_raw_row(
                    cursor,
                    load_batch_id,
                    config,
                    worksheet,
                    row,
                )

                summary.raw_rows += 1

                insert_curated_row(
                    cursor,
                    raw_row_id,
                    load_batch_id,
                    config,
                    workbook_path,
                    worksheet,
                    row,
                )

                summary.curated_rows += 1

                if row["is_control_total"]:
                    summary.control_totals += 1

        validate_loaded_batch(cursor, load_batch_id)

        conn.commit()
        cursor.close()

        return summary

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def fetch_control_totals(load_batch_id: int) -> list[tuple]:
    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                worksheet_type,
                total_computable,
                federal_share,
                state_share,
                is_additive_expenditure,
                is_financing_adjustment
            FROM chip.cms21_expenditure
            WHERE load_batch_id = %s
              AND is_control_total = TRUE
            ORDER BY worksheet_type;
            """,
            (load_batch_id,),
        )

        results = cursor.fetchall()
        cursor.close()
        return results

    finally:
        conn.close()