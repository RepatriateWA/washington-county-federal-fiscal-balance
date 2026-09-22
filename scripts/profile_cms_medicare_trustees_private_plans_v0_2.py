#!/usr/bin/env python3
"""
CMS Medicare Trustees Private Health Plans structural profiler v0.2
==================================================================

WCFFBP read-only semantic/structural validation stage.

Purpose
-------
Profile the preserved Medicare Trustees Report PDFs and Expanded/Supplementary
Tables packages for the Private Health Plans tables most relevant to independent
reconciliation of the WCFFBP Medicare Advantage Part C reconstruction:

    IV.C2  Medicare Payments to Private Health Plans, by Trust Fund
    IV.C3  Incurred Expenditures per Private Health Plan Enrollee
    IV.C4  Key Factors for Medicare Advantage Expenditure Estimates

Key v0.2 change
---------------
The Trustees table structure uses a parent heading "Local CCP" with child
columns "HMO" and "PPO".  Therefore this profiler models:

    LOCAL_CCP_HMO
    LOCAL_CCP_PPO
    REGIONAL_PPO
    PFFS
    SNP
    OTHER
    TOTAL

It does NOT require the literal phrase "Local PPO".

This script:
  * reads preserved source files only;
  * performs no network requests;
  * makes no database writes;
  * extracts no payment observations into a control dataset;
  * makes no actual/projected classification decision for individual values;
  * performs no reconciliation;
  * preserves table headings, units, year tokens, footnote/evidence context,
    and actual/historical/estimate/projected terminology as structural evidence.

Run from repository root:
    python scripts/profile_cms_medicare_trustees_private_plans_v0_2.py
"""

from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import xlrd
except ImportError:
    xlrd = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees"
REPORT_DIR = BASE / "reports"
TABLE_DIR = BASE / "expanded_tables"
VAL = BASE / "validation" / "private_health_plans_structure_v0_2"

VINTAGES = list(range(2015, 2027))
TARGET_OBSERVATION_YEARS = list(range(2015, 2025))

WS_RE = re.compile(r"\s+")
YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")
TABLE_RE = re.compile(r"\b(?:table\s+)?IV\.?\s*C\.?\s*([234])\b", re.I)
MAX_CONTEXT = 12000

STATUS_PATTERNS = {
    "ACTUAL": [r"\bactual experience\b", r"\bactual\b", r"\bactuals\b"],
    "HISTORICAL": [r"\bhistorical data\b", r"\bhistorical\b"],
    "ESTIMATE": [r"\bestimate(?:d|s)?\b"],
    "PROJECTED": [r"\bproject(?:ed|ion|ions)?\b"],
    "PRELIMINARY": [r"\bpreliminary\b"],
}

TABLE_TITLE_PATTERNS = {
    "IV.C2": [
        r"medicare payments to private health plans",
        r"payments to private health plans",
    ],
    "IV.C3": [
        r"incurred expenditures per private health plan enrollee",
        r"expenditures per private health plan enrollee",
        r"private health plan enrollee",
    ],
    "IV.C4": [
        r"key factors for medicare advantage expenditure estimates",
        r"medicare advantage expenditure estimates",
    ],
}

PLAN_PATTERNS = {
    "LOCAL_CCP": [r"\blocal\s+ccp\b", r"\blccp\b"],
    "HMO": [r"\bhmo\b"],
    "PPO": [r"\bppo\b"],
    "REGIONAL_PPO": [r"\bregional\s+ppo\b", r"\brppo\b"],
    "PFFS": [r"\bpffs\b", r"\bprivate fee[- ]for[- ]service\b"],
    "SNP": [r"\bsnp\b", r"\bspecial needs plans?\b"],
    "OTHER": [r"\bother\b"],
    "TOTAL": [r"\btotal\b"],
}

C2_COMPONENT_PATTERNS = {
    "BID": [r"\bbid\b", r"\bbid[- ]related\b"],
    "REBATE": [r"\brebate\b", r"\brebates\b"],
    "TOTAL": [r"\btotal\b"],
    "PART_A_PERCENT": [r"\bpart\s+a\b.*\bpercentage\b", r"\bpart\s+a\b.*\bpercent\b"],
    "CASH_BASIS": [r"\bcash\s+basis\b"],
    "INCURRED_BASIS": [r"\bincurred\s+basis\b"],
}

