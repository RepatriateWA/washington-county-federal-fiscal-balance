from pathlib import Path
import csv
import traceback

try:
    root = Path("accounting_registry/v0_3_3_working")

    for name in [
        "annual_accounting_matrix.csv",
        "canonical_annual_ledger.csv",
        "evidence_crosswalk.csv"
    ]:
        path = root / name

        print(f"\nFILE: {name}", flush=True)

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            print("COLUMNS:", reader.fieldnames, flush=True)
            rows = list(reader)
            print("ROWS:", len(rows), flush=True)

            if name == "evidence_crosswalk.csv":
                print("LAST THREE RECORDS:", flush=True)
                for row in rows[-3:]:
                    print(row, flush=True)

    print("\nETL-235D3 PASS", flush=True)

except BaseException:
    traceback.print_exc(file=__import__("sys").stdout)
    raise SystemExit(1)
