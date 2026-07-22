"""Inspect existing database objects relevant to EP-004 procurement design."""

from __future__ import annotations

import sys

from etl.db import get_connection


TARGET_OBJECTS = (
    ("expenditure", "data_source"),
    ("expenditure", "program"),
    ("expenditure", "payment"),
    ("reference", "federal_agency"),
    ("reference", "federal_program"),
)


def print_columns(cursor, schema_name: str, table_name: str) -> None:
    cursor.execute(
        """
        SELECT
            ordinal_position,
            column_name,
            data_type,
            udt_name,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
        """,
        (schema_name, table_name),
    )

    rows = cursor.fetchall()

    print(f"\nCOLUMNS: {schema_name}.{table_name}")
    print("-" * 100)

    if not rows:
        print("No columns found.")
        return

    for (
        position,
        column_name,
        data_type,
        udt_name,
        is_nullable,
        column_default,
    ) in rows:
        print(
            f"{position:>2}. "
            f"{column_name:<32} "
            f"type={data_type:<28} "
            f"udt={udt_name:<16} "
            f"nullable={is_nullable:<3} "
            f"default={column_default}"
        )


def print_constraints(cursor, schema_name: str, table_name: str) -> None:
    cursor.execute(
        """
        SELECT
            con.conname,
            CASE con.contype
                WHEN 'p' THEN 'PRIMARY KEY'
                WHEN 'u' THEN 'UNIQUE'
                WHEN 'f' THEN 'FOREIGN KEY'
                WHEN 'c' THEN 'CHECK'
                WHEN 'x' THEN 'EXCLUSION'
                ELSE con.contype::text
            END AS constraint_type,
            pg_get_constraintdef(con.oid, true) AS definition
        FROM pg_catalog.pg_constraint AS con
        JOIN pg_catalog.pg_class AS cls
          ON cls.oid = con.conrelid
        JOIN pg_catalog.pg_namespace AS ns
          ON ns.oid = cls.relnamespace
        WHERE ns.nspname = %s
          AND cls.relname = %s
        ORDER BY constraint_type, con.conname;
        """,
        (schema_name, table_name),
    )

    rows = cursor.fetchall()

    print(f"\nCONSTRAINTS: {schema_name}.{table_name}")
    print("-" * 100)

    if not rows:
        print("No constraints found.")
        return

    for constraint_name, constraint_type, definition in rows:
        print(f"{constraint_type:<14} {constraint_name}")
        print(f"  {definition}")


def print_indexes(cursor, schema_name: str, table_name: str) -> None:
    cursor.execute(
        """
        SELECT
            indexname,
            indexdef
        FROM pg_catalog.pg_indexes
        WHERE schemaname = %s
          AND tablename = %s
        ORDER BY indexname;
        """,
        (schema_name, table_name),
    )

    rows = cursor.fetchall()

    print(f"\nINDEXES: {schema_name}.{table_name}")
    print("-" * 100)

    if not rows:
        print("No indexes found.")
        return

    for index_name, index_definition in rows:
        print(index_name)
        print(f"  {index_definition}")


def print_row_count(cursor, schema_name: str, table_name: str) -> None:
    # Object names come only from the fixed TARGET_OBJECTS constant.
    cursor.execute(
        f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}";'
    )
    row_count = cursor.fetchone()[0]
    print(f"\nROW COUNT: {schema_name}.{table_name} = {row_count:,}")


def print_sample_rows(cursor, schema_name: str, table_name: str) -> None:
    cursor.execute(
        f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT 5;'
    )

    rows = cursor.fetchall()
    column_names = [description.name for description in cursor.description]

    print(f"\nSAMPLE: {schema_name}.{table_name}")
    print("-" * 100)
    print(column_names)

    if not rows:
        print("No rows found.")
        return

    for row in rows:
        print(row)


def main() -> int:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                for schema_name, table_name in TARGET_OBJECTS:
                    print("\n" + "=" * 110)
                    print(f"{schema_name}.{table_name}")
                    print("=" * 110)

                    print_columns(cursor, schema_name, table_name)
                    print_constraints(cursor, schema_name, table_name)
                    print_indexes(cursor, schema_name, table_name)
                    print_row_count(cursor, schema_name, table_name)
                    print_sample_rows(cursor, schema_name, table_name)

        return 0

    except Exception as exc:
        print(f"Inspection failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())