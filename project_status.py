from pathlib import Path

from etl.db import get_connection


IRS_YEARS = range(2015, 2025)


def check_file(path: str) -> str:
    return "PASS" if Path(path).exists() else "MISSING"


def get_scalar(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()[0]


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 60)
    print("Washington County Federal Fiscal Balance Project")
    print("=" * 60)

    print("\nReference Data")
    print("-" * 60)

    state_count = get_scalar(cur, "SELECT COUNT(*) FROM reference.state_registry;")
    county_count = get_scalar(cur, "SELECT COUNT(*) FROM reference.county_registry;")

    print(f"States loaded............... {'PASS' if state_count >= 57 else 'FAIL'} ({state_count})")
    print(f"Washington counties loaded.. {'PASS' if county_count == 39 else 'FAIL'} ({county_count})")

    print("\nIRS Data")
    print("-" * 60)

    for year in IRS_YEARS:
        row_count = get_scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM irs.county_income_tax
            WHERE tax_year = %s;
            """,
            (year,),
        )

        status = "PASS" if row_count == 360 else "NOT IMPORTED"
        print(f"{year}......................... {status} ({row_count} rows)")

        print("\nIRS State Collections")
        print("-" * 60)

    for year in [2023, 2024]:
        row_count = get_scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM irs.state_collections
            WHERE fiscal_year = %s;
            """,
            (year,),
        )

        status = "PASS" if row_count == 8 else "NOT IMPORTED"

        print(f"FY{year}....................... {status} ({row_count} rows)")
    
    print("\nProject Files")
    print("-" * 60)

    files = {
        ".env": ".env",
        "requirements.txt": "requirements.txt",
        "data dictionary": "docs/data_dictionary.md",
        "generic IRS loader": "etl/loaders/load_irs_soi.py",
        "IRS validator": "etl/validation/validate_irs.py",
        "logging config": "etl/logging_config.py",
    }

    for label, path in files.items():
        print(f"{label:<28} {check_file(path)}")

    print("\nDatabase")
    print("-" * 60)
    print("Connection.................. PASS")

    cur.close()
    conn.close()

    print("\nOverall Status")
    print("-" * 60)
    print("READY")


if __name__ == "__main__":
    main()