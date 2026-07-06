from pathlib import Path

from etl.pdf.databook import extract_table5_dataframe

pdf_file = Path("data/raw/irs_databook/2020/irs_databook_2020.pdf")

df = extract_table5_dataframe(pdf_file)

print(df.shape)

print(df[df["state_name"].isin(["United States, total", "Louisiana", "Washington"])].to_string(index=False))