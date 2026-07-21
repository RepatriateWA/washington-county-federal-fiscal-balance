from __future__ import annotations

from etl.db import get_connection


SEARCH_TERMS = (
    "medicare",
    "medicaid",
    "chip",
    "ssa",
    "oasdi",
    "cms",
    "benefit",
    "expenditure",
    "payment",
)


def main() -> None:
    sql = """
        SELECT
            t.table_schema,
            t.table_name,
            t.table_type
        FROM information_schema.tables AS t
        WHERE t.table_schema NOT IN (
            'information_schema',
            'pg_catalog'
        )
          AND (
                LOWER(t.table_schema) LIKE ANY(%s)
             OR LOWER(t.table_name) LIKE ANY(%s)
          )
        ORDER BY
            t.table_schema,
            t.table_name;
    """

    patterns = [f"%{term}%" for term in SEARCH_TERMS]

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, (patterns, patterns))
            rows = cursor.fetchall()

    if not rows:
        print("No matching tables or views found.")
        return

    print("POTENTIAL FEDERAL EXPENDITURE SOURCES")
    print("=" * 88)

    for table_schema, table_name, table_type in rows:
        print(
            f"{table_schema:<24} "
            f"{table_name:<48} "
            f"{table_type}"
        )


if __name__ == "__main__":
    main()