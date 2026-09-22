#!/usr/bin/env python3
"""
Profile CMS Medicare Trustees Private Health Plans material, vintages 2015-2026.

WCFFBP semantic profiling stage v0.1.

Purpose
-------
Read the already-preserved CMS Medicare Trustees annual reports and expanded /
supplementary packages and map where Private Health Plans concepts occur before
any control-dollar extraction is attempted.

This profiler:
  * reads ONLY preserved source artifacts;
  * inventories text-bearing ZIP members;
  * searches filenames, spreadsheet sheets/cells, CSV/text rows, HTML/XML, and PDFs;
  * records semantic hits for Private Health Plans concepts;
  * extracts nearby year tokens only as discovery metadata;
  * looks for actual / historical / estimate / projection terminology;
  * builds a vintage-by-observation-year presence matrix;
  * makes NO payment-value extraction;
  * makes NO actual/projected classification decision;
  * makes NO reconciliation;
  * makes NO database writes.

Run from repository root:
    python scripts/profile_cms_medicare_trustees_private_plans.py
"""

from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

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
VAL = BASE / "validation" / "private_health_plans_profile"

VINTAGES = list(range(2015, 2027))
TARGET_OBSERVATION_YEARS = list(range(2015, 2025))

# Phrase groups are discovery labels, not accounting classifications.
PHRASES = {
    "PRIVATE_HEALTH_PLANS": [r"\bprivate health plans?\b", r"\bprivate plans?\b"],
    "HMO": [r"\bhmo\b", r"\bhealth maintenance organization"],
    "LOCAL_PPO": [r"\blocal ppo\b"],
    "REGIONAL_PPO": [r"\bregional ppo\b"],
    "PFFS": [r"\bpffs\b", r"\bprivate fee[- ]for[- ]service\b"],
    "SNP": [r"\bsnp\b", r"\bspecial needs plans?\b"],
    "OTHER": [r"\bother\b"],
    "REBATE_EXPENDITURES": [r"\brebate expenditures?\b", r"\brebates?\b"],
    "BID_RELATED_EXPENDITURES": [
        r"\bbid[- ]related expenditures?\b",
        r"\bbid related\b",
    ],
    "TOTAL_EXPENDITURES": [r"\btotal expenditures?\b"],
    "PER_CAPITA": [r"\bper capita\b", r"\bper-capita\b"],
    "ENROLLMENT": [r"\benrollment\b", r"\benrollees?\b", r"\bbeneficiar(?:y|ies)\b"],
    "PART_C": [r"\bpart c\b", r"\bmedicare advantage\b"],
}

STATUS_TERMS = {
    "ACTUAL": [r"\bactual\b", r"\bactuals\b"],
    "HISTORICAL": [r"\bhistorical\b", r"\bhistory\b"],
    "ESTIMATE": [r"\bestimate(?:d|s)?\b"],
    "PROJECTED": [r"\bproject(?:ed|ion|ions)?\b"],
    "PRELIMINARY": [r"\bpreliminary\b"],
}

YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")
WS_RE = re.compile(r"\s+")
MAX_CONTEXT = 2500
MAX_HITS_PER_LABEL_PER_LOCATION = 50


def norm(value: Any) -> str:
    if value is None:
        return ""
    return WS_RE.sub(" ", str(value)).strip()


def labels_in(text: str, mapping: dict[str, list[str]]) -> list[str]:
    out = []
    for label, patterns in mapping.items():
        if any(re.search(p, text, flags=re.I) for p in patterns):
            out.append(label)
    return out


