from etl.common.db import get_connection


LOAD_BATCH_ID = 5
PARENT_UEIS = (
    "U5KEFDV4N965",
    "ZVW2T2CCG7V9",
)


def main() -> None:
    sql = """
        SELECT
            source_row_number,
            raw_record ->> 'recipient_uei' AS recipient_uei,
            raw_record ->> 'recipient_duns' AS recipient_duns,
            raw_record ->> 'recipient_name' AS recipient_name,
            raw_record ->> 'recipient_name_raw' AS recipient_name_raw,
            raw_record ->> 'recipient_parent_uei'
                AS recipient_parent_uei,
            raw_record ->> 'recipient_parent_name'
                AS recipient_parent_name,
            raw_record ->> 'recipient_parent_name_raw'
                AS recipient_parent_name_raw,
            raw_record ->> 'contract_award_unique_key'
                AS award_key,
            raw_record ->> 'contract_transaction_unique_key'
                AS transaction_key,
            raw_record ->> 'action_date' AS action_date
        FROM procurement.raw_award_transaction
        WHERE load_batch_id = %s
          AND raw_record ->> 'recipient_parent_uei' = ANY(%s)
        ORDER BY
            raw_record ->> 'recipient_uei',
            raw_record ->> 'action_date',
            source_row_number;
    """

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    LOAD_BATCH_ID,
                    list(PARENT_UEIS),
                ),
            )
            rows = cur.fetchall()

        print(f"Rows found: {len(rows)}")
        print()

        for row in rows:
            print(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()