from __future__ import annotations

import csv
import hashlib
from decimal import Decimal, localcontext
from pathlib import Path

from etl.common.db import get_connection


SOURCE_FILE = Path(
    "data/raw/cms/medicare/validation/accounting_integration_v0_1/"
    "cms_medicare_core_annual_profile_v0_1.csv"
)

EXPECTED_YEARS = set(range(2015, 2025))
EXPECTED_METHODOLOGY = (
    "CMS-MEDICARE-ACCOUNTING-INTEGRATION-PROFILE-v0.1"
)
EXPECTED_LEDGER_STATUS = "NOT_YET_AUTHORIZED"

# Preserve source values at native precision, but treat sub-cent
# differences in independently recomputed derived totals as numerical
# serialization effects. A difference of $0.01 or greater fails.
CORE_ARITHMETIC_TOLERANCE = Decimal("0.01")


DECIMAL_FIELDS = {
    "original_medicare_actual_ffs_dollars":
        "original_medicare_actual_ffs_dollars",
    "partc_reconstructed_dollars":
        "partc_reconstructed_dollars",
    "partd_reconstructed_dollars":
        "partd_reconstructed_dollars",
    "core_medicare_sum_dollars":
        "core_medicare_sum_dollars",
    "partc_reconstruction_coverage_pct":
        "partc_reconstruction_coverage_pct",
    "partc_accounting_coverage_pct":
        "partc_accounting_coverage_pct",
}

INTEGER_FIELDS = {
    "original_medicare_county_rows":
        "original_medicare_county_rows",
    "original_medicare_beneficiaries":
        "original_medicare_beneficiaries",
    "partc_months_processed":
        "partc_months_processed",
}