def years_in(text: str) -> list[int]:
    return sorted({int(x) for x in YEAR_RE.findall(text)})


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def record_hit(
    hits: list[dict[str, Any]],
    counters: Counter,
    *,
    vintage: int,
    artifact: str,
    member: str,
    surface: str,
    location: str,
    text: str,
) -> None:
    text = norm(text)
    if not text:
        return
    semantic = labels_in(text, PHRASES)
    status = labels_in(text, STATUS_TERMS)
    if not semantic and not status:
        return

    ys = years_in(text)
    for label in semantic + [f"STATUS_{x}" for x in status]:
        key = (vintage, artifact, member, surface, location, label)
        if counters[key] >= MAX_HITS_PER_LABEL_PER_LOCATION:
            continue
        counters[key] += 1
        hits.append(
            {
                "trustees_vintage": vintage,
                "artifact": artifact,
                "member_name": member,
                "surface": surface,
                "location": location,
                "semantic_label": label,
                "observation_year_tokens": ";".join(map(str, ys)),
                "context": text[:MAX_CONTEXT],
            }
        )


def profile_xlsx(data: bytes, vintage: int, artifact: str, member: str,
                 hits: list[dict[str, Any]], counters: Counter,
                 sheets: list[dict[str, Any]]) -> None:
    if openpyxl is None:
        sheets.append({"trustees_vintage": vintage, "artifact": artifact, "member_name": member,
                       "sheet_name": "", "rows_observed": "", "columns_observed": "",
                       "status": "SKIPPED_OPENPYXL_NOT_INSTALLED", "error": ""})
        return
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    for ws in wb.worksheets:
        record_hit(hits, counters, vintage=vintage, artifact=artifact, member=member,
                   surface="SHEET_NAME", location=ws.title, text=ws.title)
        max_r = max_c = 0
        for r, row in enumerate(ws.iter_rows(values_only=True), 1):
            max_r = r
            # Search both individual cells and row context, because table headings can span cells.
            vals = []
            for c, value in enumerate(row, 1):
                if value is None:
                    continue
                max_c = max(max_c, c)
                t = norm(value)
                vals.append(t)
                record_hit(hits, counters, vintage=vintage, artifact=artifact, member=member,
                           surface="CELL", location=f"{ws.title}!R{r}C{c}", text=t)
            if vals:
                record_hit(hits, counters, vintage=vintage, artifact=artifact, member=member,
                           surface="ROW", location=f"{ws.title}!R{r}", text=" | ".join(vals))
        sheets.append({"trustees_vintage": vintage, "artifact": artifact, "member_name": member,
                       "sheet_name": ws.title, "rows_observed": max_r, "columns_observed": max_c,
                       "status": "PROFILED", "error": ""})
    wb.close()


def profile_xls(data: bytes, vintage: int, artifact: str, member: str,
                hits: list[dict[str, Any]], counters: Counter,
                sheets: list[dict[str, Any]]) -> None:
    if xlrd is None:
        sheets.append({"trustees_vintage": vintage, "artifact": artifact, "member_name": member,
                       "sheet_name": "", "rows_observed": "", "columns_observed": "",
                       "status": "SKIPPED_XLRD_NOT_INSTALLED", "error": ""})
        return
    book = xlrd.open_workbook(file_contents=data)
    for sh in book.sheets():
        record_hit(hits, counters, vintage=vintage, artifact=artifact, member=member,
                   surface="SHEET_NAME", location=sh.name, text=sh.name)
        for r in range(sh.nrows):
            vals = []
            for c in range(sh.ncols):
                value = sh.cell_value(r, c)
                if value in ("", None):
                    continue
                t = norm(value)
                vals.append(t)
                record_hit(hits, counters, vintage=vintage, artifact=artifact, member=member,
                           surface="CELL", location=f"{sh.name}!R{r+1}C{c+1}", text=t)
            if vals:
                record_hit(hits, counters, vintage=vintage, artifact=artifact, member=member,
                           surface="ROW", location=f"{sh.name}!R{r+1}", text=" | ".join(vals))
        sheets.append({"trustees_vintage": vintage, "artifact": artifact, "member_name": member,
                       "sheet_name": sh.name, "rows_observed": sh.nrows, "columns_observed": sh.ncols,
                       "status": "PROFILED", "error": ""})


def profile_delimited(data: bytes, vintage: int, artifact: str, member: str,
                      hits: list[dict[str, Any]], counters: Counter) -> None:
    text = data.decode("utf-8-sig", errors="replace")
    for i, line in enumerate(text.splitlines(), 1):
        record_hit(hits, counters, vintage=vintage, artifact=artifact, member=member,
                   surface="TEXT_ROW", location=f"line:{i}", text=line)


