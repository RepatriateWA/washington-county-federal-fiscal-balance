from etl.db import get_connection

def main():
    conn = get_connection()
    cur = conn.cursor()

    print("\nCHIP TABLES")
    print("-" * 60)

    cur.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'chip'
      AND table_type = 'BASE TABLE'
    ORDER BY table_name;
""")

    for row in cur.fetchall():
        print(row[0])

    print("\nCHIP VIEWS")
    print("-" * 60)

    cur.execute("""
        SELECT table_name
        FROM information_schema.views
        WHERE table_schema = 'chip'
        ORDER BY table_name;
    """)

    for row in cur.fetchall():
        print(row[0])

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()