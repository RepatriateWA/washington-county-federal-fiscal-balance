from pathlib import Path
import openpyxl
import xlrd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/raw/irs/gross_collections/source"
OUTPUT = ROOT / "239b1e6c_irs_collections_notes.txt"

lines = [
    "ETL-239B1E6C - IRS GROSS COLLECTIONS SOURCE NOTES",
    "READ ONLY - NO DATABASE OR LEDGER WRITES",
    "=" * 90,
]

def clean(value):
    if value is None:
        return ""
    return " ".join(str(value).split())

for year in range(2018, 2025):
    matches = sorted(SOURCE.glob(
        f"irs_data_book_{year}_table_1_5_*"
    ))

    lines.append("")
    lines.append(f"FISCAL YEAR {year}")

    if len(matches) != 1:
        lines.append(
            f"EXPECTED ONE WORKBOOK; FOUND {len(matches)}"
        )
        continue

    path = matches[0]
    lines.append(f"FILE: {path.relative_to(ROOT)}")

    try:
        if path.suffix.lower() == ".xls":
            book = xlrd.open_workbook(str(path))
            sheets = [
                (
                    book.sheet_by_index(i).name,
                    [
                        book.sheet_by_index(i).row_values(j)
                        for j in range(
                            book.sheet_by_index(i).nrows
                        )
                    ]
                )
                for i in range(book.nsheets)
            ]
        else:
            book = openpyxl.load_workbook(
                path, read_only=True, data_only=True
            )
            sheets = [
                (ws.title, list(ws.values))
                for ws in book.worksheets
            ]

        for sheet_name, rows in sheets:
            lines.append(f"SHEET: {sheet_name}")
            n = len(rows)
            selected = sorted(
                set(range(min(20, n))) |
                set(range(max(0, n - 18), n))
            )

            for i in selected:
                cells = [
                    clean(v)
                    for v in rows[i]
                    if clean(v)
                ]
                if cells:
                    lines.append(
                        f"ROW {i + 1}: " +
                        " | ".join(cells[:8])[:1000]
                    )

    except Exception as exc:
        lines.append(
            f"READ ERROR: {type(exc).__name__}: {exc}"
        )

OUTPUT.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8"
)

print(f"Written: {OUTPUT}")