#!/usr/bin/env python
"""
CMS Medicare Advantage Part C — Plan Payment Semantic Documentation Profiler v0.1

Read-only evidence extractor for CY2014-CY2024 CMS Plan Payment ZIP packages.

Purpose
-------
* Resolve annual PLAN_PAYMENT ZIPs from the existing acquisition manifest.
* Locate the annual "Plan Payment Data Element(s)" PDF in each ZIP.
* Fingerprint the ZIP and embedded PDF with SHA-256.
* Extract PDF text page-by-page.
* Search reproducibly for three target concepts:
    - Average A/B PM/PM Payment
    - Average Rebate PM/PM Payment
    - Average Part C Risk Score
      (with CY2014 alias "Average Part Risk Score")
* Preserve page-level evidence snippets for human semantic review.
* Detect whether target terminology is found in each annual document.
* Perform NO payment reconstruction, NO enrollment imputation, and NO DB writes.

Important
---------
This script is a forensic documentation profiler, not a semantic adjudicator.
A lexical match does NOT by itself prove units, mathematical role, risk-adjustment
status, or additivity. Those conclusions require review of CMS's actual wording.

Dependency:
    pypdf

Install if needed:
    python -m pip install pypdf
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

try:
    from pypdf import PdfReader
except ImportError:
    print("ERROR: Missing dependency 'pypdf'.")
    print("Install it inside the active .venv with:")
    print("    python -m pip install pypdf")
    sys.exit(2)


REQUIRED_YEARS = list(range(2014, 2025))

DEFAULT_MANIFEST = Path(
    "data/raw/cms/medicare_advantage/validation/source_acquisition/"
    "cms_ma_partc_source_acquisition_manifest.csv"
)
DEFAULT_OUTPUT_DIR = Path(
    "data/raw/cms/medicare_advantage/validation/payment_semantics"
)

SOURCE_COLUMN_CANDIDATES = [
    "source_type", "source", "artifact_type", "dataset_type", "file_type"
]
YEAR_COLUMN_CANDIDATES = [
    "payment_year", "year", "calendar_year", "cy", "source_year"
]
PATH_COLUMN_CANDIDATES = [
    "canonical_local_path", "local_path", "destination_path", "download_path",
    "artifact_path", "file_path", "path"
]
STATUS_COLUMN_CANDIDATES = [
    "status", "acquisition_status", "download_status"
]

TARGETS = [
    {
        "canonical_field": "Average A/B PM/PM Payment",
        "concept": "AB_PMPM_PAYMENT",
        "aliases": [
            "Average A/B PM/PM Payment",
            "Average AB PM/PM Payment",
            "A/B PM/PM Payment",
            "AB PM/PM Payment",
        ],
        "keywords": ["average", "payment"],
    },
    {
        "canonical_field": "Average Rebate PM/PM Payment",
        "concept": "REBATE_PMPM_PAYMENT",
        "aliases": [
            "Average Rebate PM/PM Payment",
            "Rebate PM/PM Payment",
        ],
        "keywords": ["rebate", "payment"],
    },
    {
        "canonical_field": "Average Part C Risk Score",
        "concept": "PART_C_RISK_SCORE",
        "aliases": [
            "Average Part C Risk Score",
            "Average Part Risk Score",
            "Part C Risk Score",
            "Part Risk Score",
        ],
        "keywords": ["risk", "score"],
    },
]


def norm_col(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def first_matching_column(columns: Iterable[str], candidates: list[str]) -> str | None:
    mapping = {norm_col(c): c for c in columns}
    for candidate in candidates:
        if norm_col(candidate) in mapping:
            return mapping[norm_col(candidate)]
    return None


def sha256_path(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compact_for_match(text: str) -> str:
    text = normalize_text(text).lower()
    text = text.replace("/", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def locate_documentation_pdf(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    matches = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        base = Path(info.filename).name.lower()
        compact = re.sub(r"[^a-z0-9]+", " ", base)
        if base.endswith(".pdf") and "plan payment data element" in compact:
            matches.append(info)
    return matches


def extract_pages(pdf_bytes: bytes) -> tuple[list[str], list[str]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    errors = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
            pages.append(normalize_text(text))
        except Exception as exc:
            pages.append("")
            errors.append(f"page {i}: {type(exc).__name__}: {exc}")
    return pages, errors


def sentenceish_chunks(text: str) -> list[str]:
    """
    Produce moderately sized chunks without pretending PDF text extraction
    preserves true sentences perfectly.
    """
    text = normalize_text(text)
    if not text:
        return []
    chunks = re.split(r"(?<=[.;:])\s+|\s{2,}", text)
    chunks = [normalize_text(c) for c in chunks if normalize_text(c)]
    if len(chunks) <= 1:
        # Fallback: overlapping word windows.
        words = text.split()
        chunks = []
        step = 45
        width = 90
        for start in range(0, len(words), step):
            chunk = " ".join(words[start:start + width])
            if chunk:
                chunks.append(chunk)
            if start + width >= len(words):
                break
    return chunks


def alias_match(text: str, aliases: list[str]) -> tuple[bool, str]:
    hay = compact_for_match(text)
    for alias in aliases:
        needle = compact_for_match(alias)
        if needle and needle in hay:
            return True, alias
    return False, ""


def keyword_match(text: str, keywords: list[str]) -> bool:
    hay = compact_for_match(text)
    return all(re.search(rf"\b{re.escape(k.lower())}\b", hay) for k in keywords)


def evidence_snippet(page_text: str, aliases: list[str], keywords: list[str]) -> tuple[str, str]:
    """
    Return a bounded evidence window and match type.
    Prefer exact/normalized alias occurrence. Otherwise use keyword co-occurrence.
    """
    normalized = normalize_text(page_text)
    compact_page = compact_for_match(normalized)

    for alias in aliases:
        compact_alias = compact_for_match(alias)
        pos = compact_page.find(compact_alias)
        if pos >= 0:
            # Compact positions don't map perfectly to original; find component words
            # in normalized original and take a generous bounded character window.
            words = [w for w in re.findall(r"[A-Za-z0-9]+", alias) if len(w) > 1]
            orig_low = normalized.lower()
            starts = [orig_low.find(w.lower()) for w in words]
            starts = [p for p in starts if p >= 0]
            center = min(starts) if starts else 0
            lo = max(0, center - 500)
            hi = min(len(normalized), center + 1500)
            return normalized[lo:hi], f"ALIAS:{alias}"

    # Keyword fallback: use chunk containing all target keywords.
    for chunk in sentenceish_chunks(normalized):
        if keyword_match(chunk, keywords):
            return chunk[:2000], "KEYWORD_COOCCURRENCE"

    return "", ""


def resolve_repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    cwd = Path.cwd().resolve()
    if (cwd / ".git").exists() or (cwd / "data").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / ".git").exists():
            return parent
    return cwd


def resolve_manifest_rows(manifest_path: Path) -> tuple[pd.DataFrame, dict[str, str | None]]:
    manifest = pd.read_csv(manifest_path, dtype=object)

    source_col = first_matching_column(manifest.columns, SOURCE_COLUMN_CANDIDATES)
    year_col = first_matching_column(manifest.columns, YEAR_COLUMN_CANDIDATES)
    path_col = first_matching_column(manifest.columns, PATH_COLUMN_CANDIDATES)
    status_col = first_matching_column(manifest.columns, STATUS_COLUMN_CANDIDATES)

    missing = []
    if source_col is None:
        missing.append("source-type column")
    if year_col is None:
        missing.append("year column")
    if path_col is None:
        missing.append("local-path column")
    if missing:
        raise RuntimeError(
            "Could not resolve " + ", ".join(missing)
            + ". Manifest columns are: " + ", ".join(map(str, manifest.columns))
        )

    selected = manifest[
        manifest[source_col].astype(str).str.upper().str.strip().eq("PLAN_PAYMENT")
    ].copy()
    selected["_resolved_year"] = pd.to_numeric(selected[year_col], errors="coerce")
    selected = selected[selected["_resolved_year"].isin(REQUIRED_YEARS)].copy()
    selected["_resolved_year"] = selected["_resolved_year"].astype(int)

    return selected, {
        "source_col": source_col,
        "year_col": year_col,
        "path_col": path_col,
        "status_col": status_col,
    }


def resolve_local_path(repo_root: Path, raw_path: Any) -> Path:
    p = Path(str(raw_path))
    if not p.is_absolute():
        p = repo_root / p
    return p.resolve()


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root)
    manifest_path = (
        Path(args.manifest).resolve()
        if args.manifest
        else (repo_root / DEFAULT_MANIFEST).resolve()
    )
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else (repo_root / DEFAULT_OUTPUT_DIR).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 92)
    print("CMS MEDICARE ADVANTAGE PART C — PLAN PAYMENT SEMANTIC DOCUMENTATION PROFILE v0.1")
    print("=" * 92)
    print()
    print("Read-only CMS documentation evidence extraction; no payment reconstruction.")
    print(f"Repository root: {repo_root}")
    print(f"Manifest:        {manifest_path}")
    print()

    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}")
        return 2

    try:
        selected, cols = resolve_manifest_rows(manifest_path)
    except Exception as exc:
        print(f"ERROR resolving manifest: {exc}")
        return 2

    years = sorted(selected["_resolved_year"].tolist())
    year_counts = Counter(years)
    missing_years = [y for y in REQUIRED_YEARS if y not in year_counts]
    duplicate_years = [y for y, n in year_counts.items() if n > 1]

    print("MANIFEST RESOLUTION")
    print("-" * 92)
    print(f"Source column: {cols['source_col']}")
    print(f"Year column:   {cols['year_col']}")
    print(f"Path column:   {cols['path_col']}")
    print(f"Status column: {cols['status_col'] or 'NONE'}")
    print(f"PLAN_PAYMENT rows resolved: {len(selected)}")
    print(f"Years: {years}")
    print()

    doc_rows = []
    page_rows = []
    evidence_rows = []
    error_rows = []

    for _, row in selected.sort_values("_resolved_year").iterrows():
        year = int(row["_resolved_year"])
        zip_path = resolve_local_path(repo_root, row[cols["path_col"]])
        print(f"Profiling CY{year}: {zip_path}")

        if not zip_path.exists():
            error_rows.append({
                "payment_year": year,
                "scope": "ZIP",
                "item": str(zip_path),
                "error": "ZIP file does not exist",
            })
            continue

        try:
            zip_sha = sha256_path(zip_path)
            with zipfile.ZipFile(zip_path) as zf:
                docs = locate_documentation_pdf(zf)

                if len(docs) != 1:
                    error_rows.append({
                        "payment_year": year,
                        "scope": "DOCUMENTATION",
                        "item": str(zip_path),
                        "error": f"Expected exactly 1 Plan Payment Data Element PDF; found {len(docs)}",
                    })
                    continue

                info = docs[0]
                pdf_bytes = zf.read(info)
                pdf_sha = sha256_bytes(pdf_bytes)

                try:
                    pages, page_errors = extract_pages(pdf_bytes)
                except Exception as exc:
                    error_rows.append({
                        "payment_year": year,
                        "scope": "PDF",
                        "item": info.filename,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    continue

                for pe in page_errors:
                    error_rows.append({
                        "payment_year": year,
                        "scope": "PDF_PAGE",
                        "item": info.filename,
                        "error": pe,
                    })

                nonblank_pages = sum(bool(p.strip()) for p in pages)
                total_chars = sum(len(p) for p in pages)

                doc_rows.append({
                    "payment_year": year,
                    "zip_path": str(zip_path),
                    "zip_sha256": zip_sha,
                    "documentation_pdf": info.filename,
                    "documentation_pdf_size_bytes": info.file_size,
                    "documentation_pdf_sha256": pdf_sha,
                    "page_count": len(pages),
                    "nonblank_text_pages": nonblank_pages,
                    "extracted_text_characters": total_chars,
                    "page_extraction_errors": len(page_errors),
                })

                for page_num, page_text in enumerate(pages, start=1):
                    page_rows.append({
                        "payment_year": year,
                        "documentation_pdf": info.filename,
                        "documentation_pdf_sha256": pdf_sha,
                        "page": page_num,
                        "text_character_count": len(page_text),
                        "page_text": page_text,
                    })

                for target in TARGETS:
                    matches = []
                    for page_num, page_text in enumerate(pages, start=1):
                        matched, alias = alias_match(page_text, target["aliases"])
                        if matched:
                            snippet, match_type = evidence_snippet(
                                page_text, target["aliases"], target["keywords"]
                            )
                            matches.append((page_num, alias, match_type, snippet))
                        elif keyword_match(page_text, target["keywords"]):
                            snippet, match_type = evidence_snippet(
                                page_text, target["aliases"], target["keywords"]
                            )
                            matches.append((page_num, "", match_type, snippet))

                    if matches:
                        for match_index, (page_num, alias, match_type, snippet) in enumerate(matches, start=1):
                            evidence_rows.append({
                                "payment_year": year,
                                "documentation_pdf": info.filename,
                                "documentation_pdf_sha256": pdf_sha,
                                "canonical_field": target["canonical_field"],
                                "concept": target["concept"],
                                "definition_found": True,
                                "match_index": match_index,
                                "page": page_num,
                                "matched_alias": alias,
                                "match_type": match_type,
                                "evidence_snippet": snippet,
                            })
                    else:
                        evidence_rows.append({
                            "payment_year": year,
                            "documentation_pdf": info.filename,
                            "documentation_pdf_sha256": pdf_sha,
                            "canonical_field": target["canonical_field"],
                            "concept": target["concept"],
                            "definition_found": False,
                            "match_index": 0,
                            "page": None,
                            "matched_alias": "",
                            "match_type": "",
                            "evidence_snippet": "",
                        })

        except zipfile.BadZipFile as exc:
            error_rows.append({
                "payment_year": year,
                "scope": "ZIP",
                "item": str(zip_path),
                "error": f"BadZipFile: {exc}",
            })
        except Exception as exc:
            error_rows.append({
                "payment_year": year,
                "scope": "GENERAL",
                "item": str(zip_path),
                "error": f"{type(exc).__name__}: {exc}",
            })

    # Build one-row-per-year/concept coverage table.
    coverage_rows = []
    for year in REQUIRED_YEARS:
        for target in TARGETS:
            matches = [
                r for r in evidence_rows
                if r["payment_year"] == year and r["concept"] == target["concept"]
                and r["definition_found"]
            ]
            coverage_rows.append({
                "payment_year": year,
                "canonical_field": target["canonical_field"],
                "concept": target["concept"],
                "definition_found": bool(matches),
                "match_count": len(matches),
                "pages": "|".join(str(r["page"]) for r in matches),
                "match_types": "|".join(sorted(set(r["match_type"] for r in matches))),
                "matched_aliases": "|".join(sorted(set(
                    r["matched_alias"] for r in matches if r["matched_alias"]
                ))),
            })

    # Cross-year lexical stability: hash normalized evidence snippets, diagnostic only.
    stability_rows = []
    for target in TARGETS:
        for year in REQUIRED_YEARS:
            snippets = [
                normalize_text(r["evidence_snippet"])
                for r in evidence_rows
                if r["payment_year"] == year
                and r["concept"] == target["concept"]
                and r["definition_found"]
                and r["evidence_snippet"]
            ]
            combined = " || ".join(snippets)
            stability_rows.append({
                "payment_year": year,
                "canonical_field": target["canonical_field"],
                "concept": target["concept"],
                "evidence_present": bool(combined),
                "normalized_evidence_sha256": (
                    hashlib.sha256(combined.encode("utf-8")).hexdigest()
                    if combined else ""
                ),
                "combined_evidence": combined,
            })

    paths = {
        "documents": output_dir / "cms_ma_partc_plan_payment_documentation_inventory.csv",
        "pages": output_dir / "cms_ma_partc_plan_payment_documentation_pages.csv",
        "evidence": output_dir / "cms_ma_partc_plan_payment_semantic_evidence.csv",
        "coverage": output_dir / "cms_ma_partc_plan_payment_semantic_coverage.csv",
        "stability": output_dir / "cms_ma_partc_plan_payment_semantic_stability.csv",
        "errors": output_dir / "cms_ma_partc_plan_payment_semantic_errors.csv",
        "summary": output_dir / "cms_ma_partc_plan_payment_semantic_summary.txt",
    }

    write_csv(doc_rows, paths["documents"])
    write_csv(page_rows, paths["pages"])
    write_csv(evidence_rows, paths["evidence"])
    write_csv(coverage_rows, paths["coverage"])
    write_csv(stability_rows, paths["stability"])
    write_csv(error_rows, paths["errors"])

    docs_by_year = Counter(r["payment_year"] for r in doc_rows)
    years_with_one_doc = sum(docs_by_year[y] == 1 for y in REQUIRED_YEARS)
    docs_text_readable = sum(
        1 for r in doc_rows
        if r["nonblank_text_pages"] > 0 and r["extracted_text_characters"] > 0
    )
    coverage_found = sum(bool(r["definition_found"]) for r in coverage_rows)
    coverage_expected = len(REQUIRED_YEARS) * len(TARGETS)

    # Note: semantic target coverage is reported, but NOT required for structural PASS.
    # Missing lexical matches may reflect terminology variation and require human review.
    checks = [
        ("Required Plan Payment source rows", len(selected) == 11, f"{len(selected)}/11"),
        ("Missing required years", not missing_years,
         "NONE" if not missing_years else ",".join(map(str, missing_years))),
        ("Duplicate required years", not duplicate_years,
         "NONE" if not duplicate_years else ",".join(map(str, duplicate_years))),
        ("Years with exactly one documentation PDF", years_with_one_doc == 11, f"{years_with_one_doc}/11"),
        ("Documentation PDFs with extractable text", docs_text_readable == 11, f"{docs_text_readable}/11"),
        ("PDF/page extraction errors", len(error_rows) == 0, str(len(error_rows))),
    ]
    overall_pass = all(ok for _, ok, _ in checks)

    lines = []
    add = lines.append
    add("=" * 92)
    add("CMS MEDICARE ADVANTAGE PART C — PLAN PAYMENT SEMANTIC DOCUMENTATION PROFILE v0.1")
    add("=" * 92)
    add("")
    add("Scope: annual CMS Plan Payment Data Element documentation, CY2014-CY2024.")
    add("Purpose: preserve and surface CMS's own wording for the three Part C measures")
    add("needed for semantic adjudication before any payment reconstruction.")
    add("")
    add(f"Required years                              : {len(REQUIRED_YEARS)}")
    add(f"Manifest Plan Payment rows                  : {len(selected)}")
    add(f"Documentation PDFs profiled                 : {len(doc_rows)}")
    add(f"Documentation PDFs with extractable text    : {docs_text_readable}")
    add(f"Target year-field observations expected     : {coverage_expected}")
    add(f"Target year-field lexical coverage found    : {coverage_found}")
    add(f"Evidence rows                               : {len(evidence_rows)}")
    add(f"Page rows                                   : {len(page_rows)}")
    add(f"Profile/read errors                         : {len(error_rows)}")
    add("")
    add("VALIDATION CHECKS")
    add("-" * 92)
    for label, ok, detail in checks:
        add(f"{'PASS' if ok else 'FAIL'}  {label}: {detail}")
    add("")
    add(f"OVERALL STATUS: {'PASS' if overall_pass else 'FAIL'}")
    add("")
    add("TARGET COVERAGE BY YEAR")
    add("-" * 92)
    for year in REQUIRED_YEARS:
        parts = []
        for target in TARGETS:
            cov = next(
                r for r in coverage_rows
                if r["payment_year"] == year and r["concept"] == target["concept"]
            )
            parts.append(
                f"{target['concept']}={'FOUND' if cov['definition_found'] else 'NOT_FOUND'}"
                f"[{cov['pages'] or '-'}]"
            )
        add(f"CY{year}: " + "; ".join(parts))
    add("")
    add("INTERPRETATION")
    add("-" * 92)
    add("PASS establishes only that the 11 annual CMS Plan Payment documentation PDFs were")
    add("located, fingerprinted, and text-extracted under a deterministic read-only procedure.")
    add("Target coverage is lexical evidence discovery, not semantic proof.")
    add("")
    add("A FOUND result does not establish that A/B payment is pre- or post-risk adjustment,")
    add("that rebate is additive, or that any field should be multiplied by enrollment.")
    add("A NOT_FOUND result is not a source failure; it means terminology or PDF structure")
    add("requires broader/manual review.")
    add("")
    add("NEXT EVIDENTIARY STEP")
    add("-" * 92)
    add("Review cms_ma_partc_plan_payment_semantic_evidence.csv, beginning with CY2014,")
    add("CY2019, and CY2024. Adjudicate CMS wording for definition, units, dimensional grain,")
    add("risk-adjustment status, and additive/non-additive mathematical role. Then verify")
    add("whether the same semantics hold across all intervening years.")
    add("")
    add("GOVERNING RULE")
    add("-" * 92)
    add("Never reconstruct a Medicare dollar until we can state exactly what each")
    add("multiplicand means.")
    add("")
    add("OUTPUTS")
    add("-" * 92)
    for path in paths.values():
        add(str(path))

    summary = "\n".join(lines) + "\n"
    paths["summary"].write_text(summary, encoding="utf-8")
    print()
    print(summary)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
