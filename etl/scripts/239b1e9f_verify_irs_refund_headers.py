from pathlib import Path
from openpyxl import load_workbook

ROOT = Path(".")
TARGETS = {
    2020: "20dbs01t08rf.xlsx",
    2021: "21dbs01t08rf.xlsx",
    2022: "22dbs01t08rf.xlsx",
}

OUTPUT = Path("239b1e9f_refund_header_evidence.txt")

with OUTPUT.open("w", encoding="utf-8") as out:
    def emit(value=""):
        print(value, file=out)

    emit("ETL-239B1E9F - IRS REFUND HEADER VERIFICATION")
    emit("=" * 65)
    emit("READ ONLY - NO ACCOUNTING AUTHORIZATION")
    emit()

    for year, filename in TARGETS.items():
        matches = sorted(
            p for p in ROOT.rglob(filename)
            if ".venv" not in p.parts and ".git" not in p.parts
        )

        emit(f"FISCAL YEAR: {year}")
        emit(f"SOURCE FILE: {filename}")
        emit(f"MATCHES: {len(matches)}")

        if len(matches) != 1:
            emit("STATUS: SOURCE NOT UNIQUELY LOCATED")
            emit()
            continue

        path = matches[0]
        emit(f"PATH: {path}")

        wb = load_workbook(path, read_only=False, data_only=True)

        try:
            emit(f"WORKSHEETS: {wb.sheetnames}")

            candidates = [
                ws for ws in wb.worksheets
                if "table 8" in ws.title.lower()
                or "table8" in ws.title.lower().replace(" ", "")
            ]

            if not candidates:
                emit("STATUS: TABLE 8 SHEET NOT FOUND")
                emit()
                continue

            for ws in candidates:
                emit(f"WORKSHEET: {ws.title}")
                emit("MERGED RANGES:")
                for rng in ws.merged_cells.ranges:
                    if rng.min_row <= 12:
                        emit(f"  {rng}")

                emit("HEADER AND FOOTNOTE REGION: ROWS 1-12")
                for row in ws.iter_rows(
                    min_row=1, max_row=12,
                    min_col=1, max_col=16
                ):
                    values = [
                        f"{cell.coordinate}={str(cell.value)!r}"
                        for cell in row
                        if cell.value is not None
                    ]
                    if values:
                        emit(" | ".join(values))

                wa_row = 54
                emit(f"WASHINGTON SOURCE ROW: {wa_row}")
                for row in ws.iter_rows(
                    min_row=wa_row, max_row=wa_row,
                    min_col=1, max_col=16
                ):
                    emit(" | ".join(
                        f"{cell.coordinate}={str(cell.value)!r}"
                        for cell in row
                        if cell.value is not None
                    ))

            emit()
        finally:
            wb.close()

    emit("No database changes.")
    emit("No ledger authorization.")

print(f"Report written: {OUTPUT}")