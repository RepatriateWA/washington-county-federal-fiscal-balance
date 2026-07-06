import argparse
from pathlib import Path

import pandas as pd

from etl.db import get_connection
from etl.logging_config import get_logger

logger = get_logger(__name__)

CATEGORIES = {
    "Total": 1,
    "Business income taxes": 2,
    "Individual income tax, employment taxes, and estate and trust income tax": 3,
    "Estate tax": 9,
    "Gift tax": 10,
    "Excise taxes": 11,
}


def to_int(value):
    if pd.isna(value):
        return None

    try:
        return int(round(float(value)))
    except (ValueError, TypeError):
        return None


def get_state_lookup(cur):
    cur.execute("""
        SELECT state_id, state_name
        FROM reference.state_registry;
    """)

    return {
        state_name.upper(): state_id
        for state_id, state_name in cur.fetchall()
    }


def load_irs_databook_table5(fiscal_year: int, workbook: Path):
    if not workbook.exists():
        raise FileNotFoundError(f"Missing workbook: {workbook}")

    df = pd.read_excel(workbook, sheet_name=0, header=None)
    df = df.iloc[5:].reset_index(drop=True)

    conn = get_connection()
    cur = conn.cursor()

    state_lookup = get_state_lookup(cur)

    cur.execute("""
        DELETE FROM irs.state_collections
        WHERE fiscal_year = %s
          AND source_file = %s;
    """, (fiscal_year, str(workbook)))

    rows_loaded = 0
    skipped_states = []

    for _, row in df.iterrows():
        state_name = str(row[0]).strip()

        if not state_name or state_name.lower() == "nan":
            continue

        if state_name == "United States, total":
            continue

        state_id = state_lookup.get(state_name.upper())

        if state_id is None:
            skipped_states.append(state_name)
            continue

        for tax_category, column_index in CATEGORIES.items():
            amount = to_int(row[column_index])

            if amount is None:
                continue

            cur.execute("""
                INSERT INTO irs.state_collections (
                    fiscal_year,
                    state_id,
                    state_name,
                    tax_category,
                    gross_collections_thousands,
                    source_file
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (fiscal_year, state_id, tax_category)
                DO UPDATE SET
                    gross_collections_thousands = EXCLUDED.gross_collections_thousands,
                    source_file = EXCLUDED.source_file;
            """, (
                fiscal_year,
                state_id,
                state_name,
                tax_category,
                amount,
                str(workbook),
            ))

            rows_loaded += 1

    conn.commit()
    cur.close()
    conn.close()

    logger.info(
        "Loaded %s IRS Data Book Table 5 rows for FY%s.",
        rows_loaded,
        fiscal_year,
    )

    if skipped_states:
        logger.warning("Skipped unmatched states/areas: %s", ", ".join(skipped_states))


def main():
    parser = argparse.ArgumentParser(
        description="Load IRS Data Book Table 5 gross collections by state."
    )
    parser.add_argument("fiscal_year", type=int)
    parser.add_argument("workbook", type=Path)

    args = parser.parse_args()
    load_irs_databook_table5(args.fiscal_year, args.workbook)


if __name__ == "__main__":
    main()