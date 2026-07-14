from etl.db import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            fp.federal_program_id,
            fa.agency_code,
            fp.program_code,
            fp.program_name,
            fp.program_category
        FROM reference.federal_program fp
        JOIN reference.federal_agency fa
          ON fp.federal_agency_id = fa.federal_agency_id
        ORDER BY
            fa.agency_code,
            fp.program_name;
    """)

    print("=" * 120)
    print("FEDERAL PROGRAM DIMENSION")
    print("=" * 120)

    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()