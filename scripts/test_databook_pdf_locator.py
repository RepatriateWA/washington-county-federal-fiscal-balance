from pathlib import Path

from etl.pdf.databook import print_table_pages

pdf_file = Path("data/raw/irs_databook/2020/irs_databook_2020.pdf")

print_table_pages(pdf_file, 5)
print_table_pages(pdf_file, 8)