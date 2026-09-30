"""
ETL-171B — IRS Gross Collections Structural Profile v0.1
=========================================================

Read-only structural and semantic profiling of the preserved official
IRS Data Book Table 1-5 workbooks for FFY2015-FFY2024.

No database writes.
No tax-incidence allocation.
No accounting transformation.
No ledger authorization.
No inferred zeroes.

Objectives
----------
1. Inventory every workbook and worksheet.
2. Preserve displayed cell values from the leading portion of each sheet.
3. Locate Washington rows without assuming a fixed row number.
4. Capture the apparent header structure surrounding Washington.
5. Report numeric values exactly as stored.
6. Test whether the published Washington row contains an internally
   identifiable total and component structure.
7. Produce evidence files for semantic review before extraction logic
   is written.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


CERTIFICATION_ID = "IRS-GROSS-COLLECTIONS-PROFILE-v0.1"

START_YEAR = 2015
END_YEAR = 2024

SOURCE_DIR = Path(
    "data/raw/irs/gross_collections/source"
)

OUTPUT_DIR = Path(
    "data/raw/irs/gross_collections/validation/"
    "structural_profile_v0_1"
)

SUMMARY_PATH = OUTPUT_DIR / "workbook_summary.csv"
WASHINGTON_PATH = OUTPUT_DIR / "washington_rows.csv"
CONTEXT_PATH = OUTPUT_DIR / "washington_context.json"
REPORT_PATH = OUTPUT_DIR / "profile_report.txt"


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


def clean_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    return value


def json_safe(value: Any) -> Any:
    value = clean_scalar(value)

    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def row_as_values(
    frame: pd.DataFrame,
    row_index: int,
) -> list[Any]:
    return [
        json_safe(value)
        for value in frame.iloc[row_index].tolist()
    ]


def normalized_text(value: Any) -> str:
    value = clean_scalar(value)

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def row_contains_washington(
    frame: pd.DataFrame,
    row_index: int,
) -> bool:
    for value in frame.iloc[row_index].tolist():
        text = normalized_text(value)

        if text.lower() == "washington":
            return True

    return False


def numeric_cells(
    frame: pd.DataFrame,
    row_index: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for column_index, value in enumerate(
        frame.iloc[row_index].tolist()
    ):
        value = clean_scalar(value)

        if value is None:
            continue

        if isinstance(value, bool):
            continue

        if isinstance(value, (int, float)):
            results.append(
                {
                    "column_index": column_index,
                    "value": json_safe(value),
                }
            )
            continue

        text = str(value).strip().replace(",", "")

        if not text:
            continue

        try:
            number = float(text)
        except ValueError:
            continue

        results.append(
            {
                "column_index": column_index,
                "value": number,
            }
        )

    return results


def capture_context(
    frame: pd.DataFrame,
    row_index: int,
    before: int = 12,
    after: int = 3,
) -> list[dict[str, Any]]:
    start = max(0, row_index - before)
    stop = min(len(frame), row_index + after + 1)

    context: list[dict[str, Any]] = []

    for index in range(start, stop):
        context.append(
            {
                "zero_based_row_index": index,
                "excel_like_row_number": index + 1,
                "values": row_as_values(
                    frame,
                    index,
                ),
            }
        )

    return context


def inspect_workbook(
    path: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    fiscal_year = fiscal_year_from_name(path)
    digest = sha256_file(path)

    engine = (
        "xlrd"
        if path.suffix.lower() == ".xls"
        else "openpyxl"
    )

    workbook = pd.ExcelFile(
        path,
        engine=engine,
    )

    workbook_rows: list[dict[str, Any]] = []
    washington_rows: list[dict[str, Any]] = []
    context_records: list[dict[str, Any]] = []

    for sheet_name in workbook.sheet_names:
        frame = pd.read_excel(
            path,
            sheet_name=sheet_name,
            header=None,
            dtype=object,
            engine=engine,
        )

        nonempty_rows = int(
            frame.notna().any(axis=1).sum()
        )

        nonempty_columns = int(
            frame.notna().any(axis=0).sum()
        )

        wa_indices = [
            index
            for index in range(len(frame))
            if row_contains_washington(
                frame,
                index,
            )
        ]

        workbook_rows.append(
            {
                "fiscal_year": fiscal_year,
                "source_file": path.name,
                "source_sha256": digest,
                "file_format": path.suffix.lower().lstrip("."),
                "sheet_name": sheet_name,
                "physical_rows": len(frame),
                "physical_columns": len(frame.columns),
                "nonempty_rows": nonempty_rows,
                "nonempty_columns": nonempty_columns,
                "washington_match_count": len(wa_indices),
            }
        )

        for row_index in wa_indices:
            numeric = numeric_cells(
                frame,
                row_index,
            )

            washington_rows.append(
                {
                    "fiscal_year": fiscal_year,
                    "source_file": path.name,
                    "source_sha256": digest,
                    "sheet_name": sheet_name,
                    "zero_based_row_index": row_index,
                    "excel_like_row_number": row_index + 1,
                    "physical_column_count": len(frame.columns),
                    "numeric_cell_count": len(numeric),
                    "row_values_json": json.dumps(
                        row_as_values(
                            frame,
                            row_index,
                        ),
                        ensure_ascii=False,
                    ),
                    "numeric_cells_json": json.dumps(
                        numeric,
                        ensure_ascii=False,
                    ),
                }
            )

            context_records.append(
                {
                    "fiscal_year": fiscal_year,
                    "source_file": path.name,
                    "source_sha256": digest,
                    "sheet_name": sheet_name,
                    "washington_zero_based_row_index": row_index,
                    "washington_excel_like_row_number": row_index + 1,
                    "context_rows": capture_context(
                        frame,
                        row_index,
                    ),
                }
            )

    return (
        workbook_rows,
        washington_rows,
        context_records,
    )


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

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


def write_report(
    workbook_rows: list[dict[str, Any]],
    washington_rows: list[dict[str, Any]],
) -> None:
    lines: list[str] = []

    lines.append("=" * 100)
    lines.append(
        "IRS GROSS COLLECTIONS STRUCTURAL PROFILE v0.1"
    )
    lines.append("=" * 100)
    lines.append("")
    lines.append(
        f"Certification ID : {CERTIFICATION_ID}"
    )
    lines.append(
        f"Fiscal years     : {START_YEAR}-{END_YEAR}"
    )
    lines.append(
        f"Workbooks        : "
        f"{len(set(row['source_file'] for row in workbook_rows))}"
    )
    lines.append(
        f"Worksheet rows   : {len(workbook_rows)}"
    )
    lines.append(
        f"Washington hits  : {len(washington_rows)}"
    )
    lines.append("Database writes  : NONE")
    lines.append("Accounting edits : NONE")
    lines.append("")

    lines.append("=" * 100)
    lines.append("WORKBOOK / WORKSHEET INVENTORY")
    lines.append("=" * 100)
    lines.append("")

    for row in workbook_rows:
        lines.append(
            f"FY{row['fiscal_year']} | "
            f"{row['source_file']} | "
            f"sheet={row['sheet_name']!r} | "
            f"rows={row['physical_rows']} | "
            f"cols={row['physical_columns']} | "
            f"nonempty_rows={row['nonempty_rows']} | "
            f"nonempty_cols={row['nonempty_columns']} | "
            f"WA_hits={row['washington_match_count']}"
        )

    lines.append("")
    lines.append("=" * 100)
    lines.append("WASHINGTON ROWS")
    lines.append("=" * 100)
    lines.append("")

    for row in sorted(
        washington_rows,
        key=lambda item: (
            item["fiscal_year"],
            item["sheet_name"],
            item["zero_based_row_index"],
        ),
    ):
        lines.append(
            f"FY{row['fiscal_year']} | "
            f"sheet={row['sheet_name']!r} | "
            f"row={row['excel_like_row_number']} | "
            f"numeric_cells={row['numeric_cell_count']}"
        )
        lines.append(
            f"  values : {row['row_values_json']}"
        )
        lines.append(
            f"  numeric: {row['numeric_cells_json']}"
        )
        lines.append("")

    years_with_wa = {
        int(row["fiscal_year"])
        for row in washington_rows
    }

    expected_years = set(
        range(START_YEAR, END_YEAR + 1)
    )

    missing_years = sorted(
        expected_years - years_with_wa
    )

    duplicate_years = sorted(
        year
        for year in expected_years
        if sum(
            1
            for row in washington_rows
            if int(row["fiscal_year"]) == year
        )
        != 1
    )

    lines.append("=" * 100)
    lines.append("PROFILE RESULT")
    lines.append("=" * 100)
    lines.append("")

    if missing_years:
        lines.append(
            f"Missing Washington years : {missing_years}"
        )
    else:
        lines.append(
            "Missing Washington years : NONE"
        )

    if duplicate_years:
        lines.append(
            "Years without exactly one Washington row : "
            f"{duplicate_years}"
        )
    else:
        lines.append(
            "Exactly one Washington row per year       : PASS"
        )

    lines.append("")
    lines.append(
        "No semantic column mapping has been imposed."
    )
    lines.append(
        "No published values have been rescaled."
    )
    lines.append(
        "No gross-collections accounting decision has been made."
    )

    REPORT_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    print("=" * 100)
    print(
        "ETL-171B — IRS GROSS COLLECTIONS "
        "STRUCTURAL PROFILE v0.1"
    )
    print("=" * 100)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = sorted(
        [
            path
            for path in SOURCE_DIR.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".xls", ".xlsx"}
        ],
        key=fiscal_year_from_name,
    )

    expected_years = list(
        range(START_YEAR, END_YEAR + 1)
    )

    observed_years = [
        fiscal_year_from_name(path)
        for path in files
    ]

    if observed_years != expected_years:
        raise RuntimeError(
            "Expected exactly one source workbook for each "
            f"FY{START_YEAR}-FY{END_YEAR}; "
            f"observed years={observed_years}"
        )

    workbook_rows: list[dict[str, Any]] = []
    washington_rows: list[dict[str, Any]] = []
    context_records: list[dict[str, Any]] = []

    for path in files:
        year = fiscal_year_from_name(path)

        print(
            f"Profiling FY{year}: {path.name}"
        )

        (
            workbook_result,
            washington_result,
            context_result,
        ) = inspect_workbook(path)

        workbook_rows.extend(
            workbook_result
        )

        washington_rows.extend(
            washington_result
        )

        context_records.extend(
            context_result
        )

    write_csv(
        SUMMARY_PATH,
        workbook_rows,
    )

    write_csv(
        WASHINGTON_PATH,
        washington_rows,
    )

    with CONTEXT_PATH.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            context_records,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    write_report(
        workbook_rows,
        washington_rows,
    )

    print()
    print("=" * 100)
    print("PROFILE COMPLETE")
    print("=" * 100)
    print(
        f"Workbooks             : {len(files)}"
    )
    print(
        f"Worksheet observations: {len(workbook_rows)}"
    )
    print(
        f"Washington row hits   : {len(washington_rows)}"
    )
    print(
        f"Summary               : {SUMMARY_PATH}"
    )
    print(
        f"Washington rows       : {WASHINGTON_PATH}"
    )
    print(
        f"Context evidence      : {CONTEXT_PATH}"
    )
    print(
        f"Human-readable report : {REPORT_PATH}"
    )
    print("Database writes       : NONE")
    print("Accounting changes    : NONE")


if __name__ == "__main__":
    main()