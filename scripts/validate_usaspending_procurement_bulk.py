import argparse
import csv
import hashlib
import io
import zipfile
from collections import Counter
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fiscal-year", type=int, required=True)
    args = parser.parse_args()

    fy = args.fiscal_year
    root = Path("data/raw/usaspending/procurement") / f"FY{fy}" / "api_bulk"

    archives = sorted(root.rglob("*.zip"))
    if not archives:
        raise SystemExit(f"FAIL: No ZIP archives found under {root}")

    print("=" * 72)
    print(f"ETL-202B.3 — FY{fy} PROCUREMENT ARCHIVE VALIDATION")
    print("READ ONLY — NO DATABASE WRITES")
    print("=" * 72)

    for archive in archives:
        print(f"\nArchive: {archive}")
        digest = hashlib.sha256()
        with archive.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        print(f"SHA-256: {digest.hexdigest()}")

        with zipfile.ZipFile(archive) as zf:
            bad_member = zf.testzip()
            if bad_member:
                raise SystemExit(f"FAIL: ZIP CRC error: {bad_member}")

            members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
            print(f"CSV members: {len(members)}")

            for member in members:
                with zf.open(member) as binary:
                    text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
                    reader = csv.DictReader(text)
                    fields = reader.fieldnames or []
                    print(f"\nMember: {member}")
                    print(f"Columns: {len(fields)}")

                    if len(fields) != 297:
                        print("WARNING: Column count differs from expected 297")

                    date_col = next(
                        (c for c in fields if c.lower() == "action_date"),
                        None
                    )
                    state_col = next(
                        (c for c in fields if c.lower() in (
                            "primary_place_of_performance_state_code",
                            "place_of_performance_state_code"
                        )),
                        None
                    )
                    award_col = next(
                        (c for c in fields if c.lower() in (
                            "award_type_code", "award_type"
                        )),
                        None
                    )

                    counts = Counter()
                    total = 0
                    first_bad_dates = []
                    states = Counter()
                    award_types = Counter()

                    start = f"{fy-1}-10-01"
                    end = f"{fy}-09-30"

                    for row in reader:
                        total += 1

                        if date_col:
                            value = (row.get(date_col) or "").strip()[:10]
                            if not (start <= value <= end):
                                counts["out_of_range_dates"] += 1
                                if len(first_bad_dates) < 5:
                                    first_bad_dates.append(value)

                        if state_col:
                            states[(row.get(state_col) or "").strip()] += 1

                        if award_col:
                            award_types[(row.get(award_col) or "").strip()] += 1

                    print(f"CSV data rows: {total:,}")
                    print(f"Action-date column: {date_col or 'NOT FOUND'}")
                    print(f"State column: {state_col or 'NOT FOUND'}")
                    print(f"Award-type column: {award_col or 'NOT FOUND'}")
                    print(f"Out-of-range dates: {counts['out_of_range_dates']:,}")
                    print(f"Sample out-of-range dates: {first_bad_dates}")
                    print(f"State distribution: {dict(states)}")
                    print(f"Award-type distribution: {dict(award_types)}")

                    if not date_col or not state_col or not award_col:
                        print("STATUS: REVIEW — one or more expected fields missing")
                    elif counts["out_of_range_dates"]:
                        print("STATUS: REVIEW — fiscal-year dates require investigation")
                    else:
                        print("STATUS: PRELIMINARY STRUCTURAL PASS")

    print("\nValidation finished. No PostgreSQL operations performed.")

if __name__ == "__main__":
    main()
