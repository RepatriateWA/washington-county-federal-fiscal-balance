"""Inventory database objects potentially relevant to EP-004 procurement."""

from __future__ import annotations

import sys

from psycopg2 import sql

from etl.db import get_connection


TARGET_SCHEMAS = (
    "procurement",
    "usaspending",
    "expenditure",
    "reporting",
    "reference",
)


def main() -> int:
    query = """
        SELECT
            n.nspname AS schema_name,
            c.relname AS object_name,
            CASE c.relkind
                WHEN 'r' THEN 'table'
                WHEN 'p' THEN 'partitioned table'
                WHEN 'v' THEN 'view'
                WHEN 'm' THEN 'materialized view'
                WHEN 'S' THEN 'sequence'
                ELSE c.relkind::text
            END AS object_type
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n
          ON n.oid = c.relnamespace
        WHERE n.nspname = ANY(%s)
           OR c.relname ILIKE ANY(
                ARRAY[
                    '%%procurement%%',
                    '%%contract%%',
                    '%%award%%',
                    '%%usaspending%%',
                    '%%agency%%',
                    '%%naics%%'
                ]
           )
        ORDER BY n.nspname, c.relname;
    """

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (list(TARGET_SCHEMAS),))
                rows = cursor.fetchall()

        if not rows:
            print("No procurement-related database objects found.")
            return 0

        print("Procurement-related database objects")
        print("=" * 78)

        current_schema = None

        for schema_name, object_name, object_type in rows:
            if schema_name != current_schema:
                current_schema = schema_name
                print(f"\n[{schema_name}]")

            print(f"  {object_type:<20} {object_name}")

        print(f"\nObjects found: {len(rows)}")
        return 0

    except Exception as exc:
        print(f"Inventory failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())