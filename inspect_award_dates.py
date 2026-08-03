from etl.common.db import get_connection

AWARD_KEY = "CONT_AWD_36C26023P0181_3600_-NONE-_-NONE-"
LOAD_BATCH_ID = 5


def main() -> None:
    sql = """
        SELECT
            source_row_number,
            raw_record ->> 'action_date' AS action_date,
            raw_record ->> 'period_of_performance_start_date'
                AS performance_start,
            raw_record ->> 'period_of_performance_current_end_date'
                AS performance_current_end,
            raw_record ->> 'period_of_performance_potential_end_date'
                AS performance_potential_end,
            raw_record ->> 'modification_number'
                AS modification_number,
            raw_record ->> 'contract_transaction_unique_key'
                AS transaction_key
        FROM procurement.raw_award_transaction
        WHERE load_batch_id = %s
          AND raw_record ->> 'contract_award_unique_key' = %s
        ORDER BY
            raw_record ->> 'action_date',
            source_row_number;
    """

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(sql, (LOAD_BATCH_ID, AWARD_KEY))
            rows = cur.fetchall()

        print(f"Award: {AWARD_KEY}")
        print(f"Rows found: {len(rows)}")
        print()

        for row in rows:
            print(row)

    finally:
        conn.close()


if __name__ == "__main__":
    main()