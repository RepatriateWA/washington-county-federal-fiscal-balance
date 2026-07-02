from etl.loaders.load_states import get_connection

def main():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            ordinal_position,
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_schema = 'reference'
          AND table_name = 'county_registry'
        ORDER BY ordinal_position;
    """)

    print("\nColumns in reference.county_registry:\n")

    for position, column, datatype in cur.fetchall():
        print(f"{position:2d}. {column:<25} {datatype}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()