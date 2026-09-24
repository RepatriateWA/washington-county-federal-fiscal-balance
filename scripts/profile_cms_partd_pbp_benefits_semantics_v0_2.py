#!/usr/bin/env python3
"""
CMS Medicare Part D PBP Benefits structural/semantic profiler v0.2

Profiles the ten already-preserved official CMS PBP Benefits ZIPs CY2015-CY2024.

Purpose:
  - inventory ZIP members and tabular schemas;
  - identify Contract/PBP identifiers;
  - identify candidate Part-D/drug-benefit semantic fields;
  - inventory low-cardinality values for those candidate fields;
  - establish whether PBP Benefits can support a later exact
    (coverage year, Contract, PBP) Part-D status validator.

This script deliberately DOES NOT:
  - consume the 5,203,895 or 5,203,829 member-month controls;
  - classify any Contract+PBP as Part D / non-Part D;
  - propagate sibling-PBP or other-year status;
  - propagate payments;
  - impute values;
  - reconstruct payments;
  - write to PostgreSQL;
  - authorize ledger inclusion.
"""
from __future__ import annotations

import argparse, csv, io, re, sys, zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl

# CMS CY2024 includes very large free-text fields (for example transportation
# and dental benefit descriptions) that exceed Python csv's conservative
# default 131,072-byte field limit. Raising the parser ceiling preserves the
# source bytes/values; it does not truncate, normalize, or alter CMS data.
csv.field_size_limit(min(sys.maxsize, 10_000_000))

ROOT = Path("data/raw/cms/medicare_partd/pbp_benefits")
OUT = ROOT / "validation" / "pbp_benefits_semantic_profile_v0_2"
YEARS = tuple(range(2015, 2025))
MAX_DISTINCT_CAPTURE = 100
MAX_VALUE_LENGTH = 500

def clean(x: Any) -> str:
    return "" if x is None else str(x).strip()

def norm(x: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", clean(x).upper()).strip("_")

def decode(data: bytes):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    else:
        raise RuntimeError("Unable to decode delimited text.")
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",|\t;")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text, newline=""), dialect))