C3_COMPONENT_PATTERNS = {
    "BID_BASED_EXPENDITURES": [r"\bbid[- ]based expenditures?\b", r"\bbid expenditures?\b"],
    "REBATE_EXPENDITURES": [r"\brebate expenditures?\b"],
    "TOTAL_EXPENDITURES": [r"\btotal expenditures?\b"],
    "PER_ENROLLEE": [r"\bper\s+(?:private health plan\s+)?enrollee\b"],
    "PART_A_PLUS_B": [
        r"\bpart\s+a\b.*\bpart\s+b\b",
        r"\bsum of per capita expenditures for part a and part b\b",
    ],
}

C4_COMPONENT_PATTERNS = {
    "FFS_USPCC_PMPM": [r"\bffs\s+uspcc\s+pmpm\b", r"\buspcc\b.*\bpmpm\b"],
    "BENCHMARK_PMPM": [r"\bbenchmark\s+pmpm\b"],
    "BID_PMPM": [r"\bbid\s+pmpm\b"],
    "BID_TO_BENCHMARK_RATIO": [r"\bbid\s+to\s+benchmark\s+ratio\b"],
    "REBATE_PMPM": [r"\brebate\s+pmpm\b"],
    "REBATE_TO_BID_RATIO": [r"\brebate\s+to\s+bid\s+ratio\b"],
    "AVERAGE_FINAL_RISK_SCORES": [
        r"\baverage\s+final\s+risk\s+scores?\b",
        r"\bfinal\s+risk\s+scores?\b",
    ],
}


def norm(value: Any) -> str:
    if value is None:
        return ""
    return WS_RE.sub(" ", str(value)).strip()


def years_in(text: str) -> list[int]:
    return sorted({int(x) for x in YEAR_RE.findall(text)})


def labels_in(text: str, mapping: dict[str, list[str]]) -> list[str]:
    out = []
    for label, patterns in mapping.items():
        if any(re.search(p, text, flags=re.I | re.S) for p in patterns):
            out.append(label)
    return out


def table_ids_in(text: str) -> list[str]:
    ids = {f"IV.C{m.group(1)}" for m in TABLE_RE.finditer(text)}
    low = text.lower()
    for table_id, pats in TABLE_TITLE_PATTERNS.items():
        if any(re.search(p, low, re.I | re.S) for p in pats):
            ids.add(table_id)
    return sorted(ids)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def find_sources() -> tuple[dict[int, Path], dict[int, Path]]:
    reports: dict[int, Path] = {}
    packages: dict[int, Path] = {}
    for y in VINTAGES:
        rp = REPORT_DIR / f"medicare_trustees_{y}.pdf"
        zp = TABLE_DIR / f"medicare_trustees_{y}_expanded_tables.zip"
        if rp.exists():
            reports[y] = rp
        if zp.exists():
            packages[y] = zp
    return reports, packages


@dataclass
class Surface:
    vintage: int
    artifact: str
    member: str
    surface: str
    location: str
    text: str


def add_surface(
    surfaces: list[Surface],
    vintage: int,
    artifact: str,
    member: str,
    surface: str,
    location: str,
    text: Any,
) -> None:
    t = norm(text)
    if t:
        surfaces.append(Surface(vintage, artifact, member, surface, location, t))


