import re
import sys
from pathlib import Path

from etl.loaders.load_irs_soi import load_irs_soi
from etl.validation.validate_irs import validate_irs_year
from etl.logging_config import get_logger

logger = get_logger(__name__)

IRS_DIR = Path("data/raw/irs")
FILENAME_PATTERN = re.compile(r"irs_soi_wa_(\d{4})\.xls[x]?$", re.IGNORECASE)


def discover_workbooks():
    workbooks = []

    for path in IRS_DIR.glob("irs_soi_wa_*.xls*"):
        match = FILENAME_PATTERN.match(path.name)

        if not match:
            logger.warning("Skipping unrecognized IRS filename: %s", path.name)
            continue

        tax_year = int(match.group(1))
        workbooks.append((tax_year, path))

    return sorted(workbooks, key=lambda item: item[0])


def main():
    print("=" * 60)
    print("IRS SOI Batch Import")
    print("=" * 60)

    workbooks = discover_workbooks()

    if not workbooks:
        print(f"No IRS workbooks found in {IRS_DIR}")
        print("Expected filenames like: irs_soi_wa_2015.xls")
        sys.exit(1)

    print("\nDiscovered workbooks")
    print("-" * 60)

    for tax_year, path in workbooks:
        print(f"{tax_year}: {path}")

    results = []

    print("\nImport and validation")
    print("-" * 60)

    for tax_year, path in workbooks:
        try:
            print(f"\nImporting {tax_year}...")
            load_irs_soi(tax_year, path)

            print(f"Validating {tax_year}...")
            validate_irs_year(tax_year)

            results.append((tax_year, "PASS", None))

        except Exception as exc:
            logger.exception("IRS import failed for %s", tax_year)
            results.append((tax_year, "FAIL", str(exc)))

    print("\nSummary")
    print("-" * 60)

    failures = 0

    for tax_year, status, error in results:
        print(f"{tax_year}: {status}")

        if status != "PASS":
            failures += 1
            print(f"  Error: {error}")

    print("=" * 60)

    if failures:
        print(f"Completed with {failures} failure(s).")
        sys.exit(1)

    print("All IRS imports completed successfully.")


if __name__ == "__main__":
    main()