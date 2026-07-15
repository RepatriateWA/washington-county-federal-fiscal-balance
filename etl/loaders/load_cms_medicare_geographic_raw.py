import argparse
from pathlib import Path

import pandas as pd

from etl.db import get_connection
from etl.logging_config import get_logger


logger = get_logger(__name__)


COLUMN_MAP = {
    "YEAR": "report_year",
    "BENE_GEO_LVL": "geography_level",
    "BENE_GEO_DESC": "geography_name",
    "BENE_GEO_CD": "geography_code",
    "BENE_AGE_LVL": "age_group",
    "BENES_TOTAL_CNT": "total_beneficiaries",
    "BENES_OM_CNT": "original_medicare_beneficiaries",
    "BENES_MA_CNT": "medicare_advantage_beneficiaries",
    "MA_PRTCPTN_RATE": "medicare_advantage_rate",
    "TOT_MDCR_PYMT_AMT": "total_medicare_payments",
    "TOT_MDCR_STDZD_PYMT_AMT": "standardized_medicare_payments",
}


def to_numeric(value):
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text in {"", "*", "nan", "NaN", "N/A"}:
        return None

    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


def load_cms_medicare_geographic_raw(source_file: Path) -> None:
    if not source_file.exists():
        raise FileNotFoundError(f"Missing CMS source file: {source_file}")

    df = pd.read_csv(
        source_file,
        low_memory=False,
        dtype=str,
    )

    missing_columns = [
        column
        for column in COLUMN_MAP
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "CMS source is missing required columns: "
            + ", ".join(missing_columns)
        )

    df = df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            DELETE FROM cms_raw.medicare_geographic_variation
            WHERE source_file = %s;
            """,
            (str(source_file),),
        )

        rows_loaded = 0

        for _, row in df.iterrows():
            report_year = to_numeric(row["report_year"])

            if report_year is None:
                continue

            cur.execute(
                """
                INSERT INTO cms_raw.medicare_geographic_variation (
                    report_year,
                    geography_level,
                    geography_name,
                    geography_code,
                    age_group,
                    total_beneficiaries,
                    original_medicare_beneficiaries,
                    medicare_advantage_beneficiaries,
                    medicare_advantage_rate,
                    total_medicare_payments,
                    standardized_medicare_payments,
                    source_file
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                );
                """,
                (
                    int(report_year),
                    str(row["geography_level"]).strip(),
                    str(row["geography_name"]).strip(),
                    str(row["geography_code"]).strip(),
                    str(row["age_group"]).strip(),
                    to_numeric(row["total_beneficiaries"]),
                    to_numeric(row["original_medicare_beneficiaries"]),
                    to_numeric(row["medicare_advantage_beneficiaries"]),
                    to_numeric(row["medicare_advantage_rate"]),
                    to_numeric(row["total_medicare_payments"]),
                    to_numeric(row["standardized_medicare_payments"]),
                    str(source_file),
                ),
            )

            rows_loaded += 1

        conn.commit()

        logger.info(
            "Loaded %s CMS Medicare geographic raw rows from %s.",
            rows_loaded,
            source_file,
        )

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load selected Medicare Geographic Variation fields into cms_raw."
    )

    parser.add_argument(
        "source_file",
        type=Path,
        help="CMS Medicare Geographic Variation CSV file.",
    )

    args = parser.parse_args()

    load_cms_medicare_geographic_raw(args.source_file)


if __name__ == "__main__":
    main()