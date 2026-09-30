from __future__ import annotations

import csv
import hashlib
from decimal import Decimal
from pathlib import Path

from etl.db import get_connection


SOURCE_FILE = Path(
    "data/raw/cms/medicare/validation/county_integration_v0_1/"
    "cms_medicare_county_integration_v0_1.csv"
)

EXPECTED_ROWS = 390
EXPECTED_YEARS = 10
EXPECTED_COUNTIES = 39
EXPECTED_METHODOLOGY = "CMS-MEDICARE-COUNTY-INTEGRATION-v0.1"
EXPECTED_AUTHORIZATION = "NOT_AUTHORIZED_BY_THIS_CERTIFICATION"


NUMERIC_FIELDS = (
    "original_medicare_ffs_dollars",
    "partc_dollars",
    "partd_dollars",
    "core_medicare_dollars",
)

INTEGER_FIELDS = (
    "partc_months_represented",
    "partd_months_with_reconstructed_dollars",
)

TEXT_FIELDS = (
    "original_medicare_status",
    "partc_status",
    "partd_status",
    "core_value_status",
    "partd_coverage_status",
    "time_window_status",
    "timing_basis",
    "original_medicare_geography_basis",
    "partd_geography_basis",
    "partd_payment_match_basis",
    "mssp_treatment",
    "rds_treatment",
    "washington_mffs_treatment",
    "ledger_authorization",
    "methodology_version",
)

NULLABLE_TEXT_FIELDS = (
    "partc_year_completeness",
    "partc_geography_basis",
)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def csv_decimal(value: str) -> Decimal | None:
    text = value.strip()
    return None if text == "" else Decimal(text)


def csv_integer(value: str) -> int | None:
    text = value.strip()
    return None if text == "" else int(text)

def csv_nullable_text(value: str | None) -> str | None:
    if value is None:
        return None

    text = value.strip()

    if text == "":
        return None

    return text

