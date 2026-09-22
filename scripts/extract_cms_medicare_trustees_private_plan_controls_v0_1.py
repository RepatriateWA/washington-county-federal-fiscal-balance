#!/usr/bin/env python3
"""
CMS Medicare Trustees Private Health Plans raw control extractor v0.1
====================================================================

WCFFBP provenance-preserving extraction stage.

Purpose
-------
Extract raw numeric observations from the preserved annual Medicare Trustees
Report PDFs for the Private Health Plans control tables:

    IV.C2  Medicare Payments to Private Health Plans, by Trust Fund
    IV.C3  Incurred Expenditures per Private Health Plan Enrollee
    IV.C4  Key Factors for Medicare Advantage Expenditure Estimates

Design boundaries
-----------------
* READ ONLY with respect to preserved source artifacts.
* No network requests.
* No PostgreSQL writes.
* No preferred-vintage selection.
* No actual/projected status assignment.
* No Washington reconciliation.
* No imputation.
* No decomposition of 2015-2016 LCCP into HMO/PPO.
* IV.C4 is extracted only when present.
* Every extracted row retains trustees_vintage and observation_year separately.
* Raw source labels are retained alongside conservative normalized labels.
* Arithmetic identities are validated but are not used to manufacture values.

The parser uses the annual-report PDF text because the prior structural inspection
established the relevant table structures there.  Expanded-table packages remain
preserved provenance but are not required by this v0.1 numeric extractor.

Run from repository root:
    python scripts/extract_cms_medicare_trustees_private_plan_controls_v0_1.py
"""

from __future__ import annotations

import csv
import hashlib
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees"
REPORT_DIR = BASE / "reports"
OUTDIR = BASE / "validation" / "private_health_plans_controls_raw_v0_1"

VINTAGES = list(range(2015, 2027))

TABLE_C2 = "IV.C2"
TABLE_C3 = "IV.C3"
TABLE_C4 = "IV.C4"

DASHES = {"—", "–", "-", "n/a", "N/A", "na", "NA", ""}

TABLE_PATTERNS = {
    TABLE_C2: re.compile(
        r"Table\s+IV\.?\s*C\.?\s*2\.?\s*[—\-–.]?\s*Medicare Payments to Private Health Plans",
        re.I,
    ),
    TABLE_C3: re.compile(
        r"Table\s+IV\.?\s*C\.?\s*3\.?\s*[—\-–.]?\s*Incurred Expenditures per Private Health Plan Enrollee",
        re.I,
    ),
    TABLE_C4: re.compile(
        r"Table\s+IV\.?\s*C\.?\s*4\.?\s*[—\-–.]?\s*Key Factors for Medicare Advantage Expenditure Estimates",
        re.I,
    ),
}

NEXT_TABLE_RE = re.compile(r"\bTable\s+IV\.?\s*[A-Z]\.?\s*\d+", re.I)

YEAR_LINE_RE = re.compile(r"^\s*((?:19|20)\d{2})\s+(.*)$")
NUM_RE = re.compile(
    r"""
    (?:
        \$?\(?-?\d[\d,]*(?:\.\d+)?\)?%?
        |
        n/?a
        |
        [—–-]
    )
    """,
    re.I | re.X,
)

C2_BLOCKS = {
    "BID": "BID",
    "REBATE": "REBATE",
    "TOTAL": "TOTAL",
    "PART_A_PERCENT": "PART_A_PERCENT",
    "CASH_BASIS": "CASH_BASIS",
}

C3_COMPONENT_MARKERS = [
    ("BID_BASED", re.compile(r"\bBid[- ]based expenditures", re.I)),
    ("REBATE", re.compile(r"\bRebate expenditures", re.I)),
    ("TOTAL", re.compile(r"\bTotal expenditures", re.I)),
]

