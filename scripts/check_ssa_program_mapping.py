from etl.db import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 120)
    print("SSA BENEFIT TYPE TO FEDERAL PROGRAM MAPPING")
    print("=" * 120)

    cur.execute("""
        SELECT
            sbt.benefit_type_code,
            sbt.benefit_type_name,
            fp.program_code,
            fp.program_name
        FROM reference.ssa_benefit_type sbt
        LEFT JOIN reference.federal_program fp
          ON sbt.federal_program_id = fp.federal_program_id
        ORDER BY sbt.display_order;
    """)

    for row in cur.fetchall():
        print(row)

    print("\n2024 SSA payment rows by federal program")
    print("-" * 120)

    cur.execute("""
        SELECT
            COALESCE(fp.program_code, 'UNMAPPED_TOTAL') AS program_code,
            COUNT(*) AS payment_rows,
            SUM(bp.annual_benefits_thousands) AS annualized_thousands
        FROM ssa.benefit_payments bp
        LEFT JOIN reference.federal_program fp
          ON bp.federal_program_id = fp.federal_program_id
        WHERE bp.report_year = 2024
          AND bp.agency_code = 'SSA'
        GROUP BY COALESCE(fp.program_code, 'UNMAPPED_TOTAL')
        ORDER BY program_code;
    """)

    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()