#!/usr/bin/env python3
"""
Inspect Medicare Trustees 2021-2022 Private Health Plans status structure.

Read-only diagnostic. It does NOT assign historical/estimate boundaries,
observation status, preferred vintages, or perform reconciliation/DB writes.

Purpose:
- isolate 2021 and 2022 Trustees reports;
- preserve pages in/near Private Health Plans / Section IV.C;
- inventory IV.C2 / IV.C3 headings and status vocabulary;
- expose nearby calendar-year sequences;
- identify literal Historical data / Intermediate estimates labels;
- provide enough source-local context to explain why the v0.3 boundary
  profiler did not resolve these two vintages.

Run from repository root:
  python scripts/inspect_cms_medicare_trustees_2021_2022_status_structure.py
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees"
REPORT_DIR = BASE / "reports"
OUTDIR = BASE / "validation" / "status_structure_2021_2022"
VINTAGES = (2021, 2022)

PRIVATE_RE = re.compile(r"\bPrivate\s+Health\s+Plans\b", re.I)
IVC_RE = re.compile(r"(?:Section\s+)?IV\.?\s*C\b", re.I)
IVC2_RE = re.compile(r"Table\s+IV\.?\s*C\.?\s*2\b", re.I)
IVC3_RE = re.compile(r"Table\s+IV\.?\s*C\.?\s*3\b", re.I)
TABLE_RE = re.compile(r"Table\s+IV\.?\s*C\.?\s*\d+\b", re.I)

TERM_PATTERNS = {
    "HISTORICAL_DATA": re.compile(r"\bHistorical\s+data\b", re.I),
    "HISTORICAL": re.compile(r"\bhistorical\b", re.I),
    "INTERMEDIATE_ESTIMATES": re.compile(r"\bIntermediate\s+estimates?\b", re.I),
    "ESTIMATE": re.compile(r"\bestimat(?:e|ed|es|ing)\b", re.I),
    "PROJECTED": re.compile(r"\bproject(?:ed|ion|ions)\b", re.I),
    "INCURRED": re.compile(r"\bincurred\b", re.I),
    "CALENDAR_YEAR": re.compile(r"\bcalendar\s+year\b", re.I),
    "BID": re.compile(r"\bbid(?:-based)?\b", re.I),
    "REBATE": re.compile(r"\brebate(?:s)?\b", re.I),
    "HMO": re.compile(r"\bHMO\b", re.I),
    "PPO": re.compile(r"\bPPO\b", re.I),
    "LOCAL_CCP": re.compile(r"\bLocal\s+CCP\b", re.I),
    "REGIONAL_PPO": re.compile(r"\bRegional\s+PPO\b", re.I),
}

YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")


def report_path(vintage: int) -> Path:
    return REPORT_DIR / f"medicare_trustees_{vintage}.pdf"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize(s: str) -> str:
    return (
        s.replace("\u00a0", " ")
         .replace("\u2010", "-")
         .replace("\u2011", "-")
         .replace("\u2012", "-")
    )


def compact(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def context(text: str, start: int, end: int, radius: int = 700) -> str:
    return compact(text[max(0, start-radius):min(len(text), end+radius)])


def year_sequence(text: str) -> str:
    years = [int(x) for x in YEAR_RE.findall(text)]
    return ";".join(str(x) for x in years)


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    missing = [report_path(v) for v in VINTAGES if not report_path(v).exists()]
    if missing:
        print("FAIL: missing report(s)")
        for p in missing:
            print(p)
        return 1

    pages_rows = []
    evidence_rows = []
    table_rows = []
    errors = []

    for vintage in VINTAGES:
        path = report_path(vintage)
        digest = sha256(path)
        rel = str(path.relative_to(ROOT))
        reader = PdfReader(str(path))

        texts = []
        for i, page in enumerate(reader.pages, start=1):
            try:
                txt = normalize(page.extract_text() or "")
            except Exception as exc:
                errors.append({
                    "trustees_vintage": vintage,
                    "source_file": rel,
                    "source_page": i,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                txt = ""
            texts.append(txt)

        # Find anchor pages, then include +/- 2 pages to preserve structural context.
        anchors = set()
        for i, txt in enumerate(texts):
            if PRIVATE_RE.search(txt) or IVC2_RE.search(txt) or IVC3_RE.search(txt):
                anchors.add(i)

        selected = set()
        for i in anchors:
            for j in range(max(0, i-2), min(len(texts), i+3)):
                selected.add(j)

        for i in sorted(selected):
            txt = texts[i]
            page_no = i + 1
            labels = []
            if PRIVATE_RE.search(txt): labels.append("PRIVATE_HEALTH_PLANS")
            if IVC_RE.search(txt): labels.append("IV_C")
            if IVC2_RE.search(txt): labels.append("IV_C2")
            if IVC3_RE.search(txt): labels.append("IV_C3")

            pages_rows.append({
                "trustees_vintage": vintage,
                "source_file": rel,
                "source_sha256": digest,
                "source_page": page_no,
                "anchor_labels": ";".join(labels),
                "years_on_page": year_sequence(txt),
                "page_text": compact(txt),
            })

            for term, pat in TERM_PATTERNS.items():
                for m in pat.finditer(txt):
                    ctx = context(txt, m.start(), m.end())
                    evidence_rows.append({
                        "trustees_vintage": vintage,
                        "source_file": rel,
                        "source_sha256": digest,
                        "source_page": page_no,
                        "term": term,
                        "match_text": compact(m.group(0)),
                        "nearby_years": year_sequence(ctx),
                        "local_context": ctx,
                    })

            for m in TABLE_RE.finditer(txt):
                ctx = context(txt, m.start(), m.end(), radius=1200)
                table_rows.append({
                    "trustees_vintage": vintage,
                    "source_file": rel,
                    "source_sha256": digest,
                    "source_page": page_no,
                    "table_label": compact(m.group(0)),
                    "has_private_health_plans": bool(PRIVATE_RE.search(ctx)),
                    "has_historical_data": bool(TERM_PATTERNS["HISTORICAL_DATA"].search(ctx)),
                    "has_intermediate_estimates": bool(TERM_PATTERNS["INTERMEDIATE_ESTIMATES"].search(ctx)),
                    "has_incurred": bool(TERM_PATTERNS["INCURRED"].search(ctx)),
                    "has_calendar_year": bool(TERM_PATTERNS["CALENDAR_YEAR"].search(ctx)),
                    "nearby_years": year_sequence(ctx),
                    "table_context": ctx,
                })

    write_csv(
        OUTDIR / "trustees_2021_2022_private_plan_pages.csv",
        pages_rows,
        [
            "trustees_vintage","source_file","source_sha256","source_page",
            "anchor_labels","years_on_page","page_text"
        ],
    )
    write_csv(
        OUTDIR / "trustees_2021_2022_status_term_evidence.csv",
        evidence_rows,
        [
            "trustees_vintage","source_file","source_sha256","source_page",
            "term","match_text","nearby_years","local_context"
        ],
    )
    write_csv(
        OUTDIR / "trustees_2021_2022_ivc_table_inventory.csv",
        table_rows,
        [
            "trustees_vintage","source_file","source_sha256","source_page",
            "table_label","has_private_health_plans","has_historical_data",
            "has_intermediate_estimates","has_incurred","has_calendar_year",
            "nearby_years","table_context"
        ],
    )
    write_csv(
        OUTDIR / "trustees_2021_2022_status_structure_errors.csv",
        errors,
        ["trustees_vintage","source_file","source_page","error"],
    )

    # Literal-label diagnostic: report only, never infer.
    summary = []
    summary.append("=" * 120)
    summary.append("CMS MEDICARE TRUSTEES 2021-2022 PRIVATE HEALTH PLANS STATUS-STRUCTURE DIAGNOSTIC")
    summary.append("=" * 120)
    summary.append("")
    summary.append("READ-ONLY: no boundary/status/preferred-vintage assignment, inference, imputation, reconciliation, or DB writes.")
    summary.append("")
    summary.append(f"Selected Private Health Plans / IV.C neighborhood pages : {len(pages_rows)}")
    summary.append(f"Status/structure term evidence rows                      : {len(evidence_rows)}")
    summary.append(f"IV.C table inventory rows                                : {len(table_rows)}")
    summary.append(f"Read errors                                               : {len(errors)}")
    summary.append("")
    summary.append("VINTAGE DIAGNOSTICS")
    summary.append("-" * 120)

    for vintage in VINTAGES:
        ev = [r for r in evidence_rows if r["trustees_vintage"] == vintage]
        tabs = [r for r in table_rows if r["trustees_vintage"] == vintage]
        terms = {r["term"] for r in ev}
        summary.append(
            f"{vintage}: pages={sum(r['trustees_vintage']==vintage for r in pages_rows)} "
            f"tables={len(tabs)} "
            f"HistoricalData={'YES' if 'HISTORICAL_DATA' in terms else 'NO'} "
            f"IntermediateEstimates={'YES' if 'INTERMEDIATE_ESTIMATES' in terms else 'NO'} "
            f"Incurred={'YES' if 'INCURRED' in terms else 'NO'} "
            f"CalendarYear={'YES' if 'CALENDAR_YEAR' in terms else 'NO'}"
        )
        for t in tabs:
            summary.append(
                f"  page {t['source_page']} {t['table_label']}: "
                f"historical={t['has_historical_data']} "
                f"intermediate={t['has_intermediate_estimates']} "
                f"incurred={t['has_incurred']} "
                f"calendar_year={t['has_calendar_year']}"
            )

    checks = [
        ("Both preserved reports present", len(missing) == 0),
        ("Private Health Plans / IV.C neighborhood pages captured", len(pages_rows) > 0),
        ("Status/structure vocabulary inventoried", len(evidence_rows) > 0),
        ("IV.C tables inventoried", len(table_rows) > 0),
        ("Read errors", len(errors) == 0),
    ]
    overall = all(ok for _, ok in checks)

    summary.append("")
    summary.append("VALIDATION CHECKS")
    summary.append("-" * 120)
    for label, ok in checks:
        summary.append(f"{'PASS' if ok else 'FAIL'}  {label}")
    summary.append("")
    summary.append(f"OVERALL DIAGNOSTIC STATUS: {'PASS' if overall else 'FAIL'}")
    summary.append("")
    summary.append("INTERPRETATION")
    summary.append("PASS means the diagnostic successfully exposed source-local 2021-2022 structure.")
    summary.append("It does NOT mean a historical/estimate boundary has been established.")
    summary.append("Any subsequent boundary must be supported by explicit source structure reviewed from these outputs.")
    summary.append("")
    summary.append("OUTPUTS")
    summary.append("-" * 120)
    for name in (
        "trustees_2021_2022_private_plan_pages.csv",
        "trustees_2021_2022_status_term_evidence.csv",
        "trustees_2021_2022_ivc_table_inventory.csv",
        "trustees_2021_2022_status_structure_errors.csv",
    ):
        summary.append(str(OUTDIR / name))

    summary_path = OUTDIR / "trustees_2021_2022_status_structure_summary.txt"
    summary_path.write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