def profile_html_xml(data: bytes, vintage: int, artifact: str, member: str,
                     hits: list[dict[str, Any]], counters: Counter) -> None:
    text = data.decode("utf-8", errors="replace")
    # Preserve enough local structure for table discovery while removing extreme whitespace.
    text = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " | ", text)
    chunks = [x for x in re.split(r"\|{1,}", text) if norm(x)]
    for i, chunk in enumerate(chunks, 1):
        record_hit(hits, counters, vintage=vintage, artifact=artifact, member=member,
                   surface="HTML_XML_TEXT", location=f"chunk:{i}", text=chunk)


def profile_pdf_bytes(data: bytes, vintage: int, artifact: str, member: str,
                      hits: list[dict[str, Any]], counters: Counter,
                      pdf_rows: list[dict[str, Any]]) -> None:
    if PdfReader is None:
        pdf_rows.append({"trustees_vintage": vintage, "artifact": artifact, "member_name": member,
                         "pages": "", "pages_extractable": 0,
                         "status": "SKIPPED_PYPDF_NOT_INSTALLED", "error": ""})
        return
    reader = PdfReader(io.BytesIO(data))
    extractable = 0
    for page_no, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            extractable += 1
        # Whole-page context catches headings split across PDF text objects.
        record_hit(hits, counters, vintage=vintage, artifact=artifact, member=member,
                   surface="PDF_PAGE", location=f"page:{page_no}", text=text)
    pdf_rows.append({"trustees_vintage": vintage, "artifact": artifact, "member_name": member,
                     "pages": len(reader.pages), "pages_extractable": extractable,
                     "status": "PROFILED", "error": ""})


def find_sources() -> tuple[dict[int, Path], dict[int, Path]]:
    reports = {}
    packages = {}
    for y in VINTAGES:
        rp = REPORT_DIR / f"medicare_trustees_{y}.pdf"
        zp = TABLE_DIR / f"medicare_trustees_{y}_expanded_tables.zip"
        if rp.exists():
            reports[y] = rp
        if zp.exists():
            packages[y] = zp
    return reports, packages


