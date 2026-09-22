#!/usr/bin/env python3
"""
CMS Medicare Trustees incurred-boundary evidence extractor v0.1
===============================================================

WCFFBP evidence gate.

Purpose
-------
For each preserved Medicare Trustees annual report (2015-2026), identify and
preserve source text that explicitly describes the calendar-year boundary
between private-plan values "determined on an incurred basis" and subsequent
estimated/projected values.

This script is intentionally conservative:
* No observation-status assignment.
* No preferred-vintage selection.
* No inference that report vintage minus one is the boundary.
* No imputation when a boundary sentence cannot be established.
* No reconciliation and no database writes.
* Every proposed boundary must be supported by source text containing both
  incurred-basis language and an explicit calendar-year range/end year.

Run from repository root:
    python scripts/extract_cms_medicare_trustees_incurred_boundary_evidence_v0_1.py
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any, Optional

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees"
REPORT_DIR = BASE / "reports"
OUTDIR = BASE / "validation" / "incurred_boundary_evidence_v0_1"
VINTAGES = list(range(2015, 2027))

# We are looking for the methodological prose around private-plan per-capita
# benchmarks/bids/rebates, not merely any occurrence of "incurred."
PRIVATE_PLAN_ANCHORS = [
    re.compile(r"private health plan", re.I),
    re.compile(r"per[- ]capita", re.I),
    re.compile(r"\bbenchmark", re.I),
    re.compile(r"\bbid(?:s)?\b", re.I),
    re.compile(r"\brebate(?:s)?\b", re.I),
]

INCURRED_PHRASES = [
    re.compile(r"determined\s+on\s+an?\s+incurred\s+basis", re.I),
    re.compile(r"on\s+an?\s+incurred\s+basis", re.I),
    re.compile(r"incurred\s+basis", re.I),
]

ESTIMATE_TERMS = re.compile(
    r"\b(?:estimate|estimated|estimates|projected|projection|projections|forecast|forecasts)\b",
    re.I,
)

YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

# Common source constructions, deliberately allowing prose between the
# calendar-year phrase and the end year.
RANGE_PATTERNS = [
    re.compile(
        r"calendar\s+years?\s+((?:19|20)\d{2})\s*(?:through|to|-|–|—)\s*((?:19|20)\d{2})",
        re.I,
    ),
    re.compile(
        r"(?:for|through)\s+calendar\s+years?\s+((?:19|20)\d{2})\s*(?:through|to|-|–|—)\s*((?:19|20)\d{2})",
        re.I,
    ),
    re.compile(
        r"calendar\s+years?.{0,160}?(?:through|to)\s+((?:19|20)\d{2})",
        re.I | re.S,
    ),
]

TABLE_C3_RE = re.compile(r"Table\s+IV\.?\s*C\.?\s*3\b", re.I)
TABLE_C4_RE = re.compile(r"Table\s+IV\.?\s*C\.?\s*4\b", re.I)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def report_path(vintage: int) -> Path:
    return REPORT_DIR / f"medicare_trustees_{vintage}.pdf"


def clean(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("\u2010", "-")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def anchor_score(text: str) -> int:
    return sum(1 for p in PRIVATE_PLAN_ANCHORS if p.search(text))


def extract_boundary_from_context(context: str) -> tuple[Optional[int], str]:
    """
    Return an explicit incurred-through year only when the context itself
    supports it.  No vintage arithmetic is used.
    """
    for pat in RANGE_PATTERNS:
        m = pat.search(context)
        if not m:
            continue
        years = [int(x) for x in m.groups() if x and x.isdigit()]
        if years:
            return max(years), m.group(0)

    # Conservative fallback: if "incurred basis" is followed closely by an
    # explicit "through YYYY" construction, accept that end year.
    m = re.search(
        r"incurred\s+basis.{0,240}?\bthrough\s+((?:19|20)\d{2})\b",
        context,
        re.I | re.S,
    )
    if m:
        return int(m.group(1)), m.group(0)

    return None, ""


def extract_report(vintage: int, path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if PdfReader is None:
        return evidence, [{
            "trustees_vintage": vintage,
            "source_file": str(path.relative_to(ROOT)),
            "page_number": "",
            "error": "pypdf is not installed",
        }]

    digest = sha256_file(path)
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        return evidence, [{
            "trustees_vintage": vintage,
            "source_file": str(path.relative_to(ROOT)),
            "page_number": "",
            "error": f"{type(exc).__name__}: {exc}",
        }]

    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(clean(page.extract_text() or ""))
        except Exception as exc:
            pages.append("")
            errors.append({
                "trustees_vintage": vintage,
                "source_file": str(path.relative_to(ROOT)),
                "page_number": i + 1,
                "error": f"page extraction {type(exc).__name__}: {exc}",
            })

    # Search each explicit incurred-basis phrase.  Include adjacent page text
    # because the methodological paragraph may straddle a page boundary.
    for i, page in enumerate(pages):
        for phrase_pat in INCURRED_PHRASES:
            for hit in phrase_pat.finditer(page):
                prev_tail = pages[i - 1][-2500:] if i > 0 else ""
                next_head = pages[i + 1][:2500] if i + 1 < len(pages) else ""
                local_start = max(0, hit.start() - 1800)
                local_end = min(len(page), hit.end() + 2600)
                context = prev_tail + "\n" + page[local_start:local_end] + "\n" + next_head
                context_one_line = compact(context)

                score = anchor_score(context_one_line)
                incurred_through, boundary_match = extract_boundary_from_context(context_one_line)

                # Capture whether the same context contains estimate/projected
                # language, but do not assign the first projected year.
                estimate_terms = sorted(set(
                    m.group(0).lower() for m in ESTIMATE_TERMS.finditer(context_one_line)
                ))

                evidence.append({
                    "trustees_vintage": vintage,
                    "source_file": str(path.relative_to(ROOT)),
                    "source_sha256": digest,
                    "source_page": i + 1,
                    "matched_incurred_phrase": hit.group(0),
                    "private_plan_anchor_score": score,
                    "explicit_incurred_through_year": (
                        "" if incurred_through is None else incurred_through
                    ),
                    "boundary_match_text": boundary_match,
                    "estimate_projected_terms_in_context": ";".join(estimate_terms),
                    "contains_iv_c3": "YES" if TABLE_C3_RE.search(context_one_line) else "NO",
                    "contains_iv_c4": "YES" if TABLE_C4_RE.search(context_one_line) else "NO",
                    "context": context_one_line,
                    "boundary_status": (
                        "EXPLICIT_CANDIDATE" if incurred_through is not None and score >= 2
                        else "CONTEXT_ONLY"
                    ),
                })

    return evidence, errors


def select_candidates(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Select at most one best explicit candidate per vintage, but label it only
    as a candidate. This is evidence organization, not methodological adoption.
    """
    by_vintage: dict[int, list[dict[str, Any]]] = {}
    for row in evidence:
        by_vintage.setdefault(int(row["trustees_vintage"]), []).append(row)

    rows: list[dict[str, Any]] = []
    for vintage in VINTAGES:
        candidates = [
            r for r in by_vintage.get(vintage, [])
            if r["boundary_status"] == "EXPLICIT_CANDIDATE"
        ]
        candidates.sort(
            key=lambda r: (
                int(r["private_plan_anchor_score"]),
                1 if r["contains_iv_c3"] == "YES" else 0,
                1 if r["estimate_projected_terms_in_context"] else 0,
            ),
            reverse=True,
        )

        distinct_years = sorted({
            int(r["explicit_incurred_through_year"])
            for r in candidates
            if r["explicit_incurred_through_year"] != ""
        })

        if not candidates:
            rows.append({
                "trustees_vintage": vintage,
                "candidate_status": "NO_EXPLICIT_BOUNDARY_FOUND",
                "explicit_incurred_through_year": "",
                "implied_first_post_boundary_year": "",
                "candidate_count": 0,
                "distinct_candidate_boundary_years": "",
                "candidate_consistency": "NOT_APPLICABLE",
                "source_file": "",
                "source_sha256": "",
                "source_page": "",
                "boundary_match_text": "",
                "context": "",
                "methodological_decision": "UNASSIGNED",
            })
            continue

        best = candidates[0]
        end_year = int(best["explicit_incurred_through_year"])
        rows.append({
            "trustees_vintage": vintage,
            "candidate_status": "EXPLICIT_SOURCE_CANDIDATE",
            "explicit_incurred_through_year": end_year,
            "implied_first_post_boundary_year": end_year + 1,
            "candidate_count": len(candidates),
            "distinct_candidate_boundary_years": ";".join(map(str, distinct_years)),
            "candidate_consistency": (
                "CONSISTENT" if len(distinct_years) == 1 else "CONFLICTING"
            ),
            "source_file": best["source_file"],
            "source_sha256": best["source_sha256"],
            "source_page": best["source_page"],
            "boundary_match_text": best["boundary_match_text"],
            "context": best["context"],
            "methodological_decision": "UNASSIGNED",
        })

    return rows


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print("=" * 112)
    print("CMS MEDICARE TRUSTEES INCURRED-BOUNDARY EVIDENCE EXTRACTOR v0.1")
    print("=" * 112)
    print("No status assignment, preferred-vintage selection, vintage arithmetic inference, reconciliation, or DB writes.\n")

    missing = [report_path(v) for v in VINTAGES if not report_path(v).exists()]
    if missing:
        print("FAIL  Missing preserved annual report(s):")
        for p in missing:
            print(f"      {p}")
        return 1

    evidence: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for vintage in VINTAGES:
        rows, errs = extract_report(vintage, report_path(vintage))
        evidence.extend(rows)
        errors.extend(errs)

    candidates = select_candidates(evidence)

    evidence_fields = [
        "trustees_vintage", "source_file", "source_sha256", "source_page",
        "matched_incurred_phrase", "private_plan_anchor_score",
        "explicit_incurred_through_year", "boundary_match_text",
        "estimate_projected_terms_in_context", "contains_iv_c3", "contains_iv_c4",
        "boundary_status", "context",
    ]
    write_csv(
        OUTDIR / "trustees_incurred_boundary_evidence.csv",
        evidence,
        evidence_fields,
    )

    candidate_fields = [
        "trustees_vintage", "candidate_status",
        "explicit_incurred_through_year", "implied_first_post_boundary_year",
        "candidate_count", "distinct_candidate_boundary_years",
        "candidate_consistency", "source_file", "source_sha256",
        "source_page", "boundary_match_text", "context",
        "methodological_decision",
    ]
    write_csv(
        OUTDIR / "trustees_incurred_boundary_candidates.csv",
        candidates,
        candidate_fields,
    )

    write_csv(
        OUTDIR / "trustees_incurred_boundary_errors.csv",
        errors,
        ["trustees_vintage", "source_file", "page_number", "error"],
    )

    explicit = [
        r for r in candidates
        if r["candidate_status"] == "EXPLICIT_SOURCE_CANDIDATE"
    ]
    missing_boundary = [
        r for r in candidates
        if r["candidate_status"] == "NO_EXPLICIT_BOUNDARY_FOUND"
    ]
    conflicts = [
        r for r in candidates
        if r["candidate_consistency"] == "CONFLICTING"
    ]

    # Diagnostic only. A one-year lag is NOT required for PASS because that
    # would turn our expected result into the validation criterion.
    lag_rows = []
    for r in explicit:
        vintage = int(r["trustees_vintage"])
        end_year = int(r["explicit_incurred_through_year"])
        lag_rows.append((vintage, end_year, vintage - end_year))

    checks = [
        ("Annual reports 2015-2026 present", len(missing) == 0),
        ("Incurred-basis source contexts extracted", len(evidence) > 0),
        ("At least one explicit boundary candidate established", len(explicit) > 0),
        ("No conflicting explicit boundary years within a vintage", len(conflicts) == 0),
        ("Every candidate remains methodological-decision-unassigned",
         all(r["methodological_decision"] == "UNASSIGNED" for r in candidates)),
        ("Profile/read errors", len(errors) == 0),
    ]
    overall = all(ok for _, ok in checks)

    lines = [
        "=" * 112,
        "CMS MEDICARE TRUSTEES INCURRED-BOUNDARY EVIDENCE EXTRACTOR v0.1",
        "=" * 112,
        "",
        "BOUNDARY",
        "Source-evidence extraction only. No observation status or preferred vintage is assigned.",
        "",
        f"Trustees vintages expected                   : {len(VINTAGES)}",
        f"Annual reports present                       : {len(VINTAGES) - len(missing)}",
        f"Incurred-basis contexts                      : {len(evidence):,}",
        f"Vintages with explicit boundary candidate    : {len(explicit)}",
        f"Vintages without explicit boundary candidate : {len(missing_boundary)}",
        f"Vintages with conflicting candidates         : {len(conflicts)}",
        f"Profile/read errors                          : {len(errors)}",
        "",
        "VINTAGE-BY-VINTAGE EXPLICIT SOURCE CANDIDATES",
        "-" * 112,
    ]

    for r in candidates:
        vintage = int(r["trustees_vintage"])
        if r["candidate_status"] == "EXPLICIT_SOURCE_CANDIDATE":
            end_year = int(r["explicit_incurred_through_year"])
            lag = vintage - end_year
            lines.append(
                f"{vintage}: incurred-through={end_year}  "
                f"first-post-boundary={end_year + 1}  "
                f"lag={lag}  candidates={r['candidate_count']}  "
                f"consistency={r['candidate_consistency']}"
            )
        else:
            lines.append(f"{vintage}: NO EXPLICIT BOUNDARY FOUND")

    lines += [
        "",
        "VALIDATION CHECKS",
        "-" * 112,
    ]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)

    lines += [
        "",
        f"OVERALL EVIDENCE-EXTRACTION STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "A PASS means explicit incurred-basis source evidence was preserved without imposing a status rule.",
        "Missing annual boundaries remain evidence gaps; they are not filled by assuming vintage minus one.",
        "The candidate table is therefore an evidentiary input to the next methodological decision, not policy itself.",
        "",
        "OUTPUTS",
        "-" * 112,
        str(OUTDIR / "trustees_incurred_boundary_evidence.csv"),
        str(OUTDIR / "trustees_incurred_boundary_candidates.csv"),
        str(OUTDIR / "trustees_incurred_boundary_errors.csv"),
    ]

    summary = OUTDIR / "trustees_incurred_boundary_summary.txt"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
