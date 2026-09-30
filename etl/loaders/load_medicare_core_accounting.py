from __future__ import annotations

import csv
import hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path

from etl.db import get_connection


SOURCE_FILE = Path(
    "data/raw/cms/medicare/validation/county_integration_v0_1/"
    "cms_medicare_county_integration_v0_1.csv"
)

EXPECTED_ROWS = 390
EXPECTED_YEARS = set(range(2015, 2025))
EXPECTED_COUNTIES = 39

EXPECTED_METHODOLOGY = "CMS-MEDICARE-COUNTY-INTEGRATION-v0.1"
EXPECTED_LEDGER_AUTHORIZATION = "NOT_AUTHORIZED_BY_THIS_CERTIFICATION"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def nullable_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None

    text = value.strip()

    if text == "":
        return None

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value: {value!r}") from exc


def nullable_integer(value: str | None) -> int | None:
    if value is None:
        return None

    text = value.strip()

    if text == "":
        return None

    return int(text)


def required_text(row: dict[str, str], column: str) -> str:
    value = row.get(column)

    if value is None or value.strip() == "":
        raise ValueError(f"Missing required value for {column}")

    return value.strip()

def nullable_text(value: str | None) -> str | None:
    if value is None:
        return None

    text = value.strip()

    if text == "":
        return None

    return text

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
        }

        actual_columns = set(reader.fieldnames or [])
        missing_columns = required_columns - actual_columns

        if missing_columns:
            raise ValueError(
                "Source artifact is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        for source_row_number, row in enumerate(reader, start=2):
            calendar_year = int(required_text(row, "calendar_year"))
            county_fips = required_text(row, "county_fips")
            county_name = required_text(row, "county")

            methodology_version = required_text(
                row,
                "methodology_version",
            )

            ledger_authorization = required_text(
                row,
                "ledger_authorization",
            )

            if methodology_version != EXPECTED_METHODOLOGY:
                raise ValueError(
                    f"Row {source_row_number}: unexpected methodology "
                    f"{methodology_version!r}"
                )

            if ledger_authorization != EXPECTED_LEDGER_AUTHORIZATION:
                raise ValueError(
                    f"Row {source_row_number}: unexpected ledger "
                    f"authorization {ledger_authorization!r}"
                )

            if calendar_year not in EXPECTED_YEARS:
                raise ValueError(
                    f"Row {source_row_number}: unexpected year "
                    f"{calendar_year}"
                )

            if len(county_fips) != 5 or not county_fips.startswith("53"):
                raise ValueError(
                    f"Row {source_row_number}: invalid Washington "
                    f"county FIPS {county_fips!r}"
                )

            rows.append(
                {
                    "source_row_number": source_row_number,
                    "calendar_year": calendar_year,
                    "county_fips": county_fips,
                    "county_name": county_name,
                    "original_medicare_ffs_dollars":
                        nullable_decimal(
                            row["original_medicare_ffs_dollars"]
                        ),
                    "partc_dollars":
                        nullable_decimal(row["partc_dollars"]),
                    "partd_dollars":
                        nullable_decimal(row["partd_dollars"]),
                    "core_medicare_dollars":
                        nullable_decimal(row["core_medicare_dollars"]),
                    "original_medicare_status":
                        required_text(
                            row,
                            "original_medicare_status",
                        ),
                    "partc_status":
                        required_text(row, "partc_status"),
                    "partd_status":
                        required_text(row, "partd_status"),
                    "core_value_status":
                        required_text(row, "core_value_status"),
                    "partc_months_represented":
                        nullable_integer(
                            row["partc_months_represented"]
                        ),
                    "partd_months_with_reconstructed_dollars":
                        nullable_integer(
                            row[
                                "partd_months_with_reconstructed_dollars"
                            ]
                        ),
                    "partc_year_completeness":
                        nullable_text(
                            row["partc_year_completeness"]
                        ),
                    "partd_coverage_status":
                        required_text(
                            row,
                            "partd_coverage_status",
                        ),
                    "time_window_status":
                        required_text(row, "time_window_status"),
                    "timing_basis":
                        required_text(row, "timing_basis"),
                    "original_medicare_geography_basis":
                        required_text(
                            row,
                            "original_medicare_geography_basis",
                        ),
                    "partc_geography_basis":
                        nullable_text(
                            row["partc_geography_basis"]
                        ),
                    "partd_geography_basis":
                        nullable_text(
                            row["partd_geography_basis"]    
                        ),
                    "partd_payment_match_basis":
                        required_text(
                            row,
                            "partd_payment_match_basis",
                        ),
                    "mssp_treatment":
                        required_text(row, "mssp_treatment"),
                    "rds_treatment":
                        required_text(row, "rds_treatment"),
                    "washington_mffs_treatment":
                        required_text(
                            row,
                            "washington_mffs_treatment",
                        ),
                    "ledger_authorization":
                        ledger_authorization,
                    "methodology_version":
                        methodology_version,
                }
            )

    return rows


def validate_source_shape(rows: list[dict[str, object]]) -> None:
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(
            f"Expected {EXPECTED_ROWS} source rows; found {len(rows)}"
        )

    years = {int(row["calendar_year"]) for row in rows}
    counties = {str(row["county_fips"]) for row in rows}

    if years != EXPECTED_YEARS:
        raise ValueError(
            f"Unexpected year universe: {sorted(years)}"
        )

    if len(counties) != EXPECTED_COUNTIES:
        raise ValueError(
            f"Expected {EXPECTED_COUNTIES} counties; "
            f"found {len(counties)}"
        )

    keys = [
        (int(row["calendar_year"]), str(row["county_fips"]))
        for row in rows
    ]

    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate calendar_year/county_fips keys")


def fetch_county_registry(cur) -> dict[str, tuple[int, str]]:
    cur.execute(
        """
        SELECT
            county_id,
            full_fips,
            county_name
        FROM reference.county_registry
        WHERE full_fips LIKE '53%'
        ORDER BY full_fips
        """
    )

    registry: dict[str, tuple[int, str]] = {}

    for county_id, full_fips, county_name in cur.fetchall():
        registry[str(full_fips).strip()] = (
            int(county_id),
            str(county_name).strip(),
        )

    return registry


def normalized_county_name(value: str) -> str:
    text = value.strip()

    if text.lower().endswith(" county"):
        text = text[:-7]

    return text.strip().lower()


def main() -> None:
    rows = load_source_rows()
    validate_source_shape(rows)

    source_sha256 = sha256_file(SOURCE_FILE)
    source_file = SOURCE_FILE.as_posix()

    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                registry = fetch_county_registry(cur)

                if len(registry) != EXPECTED_COUNTIES:
                    raise ValueError(
                        "Washington county registry does not contain "
                        f"{EXPECTED_COUNTIES} canonical counties; "
                        f"found {len(registry)}"
                    )

                prepared_rows: list[tuple[object, ...]] = []

                for row in rows:
                    county_fips = str(row["county_fips"])

                    if county_fips not in registry:
                        raise ValueError(
                            f"Unmatched county FIPS {county_fips}"
                        )

                    county_id, registry_name = registry[county_fips]
                    source_name = str(row["county_name"])

                    if (
                        normalized_county_name(source_name)
                        != normalized_county_name(registry_name)
                    ):
                        raise ValueError(
                            f"County-name mismatch for {county_fips}: "
                            f"source={source_name!r}, "
                            f"registry={registry_name!r}"
                        )

                    prepared_rows.append(
                        (
                            row["calendar_year"],
                            county_fips,
                            county_id,
                            row["original_medicare_ffs_dollars"],
                            row["partc_dollars"],
                            row["partd_dollars"],
                            row["core_medicare_dollars"],
                            row["original_medicare_status"],
                            row["partc_status"],
                            row["partd_status"],
                            row["core_value_status"],
                            row["partc_months_represented"],
                            row[
                                "partd_months_with_reconstructed_dollars"
                            ],
                            row["partc_year_completeness"],
                            row["partd_coverage_status"],
                            row["time_window_status"],
                            row["timing_basis"],
                            row[
                                "original_medicare_geography_basis"
                            ],
                            row["partc_geography_basis"],
                            row["partd_geography_basis"],
                            row["partd_payment_match_basis"],
                            row["mssp_treatment"],
                            row["rds_treatment"],
                            row["washington_mffs_treatment"],
                            row["ledger_authorization"],
                            row["methodology_version"],
                            source_file,
                            source_sha256,
                        )
                    )

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM cms.medicare_core_county_year
                    """
                )
                existing_rows = cur.fetchone()[0]

                if existing_rows != 0:
                    raise RuntimeError(
                        "cms.medicare_core_county_year is not empty "
                        f"({existing_rows} rows). Refusing to overwrite "
                        "a previously promoted certification artifact."
                    )

                insert_sql = """
                    INSERT INTO cms.medicare_core_county_year (
                        calendar_year,
                        county_fips,
                        county_id,
                        original_medicare_ffs_dollars,
                        partc_dollars,
                        partd_dollars,
                        core_medicare_dollars,
                        original_medicare_status,
                        partc_status,
                        partd_status,
                        core_value_status,
                        partc_months_represented,
                        partd_months_with_reconstructed_dollars,
                        partc_year_completeness,
                        partd_coverage_status,
                        time_window_status,
                        timing_basis,
                        original_medicare_geography_basis,
                        partc_geography_basis,
                        partd_geography_basis,
                        partd_payment_match_basis,
                        mssp_treatment,
                        rds_treatment,
                        washington_mffs_treatment,
                        ledger_authorization,
                        methodology_version,
                        source_file,
                        source_sha256
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                """

                cur.executemany(insert_sql, prepared_rows)

                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS rows,
                        COUNT(DISTINCT calendar_year) AS years,
                        COUNT(DISTINCT county_fips) AS counties
                    FROM cms.medicare_core_county_year
                    """
                )

                loaded_rows, loaded_years, loaded_counties = cur.fetchone()

                if loaded_rows != EXPECTED_ROWS:
                    raise RuntimeError(
                        f"Post-load row count is {loaded_rows}; "
                        f"expected {EXPECTED_ROWS}"
                    )

                if loaded_years != 10:
                    raise RuntimeError(
                        f"Post-load year count is {loaded_years}; "
                        "expected 10"
                    )

                if loaded_counties != EXPECTED_COUNTIES:
                    raise RuntimeError(
                        f"Post-load county count is {loaded_counties}; "
                        f"expected {EXPECTED_COUNTIES}"
                    )

        print("=" * 80)
        print("ETL-169 MEDICARE CORE ACCOUNTING LOAD")
        print("=" * 80)
        print(f"Source file     : {source_file}")
        print(f"Source SHA-256  : {source_sha256}")
        print(f"Rows loaded     : {EXPECTED_ROWS}")
        print("Years           : 2015-2024 (10)")
        print("Counties        : 39")
        print(f"Methodology     : {EXPECTED_METHODOLOGY}")
        print(
            "Ledger authority: "
            f"{EXPECTED_LEDGER_AUTHORIZATION}"
        )
        print()
        print("LOAD RESULT: PASS")

    finally:
        conn.close()


if __name__ == "__main__":
    main()