def pass_fail(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


def main() -> None:
    source_sha256 = sha256_file(SOURCE_FILE)

    with SOURCE_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        source_rows = list(csv.DictReader(handle))

    source_by_key = {
        (int(row["calendar_year"]), row["county_fips"].strip()): row
        for row in source_rows
    }

    conn = get_connection()

    failures: list[str] = []

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
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
                FROM cms.medicare_core_county_year
                ORDER BY calendar_year, county_fips
                """
            )

            db_rows = cur.fetchall()
            columns = [item.name for item in cur.description]

            db_records = [
                dict(zip(columns, row))
                for row in db_rows
            ]

            print("=" * 100)
            print("CMS MEDICARE CORE ACCOUNTING VALIDATION — ETL-169")
            print("=" * 100)
            print(
                "Purpose: verify exact promotion of "
                "CMS-MEDICARE-COUNTY-INTEGRATION-v0.1"
            )
            print("DB writes: NONE")
            print("Ledger authorization: NONE")
            print()

            row_count_ok = len(db_records) == EXPECTED_ROWS
            print(
                f"Database rows                       "
                f"{len(db_records):>8}  "
                f"{pass_fail(row_count_ok)}"
            )
            if not row_count_ok:
                failures.append("database row count")

            years = {row["calendar_year"] for row in db_records}
            years_ok = (
                len(years) == EXPECTED_YEARS
                and years == set(range(2015, 2025))
            )
            print(
                f"Distinct years                      "
                f"{len(years):>8}  "
                f"{pass_fail(years_ok)}"
            )
            if not years_ok:
                failures.append("year universe")

            counties = {row["county_fips"] for row in db_records}
            counties_ok = len(counties) == EXPECTED_COUNTIES
            print(
                f"Distinct counties                   "
                f"{len(counties):>8}  "
                f"{pass_fail(counties_ok)}"
            )
            if not counties_ok:
                failures.append("county universe")

            db_keys = {
                (row["calendar_year"], row["county_fips"])
                for row in db_records
            }

            source_keys = set(source_by_key)

            key_match = db_keys == source_keys
            print(
                f"Source/database key universe                 "
                f"{pass_fail(key_match)}"
            )
            if not key_match:
                failures.append("source/database key universe")

            cur.execute(
                """
                SELECT COUNT(*)
                FROM cms.medicare_core_county_year m
                JOIN reference.county_registry c
                  ON c.county_id = m.county_id
                 AND c.full_fips = m.county_fips
                """
            )
            linked_rows = cur.fetchone()[0]

            geography_ok = linked_rows == EXPECTED_ROWS
            print(
                f"Canonical county linkage             "
                f"{linked_rows:>8}  "
                f"{pass_fail(geography_ok)}"
            )
            if not geography_ok:
                failures.append("canonical county linkage")

            cur.execute(
                """
                SELECT COUNT(DISTINCT source_sha256)
                FROM cms.medicare_core_county_year
                """
            )
            distinct_hashes = cur.fetchone()[0]

            cur.execute(
                """
                SELECT MIN(source_sha256)
                FROM cms.medicare_core_county_year
                """
            )
            stored_hash = cur.fetchone()[0]

            hash_ok = (
                distinct_hashes == 1
                and stored_hash == source_sha256
            )

            print(
                f"Source SHA-256 preserved                      "
                f"{pass_fail(hash_ok)}"
            )
            if not hash_ok:
                failures.append("source SHA-256")

            field_mismatches = 0

            for db_row in db_records:
                key = (
                    db_row["calendar_year"],
                    db_row["county_fips"],
                )

                source = source_by_key.get(key)

                if source is None:
                    field_mismatches += 1
                    failures.append(f"missing source key {key}")
                    continue

                for field in NUMERIC_FIELDS:
                    expected = csv_decimal(source[field])
                    actual = db_row[field]

                    if actual != expected:
                        field_mismatches += 1
                        failures.append(
                            f"{key} {field}: "
                            f"db={actual!r} source={expected!r}"
                        )

                for field in INTEGER_FIELDS:
                    expected = csv_integer(source[field])
                    actual = db_row[field]

                    if actual != expected:
                        field_mismatches += 1
                        failures.append(
                            f"{key} {field}: "
                            f"db={actual!r} source={expected!r}"
                        )

                for field in TEXT_FIELDS:
                    expected = source[field].strip()
                    actual = db_row[field]

                    if actual != expected:
                        field_mismatches += 1
                        failures.append(
                            f"{key} {field}: "
                            f"db={actual!r} source={expected!r}"
                        )

                for field in NULLABLE_TEXT_FIELDS:
                    expected = csv_nullable_text(source[field])
                    actual = db_row[field]

                    if actual != expected:
                        field_mismatches += 1
                        failures.append(
                            f"{key} {field}: "
                            f"db={actual!r} source={expected!r}"
                        )        

            exact_copy_ok = field_mismatches == 0

            print(
                f"Field-level source reproduction      "
                f"{field_mismatches:>8}  "
                f"{pass_fail(exact_copy_ok)}"
            )

            if not exact_copy_ok:
                failures.append("field-level source reproduction")

            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE partc_dollars IS NULL
                    ),
                    COUNT(*) FILTER (
                        WHERE core_medicare_dollars IS NULL
                    )
                FROM cms.medicare_core_county_year
                """
            )

            null_partc, null_core = cur.fetchone()

            null_preservation_ok = (
                null_partc == 14
                and null_core == 14
            )

            print(
                f"Part C NULL county-years             "
                f"{null_partc:>8}  "
                f"{pass_fail(null_partc == 14)}"
            )
            print(
                f"Core NULL county-years               "
                f"{null_core:>8}  "
                f"{pass_fail(null_core == 14)}"
            )

            if not null_preservation_ok:
                failures.append("Part C/core NULL preservation")

            cur.execute(
                """
                SELECT COUNT(*)
                FROM cms.medicare_core_county_year
                WHERE partc_dollars = 0
                  AND (
                        partc_status <> 'RECONSTRUCTED'
                     OR partc_year_completeness <> 'COMPLETE'
                  )
                """
            )

            suspicious_zero_rows = cur.fetchone()[0]
            zero_ok = suspicious_zero_rows == 0

            print(
                f"Suspicious Part C zero rows          "
                f"{suspicious_zero_rows:>8}  "
                f"{pass_fail(zero_ok)}"
            )

            if not zero_ok:
                failures.append("Part C zero/imputation invariant")

            cur.execute(
                """
                SELECT COUNT(*)
                FROM cms.medicare_core_county_year
                WHERE methodology_version <> %s
                """,
                (EXPECTED_METHODOLOGY,),
            )

            bad_methodology = cur.fetchone()[0]

            methodology_ok = bad_methodology == 0
            print(
                f"Methodology-version violations       "
                f"{bad_methodology:>8}  "
                f"{pass_fail(methodology_ok)}"
            )

            if not methodology_ok:
                failures.append("methodology version")

            cur.execute(
                """
                SELECT COUNT(*)
                FROM cms.medicare_core_county_year
                WHERE ledger_authorization <> %s
                """,
                (EXPECTED_AUTHORIZATION,),
            )

            bad_authorization = cur.fetchone()[0]

            authorization_ok = bad_authorization == 0
            print(
                f"Authorization-status violations      "
                f"{bad_authorization:>8}  "
                f"{pass_fail(authorization_ok)}"
            )

            if not authorization_ok:
                failures.append("ledger authorization preservation")

            cur.execute(
                """
                SELECT
                    calendar_year,
                    COUNT(*) AS county_rows,
                    COUNT(*) FILTER (
                        WHERE partc_dollars IS NOT NULL
                    ) AS partc_available,
                    COUNT(*) FILTER (
                        WHERE core_medicare_dollars IS NOT NULL
                    ) AS complete_core,
                    SUM(original_medicare_ffs_dollars)
                        AS original_medicare_sum,
                    SUM(partc_dollars)
                        AS available_partc_sum,
                    SUM(partd_dollars)
                        AS partd_sum,
                    SUM(core_medicare_dollars)
                        AS available_core_sum
                FROM cms.medicare_core_county_year
                GROUP BY calendar_year
                ORDER BY calendar_year
                """
            )

            annual_rows = cur.fetchall()

            print()
            print("ANNUAL DATABASE PROFILE")
            print("-" * 100)
            print(
                "YEAR  COUNTIES  PARTC-AVAILABLE  COMPLETE-CORE  "
                "ORIGINAL-MEDICARE"
            )

            for (
                year,
                county_rows,
                partc_available,
                complete_core,
                original_sum,
                _partc_sum,
                _partd_sum,
                _core_sum,
            ) in annual_rows:
                print(
                    f"{year}  "
                    f"{county_rows:>8}  "
                    f"{partc_available:>15}  "
                    f"{complete_core:>13}  "
                    f"{original_sum:>18,.2f}"
                )

            print()
            print("=" * 100)

            if failures:
                print("ETL-169 VALIDATION RESULT: FAIL")
                print("=" * 100)
                print()
                print("FAILURES")

                # Keep console output bounded.
                for failure in failures[:25]:
                    print(f"  - {failure}")

                if len(failures) > 25:
                    print(
                        f"  ... plus {len(failures) - 25} "
                        "additional failure(s)"
                    )

                raise SystemExit(1)

            print("ETL-169 VALIDATION RESULT: PASS")
            print(
                "CERTIFIED ARTIFACT PROMOTION: EXACT / "
                "NO ANALYTICAL TRANSFORMATION"
            )
            print(
                "FINAL FEDERAL-INFLOW LEDGER AUTHORIZATION: "
                "NOT GRANTED BY ETL-169"
            )
            print("=" * 100)

    finally:
        conn.close()


if __name__ == "__main__":
    main()