"""Batch loader for CMS-21 CHIP workbooks."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_ROOT = Path("data/raw/chip/cms21")
YEAR_RE = re.compile(r"^(19|20)\d{2}$")

@dataclass(frozen=True)
class FiscalYearWorkbook:
    fiscal_year: int
    workbook: Path

@dataclass(frozen=True)
class RunResult:
    fiscal_year: int
    workbook: Path
    load_passed: bool
    validation_passed: bool | None
    message: str

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover and load CMS-21 CHIP workbooks by fiscal year.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--years", type=int, nargs="*")
    parser.add_argument("--notes-template", default="CMS-21 directory load for FY{year}.")
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)

def discover_workbooks(root: Path, requested_years: Iterable[int] | None = None) -> list[FiscalYearWorkbook]:
    if not root.exists():
        raise FileNotFoundError(f"CMS-21 root directory does not exist: {root}")
    requested = set(requested_years or [])
    discovered: list[FiscalYearWorkbook] = []
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not YEAR_RE.fullmatch(year_dir.name):
            continue
        fiscal_year = int(year_dir.name)
        if requested and fiscal_year not in requested:
            continue
        candidates = sorted(p for p in year_dir.glob("*.xlsx") if not p.name.startswith("~$"))
        if not candidates:
            raise FileNotFoundError(f"FY{fiscal_year}: no .xlsx workbook found in {year_dir}")
        preferred = [p for p in candidates if "CHIP" in p.name.upper() and "FMR" in p.name.upper() and "NET EXPENDITURES" in p.name.upper()]
        if len(preferred) == 1:
            workbook = preferred[0]
        elif len(candidates) == 1:
            workbook = candidates[0]
        else:
            names = "\n  ".join(p.name for p in candidates)
            raise RuntimeError(f"FY{fiscal_year}: multiple possible workbooks found:\n  {names}")
        discovered.append(FiscalYearWorkbook(fiscal_year, workbook))
    if requested:
        found = {item.fiscal_year for item in discovered}
        missing = sorted(requested - found)
        if missing:
            raise FileNotFoundError("No workbook discovered for: " + ", ".join(map(str, missing)))
    if not discovered:
        raise FileNotFoundError(f"No CMS-21 workbooks discovered under {root}")
    return discovered

def display_command(command: Sequence[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)

def run_command(command: Sequence[str], dry_run: bool) -> bool:
    print(f"COMMAND: {display_command(command)}")
    if dry_run:
        return True
    return subprocess.run(command, check=False).returncode == 0

def load_one(item: FiscalYearWorkbook, notes_template: str, skip_validation: bool, dry_run: bool) -> RunResult:
    year = item.fiscal_year
    print("\n" + "=" * 88)
    print(f"FY{year}: {item.workbook}")
    print("=" * 88)
    load_command = [
        sys.executable, "-m", "etl.loaders.load_chip_cms21",
        "--fiscal-year", str(year),
        "--workbook", str(item.workbook),
        "--notes", notes_template.format(year=year),
    ]
    if not run_command(load_command, dry_run):
        return RunResult(year, item.workbook, False, None, "LOAD FAILED")
    if skip_validation:
        return RunResult(year, item.workbook, True, None, "LOAD PASS; VALIDATION SKIPPED")
    validation_command = [sys.executable, "-m", "scripts.validate_chip_cms21", "--fiscal-year", str(year)]
    validation_passed = run_command(validation_command, dry_run)
    return RunResult(year, item.workbook, True, validation_passed, "PASS" if validation_passed else "VALIDATION FAILED")

def print_summary(results: Sequence[RunResult], dry_run: bool) -> None:
    print("\n" + "=" * 88)
    print("CMS-21 DIRECTORY LOAD SUMMARY")
    print("=" * 88)
    for result in results:
        suffix = " (dry run)" if dry_run else ""
        print(f"FY{result.fiscal_year}  {result.message}{suffix}  {result.workbook.name}")
    failures = [r for r in results if not r.load_passed or r.validation_passed is False]
    print("-" * 88)
    if failures:
        print(f"OVERALL RESULT: FAIL ({len(failures)} of {len(results)} fiscal years failed)")
    else:
        print(f"OVERALL RESULT: PASS ({len(results)} fiscal years processed)")

def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        workbooks = discover_workbooks(args.root, args.years)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("DISCOVERED CMS-21 WORKBOOKS")
    print("-" * 88)
    for item in workbooks:
        print(f"FY{item.fiscal_year}: {item.workbook}")
    results: list[RunResult] = []
    for item in workbooks:
        result = load_one(item, args.notes_template, args.skip_validation, args.dry_run)
        results.append(result)
        failed = not result.load_passed or result.validation_passed is False
        if failed and not args.continue_on_error:
            print("\nStopping after failure. Use --continue-on-error to process later years.")
            break
    print_summary(results, args.dry_run)
    return 1 if any(not r.load_passed or r.validation_passed is False for r in results) else 0

if __name__ == "__main__":
    raise SystemExit(main())