from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from etl.common.db import get_connection


def print_rows(title, columns, rows):
    print()
    print("=" * 96)
    print(title)
    print("=" * 96)

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

    print("=" * 96)
    print("AP-001B — WASHINGTON TRANSACTION ATTRIBUTION VALIDATION")
    print("=" * 96)

    columns, rows = fetch(
        cur,
        """
        SELECT
            geographic_attribution_class,
            COUNT(*) AS transaction_count,
            SUM(federal_action_obligation) AS federal_action_obligation
        FROM analysis.v_assistance_geographic_attribution
        GROUP BY geographic_attribution_class
        ORDER BY geographic_attribution_class;
        """
    )
    print_rows("1. ATTRIBUTION CLASS SUMMARY", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT
            (SELECT COUNT(*)
             FROM analysis.v_certified_assistance_ledger)
                AS certified_rows,
            (SELECT COUNT(*)
             FROM analysis.v_assistance_geographic_attribution)
                AS attributed_rows,
            (SELECT COUNT(*)
             FROM analysis.v_assistance_geographic_attribution)
            -
            (SELECT COUNT(*)
             FROM analysis.v_certified_assistance_ledger)
                AS row_difference;
        """
    )
    print_rows("2. TRANSACTION COVERAGE", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT
            s.certified_obligation,
            a.attributed_obligation,
            a.attributed_obligation - s.certified_obligation
                AS obligation_difference
        FROM (
            SELECT COALESCE(SUM(federal_action_obligation), 0)
                AS certified_obligation
            FROM analysis.v_certified_assistance_ledger
        ) s
        CROSS JOIN (
            SELECT COALESCE(SUM(federal_action_obligation), 0)
                AS attributed_obligation
            FROM analysis.v_assistance_geographic_attribution
        ) a;
        """
    )
    print_rows("3. FINANCIAL RECONCILIATION", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT COUNT(*) AS unclassified_transactions
        FROM analysis.v_assistance_geographic_attribution
        WHERE geographic_attribution_class IS NULL;
        """
    )
    print_rows("4. ATTRIBUTION COMPLETENESS", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT COUNT(*) AS duplicate_transaction_groups
        FROM (
            SELECT assistance_transaction_id
            FROM analysis.v_assistance_geographic_attribution
            GROUP BY assistance_transaction_id
            HAVING COUNT(*) <> 1
        ) q;
        """
    )
    print_rows("5. ATTRIBUTION EXCLUSIVITY", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT COUNT(*) AS invalid_wa_county_transactions
        FROM analysis.v_assistance_geographic_attribution
        WHERE geographic_attribution_class = 'WA_COUNTY'
          AND (
              reference_state_abbreviation <> 'WA'
              OR reference_county_id IS NULL
          );
        """
    )
    print_rows("6. WA COUNTY INTEGRITY", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT COUNT(*) AS invalid_wa_unspecified_transactions
        FROM analysis.v_assistance_geographic_attribution
        WHERE geographic_attribution_class = 'WA_UNSPECIFIED'
          AND reference_county_id IS NOT NULL;
        """
    )
    print_rows("7. WA UNSPECIFIED INTEGRITY", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT
            COUNT(*) AS conflict_transactions,
            SUM(federal_action_obligation) AS conflict_obligation
        FROM analysis.v_wa_geography_conflicts;
        """
    )
    print_rows("8. GEOGRAPHY CONFLICT PROFILE", columns, rows)

    columns, rows = fetch(
        cur,
        """
        SELECT
            action_date_fiscal_year AS fiscal_year,
            geographic_attribution_class,
            COUNT(*) AS transaction_count,
            SUM(federal_action_obligation) AS obligation
        FROM analysis.v_assistance_geographic_attribution
        GROUP BY
            action_date_fiscal_year,
            geographic_attribution_class
        ORDER BY
            action_date_fiscal_year,
            geographic_attribution_class;
        """
    )
    print_rows("9. FISCAL YEAR BY ATTRIBUTION CLASS", columns, rows)

    cur.close()
    conn.close()

    print()
    print("=" * 96)
    print("VALIDATION COMPLETE")
    print("=" * 96)


if __name__ == "__main__":
    main()