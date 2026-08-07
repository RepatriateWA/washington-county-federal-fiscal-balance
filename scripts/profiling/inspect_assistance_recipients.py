from etl.common.db import get_connection

LOAD_BATCH_ID = 6

conn = get_connection()

with conn.cursor() as cur:

    print("=" * 80)
    print("TOP 50 RECIPIENT NAMES")
    print("=" * 80)

    cur.execute("""
        SELECT
            raw_record->>'recipient_name' AS recipient_name,
            COUNT(*) AS row_count
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
        GROUP BY recipient_name
        ORDER BY row_count DESC
        LIMIT 50;
    """, (LOAD_BATCH_ID,))

    for row in cur.fetchall():
        print(row)

    print()
    print("=" * 80)
    print("BUSINESS TYPES")
    print("=" * 80)

    cur.execute("""
        SELECT
            raw_record->>'business_types_code' AS code,
            raw_record->>'business_types_description' AS description,
            COUNT(*) AS row_count
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
        GROUP BY code, description
        ORDER BY row_count DESC;
    """, (LOAD_BATCH_ID,))

    for row in cur.fetchall():
        print(row)

conn.close()