from pathlib import Path

from etl.pdf.databook import extract_table_text

pdf_file = Path("data/raw/irs_databook/2020/irs_databook_2020.pdf")

text = extract_table_text(pdf_file, 5)

print(text[:5000])