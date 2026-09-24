#!/usr/bin/env python3
"""
validate_cms_partd_reconciliation_identity.py

Read-only validator for CMS Medicare Part D Plan Reconciliation workbooks.

Purpose
-------
For CY2015-CY2024, test the published accounting identity:

    Reconciliation Amount = LICS + Reinsurance + Risk Sharing

at:
  1. Contract-row level,
  2. Published Contract "Totals" row, and
  3. Published Parent Organization "Totals" row.

Also compare the published Contract and Parent Organization totals without
assuming they must be identical.

Boundary
--------
- READ ONLY.
- No imputation.
- No database writes.
- No ledger inclusion.
- Does not decide whether reconciliation amounts are additive to Part D Plans.
- RDS remains outside scope.
- Differences between Contract and Parent Organization published totals are
  evidence and are not silently reconciled.

Default source root:
    data/raw/cms/medicare_advantage/plan_payment

Default output:
    data/raw/cms/medicare_advantage/validation/
        partd_reconciliation_identity_v0_2/

PASS/FAIL philosophy
--------------------
The component identity is tested using a conservative dual tolerances: strict $0.02 and published-field $0.10 after parsing published numeric cells. This tolerance is
only for binary floating-point / displayed-cent effects; it is not an
economic materiality threshold.

Contract-vs-Parent-Organization differences are reported but do NOT fail the
component identity certification because the two published aggregation
universes can differ and the purpose here is to measure, not erase, that fact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import openpyxl


YEARS = range(2015, 2025)
STRICT_IDENTITY_TOLERANCE_DOLLARS = 0.02
PUBLISHED_ROUNDING_TOLERANCE_DOLLARS = 0.10

OUT_CONTRACT_ROWS = "cms_partd_reconciliation_contract_identity.csv"
OUT_PUBLISHED_TOTALS = "cms_partd_reconciliation_published_totals.csv"
OUT_AGG_COMPARISON = "cms_partd_reconciliation_aggregation_comparison.csv"
OUT_YEAR_SUMMARY = "cms_partd_reconciliation_identity_year_summary.csv"
OUT_SOURCE_MANIFEST = "cms_partd_reconciliation_identity_source_manifest.csv"
OUT_REPORT = "cms_partd_reconciliation_identity_report.txt"

REQUIRED = {
    "contract": "CONTRACT",
    "reconciliation_amount": "RECONCILIATION_AMOUNT",
    "lics": "LICS",
    "reinsurance": "REINSURANCE",
    "risk_sharing": "RISK_SHARING",
}


@dataclass
class WorkbookSource:
    year: int
    zip_path: Path
    member_name: str
    member_sha256: str
    zip_sha256: str
    duplicate_zip_count: int


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def norm(value: Any) -> str:
    s = clean_text(value).upper()
    s = re.sub(r"[^A-Z0-9]+", "_", s)
    return s.strip("_")


def parse_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        return x if math.isfinite(x) else None
    s = str(value).strip()
    if not s or s.upper() in {"N/A", "NA", "NULL", "NONE", "-", "--"}:
        return None
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "").strip()
    try:
        x = float(s)
    except ValueError:
        return None
    if negative:
        x = -x
    return x if math.isfinite(x) else None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def looks_like_reconciliation_member(name: str) -> bool:
    base = Path(name).name.lower()
    return (
        base.endswith(".xlsx")
        and "partd" in base.replace(" ", "")
        and "recon" in base
    )


def candidate_zips(year_dir: Path) -> list[Path]:
    return sorted(year_dir.glob("*.zip"))


def discover_source(root: Path, year: int) -> tuple[Optional[WorkbookSource], list[str]]:
    errors: list[str] = []
    year_dir = root / str(year)
    if not year_dir.exists():
        return None, [f"Missing year directory: {year_dir}"]

    found: list[tuple[Path, str, bytes]] = []
    for zp in candidate_zips(year_dir):
        try:
            with zipfile.ZipFile(zp) as zf:
                for member in zf.namelist():
                    if looks_like_reconciliation_member(member):
                        found.append((zp, member, zf.read(member)))
        except Exception as exc:
            errors.append(f"{year}: cannot inspect {zp}: {exc}")

    if not found:
        return None, errors + [f"{year}: no Part D reconciliation XLSX found"]

    by_member_hash: dict[str, list[tuple[Path, str, bytes]]] = {}
    for item in found:
        by_member_hash.setdefault(sha256_bytes(item[2]), []).append(item)

    if len(by_member_hash) != 1:
        details = "; ".join(
            f"{h[:12]}... ({len(items)} copies)" for h, items in by_member_hash.items()
        )
        return None, errors + [
            f"{year}: conflicting Part D reconciliation workbook bytes: {details}"
        ]

    member_hash, copies = next(iter(by_member_hash.items()))
    zp, member, _ = sorted(copies, key=lambda x: (str(x[0]), x[1]))[0]
    return WorkbookSource(
        year=year,
        zip_path=zp,
        member_name=member,
        member_sha256=member_hash,
        zip_sha256=sha256_file(zp),
        duplicate_zip_count=len({str(x[0]) for x in copies}),
    ), errors


def load_workbook_from_zip(source: WorkbookSource) -> openpyxl.Workbook:
    import io
    with zipfile.ZipFile(source.zip_path) as zf:
        data = zf.read(source.member_name)
    return openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)


def detect_header(ws, required_norms: Iterable[str], max_rows: int = 30) -> tuple[int, dict[str, int]]:
    required = set(required_norms)
    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_rows, values_only=True), 1):
        mapping: dict[str, int] = {}
        for col_idx, value in enumerate(row, 1):
            n = norm(value)
            if n:
                mapping[n] = col_idx
        if required.issubset(mapping):
            return row_idx, mapping
    raise ValueError(
        f"Could not locate header containing {sorted(required)} in sheet {ws.title!r}"
    )


def find_sheet(wb: openpyxl.Workbook, wanted: str) -> Optional[Any]:
    wanted_n = norm(wanted)
    for ws in wb.worksheets:
        if norm(ws.title) == wanted_n:
            return ws
    return None


def value_at(row: tuple[Any, ...], col1: int) -> Any:
    idx = col1 - 1
    return row[idx] if 0 <= idx < len(row) else None


def identity_status(rec: Optional[float], lics: Optional[float],
                    reins: Optional[float], risk: Optional[float]) -> tuple[str, str, Optional[float], Optional[float]]:
    vals = (rec, lics, reins, risk)
    if any(v is None for v in vals):
        return "NONNUMERIC_OR_MISSING", "NONNUMERIC_OR_MISSING", None, None
    components = float(lics) + float(reins) + float(risk)
    diff = float(rec) - components
    return (
        "PASS" if abs(diff) <= STRICT_IDENTITY_TOLERANCE_DOLLARS else "FAIL",
        "PASS" if abs(diff) <= PUBLISHED_ROUNDING_TOLERANCE_DOLLARS else "FAIL",
        components,
        diff,
    )


def fmt(x: Optional[float]) -> str:
    return "" if x is None else f"{x:.10f}"


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def process_sheet(year: int, ws, grain: str) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]], list[str]]:
    errors: list[str] = []
    entity_col = "CONTRACT" if grain == "CONTRACT" else "PARENT_ORGANIZATION"
    required = [
        entity_col,
        "RECONCILIATION_AMOUNT",
        "LICS",
        "REINSURANCE",
        "RISK_SHARING",
    ]
    try:
        header_row, cols = detect_header(ws, required)
    except Exception as exc:
        return [], None, [f"{year} {grain}: {exc}"]

    rows_out: list[dict[str, Any]] = []
    totals: Optional[dict[str, Any]] = None

    for excel_row, row in enumerate(ws.iter_rows(min_row=header_row + 1, values_only=True), header_row + 1):
        key_raw = value_at(row, cols[entity_col])
        key = clean_text(key_raw)
        if not key:
            continue

        rec = parse_number(value_at(row, cols["RECONCILIATION_AMOUNT"]))
        lics = parse_number(value_at(row, cols["LICS"]))
        reins = parse_number(value_at(row, cols["REINSURANCE"]))
        risk = parse_number(value_at(row, cols["RISK_SHARING"]))
        strict_status, published_status, components, diff = identity_status(rec, lics, reins, risk)

        record = {
            "payment_year": year,
            "grain": grain,
            "sheet_name": ws.title,
            "excel_row": excel_row,
            "entity_key": key,
            "reconciliation_amount": fmt(rec),
            "lics": fmt(lics),
            "reinsurance": fmt(reins),
            "risk_sharing": fmt(risk),
            "component_sum": fmt(components),
            "identity_difference": fmt(diff),
            "identity_abs_difference": fmt(abs(diff) if diff is not None else None),
            "strict_identity_status": strict_status,
            "published_rounding_identity_status": published_status,
        }

        if norm(key) == "TOTALS":
            totals = record
        else:
            rows_out.append(record)

    if totals is None:
        errors.append(f"{year} {grain}: published Totals row not found")
    return rows_out, totals, errors

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("data/raw/cms/medicare_advantage/plan_payment"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "data/raw/cms/medicare_advantage/validation/"
            "partd_reconciliation_identity_v0_2"
        ),
    )
    args = parser.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    generated = datetime.now(timezone.utc).isoformat()

    manifest: list[dict[str, Any]] = []
    contract_rows: list[dict[str, Any]] = []
    published_totals: list[dict[str, Any]] = []
    aggregation: list[dict[str, Any]] = []
    year_summary: list[dict[str, Any]] = []
    global_errors: list[str] = []

    for year in YEARS:
        source, discovery_errors = discover_source(args.root, year)
        global_errors.extend(discovery_errors)
        if source is None:
            year_summary.append({
                "payment_year": year,
                "source_status": "FAIL",
                "contract_rows": 0,
                "contract_identity_pass": 0,
                "contract_identity_fail": 0,
                "contract_nonnumeric_or_missing": 0,
                "contract_total_status": "NOT_RUN",
                "parent_total_status": "NOT_RUN",
                "overall_identity_status": "FAIL",
            })
            continue

        manifest.append({
            "payment_year": year,
            "zip_path": str(source.zip_path),
            "zip_sha256": source.zip_sha256,
            "member_name": source.member_name,
            "member_sha256": source.member_sha256,
            "duplicate_zip_count_with_identical_member": source.duplicate_zip_count,
        })

        try:
            wb = load_workbook_from_zip(source)
        except Exception as exc:
            global_errors.append(f"{year}: workbook open failure: {exc}")
            continue

        contract_ws = find_sheet(wb, "Contract")
        parent_ws = find_sheet(wb, "Parent Organization")
        if contract_ws is None:
            global_errors.append(f"{year}: Contract sheet missing")
        if parent_ws is None:
            global_errors.append(f"{year}: Parent Organization sheet missing")

        c_rows: list[dict[str, Any]] = []
        c_total = None
        p_total = None
        local_errors: list[str] = []

        if contract_ws is not None:
            c_rows, c_total, errs = process_sheet(year, contract_ws, "CONTRACT")
            local_errors.extend(errs)
            contract_rows.extend(c_rows)
            if c_total:
                published_totals.append(c_total)

        if parent_ws is not None:
            _, p_total, errs = process_sheet(year, parent_ws, "PARENT_ORGANIZATION")
            local_errors.extend(errs)
            if p_total:
                published_totals.append(p_total)

        global_errors.extend(local_errors)

        passes = sum(r["strict_identity_status"] == "PASS" for r in c_rows)
        fails = sum(r["strict_identity_status"] == "FAIL" for r in c_rows)
        missing = sum(r["strict_identity_status"] == "NONNUMERIC_OR_MISSING" for r in c_rows)

        c_status = c_total["published_rounding_identity_status"] if c_total else "NOT_RUN"
        p_status = p_total["published_rounding_identity_status"] if p_total else "NOT_RUN"

        if c_total and p_total:
            fields = ["reconciliation_amount", "lics", "reinsurance", "risk_sharing"]
            comp: dict[str, Any] = {"payment_year": year}
            for field in fields:
                cv = parse_number(c_total[field])
                pv = parse_number(p_total[field])
                diff = None if cv is None or pv is None else cv - pv
                comp[f"contract_{field}"] = fmt(cv)
                comp[f"parent_{field}"] = fmt(pv)
                comp[f"difference_{field}"] = fmt(diff)
                comp[f"abs_difference_{field}"] = fmt(abs(diff) if diff is not None else None)
            aggregation.append(comp)

        published_detail_fail = sum(
            r["published_rounding_identity_status"] == "FAIL" for r in c_rows
        )
        overall = (
            "PASS"
            if (
                not local_errors
                and published_detail_fail == 0
                and missing == 0
                and c_total is not None
                and p_total is not None
                and c_status == "PASS"
                and p_status == "PASS"
            )
            else "FAIL"
        )

        year_summary.append({
            "payment_year": year,
            "source_status": "PASS",
            "contract_rows": len(c_rows),
            "contract_identity_pass": passes,
            "contract_identity_fail": fails,
            "contract_nonnumeric_or_missing": missing,
            "contract_total_status": c_status,
            "parent_total_status": p_status,
            "overall_identity_status": overall,
        })

    row_fields = [
        "payment_year", "grain", "sheet_name", "excel_row", "entity_key",
        "reconciliation_amount", "lics", "reinsurance", "risk_sharing",
        "component_sum", "identity_difference", "identity_abs_difference",
        "strict_identity_status", "published_rounding_identity_status",
    ]
    write_csv(out / OUT_CONTRACT_ROWS, contract_rows, row_fields)
    write_csv(out / OUT_PUBLISHED_TOTALS, published_totals, row_fields)

    agg_fields = ["payment_year"]
    for field in ["reconciliation_amount", "lics", "reinsurance", "risk_sharing"]:
        agg_fields += [
            f"contract_{field}", f"parent_{field}",
            f"difference_{field}", f"abs_difference_{field}",
        ]
    write_csv(out / OUT_AGG_COMPARISON, aggregation, agg_fields)

    summary_fields = [
        "payment_year", "source_status", "contract_rows",
        "contract_identity_pass", "contract_identity_fail",
        "contract_nonnumeric_or_missing", "contract_total_status",
        "parent_total_status", "overall_identity_status",
    ]
    write_csv(out / OUT_YEAR_SUMMARY, year_summary, summary_fields)

    manifest_fields = [
        "payment_year", "zip_path", "zip_sha256", "member_name",
        "member_sha256", "duplicate_zip_count_with_identical_member",
    ]
    write_csv(out / OUT_SOURCE_MANIFEST, manifest, manifest_fields)

    required_years = len(list(YEARS))
    source_years = len(manifest)
    contract_fail = sum(r["strict_identity_status"] == "FAIL" for r in contract_rows)
    published_contract_fail = sum(r["published_rounding_identity_status"] == "FAIL" for r in contract_rows)
    contract_missing = sum(r["strict_identity_status"] == "NONNUMERIC_OR_MISSING" for r in contract_rows)
    failed_years = [str(r["payment_year"]) for r in year_summary if r["overall_identity_status"] != "PASS"]

    overall_pass = (
        source_years == required_years
        and published_contract_fail == 0
        and contract_missing == 0
        and not failed_years
        and not global_errors
    )

    report_lines = [
        "CMS MEDICARE PART D RECONCILIATION IDENTITY VALIDATOR",
        "=" * 72,
        f"Generated UTC: {generated}",
        "Scope: CY2015-CY2024",
        "",
        "BOUNDARY",
        "-" * 72,
        "Read-only validation only.",
        "No imputation, database writes, reconstruction, or ledger inclusion.",
        "RDS is outside scope.",
        "Contract-vs-Parent-Organization differences are measured, not erased.",
        "",
        "TESTED IDENTITY",
        "-" * 72,
        "Reconciliation Amount = LICS + Reinsurance + Risk Sharing",
        f"Strict identity tolerance: ${STRICT_IDENTITY_TOLERANCE_DOLLARS:.2f}",
        f"Published-field rounding tolerance: ${PUBLISHED_ROUNDING_TOLERANCE_DOLLARS:.2f}",
        "Strict exceptions are retained; certification uses the published-field rounding test.",
        "",
        "COUNTS",
        "-" * 72,
        f"Required years: {required_years}",
        f"Source years resolved: {source_years}",
        f"Contract detail rows tested: {len(contract_rows)}",
        f"Contract strict identity PASS rows: {sum(r['strict_identity_status'] == 'PASS' for r in contract_rows)}",
        f"Contract strict identity FAIL rows: {contract_fail}",
        f"Contract published-rounding FAIL rows: {published_contract_fail}",
        f"Contract nonnumeric/missing rows: {contract_missing}",
        f"Published totals rows tested: {len(published_totals)}",
        "",
        "YEAR CHECKS",
        "-" * 72,
    ]

    for r in year_summary:
        report_lines.append(
            f"{r['payment_year']}: {r['overall_identity_status']} | "
            f"contract rows={r['contract_rows']} "
            f"pass={r['contract_identity_pass']} "
            f"fail={r['contract_identity_fail']} "
            f"missing={r['contract_nonnumeric_or_missing']} | "
            f"contract total={r['contract_total_status']} | "
            f"parent total={r['parent_total_status']}"
        )

    report_lines += [
        "",
        "ERRORS",
        "-" * 72,
    ]
    if global_errors:
        report_lines.extend(global_errors)
    else:
        report_lines.append("None")

    report_lines += [
        "",
        "OVERALL",
        "-" * 72,
        f"OVERALL: {'PASS' if overall_pass else 'FAIL'}",
        "",
        "INTERPRETATION",
        "-" * 72,
        "A PASS certifies only the arithmetic identity in the published Part D",
        "reconciliation workbook across the tested source universe. It does NOT",
        "establish that Reconciliation Amount is additive to Part D Plans payment",
        "fields, does NOT establish a Washington expenditure total, and does NOT",
        "authorize ledger inclusion.",
    ]

    (out / OUT_REPORT).write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("\n".join(report_lines))
    print()
    print(f"Outputs: {out}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
