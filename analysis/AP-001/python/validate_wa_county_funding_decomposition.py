from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from etl.common.db import get_connection


def print_rows(title, columns, rows):
    print()
    print("=" * 112)
    print(title)
    print("=" * 112)

    widths = []
    for i, col in enumerate(columns):
        width = len(str(col))
        for row in rows:
            width = max(width, len(str(row[i])))
        widths.append(width)

    header = " | ".join(
        str(col).ljust(widths[i])
        for i, col in enumerate(columns)
    )
    print(header)
    print("-" * len(header))

    for row in rows:
        print(
            " | ".join(
                str(value).ljust(widths[i])
                for i, value in enumerate(row)
            )
        )


def fetch(cur, sql):
    cur.execute(sql)
    columns = [d[0] for d in cur.description]
    return columns, cur.fetchall()


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 112)
    print("AP-001B.3 — WASHINGTON COUNTY FUNDING DECOMPOSITION VALIDATION")
    print("=" * 112)

    columns, rows = fetch(
        cur,
        """
        SELECT
            COUNT(*) AS decomposition_rows,
            COUNT(DISTINCT county_id) AS distinct_counties,
            COUNT(DISTINCT fiscal_year) AS distinct_fiscal_years,
            COUNT(DISTINCT exclusive_funding_class) AS distinct_classes
        FROM analysis.v_wa_county_funding_decomposition;
        """
    )
    print_rows("1. DECOMPOSITION PROFILE", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT
            fiscal_year,
            SUM(transaction_count) AS decomposed_transactions,
            SUM(federal_action_obligation) AS decomposed_obligation
        FROM analysis.v_wa_county_funding_decomposition
        GROUP BY fiscal_year
        ORDER BY fiscal_year;
        """
    )
    print_rows("2. EXCLUSIVE DECOMPOSITION TOTALS", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT
            c.fiscal_year,
            c.total_transactions,
            d.decomposed_transactions,
            d.decomposed_transactions - c.total_transactions
                AS transaction_difference,
            c.total_obligation,
            d.decomposed_obligation,
            d.decomposed_obligation - c.total_obligation
                AS obligation_difference
        FROM (
            SELECT
                fiscal_year,
                SUM(transaction_count) AS total_transactions,
                SUM(federal_action_obligation) AS total_obligation
            FROM analysis.v_wa_county_obligations
            GROUP BY fiscal_year
        ) c
        JOIN (
            SELECT
                fiscal_year,
                SUM(transaction_count) AS decomposed_transactions,
                SUM(federal_action_obligation) AS decomposed_obligation
            FROM analysis.v_wa_county_funding_decomposition
            GROUP BY fiscal_year
        ) d
          ON d.fiscal_year = c.fiscal_year
        ORDER BY c.fiscal_year;
        """
    )
    print_rows("3. COUNTY TOTAL RECONCILIATION", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT
            fiscal_year,
            exclusive_funding_class,
            SUM(transaction_count) AS transaction_count,
            SUM(federal_action_obligation) AS obligation
        FROM analysis.v_wa_county_funding_decomposition
        GROUP BY fiscal_year, exclusive_funding_class
        ORDER BY fiscal_year, exclusive_funding_class;
        """
    )
    print_rows("4. FUNDING CLASS BY FISCAL YEAR", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT
            fiscal_year,
            SUM(federal_action_obligation) AS total_obligation,
            SUM(
                CASE WHEN exclusive_funding_class = 'COVID'
                     THEN federal_action_obligation ELSE 0 END
            ) AS covid_obligation,
            SUM(
                CASE WHEN exclusive_funding_class = 'IIJA'
                     THEN federal_action_obligation ELSE 0 END
            ) AS iija_obligation,
            SUM(
                CASE WHEN exclusive_funding_class = 'OTHER_EXTRAORDINARY'
                     THEN federal_action_obligation ELSE 0 END
            ) AS other_extraordinary_obligation,
            SUM(
                CASE WHEN exclusive_funding_class = 'ORDINARY'
                     THEN federal_action_obligation ELSE 0 END
            ) AS ordinary_obligation,
            (
                SUM(
                    CASE WHEN exclusive_funding_class = 'COVID'
                         THEN federal_action_obligation ELSE 0 END
                )
                +
                SUM(
                    CASE WHEN exclusive_funding_class = 'IIJA'
                         THEN federal_action_obligation ELSE 0 END
                )
                +
                SUM(
                    CASE WHEN exclusive_funding_class = 'OTHER_EXTRAORDINARY'
                         THEN federal_action_obligation ELSE 0 END
                )
                +
                SUM(
                    CASE WHEN exclusive_funding_class = 'ORDINARY'
                         THEN federal_action_obligation ELSE 0 END
                )
                -
                SUM(federal_action_obligation)
            ) AS decomposition_difference
        FROM analysis.v_wa_county_funding_decomposition
        GROUP BY fiscal_year
        ORDER BY fiscal_year;
        """
    )
    print_rows("5. EXCLUSIVE CLASS RECONCILIATION", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT
            county_name,
            COUNT(DISTINCT fiscal_year) AS fiscal_years_present,
            COUNT(DISTINCT exclusive_funding_class) AS classes_present
        FROM analysis.v_wa_county_funding_decomposition
        GROUP BY county_name
        ORDER BY county_name;
        """
    )
    print_rows("6. COUNTY COVERAGE", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT
            fiscal_year,
            geographic_attribution_class,
            exclusive_funding_class,
            transaction_count,
            federal_action_obligation
        FROM analysis.v_wa_funding_decomposition_reconciliation
        ORDER BY
            fiscal_year,
            geographic_attribution_class,
            exclusive_funding_class;
        """
    )
    print_rows("7. STATEWIDE RECONCILIATION DETAIL", columns, rows)

    cur.close()
    conn.close()

    print()
    print("=" * 112)
    print("VALIDATION COMPLETE")
    print("=" * 112)


if __name__ == "__main__":
    main()