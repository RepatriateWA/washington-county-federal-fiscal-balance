#!/usr/bin/env python3
"""
Certify Medicare Trustees Private Health Plans source-status boundaries v0.1
===========================================================================

WCFFBP read-only certification gate.

Combines two independently source-supported evidence mechanisms:

A. Literal "Historical data" -> "Intermediate estimates" table/header
   boundaries already resolved by:
   profile_cms_medicare_trustees_historical_estimate_boundary_v0_3.py

B. 2021/2022 Private Health Plans methodology prose:
   - annual per-capita benchmarks, bids, and rebates "were determined on an
     incurred basis" through an explicit calendar year;
   - benchmark growth for the following year "and later is estimated".

Important:
- Values are EXTRACTED from source evidence, not generated from report-year math.
- The contiguous identity is VALIDATED after extraction; it is not used to
  create either boundary.
- "Actual" is not assigned.
- No preferred vintage is selected.
- No reconciliation, imputation, or DB writes.

Run from repository root:
    python scripts/certify_cms_medicare_trustees_status_boundaries_v0_1.py
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
V03_DIR = BASE / "validation" / "historical_estimate_boundary_v0_3"
V03_RESOLUTION = V03_DIR / "trustees_private_health_plans_header_boundary_resolution.csv"
OUTDIR = BASE / "validation" / "status_boundary_certification_v0_1"
VINTAGES = list(range(2015, 2027))

# Accommodate PDF extraction such as "200 7–2020".
INCURRED_RANGE_RE = re.compile(
    r"Annual\s+per\s+capita\s+benchmarks,\s*bids,\s*and\s+rebates\s+"
    r"were\s+determined\s+on\s+an\s+incurred\s+basis\s+for\s+calendar\s+years\s+"
    r"(20\s*\d{2})\s*[–—-]\s*(20\s*\d{2})",
    re.I,
)
ESTIMATE_FROM_RE = re.compile(
    r"Benchmark\s+growth\s+for\s+years?\s+(20\s*\d{2})\s+and\s+later\s+"
    r"is\s+estimated",
    re.I,
)


def report_path(vintage: int) -> Path:
    return REPORT_DIR / f"medicare_trustees_{vintage}.pdf"


def clean_year(s: str) -> int:
    return int(re.sub(r"\s+", "", s))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def compact(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def extract_2021_2022_prose(vintage: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = report_path(vintage)
    digest = sha256_file(path)
    rel = str(path.relative_to(ROOT))
    reader = PdfReader(str(path))

    evidence = []
    errors = []

    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            errors.append({
                "trustees_vintage": vintage,
                "source_file": rel,
                "source_page": page_no,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        text = text.replace("\u00a0", " ")
        inc_matches = list(INCURRED_RANGE_RE.finditer(text))
        est_matches = list(ESTIMATE_FROM_RE.finditer(text))

        if not inc_matches and not est_matches:
            continue

        for im in inc_matches:
            inc_start = clean_year(im.group(1))
            inc_through = clean_year(im.group(2))

            # Require the estimate statement to occur locally after the incurred
            # statement. This prevents pairing unrelated report sections.
            local_est = None
            for em in est_matches:
                if em.start() >= im.end() and em.start() - im.end() <= 1800:
                    local_est = em
                    break

            if local_est is None:
                evidence.append({
                    "trustees_vintage": vintage,
                    "source_file": rel,
                    "source_sha256": digest,
                    "source_page": page_no,
                    "evidence_type": "INCURRED_METHODOLOGY_PROSE",
                    "candidate_status": "PARTIAL",
                    "incurred_start_year": inc_start,
                    "source_determined_through_year": inc_through,
                    "source_estimate_from_year": "",
                    "source_evidence_text": compact(
                        text[max(0, im.start()-400):min(len(text), im.end()+900)]
                    ),
                })
                continue

            est_from = clean_year(local_est.group(1))
            evidence.append({
                "trustees_vintage": vintage,
                "source_file": rel,
                "source_sha256": digest,
                "source_page": page_no,
                "evidence_type": "INCURRED_AND_ESTIMATED_METHODOLOGY_PROSE",
                "candidate_status": "SURVIVES",
                "incurred_start_year": inc_start,
                "source_determined_through_year": inc_through,
                "source_estimate_from_year": est_from,
                "source_evidence_text": compact(
                    text[max(0, im.start()-450):min(len(text), local_est.end()+700)]
                ),
            })

    return evidence, errors


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print("=" * 120)
    print("CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS STATUS-BOUNDARY CERTIFICATION v0.1")
    print("=" * 120)
    print(
        "Read-only certification from source-resolved header partitions plus explicit 2021/2022 methodology prose.\n"
        "No vintage arithmetic inference, actual-status assignment, preferred-vintage selection, imputation,\n"
        "reconciliation, or DB writes.\n"
    )

    errors: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    certification: list[dict[str, Any]] = []

    if not V03_RESOLUTION.exists():
        print(f"FAIL: missing required v0.3 resolution file:\n{V03_RESOLUTION}")
        return 1

    missing_reports = [v for v in VINTAGES if not report_path(v).exists()]
    if missing_reports:
        print(f"FAIL: missing preserved reports: {missing_reports}")
        return 1

    v03_rows = {int(r["trustees_vintage"]): r for r in read_csv(V03_RESOLUTION)}

    # Evidence channel A: source-resolved literal table/header partitions.
    for vintage in VINTAGES:
        r = v03_rows.get(vintage)
        if not r:
            errors.append({
                "trustees_vintage": vintage,
                "source_file": str(V03_RESOLUTION.relative_to(ROOT)),
                "source_page": "",
                "error": "Vintage missing from v0.3 resolution",
            })
            continue

        if r["boundary_resolution_status"] != "EXPLICIT_SOURCE_HEADER_BOUNDARY":
            continue

        evidence.append({
            "trustees_vintage": vintage,
            "source_file": r["source_file"],
            "source_sha256": r["source_sha256"],
            "source_page": r["source_page"],
            "evidence_type": "HISTORICAL_INTERMEDIATE_HEADER_PARTITION",
            "candidate_status": "SURVIVES",
            "incurred_start_year": "",
            "source_determined_through_year": r["historical_through_year"],
            "source_estimate_from_year": r["estimate_from_year"],
            "source_evidence_text": compact(
                f"Historical segment: {r['historical_segment']} "
                f"Intermediate-estimate segment: {r['estimate_segment']}"
            ),
        })

    # Evidence channel B: source-local methodology prose for the two structural exceptions.
    for vintage in (2021, 2022):
        ev, er = extract_2021_2022_prose(vintage)
        evidence.extend(ev)
        errors.extend(er)

    # Adjudicate from extracted evidence only.
    for vintage in VINTAGES:
        candidates = [
            r for r in evidence
            if int(r["trustees_vintage"]) == vintage
            and r["candidate_status"] == "SURVIVES"
            and str(r["source_determined_through_year"]).strip()
            and str(r["source_estimate_from_year"]).strip()
        ]

        pairs = sorted({
            (
                int(r["source_determined_through_year"]),
                int(r["source_estimate_from_year"]),
            )
            for r in candidates
        })

        if len(pairs) == 1:
            through, est_from = pairs[0]
            status = "SOURCE_RESOLVED"
            matching = [
                r for r in candidates
                if int(r["source_determined_through_year"]) == through
                and int(r["source_estimate_from_year"]) == est_from
            ]
            best = matching[0]
            evidence_types = ";".join(sorted({r["evidence_type"] for r in matching}))
            source_files = ";".join(sorted({r["source_file"] for r in matching}))
            source_pages = ";".join(sorted({str(r["source_page"]) for r in matching}))
            source_hashes = ";".join(sorted({r["source_sha256"] for r in matching}))
            contiguous = est_from == through + 1
            report_lag = vintage - through
        elif len(pairs) == 0:
            through = est_from = None
            status = "UNRESOLVED_NO_SOURCE_BOUNDARY"
            best = None
            evidence_types = source_files = source_pages = source_hashes = ""
            contiguous = False
            report_lag = None
        else:
            through = est_from = None
            status = "UNRESOLVED_CONFLICTING_SOURCE_BOUNDARIES"
            best = None
            evidence_types = ";".join(sorted({r["evidence_type"] for r in candidates}))
            source_files = ";".join(sorted({r["source_file"] for r in candidates}))
            source_pages = ";".join(sorted({str(r["source_page"]) for r in candidates}))
            source_hashes = ";".join(sorted({r["source_sha256"] for r in candidates}))
            contiguous = False
            report_lag = None

        certification.append({
            "trustees_vintage": vintage,
            "resolution_status": status,
            "source_determined_through_year": "" if through is None else through,
            "source_estimate_from_year": "" if est_from is None else est_from,
            "boundary_evidence_type": evidence_types,
            "source_file": source_files,
            "source_page": source_pages,
            "source_sha256": source_hashes,
            "source_evidence_text": "" if best is None else best["source_evidence_text"],
            "contiguous_identity_pass": "YES" if contiguous else "NO",
            "observed_report_lag_years": "" if report_lag is None else report_lag,
            "observation_status_assignment": "UNASSIGNED",
            "preferred_vintage": "UNASSIGNED",
        })

    resolved = [r for r in certification if r["resolution_status"] == "SOURCE_RESOLVED"]
    unresolved = [r for r in certification if r["resolution_status"] != "SOURCE_RESOLVED"]
    channel_a = [r for r in resolved if "HISTORICAL_INTERMEDIATE_HEADER_PARTITION" in r["boundary_evidence_type"]]
    channel_b = [r for r in resolved if "INCURRED_AND_ESTIMATED_METHODOLOGY_PROSE" in r["boundary_evidence_type"]]

    checks = [
        ("All 12 Trustees vintages represented", len(certification) == 12),
        ("All 12 boundaries independently source-resolved", len(resolved) == 12),
        ("No conflicting/unresolved certified vintages", len(unresolved) == 0),
        ("Historical/Intermediate header channel represented", len(channel_a) > 0),
        ("2021/2022 methodology-prose channel represented", {int(r["trustees_vintage"]) for r in channel_b} == {2021, 2022}),
        ("All source-resolved boundaries are contiguous", all(r["contiguous_identity_pass"] == "YES" for r in resolved)),
        ("No observation-status assignments made", all(r["observation_status_assignment"] == "UNASSIGNED" for r in certification)),
        ("No preferred-vintage assignments made", all(r["preferred_vintage"] == "UNASSIGNED" for r in certification)),
        ("Read/certification errors", len(errors) == 0),
    ]
    overall = all(ok for _, ok in checks)

    write_csv(
        OUTDIR / "trustees_status_boundary_source_evidence.csv",
        evidence,
        [
            "trustees_vintage", "source_file", "source_sha256", "source_page",
            "evidence_type", "candidate_status", "incurred_start_year",
            "source_determined_through_year", "source_estimate_from_year",
            "source_evidence_text",
        ],
    )

    write_csv(
        OUTDIR / "trustees_status_boundary_certification.csv",
        certification,
        [
            "trustees_vintage", "resolution_status",
            "source_determined_through_year", "source_estimate_from_year",
            "boundary_evidence_type", "source_file", "source_page", "source_sha256",
            "source_evidence_text", "contiguous_identity_pass",
            "observed_report_lag_years", "observation_status_assignment",
            "preferred_vintage",
        ],
    )

    write_csv(
        OUTDIR / "trustees_status_boundary_certification_errors.csv",
        errors,
        ["trustees_vintage", "source_file", "source_page", "error"],
    )

    lines = [
        "=" * 120,
        "CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS STATUS-BOUNDARY CERTIFICATION v0.1",
        "=" * 120,
        "",
        "CERTIFICATION SCOPE",
        "Source-resolved boundary evidence only. No preferred-vintage or ledger policy is assigned.",
        "",
        f"Trustees vintages expected                 : 12",
        f"Trustees vintages certified                : {len(resolved)}",
        f"Header-partition channel certifications    : {len(channel_a)}",
        f"Methodology-prose channel certifications   : {len(channel_b)}",
        f"Unresolved/conflicting vintages            : {len(unresolved)}",
        f"Errors                                     : {len(errors)}",
        "",
        "VINTAGE-BY-VINTAGE CERTIFICATION",
        "-" * 120,
    ]

    for r in certification:
        through = r["source_determined_through_year"] or "?"
        est = r["source_estimate_from_year"] or "?"
        lines.append(
            f"{r['trustees_vintage']}: {r['resolution_status']}  "
            f"source-determined-through={through}  estimate-from={est}  "
            f"identity={r['contiguous_identity_pass']}  "
            f"evidence={r['boundary_evidence_type'] or 'none'}"
        )

    lines += ["", "VALIDATION CHECKS", "-" * 120]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)
    lines += [
        "",
        f"OVERALL CERTIFICATION STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "PASS means all 12 report vintages have independently source-supported boundaries.",
        "The contiguous relationship is validated after extraction and is never used to generate a boundary.",
        "The term ACTUAL is deliberately not assigned.",
        "Observation status and preferred vintage remain UNASSIGNED pending the next policy gate.",
        "",
        "OUTPUTS",
        "-" * 120,
        str(OUTDIR / "trustees_status_boundary_source_evidence.csv"),
        str(OUTDIR / "trustees_status_boundary_certification.csv"),
        str(OUTDIR / "trustees_status_boundary_certification_errors.csv"),
    ]

    (OUTDIR / "trustees_status_boundary_certification_summary.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print("\n".join(lines))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
