#!/usr/bin/env python3
"""
validate_cms_partd_cpsc_pbp_coexistence_v0_1.py

Memory-safe, read-only targeted validator for the 5,203,895 numeric Washington
CPSC member-months classified as SAME_CONTRACT_OTHER_PBP.

Purpose
-------
For each affected unmatched Contract+PBP+month, determine whether at least one
DIFFERENT PBP under the SAME contract and month:
  (a) is observed in Washington CPSC with numeric enrollment, and
  (b) exists in that year's CMS PartDPlans payment workbook.

This establishes same-contract/same-month coexistence evidence only.

It does NOT:
- infer that an unmatched PBP itself carries Part D;
- transfer or propagate payment values between PBPs;
- impute suppressed/nonnumeric enrollment;
- reconstruct Part D dollars;
- write to PostgreSQL;
- authorize ledger inclusion.

The monthly CPSC corpus is streamed one selected source at a time and released.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import openpyxl

EXPECTED_CONTROL = 5_203_895
YEARS = range(2015, 2025)
REQUIRED_MONTHS = [(y, m) for y in range(2015, 2025)
                   for m in range(1, 13)
                   if not (y == 2024 and m > 9)]

CPSC_REQUIRED = {
    "CONTRACT_NUMBER",
    "PLAN_ID",
    "STATE",
    "COUNTY",
    "ENROLLMENT",
}

def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()

def norm(v: Any) -> str:
    s = clean(v).upper().replace("/", " ")
    return re.sub(r"[^A-Z0-9]+", "_", s).strip("_")

def canon_pbp(v: Any) -> str:
    s = clean(v)
    if not s:
        return ""
    try:
        return f"{int(float(s)):03d}"
    except (ValueError, TypeError):
        return s.upper()

def parse_int(v: Any):
    s = clean(v).replace(",", "")
    if not s:
        return None
    try:
        x = float(s)
        if x.is_integer():
            return int(x)
    except ValueError:
        pass
    return None

def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write_csv(path: Path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def pick(row: dict[str, str], *names: str) -> str:
    m = {norm(k): v for k, v in row.items()}
    for name in names:
        if norm(name) in m:
            return clean(m[norm(name)])
    return ""

def find_partdplans(root: Path, year: int):
    hits = []
    yd = root / str(year)
    for zp in sorted(yd.glob("*.zip")):
        try:
            with zipfile.ZipFile(zp) as z:
                for member in z.namelist():
                    b = Path(member).name.lower().replace(" ", "")
                    if b.endswith(".xlsx") and "partdplans" in b and "recon" not in b:
                        data = z.read(member)
                        hits.append(
                            (zp, member, data, hashlib.sha256(data).hexdigest())
                        )
        except zipfile.BadZipFile:
            continue
    if not hits:
        raise RuntimeError(f"CY{year}: PartDPlans workbook not found")
    if len({x[3] for x in hits}) != 1:
        raise RuntimeError(f"CY{year}: conflicting PartDPlans workbook bytes")
    return sorted(hits, key=lambda x: (str(x[0]), x[1]))[0]

def load_payment_keys(root: Path, year: int):
    zp, member, data, mhash = find_partdplans(root, year)
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            for hr, vals in enumerate(
                ws.iter_rows(min_row=1, max_row=30, values_only=True), 1
            ):
                hdr = [norm(x) for x in vals]
                if "CONTRACT_NUMBER" not in hdr or "PLAN_BENEFIT_PACKAGE" not in hdr:
                    continue
                ci = hdr.index("CONTRACT_NUMBER")
                pi = hdr.index("PLAN_BENEFIT_PACKAGE")
                keys, dups = set(), []
                for row in ws.iter_rows(min_row=hr + 1, values_only=True):
                    c = clean(row[ci] if ci < len(row) else "").upper()
                    p = canon_pbp(row[pi] if pi < len(row) else "")
                    if not c or not p:
                        continue
                    k = (c, p)
                    if k in keys:
                        dups.append(k)
                    keys.add(k)
                return keys, dups, {
                    "year": year,
                    "zip_path": str(zp),
                    "zip_sha256": sha_file(zp),
                    "member_name": member,
                    "member_sha256": mhash,
                    "sheet_name": ws.title,
                    "header_row": hr,
                    "payment_key_count": len(keys),
                }
    finally:
        wb.close()
    raise RuntimeError(f"CY{year}: PartDPlans Contract/PBP table not found")

def infer_date(text: str):
    s = text.replace("\\", "/")
    patterns = [
        r"(?<!\d)(20(?:1[4-9]|2[0-4]))[-_/ ]?(0[1-9]|1[0-2])(?!\d)",
        r"(?<!\d)(0[1-9]|1[0-2])[-_/ ]?(20(?:1[4-9]|2[0-4]))(?!\d)",
    ]
    m = re.search(patterns[0], s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(patterns[1], s)
    if m:
        return int(m.group(2)), int(m.group(1))

    month_names = {
        "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,
        "apr":4,"april":4,"may":5,"jun":6,"june":6,"jul":7,"july":7,
        "aug":8,"august":8,"sep":9,"sept":9,"september":9,"oct":10,
        "october":10,"nov":11,"november":11,"dec":12,"december":12,
    }
    low = s.lower()
    ym = re.search(r"(20(?:1[4-9]|2[0-4]))", low)
    if ym:
        y = int(ym.group(1))
        for name, mo in month_names.items():
            if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", low):
                return y, mo
    return None

def decode_delimited(data: bytes):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return None

    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",|\t;")
    except csv.Error:
        dialect = csv.excel

    stream = io.StringIO(text)
    reader = csv.reader(stream, dialect)
    try:
        header = next(reader)
    except StopIteration:
        return None
    return header, reader

def inspect_member_header(data: bytes):
    parsed = decode_delimited(data)
    if not parsed:
        return None
    header, _ = parsed
    h = {norm(x) for x in header}
    return header if CPSC_REQUIRED.issubset(h) else None

def build_source_index(root: Path):
    """
    Metadata-only index. We inspect headers but do not retain member bytes or rows.
    """
    admitted = []
    candidate_count = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()

        if suffix == ".zip":
            try:
                with zipfile.ZipFile(path) as z:
                    for info in z.infolist():
                        if info.is_dir():
                            continue
                        member_suffix = Path(info.filename).suffix.lower()
                        if member_suffix not in (".csv", ".txt"):
                            continue
                        candidate_count += 1
                        try:
                            data = z.read(info.filename)
                        except Exception:
                            continue
                        header = inspect_member_header(data)
                        if not header:
                            continue
                        dt = infer_date(str(path) + "/" + info.filename)
                        admitted.append({
                            "container_path": str(path),
                            "member_name": info.filename,
                            "is_zip": True,
                            "date": dt,
                            "header": header,
                            "size": info.file_size,
                            "crc": info.CRC,
                        })
                        del data
            except zipfile.BadZipFile:
                continue

        elif suffix in (".csv", ".txt"):
            candidate_count += 1
            try:
                with path.open("rb") as f:
                    data = f.read()
            except Exception:
                continue
            header = inspect_member_header(data)
            if header:
                admitted.append({
                    "container_path": str(path),
                    "member_name": "",
                    "is_zip": False,
                    "date": infer_date(str(path)),
                    "header": header,
                    "size": path.stat().st_size,
                    "crc": "",
                })
            del data

    return candidate_count, admitted

def select_month_sources(admitted):
    by_month = defaultdict(list)
    for x in admitted:
        if x["date"] in REQUIRED_MONTHS:
            by_month[x["date"]].append(x)

    selected, errors = {}, []
    for ym in REQUIRED_MONTHS:
        hits = by_month.get(ym, [])
        if not hits:
            errors.append(f"{ym[0]}-{ym[1]:02d}: no CPSC source resolved")
            continue

        # Prefer exact duplicate-equivalent metadata where possible; otherwise
        # choose deterministically but record ambiguity as an error.
        signatures = {(h["size"], h["crc"]) for h in hits}
        if len(hits) > 1 and len(signatures) > 1:
            errors.append(
                f"{ym[0]}-{ym[1]:02d}: multiple non-equivalent CPSC sources resolved"
            )
            continue
        selected[ym] = sorted(
            hits, key=lambda h: (h["container_path"], h["member_name"])
        )[0]
    return selected, errors

def stream_selected_source(meta):
    path = Path(meta["container_path"])
    if meta["is_zip"]:
        with zipfile.ZipFile(path) as z:
            data = z.read(meta["member_name"])
    else:
        data = path.read_bytes()

    parsed = decode_delimited(data)
    if not parsed:
        del data
        raise RuntimeError("unable to decode selected CPSC source")
    header, reader = parsed
    idx = {norm(x): i for i, x in enumerate(header)}
    try:
        for row in reader:
            yield row, idx
    finally:
        del data

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--classification-dir", type=Path,
        default=Path(
            "data/raw/cms/medicare_advantage/validation/"
            "partd_cpsc_nonmatch_classification_v0_1"
        )
    )
    ap.add_argument(
        "--cpsc-root", type=Path,
        default=Path("data/raw/cms/medicare_advantage")
    )
    ap.add_argument(
        "--plan-payment-root", type=Path,
        default=Path("data/raw/cms/medicare_advantage/plan_payment")
    )
    ap.add_argument(
        "--output-dir", type=Path,
        default=Path(
            "data/raw/cms/medicare_advantage/validation/"
            "partd_cpsc_pbp_coexistence_v0_1"
        )
    )
    a = ap.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=True)

    errors, warnings = [], []

    classified_path = (
        a.classification_dir / "partd_cpsc_nonmatch_classified_rows.csv"
    )
    if not classified_path.exists():
        print(f"ERROR: missing {classified_path}", file=sys.stderr)
        return 2

    # Target month-level unmatched observations and affected contracts.
    target_rows = []
    for i, r in enumerate(read_csv(classified_path), 2):
        if pick(r, "classification_v0_1") != "SAME_CONTRACT_OTHER_PBP":
            continue
        try:
            target_rows.append({
                "year": int(pick(r, "year")),
                "month": int(pick(r, "month")),
                "contract": pick(r, "contract", "contract_number").upper(),
                "pbp": canon_pbp(pick(r, "pbp", "plan_benefit_package")),
                "numeric_enrollment": int(float(
                    pick(r, "numeric_enrollment", "enrollment")
                )),
            })
        except Exception as exc:
            errors.append(f"classification input row {i}: {exc}")

    target_by_month_key = Counter()
    affected_contracts_by_month = defaultdict(set)
    for r in target_rows:
        k = (r["year"], r["month"], r["contract"], r["pbp"])
        target_by_month_key[k] += r["numeric_enrollment"]
        affected_contracts_by_month[(r["year"], r["month"])].add(r["contract"])

    target_control = sum(target_by_month_key.values())

    # Annual payment keys.
    payment_keys = {}
    payment_manifest, duplicate_rows = [], []
    for y in YEARS:
        try:
            keys, dups, mf = load_payment_keys(a.plan_payment_root, y)
            payment_keys[y] = keys
            payment_manifest.append(mf)
            duplicate_rows.extend(
                {"year": y, "contract": c, "pbp": p} for c, p in dups
            )
        except Exception as exc:
            payment_keys[y] = set()
            errors.append(str(exc))

    # Metadata-only CPSC source index.
    candidate_count, admitted = build_source_index(a.cpsc_root)
    selected, source_errors = select_month_sources(admitted)
    errors.extend(source_errors)

    source_rows = []
    observed_numeric = Counter()       # y,m,contract,pbp -> numeric WA enrollment
    observed_suppressed = Counter()    # y,m,contract,pbp -> row count
    observed_plan_types = defaultdict(set)
    observed_org_types = defaultdict(set)

    for ym in REQUIRED_MONTHS:
        if ym not in selected:
            continue
        y, m = ym
        affected = affected_contracts_by_month.get(ym, set())
        meta = selected[ym]
        print(f"{y}-{m:02d}: starting targeted coexistence scan...")

        rows_seen = 0
        numeric_kept = 0
        try:
            for row, idx in stream_selected_source(meta):
                rows_seen += 1

                def g(field):
                    i = idx.get(field)
                    return "" if i is None or i >= len(row) else clean(row[i])

                state = g("STATE").upper()
                if state not in ("WA", "WASHINGTON"):
                    continue
                contract = g("CONTRACT_NUMBER").upper()
                if contract not in affected:
                    continue
                p = canon_pbp(g("PLAN_ID"))
                if not p:
                    continue

                e = parse_int(g("ENROLLMENT"))
                key = (y, m, contract, p)
                if e is None:
                    observed_suppressed[key] += 1
                else:
                    observed_numeric[key] += e
                    numeric_kept += e

                # These fields are optional in CPSC; retain if present.
                for candidate in ("PLAN_TYPE",):
                    if candidate in idx:
                        v = g(candidate)
                        if v:
                            observed_plan_types[key].add(v)
                for candidate in ("ORGANIZATION_TYPE",):
                    if candidate in idx:
                        v = g(candidate)
                        if v:
                            observed_org_types[key].add(v)

            source_rows.append({
                "year": y, "month": m,
                "container_path": meta["container_path"],
                "member_name": meta["member_name"],
                "source_size": meta["size"],
                "source_crc": meta["crc"],
                "rows_streamed": rows_seen,
                "affected_contract_count": len(affected),
                "targeted_numeric_enrollment_observed": numeric_kept,
            })
            print(
                f"{y}-{m:02d}: complete | affected contracts={len(affected):,} "
                f"| targeted WA numeric={numeric_kept:,}"
            )
        except Exception as exc:
            errors.append(f"{y}-{m:02d}: {exc}")

    # Evaluate each target unmatched Contract+PBP+month.
    detail = []
    categories = Counter()
    target_observed_diff_total = 0

    for (y, m, c, p), expected_n in sorted(target_by_month_key.items()):
        observed_target_n = observed_numeric.get((y, m, c, p), 0)
        target_observed_diff_total += observed_target_n - expected_n

        other_numeric_pbps = sorted(
            pp for (yy, mm, cc, pp), n in observed_numeric.items()
            if yy == y and mm == m and cc == c and pp != p and n > 0
        )
        matched_other_pbps = sorted(
            pp for pp in other_numeric_pbps if (c, pp) in payment_keys.get(y, set())
        )
        unmatched_other_pbps = sorted(
            pp for pp in other_numeric_pbps if (c, pp) not in payment_keys.get(y, set())
        )

        if matched_other_pbps:
            category = "COEXISTS_WITH_MATCHED_PARTD_PBP"
        elif other_numeric_pbps:
            category = "COEXISTS_ONLY_WITH_OTHER_UNMATCHED_PBP"
        else:
            category = "ONLY_NUMERIC_WA_PBP_OBSERVED_FOR_CONTRACT_MONTH"

        categories[category] += expected_n

        detail.append({
            "year": y, "month": m, "contract": c,
            "unmatched_pbp": p,
            "control_numeric_enrollment": expected_n,
            "rescanned_numeric_enrollment": observed_target_n,
            "control_minus_rescan": expected_n - observed_target_n,
            "coexistence_category": category,
            "other_numeric_pbp_count": len(other_numeric_pbps),
            "other_numeric_pbps": ",".join(other_numeric_pbps),
            "matched_partd_other_pbp_count": len(matched_other_pbps),
            "matched_partd_other_pbps": ",".join(matched_other_pbps),
            "other_unmatched_pbp_count": len(unmatched_other_pbps),
            "other_unmatched_pbps": ",".join(unmatched_other_pbps),
            "target_suppressed_nonnumeric_row_count":
                observed_suppressed.get((y, m, c, p), 0),
        })

    category_rows = [{
        "category": cat,
        "numeric_enrollment": n,
        "share_of_control": n / target_control if target_control else 0.0,
    } for cat, n in sorted(categories.items(), key=lambda x: -x[1])]

    category_total = sum(categories.values())
    rescan_control_total = sum(
        observed_numeric.get((y, m, c, p), 0)
        for y, m, c, p in target_by_month_key
    )

    write_csv(
        a.output_dir / "partd_cpsc_pbp_coexistence_detail.csv", detail,
        [
            "year","month","contract","unmatched_pbp",
            "control_numeric_enrollment","rescanned_numeric_enrollment",
            "control_minus_rescan","coexistence_category",
            "other_numeric_pbp_count","other_numeric_pbps",
            "matched_partd_other_pbp_count","matched_partd_other_pbps",
            "other_unmatched_pbp_count","other_unmatched_pbps",
            "target_suppressed_nonnumeric_row_count",
        ]
    )
    write_csv(
        a.output_dir / "partd_cpsc_pbp_coexistence_summary.csv",
        category_rows,
        ["category","numeric_enrollment","share_of_control"]
    )
    write_csv(
        a.output_dir / "partd_cpsc_pbp_coexistence_source_manifest.csv",
        source_rows,
        [
            "year","month","container_path","member_name","source_size","source_crc",
            "rows_streamed","affected_contract_count",
            "targeted_numeric_enrollment_observed",
        ]
    )
    write_csv(
        a.output_dir / "partd_payment_source_manifest.csv",
        payment_manifest,
        [
            "year","zip_path","zip_sha256","member_name","member_sha256",
            "sheet_name","header_row","payment_key_count",
        ]
    )
    write_csv(
        a.output_dir / "partd_payment_duplicate_keys.csv",
        duplicate_rows, ["year","contract","pbp"]
    )

    checks = [
        ("target control equals 5,203,895", target_control == EXPECTED_CONTROL),
        ("all 117 months resolved", len(selected) == len(REQUIRED_MONTHS)),
        ("all 117 months streamed", len(source_rows) == len(REQUIRED_MONTHS)),
        ("target CPSC rescan reproduces control",
         rescan_control_total == target_control),
        ("coexistence category accounting identity",
         category_total == target_control),
        ("every detail control equals rescan",
         all(r["control_minus_rescan"] == 0 for r in detail)),
        ("no duplicate annual Part D payment keys", not duplicate_rows),
        ("no source/profile errors", not errors),
    ]
    overall = all(ok for _, ok in checks)

    lines = [
        "CMS MEDICARE PART D CPSC PBP COEXISTENCE VALIDATOR v0.1",
        "=" * 76,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "Scope: SAME_CONTRACT_OTHER_PBP numeric enrollment",
        "",
        "BOUNDARY", "-" * 76,
        "Memory-safe targeted read-only CPSC rescan.",
        "Same-contract/same-month coexistence evidence only.",
        "No payment propagation, imputation, reconstruction, DB writes, or ledger inclusion.",
        "",
        "SOURCE INDEX", "-" * 76,
        f"Candidate files scanned: {candidate_count:,}",
        f"CPSC-like members admitted by header: {len(admitted):,}",
        f"Required months: {len(REQUIRED_MONTHS):,}",
        f"Resolved months: {len(selected):,}",
        "",
        "CONTROL", "-" * 76,
        f"Expected target member-months: {EXPECTED_CONTROL:,}",
        f"Input target member-months: {target_control:,}",
        f"Rescanned target member-months: {rescan_control_total:,}",
        f"Rescan difference: {target_control - rescan_control_total:,}",
        "",
        "COEXISTENCE CATEGORIES", "-" * 76,
    ]
    for r in category_rows:
        lines.append(
            f"{r['category']}: {r['numeric_enrollment']:,} "
            f"({r['share_of_control']:.4%})"
        )
    lines += ["", "CHECKS", "-" * 76]
    lines += [f"{label}: {'PASS' if ok else 'FAIL'}" for label, ok in checks]
    lines += ["", "WARNINGS", "-" * 76] + (warnings or ["None"])
    lines += ["", "ERRORS", "-" * 76] + (errors or ["None"])
    lines += [
        "", "OVERALL", "-" * 76,
        f"OVERALL: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION BOUNDARY", "-" * 76,
        "COEXISTS_WITH_MATCHED_PARTD_PBP means a different PBP under the same",
        "contract/month had numeric Washington CPSC enrollment and existed in",
        "that year's PartDPlans payment file.",
        "It does NOT establish that the unmatched PBP itself carried Part D.",
        "No payment value may be transferred between PBPs from this result alone.",
    ]
    report = "\n".join(lines) + "\n"
    (a.output_dir / "partd_cpsc_pbp_coexistence_report.txt").write_text(
        report, encoding="utf-8"
    )
    print(report)
    print(f"Outputs: {a.output_dir}")
    return 0 if overall else 1

if __name__ == "__main__":
    sys.exit(main())
