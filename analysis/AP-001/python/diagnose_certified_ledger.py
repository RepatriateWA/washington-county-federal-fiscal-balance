from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from etl.common.db import get_connection

def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 88)
    print("AP-001A — CERTIFIED LEDGER DIAGNOSTICS")
    print("=" * 88)

    print("\n1. FISCAL YEAR BY LOAD BATCH")
    print("-" * 88)

    cur.execute(
        """
        SELECT
            load_batch_id,
            action_date_fiscal_year,
            COUNT(*) AS transaction_count,
            SUM(federal_action_obligation) AS obligation
        FROM assistance.award_transaction
        GROUP BY
            load_batch_id,
            action_date_fiscal_year
        ORDER BY
            load_batch_id,
            action_date_fiscal_year;
        """
    )

    for row in cur.fetchall():
        print(row)

    print("\n2. COUNTY FIPS FORMAT IN procurement.place")
    print("-" * 88)

    cur.execute(
        """
        SELECT
            state_code,
            state_fips,
            county_name,
            county_fips,
            LENGTH(TRIM(county_fips)) AS county_fips_length,
            COUNT(*) AS place_count
        FROM procurement.place
        WHERE county_fips IS NOT NULL
        GROUP BY
            state_code,
            state_fips,
            county_name,
            county_fips
        ORDER BY
            state_code,
            county_fips
        LIMIT 50;
        """
    )

    for row in cur.fetchall():
        print(row)

    print("\n3. WASHINGTON COUNTY FIPS FORMAT")
    print("-" * 88)

    cur.execute(
        """
        SELECT
            p.state_code,
            p.state_fips,
            p.county_name,
            p.county_fips,
            LENGTH(TRIM(p.county_fips)) AS place_fips_length,
            cr.county_fips AS registry_county_fips,
            cr.full_fips AS registry_full_fips
        FROM procurement.place p
        LEFT JOIN reference.county_registry cr
          ON cr.full_fips = TRIM(p.county_fips)
          OR (
                cr.county_fips = RIGHT(TRIM(p.county_fips), 3)
                AND p.state_fips = '53'
             )
        WHERE p.state_code = 'WA'
          AND p.county_fips IS NOT NULL
        ORDER BY p.county_fips
        LIMIT 100;
        """
    )

    for row in cur.fetchall():
        print(row)

    print("\n4. UNRESOLVED COUNTY PROFILE")
    print("-" * 88)

    cur.execute(
        """
        SELECT
            place_source_condition,
            performance_state_code,
            performance_state_fips,
            performance_county_name,
            performance_county_fips,
            COUNT(*) AS transaction_count,
            SUM(federal_action_obligation) AS obligation
        FROM analysis.v_certified_assistance_ledger
        WHERE reference_county_id IS NULL
        GROUP BY
            place_source_condition,
            performance_state_code,
            performance_state_fips,
            performance_county_name,
            performance_county_fips
        ORDER BY
            transaction_count DESC,
            performance_county_fips;
        """
    )

    for row in cur.fetchall():
        print(row)

    print("\n5. FINAL NINE UNRESOLVED COUNTY TRANSACTIONS")
    print("-" * 88)

    cur.execute(
        """
        SELECT
            assistance_transaction_id,
            assistance_transaction_unique_key,
            load_batch_id,
            action_date_fiscal_year,
            action_date,
            federal_action_obligation,
            recipient_name,
            performance_state_code,
            performance_county_name,
            performance_county_fips,
            performance_city_name,
            performance_zip4,
            place_identity_key,
            place_identity_type,
            place_source_condition,
            usaspending_permalink
        FROM analysis.v_certified_assistance_ledger
        WHERE reference_county_id IS NULL
        AND place_source_condition IS NULL
        ORDER BY
            action_date_fiscal_year,
            assistance_transaction_id;
    """
)

    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()

    
if __name__ == "__main__":
    main()