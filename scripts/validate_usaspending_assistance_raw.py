"""
Validate raw USAspending Assistance ingestion.

Run:
    python -m scripts.validate_usaspending_assistance_raw
"""

from etl.common.db import get_connection


def main() -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            print("=" * 88)
            print("USASPENDING ASSISTANCE RAW INGESTION VALIDATION")
            print("=" * 88)

            cur.execute("""
                SELECT
                    lb.load_batch_id,
                    lb.fiscal_year_start,
                    lb.load_status,
                    lb.source_record_count,
                    lb.loaded_record_count,
                    COUNT(raw.raw_assistance_transaction_id) AS database_rows,
                    COUNT(DISTINCT raw.assistance_transaction_unique_key)
                        AS distinct_transaction_keys,
                    COUNT(DISTINCT raw.assistance_award_unique_key)
                        AS distinct_award_keys,
                    lb.source_file
                FROM procurement.load_batch AS lb
                JOIN assistance.raw_award_transaction AS raw
                  ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_batch_id BETWEEN 7 AND 12
                GROUP BY
                    lb.load_batch_id,
                    lb.fiscal_year_start,
                    lb.load_status,
                    lb.source_record_count,
                    lb.loaded_record_count,
                    lb.source_file
                ORDER BY lb.load_batch_id;
            """)
            rows = cur.fetchall()
            if not rows:
                raise ValueError("No raw Assistance rows found for load batches 7-12.")

            failures = []

            print()
            print("Batch | FY   | Status     | Source Rows | Loaded Rows | DB Rows | Tx Keys | Award Keys")
            print("-" * 88)

            for row in rows:
                batch_id, fy, status, source_count, loaded_count, db_rows, tx_keys, award_keys, source_file = row
                print(
                    f"{batch_id:5} | {str(fy or ''):4} | {status:10} | "
                    f"{source_count or 0:11,} | {loaded_count or 0:11,} | "
                    f"{db_rows:7,} | {tx_keys:7,} | {award_keys:10,}"
                )
                print(f"      {source_file}")

                if status != "COMPLETED":
                    failures.append(f"Batch {batch_id}: status={status}")
                if not (source_count == loaded_count == db_rows):
                    failures.append(
                        f"Batch {batch_id}: row-count mismatch "
                        f"source={source_count}, loaded={loaded_count}, db={db_rows}"
                    )
                if db_rows != tx_keys:
                    failures.append(
                        f"Batch {batch_id}: duplicate transaction keys "
                        f"rows={db_rows}, distinct={tx_keys}"
                    )

            print()
            print("PAIRWISE CROSS-BATCH TRANSACTION OVERLAP")
            print("-" * 88)
            cur.execute("""
                WITH batches AS (
                    SELECT DISTINCT load_batch_id
                    FROM assistance.raw_award_transaction
                    WHERE load_batch_id BETWEEN 7 AND 12
                ),
                pairs AS (
                    SELECT a.load_batch_id AS batch_a, b.load_batch_id AS batch_b
                    FROM batches a
                    JOIN batches b ON a.load_batch_id < b.load_batch_id
                )
                SELECT p.batch_a, p.batch_b, COUNT(*) AS shared_transaction_keys
                FROM pairs p
                JOIN assistance.raw_award_transaction a
                  ON a.load_batch_id = p.batch_a
                JOIN assistance.raw_award_transaction b
                  ON b.load_batch_id = p.batch_b
                 AND b.assistance_transaction_unique_key =
                     a.assistance_transaction_unique_key
                GROUP BY p.batch_a, p.batch_b
                ORDER BY p.batch_a, p.batch_b;
            """)
            overlaps = cur.fetchall()
            if overlaps:
                for batch_a, batch_b, shared in overlaps:
                    print(f"Batch {batch_a} vs {batch_b}: {shared:,} shared transaction keys")
            else:
                print("No cross-batch transaction-key overlap detected.")

            print()
            print("FY2020 BATCH 7 VS 8 RAW RECORD COMPARISON")
            print("-" * 88)
            cur.execute("""
                SELECT
                    COUNT(*) AS shared_keys,
                    COUNT(*) FILTER (WHERE a.raw_record = b.raw_record)
                        AS identical_raw_records,
                    COUNT(*) FILTER (WHERE a.raw_record <> b.raw_record)
                        AS differing_raw_records
                FROM assistance.raw_award_transaction a
                JOIN assistance.raw_award_transaction b
                  ON b.assistance_transaction_unique_key =
                     a.assistance_transaction_unique_key
                WHERE a.load_batch_id = 7
                  AND b.load_batch_id = 8;
            """)
            shared, identical, differing = cur.fetchone()
            print(f"Shared transaction keys ......... {shared:,}")
            print(f"Identical raw records ........... {identical:,}")
            print(f"Differing raw records ........... {differing:,}")

            print()
            print("FISCAL-YEAR DISTRIBUTION FROM SOURCE ROWS")
            print("-" * 88)
            cur.execute("""
                SELECT
                    load_batch_id,
                    NULLIF(BTRIM(raw_record ->> 'action_date_fiscal_year'), '') AS action_fy,
                    COUNT(*)
                FROM assistance.raw_award_transaction
                WHERE load_batch_id BETWEEN 7 AND 12
                GROUP BY load_batch_id, action_fy
                ORDER BY load_batch_id, action_fy;
            """)
            for batch_id, fy, count in cur.fetchall():
                print(f"Batch {batch_id}: FY {fy}: {count:,}")

            print()
            print("COVID SOURCE FIELD PRESENCE")
            print("-" * 88)
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE NULLIF(BTRIM(raw_record ->>
                            'disaster_emergency_fund_codes_for_overall_award'), '') IS NOT NULL
                    ),
                    COUNT(*) FILTER (
                        WHERE NULLIF(BTRIM(raw_record ->>
                            'obligated_amount_from_COVID-19_supplementals_for_overall_award'), '') IS NOT NULL
                    ),
                    COUNT(*) FILTER (
                        WHERE NULLIF(BTRIM(raw_record ->>
                            'outlayed_amount_from_COVID-19_supplementals_for_overall_award'), '') IS NOT NULL
                    )
                FROM assistance.raw_award_transaction
                WHERE load_batch_id BETWEEN 7 AND 12;
            """)
            defc, covid_obl, covid_outlay = cur.fetchone()
            print(f"Rows with DEFC value ............ {defc:,}")
            print(f"Rows with COVID obligation ...... {covid_obl:,}")
            print(f"Rows with COVID outlay .......... {covid_outlay:,}")

            print()
            print("WASHINGTON GEOGRAPHY PRESENCE")
            print("-" * 88)
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE raw_record ->> 'recipient_state_code' = 'WA'
                    ),
                    COUNT(*) FILTER (
                        WHERE raw_record ->>
                        'prime_award_transaction_place_of_performance_state_fips_code' = '53'
                    ),
                    COUNT(*) FILTER (
                        WHERE raw_record ->> 'recipient_state_code' = 'WA'
                          AND NULLIF(BTRIM(raw_record ->>
                          'prime_award_transaction_recipient_county_fips_code'), '') IS NOT NULL
                    ),
                    COUNT(*) FILTER (
                        WHERE raw_record ->>
                        'prime_award_transaction_place_of_performance_state_fips_code' = '53'
                          AND NULLIF(BTRIM(raw_record ->>
                          'prime_award_transaction_place_of_performance_county_fips_code'), '') IS NOT NULL
                    )
                FROM assistance.raw_award_transaction
                WHERE load_batch_id BETWEEN 7 AND 12;
            """)
            values = cur.fetchone()
            print(f"WA recipient rows ............... {values[0]:,}")
            print(f"WA place-of-performance rows .... {values[1]:,}")
            print(f"WA recipient county rows ........ {values[2]:,}")
            print(f"WA performance county rows ...... {values[3]:,}")

            print()
            print("=" * 88)
            if failures:
                print("VALIDATION: FAIL")
                for failure in failures:
                    print(f"  - {failure}")
                print("=" * 88)
                return 1

            print("VALIDATION: PASS")
            print("=" * 88)
            return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())