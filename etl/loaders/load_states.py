from pathlib import Path

import pandas as pd
import psycopg2

from etl.utils.download import download_file

# Census state reference file
URL = "https://www2.census.gov/geo/docs/reference/state.txt"
LOCAL_FILE = Path("data/raw/reference/census/state.txt")


def get_connection():
    # Adjust if your password/user differs
    return psycopg2.connect(
        dbname="wcffbp",
        user="postgres",
        password="Bl@Rg2!!^99",
        host="localhost",
        port="5432",
    )


def load_states():
    # 1. Download
    file_path = download_file(URL, LOCAL_FILE)

    # 2. Read
    df = pd.read_csv(file_path, sep="|")

    # 3. Clean columns
    df = df.rename(columns={
        "STATE": "state_fips",
        "STUSAB": "state_abbreviation",
        "STATE_NAME": "state_name"
    })

    df = df[["state_fips", "state_abbreviation", "state_name"]]

    print(f"Loaded {len(df)} states")

    # 4. Insert into DB
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE SCHEMA IF NOT EXISTS reference;

        CREATE TABLE IF NOT EXISTS reference.state_registry (
            state_fips INTEGER PRIMARY KEY,
            state_abbreviation TEXT,
            state_name TEXT
        );
    """)

    # Clear table (idempotent load)
    cur.execute("DELETE FROM reference.state_registry;")

    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO reference.state_registry (state_fips, state_abbreviation, state_name)
            VALUES (%s, %s, %s);
        """, (row.state_fips, row.state_abbreviation, row.state_name))

    conn.commit()
    cur.close()
    conn.close()

    print("States loaded successfully into PostgreSQL.")


if __name__ == "__main__":
    load_states()
    