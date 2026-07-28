from etl.common.db import get_connection


def main() -> None:
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    raw.raw_record ->> 'funding_agency_code'
                        AS funding_agency_code,
                    raw.raw_record ->> 'funding_agency_name'
                        AS funding_agency_name,
                    COUNT(*) AS transaction_count,
                    MIN(txn.action_date) AS first_action_date,
                    MAX(txn.action_date) AS last_action_date
                FROM procurement.award_transaction AS txn
                JOIN procurement.raw_award_transaction AS raw
                  ON raw.load_batch_id = txn.load_batch_id
                 AND raw.source_row_number = txn.source_row_number
                WHERE txn.load_batch_id = 4
                  AND txn.award_id = 3
                GROUP BY
                    raw.raw_record ->> 'funding_agency_code',
                    raw.raw_record ->> 'funding_agency_name'
                ORDER BY transaction_count DESC;
                """
            )

            for row in cur.fetchall():
                print(row)

    finally:
        conn.close()


if __name__ == "__main__":
    main()