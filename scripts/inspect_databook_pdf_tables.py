from pathlib import Path
import pdfplumber

PDF_FILE = Path("data/raw/irs_databook/2020/irs_databook_2020.pdf")

with pdfplumber.open(PDF_FILE) as pdf:
    print(f"Pages: {len(pdf.pages)}")

    for i, page in enumerate(pdf.pages, start=1):
        text = page.extract_text() or ""

        if "Table 5" in text or "Gross Collections, by Type of Tax and State" in text:
            print("=" * 80)
            print(f"Possible Table 5 page: {i}")
            print("=" * 80)
            print(text[:2000])