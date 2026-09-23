#!/usr/bin/env python3
"""Create v0.2 of the CMS MA Part C weighted Trustees reconciler.

Preserves v0.1 and makes one semantic interface correction:
the reconstruction artifact now emits canonical plan types HMO and LOCAL PPO,
so the downstream reconciler must consume HMO rather than raw HMO/HMOPOS.
"""
from pathlib import Path
import difflib

SOURCE = Path("scripts/reconcile_cms_ma_partc_to_trustees_ivc3_weighted_v0_1.py")
TARGET = Path("scripts/reconcile_cms_ma_partc_to_trustees_ivc3_weighted_v0_2.py")

OLD = 'recognized_plan_types = {"HMO/HMOPOS": "HMO", "LOCAL PPO": "PPO"}'
NEW = 'recognized_plan_types = {"HMO": "HMO", "LOCAL PPO": "PPO"}'
OLD_TITLE = "CMS MA PART C — WA-MEMBER-MONTH-WEIGHTED TRUSTEES IV.C3 RECONCILIATION v0.1"
NEW_TITLE = "CMS MA PART C — WA-MEMBER-MONTH-WEIGHTED TRUSTEES IV.C3 RECONCILIATION v0.2"

def fail(msg):
    print("FAIL ", msg)
    raise SystemExit(1)

def main():
    print("=" * 96)
    print("CREATE CMS MA PART C TRUSTEES WEIGHTED RECONCILIATION FIX v0.2")
    print("=" * 96)
    print(f"Source : {SOURCE}")
    print(f"Target : {TARGET}\n")

    if not SOURCE.is_file():
        fail(f"Source not found: {SOURCE}")
    if TARGET.exists():
        fail(f"Target already exists; refusing to overwrite: {TARGET}")

    src = SOURCE.read_text(encoding="utf-8")
    old_n, new_n = src.count(OLD), src.count(NEW)

    print("PRE-WRITE VALIDATION")
    print("-" * 96)
    print(f"{'PASS' if old_n == 1 else 'FAIL'}  Old mapping occurs exactly once: {old_n}")
    print(f"{'PASS' if new_n == 0 else 'FAIL'}  New mapping absent from v0.1 source: {new_n}")
    if old_n != 1 or new_n != 0:
        fail("Source does not match expected v0.1 state.")

    dst = src.replace(OLD, NEW, 1)
    title_n = dst.count(OLD_TITLE)
    if title_n == 1:
        dst = dst.replace(OLD_TITLE, NEW_TITLE, 1)
    elif title_n > 1:
        fail(f"Unexpected duplicate visible version titles: {title_n}")

    TARGET.write_text(dst, encoding="utf-8")
    written = TARGET.read_text(encoding="utf-8")

    checks = [
        ("Target file exists", TARGET.is_file()),
        ("Old mapping absent from v0.2", written.count(OLD) == 0),
        ("Canonical mapping occurs exactly once", written.count(NEW) == 1),
        ("v0.1 source remains unchanged", SOURCE.read_text(encoding="utf-8") == src),
    ]

    print("\nPOST-WRITE VALIDATION")
    print("-" * 96)
    for label, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    if not all(ok for _, ok in checks):
        fail("Post-write validation failed.")

    print("\nCONTROLLED DIFF")
    print("-" * 96)
    for line in difflib.unified_diff(
        src.splitlines(), written.splitlines(),
        fromfile=str(SOURCE), tofile=str(TARGET), lineterm=""
    ):
        print(line)

    print("\nOVERALL STATUS: PASS")
    print(f"\nCreated:\n{TARGET}")
    print(f"\nNext command:\npython {TARGET}")

if __name__ == "__main__":
    main()