def extract_pdf_surfaces(
    data: bytes,
    vintage: int,
    artifact: str,
    member: str,
    surfaces: list[Surface],
    pdf_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    if PdfReader is None:
        pdf_rows.append({
            "trustees_vintage": vintage, "artifact": artifact, "member_name": member,
            "pages": "", "pages_extractable": 0,
            "status": "SKIPPED_PYPDF_NOT_INSTALLED", "error": "",
        })
        return
    try:
        reader = PdfReader(io.BytesIO(data))
        extractable = 0
        for page_no, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                extractable += 1
                add_surface(
                    surfaces, vintage, artifact, member,
                    "PDF_PAGE", f"page:{page_no}", text[:MAX_CONTEXT]
                )
        pdf_rows.append({
            "trustees_vintage": vintage, "artifact": artifact, "member_name": member,
            "pages": len(reader.pages), "pages_extractable": extractable,
            "status": "PROFILED", "error": "",
        })
    except Exception as exc:
        errors.append({
            "trustees_vintage": vintage, "artifact": artifact,
            "member_name": member, "location": "",
            "error": f"{type(exc).__name__}: {exc}",
        })


def extract_xlsx_surfaces(
    data: bytes,
    vintage: int,
    artifact: str,
    member: str,
    surfaces: list[Surface],
    sheet_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    if openpyxl is None:
        sheet_rows.append({
            "trustees_vintage": vintage, "artifact": artifact, "member_name": member,
            "sheet_name": "", "rows_observed": "", "columns_observed": "",
            "status": "SKIPPED_OPENPYXL_NOT_INSTALLED", "error": "",
        })
        return
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        for ws in wb.worksheets:
            add_surface(surfaces, vintage, artifact, member, "SHEET_NAME", ws.title, ws.title)
            max_r = max_c = 0
            for r, row in enumerate(ws.iter_rows(values_only=True), 1):
                max_r = r
                vals: list[str] = []
                for c, value in enumerate(row, 1):
                    if value is None:
                        continue
                    max_c = max(max_c, c)
                    t = norm(value)
                    if t:
                        vals.append(t)
                if vals:
                    add_surface(
                        surfaces, vintage, artifact, member,
                        "ROW", f"{ws.title}!R{r}", " | ".join(vals)
                    )
            sheet_rows.append({
                "trustees_vintage": vintage, "artifact": artifact, "member_name": member,
                "sheet_name": ws.title, "rows_observed": max_r,
                "columns_observed": max_c, "status": "PROFILED", "error": "",
            })
        wb.close()
    except Exception as exc:
        errors.append({
            "trustees_vintage": vintage, "artifact": artifact,
            "member_name": member, "location": "",
            "error": f"{type(exc).__name__}: {exc}",
        })


def extract_xls_surfaces(
    data: bytes,
    vintage: int,
    artifact: str,
    member: str,
    surfaces: list[Surface],
    sheet_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    if xlrd is None:
        sheet_rows.append({
            "trustees_vintage": vintage, "artifact": artifact, "member_name": member,
            "sheet_name": "", "rows_observed": "", "columns_observed": "",
            "status": "SKIPPED_XLRD_NOT_INSTALLED", "error": "",
        })
        return
    try:
        book = xlrd.open_workbook(file_contents=data)
        for sh in book.sheets():
            add_surface(surfaces, vintage, artifact, member, "SHEET_NAME", sh.name, sh.name)
            for r in range(sh.nrows):
                vals = []
                for c in range(sh.ncols):
                    value = sh.cell_value(r, c)
                    t = norm(value)
                    if t:
                        vals.append(t)
                if vals:
                    add_surface(
                        surfaces, vintage, artifact, member,
                        "ROW", f"{sh.name}!R{r+1}", " | ".join(vals)
                    )
            sheet_rows.append({
                "trustees_vintage": vintage, "artifact": artifact, "member_name": member,
                "sheet_name": sh.name, "rows_observed": sh.nrows,
                "columns_observed": sh.ncols, "status": "PROFILED", "error": "",
            })
    except Exception as exc:
        errors.append({
            "trustees_vintage": vintage, "artifact": artifact,
            "member_name": member, "location": "",
            "error": f"{type(exc).__name__}: {exc}",
        })


def extract_text_surfaces(
    data: bytes,
    vintage: int,
    artifact: str,
    member: str,
    surfaces: list[Surface],
) -> None:
    text = data.decode("utf-8-sig", errors="replace")
    for i, line in enumerate(text.splitlines(), 1):
        add_surface(surfaces, vintage, artifact, member, "TEXT_ROW", f"line:{i}", line)


def structural_records(surfaces: list[Surface]) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]
]:
    evidence: list[dict[str, Any]] = []
    table_presence: list[dict[str, Any]] = []
    context_rows: list[dict[str, Any]] = []

    seen_evidence = set()
    seen_presence = set()

    for s in surfaces:
        ids = table_ids_in(s.text)
        if not ids:
            continue

        status = labels_in(s.text, STATUS_PATTERNS)
        plans = labels_in(s.text, PLAN_PATTERNS)
        ys = years_in(s.text)

        for table_id in ids:
            components_map = (
                C2_COMPONENT_PATTERNS if table_id == "IV.C2"
                else C3_COMPONENT_PATTERNS if table_id == "IV.C3"
                else C4_COMPONENT_PATTERNS
            )
            components = labels_in(s.text, components_map)

            pkey = (s.vintage, table_id, s.artifact, s.member, s.surface, s.location)
            if pkey not in seen_presence:
                seen_presence.add(pkey)
                table_presence.append({
                    "trustees_vintage": s.vintage,
                    "table_id": table_id,
                    "artifact": s.artifact,
                    "member_name": s.member,
                    "surface": s.surface,
                    "location": s.location,
                    "observation_year_tokens": ";".join(map(str, ys)),
                    "status_terms": ";".join(status),
                    "plan_terms": ";".join(plans),
                    "component_terms": ";".join(components),
                })

            for kind, labels in (
                ("STATUS", status),
                ("PLAN", plans),
                ("COMPONENT", components),
            ):
                for label in labels:
                    ekey = (s.vintage, table_id, s.artifact, s.member,
                            s.surface, s.location, kind, label)
                    if ekey in seen_evidence:
                        continue
                    seen_evidence.add(ekey)
                    evidence.append({
                        "trustees_vintage": s.vintage,
                        "table_id": table_id,
                        "artifact": s.artifact,
                        "member_name": s.member,
                        "surface": s.surface,
                        "location": s.location,
                        "evidence_kind": kind,
                        "evidence_label": label,
                        "observation_year_tokens": ";".join(map(str, ys)),
                        "context": s.text[:MAX_CONTEXT],
                    })

            context_rows.append({
                "trustees_vintage": s.vintage,
                "table_id": table_id,
                "artifact": s.artifact,
                "member_name": s.member,
                "surface": s.surface,
                "location": s.location,
                "context": s.text[:MAX_CONTEXT],
            })

    return evidence, table_presence, context_rows


def infer_local_ccp_structure(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Structural inference only.

    A vintage is marked LOCAL_CCP_HMO / LOCAL_CCP_PPO STRUCTURALLY_SUPPORTED when
    Local CCP, HMO, and PPO occur in evidence for IV.C3.  This does not extract
    or assign any numeric value.
    """
    by_vintage: dict[int, set[str]] = defaultdict(set)
    for row in evidence:
        if row["table_id"] == "IV.C3" and row["evidence_kind"] == "PLAN":
            by_vintage[int(row["trustees_vintage"])].add(row["evidence_label"])

    rows = []
    for y in VINTAGES:
        labels = by_vintage[y]
        parent = "LOCAL_CCP" in labels
        hmo = "HMO" in labels
        ppo = "PPO" in labels
        regional = "REGIONAL_PPO" in labels
        rows.append({
            "trustees_vintage": y,
            "local_ccp_parent_found": "YES" if parent else "NO",
            "hmo_child_found": "YES" if hmo else "NO",
            "ppo_child_found": "YES" if ppo else "NO",
            "regional_ppo_found": "YES" if regional else "NO",
            "LOCAL_CCP_HMO": "STRUCTURALLY_SUPPORTED" if parent and hmo else "NOT_ESTABLISHED",
            "LOCAL_CCP_PPO": "STRUCTURALLY_SUPPORTED" if parent and ppo else "NOT_ESTABLISHED",
            "regional_ppo_distinguishable": "YES" if ppo and regional else "NO",
        })
    return rows


def build_coverage(
    evidence: list[dict[str, Any]],
    presence: list[dict[str, Any]],
    local_structure: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    table_seen = defaultdict(set)
    plan_seen = defaultdict(set)
    component_seen = defaultdict(set)
    status_seen = defaultdict(set)
    year_seen = defaultdict(set)

    for row in presence:
        y = int(row["trustees_vintage"])
        tid = row["table_id"]
        table_seen[y].add(tid)
        for token in filter(None, row["observation_year_tokens"].split(";")):
            yi = int(token)
            if yi in TARGET_OBSERVATION_YEARS:
                year_seen[(y, tid)].add(yi)

    for row in evidence:
        y = int(row["trustees_vintage"])
        tid = row["table_id"]
        label = row["evidence_label"]
        if row["evidence_kind"] == "PLAN":
            plan_seen[(y, tid)].add(label)
        elif row["evidence_kind"] == "COMPONENT":
            component_seen[(y, tid)].add(label)
        elif row["evidence_kind"] == "STATUS":
            status_seen[(y, tid)].add(label)

    local_by_y = {int(r["trustees_vintage"]): r for r in local_structure}
    rows = []
    for y in VINTAGES:
        for tid in ("IV.C2", "IV.C3", "IV.C4"):
            rows.append({
                "trustees_vintage": y,
                "table_id": tid,
                "table_found": "YES" if tid in table_seen[y] else "NO",
                "plan_terms": ";".join(sorted(plan_seen[(y, tid)])),
                "component_terms": ";".join(sorted(component_seen[(y, tid)])),
                "status_terms": ";".join(sorted(status_seen[(y, tid)])),
                "target_observation_years": ";".join(map(str, sorted(year_seen[(y, tid)]))),
                "LOCAL_CCP_HMO": (
                    local_by_y[y]["LOCAL_CCP_HMO"] if tid == "IV.C3" else ""
                ),
                "LOCAL_CCP_PPO": (
                    local_by_y[y]["LOCAL_CCP_PPO"] if tid == "IV.C3" else ""
                ),
            })
    return rows


def main() -> int:
    VAL.mkdir(parents=True, exist_ok=True)

    print("=" * 104)
    print("CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS STRUCTURAL PROFILE v0.2")
    print("=" * 104)
    print("Read-only. No payment extraction, observation-status assignment, reconciliation, or DB writes.\n")

    reports, packages = find_sources()
    surfaces: list[Surface] = []
    members: list[dict[str, Any]] = []
    sheet_rows: list[dict[str, Any]] = []
    pdf_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for vintage, path in sorted(reports.items()):
        try:
            extract_pdf_surfaces(
                path.read_bytes(), vintage, "ANNUAL_REPORT", path.name,
                surfaces, pdf_rows, errors
            )
        except Exception as exc:
            errors.append({
                "trustees_vintage": vintage, "artifact": "ANNUAL_REPORT",
                "member_name": path.name, "location": "",
                "error": f"{type(exc).__name__}: {exc}",
            })

    for vintage, path in sorted(packages.items()):
        try:
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    ext = Path(info.filename).suffix.lower()
                    members.append({
                        "trustees_vintage": vintage,
                        "member_name": info.filename,
                        "extension": ext,
                        "member_bytes": info.file_size,
                    })
                    add_surface(
                        surfaces, vintage, "EXPANDED_TABLES", info.filename,
                        "MEMBER_NAME", "filename", info.filename
                    )

                    if ext not in {
                        ".xlsx", ".xlsm", ".xls", ".csv", ".txt",
                        ".html", ".htm", ".xml", ".pdf"
                    }:
                        continue
                    data = zf.read(info)
                    if ext in {".xlsx", ".xlsm"}:
                        extract_xlsx_surfaces(
                            data, vintage, "EXPANDED_TABLES", info.filename,
                            surfaces, sheet_rows, errors
                        )
                    elif ext == ".xls":
                        extract_xls_surfaces(
                            data, vintage, "EXPANDED_TABLES", info.filename,
                            surfaces, sheet_rows, errors
                        )
                    elif ext in {".csv", ".txt", ".html", ".htm", ".xml"}:
                        extract_text_surfaces(
                            data, vintage, "EXPANDED_TABLES", info.filename, surfaces
                        )
                    elif ext == ".pdf":
                        extract_pdf_surfaces(
                            data, vintage, "EXPANDED_TABLES", info.filename,
                            surfaces, pdf_rows, errors
                        )
        except Exception as exc:
            errors.append({
                "trustees_vintage": vintage, "artifact": "EXPANDED_TABLES",
                "member_name": path.name, "location": "",
                "error": f"{type(exc).__name__}: {exc}",
            })

    evidence, presence, contexts = structural_records(surfaces)
    local_structure = infer_local_ccp_structure(evidence)
    coverage = build_coverage(evidence, presence, local_structure)

    write_csv(
        VAL / "cms_medicare_trustees_private_plans_table_evidence.csv",
        evidence,
        [
            "trustees_vintage", "table_id", "artifact", "member_name",
            "surface", "location", "evidence_kind", "evidence_label",
            "observation_year_tokens", "context",
        ],
    )
    write_csv(
        VAL / "cms_medicare_trustees_private_plans_table_presence.csv",
        presence,
        [
            "trustees_vintage", "table_id", "artifact", "member_name",
            "surface", "location", "observation_year_tokens",
            "status_terms", "plan_terms", "component_terms",
        ],
    )
    write_csv(
        VAL / "cms_medicare_trustees_private_plans_table_contexts.csv",
        contexts,
        [
            "trustees_vintage", "table_id", "artifact", "member_name",
            "surface", "location", "context",
        ],
    )
    write_csv(
        VAL / "cms_medicare_trustees_private_plans_local_ccp_structure.csv",
        local_structure,
        [
            "trustees_vintage", "local_ccp_parent_found", "hmo_child_found",
            "ppo_child_found", "regional_ppo_found", "LOCAL_CCP_HMO",
            "LOCAL_CCP_PPO", "regional_ppo_distinguishable",
        ],
    )
    write_csv(
        VAL / "cms_medicare_trustees_private_plans_structural_coverage.csv",
        coverage,
        [
            "trustees_vintage", "table_id", "table_found", "plan_terms",
            "component_terms", "status_terms", "target_observation_years",
            "LOCAL_CCP_HMO", "LOCAL_CCP_PPO",
        ],
    )
    write_csv(
        VAL / "cms_medicare_trustees_private_plans_members.csv",
        members,
        ["trustees_vintage", "member_name", "extension", "member_bytes"],
    )
    write_csv(
        VAL / "cms_medicare_trustees_private_plans_sheets.csv",
        sheet_rows,
        [
            "trustees_vintage", "artifact", "member_name", "sheet_name",
            "rows_observed", "columns_observed", "status", "error",
        ],
    )
    write_csv(
        VAL / "cms_medicare_trustees_private_plans_pdfs.csv",
        pdf_rows,
        [
            "trustees_vintage", "artifact", "member_name", "pages",
            "pages_extractable", "status", "error",
        ],
    )
    write_csv(
        VAL / "cms_medicare_trustees_private_plans_errors.csv",
        errors,
        ["trustees_vintage", "artifact", "member_name", "location", "error"],
    )

    # Validation gates.  These deliberately test structural discovery only.
    coverage_by = {(int(r["trustees_vintage"]), r["table_id"]): r for r in coverage}
    local_by = {int(r["trustees_vintage"]): r for r in local_structure}

    report_complete = sorted(reports) == VINTAGES
    package_complete = sorted(packages) == VINTAGES
    c2_all = all(coverage_by[(y, "IV.C2")]["table_found"] == "YES" for y in VINTAGES)
    c3_all = all(coverage_by[(y, "IV.C3")]["table_found"] == "YES" for y in VINTAGES)
    c4_all = all(coverage_by[(y, "IV.C4")]["table_found"] == "YES" for y in VINTAGES)

    local_hmo_all = all(
        local_by[y]["LOCAL_CCP_HMO"] == "STRUCTURALLY_SUPPORTED" for y in VINTAGES
    )
    local_ppo_all = all(
        local_by[y]["LOCAL_CCP_PPO"] == "STRUCTURALLY_SUPPORTED" for y in VINTAGES
    )
    regional_distinct_all = all(
        local_by[y]["regional_ppo_distinguishable"] == "YES" for y in VINTAGES
    )

    def comp_all(table_id: str, required: set[str]) -> bool:
        for y in VINTAGES:
            found = set(filter(None, coverage_by[(y, table_id)]["component_terms"].split(";")))
            if not required.issubset(found):
                return False
        return True

    c2_components = comp_all(
        "IV.C2", {"BID", "REBATE", "TOTAL", "CASH_BASIS", "INCURRED_BASIS"}
    )
    c3_components = comp_all(
        "IV.C3", {"BID_BASED_EXPENDITURES", "REBATE_EXPENDITURES", "PER_ENROLLEE"}
    )
    c4_components = comp_all(
        "IV.C4",
        {
            "FFS_USPCC_PMPM", "BENCHMARK_PMPM", "BID_PMPM",
            "BID_TO_BENCHMARK_RATIO", "REBATE_PMPM",
            "REBATE_TO_BID_RATIO", "AVERAGE_FINAL_RISK_SCORES",
        },
    )

    no_errors = len(errors) == 0

    checks = [
        ("Annual report source universe 2015-2026 present", report_complete),
        ("Expanded-package source universe 2015-2026 present", package_complete),
        ("Table IV.C2 structurally located in every vintage", c2_all),
        ("Table IV.C3 structurally located in every vintage", c3_all),
        ("Table IV.C4 structurally located in every vintage", c4_all),
        ("IV.C3 Local CCP -> HMO structure supported in every vintage", local_hmo_all),
        ("IV.C3 Local CCP -> PPO structure supported in every vintage", local_ppo_all),
        ("IV.C3 Local PPO distinguishable from Regional PPO in every vintage", regional_distinct_all),
        ("IV.C2 core accounting components found in every vintage", c2_components),
        ("IV.C3 bid/rebate per-enrollee structure found in every vintage", c3_components),
        ("IV.C4 PMPM/risk-score factor structure found in every vintage", c4_components),
        ("Profile/read errors", no_errors),
    ]
    overall = all(ok for _, ok in checks)

    table_counts = Counter((r["table_id"] for r in presence))
    evidence_counts = Counter((r["table_id"], r["evidence_kind"]) for r in evidence)

    lines = [
        "=" * 104,
        "CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS STRUCTURAL PROFILE v0.2",
        "=" * 104,
        "",
        f"Trustees vintages expected                    : {len(VINTAGES)}",
        f"Annual reports present                        : {len(reports)}",
        f"Expanded packages present                     : {len(packages)}",
        f"Expanded-package members inventoried          : {len(members)}",
        f"Spreadsheet sheets profiled                   : {len(sheet_rows)}",
        f"PDF artifacts profiled                        : {len(pdf_rows)}",
        f"Text/row/page surfaces collected              : {len(surfaces)}",
        f"Table-presence evidence rows                  : {len(presence)}",
        f"Structural evidence rows                      : {len(evidence)}",
        f"Profile/read errors                           : {len(errors)}",
        "",
        "TABLE EVIDENCE COUNTS",
        "-" * 104,
    ]
    for tid in ("IV.C2", "IV.C3", "IV.C4"):
        lines.append(
            f"{tid:<8} presence={table_counts[tid]:>6,}  "
            f"PLAN={evidence_counts[(tid, 'PLAN')]:>6,}  "
            f"COMPONENT={evidence_counts[(tid, 'COMPONENT')]:>6,}  "
            f"STATUS={evidence_counts[(tid, 'STATUS')]:>6,}"
        )

    lines += ["", "LOCAL CCP STRUCTURE BY TRUSTEES VINTAGE", "-" * 104]
    for row in local_structure:
        lines.append(
            f"{row['trustees_vintage']}: "
            f"LocalCCP={row['local_ccp_parent_found']}  "
            f"HMO={row['hmo_child_found']}  "
            f"PPO={row['ppo_child_found']}  "
            f"RegionalPPO={row['regional_ppo_found']}  "
            f"LOCAL_CCP_HMO={row['LOCAL_CCP_HMO']}  "
            f"LOCAL_CCP_PPO={row['LOCAL_CCP_PPO']}"
        )

    lines += ["", "STRUCTURAL COVERAGE", "-" * 104]
    for y in VINTAGES:
        for tid in ("IV.C2", "IV.C3", "IV.C4"):
            row = coverage_by[(y, tid)]
            lines.append(
                f"{y} {tid}: found={row['table_found']}  "
                f"plans=[{row['plan_terms']}]  "
                f"components=[{row['component_terms']}]  "
                f"status=[{row['status_terms']}]  "
                f"target-years=[{row['target_observation_years']}]"
            )

    lines += ["", "VALIDATION CHECKS", "-" * 104]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)

    lines += [
        "",
        f"OVERALL STRUCTURAL PROFILE STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "IMPORTANT:",
        "A PASS establishes only that the preserved Trustees source universe contains a structurally",
        "traceable IV.C2 / IV.C3 / IV.C4 control framework and that Local CCP HMO/PPO can be kept",
        "distinct from Regional PPO. It does NOT establish comparability of any dollar observation.",
        "",
        "This script extracts no Trustees payment observations into a control dataset and assigns no",
        "individual observation as actual, historical, estimated, or projected. Those remain later gates.",
        "",
        "OUTPUTS",
        "-" * 104,
        str(VAL / "cms_medicare_trustees_private_plans_table_evidence.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_table_presence.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_table_contexts.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_local_ccp_structure.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_structural_coverage.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_members.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_sheets.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_pdfs.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_errors.csv"),
    ]

    summary_path = VAL / "cms_medicare_trustees_private_plans_structural_profile_summary.txt"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
