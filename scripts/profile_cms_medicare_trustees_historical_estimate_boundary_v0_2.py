#!/usr/bin/env python3
"""
CMS Medicare Trustees Private Health Plans historical/estimate boundary profiler v0.2
======================================================================================

WCFFBP evidence gate following v0.1 informative FAIL.

Purpose
-------
Extract only source-defined "Historical data" -> "Intermediate estimates"
boundaries that occur inside the Medicare Trustees PRIVATE HEALTH PLANS /
Section IV.C neighborhood.

This version deliberately narrows the evidence channel:
* Anchors to Section IV.C / Private Health Plans pages.
* Uses literal "Historical data" and "Intermediate estimates" labels.
* Extracts historical years strictly BEFORE the Intermediate estimates label.
* Extracts estimate years strictly AFTER that label.
* Does NOT use generic "estimated" / "projected" prose as boundary evidence.
* Does NOT infer vintage-minus-one or any other report-year formula.
* Does NOT mix incurred-basis evidence into this extraction.
* Conflicts remain unresolved.
* No observation-status assignment.
* No preferred-vintage selection.
* No imputation, reconciliation, or DB writes.

Run from repository root:
    python scripts/profile_cms_medicare_trustees_historical_estimate_boundary_v0_2.py
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees"
REPORT_DIR = BASE / "reports"
OUTDIR = BASE / "validation" / "historical_estimate_boundary_v0_2"
VINTAGES = list(range(2015, 2027))

YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
HIST_LABEL_RE = re.compile(r"\bHistorical\s+data\s*:?", re.I)
EST_LABEL_RE = re.compile(r"\bIntermediate\s+estimates?\s*:?", re.I)

PRIVATE_HEALTH_PLANS_RE = re.compile(r"\bPrivate\s+Health\s+Plans\b", re.I)
SECTION_IVC_RE = re.compile(
    r"(?:Section\s+)?IV\.?\s*C\b|Table\s+IV\.?\s*C\.?\s*[234]\b",
    re.I,
)
IVC_TABLE_RE = re.compile(r"Table\s+IV\.?\s*C\.?\s*[234]\b", re.I)

# Explicit exclusion channel. We do not let a local block whose identity is
# clearly Part D / IV.B qualify merely because it contains MA-related words.
PART_D_RE = re.compile(r"\bPart\s+D\b|prescription\s+drug", re.I)
IVB_RE = re.compile(r"(?:Section\s+)?IV\.?\s*B\b|Table\s+IV\.?\s*B\.?\s*\d+\b", re.I)

# Section headings that can terminate an IV.C neighborhood.
NEXT_MAJOR_SECTION_RE = re.compile(
    r"(?:Section\s+)?IV\.?\s*[DEFG]\b|"
    r"\bV\.\s+[A-Z]|"
    r"\bAppendix\b",
    re.I,
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
        .replace("\u2013", "–")
        .replace("\u2014", "—")
    )


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def page_is_ivc_private(page_text: str) -> tuple[bool, str]:
    """
    Strict page admission. A page must identify itself as Private Health Plans
    or Section/Table IV.C. Generic MA terminology is intentionally insufficient.
    """
    has_private = bool(PRIVATE_HEALTH_PLANS_RE.search(page_text))
    has_ivc = bool(SECTION_IVC_RE.search(page_text))

    if has_private and has_ivc:
        return True, "PRIVATE_HEALTH_PLANS_AND_IVC"
    if has_private:
        return True, "PRIVATE_HEALTH_PLANS_HEADING"
    if has_ivc:
        return True, "IVC_SECTION_OR_TABLE"
    return False, "NO_PRIVATE_HEALTH_PLANS_OR_IVC_ANCHOR"


def extract_partition_candidates(
    vintage: int,
    page_number: int,
    page_text: str,
    source_file: str,
    digest: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    admitted, anchor_rule = page_is_ivc_private(page_text)
    if not admitted:
        return rows

    text = compact(page_text)

    # Find each literal Historical data -> Intermediate estimates pair.
    for hm in HIST_LABEL_RE.finditer(text):
        em = EST_LABEL_RE.search(text, hm.end())
        if not em:
            continue

        # Keep the pair local. If labels are extremely far apart, this is
        # unlikely to be one table/header partition.
        if em.start() - hm.end() > 1800:
            continue

        # Determine local window boundaries without allowing the estimate side
        # to consume arbitrary later tables.
        left_start = max(0, hm.start() - 900)
        right_end = min(len(text), em.end() + 1800)

        # If another Historical data label appears shortly after the estimate
        # label, stop before it: that is likely another table/block.
        next_hist = HIST_LABEL_RE.search(text, em.end())
        if next_hist and next_hist.start() < right_end:
            right_end = next_hist.start()

        # Likewise stop at an obvious next major section.
        next_section = NEXT_MAJOR_SECTION_RE.search(text, em.end())
        if next_section and next_section.start() < right_end:
            right_end = next_section.start()

        before = text[hm.end():em.start()]
        after = text[em.end():right_end]
        context = text[left_start:right_end]

        # Reject locally identified Part D/IV.B blocks unless an explicit IV.C
        # table marker occurs in the same local context.
        local_ivc = bool(IVC_TABLE_RE.search(context) or PRIVATE_HEALTH_PLANS_RE.search(context))
        contaminated = bool(PART_D_RE.search(context) or IVB_RE.search(context))
        if contaminated and not local_ivc:
            rows.append({
                "trustees_vintage": vintage,
                "source_file": source_file,
                "source_sha256": digest,
                "source_page": page_number,
                "anchor_rule": anchor_rule,
                "candidate_status": "REJECTED",
                "rejection_reason": "LOCAL_PART_D_OR_IVB_WITHOUT_IVC_PRIVATE_ANCHOR",
                "historical_years": "",
                "estimate_years": "",
                "historical_through_year": "",
                "estimate_from_year": "",
                "contiguous_boundary": "",
                "historical_segment": compact(before),
                "estimate_segment": compact(after),
                "local_context": compact(context),
            })
            continue

        hist_years = [int(y) for y in YEAR_RE.findall(before)]
        est_years = [int(y) for y in YEAR_RE.findall(after)]

        # Year plausibility is broad and source-driven. We only discard years
        # impossibly far from the report's table horizon, not based on a desired
        # one-year/two-year lag.
        hist_years = sorted(set(y for y in hist_years if 2000 <= y <= vintage + 10))
        est_years = sorted(set(y for y in est_years if 2000 <= y <= vintage + 80))

        hist_through = max(hist_years) if hist_years else None
        estimate_from = min(est_years) if est_years else None

        # Crucial v0.2 rule: the estimate minimum is taken ONLY from text after
        # the Intermediate estimates label. Historical years can never leak into
        # the estimate side.
        if hist_through is None or estimate_from is None:
            status = "CONTEXT_ONLY"
            reason = "MISSING_YEAR_ON_ONE_OR_BOTH_LABEL_SIDES"
            contiguous = ""
        else:
            status = "SURVIVES"
            reason = ""
            contiguous = "YES" if estimate_from == hist_through + 1 else "NO"

        rows.append({
            "trustees_vintage": vintage,
            "source_file": source_file,
            "source_sha256": digest,
            "source_page": page_number,
            "anchor_rule": anchor_rule,
            "candidate_status": status,
            "rejection_reason": reason,
            "historical_years": ";".join(map(str, hist_years)),
            "estimate_years": ";".join(map(str, est_years)),
            "historical_through_year": "" if hist_through is None else hist_through,
            "estimate_from_year": "" if estimate_from is None else estimate_from,
            "contiguous_boundary": contiguous,
            "historical_segment": compact(before),
            "estimate_segment": compact(after),
            "local_context": compact(context),
        })

    return rows


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

    source_file = str(path.relative_to(ROOT))
    digest = sha256_file(path)

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        return evidence, [{
            "trustees_vintage": vintage,
            "source_file": source_file,
            "page_number": "",
            "error": f"{type(exc).__name__}: {exc}",
        }]

    for idx, page in enumerate(reader.pages):
        try:
            text = normalize(page.extract_text() or "")
        except Exception as exc:
            errors.append({
                "trustees_vintage": vintage,
                "source_file": source_file,
                "page_number": idx + 1,
                "error": f"page extraction {type(exc).__name__}: {exc}",
            })
            continue

        evidence.extend(
            extract_partition_candidates(
                vintage=vintage,
                page_number=idx + 1,
                page_text=text,
                source_file=source_file,
                digest=digest,
            )
        )

    return evidence, errors


def adjudicate(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_vintage: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence:
        by_vintage[int(row["trustees_vintage"])].append(row)

    out: list[dict[str, Any]] = []

    for vintage in VINTAGES:
        survivors = [
            r for r in by_vintage.get(vintage, [])
            if r["candidate_status"] == "SURVIVES"
        ]

        # Deduplicate exact boundary/page pairs.
        unique: dict[tuple, dict[str, Any]] = {}
        for r in survivors:
            key = (
                int(r["historical_through_year"]),
                int(r["estimate_from_year"]),
                int(r["source_page"]),
            )
            unique[key] = r
        survivors = list(unique.values())

        pairs = sorted({
            (int(r["historical_through_year"]), int(r["estimate_from_year"]))
            for r in survivors
        })
        contiguous_pairs = [p for p in pairs if p[1] == p[0] + 1]

        if not pairs:
            status = "UNRESOLVED_NO_EXPLICIT_HEADER_BOUNDARY"
            chosen = None
        elif len(pairs) == 1:
            chosen = pairs[0]
            if chosen[1] == chosen[0] + 1:
                status = "EXPLICIT_SOURCE_HEADER_BOUNDARY"
            else:
                status = "UNRESOLVED_NONCONTIGUOUS_HEADER_BOUNDARY"
        else:
            chosen = None
            status = "UNRESOLVED_CONFLICTING_HEADER_BOUNDARIES"

        best = None
        if chosen is not None:
            matching = [
                r for r in survivors
                if (
                    int(r["historical_through_year"]),
                    int(r["estimate_from_year"]),
                ) == chosen
            ]
            matching.sort(
                key=lambda r: (
                    1 if r["anchor_rule"] == "PRIVATE_HEALTH_PLANS_AND_IVC" else 0,
                    1 if r["anchor_rule"] == "IVC_SECTION_OR_TABLE" else 0,
                ),
                reverse=True,
            )
            best = matching[0] if matching else None

        out.append({
            "trustees_vintage": vintage,
            "boundary_resolution_status": status,
            "historical_through_year": "" if chosen is None else chosen[0],
            "estimate_from_year": "" if chosen is None else chosen[1],
            "surviving_candidate_count": len(survivors),
            "distinct_boundary_pairs": ";".join(f"{a}->{b}" for a, b in pairs),
            "contiguous_pair_count": len(contiguous_pairs),
            "source_file": "" if best is None else best["source_file"],
            "source_sha256": "" if best is None else best["source_sha256"],
            "source_page": "" if best is None else best["source_page"],
            "anchor_rule": "" if best is None else best["anchor_rule"],
            "historical_segment": "" if best is None else best["historical_segment"],
            "estimate_segment": "" if best is None else best["estimate_segment"],
            "observation_status_assignment": "UNASSIGNED",
            "preferred_vintage": "UNASSIGNED",
        })

    return out


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print("=" * 120)
    print("CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS HISTORICAL/ESTIMATE BOUNDARY PROFILER v0.2")
    print("=" * 120)
    print(
        "Literal Historical data -> Intermediate estimates partitions in IV.C/Private Health Plans context only.\n"
        "No generic projection prose, status assignment, preferred-vintage selection, vintage arithmetic inference,\n"
        "reconciliation, imputation, or DB writes.\n"
    )

    missing = [report_path(v) for v in VINTAGES if not report_path(v).exists()]
    if missing:
        print("FAIL  Missing preserved annual report(s):")
        for p in missing:
            print(f"      {p}")
        return 1

    evidence: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for vintage in VINTAGES:
        ev, er = extract_report(vintage, report_path(vintage))
        evidence.extend(ev)
        errors.extend(er)

    resolution = adjudicate(evidence)

    write_csv(
        OUTDIR / "trustees_private_health_plans_header_boundary_evidence.csv",
        evidence,
        [
            "trustees_vintage", "source_file", "source_sha256", "source_page",
            "anchor_rule", "candidate_status", "rejection_reason",
            "historical_years", "estimate_years",
            "historical_through_year", "estimate_from_year",
            "contiguous_boundary", "historical_segment",
            "estimate_segment", "local_context",
        ],
    )

    write_csv(
        OUTDIR / "trustees_private_health_plans_header_boundary_resolution.csv",
        resolution,
        [
            "trustees_vintage", "boundary_resolution_status",
            "historical_through_year", "estimate_from_year",
            "surviving_candidate_count", "distinct_boundary_pairs",
            "contiguous_pair_count", "source_file", "source_sha256",
            "source_page", "anchor_rule", "historical_segment",
            "estimate_segment", "observation_status_assignment",
            "preferred_vintage",
        ],
    )

    write_csv(
        OUTDIR / "trustees_private_health_plans_header_boundary_errors.csv",
        errors,
        ["trustees_vintage", "source_file", "page_number", "error"],
    )

    resolved = [
        r for r in resolution
        if r["boundary_resolution_status"] == "EXPLICIT_SOURCE_HEADER_BOUNDARY"
    ]
    conflicts = [
        r for r in resolution
        if r["boundary_resolution_status"] == "UNRESOLVED_CONFLICTING_HEADER_BOUNDARIES"
    ]
    noncontiguous = [
        r for r in resolution
        if r["boundary_resolution_status"] == "UNRESOLVED_NONCONTIGUOUS_HEADER_BOUNDARY"
    ]
    unresolved = [
        r for r in resolution
        if r["boundary_resolution_status"].startswith("UNRESOLVED")
    ]

    checks = [
        ("Annual reports 2015-2026 present", len(missing) == 0),
        ("Literal Private Health Plans historical/estimate evidence preserved", len(evidence) > 0),
        ("At least one explicit contiguous source header boundary established", len(resolved) > 0),
        ("Conflicting boundary pairs remain unresolved", all(
            r["historical_through_year"] == "" and r["estimate_from_year"] == ""
            for r in conflicts
        )),
        ("Noncontiguous single boundaries remain unresolved", all(
            r["boundary_resolution_status"] == "UNRESOLVED_NONCONTIGUOUS_HEADER_BOUNDARY"
            for r in noncontiguous
        )),
        ("No observation-status or preferred-vintage assignments made", all(
            r["observation_status_assignment"] == "UNASSIGNED"
            and r["preferred_vintage"] == "UNASSIGNED"
            for r in resolution
        )),
        ("Profile/read errors", len(errors) == 0),
    ]
    overall = all(ok for _, ok in checks)

    lines = [
        "=" * 120,
        "CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS HISTORICAL/ESTIMATE BOUNDARY PROFILER v0.2",
        "=" * 120,
        "",
        "BOUNDARY",
        "Literal source table/header partition only; uncertainty is preserved.",
        "",
        f"Trustees vintages expected                   : {len(VINTAGES)}",
        f"Annual reports present                       : {len(VINTAGES) - len(missing)}",
        f"Header-partition evidence rows               : {len(evidence):,}",
        f"Vintages with explicit contiguous boundary   : {len(resolved)}",
        f"Vintages unresolved                          : {len(unresolved)}",
        f"  conflicting boundary pairs                 : {len(conflicts)}",
        f"  noncontiguous single boundary              : {len(noncontiguous)}",
        f"Profile/read errors                          : {len(errors)}",
        "",
        "VINTAGE-BY-VINTAGE RESOLUTION",
        "-" * 120,
    ]

    for r in resolution:
        hist = r["historical_through_year"] or "?"
        est = r["estimate_from_year"] or "?"
        pairs = r["distinct_boundary_pairs"] or "none"
        lines.append(
            f"{int(r['trustees_vintage'])}: {r['boundary_resolution_status']}  "
            f"historical-through={hist}  estimate-from={est}  "
            f"surviving={r['surviving_candidate_count']}  pairs={pairs}"
        )

    lines += ["", "VALIDATION CHECKS", "-" * 120]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)
    lines += [
        "",
        f"OVERALL PROFILER STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "PASS means this narrow source-header evidence channel behaved conservatively.",
        "It does not require all vintages to resolve and does not itself assign observation status.",
        "Resolved boundaries come only from literal Historical data / Intermediate estimates partitions",
        "inside admitted Private Health Plans / IV.C source context.",
        "Unresolved years are not filled using report-vintage arithmetic.",
        "",
        "OUTPUTS",
        "-" * 120,
        str(OUTDIR / "trustees_private_health_plans_header_boundary_evidence.csv"),
        str(OUTDIR / "trustees_private_health_plans_header_boundary_resolution.csv"),
        str(OUTDIR / "trustees_private_health_plans_header_boundary_errors.csv"),
    ]

    summary = OUTDIR / "trustees_private_health_plans_header_boundary_summary.txt"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
