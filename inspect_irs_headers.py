import pandas as pd

file = "data/raw/irs/15incywa.xls"

df = pd.read_excel(file, sheet_name=0, header=None)

pd.set_option("display.max_columns", 40)
pd.set_option("display.width", 200)

print("\nRows 3 through 8:")
print(df.iloc[3:9, 0:25])

print("\nRows 3 through 8, columns 25 through 60:")
print(df.iloc[3:9, 25:60])