#!/usr/bin/env python
"""
Create v0.2 copies of the CMS MA Part C production validators with the
evidence-based HMO/HMOPOS canonicalization repair.

Run from the WCFFBP repository root:

    python scripts/create_cms_ma_partc_hmo_fix_v0_2.py

READ/WRITE SCOPE
----------------
Reads:
  scripts/validate_cms_ma_partc_monthly_linkage.py
  scripts/validate_cms_ma_partc_payment_reconstruction.py

Creates (does not overwrite v0.1/original files):
  scripts/validate_cms_ma_partc_monthly_linkage_v0_2.py
  scripts/validate_cms_ma_partc_payment_reconstruction_v0_2.py

The only semantic source-code change permitted is:
  {"HMO", "HMO POS", "HMOPOS"}
to
  {"HMO", "HMO POS", "HMOPOS", "HMO/HMOPOS"}

The script refuses to proceed if the expected old expression is absent,
already changed, or appears other than exactly once in either source.
"""

from pathlib import Path
import difflib
import sys

ROOT = Path.cwd()

FILES = [
    (
        ROOT / "scripts" / "validate_cms_ma_partc_monthly_linkage.py",
        ROOT / "scripts" / "validate_cms_ma_partc_monthly_linkage_v0_2.py",
    ),
    (
        ROOT / "scripts" / "validate_cms_ma_partc_payment_reconstruction.py",
        ROOT / "scripts" / "validate_cms_ma_partc_payment_reconstruction_v0_2.py",
    ),
]

OLD = '{"HMO", "HMO POS", "HMOPOS"}'
NEW = '{"HMO", "HMO POS", "HMOPOS", "HMO/HMOPOS"}'


def main():
    planned = []

    print("=" * 88)
    print("CMS MA PART C — HMO/HMOPOS CANONICALIZATION REPAIR v0.2")
    print("=" * 88)
    print("Evidence-based repair only; original production scripts are preserved.")
    print()

    for source, dest in FILES:
        if not source.exists():
            raise SystemExit(f"FAIL: source file not found: {source}")
        if dest.exists():
            raise SystemExit(
                f"FAIL: destination already exists; refusing to overwrite: {dest}"
            )

        text = source.read_text(encoding="utf-8")
        old_count = text.count(OLD)
        new_count = text.count(NEW)

        print(f"Source: {source.relative_to(ROOT)}")
        print(f"  expected old expression occurrences : {old_count}")
        print(f"  already-fixed expression occurrences: {new_count}")

        if old_count != 1:
            raise SystemExit(
                "FAIL: expected the old canonicalization expression exactly once "
                f"in {source.name}; observed {old_count}. No files written."
            )
        if new_count != 0:
            raise SystemExit(
                f"FAIL: {source.name} already contains the v0.2 expression. "
                "No files written."
            )

        revised = text.replace(OLD, NEW, 1)

        # Guardrail: replacement must change exactly one line semantically.
        diff = list(
            difflib.unified_diff(
                text.splitlines(),
                revised.splitlines(),
                fromfile=source.name,
                tofile=dest.name,
                lineterm="",
            )
        )
        removed = [x for x in diff if x.startswith("-") and not x.startswith("---")]
        added = [x for x in diff if x.startswith("+") and not x.startswith("+++")]

        if len(removed) != 1 or len(added) != 1:
            raise SystemExit(
                f"FAIL: unexpected diff shape for {source.name}: "
                f"{len(removed)} removed, {len(added)} added. No files written."
            )

        planned.append((source, dest, revised, diff))
        print("  pre-write validation               : PASS")
        print()

    # Only write after BOTH source files pass all guardrails.
    for source, dest, revised, diff in planned:
        dest.write_text(revised, encoding="utf-8")
        print(f"CREATED: {dest.relative_to(ROOT)}")
        print("DIFF:")
        for line in diff:
            print(line)
        print()

    print("VALIDATION")
    print("-" * 88)
    for _, dest, _, _ in planned:
        text = dest.read_text(encoding="utf-8")
        ok = text.count(NEW) == 1 and text.count(OLD) == 0
        print(f"{'PASS' if ok else 'FAIL'}  {dest.name}")
        if not ok:
            return 1

    print()
    print("OVERALL STATUS: PASS")
    print("Original production scripts were not modified.")
    print()
    print("NEXT RUN:")
    print("  python scripts\\validate_cms_ma_partc_monthly_linkage_v0_2.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
