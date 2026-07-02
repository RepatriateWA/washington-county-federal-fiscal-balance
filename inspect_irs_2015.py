import pandas as pd

file = "data/raw/irs/15incywa.xls"

xls = pd.ExcelFile(file)

print("\nWorksheets:\n")

for sheet in xls.sheet_names:
    print(sheet)

print("\nPreview first sheet:\n")

df = pd.read_excel(file, sheet_name=0, header=None)

print(df.head(25))