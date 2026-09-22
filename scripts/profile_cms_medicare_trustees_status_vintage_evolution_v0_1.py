#!/usr/bin/env python3
"""
CMS Medicare Trustees observation-status / vintage-evolution profiler v0.1
===========================================================================

WCFFBP evidence gate following validated raw Trustees control extraction.

Purpose
-------
Profile how the same Medicare Trustees IV.C2 / IV.C3 observations evolve across
successive Trustees vintages, while separately collecting source text relevant
to historical / actual / estimate / projected status.

This script deliberately DOES NOT assign observation status and DOES NOT select
a preferred vintage.  Its job is to produce the evidence needed to make those
methodological decisions explicitly.

Inputs
------
Validated raw controls:
  data/raw/cms/medicare_trustees/validation/private_health_plans_controls_raw_v0_2/
    cms_medicare_trustees_private_plan_controls_raw.csv

Preserved annual reports:
  data/raw/cms/medicare_trustees/reports/medicare_trustees_YYYY.pdf

Outputs
-------
  data/raw/cms/medicare_trustees/validation/status_vintage_evolution_v0_1/

No network requests. No database writes. No imputation. No reconciliation.
"""

from __future__ import annotations

import csv
import hashlib
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees"
RAW = (
    BASE / "validation" / "private_health_plans_controls_raw_v0_2"
    / "cms_medicare_trustees_private_plan_controls_raw.csv"
)
REPORT_DIR = BASE / "reports"
OUTDIR = BASE / "validation" / "status_vintage_evolution_v0_1"

VINTAGES = list(range(2015, 2027))
FOCUS_YEARS = list(range(2015, 2025))
FOCUS_TABLES = {"IV.C2", "IV.C3"}

STATUS_PATTERNS = [
    ("ACTUAL", re.compile(r"\bactual(?:ly)?\b", re.I)),
    ("HISTORICAL", re.compile(r"\bhistor(?:ic|ical|ically)\b", re.I)),
    ("ESTIMATE", re.compile(r"\bestimat(?:e|ed|es|ing)\b", re.I)),
    ("PROJECTED", re.compile(r"\bproject(?:ed|ion|ions|ing)\b", re.I)),
    ("FORECAST", re.compile(r"\bforecast(?:s|ed|ing)?\b", re.I)),
    ("INCURRED", re.compile(r"\bincurred\b", re.I)),
    ("CASH", re.compile(r"\bcash\b", re.I)),
]

TABLE_PATTERNS = {
    "IV.C2": re.compile(r"Table\s+IV\.?\s*C\.?\s*2\b", re.I),
    "IV.C3": re.compile(r"Table\s+IV\.?\s*C\.?\s*3\b", re.I),
    "IV.C4": re.compile(r"Table\s+IV\.?\s*C\.?\s*4\b", re.I),
}
NEXT_TABLE_RE = re.compile(r"Table\s+IV\.?\s*C\.?\s*[2345]\b", re.I)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def fnum(x: str) -> Optional[float]:
    if x is None or str(x).strip() == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def report_path(vintage: int) -> Path:
    return REPORT_DIR / f"medicare_trustees_{vintage}.pdf"


