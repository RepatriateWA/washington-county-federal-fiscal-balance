from pathlib import Path

import pandas as pd

from etl.loaders.load_states import get_connection
from etl.utils.download import download_file

URL = "https://www2.census.gov/geo/docs/reference/codes/files/national_county.txt"
LOCAL_FILE = Path("data/raw/reference/census/national_county.txt")


def load_counties():
    file_path = download_file(URL, LOCAL_FILE)

    df = pd.read_csv(
        file_path,
        sep=",",
        header=None,
        names=["state_abbreviation", "state_fips", "county_fips", "county_name", "classfp"],
        dtype=str,
    )

    wa = df[df["state_fips"] == "53"].copy()
    wa["full_fips"] = wa["state_fips"] + wa["county_fips"]
    wa["county_type"] = "county"

    print(f"Loaded {len(wa)} Washington counties")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM reference.county_registry
        WHERE state_id = 48;
    """)

    for _, row in wa.iterrows():
        cur.execute("""
            INSERT INTO reference.county_registry
                (state_id, county_fips, full_fips, county_name, county_type)
            VALUES
                (%s, %s, %s, %s, %s);
        """, (
            48,
            row.county_fips,
            row.full_fips,
            row.county_name,
            row.county_type,
        ))

    conn.commit()
    cur.close()
    conn.close()

    print("Washington counties loaded successfully into PostgreSQL.")


if __name__ == "__main__":
    load_counties()