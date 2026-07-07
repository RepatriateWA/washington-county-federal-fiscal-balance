from pathlib import Path
import sys

from etl.loaders.load_irs_databook_table5 import load_irs_databook_table5
from etl.logging_config import get_logger

logger = get_logger(__name__)

DATA_BOOK_DIR = Path("data/raw/irs_databook")
YEARS = range(2015, 2025)


def find_source_file(year: int) -> Path | None:
    year_dir = DATA_BOOK_DIR / str(year)

    candidates = [
        year_dir / f"table_5_gross_collections.xlsx",
        year_dir / f"table_5_gross_collections.xls",
        year_dir / f"irs_databook_{year}.pdf",
    ]

    for path in candidates:
        if path.exists():
            return path

    return None


def main():
    print("=" * 60)
    print("IRS Data Book Table 5 Batch Import")
    print("=" * 60)

    results = []

    for year in YEARS:
        source_file = find_source_file(year)

        if source_file is None:
            print(f"{year}: MISSING source file")
            results.append((year, "MISSING", None))
            continue

        print(f"\nImporting FY{year} from {source_file}")

        try:
            load_irs_databook_table5(year, source_file)
            results.append((year, "PASS", None))
            print(f"FY{year}: PASS")

        except Exception as exc:
            logger.exception("Failed to import IRS Data Book Table 5 for FY%s", year)
            results.append((year, "FAIL", str(exc)))
            print(f"FY{year}: FAIL")

    print("\nSummary")
    print("-" * 60)

    failures = 0

    for year, status, error in results:
        print(f"{year}: {status}")

        if status != "PASS":
            failures += 1
            if error:
                print(f"  Error: {error}")

    print("=" * 60)

    if failures:
        print(f"Completed with {failures} issue(s).")
        sys.exit(1)

    print("All IRS Data Book imports completed successfully.")


if __name__ == "__main__":
    main()