C4_FIELD_PATTERNS = [
    ("FFS_USPCC_PMPM", re.compile(r"FFS\s+USPCC\s+PMPM", re.I)),
    ("BENCHMARK_PMPM", re.compile(r"Benchmark\s+PMPM", re.I)),
    ("BID_PMPM", re.compile(r"\bBid\s+PMPM", re.I)),
    ("BID_TO_BENCHMARK_RATIO", re.compile(r"Bid[- ]to[- ]benchmark\s+ratio", re.I)),
    ("REBATE_PMPM", re.compile(r"Rebate\s+PMPM", re.I)),
    ("REBATE_TO_BID_RATIO", re.compile(r"Rebate[- ]to[- ]bid\s+ratio", re.I)),
    ("AVERAGE_FINAL_RISK_SCORE", re.compile(r"Average\s+final\s+risk\s+scores?", re.I)),
]


@dataclass
class TableText:
    vintage: int
    table_id: str
    page_number: int
    source_file: Path
    source_sha256: str
    text: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def parse_numeric(token: str) -> tuple[Optional[float], str]:
    raw = token.strip()
    if raw in DASHES or raw.lower() in {"n/a", "na"}:
        return None, "SOURCE_MISSING"
    percent = raw.endswith("%")
    t = raw.replace("$", "").replace(",", "").replace("%", "").strip()
    negative = t.startswith("(") and t.endswith(")")
    if negative:
        t = t[1:-1]
    try:
        value = float(t)
        if negative:
            value = -value
        return value, "NUMERIC_PERCENT" if percent else "NUMERIC"
    except ValueError:
        return None, "UNPARSED"


def report_path(vintage: int) -> Path:
    return REPORT_DIR / f"medicare_trustees_{vintage}.pdf"