def choose_header(raw):
    """Select the most header-like row among first 60 rows."""
    cand = []
    for i, row in enumerate(raw[:60]):
        vals = [clean(x) for x in row]
        nonblank = sum(bool(x) for x in vals)
        textual = sum(bool(x) and not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", x) for x in vals)
        identifierish = sum(
            any(k in norm(x) for k in ("CONTRACT", "PBP", "PLAN", "DRUG", "PART_D", "BENEFIT", "RX"))
            for x in vals if x
        )
        cand.append((identifierish, nonblank, textual, -i, i, vals))
    if not cand:
        return 0, []
    *_, idx, header = max(cand)
    while header and not header[-1]:
        header.pop()
    return idx, header

def table_from_bytes(name: str, data: bytes):
    ext = Path(name).suffix.lower()
    if ext in {".csv", ".txt", ".tsv"}:
        raw = decode(data)
        if not raw:
            return []
        idx, header = choose_header(raw)
        rows = [r[:len(header)] for r in raw[idx + 1:] if any(clean(x) for x in r)]
        return [("", header, rows)]
    if ext in {".xlsx", ".xlsm"}:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out = []
        try:
            for ws in wb.worksheets:
                raw = list(ws.iter_rows(values_only=True))
                if not raw:
                    continue
                idx, header = choose_header(raw)
                rows = [list(r[:len(header)]) for r in raw[idx + 1:] if any(clean(x) for x in r)]
                out.append((ws.title, header, rows))
        finally:
            wb.close()
        return out
    return []

def field_role(field: str) -> str:
    z = norm(field)

    if z in {"CONTRACT", "CONTRACT_ID", "CONTRACT_NUMBER", "CONTRACTID", "H_NUMBER"}:
        return "CONTRACT"
    if "CONTRACT" in z and "NAME" not in z:
        return "CONTRACT"

    if z in {
        "PBP", "PBP_ID", "PBP_NUMBER", "PLAN_ID", "PLANID",
        "PLAN_BENEFIT_PACKAGE", "PLAN_BENEFIT_PACKAGE_ID",
        "PLAN_BENEFIT_PACKAGE_NUMBER"
    }:
        return "PLAN_PBP"
    if "PBP" in z and not any(k in z for k in ("NAME", "DESCRIPTION")):
        return "PLAN_PBP"

    # Strong semantic candidates for whether/how Part D / Rx benefits are offered.
    strong = (
        "PART_D", "PARTD", "PRESCRIPTION_DRUG", "DRUG_BENEFIT",
        "DRUG_COVERAGE", "RX_BENEFIT", "RX_COVERAGE",
        "MA_PD", "MAPD", "PDP"
    )
    if any(k in z for k in strong):
        return "PARTD_STRONG"

    # Broader benefit fields that may carry relevant status/detail after inspection.
    broader = (
        "DRUG", "PRESCRIPTION", "PHARMACY", "FORMULARY",
        "DEDUCTIBLE", "GAP_COVERAGE", "TIER", "COST_SHARING"
    )
    if any(k in z for k in broader):
        return "PARTD_CONTEXT"

    if z in {
        "PLAN_TYPE", "ORGANIZATION_TYPE", "PLAN_NAME",
        "MARKETING_NAME", "SNP_TYPE", "SPECIAL_NEEDS_PLAN_TYPE"
    }:
        return "PLAN_CONTEXT"

    return ""

def member_category(name: str) -> str:
    u = name.upper()
    if any(k in u for k in ("SECTION_RX", "SECTION D", "PART D", "PARTD", "DRUG", "RX")):
        return "PARTD_NAMED_MEMBER"
    if "PBP" in u:
        return "PBP_MEMBER"
    if "BENEFIT" in u:
        return "BENEFIT_MEMBER"
    return "OTHER"

def write_csv(path: Path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def locate_zip(root: Path, year: int):
    yd = root / str(year)
    if not yd.exists():
        return []
    return sorted(p for p in yd.glob("*.zip") if p.is_file())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--output-dir", type=Path, default=OUT)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    member_rows = []
    table_rows = []
    field_rows = []
    value_rows = []
    year_rows = []
    errors = []
    year_stats = {}

    for year in YEARS:
        zips = locate_zip(args.root, year)
        if len(zips) != 1:
            errors.append({
                "year": year, "source": str(args.root / str(year)),
                "error": f"Expected exactly one preserved PBP Benefits ZIP; found {len(zips)}"
            })
            year_stats[year] = Counter()
            continue

        zp = zips[0]
        stats = Counter()
        year_stats[year] = stats

        try:
            with zipfile.ZipFile(zp) as z:
                bad = z.testzip()
                if bad:
                    raise RuntimeError(f"ZIP integrity failure: {bad}")

                stats["zip_members"] = len(z.infolist())

                for info in z.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename
                    ext = Path(name).suffix.lower()
                    cat = member_category(name)

                    member_rows.append({
                        "year": year, "archive": str(zp), "member_name": name,
                        "member_category": cat, "extension": ext,
                        "uncompressed_bytes": info.file_size
                    })

                    if ext not in {".csv", ".txt", ".tsv", ".xlsx", ".xlsm"}:
                        continue

                    try:
                        blob = z.read(info)
                        parsed = table_from_bytes(name, blob)
                        for sheet, header, rows in parsed:
                            stats["tables"] += 1
                            roles = [field_role(h) for h in header]
                            contracts = [header[i] for i, r in enumerate(roles) if r == "CONTRACT"]
                            plans = [header[i] for i, r in enumerate(roles) if r == "PLAN_PBP"]
                            strong = [header[i] for i, r in enumerate(roles) if r == "PARTD_STRONG"]
                            context = [header[i] for i, r in enumerate(roles) if r == "PARTD_CONTEXT"]
                            pctx = [header[i] for i, r in enumerate(roles) if r == "PLAN_CONTEXT"]

                            has_ids = bool(contracts and plans)
                            has_sem = bool(strong or context)

                            if has_ids:
                                stats["tables_contract_pbp"] += 1
                            if has_ids and strong:
                                stats["tables_contract_pbp_strong"] += 1
                            if has_ids and has_sem:
                                stats["tables_contract_pbp_any_partd"] += 1

                            table_rows.append({
                                "year": year, "archive": str(zp),
                                "member_name": name, "member_category": cat,
                                "sheet_name": sheet, "row_count": len(rows),
                                "column_count": len(header),
                                "contract_fields": " | ".join(contracts),
                                "plan_pbp_fields": " | ".join(plans),
                                "strong_partd_fields": " | ".join(strong),
                                "partd_context_fields": " | ".join(context),
                                "plan_context_fields": " | ".join(pctx),
                                "has_contract_pbp": "YES" if has_ids else "NO",
                                "has_strong_partd_field": "YES" if strong else "NO",
                                "has_any_partd_candidate": "YES" if has_sem else "NO",
                            })

                            for i, h in enumerate(header):
                                role = roles[i]
                                if not role:
                                    continue
                                vals = Counter(clean(r[i]) if i < len(r) else "" for r in rows)
                                distinct = [v for v in vals if v != ""]
                                field_rows.append({
                                    "year": year, "member_name": name,
                                    "member_category": cat, "sheet_name": sheet,
                                    "field_name": h, "field_role": role,
                                    "row_count": len(rows),
                                    "nonblank_count": sum(vals[v] for v in distinct),
                                    "distinct_nonblank_values": len(distinct),
                                    "values_captured": "YES" if len(distinct) <= MAX_DISTINCT_CAPTURE else "NO"
                                })

                                if role in {"PARTD_STRONG", "PARTD_CONTEXT", "PLAN_CONTEXT"} and len(distinct) <= MAX_DISTINCT_CAPTURE:
                                    for v, count in vals.most_common():
                                        if not v:
                                            continue
                                        value_rows.append({
                                            "year": year, "member_name": name,
                                            "member_category": cat, "sheet_name": sheet,
                                            "field_name": h, "field_role": role,
                                            "value": v[:MAX_VALUE_LENGTH], "count": count
                                        })
                    except Exception as e:
                        errors.append({
                            "year": year, "source": f"{zp} -> {name}",
                            "error": f"{type(e).__name__}: {e}"
                        })
        except Exception as e:
            errors.append({
                "year": year, "source": str(zp),
                "error": f"{type(e).__name__}: {e}"
            })

    for year in YEARS:
        st = year_stats.get(year, Counter())
        year_rows.append({
            "year": year,
            "zip_members": st["zip_members"],
            "tables_profiled": st["tables"],
            "tables_with_contract_pbp": st["tables_contract_pbp"],
            "tables_with_contract_pbp_and_strong_partd": st["tables_contract_pbp_strong"],
            "tables_with_contract_pbp_and_any_partd_candidate": st["tables_contract_pbp_any_partd"]
        })

    checks = [
        ("exactly one preserved PBP Benefits ZIP for every CY2015-CY2024",
         all(len(locate_zip(args.root, y)) == 1 for y in YEARS)),
        ("all years contain readable tabular data",
         all(year_stats.get(y, Counter())["tables"] > 0 for y in YEARS)),
        ("all years expose Contract + PBP together in at least one table",
         all(year_stats.get(y, Counter())["tables_contract_pbp"] > 0 for y in YEARS)),
        ("all years expose Contract + PBP with at least one Part-D candidate field",
         all(year_stats.get(y, Counter())["tables_contract_pbp_any_partd"] > 0 for y in YEARS)),
        ("no structural/semantic profile errors", not errors),
    ]
    overall = all(v for _, v in checks)

    write_csv(args.output_dir / "cms_pbp_benefits_member_inventory.csv", member_rows,
              ["year","archive","member_name","member_category","extension","uncompressed_bytes"])
    write_csv(args.output_dir / "cms_pbp_benefits_table_summary.csv", table_rows,
              ["year","archive","member_name","member_category","sheet_name","row_count","column_count",
               "contract_fields","plan_pbp_fields","strong_partd_fields","partd_context_fields",
               "plan_context_fields","has_contract_pbp","has_strong_partd_field","has_any_partd_candidate"])
    write_csv(args.output_dir / "cms_pbp_benefits_semantic_fields.csv", field_rows,
              ["year","member_name","member_category","sheet_name","field_name","field_role",
               "row_count","nonblank_count","distinct_nonblank_values","values_captured"])
    write_csv(args.output_dir / "cms_pbp_benefits_semantic_values.csv", value_rows,
              ["year","member_name","member_category","sheet_name","field_name","field_role","value","count"])
    write_csv(args.output_dir / "cms_pbp_benefits_year_summary.csv", year_rows,
              ["year","zip_members","tables_profiled","tables_with_contract_pbp",
               "tables_with_contract_pbp_and_strong_partd",
               "tables_with_contract_pbp_and_any_partd_candidate"])
    write_csv(args.output_dir / "cms_pbp_benefits_profile_errors.csv", errors,
              ["year","source","error"])

    lines = [
        "CMS MEDICARE PART D PBP BENEFITS STRUCTURAL/SEMANTIC PROFILE v0.2",
        "=" * 76,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Source root: {args.root}",
        "",
        "BOUNDARY",
        "-" * 76,
        "Profiles preserved official CMS PBP Benefits packages only.",
        "Delimited-text parser ceiling raised to 10,000,000 bytes solely to admit",
        "large CMS free-text fields; source values are not truncated or normalized.",
        "Does not consume the unmatched member-month control and does not classify",
        "Part D status. No sibling-PBP/other-year propagation, payment propagation,",
        "imputation, reconstruction, DB writes, or ledger inclusion.",
        "",
        "YEAR SUMMARY",
        "-" * 76,
    ]
    for r in year_rows:
        lines.append(
            f"CY{r['year']}: ZIP members={r['zip_members']}, tables={r['tables_profiled']}, "
            f"Contract+PBP tables={r['tables_with_contract_pbp']}, "
            f"with strong Part-D fields={r['tables_with_contract_pbp_and_strong_partd']}, "
            f"with any Part-D candidate={r['tables_with_contract_pbp_and_any_partd_candidate']}"
        )
    lines += ["", "CHECKS", "-" * 76]
    lines += [f"{label}: {'PASS' if ok else 'FAIL'}" for label, ok in checks]
    lines += ["", "ERRORS", "-" * 76]
    if errors:
        lines += [f"CY{x['year']} | {x['source']} | {x['error']}" for x in errors]
    else:
        lines += ["None"]
    lines += [
        "",
        "INTERPRETIVE BOUNDARY",
        "-" * 76,
        "A PASS means the preserved PBP Benefits packages expose reproducible",
        "same-year plan-level structure suitable for designing a later status rule.",
        "It does not establish that any candidate field/value means Part D present",
        "or absent. That semantic decision requires inspection of the captured values.",
        "",
        "OVERALL",
        "-" * 76,
        f"OVERALL: {'PASS' if overall else 'FAIL'}",
    ]
    report = "\n".join(lines) + "\n"
    (args.output_dir / "cms_pbp_benefits_semantic_profile_report.txt").write_text(report, encoding="utf-8")
    print(report)
    print(f"Outputs: {args.output_dir}")
    return 0 if overall else 1

if __name__ == "__main__":
    sys.exit(main())
