import argparse
from pathlib import Path

import pandas as pd

from etl.db import get_connection
from etl.logging_config import get_logger


logger = get_logger(__name__)


COUNT_SHEET = "Table4_County_Beneficiaries"
AMOUNT_SHEET = "Table5_County_Benefits"

STATE_ABBREVIATION = "WA"

BENEFIT_COLUMNS = {
    "TOTAL": 3,
    "RETIRED_WORKERS": 4,
    "RETIRED_SPOUSES": 5,
    "RETIRED_CHILDREN": 6,
    "SURVIVOR_WIDOWERS_PARENTS": 7,
    "SURVIVOR_CHILDREN": 8,
    "DISABLED_WORKERS": 9,
    "DISABLED_SPOUSES": 10,
    "DISABLED_CHILDREN": 11,
}


def to_int(value):
    """Convert an SSA spreadsheet value to an integer."""
    if pd.isna(value):
        return None

    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def normalize_fips(value):
    """Return a five-character county FIPS code."""
    numeric_value = to_int(value)

    if numeric_value is None:
        return None

    return str(numeric_value).zfill(5)


def get_state(cur):
    cur.execute(
        """
        SELECT state_id, state_name
        FROM reference.state_registry
        WHERE state_abbreviation = %s;
        """,
        (STATE_ABBREVIATION,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            f"State {STATE_ABBREVIATION} was not found in reference.state_registry."
        )

    return row


def get_county_lookup(cur, state_id):
    cur.execute(
        """
        SELECT
            county_id,
            full_fips,
            county_name
        FROM reference.county_registry
        WHERE state_id = %s;
        """,
        (state_id,),
    )

    return {
        str(full_fips).zfill(5): {
            "county_id": county_id,
            "county_name": county_name,
        }
        for county_id, full_fips, county_name in cur.fetchall()
    }


def get_benefit_type_lookup(cur):
    cur.execute(
        """
        SELECT
            ssa_benefit_type_id,
            benefit_type_code,
            benefit_type_name
        FROM reference.ssa_benefit_type;
        """
    )

    return {
        benefit_type_code: {
            "ssa_benefit_type_id": benefit_type_id,
            "benefit_type_name": benefit_type_name,
        }
        for benefit_type_id, benefit_type_code, benefit_type_name in cur.fetchall()
    }


def read_county_sheet(source_file, sheet_name):
    df = pd.read_excel(
        source_file,
        sheet_name=sheet_name,
        header=None,
    )

    # Rows 0–3 contain titles and headers.
    return df.iloc[4:].reset_index(drop=True)


def build_count_lookup(count_df):
    count_lookup = {}

    for _, row in count_df.iterrows():
        full_fips = normalize_fips(row[2])

        if full_fips is None:
            continue

        # Exclude the Washington statewide total row, which has ANSI code 53.
        if full_fips == "00053":
            continue

        county_name = str(row[0]).strip()

        if not county_name or county_name.lower() == "nan":
            continue

        count_lookup[full_fips] = {
            "county_name": county_name,
            "values": {
                benefit_code: to_int(row[column_index])
                for benefit_code, column_index in BENEFIT_COLUMNS.items()
            },
        }

    return count_lookup


def build_amount_lookup(amount_df):
    amount_lookup = {}

    for _, row in amount_df.iterrows():
        full_fips = normalize_fips(row[2])

        if full_fips is None:
            continue

        # Exclude the Washington statewide total row.
        if full_fips == "00053":
            continue

        county_name = str(row[0]).strip()

        if not county_name or county_name.lower() == "nan":
            continue

        amount_lookup[full_fips] = {
            "county_name": county_name,
            "values": {
                benefit_code: to_int(row[column_index])
                for benefit_code, column_index in BENEFIT_COLUMNS.items()
            },
        }

    return amount_lookup


def load_ssa_oasdi_county(report_year, source_file):
    if not source_file.exists():
        raise FileNotFoundError(f"Missing SSA source file: {source_file}")

    count_df = read_county_sheet(source_file, COUNT_SHEET)
    amount_df = read_county_sheet(source_file, AMOUNT_SHEET)

    count_lookup = build_count_lookup(count_df)
    amount_lookup = build_amount_lookup(amount_df)

    count_fips = set(count_lookup)
    amount_fips = set(amount_lookup)

    if count_fips != amount_fips:
        missing_from_counts = sorted(amount_fips - count_fips)
        missing_from_amounts = sorted(count_fips - amount_fips)

        raise ValueError(
            "SSA county sheets do not contain matching county FIPS codes. "
            f"Missing from counts: {missing_from_counts}; "
            f"missing from amounts: {missing_from_amounts}"
        )

    conn = get_connection()
    cur = conn.cursor()

    try:
        state_id, state_name = get_state(cur)
        county_lookup = get_county_lookup(cur, state_id)
        benefit_type_lookup = get_benefit_type_lookup(cur)

        missing_benefit_types = (
            set(BENEFIT_COLUMNS) - set(benefit_type_lookup)
        )

        if missing_benefit_types:
            raise ValueError(
                "Missing SSA benefit type reference rows: "
                + ", ".join(sorted(missing_benefit_types))
            )

        cur.execute(
            """
            DELETE FROM ssa.benefit_payments
            WHERE report_year = %s
              AND agency_code = 'SSA';
            """,
            (report_year,),
        )

        rows_loaded = 0
        counties_loaded = 0
        unmatched_counties = []

        for full_fips in sorted(count_fips):
            source_county = count_lookup[full_fips]
            source_amount = amount_lookup[full_fips]

            county_reference = county_lookup.get(full_fips)

            if county_reference is None:
                unmatched_counties.append(
                    f"{source_county['county_name']} ({full_fips})"
                )
                continue

            county_id = county_reference["county_id"]
            county_name = county_reference["county_name"]

            for benefit_code in BENEFIT_COLUMNS:
                benefit_reference = benefit_type_lookup[benefit_code]

                beneficiary_count = source_county["values"][benefit_code]
                monthly_benefits_thousands = source_amount["values"][
                    benefit_code
                ]

                annual_benefits_thousands = None

                if monthly_benefits_thousands is not None:
                    annual_benefits_thousands = (
                        monthly_benefits_thousands * 12
                    )

                cur.execute(
                    """
                    INSERT INTO ssa.benefit_payments (
                        report_year,
                        state_id,
                        county_id,
                        state_name,
                        county_name,
                        agency_code,
                        benefit_type,
                        ssa_benefit_type_id,
                        beneficiary_count,
                        monthly_benefits_thousands,
                        annual_benefits_thousands,
                        source_file,
                        source_table
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, 'SSA',
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (
                        report_year,
                        state_id,
                        county_id,
                        benefit_type
                    )
                    DO UPDATE SET
                        ssa_benefit_type_id =
                            EXCLUDED.ssa_benefit_type_id,
                        beneficiary_count =
                            EXCLUDED.beneficiary_count,
                        monthly_benefits_thousands =
                            EXCLUDED.monthly_benefits_thousands,
                        annual_benefits_thousands =
                            EXCLUDED.annual_benefits_thousands,
                        source_file =
                            EXCLUDED.source_file,
                        source_table =
                            EXCLUDED.source_table;
                    """,
                    (
                        report_year,
                        state_id,
                        county_id,
                        state_name,
                        county_name,
                        benefit_reference["benefit_type_name"],
                        benefit_reference["ssa_benefit_type_id"],
                        beneficiary_count,
                        monthly_benefits_thousands,
                        annual_benefits_thousands,
                        str(source_file),
                        f"{COUNT_SHEET}; {AMOUNT_SHEET}",
                    ),
                )

                rows_loaded += 1

            counties_loaded += 1

        if unmatched_counties:
            raise ValueError(
                "Could not resolve SSA counties against "
                "reference.county_registry: "
                + ", ".join(unmatched_counties)
            )

        if counties_loaded != 39:
            raise ValueError(
                f"Expected 39 Washington counties, loaded {counties_loaded}."
            )

        expected_rows = 39 * len(BENEFIT_COLUMNS)

        if rows_loaded != expected_rows:
            raise ValueError(
                f"Expected {expected_rows} SSA benefit rows, "
                f"loaded {rows_loaded}."
            )

        conn.commit()

        logger.info(
            "Loaded %s SSA benefit payment rows for %s "
            "across %s Washington counties.",
            rows_loaded,
            report_year,
            counties_loaded,
        )

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Load SSA OASDI county beneficiary counts and "
            "December monthly benefit amounts."
        )
    )

    parser.add_argument(
        "report_year",
        type=int,
        help="SSA publication/report year, such as 2024.",
    )

    parser.add_argument(
        "source_file",
        type=Path,
        help="Washington SSA OASDI workbook.",
    )

    args = parser.parse_args()

    load_ssa_oasdi_county(
        report_year=args.report_year,
        source_file=args.source_file,
    )


if __name__ == "__main__":
    main()