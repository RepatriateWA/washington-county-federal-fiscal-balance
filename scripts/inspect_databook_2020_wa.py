from pathlib import Path
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 400)

file = Path("data/raw/irs_databook/2020/table_5_gross_collections.xlsx")

df = pd.read_excel(file, header=None)

# Find the Washington row
wa = df[df.iloc[:,0].astype(str).str.strip() == "Washington"]

print("Washington row index:")
print(wa.index)

print("\nWashington row:")
print(wa.T)