def extract_table_contexts(vintage: int, path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect status vocabulary contexts near IV.C2/IV.C3, without assigning status."""
    evidence: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if PdfReader is None:
        return evidence, [{
            "trustees_vintage": vintage,
            "source_file": str(path.relative_to(ROOT)),
            "table_id": "",
            "page_number": "",
            "error": "pypdf not installed",
        }]

    digest = sha256_file(path)
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        return evidence, [{
            "trustees_vintage": vintage,
            "source_file": str(path.relative_to(ROOT)),
            "table_id": "",
            "page_number": "",
            "error": f"{type(exc).__name__}: {exc}",
        }]

    pages = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
            txt = txt.replace("\u00a0", " ")
            txt = re.sub(r"[ \t]+", " ", txt)
            pages.append(txt)
        except Exception as exc:
            pages.append("")
            errors.append({
                "trustees_vintage": vintage,
                "source_file": str(path.relative_to(ROOT)),
                "table_id": "",
                "page_number": i + 1,
                "error": f"page extraction {type(exc).__name__}: {exc}",
            })

    for table_id in ("IV.C2", "IV.C3"):
        pat = TABLE_PATTERNS[table_id]
        hits = [(i, pat.search(txt)) for i, txt in enumerate(pages) if pat.search(txt)]
        if not hits:
            errors.append({
                "trustees_vintage": vintage,
                "source_file": str(path.relative_to(ROOT)),
                "table_id": table_id,
                "page_number": "",
                "error": "table identifier not found for status-context profiling",
            })
            continue

        # Use first occurrence, matching the validated raw extractor's annual-report basis.
        i, m = hits[0]
        assert m is not None
        page = pages[i]

        # Include prose immediately preceding table and the table itself, but stop
        # before the next numbered table when possible.
        start = max(0, m.start() - 5000)
        block = page[start:]
        next_hits = [
            x for x in NEXT_TABLE_RE.finditer(block)
            if x.start() > (m.start() - start) + 10
        ]
        if next_hits:
            block = block[:next_hits[0].start()]

        # Add a limited next-page continuation for nearby explanatory notes/prose.
        if i + 1 < len(pages):
            block += "\n" + pages[i + 1][:3500]

        for label, sp in STATUS_PATTERNS:
            for hit in sp.finditer(block):
                left = max(0, hit.start() - 350)
                right = min(len(block), hit.end() + 550)
                context = re.sub(r"\s+", " ", block[left:right]).strip()
                evidence.append({
                    "trustees_vintage": vintage,
                    "table_id": table_id,
                    "status_term": label,
                    "matched_text": hit.group(0),
                    "source_file": str(path.relative_to(ROOT)),
                    "source_sha256": digest,
                    "source_page": i + 1,
                    "context": context,
                    "status_assignment": "UNASSIGNED",
                })

    return evidence, errors


def build_evolution(raw: list[dict[str, str]]) -> list[dict[str, Any]]:
    """
    One row per source observation, augmented with within-series revision metrics.

    Series identity intentionally excludes trustees_vintage and value:
      table / observation year / accounting scope / plan type / component /
      unit / basis.
    """
    focus = [
        r for r in raw
        if r.get("table_id") in FOCUS_TABLES
        and r.get("value_status", "").startswith("NUMERIC")
        and int(r["observation_year"]) in FOCUS_YEARS
    ]

    groups: dict[tuple, list[dict[str, str]]] = defaultdict(list)
    for r in focus:
        key = (
            r["table_id"],
            int(r["observation_year"]),
            r["accounting_scope"],
            r["plan_type_normalized"],
            r["component_normalized"],
            r["unit"],
            r["basis"],
        )
        groups[key].append(r)

    out: list[dict[str, Any]] = []
    for key, items in groups.items():
        items.sort(key=lambda r: int(r["trustees_vintage"]))
        numeric_items = [(int(r["trustees_vintage"]), fnum(r["value"]), r) for r in items]
        numeric_items = [(v, x, r) for v, x, r in numeric_items if x is not None]
        if not numeric_items:
            continue

        first_v, first_val, _ = numeric_items[0]
        last_v, last_val, _ = numeric_items[-1]

        for idx, (vintage, value, r) in enumerate(numeric_items):
            prev_value = numeric_items[idx - 1][1] if idx > 0 else None
            next_value = numeric_items[idx + 1][1] if idx + 1 < len(numeric_items) else None
            delta_prev = None if prev_value is None else value - prev_value
            pct_prev = (
                None if prev_value in (None, 0)
                else 100.0 * (value - prev_value) / abs(prev_value)
            )
            delta_final = value - last_val
            pct_final = (
                None if last_val == 0
                else 100.0 * (value - last_val) / abs(last_val)
            )

            out.append({
                "table_id": key[0],
                "observation_year": key[1],
                "accounting_scope": key[2],
                "plan_type_normalized": key[3],
                "component_normalized": key[4],
                "unit": key[5],
                "basis": key[6],
                "trustees_vintage": vintage,
                "value": value,
                "first_available_vintage": first_v,
                "latest_available_vintage": last_v,
                "number_of_vintages_in_series": len(numeric_items),
                "previous_vintage_value": "" if prev_value is None else prev_value,
                "delta_from_previous_vintage": "" if delta_prev is None else delta_prev,
                "pct_change_from_previous_vintage": "" if pct_prev is None else pct_prev,
                "latest_vintage_value": last_val,
                "delta_from_latest_vintage": delta_final,
                "pct_change_from_latest_vintage": pct_final,
                "is_latest_available_vintage": "YES" if vintage == last_v else "NO",
                "observation_status": "UNASSIGNED",
                "preferred_vintage": "UNASSIGNED",
                "source_file": r["source_file"],
                "source_sha256": r["source_sha256"],
                "source_page": r["source_page"],
            })

    return sorted(out, key=lambda r: (
        r["table_id"], r["observation_year"], r["plan_type_normalized"],
        r["component_normalized"], r["trustees_vintage"]
    ))


def build_series_summary(evolution: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in evolution:
        key = (
            r["table_id"], r["observation_year"], r["accounting_scope"],
            r["plan_type_normalized"], r["component_normalized"],
            r["unit"], r["basis"],
        )
        groups[key].append(r)

    out = []
    for key, items in sorted(groups.items()):
        items.sort(key=lambda r: int(r["trustees_vintage"]))
        vals = [float(r["value"]) for r in items]
        revisions = [
            abs(float(r["delta_from_previous_vintage"]))
            for r in items
            if r["delta_from_previous_vintage"] != ""
        ]
        changes = sum(
            1 for r in items
            if r["delta_from_previous_vintage"] != ""
            and not math.isclose(float(r["delta_from_previous_vintage"]), 0.0, abs_tol=1e-12)
        )
        out.append({
            "table_id": key[0],
            "observation_year": key[1],
            "accounting_scope": key[2],
            "plan_type_normalized": key[3],
            "component_normalized": key[4],
            "unit": key[5],
            "basis": key[6],
            "first_available_vintage": items[0]["trustees_vintage"],
            "latest_available_vintage": items[-1]["trustees_vintage"],
            "vintage_count": len(items),
            "first_value": vals[0],
            "latest_value": vals[-1],
            "first_to_latest_change": vals[-1] - vals[0],
            "first_to_latest_pct_change": (
                "" if vals[0] == 0 else 100.0 * (vals[-1] - vals[0]) / abs(vals[0])
            ),
            "number_of_intervintage_changes": changes,
            "max_absolute_intervintage_revision": max(revisions) if revisions else 0.0,
            "status_assignment": "UNASSIGNED",
            "preferred_vintage": "UNASSIGNED",
        })
    return out


def build_year_vintage_matrix(evolution: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coverage matrix only; does not infer actual/projected status."""
    counts: dict[tuple, int] = defaultdict(int)
    for r in evolution:
        counts[(r["table_id"], r["observation_year"], r["trustees_vintage"])] += 1

    out = []
    for table in ("IV.C2", "IV.C3"):
        for year in FOCUS_YEARS:
            for vintage in VINTAGES:
                if vintage < year:
                    continue
                out.append({
                    "table_id": table,
                    "observation_year": year,
                    "trustees_vintage": vintage,
                    "numeric_observation_count": counts.get((table, year, vintage), 0),
                    "status_assignment": "UNASSIGNED",
                    "preferred_vintage": "UNASSIGNED",
                })
    return out


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    print("=" * 110)
    print("CMS MEDICARE TRUSTEES STATUS / VINTAGE-EVOLUTION PROFILER v0.1")
    print("=" * 110)
    print("No status assignment, preferred-vintage selection, reconciliation, imputation, or DB writes.\n")

    errors: list[dict[str, Any]] = []

    if not RAW.exists():
        print(f"FAIL  Validated raw control file not found:\n      {RAW}")
        return 1

    missing_reports = [report_path(y) for y in VINTAGES if not report_path(y).exists()]
    if missing_reports:
        print("FAIL  Missing preserved annual report(s):")
        for p in missing_reports:
            print(f"      {p}")
        return 1

    raw = read_csv(RAW)
    evolution = build_evolution(raw)
    series = build_series_summary(evolution)
    matrix = build_year_vintage_matrix(evolution)

    evidence: list[dict[str, Any]] = []
    for vintage in VINTAGES:
        ev, err = extract_table_contexts(vintage, report_path(vintage))
        evidence.extend(ev)
        errors.extend(err)

    evo_fields = [
        "table_id", "observation_year", "accounting_scope",
        "plan_type_normalized", "component_normalized", "unit", "basis",
        "trustees_vintage", "value", "first_available_vintage",
        "latest_available_vintage", "number_of_vintages_in_series",
        "previous_vintage_value", "delta_from_previous_vintage",
        "pct_change_from_previous_vintage", "latest_vintage_value",
        "delta_from_latest_vintage", "pct_change_from_latest_vintage",
        "is_latest_available_vintage", "observation_status",
        "preferred_vintage", "source_file", "source_sha256", "source_page",
    ]
    write_csv(OUTDIR / "trustees_control_vintage_evolution.csv", evolution, evo_fields)

    series_fields = [
        "table_id", "observation_year", "accounting_scope",
        "plan_type_normalized", "component_normalized", "unit", "basis",
        "first_available_vintage", "latest_available_vintage", "vintage_count",
        "first_value", "latest_value", "first_to_latest_change",
        "first_to_latest_pct_change", "number_of_intervintage_changes",
        "max_absolute_intervintage_revision", "status_assignment",
        "preferred_vintage",
    ]
    write_csv(OUTDIR / "trustees_control_series_summary.csv", series, series_fields)

    write_csv(
        OUTDIR / "trustees_control_year_vintage_matrix.csv",
        matrix,
        [
            "table_id", "observation_year", "trustees_vintage",
            "numeric_observation_count", "status_assignment", "preferred_vintage",
        ],
    )

    write_csv(
        OUTDIR / "trustees_status_source_evidence.csv",
        evidence,
        [
            "trustees_vintage", "table_id", "status_term", "matched_text",
            "source_file", "source_sha256", "source_page", "context",
            "status_assignment",
        ],
    )

    write_csv(
        OUTDIR / "trustees_status_profiler_errors.csv",
        errors,
        [
            "trustees_vintage", "source_file", "table_id",
            "page_number", "error",
        ],
    )

    # Diagnostics, not status decisions.
    status_counts: dict[tuple, int] = defaultdict(int)
    for r in evidence:
        status_counts[(r["table_id"], r["status_term"])] += 1

    focus_raw_count = sum(
        1 for r in raw
        if r.get("table_id") in FOCUS_TABLES
        and r.get("value_status", "").startswith("NUMERIC")
        and int(r["observation_year"]) in FOCUS_YEARS
    )

    checks = [
        ("Validated raw v0.2 control file readable", RAW.exists()),
        ("Annual reports 2015-2026 present", len(missing_reports) == 0),
        ("IV.C2 focus observations represented", any(r["table_id"] == "IV.C2" for r in evolution)),
        ("IV.C3 focus observations represented", any(r["table_id"] == "IV.C3" for r in evolution)),
        ("Every evolution row remains status-unassigned",
         all(r["observation_status"] == "UNASSIGNED" for r in evolution)),
        ("Every evolution row remains preferred-vintage-unassigned",
         all(r["preferred_vintage"] == "UNASSIGNED" for r in evolution)),
        ("Source-status evidence collected for IV.C2",
         any(r["table_id"] == "IV.C2" for r in evidence)),
        ("Source-status evidence collected for IV.C3",
         any(r["table_id"] == "IV.C3" for r in evidence)),
        ("Profile/read errors", len(errors) == 0),
    ]
    overall = all(ok for _, ok in checks)

    lines = [
        "=" * 110,
        "CMS MEDICARE TRUSTEES STATUS / VINTAGE-EVOLUTION PROFILER v0.1",
        "=" * 110,
        "",
        "BOUNDARY",
        "Evidence profiling only. No observation-status assignment and no preferred-vintage selection.",
        "",
        f"Validated raw focus observations          : {focus_raw_count:,}",
        f"Vintage-evolution rows                    : {len(evolution):,}",
        f"Distinct longitudinal series              : {len(series):,}",
        f"Year-vintage coverage rows                : {len(matrix):,}",
        f"Status-source evidence contexts           : {len(evidence):,}",
        f"Profile/read errors                       : {len(errors):,}",
        "",
        "STATUS VOCABULARY CONTEXT COUNTS",
        "-" * 110,
    ]
    for table in ("IV.C2", "IV.C3"):
        pieces = []
        for label, _ in STATUS_PATTERNS:
            pieces.append(f"{label}={status_counts.get((table, label), 0)}")
        lines.append(f"{table:<7} " + "  ".join(pieces))

    lines += ["", "VALIDATION CHECKS", "-" * 110]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)
    lines += [
        "",
        f"OVERALL PROFILER STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "A PASS means the validated Trustees observations have been organized longitudinally and",
        "source text relevant to historical/actual/estimate/projected terminology has been preserved.",
        "It does NOT establish the status of any individual numeric observation and does NOT choose",
        "a preferred Trustees vintage. Those are the next evidence-based methodological decisions.",
        "",
        "OUTPUTS",
        "-" * 110,
        str(OUTDIR / "trustees_control_vintage_evolution.csv"),
        str(OUTDIR / "trustees_control_series_summary.csv"),
        str(OUTDIR / "trustees_control_year_vintage_matrix.csv"),
        str(OUTDIR / "trustees_status_source_evidence.csv"),
        str(OUTDIR / "trustees_status_profiler_errors.csv"),
    ]

    summary = OUTDIR / "trustees_status_vintage_evolution_summary.txt"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
