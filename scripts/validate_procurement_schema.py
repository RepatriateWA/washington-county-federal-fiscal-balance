"""Validate the database objects created by Migration 108."""

from __future__ import annotations

import sys

from etl.common.db import get_connection


EXPECTED_TABLES = {
    "load_batch",
    "recipient",
    "naics",
    "psc",
    "award",
    "award_transaction",
    "place_of_performance",
    "raw_award_transaction",
}


def main() -> int:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'procurement'
                      AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                    """
                )
                actual_tables = {row[0] for row in cursor.fetchall()}

                cursor.execute(
                    """
                    SELECT
                        tc.table_name,
                        COUNT(*) AS foreign_key_count
                    FROM information_schema.table_constraints AS tc
                    WHERE tc.table_schema = 'procurement'
                      AND tc.constraint_type = 'FOREIGN KEY'
                    GROUP BY tc.table_name
                    ORDER BY tc.table_name;
                    """
                )
                foreign_keys = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT
                        tablename,
                        indexname
                    FROM pg_catalog.pg_indexes
                    WHERE schemaname = 'procurement'
                    ORDER BY tablename, indexname;
                    """
                )
                indexes = cursor.fetchall()

        missing_tables = EXPECTED_TABLES - actual_tables
        unexpected_tables = actual_tables - EXPECTED_TABLES

        print("Migration 108 — Procurement Schema Validation")
        print("=" * 72)

        print("\nTables found:")
        for table_name in sorted(actual_tables):
            print(f"  {table_name}")

        if missing_tables:
            print("\nMissing tables:")
            for table_name in sorted(missing_tables):
                print(f"  {table_name}")

        if unexpected_tables:
            print("\nAdditional procurement tables:")
            for table_name in sorted(unexpected_tables):
                print(f"  {table_name}")

        print("\nForeign keys:")
        if foreign_keys:
            for table_name, count in foreign_keys:
                print(f"  {table_name:<28} {count}")
        else:
            print("  None found")

        print(f"\nIndexes found: {len(indexes)}")

        if missing_tables:
            print("\nVALIDATION FAILED")
            return 1

        print("\nVALIDATION PASSED")
        return 0

    except Exception as exc:
        print(f"Validation failed with an exception: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())