from etl.common.db import get_connection


def print_variation(
    cur,
    *,
    code_key: str,
    name_key: str,
    heading: str,
) -> None:
    """
    Print transaction counts and date ranges for one subagency relationship.
    """
    cur.execute(
        f"""
        SELECT
            raw.raw_record ->> %s AS subagency_code,
            raw.raw_record ->> %s AS subagency_name,
            COUNT(*) AS transaction_count,
            MIN(txn.action_date) AS first_action_date,
            MAX(txn.action_date) AS last_action_date
        FROM procurement.award_transaction AS txn
        JOIN procurement.raw_award_transaction AS raw
          ON raw.load_batch_id = txn.load_batch_id
         AND raw.source_row_number = txn.source_row_number
        WHERE txn.load_batch_id = %s
          AND txn.award_id = %s
        GROUP BY
            raw.raw_record ->> %s,
            raw.raw_record ->> %s
        ORDER BY
            last_action_date DESC,
            transaction_count DESC;
        """,
        (
            code_key,
            name_key,
            4,
            3,
            code_key,
            name_key,
        ),
    )

    print()
    print("=" * 76)
    print(heading)
    print("=" * 76)

    for row in cur.fetchall():
        print(row)


def print_latest_transactions(cur) -> None:
    """
    Print the most recent transactions and their agency relationships.
    """
    cur.execute(
        """
        SELECT
            txn.action_date,
            txn.source_row_number,
            raw.raw_record ->> 'awarding_agency_code',
            raw.raw_record ->> 'awarding_sub_agency_code',
            raw.raw_record ->> 'awarding_sub_agency_name',
            raw.raw_record ->> 'funding_agency_code',
            raw.raw_record ->> 'funding_sub_agency_code',
            raw.raw_record ->> 'funding_sub_agency_name'
        FROM procurement.award_transaction AS txn
        JOIN procurement.raw_award_transaction AS raw
          ON raw.load_batch_id = txn.load_batch_id
         AND raw.source_row_number = txn.source_row_number
        WHERE txn.load_batch_id = 4
          AND txn.award_id = 3
        ORDER BY
            txn.action_date DESC,
            txn.source_row_number DESC
        LIMIT 20;
        """
    )

    print()
    print("=" * 76)
    print("MOST RECENT TRANSACTIONS")
    print("=" * 76)

    for row in cur.fetchall():
        print(row)


def main() -> None:
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            print_variation(
                cur,
                code_key="awarding_sub_agency_code",
                name_key="awarding_sub_agency_name",
                heading="AWARDING SUBAGENCY VARIATION",
            )

            print_variation(
                cur,
                code_key="funding_sub_agency_code",
                name_key="funding_sub_agency_name",
                heading="FUNDING SUBAGENCY VARIATION",
            )

            print_latest_transactions(cur)

    finally:
        conn.close()


if __name__ == "__main__":
    main()