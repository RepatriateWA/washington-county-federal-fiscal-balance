from etl.common.db import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 110)
    print("PROCUREMENT LOAD BATCH INVENTORY")
    print("=" * 110)

    # First show the batch table itself
    cur.execute("""
        SELECT *
        FROM procurement.load_batch
        ORDER BY load_batch_id;
    """)

    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()

    print()
    print("LOAD BATCH TABLE")
    print("-" * 110)
    print(" | ".join(columns))
    print("-" * 110)

    for row in rows:
        print(" | ".join(str(value) for value in row))

    # Then summarize raw and canonical transaction counts by batch
    print()
    print("=" * 110)
    print("TRANSACTION COUNTS BY LOAD BATCH")
    print("=" * 110)

    cur.execute("""
        SELECT
            lb.load_batch_id,

            COUNT(DISTINCT rat.raw_award_transaction_id)
                AS raw_transaction_rows,

            COUNT(DISTINCT at.award_transaction_id)
                AS canonical_transaction_rows,

            COUNT(DISTINCT at.award_id)
                AS canonical_awards

        FROM procurement.load_batch lb

        LEFT JOIN procurement.raw_award_transaction rat
          ON rat.load_batch_id = lb.load_batch_id

        LEFT JOIN procurement.award_transaction at
          ON at.load_batch_id = lb.load_batch_id

        GROUP BY lb.load_batch_id

        ORDER BY lb.load_batch_id;
    """)

    print(
        f"{'Batch':>7} | "
        f"{'Raw Rows':>12} | "
        f"{'Canonical Tx':>14} | "
        f"{'Awards':>12}"
    )
    print("-" * 60)

    for row in cur.fetchall():
        print(
            f"{row[0]:>7} | "
            f"{row[1]:>12,} | "
            f"{row[2]:>14,} | "
            f"{row[3]:>12,}"
        )

    # Fiscal-year distribution from canonical transactions
    print()
    print("=" * 110)
    print("FISCAL YEAR DISTRIBUTION BY LOAD BATCH")
    print("=" * 110)

    cur.execute("""
        SELECT
            load_batch_id,
            action_date_fiscal_year,
            COUNT(*) AS transaction_count,
            SUM(federal_action_obligation) AS obligation
        FROM procurement.award_transaction
        GROUP BY
            load_batch_id,
            action_date_fiscal_year
        ORDER BY
            load_batch_id,
            action_date_fiscal_year;
    """)

    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()