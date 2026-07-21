from __future__ import annotations

from etl.db import get_connection


TARGET_VIEWS = (
    ("reporting", "v_federal_expenditures_by_county_year"),
    ("reporting", "v_federal_expenditures_by_state_year"),
    ("reporting", "v_medicare_expenditures_by_county_year"),
    ("reporting", "v_medicare_expenditures_by_state_year"),
    ("reporting", "v_washington_medicaid_expenditures"),
    ("reporting", "v_washington_ssa_summary"),
    ("reporting", "v_washington_tracked_expenditures"),
)


def main() -> None:
    sql = """
        SELECT pg_get_viewdef(%s::regclass, true);
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for schema_name, view_name in TARGET_VIEWS:
                qualified_name = f"{schema_name}.{view_name}"

                print("=" * 100)
                print(qualified_name)
                print("=" * 100)

                try:
                    cursor.execute(sql, (qualified_name,))
                    row = cursor.fetchone()
                    print(row[0] if row else "View definition not found.")
                except Exception as exc:
                    connection.rollback()
                    print(f"ERROR: {exc}")

                print()


if __name__ == "__main__":
    main()