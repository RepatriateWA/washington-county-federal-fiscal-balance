from __future__ import annotations

from etl.db import get_connection


TARGET_SCHEMAS = (
    "ssa",
    "chip",
    "cms",
    "expenditure",
    "reporting",
)


def main() -> None:
    sql = """
        SELECT
            c.table_schema,
            c.table_name,
            t.table_type,
            c.ordinal_position,
            c.column_name,
            c.data_type
        FROM information_schema.columns AS c
        JOIN information_schema.tables AS t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
        WHERE c.table_schema = ANY(%s)
        ORDER BY
            c.table_schema,
            c.table_name,
            c.ordinal_position;
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, (list(TARGET_SCHEMAS),))
            rows = cursor.fetchall()

    if not rows:
        print("No matching expenditure tables or views were found.")
        return

    current_object = None

    for (
        table_schema,
        table_name,
        table_type,
        ordinal_position,
        column_name,
        data_type,
    ) in rows:
        object_name = f"{table_schema}.{table_name}"

        if object_name != current_object:
            if current_object is not None:
                print()

            print("=" * 88)
            print(f"{object_name} [{table_type}]")
            print("=" * 88)
            current_object = object_name

        print(
            f"{ordinal_position:>3}  "
            f"{column_name:<42} "
            f"{data_type}"
        )


if __name__ == "__main__":
    main()