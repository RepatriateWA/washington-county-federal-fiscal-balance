from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from etl.common.db import get_connection

def print_rows(title, columns, rows):
    print()
    print("=" * 88)
    print(title)
    print("=" * 88)

    if not rows:
        print("(no rows)")
        return

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
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    return columns, rows


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 88)
    print("AP-001A — CERTIFIED ASSISTANCE LEDGER VALIDATION")
    print("=" * 88)

    # 1. Row-count reconciliation
    columns, rows = fetch(
        cur,
        """
        SELECT
            (SELECT COUNT(*)
             FROM assistance.award_transaction)
                AS source_transactions,

            (SELECT COUNT(*)
             FROM analysis.v_certified_assistance_ledger)
                AS ledger_rows,

            (SELECT COUNT(*)
             FROM analysis.v_certified_assistance_ledger)
            -
            (SELECT COUNT(*)
             FROM assistance.award_transaction)
                AS row_difference;
        """,
    )
    print_rows(
        "1. TRANSACTION ROW RECONCILIATION",
        columns,
        rows,
    )

    # 2. Transaction-key uniqueness
    columns, rows = fetch(
        cur,
        """
        SELECT COUNT(*) AS duplicate_transaction_key_groups
        FROM (
            SELECT
                assistance_transaction_unique_key
            FROM analysis.v_certified_assistance_ledger
            GROUP BY assistance_transaction_unique_key
            HAVING COUNT(*) <> 1
        ) q;
        """,
    )
    print_rows(
        "2. TRANSACTION KEY UNIQUENESS",
        columns,
        rows,
    )

    # 3. Transaction-ID uniqueness
    columns, rows = fetch(
        cur,
        """
        SELECT COUNT(*) AS duplicate_transaction_id_groups
        FROM (
            SELECT
                assistance_transaction_id
            FROM analysis.v_certified_assistance_ledger
            GROUP BY assistance_transaction_id
            HAVING COUNT(*) <> 1
        ) q;
        """,
    )
    print_rows(
        "3. TRANSACTION ID UNIQUENESS",
        columns,
        rows,
    )

    # 4. Obligation reconciliation
    columns, rows = fetch(
        cur,
        """
        SELECT
            s.source_obligation,
            l.ledger_obligation,
            l.ledger_obligation - s.source_obligation
                AS obligation_difference
        FROM (
            SELECT
                COALESCE(
                    SUM(federal_action_obligation),
                    0
                ) AS source_obligation
            FROM assistance.award_transaction
        ) s
        CROSS JOIN (
            SELECT
                COALESCE(
                    SUM(federal_action_obligation),
                    0
                ) AS ledger_obligation
            FROM analysis.v_certified_assistance_ledger
        ) l;
        """,
    )
    print_rows(
        "4. FEDERAL ACTION OBLIGATION RECONCILIATION",
        columns,
        rows,
    )

    # 5. Fiscal-year reconciliation
    columns, rows = fetch(
        cur,
        """
        SELECT
            COALESCE(
                s.action_date_fiscal_year,
                l.action_date_fiscal_year
            ) AS fiscal_year,

            COALESCE(s.source_rows, 0)
                AS source_rows,

            COALESCE(l.ledger_rows, 0)
                AS ledger_rows,

            COALESCE(l.ledger_rows, 0)
            -
            COALESCE(s.source_rows, 0)
                AS row_difference,

            COALESCE(s.source_obligation, 0)
                AS source_obligation,

            COALESCE(l.ledger_obligation, 0)
                AS ledger_obligation,

            COALESCE(l.ledger_obligation, 0)
            -
            COALESCE(s.source_obligation, 0)
                AS obligation_difference

        FROM (
            SELECT
                action_date_fiscal_year,
                COUNT(*) AS source_rows,
                COALESCE(
                    SUM(federal_action_obligation),
                    0
                ) AS source_obligation
            FROM assistance.award_transaction
            GROUP BY action_date_fiscal_year
        ) s

        FULL OUTER JOIN (
            SELECT
                action_date_fiscal_year,
                COUNT(*) AS ledger_rows,
                COALESCE(
                    SUM(federal_action_obligation),
                    0
                ) AS ledger_obligation
            FROM analysis.v_certified_assistance_ledger
            GROUP BY action_date_fiscal_year
        ) l
          ON l.action_date_fiscal_year =
             s.action_date_fiscal_year

        ORDER BY fiscal_year;
        """,
    )
    print_rows(
        "5. FISCAL-YEAR RECONCILIATION",
        columns,
        rows,
    )

    # 6. DEFC profile
    columns, rows = fetch(
        cur,
        """
        SELECT
            COUNT(*) FILTER (
                WHERE defc_code_count > 0
            ) AS transactions_with_defc,

            COUNT(*) FILTER (
                WHERE defc_code_count > 1
            ) AS transactions_with_multiple_defc,

            COUNT(*) FILTER (
                WHERE is_extraordinary
            ) AS extraordinary_transactions,

            COUNT(*) FILTER (
                WHERE is_covid
            ) AS covid_transactions,

            COUNT(*) FILTER (
                WHERE is_iija
            ) AS iija_transactions

        FROM analysis.v_certified_assistance_ledger;
        """,
    )
    print_rows(
        "6. EXTRAORDINARY FUNDING PROFILE",
        columns,
        rows,
    )

    # 7. Geography profile
    columns, rows = fetch(
        cur,
        """
        SELECT
            COUNT(*) AS total_rows,

            COUNT(*) FILTER (
                WHERE place_of_performance_id IS NOT NULL
            ) AS rows_with_performance_place,

            COUNT(*) FILTER (
                WHERE reference_state_id IS NOT NULL
            ) AS rows_with_reference_state,

            COUNT(*) FILTER (
                WHERE reference_county_id IS NOT NULL
            ) AS rows_with_reference_county,

            COUNT(*) FILTER (
                WHERE place_source_condition IS NOT NULL
            ) AS rows_with_place_source_condition

        FROM analysis.v_certified_assistance_ledger;
        """,
    )
    print_rows(
        "7. PLACE-OF-PERFORMANCE GEOGRAPHY PROFILE",
        columns,
        rows,
    )

    cur.close()
    conn.close()

    print()
    print("=" * 88)
    print("VALIDATION COMPLETE")
    print("=" * 88)


if __name__ == "__main__":
    main()