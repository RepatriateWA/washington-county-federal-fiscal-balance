#!/usr/bin/env python3
"""
validate_cms_partd_pbp_exact_status_v0_8.py

CMS Medicare Part D — Exact Contract+PBP Status Validation v0.8

Applies the prospectively frozen, independently certified CMS semantic rule:
    mrx_drug_ben_yn = 1 -> Part D benefit YES
    mrx_drug_ben_yn = 2 -> Part D benefit NO

ONLY to the remaining exact same-year Contract+PBP relationships left after the
prior Landscape/PBP positive-evidence gates.

Expected hard controls:
    relationships = 240
    member-months = 5,197,132

This validator does NOT:
  * use sibling-PBP status
  * use another year's status
  * propagate or assign payments
  * impute values
  * reconstruct Part D payments
  * write to PostgreSQL
  * authorize ledger inclusion

Run from repository root:
    python scripts/validate_cms_partd_pbp_exact_status_v0_8.py
"""

from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
PBP_ROOT = REPO_ROOT / "data" / "raw" / "cms" / "medicare_partd" / "pbp_benefits"
VALIDATION_ROOT = PBP_ROOT / "validation"
OUTPUT_DIR = VALIDATION_ROOT / "pbp_exact_status_v0_8"

YEARS = tuple(range(2015, 2025))
EXPECTED_RELATIONSHIPS = 240
EXPECTED_MEMBER_MONTHS = 5_197_132

FIELD = "mrx_drug_ben_yn"
CONTRACT_FIELD = "pbp_a_hnumber"
PBP_FIELD = "pbp_a_plan_identifier"
SEGMENT_FIELD = "segment_id"

FROZEN_MAP = {
    "1": "PARTD_YES",
    "2": "PARTD_NO",
}

# Canonical predecessor output: v0.7 classified 241 post-Landscape relationships.
# We deliberately consume its exact relationship-level output rather than
# re-creating the disputed population from broader source files.
V07_DIR = VALIDATION_ROOT / "pbp_benefits_status_validation_v0_7"

@dataclass
class Target:
    year: int
    contract: str
    pbp: str
    member_months: int
    source_row: dict

def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip())

def low(s) -> str:
    return norm(s).lower()

def norm_contract(s) -> str:
    return norm(s).upper()

def norm_pbp(s) -> str:
    v = norm(s)
    if re.fullmatch(r"\d+(?:\.0+)?", v):
        return str(int(float(v))).zfill(3)
    return v.upper()

def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1", errors="replace")

def detect_delimiter(text: str) -> str:
    first = text.splitlines()[0] if text.splitlines() else text
    candidates = {"\t": first.count("\t"), ",": first.count(","), "|": first.count("|")}
    delim, count = max(candidates.items(), key=lambda x: x[1])
    if count <= 0:
        raise RuntimeError("Unable to detect delimiter")
    return delim

def infer_year(text: str) -> Optional[int]:
    vals = {int(x) for x in re.findall(r"(?<!\d)(20(?:1[5-9]|2[0-4]))(?!\d)", text)}
    return next(iter(vals)) if len(vals) == 1 else None

def discover_year_zip(year: int) -> Path:
    candidates = []
    for p in PBP_ROOT.rglob("*.zip"):
        if "validation" in {x.lower() for x in p.parts}:
            continue
        if infer_year(p.name) == year or infer_year(str(p.parent)) == year:
            candidates.append(p.resolve())
    candidates = sorted(set(candidates))
    if not candidates:
        raise FileNotFoundError(f"CY{year}: no PBP Benefits ZIP found")
    scored = []
    for p in candidates:
        s = p.name.lower()
        score = (4 if str(year) in s else 0) + (3 if "pbp" in s else 0) + (2 if "benefit" in s else 0)
        scored.append((score, p))
    best_score = max(x[0] for x in scored)
    best = [p for score, p in scored if score == best_score]
    if len(best) != 1:
        raise RuntimeError(f"CY{year}: ambiguous PBP ZIP: " + " | ".join(map(str, best)))
    return best[0]

def find_member(zf: zipfile.ZipFile, basename: str) -> str:
    hits = [n for n in zf.namelist()
            if not n.endswith("/") and Path(n).name.lower() == basename.lower()]
    if len(hits) != 1:
        raise RuntimeError(f"Expected exactly one {basename}; found {len(hits)}")
    return hits[0]

