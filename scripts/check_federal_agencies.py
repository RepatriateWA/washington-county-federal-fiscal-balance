from etl.db import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            federal_agency_id,
            agency_code,
            agency_name,
            parent_agency_code,
            agency_level,
            is_revenue_agency,
            is_expenditure_agency,
            is_active
        FROM reference.federal_agency
        ORDER BY federal_agency_id;
    """)

    print("=" * 120)
    print("FEDERAL AGENCY DIMENSION")
    print("=" * 120)

    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()