import argparse
from pathlib import Path

from etl.common.db import get_connection


def run_sql_file(sql_file: Path):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(sql_file.read_text())

    conn.commit()
    cur.close()
    conn.close()

    print(f"Executed {sql_file}")


def main():
    parser = argparse.ArgumentParser(description="Run a SQL file.")
    parser.add_argument("sql_file", type=Path)

    args = parser.parse_args()
    run_sql_file(args.sql_file)


if __name__ == "__main__":
    main()