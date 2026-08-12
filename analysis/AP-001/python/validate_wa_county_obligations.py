from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from etl.common.db import get_connection


def print_rows(title, columns, rows):
    print()
    print("=" * 108)
    print(title)
    print("=" * 108)

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

    print("=" * 108)
    print("AP-001B.2 — WASHINGTON COUNTY OBLIGATION VALIDATION")
    print("=" * 108)

    # 1. County-year row profile
    columns, rows = fetch(
        cur,
        """
        SELECT
            COUNT(*) AS county_year_rows,
            COUNT(DISTINCT county_id) AS distinct_counties,
            COUNT(DISTINCT fiscal_year) AS distinct_fiscal_years
        FROM analysis.v_wa_county_obligations;
        """
    )
    print_rows("1. COUNTY-YEAR PROFILE", columns, rows)

    # 2. County transaction reconciliation
    columns, rows = fetch(
        cur,
        """
        SELECT
            s.source_transactions,
            v.summary_transactions,
            v.summary_transactions - s.source_transactions
                AS transaction_difference
        FROM (
            SELECT COUNT(*) AS source_transactions
            FROM analysis.v_wa_county_transactions
        ) s
        CROSS JOIN (
            SELECT COALESCE(SUM(transaction_count), 0)
                AS summary_transactions
            FROM analysis.v_wa_county_obligations
        ) v;
        """
    )
    print_rows("2. COUNTY TRANSACTION RECONCILIATION", columns, rows)

    # 3. County obligation reconciliation
    columns, rows = fetch(
        cur,
        """
        SELECT
            s.source_obligation,
            v.summary_obligation,
            v.summary_obligation - s.source_obligation
                AS obligation_difference
        FROM (
            SELECT COALESCE(SUM(federal_action_obligation), 0)
                AS source_obligation
            FROM analysis.v_wa_county_transactions
        ) s
        CROSS JOIN (
            SELECT COALESCE(SUM(federal_action_obligation), 0)
                AS summary_obligation
            FROM analysis.v_wa_county_obligations
        ) v;
        """
    )
    print_rows("3. COUNTY OBLIGATION RECONCILIATION", columns, rows)

    # 4. Fiscal-year reconciliation
    columns, rows = fetch(
        cur,
        """
        SELECT
            COALESCE(s.fiscal_year, v.fiscal_year) AS fiscal_year,
            COALESCE(s.source_transactions, 0) AS source_transactions,
            COALESCE(v.summary_transactions, 0) AS summary_transactions,
            COALESCE(v.summary_transactions, 0)
              - COALESCE(s.source_transactions, 0)
                AS transaction_difference,
            COALESCE(s.source_obligation, 0) AS source_obligation,
            COALESCE(v.summary_obligation, 0) AS summary_obligation,
            COALESCE(v.summary_obligation, 0)
              - COALESCE(s.source_obligation, 0)
                AS obligation_difference
        FROM (
            SELECT
                action_date_fiscal_year AS fiscal_year,
                COUNT(*) AS source_transactions,
                SUM(federal_action_obligation) AS source_obligation
            FROM analysis.v_wa_county_transactions
            GROUP BY action_date_fiscal_year
        ) s
        FULL OUTER JOIN (
            SELECT
                fiscal_year,
                SUM(transaction_count) AS summary_transactions,
                SUM(federal_action_obligation) AS summary_obligation
            FROM analysis.v_wa_county_obligations
            GROUP BY fiscal_year
        ) v
          ON v.fiscal_year = s.fiscal_year
        ORDER BY fiscal_year;
        """
    )
    print_rows("4. FISCAL-YEAR COUNTY RECONCILIATION", columns, rows)

    # 5. Component identity
    columns, rows = fetch(
        cur,
        """
        SELECT
            fiscal_year,
            SUM(federal_action_obligation) AS total_obligation,
            SUM(covid_obligation) AS covid_obligation,
            SUM(covid_excluded_obligation) AS covid_excluded_obligation,
            SUM(covid_obligation)
              + SUM(covid_excluded_obligation)
              - SUM(federal_action_obligation)
                AS covid_partition_difference
        FROM analysis.v_wa_county_obligations
        GROUP BY fiscal_year
        ORDER BY fiscal_year;
        """
    )
    print_rows("5. COVID PARTITION RECONCILIATION", columns, rows)

    # 6. Extraordinary decomposition
    columns, rows = fetch(
        cur,
        """
        SELECT
            fiscal_year,
            SUM(federal_action_obligation) AS total_obligation,
            SUM(covid_obligation) AS covid_obligation,
            SUM(iija_obligation) AS iija_obligation,
            SUM(other_extraordinary_obligation)
                AS other_extraordinary_obligation,
            SUM(ordinary_obligation) AS ordinary_obligation,
            (
                SUM(covid_obligation)
                + SUM(iija_obligation)
                + SUM(other_extraordinary_obligation)
                + SUM(ordinary_obligation)
                - SUM(federal_action_obligation)
            ) AS decomposition_difference
        FROM analysis.v_wa_county_obligations
        GROUP BY fiscal_year
        ORDER BY fiscal_year;
        """
    )
    print_rows("6. EXTRAORDINARY FUNDING DECOMPOSITION", columns, rows)

    # 7. Statewide reconciliation
    columns, rows = fetch(
        cur,
        """
        SELECT
            fiscal_year,
            SUM(transaction_count) AS transaction_count,
            SUM(federal_action_obligation) AS obligation
        FROM analysis.v_wa_obligation_reconciliation
        GROUP BY fiscal_year
        ORDER BY fiscal_year;
        """
    )
    print_rows("7. STATEWIDE ATTRIBUTION RECONCILIATION", columns, rows)

    # 8. Reconciliation by class
    columns, rows = fetch(
        cur,
        """
        SELECT
            fiscal_year,
            geographic_attribution_class,
            transaction_count,
            federal_action_obligation
        FROM analysis.v_wa_obligation_reconciliation
        ORDER BY fiscal_year, geographic_attribution_class;
        """
    )
    print_rows("8. RECONCILIATION BY ATTRIBUTION CLASS", columns, rows)

    # 9. County coverage by year
    columns, rows = fetch(
        cur,
        """
        SELECT
            fiscal_year,
            COUNT(DISTINCT county_id) AS counties_present
        FROM analysis.v_wa_county_obligations
        GROUP BY fiscal_year
        ORDER BY fiscal_year;
        """
    )
    print_rows("9. COUNTY COVERAGE BY FISCAL YEAR", columns, rows)

    cur.close()
    conn.close()

    print()
    print("=" * 108)
    print("VALIDATION COMPLETE")
    print("=" * 108)


if __name__ == "__main__":
    main()