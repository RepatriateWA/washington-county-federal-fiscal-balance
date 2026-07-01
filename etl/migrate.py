from pathlib import Path
from psycopg import connect

from config import DB_CONFIG

MIGRATIONS_DIR = Path(__file__).parent.parent / "database" / "migrations"


def run_migrations():
    conn = connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        dbname=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )

    try:
        with conn:
            with conn.cursor() as cur:
                for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                    print(f"Running {migration.name}...")

                    sql = migration.read_text(encoding="utf-8")
                    cur.execute(sql)

                    print(f"✓ {migration.name} completed")

        print("\nAll migrations completed successfully.")

    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()