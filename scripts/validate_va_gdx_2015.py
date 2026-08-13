from etl.common.db import get_connection


def main() -> None:
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            print("=" * 88)
            print("VA GDX FY2015 VALIDATION")
            print("=" * 88)

            cur.execute(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT county_id)
                FROM va.gdx_county_expenditure
                WHERE fiscal_year = 2015;
                """
            )
            exp_rows, counties = cur.fetchone()

            print()
            print(f"Expenditure rows ................. {exp_rows:,}")
            print(f"Distinct counties ................ {counties:,}")

            cur.execute(
                """
                SELECT COUNT(*)
                FROM va.gdx_county_metric
                WHERE fiscal_year = 2015;
                """
            )
            metric_rows = cur.fetchone()[0]

            print(f"Metric rows ...................... {metric_rows:,}")

            cur.execute(
                """
                SELECT
                    e.county_name_source,
                    c.category_code,
                    e.source_amount,
                    e.source_unit,
                    e.expenditure_amount
                FROM va.gdx_county_expenditure AS e
                JOIN va.gdx_expenditure_category AS c
                  ON c.gdx_category_id = e.gdx_category_id
                WHERE e.fiscal_year = 2015
                  AND UPPER(e.county_name_source) = 'ADAMS'
                ORDER BY e.source_column_number;
                """
            )

            print()
            print("ADAMS COUNTY SOURCE / NORMALIZED VALUES")
            print("-" * 88)

            for row in cur.fetchall():
                print(row)

            cur.execute(
                """
                SELECT
                    COUNT(*),
                    SUM(va_gdx_expenditure_amount)
                FROM va.v_washington_county_gdx_control_total
                WHERE fiscal_year = 2015;
                """
            )

            control_count, control_total = cur.fetchone()

            print()
            print("COUNTY CONTROL TOTAL VIEW")
            print("-" * 88)
            print(f"County rows ...................... {control_count:,}")
            print(f"Washington VA expenditure ....... ${control_total:,.2f}")

            passed = (
                int(exp_rows) == 312
                and int(counties) == 39
                and int(metric_rows) == 78
                and int(control_count) == 39
            )

            print()
            print("=" * 88)
            print(
                "OVERALL RESULT: "
                + ("PASS" if passed else "FAIL")
            )
            print("=" * 88)

            if not passed:
                raise SystemExit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()