def choose_v07_detail() -> Path:
    if not V07_DIR.exists():
        raise FileNotFoundError(f"Required predecessor directory not found: {V07_DIR}")

    canonical = V07_DIR / "cms_partd_pbp_status_detail.csv"
    if canonical.exists():
        return canonical

    csvs = list(V07_DIR.glob("*.csv"))
    candidates = []
    for p in csvs:
        try:
            with p.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                headers = [low(x) for x in (reader.fieldnames or [])]
                sample = []
                for i, row in enumerate(reader):
                    sample.append(row)
                    if i >= 3:
                        break
        except Exception:
            continue
        joined = " ".join(headers)
        score = 0
        if "contract" in joined: score += 3
        if "pbp" in joined or "plan" in joined: score += 3
        if "year" in joined: score += 2
        if "member" in joined or "enrollment" in joined: score += 2
        if "class" in joined or "status" in joined or "evidence" in joined: score += 1
        if score >= 8:
            candidates.append((score, p, headers))
    if not candidates:
        raise RuntimeError("Could not identify v0.7 relationship-level detail CSV")
    max_score = max(x[0] for x in candidates)
    best = [x for x in candidates if x[0] == max_score]
    if len(best) != 1:
        raise RuntimeError("Ambiguous v0.7 detail CSV candidates: " + " | ".join(str(x[1]) for x in best))
    return best[0][1]

def find_col(headers: list[str], predicates) -> Optional[str]:
    for h in headers:
        lh = low(h)
        if predicates(lh):
            return h
    return None

def load_targets() -> tuple[list[Target], Path, int, int]:
    p = choose_v07_detail()
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        year_col = find_col(headers, lambda h: h == "year" or "coverage_year" in h)
        contract_col = find_col(headers, lambda h: h == "contract" or h.endswith("_contract") or "contract_number" in h)
        pbp_col = find_col(headers, lambda h: h == "pbp" or "pbp" in h or "plan_identifier" in h)
        mm_col = find_col(headers, lambda h: "member_month" in h or h == "numeric_enrollment" or ("enrollment" in h and "numeric" in h))
        class_col = find_col(headers, lambda h: "classification" in h or h == "status" or "evidence_class" in h)

        missing = [name for name, col in [
            ("year", year_col), ("contract", contract_col), ("pbp", pbp_col),
            ("member-month", mm_col), ("classification", class_col)
        ] if col is None]
        if missing:
            raise RuntimeError("v0.7 detail missing columns: " + ", ".join(missing))

        raw_rows = list(reader)

    # We want the 240 rows that v0.7 left without positive PBP Part-D evidence.
    # Accept exact known label first; otherwise require an unambiguous population
    # whose count and member-month total match the certified hard controls.
    def mm_value(row):
        raw = norm(row.get(mm_col))
        if not raw:
            return 0
        return int(round(float(raw.replace(",", ""))))

    exact = [
        row for row in raw_rows
        if low(row.get(class_col)) == "pbp_present_no_positive_partd_evidence"
    ]
    if len(exact) == EXPECTED_RELATIONSHIPS and sum(mm_value(r) for r in exact) == EXPECTED_MEMBER_MONTHS:
        chosen = exact
    else:
        # Conservative fallback: identify classification group(s) only by exact
        # predecessor hard controls; never guess from wording alone.
        groups = defaultdict(list)
        for row in raw_rows:
            groups[norm(row.get(class_col))].append(row)
        matching_groups = [
            rows for label, rows in groups.items()
            if len(rows) == EXPECTED_RELATIONSHIPS
            and sum(mm_value(r) for r in rows) == EXPECTED_MEMBER_MONTHS
        ]
        if len(matching_groups) != 1:
            detail = "; ".join(
                f"{label!r}: n={len(rows)}, mm={sum(mm_value(r) for r in rows):,}"
                for label, rows in groups.items()
            )
            raise RuntimeError(
                "Could not uniquely recover certified 240 / 5,197,132 predecessor population. "
                + detail
            )
        chosen = matching_groups[0]

    targets = []
    for row in chosen:
        targets.append(Target(
            year=int(float(norm(row[year_col]))),
            contract=norm_contract(row[contract_col]),
            pbp=norm_pbp(row[pbp_col]),
            member_months=mm_value(row),
            source_row=row,
        ))

    return targets, p, len(chosen), sum(t.member_months for t in targets)

