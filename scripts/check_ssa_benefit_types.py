from etl.db import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            ssa_benefit_type_id,
            benefit_type_code,
            benefit_type_name,
            benefit_group,
            display_order,
            is_total
        FROM reference.ssa_benefit_type
        ORDER BY display_order;
    """)

    print("=" * 100)
    print("SSA BENEFIT TYPES")
    print("=" * 100)

    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()