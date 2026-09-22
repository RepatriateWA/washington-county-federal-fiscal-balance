#!/usr/bin/env python3
"""
CMS Medicare Trustees incurred-boundary evidence extractor v0.2
===============================================================

WCFFBP evidence gate following informative v0.1 FAIL.

Purpose
-------
Identify, vintage by vintage, explicit Medicare Trustees source language that
defines the Private Health Plans historical/incurred boundary.

v0.2 is deliberately sentence/paragraph local. It fixes v0.1's overly broad
association of "incurred basis" phrases with unrelated year ranges elsewhere
in a large context window.

Conservative rules
------------------
* No observation-status assignment.
* No preferred-vintage selection.
* No vintage-minus-one inference.
* No imputation.
* No database writes.
* No reconciliation.
* A boundary candidate requires:
    1. incurred-basis language;
    2. an explicit calendar-year range/end year locally associated with it;
    3. Private Health Plans / IV.C context;
    4. no Part D / IV.B contamination in the local evidence unit.
* Conflicting surviving candidates => UNRESOLVED, not guessed.
* Missing explicit evidence => UNRESOLVED.

Run from repository root:
    python scripts/extract_cms_medicare_trustees_incurred_boundary_evidence_v0_2.py
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
OUTDIR = BASE / "validation" / "incurred_boundary_evidence_v0_2"
VINTAGES = list(range(2015, 2027))

INCURRED_RE = re.compile(
    r"(?:determined\s+)?on\s+an?\s+incurred\s+basis|incurred\s+basis",
    re.I,
)

PRIVATE_PLAN_RE = re.compile(
    r"private\s+health\s+plan|private[- ]plan|Medicare\s+Advantage|"
    r"local\s+CCP|regional\s+PPO|HMO|PPO|benchmark|rebate|\bbid(?:s)?\b",
    re.I,
)

IVC_RE = re.compile(r"\bIV\.?\s*C\b|Table\s+IV\.?\s*C\.?\s*[234]\b", re.I)
IVB_RE = re.compile(r"\bIV\.?\s*B\b|Table\s+IV\.?\s*B\.?\s*\d+\b", re.I)
PART_D_RE = re.compile(r"\bPart\s+D\b|prescription\s+drug", re.I)

STATUS_LABEL_RE = re.compile(
    r"\b(?:Historical\s+data|Intermediate\s+estimates?|"
    r"historical|actual|estimated|estimates|projected|projections?)\b",
    re.I,
)

YEAR_RANGE_PATTERNS = [
    re.compile(
        r"calendar\s+years?\s+((?:19|20)\d{2})\s*"
        r"(?:through|to|-|–|—)\s*((?:19|20)\d{2})",
        re.I,
    ),
    re.compile(
        r"calendar\s+year\s+((?:19|20)\d{2})\b",
        re.I,
    ),
    re.compile(
        r"\bthrough\s+calendar\s+year\s+((?:19|20)\d{2})\b",
        re.I,
    ),
]

# A narrow direct-association pattern. This is intentionally stricter than
# merely finding any year somewhere in the paragraph.
DIRECT_ASSOCIATION_PATTERNS = [
    re.compile(
        r"(?:determined\s+)?on\s+an?\s+incurred\s+basis"
        r".{0,180}?"
        r"calendar\s+years?\s+((?:19|20)\d{2})\s*"
        r"(?:through|to|-|–|—)\s*((?:19|20)\d{2})",
        re.I | re.S,
    ),
    re.compile(
        r"calendar\s+years?\s+((?:19|20)\d{2})\s*"
        r"(?:through|to|-|–|—)\s*((?:19|20)\d{2})"
        r".{0,180}?"
        r"(?:determined\s+)?on\s+an?\s+incurred\s+basis",
        re.I | re.S,
    ),
    re.compile(
        r"(?:determined\s+)?on\s+an?\s+incurred\s+basis"
        r".{0,180}?\bthrough\s+((?:19|20)\d{2})\b",
        re.I | re.S,
    ),
]


def report_path(vintage: int) -> Path:
    return REPORT_DIR / f"medicare_trustees_{vintage}.pdf"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_text(text: str) -> str:
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
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def split_units(text: str) -> list[str]:
    """
    Build conservative prose units.

    PDF extraction often inserts line breaks inside sentences. We first
    collapse whitespace, then split primarily at punctuation followed by a
    capital letter/table marker. Units are later combined with one immediate
    neighbor only.
    """
    text = compact(text)
    if not text:
        return []
    parts = re.split(
        r"(?<=[.!?])\s+(?=(?:[A-Z]|Table\s+IV|For\s+calendar|Beginning\s+with))",
        text,
    )
    return [p.strip() for p in parts if p.strip()]


def explicit_boundary(unit: str) -> tuple[Optional[int], str]:
    for pat in DIRECT_ASSOCIATION_PATTERNS:
        m = pat.search(unit)
        if not m:
            continue
        years = [int(g) for g in m.groups() if g]
        if years:
            return max(years), m.group(0)
    return None, ""


def local_context_ok(unit: str, neighborhood: str) -> tuple[bool, str]:
    """
    Require affirmative IV.C/private-plan evidence and reject local IV.B/Part D
    contamination. The direct unit is weighted most heavily; neighborhood is
    used only to establish section context.
    """
    direct_private = bool(PRIVATE_PLAN_RE.search(unit))
    direct_ivc = bool(IVC_RE.search(unit))
    near_private = bool(PRIVATE_PLAN_RE.search(neighborhood))
    near_ivc = bool(IVC_RE.search(neighborhood))

    direct_bad = bool(IVB_RE.search(unit) or PART_D_RE.search(unit))
    near_bad = bool(IVB_RE.search(neighborhood) or PART_D_RE.search(neighborhood))

    if direct_bad:
        return False, "REJECT_DIRECT_PART_D_OR_IVB"
    if direct_private or direct_ivc:
        return True, "ACCEPT_DIRECT_PRIVATE_PLAN_OR_IVC"
    if near_private and near_ivc and not near_bad:
        return True, "ACCEPT_NEARBY_PRIVATE_PLAN_AND_IVC"
    return False, "REJECT_INSUFFICIENT_PRIVATE_PLAN_IVC_CONTEXT"


def extract_report(
    vintage: int, path: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    status_evidence: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if PdfReader is None:
        return candidates, status_evidence, [{
            "trustees_vintage": vintage,
            "source_file": str(path.relative_to(ROOT)),
            "page_number": "",
            "error": "pypdf is not installed",
        }]

    digest = sha256_file(path)
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        return candidates, status_evidence, [{
            "trustees_vintage": vintage,
            "source_file": str(path.relative_to(ROOT)),
            "page_number": "",
            "error": f"{type(exc).__name__}: {exc}",
        }]

    pages: list[str] = []
    for idx, page in enumerate(reader.pages):
        try:
            pages.append(normalize_text(page.extract_text() or ""))
        except Exception as exc:
            pages.append("")
            errors.append({
                "trustees_vintage": vintage,
                "source_file": str(path.relative_to(ROOT)),
                "page_number": idx + 1,
                "error": f"page extraction {type(exc).__name__}: {exc}",
            })

    for page_idx, page_text in enumerate(pages):
        # Include a small amount of adjacent-page text only for section context,
        # not for year extraction.
        units = split_units(page_text)

        for unit_idx, unit in enumerate(units):
            if not INCURRED_RE.search(unit):
                continue

            # Candidate unit may be current sentence plus ONE adjacent sentence.
            combos: list[tuple[str, str]] = [("SAME_UNIT", unit)]
            if unit_idx > 0:
                combos.append(("PREVIOUS_PLUS_UNIT", units[unit_idx - 1] + " " + unit))
            if unit_idx + 1 < len(units):
                combos.append(("UNIT_PLUS_NEXT", unit + " " + units[unit_idx + 1]))

            # Nearby section context, never used to extract the boundary year.
            local_units = units[max(0, unit_idx - 2): min(len(units), unit_idx + 3)]
            neighborhood = " ".join(local_units)

            found_for_hit = False
            for association_type, candidate_unit in combos:
                end_year, matched = explicit_boundary(candidate_unit)
                if end_year is None:
                    continue

                ok, context_rule = local_context_ok(candidate_unit, neighborhood)
                row = {
                    "trustees_vintage": vintage,
                    "source_file": str(path.relative_to(ROOT)),
                    "source_sha256": digest,
                    "source_page": page_idx + 1,
                    "association_type": association_type,
                    "explicit_incurred_through_year": end_year,
                    "boundary_match_text": compact(matched),
                    "context_rule": context_rule,
                    "candidate_status": "SURVIVES" if ok else "REJECTED",
                    "evidence_unit": compact(candidate_unit),
                    "local_section_context": compact(neighborhood),
                }
                candidates.append(row)
                found_for_hit = found_for_hit or ok

            # Preserve unresolved incurred phrase too, so absence of a candidate
            # is auditable rather than silently dropped.
            if not found_for_hit:
                candidates.append({
                    "trustees_vintage": vintage,
                    "source_file": str(path.relative_to(ROOT)),
                    "source_sha256": digest,
                    "source_page": page_idx + 1,
                    "association_type": "NO_LOCAL_BOUNDARY",
                    "explicit_incurred_through_year": "",
                    "boundary_match_text": "",
                    "context_rule": "NO_SURVIVING_LOCAL_ASSOCIATION",
                    "candidate_status": "CONTEXT_ONLY",
                    "evidence_unit": compact(unit),
                    "local_section_context": compact(neighborhood),
                })

        # Independently preserve explicit source status labels in IV.C/private
        # plan context. These are evidence only; they do not classify numbers.
        for m in STATUS_LABEL_RE.finditer(page_text):
            left = max(0, m.start() - 500)
            right = min(len(page_text), m.end() + 800)
            ctx = compact(page_text[left:right])
            if (PRIVATE_PLAN_RE.search(ctx) or IVC_RE.search(ctx)) and not (
                IVB_RE.search(ctx) or PART_D_RE.search(ctx)
            ):
                status_evidence.append({
                    "trustees_vintage": vintage,
                    "source_file": str(path.relative_to(ROOT)),
                    "source_sha256": digest,
                    "source_page": page_idx + 1,
                    "status_label": m.group(0),
                    "context": ctx,
                    "observation_status_assignment": "UNASSIGNED",
                })

    return candidates, status_evidence, errors


def adjudicate(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_vintage: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_vintage[int(row["trustees_vintage"])].append(row)

    out: list[dict[str, Any]] = []
    for vintage in VINTAGES:
        surviving = [
            r for r in by_vintage.get(vintage, [])
            if r["candidate_status"] == "SURVIVES"
            and r["explicit_incurred_through_year"] != ""
        ]

        # Deduplicate repeated extraction of the same textual evidence.
        unique = {}
        for r in surviving:
            key = (
                int(r["explicit_incurred_through_year"]),
                r["source_page"],
                r["boundary_match_text"],
            )
            unique[key] = r
        surviving = list(unique.values())

        years = sorted({
            int(r["explicit_incurred_through_year"]) for r in surviving
        })

        if not years:
            status = "UNRESOLVED_NO_EXPLICIT_LOCAL_BOUNDARY"
            chosen_year: Any = ""
        elif len(years) > 1:
            status = "UNRESOLVED_CONFLICTING_EXPLICIT_BOUNDARIES"
            chosen_year = ""
        else:
            status = "EXPLICIT_SOURCE_BOUNDARY"
            chosen_year = years[0]

        best = None
        if len(years) == 1:
            same_year = [
                r for r in surviving
                if int(r["explicit_incurred_through_year"]) == years[0]
            ]
            # Same-sentence/direct private-plan evidence first.
            same_year.sort(
                key=lambda r: (
                    1 if r["association_type"] == "SAME_UNIT" else 0,
                    1 if r["context_rule"] == "ACCEPT_DIRECT_PRIVATE_PLAN_OR_IVC" else 0,
                ),
                reverse=True,
            )
            best = same_year[0] if same_year else None

        out.append({
            "trustees_vintage": vintage,
            "boundary_resolution_status": status,
            "explicit_incurred_through_year": chosen_year,
            "implied_first_post_boundary_year": (
                "" if chosen_year == "" else int(chosen_year) + 1
            ),
            "surviving_candidate_count": len(surviving),
            "distinct_surviving_boundary_years": ";".join(map(str, years)),
            "source_file": "" if best is None else best["source_file"],
            "source_sha256": "" if best is None else best["source_sha256"],
            "source_page": "" if best is None else best["source_page"],
            "association_type": "" if best is None else best["association_type"],
            "boundary_match_text": "" if best is None else best["boundary_match_text"],
            "evidence_unit": "" if best is None else best["evidence_unit"],
            "methodological_decision": "UNASSIGNED",
            "preferred_vintage": "UNASSIGNED",
        })
    return out


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print("=" * 116)
    print("CMS MEDICARE TRUSTEES INCURRED-BOUNDARY EVIDENCE EXTRACTOR v0.2")
    print("=" * 116)
    print(
        "Sentence/paragraph-local evidence only. No status assignment, preferred-vintage selection, "
        "vintage arithmetic inference, reconciliation, or DB writes.\n"
    )

    missing = [report_path(v) for v in VINTAGES if not report_path(v).exists()]
    if missing:
        print("FAIL  Missing preserved annual report(s):")
        for path in missing:
            print(f"      {path}")
        return 1

    candidates: list[dict[str, Any]] = []
    status_evidence: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for vintage in VINTAGES:
        c, s, e = extract_report(vintage, report_path(vintage))
        candidates.extend(c)
        status_evidence.extend(s)
        errors.extend(e)

    resolution = adjudicate(candidates)

    write_csv(
        OUTDIR / "trustees_incurred_boundary_local_evidence.csv",
        candidates,
        [
            "trustees_vintage", "source_file", "source_sha256", "source_page",
            "association_type", "explicit_incurred_through_year",
            "boundary_match_text", "context_rule", "candidate_status",
            "evidence_unit", "local_section_context",
        ],
    )

    write_csv(
        OUTDIR / "trustees_incurred_boundary_resolution.csv",
        resolution,
        [
            "trustees_vintage", "boundary_resolution_status",
            "explicit_incurred_through_year", "implied_first_post_boundary_year",
            "surviving_candidate_count", "distinct_surviving_boundary_years",
            "source_file", "source_sha256", "source_page", "association_type",
            "boundary_match_text", "evidence_unit",
            "methodological_decision", "preferred_vintage",
        ],
    )

    write_csv(
        OUTDIR / "trustees_private_plan_status_label_evidence.csv",
        status_evidence,
        [
            "trustees_vintage", "source_file", "source_sha256", "source_page",
            "status_label", "context", "observation_status_assignment",
        ],
    )

    write_csv(
        OUTDIR / "trustees_incurred_boundary_errors.csv",
        errors,
        ["trustees_vintage", "source_file", "page_number", "error"],
    )

    resolved = [
        r for r in resolution
        if r["boundary_resolution_status"] == "EXPLICIT_SOURCE_BOUNDARY"
    ]
    conflicts = [
        r for r in resolution
        if r["boundary_resolution_status"]
        == "UNRESOLVED_CONFLICTING_EXPLICIT_BOUNDARIES"
    ]
    unresolved = [
        r for r in resolution
        if r["boundary_resolution_status"].startswith("UNRESOLVED")
    ]

    # PASS is about faithful extraction behavior, not forcing all vintages to
    # resolve. Unresolved years are legitimate evidence outcomes.
    checks = [
        ("Annual reports 2015-2026 present", len(missing) == 0),
        ("Local incurred-basis evidence surfaces preserved", len(candidates) > 0),
        ("At least one explicit source boundary resolved", len(resolved) > 0),
        ("All conflicting boundaries remain unresolved", all(
            r["explicit_incurred_through_year"] == ""
            for r in conflicts
        )),
        ("No methodological decisions assigned", all(
            r["methodological_decision"] == "UNASSIGNED"
            and r["preferred_vintage"] == "UNASSIGNED"
            for r in resolution
        )),
        ("Profile/read errors", len(errors) == 0),
    ]
    overall = all(ok for _, ok in checks)

    lines = [
        "=" * 116,
        "CMS MEDICARE TRUSTEES INCURRED-BOUNDARY EVIDENCE EXTRACTOR v0.2",
        "=" * 116,
        "",
        "BOUNDARY",
        "Strict local source association only. Missing/conflicting evidence remains UNRESOLVED.",
        "",
        f"Trustees vintages expected                   : {len(VINTAGES)}",
        f"Annual reports present                       : {len(VINTAGES) - len(missing)}",
        f"Local incurred evidence rows                 : {len(candidates):,}",
        f"Private-plan status-label evidence rows      : {len(status_evidence):,}",
        f"Vintages with explicit resolved boundary     : {len(resolved)}",
        f"Vintages unresolved                          : {len(unresolved)}",
        f"  of which conflicting explicit boundaries   : {len(conflicts)}",
        f"Profile/read errors                          : {len(errors)}",
        "",
        "VINTAGE-BY-VINTAGE RESOLUTION",
        "-" * 116,
    ]

    for r in resolution:
        vintage = int(r["trustees_vintage"])
        status = r["boundary_resolution_status"]
        if status == "EXPLICIT_SOURCE_BOUNDARY":
            end_year = int(r["explicit_incurred_through_year"])
            lines.append(
                f"{vintage}: RESOLVED  incurred-through={end_year}  "
                f"first-post-boundary={end_year + 1}  "
                f"source-lag={vintage - end_year}  "
                f"surviving-evidence={r['surviving_candidate_count']}"
            )
        else:
            years = r["distinct_surviving_boundary_years"] or "none"
            lines.append(
                f"{vintage}: {status}  surviving-years={years}  "
                f"surviving-evidence={r['surviving_candidate_count']}"
            )

    lines += ["", "VALIDATION CHECKS", "-" * 116]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)
    lines += [
        "",
        f"OVERALL EVIDENCE-EXTRACTION STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "PASS means v0.2 enforced local grammatical/source association and preserved uncertainty.",
        "It does not mean every vintage has a resolved boundary.",
        "A resolved boundary is source-derived; an unresolved boundary is not filled by report-year arithmetic.",
        "No observation-status or preferred-vintage policy is authorized by this script alone.",
        "",
        "OUTPUTS",
        "-" * 116,
        str(OUTDIR / "trustees_incurred_boundary_local_evidence.csv"),
        str(OUTDIR / "trustees_incurred_boundary_resolution.csv"),
        str(OUTDIR / "trustees_private_plan_status_label_evidence.csv"),
        str(OUTDIR / "trustees_incurred_boundary_errors.csv"),
    ]

    summary = OUTDIR / "trustees_incurred_boundary_summary.txt"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