TEXT_FIELDS = {
    "partc_year_completeness":
        "partc_year_completeness",
    "partd_dollar_source_field":
        "partd_dollar_source_field",
    "partd_coverage_status":
        "partd_coverage_status",
    "combined_period_status":
        "combined_period_status",
    "timing_basis_status":
        "timing_basis_status",
    "ledger_status":
        "ledger_status",
    "methodology_version":
        "methodology_version",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def status(value: bool) -> str:
    return "PASS" if value else "FAIL"


def main() -> None:
    with SOURCE_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        source_rows = list(csv.DictReader(handle))

    source_by_year = {
        int(row["year"]): row
        for row in source_rows
    }

    source_sha256 = sha256_file(SOURCE_FILE)

    failures: list[str] = []

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    m.calendar_year,
                    s.state_fips,
                    s.state_abbreviation,
                    m.original_medicare_actual_ffs_dollars,
                    m.partc_reconstructed_dollars,
                    m.partd_reconstructed_dollars,
                    m.core_medicare_sum_dollars,
                    m.original_medicare_county_rows,
                    m.original_medicare_beneficiaries,
                    m.partc_months_processed,
                    m.partc_year_completeness,
                    m.partc_reconstruction_coverage_pct,
                    m.partc_accounting_coverage_pct,
                    m.partd_dollar_source_field,
                    m.partd_coverage_status,
                    m.combined_period_status,
                    m.timing_basis_status,
                    m.ledger_status,
                    m.methodology_version,
                    m.source_file,
                    m.source_sha256
                FROM cms.medicare_core_state_year m
                JOIN reference.state_registry s
                  ON s.state_id = m.state_id
                ORDER BY m.calendar_year
                """
            )

            columns = [item.name for item in cur.description]

            db_rows = [
                dict(zip(columns, row))
                for row in cur.fetchall()
            ]

            print("=" * 100)
            print(
                "CMS MEDICARE CORE STATE ACCOUNTING "
                "VALIDATION — ETL-170"
            )
            print("=" * 100)
            print(
                "Purpose: verify exact promotion of the certified "
                "Washington state Medicare annual profile"
            )
            print("DB writes: NONE")
            print("CY-to-FFY conversion: NONE")
            print("Ledger authorization: NONE")
            print()

            row_ok = len(db_rows) == 10
            print(
                f"Database rows                         "
                f"{len(db_rows):>8}  {status(row_ok)}"
            )
            if not row_ok:
                failures.append("database row count")

            years = {row["calendar_year"] for row in db_rows}
            years_ok = years == EXPECTED_YEARS

            print(
                f"Year universe                         "
                f"{len(years):>8}  {status(years_ok)}"
            )
            if not years_ok:
                failures.append("year universe")

            state_ok = all(
                str(row["state_fips"]).strip() == "53"
                and row["state_abbreviation"] == "WA"
                for row in db_rows
            )

            print(
                f"Washington state linkage                       "
                f"{status(state_ok)}"
            )
            if not state_ok:
                failures.append("Washington state linkage")

            db_years = {row["calendar_year"] for row in db_rows}
            source_years = set(source_by_year)

            key_ok = db_years == source_years

            print(
                f"Source/database year universe                  "
                f"{status(key_ok)}"
            )
            if not key_ok:
                failures.append("source/database year universe")

            hashes = {row["source_sha256"] for row in db_rows}
            hash_ok = hashes == {source_sha256}

            print(
                f"Source SHA-256 preserved                       "
                f"{status(hash_ok)}"
            )
            if not hash_ok:
                failures.append("source SHA-256")

            mismatches = 0

            for db_row in db_rows:
                year = db_row["calendar_year"]
                source = source_by_year[year]

                for db_field, source_field in DECIMAL_FIELDS.items():
                    expected = Decimal(source[source_field].strip())
                    actual = db_row[db_field]

                    if actual != expected:
                        mismatches += 1
                        failures.append(
                            f"{year} {db_field}: "
                            f"db={actual!r} source={expected!r}"
                        )

                for db_field, source_field in INTEGER_FIELDS.items():
                    expected = int(source[source_field].strip())
                    actual = db_row[db_field]

                    if actual != expected:
                        mismatches += 1
                        failures.append(
                            f"{year} {db_field}: "
                            f"db={actual!r} source={expected!r}"
                        )

                for db_field, source_field in TEXT_FIELDS.items():
                    expected = source[source_field].strip()
                    actual = db_row[db_field]

                    if actual != expected:
                        mismatches += 1
                        failures.append(
                            f"{year} {db_field}: "
                            f"db={actual!r} source={expected!r}"
                        )

            exact_ok = mismatches == 0

            print(
                f"Field-level source reproduction       "
                f"{mismatches:>8}  {status(exact_ok)}"
            )
            if not exact_ok:
                failures.append("field-level source reproduction")

            arithmetic_failures = 0
            max_arithmetic_difference = Decimal("0")
            max_arithmetic_difference_year = None

            for row in db_rows:
                with localcontext() as ctx:
                    ctx.prec = 80
                    calculated = (
                        row["original_medicare_actual_ffs_dollars"]
                        + row["partc_reconstructed_dollars"]
                        + row["partd_reconstructed_dollars"]
                    )
                    difference = abs(
                        row["core_medicare_sum_dollars"] - calculated
                    )

                if difference > max_arithmetic_difference:
                    max_arithmetic_difference = difference
                    max_arithmetic_difference_year = row["calendar_year"]

                if difference >= CORE_ARITHMETIC_TOLERANCE:
                    arithmetic_failures += 1
                    failures.append(
                        f"{row['calendar_year']} core arithmetic: "
                        f"db={row['core_medicare_sum_dollars']!r} "
                        f"calculated={calculated!r} "
                        f"difference={difference!r} "
                        f"tolerance={CORE_ARITHMETIC_TOLERANCE!r}"
                    )

            arithmetic_ok = arithmetic_failures == 0

            print(
                f"Core arithmetic tolerance             "
                f"${CORE_ARITHMETIC_TOLERANCE}"
            )

            print(
                f"Maximum arithmetic difference         "
                f"{str(max_arithmetic_difference):>8}"
            )

            if max_arithmetic_difference_year is not None:
                print(
                    f"Maximum-difference year               "
                    f"{max_arithmetic_difference_year:>8}"
                )

            print(
                f"Core arithmetic violations            "
                f"{arithmetic_failures:>8}  "
                f"{status(arithmetic_ok)}"
            )

            cur.execute(
                """
                SELECT COUNT(*)
                FROM cms.medicare_core_state_year
                WHERE original_medicare_county_rows <> 39
                """
            )
            bad_county_rows = cur.fetchone()[0]

            print(
                f"Original Medicare county-row violations"
                f"{bad_county_rows:>7}  "
                f"{status(bad_county_rows == 0)}"
            )

            if bad_county_rows:
                failures.append("Original Medicare county rows")

            cur.execute(
                """
                SELECT COUNT(*)
                FROM cms.medicare_core_state_year
                WHERE ledger_status <> %s
                """,
                (EXPECTED_LEDGER_STATUS,),
            )
            bad_ledger = cur.fetchone()[0]

            print(
                f"Ledger-status violations              "
                f"{bad_ledger:>8}  "
                f"{status(bad_ledger == 0)}"
            )

            if bad_ledger:
                failures.append("ledger status")

            cur.execute(
                """
                SELECT COUNT(*)
                FROM cms.medicare_core_state_year
                WHERE methodology_version <> %s
                """,
                (EXPECTED_METHODOLOGY,),
            )
            bad_method = cur.fetchone()[0]

            print(
                f"Methodology-version violations         "
                f"{bad_method:>8}  "
                f"{status(bad_method == 0)}"
            )

            if bad_method:
                failures.append("methodology version")

            print()
            print("ANNUAL STATE MEDICARE PROFILE")
            print("-" * 100)
            print(
                "YEAR        ORIGINAL              PART C"
                "              PART D                CORE"
            )

            for row in db_rows:
                print(
                    f"{row['calendar_year']}  "
                    f"{row['original_medicare_actual_ffs_dollars']:>18,.2f}  "
                    f"{row['partc_reconstructed_dollars']:>18,.2f}  "
                    f"{row['partd_reconstructed_dollars']:>18,.2f}  "
                    f"{row['core_medicare_sum_dollars']:>18,.2f}"
                )

            row_2024 = next(
                row
                for row in db_rows
                if row["calendar_year"] == 2024
            )

            partial_2024_ok = (
                row_2024["partc_months_processed"] == 9
                and row_2024["partc_year_completeness"]
                == "PARTIAL_JAN_SEP"
                and row_2024["combined_period_status"]
                == "MIXED_2024_PARTIAL_PARTC_PARTD"
            )

            print()
            print(
                "2024 partial-period status                       "
                f"{status(partial_2024_ok)}"
            )

            if not partial_2024_ok:
                failures.append("2024 partial-period status")

            print()
            print("=" * 100)

            if failures:
                print("ETL-170 VALIDATION RESULT: FAIL")
                print("=" * 100)

                for failure in failures[:25]:
                    print(f"  - {failure}")

                if len(failures) > 25:
                    print(
                        f"  ... plus {len(failures) - 25} "
                        "additional failure(s)"
                    )

                raise SystemExit(1)

            print("ETL-170 VALIDATION RESULT: PASS")
            print(
                "STATE MEDICARE PROFILE PROMOTION: "
                "EXACT / NO ANALYTICAL TRANSFORMATION"
            )
            print(
                "CALENDAR-YEAR LABELS: PRESERVED / "
                "FFY CONVERSION NOT AUTHORIZED"
            )
            print(
                "FINAL FEDERAL-INFLOW LEDGER AUTHORIZATION: "
                "NOT GRANTED BY ETL-170"
            )
            print("=" * 100)

    finally:
        conn.close()


if __name__ == "__main__":
    main()