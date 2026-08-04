from etl.common.db import get_connection


LOAD_BATCH_ID = 5
AWARD_ID = 2954


def main() -> None:
    sql = """
        SELECT
            at.award_transaction_id,
            at.source_row_number,
            at.action_date,
            raw.raw_record ->> 'recipient_uei'
                AS recipient_uei,
            raw.raw_record ->> 'recipient_name'
                AS recipient_name,
            raw.raw_record ->> 'contract_award_unique_key'
                AS award_key,
            raw.raw_record ->> 'contract_transaction_unique_key'
                AS transaction_key
        FROM procurement.award_transaction AS at
        JOIN procurement.raw_award_transaction AS raw
          ON raw.load_batch_id = at.load_batch_id
         AND raw.source_row_number = at.source_row_number
        WHERE at.load_batch_id = %s
          AND at.award_id = %s
        ORDER BY
            at.action_date,
            at.source_row_number,
            at.award_transaction_id;
    """

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    LOAD_BATCH_ID,
                    AWARD_ID,
                ),
            )

            rows = cur.fetchall()

        print(f"Award ID: {AWARD_ID}")
        print(f"Rows found: {len(rows)}")
        print()

        for row in rows:
            print(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()