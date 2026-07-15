from etl.db import get_connection
from etl.logging_config import get_logger


logger = get_logger(__name__)

WASHINGTON_STATE_ID = 48
WASHINGTON_STATE_FIPS = "53"
UNKNOWN_COUNTY_CODE = "53000"
MEDICARE_PROGRAM_CODE = "MEDICARE"
CMS_AGENCY_CODE = "CMS"


def scalar(cur, sql, params=None):
    cur.execute(sql, params or ())
    row = cur.fetchone()
    return row[0] if row else None


def load_cms_medicare_geographic_payments() -> None:
    conn = get_connection()
    cur = conn.cursor()

    try:
        federal_agency_id = scalar(
            cur,
            """
            SELECT federal_agency_id
            FROM reference.federal_agency
            WHERE agency_code = %s;
            """,
            (CMS_AGENCY_CODE,),
        )

        if federal_agency_id is None:
            raise ValueError(
                "CMS agency is missing from reference.federal_agency."
            )

        federal_program_id = scalar(
            cur,
            """
            SELECT federal_program_id
            FROM reference.federal_program
            WHERE program_code = %s;
            """,
            (MEDICARE_PROGRAM_CODE,),
        )

        if federal_program_id is None:
            raise ValueError(
                "MEDICARE is missing from reference.federal_program."
            )

        cur.execute(
            """
            DELETE FROM cms.medicare_geographic_payments
            WHERE state_id = %s;
            """,
            (WASHINGTON_STATE_ID,),
        )

        cur.execute(
            """
            INSERT INTO cms.medicare_geographic_payments (
                report_year,
                state_id,
                county_id,
                federal_agency_id,
                federal_program_id,
                geography_code,
                age_group,
                total_beneficiaries,
                original_medicare_beneficiaries,
                medicare_advantage_beneficiaries,
                medicare_advantage_rate,
                total_medicare_payments_dollars,
                standardized_medicare_payments_dollars,
                source_file,
                methodology_note
            )
            SELECT
                raw.report_year,
                %s AS state_id,
                county.county_id,
                %s AS federal_agency_id,
                %s AS federal_program_id,
                LPAD(
                    REGEXP_REPLACE(raw.geography_code, '\\.0$', ''),
                    5,
                    '0'
                ) AS geography_code,
                raw.age_group,
                raw.total_beneficiaries::BIGINT,
                raw.original_medicare_beneficiaries::BIGINT,
                raw.medicare_advantage_beneficiaries::BIGINT,
                raw.medicare_advantage_rate,
                raw.total_medicare_payments,
                raw.standardized_medicare_payments,
                raw.source_file,
                (
                    'Original Medicare geographic variation payment data. '
                    'Actual CMS payment amount used for fiscal-balance reporting; '
                    'standardized payment retained for analytical comparison. '
                    'Medicare Advantage enrollment is included, but Medicare '
                    'Advantage payments are not fully represented in this source.'
                ) AS methodology_note
            FROM cms_raw.medicare_geographic_variation raw
            JOIN reference.county_registry county
                ON county.full_fips = LPAD(
                    REGEXP_REPLACE(raw.geography_code, '\\.0$', ''),
                    5,
                    '0'
                )
               AND county.state_id = %s
            WHERE raw.report_year BETWEEN 2015 AND 2024
              AND raw.geography_level = 'County'
              AND raw.geography_name LIKE 'WA-%%'
              AND raw.geography_code <> %s
              AND raw.age_group = 'All';
            """,
            (
                WASHINGTON_STATE_ID,
                federal_agency_id,
                federal_program_id,
                WASHINGTON_STATE_ID,
                UNKNOWN_COUNTY_CODE,
            ),
        )

        rows_loaded = cur.rowcount

        expected_rows = 39 * 10

        if rows_loaded != expected_rows:
            raise ValueError(
                f"Expected {expected_rows} curated Medicare rows, "
                f"loaded {rows_loaded}."
            )

        conn.commit()

        logger.info(
            "Loaded %s CMS Medicare geographic payment rows "
            "for Washington, 2015-2024.",
            rows_loaded,
        )

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


def main() -> None:
    load_cms_medicare_geographic_payments()


if __name__ == "__main__":
    main()