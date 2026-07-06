from pathlib import Path
import pandas as pd

from etl.db import get_connection
from etl.utils.irs_header_scanner import find_amount_column

IRS_FILES = [
    (2015, Path("data/raw/irs/irs_soi_wa_2015.xls")),
    (2016, Path("data/raw/irs/irs_soi_wa_2016.xls")),
    (2017, Path("data/raw/irs/irs_soi_wa_2017.xlsx")),
    (2018, Path("data/raw/irs/irs_soi_wa_2018.xlsx")),
    (2019, Path("data/raw/irs/irs_soi_wa_2019.xlsx")),
    (2020, Path("data/raw/irs/irs_soi_wa_2020.xlsx")),
    (2021, Path("data/raw/irs/irs_soi_wa_2021.xlsx")),
    (2022, Path("data/raw/irs/irs_soi_wa_2022.xlsx")),
]

print("=" * 110)
print("WASHINGTON STATE - ESTIMATED FEDERAL TAXES PAID")
print("=" * 110)
print()
print(f"{'Year':<8}{'Measure':<45}{'Amount ($)':>25}")
print("-" * 110)

for year, path in IRS_FILES:
    df = pd.read_excel(path, sheet_name=0, header=None)
    col = find_amount_column(df, "Total tax liability")
    amount_thousands = df.iloc[6, col]
    print(
        f"{year:<8}"
        f"{'Total Tax Liability (IRS SOI)':<45}"
        f"{amount_thousands * 1000:>25,.0f}"
    )

conn = get_connection()
cur = conn.cursor()

cur.execute("""
SELECT fiscal_year, gross_collections_thousands
FROM irs.state_collections
WHERE tax_category = 'Total [1]'
ORDER BY fiscal_year;
""")

for year, amount_thousands in cur.fetchall():
    print(
        f"{year:<8}"
        f"{'Gross IRS Collections':<45}"
        f"{amount_thousands * 1000:>25,.0f}"
    )

cur.close()
conn.close()