from pathlib import Path

from etl.pdf.databook import extract_table_text, parse_table5_first_half

pdf_file = Path("data/raw/irs_databook/2020/irs_databook_2020.pdf")

text = extract_table_text(pdf_file, 5)
rows = parse_table5_first_half(text)

for row in rows:
    if row["state_name"] in {"Washington", "Louisiana", "United States, total"}:
        print(row)

print(f"Rows parsed: {len(rows)}")