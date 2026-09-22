#!/usr/bin/env python3
"""
CMS Medicare Trustees Private Health Plans historical/estimate boundary profiler v0.3
======================================================================================

WCFFBP evidence gate following v0.2 PASS and targeted evidence review.

Purpose
-------
Extract source-defined "Historical data" -> "Intermediate estimates" boundaries
inside Medicare Trustees PRIVATE HEALTH PLANS / Section IV.C context.

v0.3 makes one surgical correction to v0.2:
    Do NOT use min()/max() over every year in a long post-/pre-label window.
    Instead, identify the calendar-year TABLE SEQUENCE adjacent to each label.

This prevents downstream footnote years (e.g., "payments ... in 2005-2007")
from redefining an Intermediate estimates boundary whose tabular series
actually begins in 2015/2016/2017.

Conservative boundaries
-----------------------
* Private Health Plans / IV.C anchored only.
* Literal "Historical data" and "Intermediate estimates" labels only.
* Adjacent table-year sequences only.
* No generic estimated/projected prose.
* No vintage arithmetic inference.
* No incurred-basis evidence mixed into this channel.
* Conflicts remain unresolved.
* No observation-status assignment.
* No preferred-vintage selection.
* No imputation, reconciliation, or DB writes.

Run from repository root:
    python scripts/profile_cms_medicare_trustees_historical_estimate_boundary_v0_3.py
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
OUTDIR = BASE / "validation" / "historical_estimate_boundary_v0_3"
VINTAGES = list(range(2015, 2027))

YEAR_TOKEN_RE = re.compile(r"\b((?:19|20)\d{2})\b")
HIST_LABEL_RE = re.compile(r"\bHistorical\s+data\s*:?", re.I)
EST_LABEL_RE = re.compile(r"\bIntermediate\s+estimates?\s*:?", re.I)

PRIVATE_HEALTH_PLANS_RE = re.compile(r"\bPrivate\s+Health\s+Plans\b", re.I)
SECTION_IVC_RE = re.compile(
    r"(?:Section\s+)?IV\.?\s*C\b|Table\s+IV\.?\s*C\.?\s*[234]\b",
    re.I,
)
IVC_TABLE_RE = re.compile(r"Table\s+IV\.?\s*C\.?\s*[234]\b", re.I)

PART_D_RE = re.compile(r"\bPart\s+D\b|prescription\s+drug", re.I)
IVB_RE = re.compile(
    r"(?:Section\s+)?IV\.?\s*B\b|Table\s+IV\.?\s*B\.?\s*\d+\b",
    re.I,
)
NEXT_MAJOR_SECTION_RE = re.compile(
    r"(?:Section\s+)?IV\.?\s*[DEFG]\b|\bV\.\s+[A-Z]|\bAppendix\b",
    re.I,
)

# Text that commonly marks a transition from table body to footnotes/prose.
FOOTNOTE_MARKER_RE = re.compile(
    r"(?:\bNote\s*:|\bNotes\s*:|\bSource\s*:|\bSources\s*:|"
    r"\bAmounts?\s+shown\b|\bAmounts?\s+do\s+not\b|"
    r"\bIncludes?\b|\bExcludes?\b|\bBeginning\s+with\b|"
    r"\bFor\s+purposes?\s+of\b|\bTotals?\s+may\b)",
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
    has_private = bool(PRIVATE_HEALTH_PLANS_RE.search(page_text))
    has_ivc = bool(SECTION_IVC_RE.search(page_text))
    if has_private and has_ivc:
        return True, "PRIVATE_HEALTH_PLANS_AND_IVC"
    if has_private:
        return True, "PRIVATE_HEALTH_PLANS_HEADING"
    if has_ivc:
        return True, "IVC_SECTION_OR_TABLE"
    return False, "NO_PRIVATE_HEALTH_PLANS_OR_IVC_ANCHOR"


def year_positions(text: str) -> list[tuple[int, int]]:
    return [(m.start(), int(m.group(1))) for m in YEAR_TOKEN_RE.finditer(text)]


def adjacent_year_sequence_after(text: str) -> tuple[list[int], str]:
    """
    Identify the first calendar-year table sequence after a label.

    Key v0.3 property:
    once a plausible increasing table sequence has begun, a later backward
    jump is treated as leaving the table sequence (typically a footnote), not
    as a new candidate minimum.

    Returns (sequence, diagnostic_rule).
    """
    scan = text[:1800]
    marker = FOOTNOTE_MARKER_RE.search(scan)
    marker_pos = marker.start() if marker else None
    toks = year_positions(scan)

    seq: list[int] = []
    last_pos = None

    for pos, year in toks:
        if marker_pos is not None and pos >= marker_pos and seq:
            break

        if not seq:
            # A report table's estimate sequence should be reasonably close to
            # the report era. This is deliberately broad; it is NOT a
            # vintage-minus-one rule.
            if 2000 <= year <= 2100:
                seq = [year]
                last_pos = pos
            continue

        # If years are separated by a very large prose gap, the table sequence
        # has likely ended.
        if last_pos is not None and pos - last_pos > 260:
            break

        prev = seq[-1]

        # Normal table chronology. Repeated year can occur in PDF extraction;
        # allow it without duplicating.
        if year == prev:
            last_pos = pos
            continue
        if year == prev + 1:
            seq.append(year)
            last_pos = pos
            continue

        # Some extracted tables skip a displayed year due layout; permit a
        # small forward jump but never a backward jump.
        if prev < year <= prev + 3:
            seq.append(year)
            last_pos = pos
            continue

        # A backward year (e.g. 2005 after a 2015-2024 series) is a structural
        # boundary/footnote signal, not a candidate estimate start.
        break

    return sorted(set(seq)), "FIRST_FORWARD_TABLE_SEQUENCE_AFTER_LABEL"


def adjacent_year_sequence_before(text: str) -> tuple[list[int], str]:
    """
    Identify the last calendar-year table sequence immediately before a label.

    Work backward from the label, then return the sequence chronologically.
    A backward scan encountering a forward jump in calendar time terminates,
    symmetrically preventing unrelated earlier prose years from entering.
    """
    scan = text[-1800:]
    toks = year_positions(scan)

    rev_seq: list[int] = []
    last_pos = None

    for pos, year in reversed(toks):
        if not rev_seq:
            if 2000 <= year <= 2100:
                rev_seq = [year]
                last_pos = pos
            continue

        if last_pos is not None and last_pos - pos > 260:
            break

        later = rev_seq[-1]

        if year == later:
            last_pos = pos
            continue
        if year == later - 1:
            rev_seq.append(year)
            last_pos = pos
            continue
        if later - 3 <= year < later:
            rev_seq.append(year)
            last_pos = pos
            continue

        break

    seq = sorted(set(rev_seq))
    return seq, "LAST_FORWARD_TABLE_SEQUENCE_BEFORE_LABEL"


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

    for hm in HIST_LABEL_RE.finditer(text):
        em = EST_LABEL_RE.search(text, hm.end())
        if not em:
            continue
        if em.start() - hm.end() > 1800:
            continue

        left_start = max(0, hm.start() - 1800)
        right_end = min(len(text), em.end() + 1800)

        next_hist = HIST_LABEL_RE.search(text, em.end())
        if next_hist and next_hist.start() < right_end:
            right_end = next_hist.start()

        next_section = NEXT_MAJOR_SECTION_RE.search(text, em.end())
        if next_section and next_section.start() < right_end:
            right_end = next_section.start()

        pre_label_context = text[left_start:hm.start()]
        between_labels = text[hm.end():em.start()]
        post_est_context = text[em.end():right_end]
        local_context = text[left_start:right_end]

        local_ivc = bool(
            IVC_TABLE_RE.search(local_context)
            or PRIVATE_HEALTH_PLANS_RE.search(local_context)
        )
        contaminated = bool(
            PART_D_RE.search(local_context) or IVB_RE.search(local_context)
        )

        if contaminated and not local_ivc:
            rows.append({
                "trustees_vintage": vintage,
                "source_file": source_file,
                "source_sha256": digest,
                "source_page": page_number,
                "anchor_rule": anchor_rule,
                "candidate_status": "REJECTED",
                "rejection_reason": "LOCAL_PART_D_OR_IVB_WITHOUT_IVC_PRIVATE_ANCHOR",
                "historical_year_sequence": "",
                "estimate_year_sequence": "",
                "historical_through_year": "",
                "estimate_from_year": "",
                "contiguous_boundary": "",
                "historical_sequence_rule": "",
                "estimate_sequence_rule": "",
                "historical_segment": compact(between_labels),
                "estimate_segment": compact(post_est_context),
                "local_context": compact(local_context),
            })
            continue

        # Historical sequence: in many Trustees tables, years follow the
        # Historical data label and precede Intermediate estimates. Prefer that
        # segment. If PDF ordering places years immediately before the label,
        # use the symmetric before-label sequence as a fallback.
        hist_after, hist_after_rule = adjacent_year_sequence_after(between_labels)
        hist_before, hist_before_rule = adjacent_year_sequence_before(pre_label_context)

        if hist_after:
            hist_seq = hist_after
            hist_rule = "FIRST_TABLE_SEQUENCE_BETWEEN_LABELS"
        else:
            hist_seq = hist_before
            hist_rule = hist_before_rule

        est_seq, est_rule = adjacent_year_sequence_after(post_est_context)

        hist_through = max(hist_seq) if hist_seq else None
        estimate_from = min(est_seq) if est_seq else None

        if hist_through is None or estimate_from is None:
            status = "CONTEXT_ONLY"
            reason = "MISSING_ADJACENT_TABLE_YEAR_SEQUENCE"
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
            "historical_year_sequence": ";".join(map(str, hist_seq)),
            "estimate_year_sequence": ";".join(map(str, est_seq)),
            "historical_through_year": "" if hist_through is None else hist_through,
            "estimate_from_year": "" if estimate_from is None else estimate_from,
            "contiguous_boundary": contiguous,
            "historical_sequence_rule": hist_rule,
            "estimate_sequence_rule": est_rule,
            "historical_segment": compact(between_labels),
            "estimate_segment": compact(post_est_context),
            "local_context": compact(local_context),
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
            "source_file": "" if best is None else best["source_file"],
            "source_sha256": "" if best is None else best["source_sha256"],
            "source_page": "" if best is None else best["source_page"],
            "anchor_rule": "" if best is None else best["anchor_rule"],
            "historical_year_sequence": "" if best is None else best["historical_year_sequence"],
            "estimate_year_sequence": "" if best is None else best["estimate_year_sequence"],
            "historical_segment": "" if best is None else best["historical_segment"],
            "estimate_segment": "" if best is None else best["estimate_segment"],
            "observation_status_assignment": "UNASSIGNED",
            "preferred_vintage": "UNASSIGNED",
        })

    return out


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print("=" * 120)
    print("CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS HISTORICAL/ESTIMATE BOUNDARY PROFILER v0.3")
    print("=" * 120)
    print(
        "Literal Historical data -> Intermediate estimates partitions in IV.C/Private Health Plans context.\n"
        "v0.3 uses adjacent table-year sequences so downstream footnote years cannot redefine boundaries.\n"
        "No status assignment, preferred-vintage selection, vintage arithmetic inference, reconciliation,\n"
        "imputation, or DB writes.\n"
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
            "historical_year_sequence", "estimate_year_sequence",
            "historical_through_year", "estimate_from_year",
            "contiguous_boundary", "historical_sequence_rule",
            "estimate_sequence_rule", "historical_segment",
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
            "source_file", "source_sha256", "source_page", "anchor_rule",
            "historical_year_sequence", "estimate_year_sequence",
            "historical_segment", "estimate_segment",
            "observation_status_assignment", "preferred_vintage",
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

    # Diagnostic only: do the resolved boundaries happen to have a consistent
    # report-year relationship? This is reported, never used to create them.
    lags = sorted(set(
        int(r["trustees_vintage"]) - int(r["historical_through_year"])
        for r in resolved
    ))

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
        "CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS HISTORICAL/ESTIMATE BOUNDARY PROFILER v0.3",
        "=" * 120,
        "",
        "BOUNDARY",
        "Literal source table/header partition with adjacent table-year sequences only.",
        "",
        f"Trustees vintages expected                   : {len(VINTAGES)}",
        f"Annual reports present                       : {len(VINTAGES) - len(missing)}",
        f"Header-partition evidence rows               : {len(evidence):,}",
        f"Vintages with explicit contiguous boundary   : {len(resolved)}",
        f"Vintages unresolved                          : {len(unresolved)}",
        f"  conflicting boundary pairs                 : {len(conflicts)}",
        f"  noncontiguous single boundary              : {len(noncontiguous)}",
        f"Resolved historical-through source lags      : {';'.join(map(str, lags)) if lags else 'none'}",
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
        "PASS means the v0.3 adjacent-table-sequence correction behaved conservatively.",
        "Resolved boundaries are source-derived from literal Historical data / Intermediate estimates partitions.",
        "The reported source lag is diagnostic only and was not used to infer any boundary.",
        "Unresolved vintages remain unresolved and require a separate evidence investigation.",
        "No observation-status or preferred-vintage policy is authorized by this script alone.",
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
