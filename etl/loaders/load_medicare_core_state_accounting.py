from __future__ import annotations

import csv
import hashlib
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from etl.common.db import get_connection

CORE_ARITHMETIC_TOLERANCE = Decimal("0.01")

SOURCE_FILE = Path(
    "data/raw/cms/medicare/validation/accounting_integration_v0_1/"
    "cms_medicare_core_annual_profile_v0_1.csv"
)

EXPECTED_ROWS = 10
EXPECTED_YEARS = set(range(2015, 2025))
EXPECTED_METHODOLOGY = (
    "CMS-MEDICARE-ACCOUNTING-INTEGRATION-PROFILE-v0.1"
)
EXPECTED_LEDGER_STATUS = "NOT_YET_AUTHORIZED"

# Preserve source values at native precision, but treat sub-cent
# differences in independently recomputed derived totals as numerical
# serialization effects. A difference of $0.01 or greater fails.
CORE_ARITHMETIC_TOLERANCE = Decimal("0.01")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def required_text(row: dict[str, str], column: str) -> str:
    value = row.get(column)

    if value is None or value.strip() == "":
        raise ValueError(f"Missing required value for {column}")

    return value.strip()


def required_decimal(row: dict[str, str], column: str) -> Decimal:
    text = required_text(row, column)

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"Invalid numeric value for {column}: {text!r}"
        ) from exc


def required_integer(row: dict[str, str], column: str) -> int:
    return int(required_text(row, column))


def load_source_rows() -> list[dict[str, object]]:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(SOURCE_FILE)

    rows: list[dict[str, object]] = []

    with SOURCE_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        required_columns = {
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
        }

        actual_columns = set(reader.fieldnames or [])
        missing = required_columns - actual_columns

        if missing:
            raise ValueError(
                "Source artifact is missing required columns: "
                + ", ".join(sorted(missing))
            )

        for source_row_number, row in enumerate(reader, start=2):
            year = required_integer(row, "year")

            if year not in EXPECTED_YEARS:
                raise ValueError(
                    f"Row {source_row_number}: unexpected year {year}"
                )

            methodology = required_text(
                row,
                "methodology_version",
            )

            if methodology != EXPECTED_METHODOLOGY:
                raise ValueError(
                    f"Row {source_row_number}: unexpected methodology "
                    f"{methodology!r}"
                )

            ledger_status = required_text(row, "ledger_status")

            if ledger_status != EXPECTED_LEDGER_STATUS:
                raise ValueError(
                    f"Row {source_row_number}: unexpected ledger status "
                    f"{ledger_status!r}"
                )

            original = required_decimal(
                row,
                "original_medicare_actual_ffs_dollars",
            )
            partc = required_decimal(
                row,
                "partc_reconstructed_dollars",
            )
            partd = required_decimal(
                row,
                "partd_reconstructed_dollars",
            )
            core = required_decimal(
                row,
                "core_medicare_sum_dollars",
            )

            with localcontext() as ctx:
                ctx.prec = 80
                calculated_core = original + partc + partd
                arithmetic_difference = abs(core - calculated_core)

            if arithmetic_difference >= CORE_ARITHMETIC_TOLERANCE:
                raise ValueError(
                    f"Row {source_row_number}: core arithmetic failure: "
                    f"core={core} "
                    f"calculated={calculated_core} "
                    f"difference={arithmetic_difference} "
                    f"tolerance={CORE_ARITHMETIC_TOLERANCE}"
                )

            rows.append(
                {
                    "year": year,
                    "original":
                        original,
                    "partc":
                        partc,
                    "partd":
                        partd,
                    "core":
                        core,
                    "county_rows":
                        required_integer(
                            row,
                            "original_medicare_county_rows",
                        ),
                    "beneficiaries":
                        required_integer(
                            row,
                            "original_medicare_beneficiaries",
                        ),
                    "partc_months":
                        required_integer(
                            row,
                            "partc_months_processed",
                        ),
                    "partc_year_completeness":
                        required_text(
                            row,
                            "partc_year_completeness",
                        ),
                    "partc_reconstruction_coverage_pct":
                        required_decimal(
                            row,
                            "partc_reconstruction_coverage_pct",
                        ),
                    "partc_accounting_coverage_pct":
                        required_decimal(
                            row,
                            "partc_accounting_coverage_pct",
                        ),
                    "partd_dollar_source_field":
                        required_text(
                            row,
                            "partd_dollar_source_field",
                        ),
                    "partd_coverage_status":
                        required_text(
                            row,
                            "partd_coverage_status",
                        ),
                    "combined_period_status":
                        required_text(
                            row,
                            "combined_period_status",
                        ),
                    "timing_basis_status":
                        required_text(
                            row,
                            "timing_basis_status",
                        ),
                    "ledger_status":
                        ledger_status,
                    "methodology_version":
                        methodology,
                }
            )

    if len(rows) != EXPECTED_ROWS:
        raise ValueError(
            f"Expected {EXPECTED_ROWS} rows; found {len(rows)}"
        )

    years = {int(row["year"]) for row in rows}

    if years != EXPECTED_YEARS:
        raise ValueError(
            f"Unexpected year universe: {sorted(years)}"
        )

    return rows