def load_exact_mrx_status(year: int, wanted: set[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    zip_path = discover_year_zip(year)
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"CY{year}: ZIP integrity failure at {bad}")
        member = find_member(zf, "pbp_mrx.txt")
        text = decode_bytes(zf.read(member))

    delim = detect_delimiter(text[:10000])
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delim)
    headers = reader.fieldnames or []
    hmap = {low(h): h for h in headers if h}

    required = {}
    for canonical in (CONTRACT_FIELD, PBP_FIELD, FIELD):
        actual = hmap.get(canonical.lower())
        if actual is None:
            raise RuntimeError(f"CY{year}: missing {canonical} in pbp_mrx.txt")
        required[canonical] = actual
    segment_actual = hmap.get(SEGMENT_FIELD.lower())

    observed = defaultdict(list)
    for row in reader:
        key = (
            norm_contract(row.get(required[CONTRACT_FIELD])),
            norm_pbp(row.get(required[PBP_FIELD])),
        )
        if key not in wanted:
            continue
        observed[key].append({
            "code": norm(row.get(required[FIELD])),
            "segment_id": norm(row.get(segment_actual)) if segment_actual else "",
        })

    out = {}
    for key in wanted:
        rows = observed.get(key, [])
        if not rows:
            out[key] = {
                "classification": "STATUS_UNRESOLVED",
                "codes": "",
                "segments": "",
                "record_count": 0,
                "reason": "Exact same-year Contract+PBP absent from pbp_mrx.txt",
            }
            continue
        codes = sorted({r["code"] for r in rows})
        segments = sorted({r["segment_id"] for r in rows if r["segment_id"]})
        if len(codes) == 1 and codes[0] in FROZEN_MAP:
            classification = FROZEN_MAP[codes[0]]
            reason = "Exact same-year pbp_mrx certified code"
        elif len(codes) > 1:
            classification = "STATUS_CONFLICT"
            reason = "Conflicting mrx_drug_ben_yn codes across exact Contract+PBP records"
        else:
            classification = "STATUS_UNRESOLVED"
            reason = "Blank or undocumented mrx_drug_ben_yn code"
        out[key] = {
            "classification": classification,
            "codes": "|".join(codes),
            "segments": "|".join(segments),
            "record_count": len(rows),
            "reason": reason,
        }
    return out

