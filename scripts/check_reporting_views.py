from etl.db import get_connection


def print_rows(cur, title, sql):
    print("\n" + "=" * 120)
    print(title)
    print("=" * 120)

    cur.execute(sql)

    for row in cur.fetchall():
        print(row)


def main():
    conn = get_connection()
    cur = conn.cursor()

    print_rows(
        cur,
        "WASHINGTON FEDERAL RECEIPTS",
        """
        SELECT
            fiscal_year,
            gross_collections_dollars
        FROM reporting.v_washington_revenue_summary
        ORDER BY fiscal_year;
        """,
    )

    print_rows(
        cur,
        "WASHINGTON SSA ANNUALIZED EXPENDITURES",
        """
        SELECT
            report_year,
            program_code,
            beneficiary_count,
            annualized_benefits_dollars
        FROM reporting.v_washington_ssa_summary
        ORDER BY
            report_year,
            program_code;
        """,
    )

    print_rows(
        cur,
        "SPOKANE COUNTY SSA DETAIL",
        """
        SELECT
            report_year,
            program_code,
            benefit_type,
            beneficiary_count,
            annualized_benefits_dollars
        FROM reporting.v_federal_expenditures_by_county_year
        WHERE county_name = 'Spokane'
          AND benefit_type <> 'Total'
        ORDER BY
            report_year,
            program_code,
            benefit_type;
        """,
    )

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()