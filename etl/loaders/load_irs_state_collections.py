import argparse
from pathlib import Path

import pandas as pd

from etl.db import get_connection
from etl.logging_config import get_logger

logger = get_logger(__name__)

STATE_ID = 48
STATE_NAME = "Washington"


def to_int(value):
    if pd.isna(value):
        return None

    if isinstance(value, str):
        value = value.strip()
        if value.lower() in {"d", "n/a", "nan", ""}:
            return None

    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def load_irs_state_collections(fiscal_year: int, source_file: Path):
    if not source_file.exists():
        raise FileNotFoundError(f"Missing source file: {source_file}")

    df = pd.read_excel(source_file, sheet_name=0, header=None)

    data_rows = df.iloc[3:11].copy()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM irs.state_collections
        WHERE fiscal_year = %s
          AND state_id = %s;
        """,
        (fiscal_year, STATE_ID),
    )

    rows_loaded = 0

    for _, row in data_rows.iterrows():
        tax_category = str(row[0]).strip()

        if not tax_category or tax_category.lower() == "nan":
            continue

        cur.execute(
            """
            INSERT INTO irs.state_collections (
                fiscal_year,
                state_id,
                state_name,
                tax_category,
                returns_filed,
                returns_filed_electronically,
                gross_collections_thousands,
                refunds_issued,
                refund_amount_thousands,
                source_file
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                fiscal_year,
                STATE_ID,
                STATE_NAME,
                tax_category,
                to_int(row[1]),
                to_int(row[2]),
                to_int(row[3]),
                to_int(row[4]),
                to_int(row[5]),
                str(source_file),
            ),
        )

        rows_loaded += 1

    conn.commit()
    cur.close()
    conn.close()

    logger.info("Loaded %s IRS state collection rows for FY%s.", rows_loaded, fiscal_year)


def main():
    parser = argparse.ArgumentParser(description="Load IRS state collections workbook.")
    parser.add_argument("fiscal_year", type=int)
    parser.add_argument("source_file", type=Path)

    args = parser.parse_args()
    load_irs_state_collections(args.fiscal_year, args.source_file)


if __name__ == "__main__":
    main()