def write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("CMS MEDICARE PART D PBP EXACT STATUS VALIDATION v0.8")
    print("=" * 78)
    print()
    print("FROZEN SEMANTIC RULE:")
    print("  mrx_drug_ben_yn = 1 -> PARTD_YES")
    print("  mrx_drug_ben_yn = 2 -> PARTD_NO")
    print()
    print("BOUNDARY:")
    print("  Exact same-year Contract+PBP only.")
    print("  No sibling-PBP or other-year status propagation.")
    print("  No payment propagation, imputation, reconstruction, DB writes,")
    print("  or ledger inclusion.")
    print()

    errors = []
    try:
        targets, predecessor, input_n, input_mm = load_targets()
    except Exception as exc:
        print(f"FATAL: {exc}")
        return 1

    target_keys_by_year = defaultdict(set)
    for t in targets:
        target_keys_by_year[t.year].add((t.contract, t.pbp))

    status_by_year = {}
    for year in sorted(target_keys_by_year):
        try:
            status_by_year[year] = load_exact_mrx_status(year, target_keys_by_year[year])
        except Exception as exc:
            errors.append({"year": year, "error": str(exc)})
            status_by_year[year] = {}

    detail = []
    for t in targets:
        evidence = status_by_year.get(t.year, {}).get(
            (t.contract, t.pbp),
            {
                "classification": "STATUS_UNRESOLVED",
                "codes": "",
                "segments": "",
                "record_count": 0,
                "reason": "Year source/profile error",
            },
        )
        detail.append({
            "year": t.year,
            "contract": t.contract,
            "pbp": t.pbp,
            "member_months": t.member_months,
            "classification": evidence["classification"],
            "mrx_drug_ben_yn_codes": evidence["codes"],
            "pbp_mrx_record_count": evidence["record_count"],
            "segment_ids": evidence["segments"],
            "reason": evidence["reason"],
        })

    classes = ("PARTD_YES", "PARTD_NO", "STATUS_UNRESOLVED", "STATUS_CONFLICT")
    rel_counts = {c: sum(r["classification"] == c for r in detail) for c in classes}
    mm_counts = {
        c: sum(r["member_months"] for r in detail if r["classification"] == c)
        for c in classes
    }

    classified_n = sum(rel_counts.values())
    classified_mm = sum(mm_counts.values())

    checks = [
        ("Predecessor relationship control", input_n == EXPECTED_RELATIONSHIPS,
         f"{input_n:,} == {EXPECTED_RELATIONSHIPS:,}"),
        ("Predecessor member-month control", input_mm == EXPECTED_MEMBER_MONTHS,
         f"{input_mm:,} == {EXPECTED_MEMBER_MONTHS:,}"),
        ("Relationship classification identity", classified_n == EXPECTED_RELATIONSHIPS,
         f"{classified_n:,} == {EXPECTED_RELATIONSHIPS:,}"),
        ("Member-month classification identity", classified_mm == EXPECTED_MEMBER_MONTHS,
         f"{classified_mm:,} == {EXPECTED_MEMBER_MONTHS:,}"),
        ("No source/profile errors", len(errors) == 0, f"errors={len(errors)}"),
        ("Only frozen source codes used for affirmative/negative status",
         all(
             (r["classification"] not in {"PARTD_YES", "PARTD_NO"})
             or r["mrx_drug_ben_yn_codes"] in {"1", "2"}
             for r in detail
         ),
         "YES/NO require exact certified code 1/2"),
    ]
    overall = all(ok for _, ok, _ in checks)

    write_csv(
        OUTPUT_DIR / "cms_partd_pbp_exact_status_v0_8_detail.csv",
        detail,
        [
            "year", "contract", "pbp", "member_months", "classification",
            "mrx_drug_ben_yn_codes", "pbp_mrx_record_count", "segment_ids", "reason"
        ],
    )
    summary_rows = [
        {
            "classification": c,
            "relationships": rel_counts[c],
            "member_months": mm_counts[c],
            "member_month_share_pct": (
                100.0 * mm_counts[c] / EXPECTED_MEMBER_MONTHS
                if EXPECTED_MEMBER_MONTHS else 0.0
            ),
        }
        for c in classes
    ]
    write_csv(
        OUTPUT_DIR / "cms_partd_pbp_exact_status_v0_8_summary.csv",
        summary_rows,
        ["classification", "relationships", "member_months", "member_month_share_pct"],
    )
    write_csv(
        OUTPUT_DIR / "cms_partd_pbp_exact_status_v0_8_checks.csv",
        [
            {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail_text}
            for name, ok, detail_text in checks
        ],
        ["check", "status", "detail"],
    )
    write_csv(
        OUTPUT_DIR / "cms_partd_pbp_exact_status_v0_8_errors.csv",
        errors,
        ["year", "error"],
    )

    txt = []
    txt.append("CMS MEDICARE PART D PBP EXACT STATUS VALIDATION v0.8")
    txt.append("")
    txt.append(f"Predecessor: {predecessor}")
    txt.append("Frozen semantic rule: 1=Part D YES; 2=Part D NO")
    txt.append("Exact same-year Contract+PBP only.")
    txt.append("")
    txt.append("CONTROL")
    txt.append(f"Relationships: {input_n:,}")
    txt.append(f"Member-months: {input_mm:,}")
    txt.append("")
    txt.append("CLASSIFICATION")
    for c in classes:
        pct = 100.0 * mm_counts[c] / EXPECTED_MEMBER_MONTHS
        txt.append(
            f"{c}: {rel_counts[c]:,} relationships | "
            f"{mm_counts[c]:,} member-months | {pct:.6f}%"
        )
    txt.append("")
    txt.append("CHECKS")
    for name, ok, d in checks:
        txt.append(f"[{'PASS' if ok else 'FAIL'}] {name} — {d}")
    txt.append("")
    txt.append(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    txt.append("")
    txt.append(
        "Boundary: A PARTD_YES classification establishes benefit status only. "
        "It does not authorize borrowing or assigning a sibling-PBP payment and "
        "does not authorize ledger inclusion."
    )
    (OUTPUT_DIR / "cms_partd_pbp_exact_status_v0_8_summary.txt").write_text(
        "\n".join(txt) + "\n", encoding="utf-8"
    )

    print("CONTROL:")
    print(f"  Expected relationships: {EXPECTED_RELATIONSHIPS:,}")
    print(f"  Input relationships:    {input_n:,}")
    print(f"  Expected member-months: {EXPECTED_MEMBER_MONTHS:,}")
    print(f"  Input member-months:    {input_mm:,}")
    print()
    print("CLASSIFICATION:")
    for c in classes:
        pct = 100.0 * mm_counts[c] / EXPECTED_MEMBER_MONTHS
        print(
            f"  {c}: {rel_counts[c]:,} relationships | "
            f"{mm_counts[c]:,} member-months | {pct:.6f}%"
        )
    print()
    print("CHECKS:")
    for name, ok, _ in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print()
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1

if __name__ == "__main__":
    sys.exit(main())
