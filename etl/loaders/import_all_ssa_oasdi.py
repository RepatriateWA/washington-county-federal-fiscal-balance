from pathlib import Path
import sys

from etl.loaders.load_ssa_oasdi_county import load_ssa_oasdi_county
from etl.logging_config import get_logger


logger = get_logger(__name__)

DATA_DIR = Path("data/raw/ssa/oasdi")
YEARS = range(2015, 2025)


def find_source_file(year: int) -> Path | None:
    year_dir = DATA_DIR / str(year)

    candidates = [
        year_dir / f"ssa_oasdi_wa_{year}.xlsx",
        year_dir / f"ssa_oasdi_wa_{year}.xls",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def main() -> None:
    print("=" * 70)
    print("SSA OASDI COUNTY BATCH IMPORT")
    print("=" * 70)

    results = []

    for year in YEARS:
        source_file = find_source_file(year)

        if source_file is None:
            print(f"{year}: MISSING source file")
            results.append((year, "MISSING", None))
            continue

        print(f"\nImporting {year} from {source_file}")

        try:
            load_ssa_oasdi_county(year, source_file)
            print(f"{year}: PASS")
            results.append((year, "PASS", None))

        except Exception as exc:
            logger.exception(
                "Failed to import SSA OASDI county data for %s",
                year,
            )
            print(f"{year}: FAIL")
            results.append((year, "FAIL", str(exc)))

    print("\nSummary")
    print("-" * 70)

    issues = 0

    for year, status, error in results:
        print(f"{year}: {status}")

        if status != "PASS":
            issues += 1

            if error:
                print(f"  Error: {error}")

    print("=" * 70)

    if issues:
        print(f"Completed with {issues} issue(s).")
        sys.exit(1)

    print("All SSA OASDI imports completed successfully.")


if __name__ == "__main__":
    main()