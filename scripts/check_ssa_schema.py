from etl.db import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            ordinal_position,
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_schema = 'ssa'
          AND table_name = 'benefit_payments'
        ORDER BY ordinal_position;
    """)

    print("=" * 80)
    print("SSA BENEFIT PAYMENTS SCHEMA")
    print("=" * 80)

    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()