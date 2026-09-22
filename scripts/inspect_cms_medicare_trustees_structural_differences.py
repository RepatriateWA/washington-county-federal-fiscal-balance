#!/usr/bin/env python3
"""
CMS Medicare Trustees Private Health Plans structural-difference inspector v0.1
===============================================================================

WCFFBP read-only diagnostic stage.

Purpose
-------
Read the outputs already produced by:

    scripts/profile_cms_medicare_trustees_private_plans_v0_2.py

and create a compact human-readable report focused on the structural differences
that caused the v0.2 validation FAIL:

  1. IV.C3 in Trustees vintages 2015 and 2016.
  2. IV.C3 plan/category and bid/rebate terminology across 2015-2026.
  3. IV.C4 appearance and structure, especially 2024-2026.

This script deliberately does NOT:
  * re-read or re-profile the 12 Trustees PDFs or ZIP packages;
  * make network requests;
  * extract payment observations into a control dataset;
  * assign actual/projected status to individual numeric observations;
  * reconcile any Trustees value to WCFFBP;
  * write to PostgreSQL;
  * modify any v0.1 or v0.2 evidence file.

Run from repository root:
    python scripts/inspect_cms_medicare_trustees_structural_differences.py
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_trustees"
    / "validation"
    / "private_health_plans_structure_v0_2"
)

CONTEXTS = BASE / "cms_medicare_trustees_private_plans_table_contexts.csv"
EVIDENCE = BASE / "cms_medicare_trustees_private_plans_table_evidence.csv"
COVERAGE = BASE / "cms_medicare_trustees_private_plans_structural_coverage.csv"
LOCAL = BASE / "cms_medicare_trustees_private_plans_local_ccp_structure.csv"

OUTDIR = (
    ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_trustees"
    / "validation"
    / "private_health_plans_structure_difference_v0_1"
)
OUTFILE = OUTDIR / "trustees_private_health_plans_structural_difference_report.txt"

MAX_CONTEXT_CHARS = 12000

FOCUS_TERMS = (
    "local ccp",
    " hmo",
    "hmo ",
    " ppo",
    "ppo ",
    "regional ppo",
    "rppo",
    "bid-based",
    "bid based",
    "rebate expenditures",
    "total expenditures",
    "per private health plan enrollee",
    "key factors for medicare advantage",
    "uspcc",
    "benchmark pmpm",
    "bid pmpm",
    "rebate pmpm",
    "risk score",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def clean(text: str) -> str:
    return " ".join((text or "").split())


def is_focus_context(row: dict[str, str]) -> bool:
    text = clean(row.get("context", "")).lower()
    return any(term in text for term in FOCUS_TERMS)


def dedupe_contexts(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Keep unique normalized contexts while preferring annual-report evidence.
    The profiler can emit the same page/row more than once through overlapping
    table recognition; this report should be readable rather than repetitive.
    """
    ranked = sorted(
        rows,
        key=lambda r: (
            0 if r.get("artifact") == "ANNUAL_REPORT" else 1,
            r.get("member_name", ""),
            r.get("surface", ""),
            r.get("location", ""),
        ),
    )
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in ranked:
        text = clean(row.get("context", ""))
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def append_context_block(lines: list[str], row: dict[str, str]) -> None:
    lines.append(
        f"SOURCE: artifact={row.get('artifact','')} | "
        f"member={row.get('member_name','')} | "
        f"surface={row.get('surface','')} | "
        f"location={row.get('location','')}"
    )
    lines.append("-" * 110)
    text = clean(row.get("context", ""))[:MAX_CONTEXT_CHARS]
    lines.append(text)
    lines.append("")


