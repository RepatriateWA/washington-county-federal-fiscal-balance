from pathlib import Path
import openpyxl
import xlrd

root = Path(__file__).resolve().parents[2]
source = root / "data/raw/irs/gross_collections/source"
output = root / "239b1e6d_irs_definition_check.txt"

terms = (
    "gross collections less refunds",
    "net collections",
    "gross collections include",
    "refund data",
    "collection and refund data",
    "classification by state",
)

lines = [
    "ETL-239B1E6D - IRS SEVEN-YEAR DEFINITION CHECK",
    "READ ONLY - NO DATABASE OR LEDGER WRITES",
    "=" * 78,
]

for year in range(2018, 2025):
    files = list(source.glob(
        f"irs_data_book_{year}_table_1_5_*"
    ))
    lines.append(f"\nFY{year}")

    if len(files) != 1:
        lines.append(f"SOURCE COUNT ERROR: {len(files)}")
        continue

    path = files[0]
    lines.append(f"FILE: {path.name}")
    hits = 0

    if path.suffix.lower() == ".xls":
        book = xlrd.open_workbook(str(path))
        sheets = [
            (
                book.sheet_by_index(i).name,
                (
                    (j + 1, book.sheet_by_index(i).row_values(j))
                    for j in range(book.sheet_by_index(i).nrows)
                )
            )
            for i in range(book.nsheets)
        ]
    else:
        book = openpyxl.load_workbook(
            path, read_only=True, data_only=True
        )
        sheets = [
            (
                ws.title,
                enumerate(ws.values, start=1)
            )
            for ws in book.worksheets
        ]

    for sheet_name, rows in sheets:
        for row_number, values in rows:
            for column, value in enumerate(values, start=1):
                if not isinstance(value, str):
                    continue
                normalized = " ".join(value.split())
                if any(term in normalized.lower() for term in terms):
                    hits += 1
                    lines.append(
                        f"{sheet_name} R{row_number} "
                        f"C{column}: {normalized}"
                    )

    lines.append(f"MATCHED CELLS: {hits}")

output.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8"
)

print(f"Report written: {output}")