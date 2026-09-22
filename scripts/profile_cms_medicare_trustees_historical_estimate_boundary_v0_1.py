#!/usr/bin/env python3
"""
CMS Medicare Trustees historical-vs-estimate boundary profiler v0.1
===================================================================

WCFFBP evidence gate.

Purpose
-------
For each preserved Medicare Trustees annual report (2015-2026), preserve and
profile source evidence that may distinguish Private Health Plans historical
data from intermediate estimates / projections.

This is an independent evidence channel from the incurred-boundary extractor.

Conservative boundaries
-----------------------
* Read-only source profiling.
* No observation-status assignment.
* No preferred-vintage selection.
* No vintage-minus-one inference.
* No imputation.
* No database writes.
* No Washington reconciliation.
* Historical/estimate labels are preserved in source context.
* A proposed year boundary is emitted only when the source locally associates
  a status label with explicit year(s) or a year range.
* Conflicting locally supported boundaries remain UNRESOLVED.

Run from repository root:
    python scripts/profile_cms_medicare_trustees_historical_estimate_boundary_v0_1.py
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees"
REPORT_DIR = BASE / "reports"
OUTDIR = BASE / "validation" / "historical_estimate_boundary_v0_1"
VINTAGES = list(range(2015, 2027))

# Private Health Plans / Part C context.
PRIVATE_RE = re.compile(
    r"private\s+health\s+plan|private[- ]plan|Medicare\s+Advantage|"
    r"local\s+CCP|regional\s+PPO|HMO|PPO|benchmark|rebate|\bbid(?:s)?\b",
    re.I,
)
IVC_RE = re.compile(r"\bIV\.?\s*C\b|Table\s+IV\.?\s*C\.?\s*[234]\b", re.I)

# Reject obvious Part D / IV.B evidence from the boundary channel.
IVB_RE = re.compile(r"\bIV\.?\s*B\b|Table\s+IV\.?\s*B\.?\s*\d+\b", re.I)
PART_D_RE = re.compile(r"\bPart\s+D\b|prescription\s+drug", re.I)

HIST_RE = re.compile(
    r"\b(?:Historical\s+data|historical\s+(?:values?|experience|data)|"
    r"historically)\b",
    re.I,
)
EST_RE = re.compile(
    r"\b(?:Intermediate\s+estimates?|estimated|estimates|"
    r"projected|projections?|forecast|forecasts)\b",
    re.I,
)

YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
YEAR_RANGE_RE = re.compile(
    r"\b((?:19|20)\d{2})\s*(?:through|to|-|–|—)\s*((?:19|20)\d{2})\b",
    re.I,
)

# Direct source constructions that can establish a local boundary.
HIST_THROUGH_PATTERNS = [
    re.compile(
        r"(?:historical\s+data|historical\s+(?:values?|experience|data))"
        r".{0,220}?\bthrough\s+(?:calendar\s+year\s+)?((?:19|20)\d{2})\b",
        re.I | re.S,
    ),
    re.compile(
        r"\bthrough\s+(?:calendar\s+year\s+)?((?:19|20)\d{2})\b"
        r".{0,220}?(?:historical\s+data|historical\s+(?:values?|experience|data))",
        re.I | re.S,
    ),
]

EST_FROM_PATTERNS = [
    re.compile(
        r"(?:intermediate\s+estimates?|estimated|projected)"
        r".{0,220}?\b(?:beginning|starting|from|for)\s+"
        r"(?:calendar\s+year\s+)?((?:19|20)\d{2})\b",
        re.I | re.S,
    ),
    re.compile(
        r"\b(?:beginning|starting|from)\s+(?:calendar\s+year\s+)?"
        r"((?:19|20)\d{2})\b.{0,220}?"
        r"(?:intermediate\s+estimates?|estimated|projected)",
        re.I | re.S,
    ),
]

# Table/header-like constructions, e.g. "Historical data 2010 2011 ... 2018
# Intermediate estimates 2019 2020 ..."
HEADER_PAIR_RE = re.compile(
    r"(Historical\s+data.{0,900}?)(Intermediate\s+estimates?.{0,900})",
    re.I | re.S,
)


def report_path(vintage: int) -> Path:
    return REPORT_DIR / f"medicare_trustees_{vintage}.pdf"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize(text: str) -> str:
    return (
        text.replace("\u00a0", " ")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
    )


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def split_units(text: str) -> list[str]:
    text = compact(text)
    if not text:
        return []
    parts = re.split(
        r"(?<=[.!?])\s+(?=(?:[A-Z]|Table\s+IV|Historical\s+data|Intermediate\s+estimates?))",
        text,
    )
    return [p.strip() for p in parts if p.strip()]


def good_context(text: str) -> tuple[bool, str]:
    if IVB_RE.search(text) or PART_D_RE.search(text):
        return False, "REJECT_PART_D_OR_IVB"
    if IVC_RE.search(text) and PRIVATE_RE.search(text):
        return True, "ACCEPT_IVC_AND_PRIVATE"
    if IVC_RE.search(text):
        return True, "ACCEPT_IVC"
    if PRIVATE_RE.search(text):
        return True, "ACCEPT_PRIVATE_PLAN"
    return False, "REJECT_NO_PRIVATE_PLAN_IVC_CONTEXT"


def years(text: str) -> list[int]:
    return [int(x) for x in YEAR_RE.findall(text)]


def direct_boundary(unit: str) -> tuple[Optional[int], Optional[int], str, str]:
    """
    Return historical-through year, estimate-from year, evidence type, match.
    Either side may be absent. No arithmetic fills the missing side.
    """
    hist_year = None
    est_year = None
    evidence = []
    match_text = []

    for pat in HIST_THROUGH_PATTERNS:
        m = pat.search(unit)
        if m:
            hist_year = int(m.group(1))
            evidence.append("EXPLICIT_HISTORICAL_THROUGH")
            match_text.append(m.group(0))
            break

    for pat in EST_FROM_PATTERNS:
        m = pat.search(unit)
        if m:
            est_year = int(m.group(1))
            evidence.append("EXPLICIT_ESTIMATE_FROM")
            match_text.append(m.group(0))
            break

    # Header/legend pair fallback. Years are partitioned by the actual labels,
    # not by report-vintage arithmetic.
    if hist_year is None or est_year is None:
        m = HEADER_PAIR_RE.search(unit)
        if m:
            hist_years = years(m.group(1))
            est_years = years(m.group(2))
            if hist_year is None and hist_years:
                hist_year = max(hist_years)
                evidence.append("HEADER_HISTORICAL_MAX_YEAR")
            if est_year is None and est_years:
                est_year = min(est_years)
                evidence.append("HEADER_ESTIMATE_MIN_YEAR")
            match_text.append(m.group(0))

    return (
        hist_year,
        est_year,
        ";".join(evidence),
        compact(" | ".join(match_text)),
    )


def extract_report(vintage: int, path: Path):
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

    pages = []
    for idx, page in enumerate(reader.pages):
        try:
            pages.append(normalize(page.extract_text() or ""))
        except Exception as exc:
            pages.append("")
            errors.append({
                "trustees_vintage": vintage,
                "source_file": str(path.relative_to(ROOT)),
                "page_number": idx + 1,
                "error": f"page extraction {type(exc).__name__}: {exc}",
            })

    for page_idx, page in enumerate(pages):
        units = split_units(page)

        # Sentence/prose-unit evidence.
        for idx, unit in enumerate(units):
            if not (HIST_RE.search(unit) or EST_RE.search(unit)):
                continue

            combos = [("SAME_UNIT", unit)]
            if idx > 0:
                combos.append(("PREVIOUS_PLUS_UNIT", units[idx - 1] + " " + unit))
            if idx + 1 < len(units):
                combos.append(("UNIT_PLUS_NEXT", unit + " " + units[idx + 1]))

            local = " ".join(units[max(0, idx - 2):min(len(units), idx + 3)])

            produced = False
            for association, candidate in combos:
                hist_y, est_y, evtype, matched = direct_boundary(candidate)
                if hist_y is None and est_y is None:
                    continue

                ok, rule = good_context(candidate + " " + local)
                evidence.append({
                    "trustees_vintage": vintage,
                    "source_file": str(path.relative_to(ROOT)),
                    "source_sha256": digest,
                    "source_page": page_idx + 1,
                    "association_type": association,
                    "historical_through_year": "" if hist_y is None else hist_y,
                    "estimate_from_year": "" if est_y is None else est_y,
                    "evidence_type": evtype,
                    "context_rule": rule,
                    "candidate_status": "SURVIVES" if ok else "REJECTED",
                    "match_text": matched,
                    "evidence_unit": compact(candidate),
                    "local_context": compact(local),
                })
                produced = produced or ok

            if not produced:
                ok, rule = good_context(unit + " " + local)
                if ok:
                    evidence.append({
                        "trustees_vintage": vintage,
                        "source_file": str(path.relative_to(ROOT)),
                        "source_sha256": digest,
                        "source_page": page_idx + 1,
                        "association_type": "STATUS_CONTEXT_ONLY",
                        "historical_through_year": "",
                        "estimate_from_year": "",
                        "evidence_type": "STATUS_LABEL_WITHOUT_EXPLICIT_LOCAL_YEAR_BOUNDARY",
                        "context_rule": rule,
                        "candidate_status": "CONTEXT_ONLY",
                        "match_text": "",
                        "evidence_unit": compact(unit),
                        "local_context": compact(local),
                    })

        # Also inspect page-local header pairs because PDF table headers may not
        # split into normal sentences.
        for m in HEADER_PAIR_RE.finditer(compact(page)):
            block = m.group(0)
            ok, rule = good_context(block)
            hist_years = years(m.group(1))
            est_years = years(m.group(2))
            evidence.append({
                "trustees_vintage": vintage,
                "source_file": str(path.relative_to(ROOT)),
                "source_sha256": digest,
                "source_page": page_idx + 1,
                "association_type": "PAGE_HEADER_PAIR",
                "historical_through_year": max(hist_years) if hist_years else "",
                "estimate_from_year": min(est_years) if est_years else "",
                "evidence_type": "HEADER_HISTORICAL_ESTIMATE_PAIR",
                "context_rule": rule,
                "candidate_status": (
                    "SURVIVES" if ok and hist_years and est_years else "REJECTED"
                ),
                "match_text": compact(block),
                "evidence_unit": compact(block),
                "local_context": compact(block),
            })

    return evidence, errors


def adjudicate(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_vintage: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence:
        by_vintage[int(row["trustees_vintage"])].append(row)

    out = []
    for vintage in VINTAGES:
        surviving = [
            r for r in by_vintage.get(vintage, [])
            if r["candidate_status"] == "SURVIVES"
            and (
                r["historical_through_year"] != ""
                or r["estimate_from_year"] != ""
            )
        ]

        # Deduplicate exact evidence repeats.
        unique = {}
        for r in surviving:
            key = (
                r["historical_through_year"],
                r["estimate_from_year"],
                r["source_page"],
                r["match_text"],
            )
            unique[key] = r
        surviving = list(unique.values())

        hist_years = sorted({
            int(r["historical_through_year"])
            for r in surviving if r["historical_through_year"] != ""
        })
        est_years = sorted({
            int(r["estimate_from_year"])
            for r in surviving if r["estimate_from_year"] != ""
        })

        hist = hist_years[0] if len(hist_years) == 1 else None
        est = est_years[0] if len(est_years) == 1 else None

        if len(hist_years) > 1 or len(est_years) > 1:
            status = "UNRESOLVED_CONFLICTING_SOURCE_BOUNDARIES"
        elif hist is not None and est is not None:
            if est == hist + 1:
                status = "EXPLICIT_SOURCE_BOUNDARY_PAIR"
            else:
                status = "UNRESOLVED_NONCONTIGUOUS_BOUNDARY_PAIR"
        elif hist is not None:
            status = "PARTIAL_HISTORICAL_THROUGH_ONLY"
        elif est is not None:
            status = "PARTIAL_ESTIMATE_FROM_ONLY"
        else:
            status = "UNRESOLVED_NO_EXPLICIT_BOUNDARY"

        best = None
        if status in {
            "EXPLICIT_SOURCE_BOUNDARY_PAIR",
            "PARTIAL_HISTORICAL_THROUGH_ONLY",
            "PARTIAL_ESTIMATE_FROM_ONLY",
        }:
            preferred = [
                r for r in surviving
                if (hist is None or r["historical_through_year"] in ("", hist))
                and (est is None or r["estimate_from_year"] in ("", est))
            ]
            preferred.sort(
                key=lambda r: (
                    1 if r["association_type"] == "PAGE_HEADER_PAIR" else 0,
                    1 if "HEADER_HISTORICAL_ESTIMATE_PAIR" in r["evidence_type"] else 0,
                    1 if r["association_type"] == "SAME_UNIT" else 0,
                ),
                reverse=True,
            )
            best = preferred[0] if preferred else None

        out.append({
            "trustees_vintage": vintage,
            "boundary_resolution_status": status,
            "historical_through_year": "" if hist is None else hist,
            "estimate_from_year": "" if est is None else est,
            "surviving_evidence_count": len(surviving),
            "distinct_historical_through_years": ";".join(map(str, hist_years)),
            "distinct_estimate_from_years": ";".join(map(str, est_years)),
            "source_file": "" if best is None else best["source_file"],
            "source_sha256": "" if best is None else best["source_sha256"],
            "source_page": "" if best is None else best["source_page"],
            "evidence_type": "" if best is None else best["evidence_type"],
            "match_text": "" if best is None else best["match_text"],
            "evidence_unit": "" if best is None else best["evidence_unit"],
            "observation_status_assignment": "UNASSIGNED",
            "preferred_vintage": "UNASSIGNED",
        })
    return out


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print("=" * 118)
    print("CMS MEDICARE TRUSTEES HISTORICAL-vs-ESTIMATE BOUNDARY PROFILER v0.1")
    print("=" * 118)
    print(
        "Independent source-evidence channel. No observation-status assignment, preferred-vintage selection, "
        "vintage arithmetic inference, reconciliation, or DB writes.\n"
    )

    missing = [report_path(v) for v in VINTAGES if not report_path(v).exists()]
    if missing:
        print("FAIL  Missing preserved annual report(s):")
        for p in missing:
            print(f"      {p}")
        return 1

    evidence = []
    errors = []
    for vintage in VINTAGES:
        ev, er = extract_report(vintage, report_path(vintage))
        evidence.extend(ev)
        errors.extend(er)

    resolution = adjudicate(evidence)

    write_csv(
        OUTDIR / "trustees_historical_estimate_local_evidence.csv",
        evidence,
        [
            "trustees_vintage", "source_file", "source_sha256", "source_page",
            "association_type", "historical_through_year", "estimate_from_year",
            "evidence_type", "context_rule", "candidate_status", "match_text",
            "evidence_unit", "local_context",
        ],
    )

    write_csv(
        OUTDIR / "trustees_historical_estimate_boundary_resolution.csv",
        resolution,
        [
            "trustees_vintage", "boundary_resolution_status",
            "historical_through_year", "estimate_from_year",
            "surviving_evidence_count", "distinct_historical_through_years",
            "distinct_estimate_from_years", "source_file", "source_sha256",
            "source_page", "evidence_type", "match_text", "evidence_unit",
            "observation_status_assignment", "preferred_vintage",
        ],
    )

    write_csv(
        OUTDIR / "trustees_historical_estimate_boundary_errors.csv",
        errors,
        ["trustees_vintage", "source_file", "page_number", "error"],
    )

    full = [
        r for r in resolution
        if r["boundary_resolution_status"] == "EXPLICIT_SOURCE_BOUNDARY_PAIR"
    ]
    partial = [
        r for r in resolution
        if r["boundary_resolution_status"].startswith("PARTIAL_")
    ]
    conflicts = [
        r for r in resolution
        if r["boundary_resolution_status"].startswith("UNRESOLVED_CONFLICTING")
    ]
    unresolved = [
        r for r in resolution
        if r["boundary_resolution_status"].startswith("UNRESOLVED")
    ]

    checks = [
        ("Annual reports 2015-2026 present", len(missing) == 0),
        ("Historical/estimate evidence surfaces preserved", len(evidence) > 0),
        ("At least one source-supported boundary or partial boundary found",
         len(full) + len(partial) > 0),
        ("Conflicting evidence is not force-resolved", all(
            r["historical_through_year"] == "" and r["estimate_from_year"] == ""
            for r in conflicts
        )),
        ("No observation-status assignments made", all(
            r["observation_status_assignment"] == "UNASSIGNED"
            and r["preferred_vintage"] == "UNASSIGNED"
            for r in resolution
        )),
        ("Profile/read errors", len(errors) == 0),
    ]
    overall = all(ok for _, ok in checks)

    lines = [
        "=" * 118,
        "CMS MEDICARE TRUSTEES HISTORICAL-vs-ESTIMATE BOUNDARY PROFILER v0.1",
        "=" * 118,
        "",
        "BOUNDARY",
        "Independent source evidence only. Missing/conflicting evidence remains unresolved.",
        "",
        f"Trustees vintages expected                   : {len(VINTAGES)}",
        f"Annual reports present                       : {len(VINTAGES) - len(missing)}",
        f"Historical/estimate evidence rows            : {len(evidence):,}",
        f"Vintages with explicit boundary pair         : {len(full)}",
        f"Vintages with partial boundary evidence      : {len(partial)}",
        f"Vintages unresolved                          : {len(unresolved)}",
        f"  of which conflicting                       : {len(conflicts)}",
        f"Profile/read errors                          : {len(errors)}",
        "",
        "VINTAGE-BY-VINTAGE RESOLUTION",
        "-" * 118,
    ]

    for r in resolution:
        vintage = int(r["trustees_vintage"])
        status = r["boundary_resolution_status"]
        hist = r["historical_through_year"] or "?"
        est = r["estimate_from_year"] or "?"
        lines.append(
            f"{vintage}: {status}  historical-through={hist}  "
            f"estimate-from={est}  evidence={r['surviving_evidence_count']}"
        )

    lines += ["", "VALIDATION CHECKS", "-" * 118]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)
    lines += [
        "",
        f"OVERALL PROFILER STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "PASS means the historical-vs-estimate evidence channel was profiled conservatively.",
        "It does not require every vintage to resolve and does not authorize a status policy.",
        "The next step is to compare these results with the independent incurred-boundary evidence",
        "and the previously validated longitudinal revision evidence before adopting any rule.",
        "",
        "OUTPUTS",
        "-" * 118,
        str(OUTDIR / "trustees_historical_estimate_local_evidence.csv"),
        str(OUTDIR / "trustees_historical_estimate_boundary_resolution.csv"),
        str(OUTDIR / "trustees_historical_estimate_boundary_errors.csv"),
    ]

    summary = OUTDIR / "trustees_historical_estimate_boundary_summary.txt"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
