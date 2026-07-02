import argparse
from pathlib import Path

import pandas as pd

from etl.db import get_connection

STATE_ID = 48


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


def reset_irs_year(cur, tax_year):
    cur.execute(
        "DELETE FROM irs.county_income_tax WHERE tax_year = %s;",
        (tax_year,),
    )


def get_or_create_bracket(cur, bracket_ids, label):
    if label in bracket_ids:
        return bracket_ids[label]

    sort_order = len(bracket_ids)

    cur.execute("""
        INSERT INTO irs.agi_bracket
            (agi_bracket_code, agi_bracket_label, sort_order)
        VALUES
            (%s, %s, %s)
        ON CONFLICT (agi_bracket_code)
        DO UPDATE SET agi_bracket_label = EXCLUDED.agi_bracket_label
        RETURNING agi_bracket_id;
    """, (sort_order, label, sort_order))

    bracket_id = cur.fetchone()[0]
    bracket_ids[label] = bracket_id

    return bracket_id


def load_irs_soi(tax_year: int, source_file: Path):
    if not source_file.exists():
        raise FileNotFoundError(f"Missing source file: {source_file}")

    df = pd.read_excel(source_file, sheet_name=0, header=None, skiprows=6)

    conn = get_connection()
    cur = conn.cursor()

    county_lookup = get_county_lookup(cur)
    reset_irs_year(cur, tax_year)

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
            tax_year,
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
            to_int(row[16]),
            to_int(row[18]),
            to_int(row[20]),
            to_int(row[22]),
            to_int(row[24]),
            to_int(row[26]),
            to_int(row[30]),
            to_int(row[32]),
            to_int(row[36]),
            to_int(row[41]),
        ))

        rows_loaded += 1

    cur.execute("""
        INSERT INTO irs.import_log (tax_year, source_file, rows_loaded)
        VALUES (%s, %s, %s);
    """, (tax_year, str(source_file), rows_loaded))

    conn.commit()
    cur.close()
    conn.close()

    print(f"Loaded {rows_loaded} IRS SOI rows for {tax_year}.")
    print(f"Skipped {skipped_rows} non-data rows.")


def main():
    parser = argparse.ArgumentParser(description="Load IRS SOI county data.")
    parser.add_argument("tax_year", type=int)
    parser.add_argument("source_file", type=Path)

    args = parser.parse_args()

    load_irs_soi(args.tax_year, args.source_file)


if __name__ == "__main__":
    main()