def extract_tables_from_pdf(path: Path, vintage: int) -> tuple[list[TableText], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    tables: list[TableText] = []
    if PdfReader is None:
        errors.append({
            "trustees_vintage": vintage,
            "source_file": str(path.relative_to(ROOT)),
            "table_id": "",
            "page_number": "",
            "error": "pypdf is not installed",
        })
        return tables, errors

    digest = sha256_file(path)
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        errors.append({
            "trustees_vintage": vintage,
            "source_file": str(path.relative_to(ROOT)),
            "table_id": "",
            "page_number": "",
            "error": f"{type(exc).__name__}: {exc}",
        })
        return tables, errors

    page_texts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            page_texts.append(clean_text(page.extract_text() or ""))
        except Exception as exc:
            page_texts.append("")
            errors.append({
                "trustees_vintage": vintage,
                "source_file": str(path.relative_to(ROOT)),
                "table_id": "",
                "page_number": i + 1,
                "error": f"page extraction {type(exc).__name__}: {exc}",
            })

    for table_id, pattern in TABLE_PATTERNS.items():
        found = False
        for i, text in enumerate(page_texts):
            m = pattern.search(text)
            if not m:
                continue
            found = True
            # Relevant Trustees tables generally fit on one page, but append the
            # next page when the current page appears to end mid-table.
            block = text[m.start():]
            if i + 1 < len(page_texts):
                next_text = page_texts[i + 1]
                if table_id in {TABLE_C3, TABLE_C4} and not re.search(
                    r"\b(?:Note:|Source:|e\.)\b", block[-800:], re.I
                ):
                    block += "\n" + next_text[:8000]
            tables.append(TableText(
                vintage=vintage,
                table_id=table_id,
                page_number=i + 1,
                source_file=path,
                source_sha256=digest,
                text=block,
            ))
            break
        if not found and not (table_id == TABLE_C4 and vintage < 2024):
            errors.append({
                "trustees_vintage": vintage,
                "source_file": str(path.relative_to(ROOT)),
                "table_id": table_id,
                "page_number": "",
                "error": "table title not found in annual-report PDF text",
            })
    return tables, errors


def source_row_base(t: TableText) -> dict[str, Any]:
    return {
        "trustees_vintage": t.vintage,
        "table_id": t.table_id,
        "source_file": str(t.source_file.relative_to(ROOT)),
        "source_sha256": t.source_sha256,
        "source_page": t.page_number,
    }


def table_lines(t: TableText) -> list[str]:
    # pypdf often emits a useful physical line structure; retain it.
    return [line.strip() for line in t.text.splitlines() if line.strip()]


def extract_c2(t: TableText) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    IV.C2 has changed presentation:
      older vintages can show separate Part A and Part B blocks;
      later vintages show combined total private-plan expenditures plus Part A %.
    We preserve the source accounting scope explicitly.
    """
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    lines = table_lines(t)

    scope = "COMBINED_PART_A_PART_B"
    for line_no, line in enumerate(lines, 1):
        low = line.lower()
        if "expenditures from the hi" in low or "part a" in low and "trust fund" in low:
            scope = "PART_A_HI"
            continue
        if "expenditures from the part b" in low or ("part b" in low and "smi" in low and "trust fund" in low):
            scope = "PART_B_SMI"
            continue

        m = YEAR_LINE_RE.match(line)
        if not m:
            continue
        year = int(m.group(1))
        tokens = NUM_RE.findall(m.group(2))
        if len(tokens) < 4:
            continue

        # Combined form: Bid, Rebate, Total, Part A %, Cash.
        # Older split form: Bid, Rebate, Total, Cash.
        fields = (
            ["BID", "REBATE", "TOTAL", "PART_A_PERCENT", "CASH_BASIS"]
            if len(tokens) >= 5 and scope == "COMBINED_PART_A_PART_B"
            else ["BID", "REBATE", "TOTAL", "CASH_BASIS"]
        )
        for idx, field in enumerate(fields):
            if idx >= len(tokens):
                break
            value, value_status = parse_numeric(tokens[idx])
            unit = "PERCENT" if field == "PART_A_PERCENT" else "BILLIONS_USD"
            row = source_row_base(t)
            row.update({
                "observation_year": year,
                "accounting_scope": scope,
                "plan_type_source": "TOTAL_PRIVATE_HEALTH_PLANS",
                "plan_type_normalized": "TOTAL_PRIVATE_HEALTH_PLANS",
                "component_source": field,
                "component_normalized": field,
                "value": "" if value is None else value,
                "unit": unit,
                "basis": "CASH" if field == "CASH_BASIS" else "INCURRED",
                "value_status": value_status,
                "source_row_number": line_no,
                "source_row_text": line,
                "observation_status": "UNASSIGNED",
                "selection_reason": "RAW_SOURCE_OBSERVATION",
            })
            rows.append(row)

    if not rows:
        errors.append({
            **source_row_base(t),
            "error": "IV.C2 parser extracted zero observations",
        })
    return rows, errors


def detect_c3_header(text: str, vintage: int) -> list[tuple[str, str]]:
    """
    Return ordered (source_label, normalized_label) plan columns.

    2015-2016 source uses LCCP as a combined category.
    2017+ source explicitly splits Local CCP into HMO and PPO.
    """
    if vintage <= 2016:
        return [
            ("LCCP", "LOCAL_CCP_COMBINED"),
            ("PFFS", "PFFS"),
            ("RPPO", "REGIONAL_PPO"),
            ("SNP", "SNP"),
            ("Other", "OTHER"),
            ("Total", "TOTAL_PRIVATE_HEALTH_PLANS"),
        ]
    return [
        ("HMO", "LOCAL_CCP_HMO"),
        ("PPO", "LOCAL_CCP_PPO"),
        ("Regional PPO", "REGIONAL_PPO"),
        ("PFFS", "PFFS"),
        ("SNP", "SNP"),
        ("Other", "OTHER"),
        ("Total", "TOTAL_PRIVATE_HEALTH_PLANS"),
    ]


def extract_c3(t: TableText) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    lines = table_lines(t)
    columns = detect_c3_header(t.text, t.vintage)

    component: Optional[str] = None
    component_source = ""
    for line_no, line in enumerate(lines, 1):
        for normalized, marker in C3_COMPONENT_MARKERS:
            if marker.search(line):
                component = normalized
                component_source = marker.search(line).group(0)
                # The first year can be on the same physical line after marker.
                break

        # A single PDF line can contain a marker plus the first year. Parse all
        # year-start segments on the line.
        segments = re.split(r"(?=(?:^|\s)(?:19|20)\d{2}\s)", line)
        for seg in segments:
            seg = seg.strip()
            m = YEAR_LINE_RE.match(seg)
            if not m or component is None:
                continue
            year = int(m.group(1))
            tokens = NUM_RE.findall(m.group(2))
            if len(tokens) < len(columns):
                continue
            tokens = tokens[:len(columns)]

            for (src_plan, norm_plan), token in zip(columns, tokens):
                value, value_status = parse_numeric(token)
                row = source_row_base(t)
                row.update({
                    "observation_year": year,
                    "accounting_scope": "PART_A_PLUS_PART_B",
                    "plan_type_source": src_plan,
                    "plan_type_normalized": norm_plan,
                    "component_source": component_source,
                    "component_normalized": component,
                    "value": "" if value is None else value,
                    "unit": "USD_PER_ENROLLEE_PER_YEAR",
                    "basis": "INCURRED",
                    "value_status": value_status,
                    "source_row_number": line_no,
                    "source_row_text": line,
                    "observation_status": "UNASSIGNED",
                    "selection_reason": "RAW_SOURCE_OBSERVATION",
                })
                rows.append(row)

    if not rows:
        errors.append({
            **source_row_base(t),
            "error": "IV.C3 parser extracted zero observations",
        })
    return rows, errors


def c4_fields_from_header(text: str) -> list[tuple[str, str]]:
    """
    Conservative ordered field list.  Trustees IV.C4 is expected to contain
    these seven concepts; only concepts actually detectable in the table text
    are returned.
    """
    out = []
    for normalized, pattern in C4_FIELD_PATTERNS:
        m = pattern.search(text)
        if m:
            out.append((m.group(0), normalized))
    # If PDF extraction omits exact Bid/Rebate PMPM labels but the known table
    # title is present, do NOT synthesize them. Missing labels stay missing.
    return out


def extract_c4(t: TableText) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    lines = table_lines(t)
    fields = c4_fields_from_header(t.text)

    if not fields:
        errors.append({
            **source_row_base(t),
            "error": "IV.C4 table found but no recognized field labels detected",
        })
        return rows, errors

    for line_no, line in enumerate(lines, 1):
        m = YEAR_LINE_RE.match(line)
        if not m:
            continue
        year = int(m.group(1))
        tokens = NUM_RE.findall(m.group(2))
        if len(tokens) < len(fields):
            continue
        tokens = tokens[:len(fields)]

        for (src_field, norm_field), token in zip(fields, tokens):
            value, value_status = parse_numeric(token)
            if norm_field in {"BID_TO_BENCHMARK_RATIO", "REBATE_TO_BID_RATIO"}:
                unit = "PERCENT"
            elif norm_field == "AVERAGE_FINAL_RISK_SCORE":
                unit = "RISK_SCORE"
            else:
                unit = "USD_PMPM"
            row = source_row_base(t)
            row.update({
                "observation_year": year,
                "accounting_scope": "IV_C4_PUBLISHED_SCOPE",
                "plan_type_source": "SOURCE_TABLE_SCOPE",
                "plan_type_normalized": "SOURCE_TABLE_SCOPE",
                "component_source": src_field,
                "component_normalized": norm_field,
                "value": "" if value is None else value,
                "unit": unit,
                "basis": "PUBLISHED_FACTOR",
                "value_status": value_status,
                "source_row_number": line_no,
                "source_row_text": line,
                "observation_status": "UNASSIGNED",
                "selection_reason": "RAW_SOURCE_OBSERVATION",
            })
            rows.append(row)

    if not rows:
        errors.append({
            **source_row_base(t),
            "error": "IV.C4 parser extracted zero observations",
        })
    return rows, errors


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def numeric(row: dict[str, Any]) -> Optional[float]:
    v = row.get("value", "")
    if v == "" or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_identity_checks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # IV.C2: incurred Bid + Rebate = Total, within vintage/year/scope.
    c2 = {}
    for r in rows:
        if r["table_id"] != TABLE_C2 or r["basis"] != "INCURRED":
            continue
        if r["component_normalized"] not in {"BID", "REBATE", "TOTAL"}:
            continue
        key = (
            r["trustees_vintage"], r["observation_year"],
            r["accounting_scope"], r["plan_type_normalized"],
        )
        c2.setdefault(key, {})[r["component_normalized"]] = numeric(r)

    for key, vals in sorted(c2.items()):
        bid, rebate, total = vals.get("BID"), vals.get("REBATE"), vals.get("TOTAL")
        if None in (bid, rebate, total):
            continue
        diff = (bid + rebate) - total
        checks.append({
            "trustees_vintage": key[0],
            "table_id": TABLE_C2,
            "observation_year": key[1],
            "accounting_scope": key[2],
            "plan_type_normalized": key[3],
            "identity": "BID_PLUS_REBATE_EQUALS_TOTAL",
            "lhs": bid + rebate,
            "rhs": total,
            "difference": diff,
            "tolerance": 0.11,  # table values are rounded to $0.1B
            "status": "PASS" if abs(diff) <= 0.11 else "FAIL",
        })

    # IV.C3: Bid-based + Rebate = Total, rounded whole dollars.
    c3 = {}
    for r in rows:
        if r["table_id"] != TABLE_C3:
            continue
        if r["component_normalized"] not in {"BID_BASED", "REBATE", "TOTAL"}:
            continue
        key = (
            r["trustees_vintage"], r["observation_year"],
            r["plan_type_normalized"],
        )
        c3.setdefault(key, {})[r["component_normalized"]] = numeric(r)

    for key, vals in sorted(c3.items()):
        bid, rebate, total = vals.get("BID_BASED"), vals.get("REBATE"), vals.get("TOTAL")
        if None in (bid, rebate, total):
            continue
        diff = (bid + rebate) - total
        checks.append({
            "trustees_vintage": key[0],
            "table_id": TABLE_C3,
            "observation_year": key[1],
            "accounting_scope": "PART_A_PLUS_PART_B",
            "plan_type_normalized": key[2],
            "identity": "BID_BASED_PLUS_REBATE_EQUALS_TOTAL",
            "lhs": bid + rebate,
            "rhs": total,
            "difference": diff,
            "tolerance": 1.1,  # whole-dollar published rounding
            "status": "PASS" if abs(diff) <= 1.1 else "FAIL",
        })

    return checks


def build_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agg: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        key = (r["trustees_vintage"], r["table_id"])
        x = agg.setdefault(key, {
            "trustees_vintage": r["trustees_vintage"],
            "table_id": r["table_id"],
            "rows": 0,
            "numeric_rows": 0,
            "source_missing_rows": 0,
            "min_observation_year": None,
            "max_observation_year": None,
            "plan_types": set(),
            "components": set(),
            "units": set(),
        })
        x["rows"] += 1
        if r["value_status"].startswith("NUMERIC"):
            x["numeric_rows"] += 1
        elif r["value_status"] == "SOURCE_MISSING":
            x["source_missing_rows"] += 1
        y = int(r["observation_year"])
        x["min_observation_year"] = y if x["min_observation_year"] is None else min(x["min_observation_year"], y)
        x["max_observation_year"] = y if x["max_observation_year"] is None else max(x["max_observation_year"], y)
        x["plan_types"].add(r["plan_type_normalized"])
        x["components"].add(r["component_normalized"])
        x["units"].add(r["unit"])

    out = []
    for key in sorted(agg):
        x = agg[key]
        out.append({
            **{k: v for k, v in x.items() if not isinstance(v, set)},
            "plan_types": ";".join(sorted(x["plan_types"])),
            "components": ";".join(sorted(x["components"])),
            "units": ";".join(sorted(x["units"])),
        })
    return out


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print("=" * 108)
    print("CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS RAW CONTROL EXTRACTOR v0.1")
    print("=" * 108)
    print("No preferred-vintage selection, status assignment, reconciliation, imputation, or DB writes.\n")

    missing = [report_path(y) for y in VINTAGES if not report_path(y).exists()]
    if missing:
        print("FAIL  Missing required annual-report PDF(s):")
        for p in missing:
            print(f"      {p}")
        return 1

    all_tables: list[TableText] = []
    errors: list[dict[str, Any]] = []
    for y in VINTAGES:
        tables, errs = extract_tables_from_pdf(report_path(y), y)
        all_tables.extend(tables)
        errors.extend(errs)

    rows: list[dict[str, Any]] = []
    for t in all_tables:
        if t.table_id == TABLE_C2:
            extracted, errs = extract_c2(t)
        elif t.table_id == TABLE_C3:
            extracted, errs = extract_c3(t)
        elif t.table_id == TABLE_C4:
            extracted, errs = extract_c4(t)
        else:
            continue
        rows.extend(extracted)
        errors.extend(errs)

    # Stable deterministic ordering.
    rows.sort(key=lambda r: (
        int(r["trustees_vintage"]),
        r["table_id"],
        int(r["observation_year"]),
        r["accounting_scope"],
        r["plan_type_normalized"],
        r["component_normalized"],
    ))

    identity = build_identity_checks(rows)
    inventory = build_inventory(rows)

    raw_fields = [
        "trustees_vintage", "observation_year", "table_id",
        "accounting_scope", "plan_type_source", "plan_type_normalized",
        "component_source", "component_normalized", "value", "unit", "basis",
        "value_status", "observation_status", "selection_reason",
        "source_file", "source_sha256", "source_page",
        "source_row_number", "source_row_text",
    ]
    write_csv(
        OUTDIR / "cms_medicare_trustees_private_plan_controls_raw.csv",
        rows, raw_fields
    )
    write_csv(
        OUTDIR / "cms_medicare_trustees_private_plan_controls_inventory.csv",
        inventory,
        [
            "trustees_vintage", "table_id", "rows", "numeric_rows",
            "source_missing_rows", "min_observation_year", "max_observation_year",
            "plan_types", "components", "units",
        ],
    )
    write_csv(
        OUTDIR / "cms_medicare_trustees_private_plan_controls_identity_checks.csv",
        identity,
        [
            "trustees_vintage", "table_id", "observation_year",
            "accounting_scope", "plan_type_normalized", "identity",
            "lhs", "rhs", "difference", "tolerance", "status",
        ],
    )
    write_csv(
        OUTDIR / "cms_medicare_trustees_private_plan_controls_errors.csv",
        errors,
        [
            "trustees_vintage", "source_file", "table_id",
            "page_number", "source_page", "error",
        ],
    )

    table_by_vintage = {(t.vintage, t.table_id) for t in all_tables}
    c2_complete = all((y, TABLE_C2) in table_by_vintage for y in VINTAGES)
    c3_complete = all((y, TABLE_C3) in table_by_vintage for y in VINTAGES)
    c4_pre_absent = all((y, TABLE_C4) not in table_by_vintage for y in range(2015, 2024))
    c4_post_present = all((y, TABLE_C4) in table_by_vintage for y in range(2024, 2027))

    c3_early_combined = all(
        any(
            r["trustees_vintage"] == y
            and r["table_id"] == TABLE_C3
            and r["plan_type_normalized"] == "LOCAL_CCP_COMBINED"
            for r in rows
        )
        for y in (2015, 2016)
    )
    c3_late_split = all(
        any(
            r["trustees_vintage"] == y
            and r["table_id"] == TABLE_C3
            and r["plan_type_normalized"] == "LOCAL_CCP_HMO"
            for r in rows
        )
        and any(
            r["trustees_vintage"] == y
            and r["table_id"] == TABLE_C3
            and r["plan_type_normalized"] == "LOCAL_CCP_PPO"
            for r in rows
        )
        for y in range(2017, 2027)
    )

    c3_components_all = all(
        {"BID_BASED", "REBATE", "TOTAL"}.issubset({
            r["component_normalized"]
            for r in rows
            if r["trustees_vintage"] == y and r["table_id"] == TABLE_C3
        })
        for y in VINTAGES
    )

    identity_failures = [r for r in identity if r["status"] == "FAIL"]
    unparsed = [r for r in rows if r["value_status"] == "UNPARSED"]

    checks = [
        ("Annual report source universe 2015-2026 present", not missing),
        ("IV.C2 found in every Trustees vintage", c2_complete),
        ("IV.C3 found in every Trustees vintage", c3_complete),
        ("IV.C4 absent before 2024 as structurally established", c4_pre_absent),
        ("IV.C4 present 2024-2026", c4_post_present),
        ("2015-2016 IV.C3 preserves combined LCCP", c3_early_combined),
        ("2017-2026 IV.C3 preserves separate Local CCP HMO/PPO", c3_late_split),
        ("IV.C3 bid/rebate/total components extracted every vintage", c3_components_all),
        ("No unparsed numeric tokens in extracted rows", len(unparsed) == 0),
        ("Published arithmetic identity checks", len(identity_failures) == 0),
        ("Extraction/read errors", len(errors) == 0),
    ]
    overall = all(ok for _, ok in checks)

    from collections import Counter
    counts = Counter(r["table_id"] for r in rows)
    numeric_counts = Counter(
        r["table_id"] for r in rows if r["value_status"].startswith("NUMERIC")
    )
    missing_counts = Counter(
        r["table_id"] for r in rows if r["value_status"] == "SOURCE_MISSING"
    )

    lines = [
        "=" * 108,
        "CMS MEDICARE TRUSTEES PRIVATE HEALTH PLANS RAW CONTROL EXTRACTOR v0.1",
        "=" * 108,
        "",
        "BOUNDARY",
        "No preferred-vintage selection, observation-status assignment, reconciliation, imputation, or DB writes.",
        "",
        f"Trustees vintages expected                  : {len(VINTAGES)}",
        f"Annual reports present                      : {len(VINTAGES) - len(missing)}",
        f"Tables structurally captured                : {len(all_tables)}",
        f"Raw observations extracted                  : {len(rows):,}",
        f"Identity checks                             : {len(identity):,}",
        f"Identity failures                           : {len(identity_failures):,}",
        f"Unparsed extracted tokens                   : {len(unparsed):,}",
        f"Extraction/read errors                      : {len(errors):,}",
        "",
        "OBSERVATIONS BY TABLE",
        "-" * 108,
    ]
    for tid in (TABLE_C2, TABLE_C3, TABLE_C4):
        lines.append(
            f"{tid:<7} rows={counts[tid]:>7,}  "
            f"numeric={numeric_counts[tid]:>7,}  "
            f"source-missing={missing_counts[tid]:>7,}"
        )

    lines += ["", "VALIDATION CHECKS", "-" * 108]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)

    lines += [
        "",
        f"OVERALL RAW EXTRACTION STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "A PASS means only that raw Trustees observations were extracted with source provenance and",
        "the expected versioned table structures were preserved. It does NOT choose a preferred",
        "Trustees vintage, classify observations as actual/projected, establish Washington comparability,",
        "or authorize any WCFFBP ledger inclusion.",
        "",
        "OUTPUTS",
        "-" * 108,
        str(OUTDIR / "cms_medicare_trustees_private_plan_controls_raw.csv"),
        str(OUTDIR / "cms_medicare_trustees_private_plan_controls_inventory.csv"),
        str(OUTDIR / "cms_medicare_trustees_private_plan_controls_identity_checks.csv"),
        str(OUTDIR / "cms_medicare_trustees_private_plan_controls_errors.csv"),
    ]

    summary = OUTDIR / "cms_medicare_trustees_private_plan_controls_summary.txt"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
