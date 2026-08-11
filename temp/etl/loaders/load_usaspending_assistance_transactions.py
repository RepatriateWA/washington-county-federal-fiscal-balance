"""
Load USAspending assistance transaction CSV members from ZIP archives.

Expected to run from the repository root:
    python -m etl.loaders.load_usaspending_assistance_transactions

The loader:
- Finds ZIPs recursively below data/raw/usaspending/assistance
- Identifies the 112-column assistance transaction CSV member
- Preserves archive/member provenance
- Prevents duplicate reloads using SHA-256 + member name
- Loads a curated set of source fields needed for COVID-001 and later analysis
- Performs no aggregation
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


ROOT = Path("data/raw/usaspending/assistance")
BATCH_SIZE = 5000

EXPECTED_MARKERS = {
    "assistance_transaction_unique_key",
    "assistance_award_unique_key",
    "federal_action_obligation",
    "action_date_fiscal_year",
    "recipient_state_code",
    "outlayed_amount_from_COVID-19_supplementals_for_overall_award",
    "obligated_amount_from_COVID-19_supplementals_for_overall_award",
}

SOURCE_TO_DB = {
    "assistance_transaction_unique_key": "assistance_transaction_unique_key",
    "assistance_award_unique_key": "assistance_award_unique_key",
    "award_id_fain": "award_id_fain",
    "modification_number": "modification_number",
    "award_id_uri": "award_id_uri",
    "federal_action_obligation": "federal_action_obligation",
    "total_obligated_amount": "total_obligated_amount",
    "total_outlayed_amount_for_overall_award": "total_outlayed_amount_for_overall_award",
    "generated_pragmatic_obligations": "generated_pragmatic_obligations",
    "disaster_emergency_fund_codes_for_overall_award": "disaster_emergency_fund_codes_for_overall_award",
    "outlayed_amount_from_COVID-19_supplementals_for_overall_award": "outlayed_amount_from_covid19_supplementals_for_overall_award",
    "obligated_amount_from_COVID-19_supplementals_for_overall_award": "obligated_amount_from_covid19_supplementals_for_overall_award",
    "action_date": "action_date",
    "action_date_fiscal_year": "action_date_fiscal_year",
    "awarding_agency_code": "awarding_agency_code",
    "awarding_agency_name": "awarding_agency_name",
    "awarding_sub_agency_code": "awarding_sub_agency_code",
    "awarding_sub_agency_name": "awarding_sub_agency_name",
    "funding_agency_code": "funding_agency_code",
    "funding_agency_name": "funding_agency_name",
    "recipient_uei": "recipient_uei",
    "recipient_duns": "recipient_duns",
    "recipient_name": "recipient_name",
    "recipient_name_raw": "recipient_name_raw",
    "recipient_city_name": "recipient_city_name",
    "prime_award_transaction_recipient_county_fips_code": "recipient_county_fips_code",
    "recipient_county_name": "recipient_county_name",
    "prime_award_transaction_recipient_state_fips_code": "recipient_state_fips_code",
    "recipient_state_code": "recipient_state_code",
    "recipient_state_name": "recipient_state_name",
    "recipient_zip_code": "recipient_zip_code",
    "primary_place_of_performance_country_code": "primary_place_of_performance_country_code",
    "primary_place_of_performance_country_name": "primary_place_of_performance_country_name",
    "primary_place_of_performance_city_name": "primary_place_of_performance_city_name",
    "prime_award_transaction_place_of_performance_county_fips_code": "place_of_performance_county_fips_code",
    "primary_place_of_performance_county_name": "primary_place_of_performance_county_name",
    "prime_award_transaction_place_of_performance_state_fips_code": "place_of_performance_state_fips_code",
    "primary_place_of_performance_state_name": "primary_place_of_performance_state_name",
    "primary_place_of_performance_zip_4": "primary_place_of_performance_zip_4",
    "cfda_number": "cfda_number",
    "cfda_title": "cfda_title",
    "assistance_type_code": "assistance_type_code",
    "assistance_type_description": "assistance_type_description",
    "transaction_description": "transaction_description",
    "prime_award_base_transaction_description": "prime_award_base_transaction_description",
    "action_type_code": "action_type_code",
    "action_type_description": "action_type_description",
    "correction_delete_indicator_code": "correction_delete_indicator_code",
    "correction_delete_indicator_description": "correction_delete_indicator_description",
    "record_type_code": "record_type_code",
    "record_type_description": "record_type_description",
    "usaspending_permalink": "usaspending_permalink",
    "initial_report_date": "initial_report_date",
    "last_modified_date": "last_modified_date",
}

NUMERIC_FIELDS = {
    "federal_action_obligation",
    "total_obligated_amount",
    "total_outlayed_amount_for_overall_award",
    "generated_pragmatic_obligations",
    "outlayed_amount_from_COVID-19_supplementals_for_overall_award",
    "obligated_amount_from_COVID-19_supplementals_for_overall_award",
}

INTEGER_FIELDS = {"action_date_fiscal_year"}
DATE_FIELDS = {"action_date", "initial_report_date"}
TIMESTAMP_FIELDS = {"last_modified_date"}


def get_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "wcffbp"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD"),
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_numeric(value):
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if value == "":
        return None
    return value


def parse_int(value):
    if value is None:
        return None
    value = value.strip()
    return int(value) if value else None


def parse_date(value):
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            pass
    return None


def parse_timestamp(value):
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            pass
    return None


def fiscal_year_from_path(path: Path):
    for part in reversed(path.parts):
        p = part.upper()
        if p.startswith("FY") and p[2:].isdigit():
            return int(p[2:])
    return None


def is_transaction_csv(header):
    return EXPECTED_MARKERS.issubset(set(header))


def convert_value(source_name, value):
    if source_name in NUMERIC_FIELDS:
        return parse_numeric(value)
    if source_name in INTEGER_FIELDS:
        return parse_int(value)
    if source_name in DATE_FIELDS:
        return parse_date(value)
    if source_name in TIMESTAMP_FIELDS:
        return parse_timestamp(value)
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


def create_load_record(cur, archive_rel, member_name, sha256, fy):
    cur.execute(
        """
        INSERT INTO usaspending.load_history
            (source_archive, source_member, source_sha256, fiscal_year, status)
        VALUES (%s, %s, %s, %s, 'started')
        ON CONFLICT (source_sha256, source_member) DO NOTHING
        RETURNING load_id
        """,
        (archive_rel, member_name, sha256, fy),
    )
    row = cur.fetchone()
    return row[0] if row else None


def mark_load_complete(cur, load_id, row_count):
    cur.execute(
        """
        UPDATE usaspending.load_history
        SET row_count_loaded=%s,
            completed_at=CURRENT_TIMESTAMP,
            status='completed'
        WHERE load_id=%s
        """,
        (row_count, load_id),
    )


def mark_load_failed(cur, load_id, error):
    cur.execute(
        """
        UPDATE usaspending.load_history
        SET completed_at=CURRENT_TIMESTAMP,
            status='failed',
            error_message=%s
        WHERE load_id=%s
        """,
        (str(error)[:4000], load_id),
    )


def main():
    if not ROOT.exists():
        print(f"ERROR: Missing root directory: {ROOT}")
        return 2

    archives = sorted(ROOT.rglob("*.zip"))
    if not archives:
        print(f"ERROR: No ZIP archives found below {ROOT}")
        return 3

    db_columns = list(SOURCE_TO_DB.values())
    insert_columns = [
        "load_id", "source_archive", "source_member", "source_row_number"
    ] + db_columns

    insert_sql = f"""
        INSERT INTO usaspending.assistance_transactions
        ({", ".join(insert_columns)})
        VALUES %s
    """

    conn = get_connection()
    conn.autocommit = False

    total_loaded = 0

    try:
        with conn.cursor() as cur:
            for archive_path in archives:
                archive_rel = str(archive_path.relative_to(ROOT))
                sha = sha256_file(archive_path)
                fy = fiscal_year_from_path(archive_path)

                print("=" * 72)
                print(archive_rel)

                with zipfile.ZipFile(archive_path, "r") as zf:
                    for info in zf.infolist():
                        if info.is_dir() or not info.filename.lower().endswith(".csv"):
                            continue

                        with zf.open(info, "r") as raw:
                            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                            reader = csv.DictReader(text)
                            header = reader.fieldnames or []

                            if not is_transaction_csv(header):
                                continue

                            print(f"  Loading: {info.filename}")

                            load_id = create_load_record(
                                cur, archive_rel, info.filename, sha, fy
                            )
                            if load_id is None:
                                print("    Already loaded; skipping.")
                                conn.rollback()
                                continue

                            conn.commit()

                            rows = []
                            row_count = 0

                            try:
                                for row_number, row in enumerate(reader, start=2):
                                    values = [
                                        convert_value(source, row.get(source))
                                        for source in SOURCE_TO_DB
                                    ]
                                    rows.append(
                                        (
                                            load_id,
                                            archive_rel,
                                            info.filename,
                                            row_number,
                                            *values,
                                        )
                                    )

                                    if len(rows) >= BATCH_SIZE:
                                        with conn.cursor() as batch_cur:
                                            execute_values(
                                                batch_cur,
                                                insert_sql,
                                                rows,
                                                page_size=BATCH_SIZE,
                                            )
                                        row_count += len(rows)
                                        total_loaded += len(rows)
                                        rows.clear()
                                        conn.commit()
                                        print(f"    {row_count:,} rows", end="\r")

                                if rows:
                                    with conn.cursor() as batch_cur:
                                        execute_values(
                                            batch_cur,
                                            insert_sql,
                                            rows,
                                            page_size=BATCH_SIZE,
                                        )
                                    row_count += len(rows)
                                    total_loaded += len(rows)
                                    conn.commit()

                                with conn.cursor() as done_cur:
                                    mark_load_complete(done_cur, load_id, row_count)
                                conn.commit()

                                print(f"    Loaded {row_count:,} rows.          ")

                            except Exception as exc:
                                conn.rollback()
                                with conn.cursor() as fail_cur:
                                    mark_load_failed(fail_cur, load_id, exc)
                                conn.commit()
                                raise

        print("=" * 72)
        print(f"Total new rows loaded: {total_loaded:,}")
        print("USAspending assistance transaction load complete.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