def main() -> int:
    VAL.mkdir(parents=True, exist_ok=True)
    print("=" * 100)
    print("CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS SEMANTIC PROFILE v0.1")
    print("=" * 100)
    print("No payment-value extraction, actual/projected classification decision, reconciliation, or DB writes.\n")

    reports, packages = find_sources()
    hits: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    sheets: list[dict[str, Any]] = []
    pdf_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    counters: Counter = Counter()

    # Profile annual reports as a second semantic surface.
    for vintage, path in sorted(reports.items()):
        try:
            data = path.read_bytes()
            profile_pdf_bytes(data, vintage, "ANNUAL_REPORT", path.name,
                              hits, counters, pdf_rows)
        except Exception as exc:
            errors.append({"trustees_vintage": vintage, "artifact": "ANNUAL_REPORT",
                           "member_name": path.name, "error": f"{type(exc).__name__}: {exc}"})

    # Profile every member of every expanded package.
    for vintage, path in sorted(packages.items()):
        try:
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    ext = Path(info.filename).suffix.lower()
                    members.append({
                        "trustees_vintage": vintage,
                        "artifact": "EXPANDED_TABLES",
                        "member_name": info.filename,
                        "extension": ext,
                        "member_bytes": info.file_size,
                    })
                    # Filename itself is a useful semantic surface.
                    record_hit(hits, counters, vintage=vintage, artifact="EXPANDED_TABLES",
                               member=info.filename, surface="MEMBER_NAME",
                               location="filename", text=info.filename)
                    if ext not in {".xlsx", ".xls", ".xlsm", ".csv", ".txt", ".html", ".htm",
                                   ".xml", ".pdf"}:
                        continue
                    data = zf.read(info)
                    try:
                        if ext in {".xlsx", ".xlsm"}:
                            profile_xlsx(data, vintage, "EXPANDED_TABLES", info.filename,
                                         hits, counters, sheets)
                        elif ext == ".xls":
                            profile_xls(data, vintage, "EXPANDED_TABLES", info.filename,
                                        hits, counters, sheets)
                        elif ext in {".csv", ".txt"}:
                            profile_delimited(data, vintage, "EXPANDED_TABLES", info.filename,
                                              hits, counters)
                        elif ext in {".html", ".htm", ".xml"}:
                            profile_html_xml(data, vintage, "EXPANDED_TABLES", info.filename,
                                             hits, counters)
                        elif ext == ".pdf":
                            profile_pdf_bytes(data, vintage, "EXPANDED_TABLES", info.filename,
                                              hits, counters, pdf_rows)
                    except Exception as exc:
                        errors.append({"trustees_vintage": vintage, "artifact": "EXPANDED_TABLES",
                                       "member_name": info.filename,
                                       "error": f"{type(exc).__name__}: {exc}"})
        except Exception as exc:
            errors.append({"trustees_vintage": vintage, "artifact": "EXPANDED_TABLES",
                           "member_name": path.name, "error": f"{type(exc).__name__}: {exc}"})

    write_csv(VAL / "cms_medicare_trustees_private_plans_hits.csv", hits,
              ["trustees_vintage", "artifact", "member_name", "surface", "location",
               "semantic_label", "observation_year_tokens", "context"])
    write_csv(VAL / "cms_medicare_trustees_private_plans_members.csv", members,
              ["trustees_vintage", "artifact", "member_name", "extension", "member_bytes"])
    write_csv(VAL / "cms_medicare_trustees_private_plans_sheets.csv", sheets,
              ["trustees_vintage", "artifact", "member_name", "sheet_name",
               "rows_observed", "columns_observed", "status", "error"])
    write_csv(VAL / "cms_medicare_trustees_private_plans_pdfs.csv", pdf_rows,
              ["trustees_vintage", "artifact", "member_name", "pages",
               "pages_extractable", "status", "error"])
    write_csv(VAL / "cms_medicare_trustees_private_plans_errors.csv", errors,
              ["trustees_vintage", "artifact", "member_name", "error"])

    # Build vintage x target-year presence matrix from contexts that contain at least
    # one substantive private-plan semantic label AND an explicit year token.
    substantive = {
        "PRIVATE_HEALTH_PLANS", "HMO", "LOCAL_PPO", "REGIONAL_PPO", "PFFS",
        "SNP", "REBATE_EXPENDITURES", "BID_RELATED_EXPENDITURES",
        "TOTAL_EXPENDITURES", "PER_CAPITA", "ENROLLMENT", "PART_C",
    }
    present = defaultdict(set)
    labels_by_vintage = defaultdict(set)
    for h in hits:
        label = h["semantic_label"]
        if label in substantive:
            labels_by_vintage[int(h["trustees_vintage"])].add(label)
            for y in filter(None, h["observation_year_tokens"].split(";")):
                yi = int(y)
                if yi in TARGET_OBSERVATION_YEARS:
                    present[int(h["trustees_vintage"])].add(yi)

    matrix = []
    for obs_y in TARGET_OBSERVATION_YEARS:
        row = {"observation_year": obs_y}
        for vintage in VINTAGES:
            row[str(vintage)] = "X" if obs_y in present[vintage] else ""
        matrix.append(row)
    write_csv(VAL / "cms_medicare_trustees_private_plans_vintage_year_matrix.csv",
              matrix, ["observation_year"] + [str(x) for x in VINTAGES])

    coverage = []
    required_labels = [
        "PRIVATE_HEALTH_PLANS", "HMO", "LOCAL_PPO", "REBATE_EXPENDITURES",
        "TOTAL_EXPENDITURES", "PER_CAPITA",
    ]
    for vintage in VINTAGES:
        row = {"trustees_vintage": vintage}
        for label in required_labels:
            row[label] = "FOUND" if label in labels_by_vintage[vintage] else "NOT_FOUND"
        row["target_year_tokens"] = ";".join(map(str, sorted(present[vintage])))
        coverage.append(row)
    write_csv(VAL / "cms_medicare_trustees_private_plans_coverage.csv", coverage,
              ["trustees_vintage"] + required_labels + ["target_year_tokens"])

    report_complete = sorted(reports) == VINTAGES
    package_complete = sorted(packages) == VINTAGES
    private_found_all = all("PRIVATE_HEALTH_PLANS" in labels_by_vintage[y] for y in VINTAGES)
    hmo_found_all = all("HMO" in labels_by_vintage[y] for y in VINTAGES)
    localppo_found_all = all("LOCAL_PPO" in labels_by_vintage[y] for y in VINTAGES)
    rebate_found_all = all("REBATE_EXPENDITURES" in labels_by_vintage[y] for y in VINTAGES)
    no_errors = len(errors) == 0

    checks = [
        ("Annual report source universe 2015-2026 present", report_complete),
        ("Expanded-package source universe 2015-2026 present", package_complete),
        ("Private Health Plans terminology found in every vintage", private_found_all),
        ("HMO terminology found in every vintage", hmo_found_all),
        ("Local PPO terminology found in every vintage", localppo_found_all),
        ("Rebate expenditure terminology found in every vintage", rebate_found_all),
        ("Profile/read errors", no_errors),
    ]

    # Semantic variation is expected; absence of one exact phrase is informative rather
    # than grounds for hiding results. Overall PASS requires core HMO/Local PPO/rebate
    # concepts in every vintage because those are our immediate profiling target.
    overall = all(ok for _, ok in checks)

    counts = Counter(h["semantic_label"] for h in hits)
    lines = [
        "=" * 100,
        "CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS SEMANTIC PROFILE v0.1",
        "=" * 100,
        "",
        f"Trustees vintages expected                 : {len(VINTAGES)}",
        f"Annual reports present                     : {len(reports)}",
        f"Expanded packages present                  : {len(packages)}",
        f"Expanded-package members inventoried       : {len(members)}",
        f"Spreadsheet sheets profiled                : {len(sheets)}",
        f"PDF artifacts profiled                     : {len(pdf_rows)}",
        f"Semantic/status hits recorded              : {len(hits)}",
        f"Profile/read errors                        : {len(errors)}",
        "",
        "SEMANTIC HIT COUNTS",
        "-" * 100,
    ]
    for label in sorted(counts):
        lines.append(f"{label:<40} {counts[label]:>8,}")

    lines += ["", "CORE COVERAGE BY TRUSTEES VINTAGE", "-" * 100]
    for row in coverage:
        lines.append(
            f"{row['trustees_vintage']}: "
            f"PrivatePlans={row['PRIVATE_HEALTH_PLANS']}  "
            f"HMO={row['HMO']}  "
            f"LocalPPO={row['LOCAL_PPO']}  "
            f"Rebate={row['REBATE_EXPENDITURES']}  "
            f"TotalExp={row['TOTAL_EXPENDITURES']}  "
            f"PerCapita={row['PER_CAPITA']}  "
            f"Years=[{row['target_year_tokens']}]"
        )

    lines += ["", "VALIDATION CHECKS", "-" * 100]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)
    lines += [
        "",
        f"OVERALL SEMANTIC PROFILE STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "IMPORTANT:",
        "This profile records terminology and source structure only. Year tokens indicate that a year",
        "appears near relevant terminology; they do NOT prove that a numeric observation was extracted.",
        "Likewise, actual/historical/estimate/projected words are recorded as evidence but are NOT yet",
        "assigned to individual observations.",
        "",
        "No Trustees payment value has been extracted by this script.",
        "",
        "OUTPUTS",
        "-" * 100,
        str(VAL / "cms_medicare_trustees_private_plans_hits.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_members.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_sheets.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_pdfs.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_errors.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_vintage_year_matrix.csv"),
        str(VAL / "cms_medicare_trustees_private_plans_coverage.csv"),
    ]
    summary = VAL / "cms_medicare_trustees_private_plans_profile_summary.txt"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
