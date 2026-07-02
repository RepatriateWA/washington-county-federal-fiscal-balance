from pathlib import Path

import pandas as pd

from etl.db import get_connection

TAX_YEAR = 2015
STATE_ID = 48
SOURCE_FILE = Path("data/raw/irs/15incywa.xls")


def to_int(value):
    if pd.isna(value):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def get_county_lookup(cur):
    cur.execute("""
        SELECT county_id, county_fips, full_fips
        FROM reference.county_registry
        WHERE state_id = %s;
    """, (STATE_ID,))

    return {
        county_fips: {
            "county_id": county_id,
            "full_fips": full_fips,
        }
        for county_id, county_fips, full_fips in cur.fetchall()
    }


def reset_irs_tables(cur):
    cur.execute("DELETE FROM irs.county_income_tax WHERE tax_year = %s;", (TAX_YEAR,))
    cur.execute("DELETE FROM irs.agi_bracket;")


def get_or_create_bracket(cur, bracket_ids, label):
    if label in bracket_ids:
        return bracket_ids[label]

    sort_order = len(bracket_ids)

    cur.execute("""
        INSERT INTO irs.agi_bracket
            (agi_bracket_code, agi_bracket_label, sort_order)
        VALUES
            (%s, %s, %s)
        RETURNING agi_bracket_id;
    """, (sort_order, label, sort_order))

    bracket_id = cur.fetchone()[0]
    bracket_ids[label] = bracket_id

    return bracket_id


def load_irs_soi_2015():
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"Missing source file: {SOURCE_FILE}")

    df = pd.read_excel(SOURCE_FILE, sheet_name=0, header=None, skiprows=6)

    conn = get_connection()
    cur = conn.cursor()

    county_lookup = get_county_lookup(cur)
    reset_irs_tables(cur)

    seen_fips = set()
    bracket_ids = {}
    rows_loaded = 0
    skipped_rows = 0

    for _, row in df.iterrows():
        raw_fips = row[0]

        if pd.isna(raw_fips):
            skipped_rows += 1
            continue

        try:
            county_fips = str(int(raw_fips)).zfill(3)
        except (ValueError, TypeError):
            skipped_rows += 1
            continue

        raw_label = row[1]

        if pd.isna(raw_label):
            skipped_rows += 1
            continue

        label = str(raw_label).strip()

        if not label:
            skipped_rows += 1
            continue

        if county_fips not in seen_fips:
            agi_label = "Total"
            seen_fips.add(county_fips)
        else:
            agi_label = label

        bracket_id = get_or_create_bracket(cur, bracket_ids, agi_label)

        if county_fips == "000":
            county_id = None
            full_fips = "53000"
        else:
            if county_fips not in county_lookup:
                skipped_rows += 1
                continue

            county_id = county_lookup[county_fips]["county_id"]
            full_fips = county_lookup[county_fips]["full_fips"]

        cur.execute("""
            INSERT INTO irs.county_income_tax (
                tax_year,
                county_id,
                state_id,
                county_fips,
                full_fips,
                agi_bracket_id,
                agi_bracket_label,
                number_of_returns,
                number_of_single_returns,
                number_of_joint_returns,
                number_of_head_of_household_returns,
                adjusted_gross_income,
                total_income_amount,
                salaries_and_wages_amount,
                taxable_interest_amount,
                ordinary_dividends_amount,
                qualified_dividends_amount,
                business_net_income_amount,
                net_capital_gain_amount,
                taxable_pensions_amount,
                taxable_social_security_amount
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            );
        """, (
            TAX_YEAR,
            county_id,
            STATE_ID,
            county_fips,
            full_fips,
            bracket_id,
            agi_label,
            to_int(row[2]),
            to_int(row[3]),
            to_int(row[4]),
            to_int(row[5]),
            to_int(row[16]),  # adjusted_gross_income
            to_int(row[18]),  # total_income_amount
            to_int(row[20]),  # salaries_and_wages_amount
            to_int(row[22]),  # taxable_interest_amount
            to_int(row[24]),  # ordinary_dividends_amount
            to_int(row[26]),  # qualified_dividends_amount
            to_int(row[30]),  # business_net_income_amount
            to_int(row[32]),  # net_capital_gain_amount
            to_int(row[36]),  # taxable_pensions_amount
            to_int(row[41]),  # taxable_social_security_amount
        ))

        rows_loaded += 1

    cur.execute("""
        INSERT INTO irs.import_log (tax_year, source_file, rows_loaded)
        VALUES (%s, %s, %s);
    """, (TAX_YEAR, str(SOURCE_FILE), rows_loaded))

    conn.commit()
    cur.close()
    conn.close()

    print(f"Loaded {rows_loaded} IRS SOI rows for {TAX_YEAR}.")
    print(f"Skipped {skipped_rows} non-data rows.")


if __name__ == "__main__":
    load_irs_soi_2015()