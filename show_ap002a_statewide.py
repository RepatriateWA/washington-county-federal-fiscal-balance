from etl.common.db import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM analysis.v_statewide_assistance_by_year
        ORDER BY fiscal_year;
        """
    )

    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()

    print()
    print(" | ".join(columns))
    print("-" * 180)

    for row in rows:
        print(" | ".join(str(value) for value in row))

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()