def fetch_washington_state_id(cur) -> int:
    cur.execute(
        """
        SELECT state_id
        FROM reference.state_registry
        WHERE state_fips = '53'
        """
    )

    rows = cur.fetchall()

    if len(rows) != 1:
        raise RuntimeError(
            "Expected exactly one Washington state registry row "
            f"for state_fips='53'; found {len(rows)}"
        )

    return int(rows[0][0])


def main() -> None:
    rows = load_source_rows()

    source_sha256 = sha256_file(SOURCE_FILE)
    source_file = SOURCE_FILE.as_posix()

    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                state_id = fetch_washington_state_id(cur)

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM cms.medicare_core_state_year
                    """
                )

                existing_rows = cur.fetchone()[0]

                if existing_rows != 0:
                    raise RuntimeError(
                        "cms.medicare_core_state_year is not empty "
                        f"({existing_rows} rows). Refusing to overwrite "
                        "a previously promoted certification artifact."
                    )

                insert_sql = """
                    INSERT INTO cms.medicare_core_state_year (
                        calendar_year,
                        state_id,
                        original_medicare_actual_ffs_dollars,
                        partc_reconstructed_dollars,
                        partd_reconstructed_dollars,
                        core_medicare_sum_dollars,
                        original_medicare_county_rows,
                        original_medicare_beneficiaries,
                        partc_months_processed,
                        partc_year_completeness,
                        partc_reconstruction_coverage_pct,
                        partc_accounting_coverage_pct,
                        partd_dollar_source_field,
                        partd_coverage_status,
                        combined_period_status,
                        timing_basis_status,
                        ledger_status,
                        methodology_version,
                        source_file,
                        source_sha256
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                """

                prepared = [
                    (
                        row["year"],
                        state_id,
                        row["original"],
                        row["partc"],
                        row["partd"],
                        row["core"],
                        row["county_rows"],
                        row["beneficiaries"],
                        row["partc_months"],
                        row["partc_year_completeness"],
                        row["partc_reconstruction_coverage_pct"],
                        row["partc_accounting_coverage_pct"],
                        row["partd_dollar_source_field"],
                        row["partd_coverage_status"],
                        row["combined_period_status"],
                        row["timing_basis_status"],
                        row["ledger_status"],
                        row["methodology_version"],
                        source_file,
                        source_sha256,
                    )
                    for row in rows
                ]

                cur.executemany(insert_sql, prepared)

                cur.execute(
                    """
                    SELECT
                        COUNT(*),
                        COUNT(DISTINCT calendar_year),
                        MIN(calendar_year),
                        MAX(calendar_year)
                    FROM cms.medicare_core_state_year
                    """
                )

                (
                    loaded_rows,
                    loaded_years,
                    min_year,
                    max_year,
                ) = cur.fetchone()

                if loaded_rows != 10:
                    raise RuntimeError(
                        f"Post-load row count {loaded_rows}; expected 10"
                    )

                if loaded_years != 10:
                    raise RuntimeError(
                        f"Post-load year count {loaded_years}; expected 10"
                    )

                if min_year != 2015 or max_year != 2024:
                    raise RuntimeError(
                        "Post-load year range is not 2015-2024"
                    )

        print("=" * 80)
        print("ETL-170 MEDICARE CORE STATE ACCOUNTING LOAD")
        print("=" * 80)
        print(f"Source file     : {source_file}")
        print(f"Source SHA-256  : {source_sha256}")
        print("Rows loaded     : 10")
        print("Years           : 2015-2024")
        print("State           : Washington (53)")
        print(f"Methodology     : {EXPECTED_METHODOLOGY}")
        print(f"Ledger status   : {EXPECTED_LEDGER_STATUS}")
        print()
        print("LOAD RESULT: PASS")

    finally:
        conn.close()


if __name__ == "__main__":
    main()