def main() -> int:
    required = [CONTEXTS, EVIDENCE, COVERAGE, LOCAL]
    missing = [p for p in required if not p.exists()]

    print("=" * 110)
    print("CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS STRUCTURAL-DIFFERENCE INSPECTOR v0.1")
    print("=" * 110)
    print("Read-only diagnostic. Uses existing v0.2 profiler outputs only.\n")

    if missing:
        print("FAIL  Required v0.2 output file(s) missing:")
        for path in missing:
            print(f"      {path}")
        return 1

    contexts = read_csv(CONTEXTS)
    evidence = read_csv(EVIDENCE)
    coverage = read_csv(COVERAGE)
    local_rows = read_csv(LOCAL)

    cov = {
        (int(r["trustees_vintage"]), r["table_id"]): r
        for r in coverage
    }
    local = {
        int(r["trustees_vintage"]): r
        for r in local_rows
    }

    evidence_by = defaultdict(list)
    for row in evidence:
        evidence_by[(int(row["trustees_vintage"]), row["table_id"])].append(row)

    contexts_by = defaultdict(list)
    for row in contexts:
        contexts_by[(int(row["trustees_vintage"]), row["table_id"])].append(row)

    lines: list[str] = []
    lines += [
        "=" * 110,
        "CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS STRUCTURAL-DIFFERENCE REPORT v0.1",
        "=" * 110,
        "",
        "PURPOSE",
        "-" * 110,
        "Inspect only the source-supported structural differences behind the v0.2 profiler FAIL.",
        "No payment observation extraction, status assignment, reconciliation, imputation, or DB writes.",
        "",
        "SECTION 1 — STRUCTURAL MATRIX",
        "-" * 110,
        "Vintage | IV.C2 | IV.C3 | IV.C4 | Local CCP | HMO | PPO | Regional PPO | Local HMO | Local PPO",
        "-" * 110,
    ]

    for year in range(2015, 2027):
        lr = local[year]
        lines.append(
            f"{year} | "
            f"{cov[(year,'IV.C2')]['table_found']:^5} | "
            f"{cov[(year,'IV.C3')]['table_found']:^5} | "
            f"{cov[(year,'IV.C4')]['table_found']:^5} | "
            f"{lr['local_ccp_parent_found']:^9} | "
            f"{lr['hmo_child_found']:^3} | "
            f"{lr['ppo_child_found']:^3} | "
            f"{lr['regional_ppo_found']:^12} | "
            f"{lr['LOCAL_CCP_HMO']:^22} | "
            f"{lr['LOCAL_CCP_PPO']:^22}"
        )

    lines += [
        "",
        "SECTION 2 — IV.C3 STRUCTURAL VOCABULARY BY VINTAGE",
        "-" * 110,
    ]
    for year in range(2015, 2027):
        r = cov[(year, "IV.C3")]
        lines += [
            f"{year}",
            f"  plan_terms      : {r.get('plan_terms','')}",
            f"  component_terms : {r.get('component_terms','')}",
            f"  status_terms    : {r.get('status_terms','')}",
            f"  target_years    : {r.get('target_observation_years','')}",
        ]

    lines += [
        "",
        "SECTION 3 — IV.C4 APPEARANCE / VOCABULARY BY VINTAGE",
        "-" * 110,
    ]
    for year in range(2015, 2027):
        r = cov[(year, "IV.C4")]
        lines += [
            f"{year}",
            f"  found           : {r.get('table_found','')}",
            f"  component_terms : {r.get('component_terms','')}",
            f"  status_terms    : {r.get('status_terms','')}",
            f"  target_years    : {r.get('target_observation_years','')}",
        ]

    lines += [
        "",
        "SECTION 4 — 2015 IV.C3 SOURCE CONTEXT",
        "-" * 110,
    ]
    rows = dedupe_contexts(
        [r for r in contexts_by[(2015, "IV.C3")] if is_focus_context(r)]
    )
    if not rows:
        lines.append("NO FOCUSED CONTEXT FOUND")
        lines.append("")
    else:
        for row in rows:
            append_context_block(lines, row)

    lines += [
        "",
        "SECTION 5 — 2016 IV.C3 SOURCE CONTEXT",
        "-" * 110,
    ]
    rows = dedupe_contexts(
        [r for r in contexts_by[(2016, "IV.C3")] if is_focus_context(r)]
    )
    if not rows:
        lines.append("NO FOCUSED CONTEXT FOUND")
        lines.append("")
    else:
        for row in rows:
            append_context_block(lines, row)

    lines += [
        "",
        "SECTION 6 — IV.C3 BID / REBATE / TOTAL EVIDENCE BY VINTAGE",
        "-" * 110,
    ]
    wanted_components = {
        "BID_BASED_EXPENDITURES",
        "REBATE_EXPENDITURES",
        "TOTAL_EXPENDITURES",
        "PER_ENROLLEE",
        "PART_A_PLUS_B",
    }
    for year in range(2015, 2027):
        rows = [
            r for r in evidence_by[(year, "IV.C3")]
            if r.get("evidence_kind") == "COMPONENT"
            and r.get("evidence_label") in wanted_components
        ]
        labels = sorted({r.get("evidence_label", "") for r in rows if r.get("evidence_label")})
        lines.append(f"{year}: {', '.join(labels) if labels else 'NONE DETECTED'}")
        for row in dedupe_contexts(rows):
            append_context_block(lines, row)

    lines += [
        "",
        "SECTION 7 — IV.C4 SOURCE CONTEXT, 2024-2026",
        "-" * 110,
    ]
    for year in (2024, 2025, 2026):
        lines += [f"", f"### TRUSTEES VINTAGE {year}", ""]
        rows = dedupe_contexts(
            [r for r in contexts_by[(year, "IV.C4")] if is_focus_context(r)]
        )
        if not rows:
            lines.append("NO FOCUSED CONTEXT FOUND")
            lines.append("")
        else:
            for row in rows:
                append_context_block(lines, row)

    lines += [
        "",
        "SECTION 8 — STATUS TERMINOLOGY NEAR IV.C2 / IV.C3 / IV.C4",
        "-" * 110,
        "These are lexical evidence only. They are NOT assignments of status to individual numeric observations.",
        "",
    ]
    for year in range(2015, 2027):
        lines.append(f"{year}")
        for table_id in ("IV.C2", "IV.C3", "IV.C4"):
            labels = sorted({
                r.get("evidence_label", "")
                for r in evidence_by[(year, table_id)]
                if r.get("evidence_kind") == "STATUS"
            })
            lines.append(
                f"  {table_id}: {', '.join(labels) if labels else 'NONE DETECTED'}"
            )

    lines += [
        "",
        "SECTION 9 — DIAGNOSTIC BOUNDARY",
        "-" * 110,
        "This report intentionally makes no claim that a missing literal term means a missing economic component.",
        "It records only what the v0.2 evidence files explicitly detected in each preserved Trustees vintage.",
        "",
        "Before changing the structural profiler or writing a numeric control extractor, inspect:",
        "  * 2015 IV.C3 source context;",
        "  * 2016 IV.C3 source context;",
        "  * vintage-specific IV.C3 bid/rebate/total wording;",
        "  * the first source-supported appearance and subsequent structure of IV.C4.",
        "",
    ]

    OUTDIR.mkdir(parents=True, exist_ok=True)
    OUTFILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    checks = [
        ("All four required v0.2 evidence files readable", True),
        ("2015 IV.C3 present in v0.2 structural coverage", cov[(2015, "IV.C3")]["table_found"] == "YES"),
        ("2016 IV.C3 present in v0.2 structural coverage", cov[(2016, "IV.C3")]["table_found"] == "YES"),
        ("2024 IV.C4 present in v0.2 structural coverage", cov[(2024, "IV.C4")]["table_found"] == "YES"),
        ("2025 IV.C4 present in v0.2 structural coverage", cov[(2025, "IV.C4")]["table_found"] == "YES"),
        ("2026 IV.C4 present in v0.2 structural coverage", cov[(2026, "IV.C4")]["table_found"] == "YES"),
    ]
    overall = all(ok for _, ok in checks)

    print(f"Context rows read                         : {len(contexts):,}")
    print(f"Evidence rows read                        : {len(evidence):,}")
    print(f"Structural coverage rows read             : {len(coverage):,}")
    print(f"Local CCP structure rows read             : {len(local_rows):,}")
    print()
    print("VALIDATION CHECKS")
    for label, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    print()
    print(f"OVERALL INSPECTOR STATUS: {'PASS' if overall else 'FAIL'}")
    print()
    print(f"Report written:")
    print(f"  {OUTFILE}")

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
