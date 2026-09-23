#!/usr/bin/env python3
"""
CMS MA Part C v0.2 certification-housekeeping utility.

Purpose
-------
Create provenance-clean v0.2 copies of the already analytically validated
scripts WITHOUT changing reconstruction/linkage/reconciliation methodology.

Expected source scripts:
  scripts/validate_cms_ma_partc_monthly_linkage_v0_2.py
  scripts/validate_cms_ma_partc_payment_reconstruction_v0_2.py
  scripts/reconcile_cms_ma_partc_to_trustees_ivc3_weighted_v0_2.py

Creates:
  scripts/validate_cms_ma_partc_monthly_linkage_v0_2_certified.py
  scripts/validate_cms_ma_partc_payment_reconstruction_v0_2_certified.py
  scripts/reconcile_cms_ma_partc_to_trustees_ivc3_weighted_v0_2_certified.py

Changes are restricted to:
  * output-directory versioning from legacy/unversioned paths to v0_2 paths;
  * visible inherited v0.1 labels to v0.2 where present.

No source CMS artifacts or database objects are modified.

Run from repository root:
    python scripts/create_cms_ma_partc_certification_housekeeping_v0_2.py
"""

from __future__ import annotations

from pathlib import Path
import difflib
import re
import sys

SCRIPTS = Path("scripts")

JOBS = [
    {
        "name": "monthly linkage",
        "src": SCRIPTS / "validate_cms_ma_partc_monthly_linkage_v0_2.py",
        "dst": SCRIPTS / "validate_cms_ma_partc_monthly_linkage_v0_2_certified.py",
        "dir_old": "monthly_linkage",
        "dir_new": "monthly_linkage_v0_2",
    },
    {
        "name": "payment reconstruction",
        "src": SCRIPTS / "validate_cms_ma_partc_payment_reconstruction_v0_2.py",
        "dst": SCRIPTS / "validate_cms_ma_partc_payment_reconstruction_v0_2_certified.py",
        "dir_old": "payment_reconstruction",
        "dir_new": "payment_reconstruction_v0_2",
    },
    {
        "name": "Trustees weighted reconciliation",
        "src": SCRIPTS / "reconcile_cms_ma_partc_to_trustees_ivc3_weighted_v0_2.py",
        "dst": SCRIPTS / "reconcile_cms_ma_partc_to_trustees_ivc3_weighted_v0_2_certified.py",
        "dir_old": "trustees_ivc3_weighted_reconciliation_v0_1",
        "dir_new": "trustees_ivc3_weighted_reconciliation_v0_2",
    },
]

def fail(msg: str) -> None:
    print(f"FAIL  {msg}")
    raise SystemExit(1)

def replace_path_component(text: str, old: str, new: str) -> tuple[str, int]:
    """
    Replace exact quoted path-component occurrences only.
    Handles common Path / string literal construction while avoiding broad
    replacement of narrative text.
    """
    patterns = [
        (f'"{old}"', f'"{new}"'),
        (f"'{old}'", f"'{new}'"),
    ]
    count = 0
    for a, b in patterns:
        n = text.count(a)
        if n:
            text = text.replace(a, b)
            count += n
    return text, count

def update_visible_version_labels(text: str) -> tuple[str, int]:
    # Narrowly update inherited display-label text, not filenames/paths.
    patterns = [
        (r"(PAYMENT RECONSTRUCTION VALIDATION )v0\.1\b", r"\1v0.2"),
        (r"(MONTHLY DIMENSIONAL LINKAGE VALIDATION )v0\.1\b", r"\1v0.2"),
        (r"(WA-MEMBER-MONTH-WEIGHTED TRUSTEES IV\.C3 RECONCILIATION )v0\.1\b", r"\1v0.2"),
    ]
    total = 0
    for pat, repl in patterns:
        text, n = re.subn(pat, repl, text)
        total += n
    return text, total

def main() -> None:
    print("=" * 108)
    print("CMS MA PART C v0.2 CERTIFICATION HOUSEKEEPING")
    print("=" * 108)
    print("Creates provenance-clean copies only; analytical logic must remain unchanged.\n")

    # Refuse partial/ambiguous runs.
    for job in JOBS:
        if not job["src"].is_file():
            fail(f"Required source missing: {job['src']}")
        if job["dst"].exists():
            fail(f"Target already exists; refusing overwrite: {job['dst']}")

    created = []

    for job in JOBS:
        src = job["src"]
        dst = job["dst"]
        original = src.read_text(encoding="utf-8")
        modified, path_changes = replace_path_component(
            original, job["dir_old"], job["dir_new"]
        )
        modified, label_changes = update_visible_version_labels(modified)

        print(f"{job['name'].upper()}")
        print("-" * 108)
        print(f"Source                 : {src}")
        print(f"Target                 : {dst}")
        print(f"Output-path replacements: {path_changes}")
        print(f"Visible-label updates   : {label_changes}")

        if path_changes < 1:
            fail(
                f"No exact output-directory occurrence found for {job['name']}: "
                f"{job['dir_old']}"
            )

        # Guardrails: required semantic lines must be identical between source
        # and destination. We only permit the path and display-label edits above.
        dst.write_text(modified, encoding="utf-8")
        reread = dst.read_text(encoding="utf-8")

        checks = [
            ("target exists", dst.is_file()),
            ("new output directory present", job["dir_new"] in reread),
            ("legacy output directory absent as quoted component",
             f'"{job["dir_old"]}"' not in reread and f"'{job['dir_old']}'" not in reread),
            ("source remains unchanged", src.read_text(encoding="utf-8") == original),
        ]
        for label, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'}  {label}")
        if not all(ok for _, ok in checks):
            fail(f"Post-write validation failed for {job['name']}")

        print("\nCONTROLLED DIFF")
        for line in difflib.unified_diff(
            original.splitlines(),
            reread.splitlines(),
            fromfile=str(src),
            tofile=str(dst),
            lineterm="",
        ):
            print(line)
        print()
        created.append(dst)

    print("=" * 108)
    print("OVERALL STATUS: PASS")
    print("=" * 108)
    print("\nCreated:")
    for p in created:
        print(f"  {p}")

    print("\nRun these in order:")
    for p in created:
        print(f"python {p}")

    print("\nCertification rule:")
    print("All three reruns must reproduce the previously validated numerical results exactly")
    print("(apart from corrected version/output-path text) before Git certification.")

if __name__ == "__main__":
    main()
