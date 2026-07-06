import argparse
from pathlib import Path

import pandas as pd

from etl.db import get_connection
from etl.logging_config import get_logger
from etl.pdf.databook import extract_table5_dataframe

logger = get_logger(__name__)


CATEGORY_COLUMNS = {
    "Total": "total_collections",
    "Business income taxes": "business_income_taxes",
    "Individual income tax, employment taxes, and estate and trust income tax": "individual_employment_estate_trust",
    "Estate tax": "estate_tax",
    "Gift tax": "gift_tax",
    "Excise taxes": "excise_taxes",
}


def get_state_lookup(cur):
    cur.execute("""
        SELECT state_id, state_name
        FROM reference.state_registry;
    """)

    return {
        state_name.upper(): state_id
        for state_id, state_name in cur.fetchall()
    }


def load_excel_dataframe(source_file: Path) -> pd.DataFrame:
    df = pd.read_excel(source_file, sheet_name=0, header=None)
    df = df.iloc[5:].reset_index(drop=True)

    rows = []

    for _, row in df.iterrows():
        state_name = str(row[0]).strip()

        if not state_name or state_name.lower() == "nan":
            continue

        rows.append({
            "state_name": state_name,
            "total_collections": row[1],
            "business_income_taxes": row[2],
            "individual_employment_estate_trust": row[3],
            "estate_tax": row[9],
            "gift_tax": row[10],
            "excise_taxes": row[11],
        })

    return pd.DataFrame(rows)


def to_int(value):
    if pd.isna(value):
        return None

    try:
        return int(round(float(value)))
    except (ValueError, TypeError):
        return None


def dataframe_from_source(source_file: Path) -> pd.DataFrame:
    suffix = source_file.suffix.lower()

    if suffix == ".pdf":
        return extract_table5_dataframe(source_file)

    if suffix in {".xlsx", ".xls"}:
        return load_excel_dataframe(source_file)

    raise ValueError(f"Unsupported IRS Data Book Table 5 source: {source_file}")


def load_irs_databook_table5(fiscal_year: int, source_file: Path):
    if not source_file.exists():
        raise FileNotFoundError(f"Missing source file: {source_file}")

    df = dataframe_from_source(source_file)

    conn = get_connection()
    cur = conn.cursor()

    state_lookup = get_state_lookup(cur)

    cur.execute("""
        DELETE FROM irs.state_collections
        WHERE fiscal_year = %s;
    """, (fiscal_year,))

    rows_loaded = 0
    skipped_states = []

    for _, row in df.iterrows():
        state_name = str(row["state_name"]).strip()

        if state_name == "United States, total":
            continue

        state_id = state_lookup.get(state_name.upper())

        if state_id is None:
            skipped_states.append(state_name)
            continue

        for tax_category, column_name in CATEGORY_COLUMNS.items():
            amount = to_int(row[column_name])

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
                str(source_file),
            ))

            rows_loaded += 1

    conn.commit()
    cur.close()
    conn.close()

    logger.info(
        "Loaded %s IRS Data Book Table 5 rows for FY%s from %s.",
        rows_loaded,
        fiscal_year,
        source_file,
    )

    if skipped_states:
        logger.warning("Skipped unmatched states/areas: %s", ", ".join(skipped_states))


def main():
    parser = argparse.ArgumentParser(
        description="Load IRS Data Book Table 5 gross collections by state."
    )
    parser.add_argument("fiscal_year", type=int)
    parser.add_argument("source_file", type=Path)

    args = parser.parse_args()
    load_irs_databook_table5(args.fiscal_year, args.source_file)


if __name__ == "__main__":
    main()