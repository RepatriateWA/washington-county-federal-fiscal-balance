#!/usr/bin/env python3
"""
investigate_cms_partd_affirmative_payment_absence_v0_3.py

CMS Medicare Part D — Affirmative Payment-Absence Investigation v0.3

PURPOSE
-------
Consume the certified v0.8 exact-status output and investigate ONLY the
PARTD_YES exceptions that lack the ordinary same-year PartDPlans payment match.

Expected hard controls from v0.8:
    PARTD_YES relationships = 3
    PARTD_YES member-months = 1,472

For each exact same-year Contract+PBP relationship, report:
  * coverage year, Contract, PBP, member-months
  * v0.8 certified mrx_drug_ben_yn evidence
  * exact same-year presence/absence in PartDPlans.xlsx
  * same-year Contract presence and sibling payment PBPs
  * exact Contract+PBP presence in adjacent PartDPlans years
  * exact same-year Landscape evidence, when source-native identifiers can
    be resolved conservatively
  * exact same-year CPSC months, numeric enrollment, plan/organization
    vocabulary, and suppressed/non-numeric row count

V0.3 CONTROLLED CORRECTIONS
---------------------------
Relative to v0.2:
  1. PartDPlans worksheet parsing no longer assumes worksheet row 1 is the
     column header. It scans the first 25 rows and admits a header only when
     BOTH canonical identifiers are present:
         Contract Number
         Plan Benefit Package
     This handles CMS title/blank pre-header rows such as CY2024 row 3.
  2. All v0.2 source-discovery and target-year/supplementary-year boundaries
     are preserved unchanged.

No target population, frozen semantic rule, payment rule, accounting identity,
or no-imputation boundary is changed.

BOUNDARY
--------
Diagnostic evidence only. This script does NOT:
  * borrow a sibling-PBP payment
  * borrow another year's payment or status
  * impute enrollment or payment
  * reconstruct Part D dollars
  * write to PostgreSQL
  * authorize ledger inclusion

Run from repository root:
    python scripts/investigate_cms_partd_affirmative_payment_absence_v0_3.py
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
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

PBP_ROOT = REPO_ROOT / "data" / "raw" / "cms" / "medicare_partd" / "pbp_benefits"
V08_DIR = PBP_ROOT / "validation" / "pbp_exact_status_v0_8"
V08_DETAIL = V08_DIR / "cms_partd_pbp_exact_status_v0_8_detail.csv"

PLAN_PAYMENT_ROOT = REPO_ROOT / "data" / "raw" / "cms" / "medicare_advantage" / "plan_payment"
LANDSCAPE_ROOT = REPO_ROOT / "data" / "raw" / "cms" / "medicare_partd" / "landscape"
CPSC_ROOT = REPO_ROOT / "data" / "raw" / "cms" / "medicare_advantage"

OUTPUT_DIR = (
    PBP_ROOT / "validation" / "partd_affirmative_payment_absence_v0_3"
)

EXPECTED_RELATIONSHIPS = 3
EXPECTED_MEMBER_MONTHS = 1_472

CONTRACT_ALIASES = {
    "contract", "contract number", "contract_number", "contract id",
    "contract_id", "contractid", "hnumber", "pbp_a_hnumber"
}
PBP_ALIASES = {
    "plan benefit package", "plan benefit package id", "plan benefit package number",
    "plan id", "plan_id", "plan identifier", "plan_identifier", "pbp",
    "pbp id", "pbp_id", "pbp_a_plan_identifier"
}
PARTD_CODE_FIELD = "mrx_drug_ben_yn"

@dataclass(frozen=True)
class Target:
    year: int
    contract: str
    pbp: str
    member_months: int
    certified_codes: str

def norm(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip())

def low(v) -> str:
    return norm(v).lower()

def norm_contract(v) -> str:
    return norm(v).upper()

def norm_pbp(v) -> str:
    s = norm(v)
    if re.fullmatch(r"\d+(?:\.0+)?", s):
        return str(int(float(s))).zfill(3)
    return s.upper()

def safe_int(v) -> Optional[int]:
    s = norm(v).replace(",", "")
    if not s:
        return None
    try:
        return int(round(float(s)))
    except Exception:
        return None

def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1", errors="replace")

def detect_delimiter(text: str) -> str:
    lines = text.splitlines()
    first = lines[0] if lines else text
    counts = {"\t": first.count("\t"), ",": first.count(","), "|": first.count("|")}
    delim, count = max(counts.items(), key=lambda x: x[1])
    if count <= 0:
        raise RuntimeError("Unable to detect delimiter")
    return delim

def infer_year(text: str) -> Optional[int]:
    vals = {int(x) for x in re.findall(r"(?<!\d)(20(?:1[4-9]|2[0-5]))(?!\d)", text)}
    return next(iter(vals)) if len(vals) == 1 else None

def find_col(headers: list[str], aliases: set[str]) -> Optional[str]:
    by_low = {low(h): h for h in headers if h is not None}
    for alias in aliases:
        if alias in by_low:
            return by_low[alias]
    return None

def find_col_contains(headers: list[str], required: tuple[str, ...],
                      forbidden: tuple[str, ...] = ()) -> Optional[str]:
    for h in headers:
        lh = low(h)
        if all(x in lh for x in required) and not any(x in lh for x in forbidden):
            return h
    return None

def load_targets() -> list[Target]:
    if not V08_DETAIL.exists():
        raise FileNotFoundError(f"Certified v0.8 detail not found: {V08_DETAIL}")
    with V08_DETAIL.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    selected = [r for r in rows if norm(r.get("classification")) == "PARTD_YES"]
    targets = [
        Target(
            year=int(norm(r["year"])),
            contract=norm_contract(r["contract"]),
            pbp=norm_pbp(r["pbp"]),
            member_months=int(norm(r["member_months"]).replace(",", "")),
            certified_codes=norm(r.get("mrx_drug_ben_yn_codes")),
        )
        for r in selected
    ]
    if len(targets) != EXPECTED_RELATIONSHIPS:
        raise RuntimeError(
            f"v0.8 PARTD_YES relationship control failed: {len(targets)} "
            f"!= {EXPECTED_RELATIONSHIPS}"
        )
    mm = sum(t.member_months for t in targets)
    if mm != EXPECTED_MEMBER_MONTHS:
        raise RuntimeError(
            f"v0.8 PARTD_YES member-month control failed: {mm} "
            f"!= {EXPECTED_MEMBER_MONTHS}"
        )
    if any(t.certified_codes != "1" for t in targets):
        raise RuntimeError("A v0.8 PARTD_YES target does not carry certified source code 1")
    return targets

# ---------------------------- Plan Payment ----------------------------

def discover_plan_payment_zip(year: int) -> Path:
    candidates = []
    for p in PLAN_PAYMENT_ROOT.rglob("*.zip"):
        if "validation" in {x.lower() for x in p.parts}:
            continue
        y = infer_year(p.name) or infer_year(str(p.parent))
        if y == year:
            candidates.append(p.resolve())
    candidates = sorted(set(candidates))
    if not candidates:
        raise FileNotFoundError(f"CY{year}: no Plan Payment ZIP found")

    # 2024 can contain duplicate official filenames. Prefer identical hashes only
    # if multiple candidates exist; otherwise require uniqueness.
    if len(candidates) > 1:
        import hashlib
        hashes = {}
        for p in candidates:
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            hashes.setdefault(h.hexdigest(), []).append(p)
        if len(hashes) == 1:
            return sorted(candidates, key=lambda p: (len(str(p)), str(p)))[0]

        scored = []
        for p in candidates:
            s = p.name.lower()
            score = (4 if str(year) in s else 0) + (3 if "payment" in s else 0)
            scored.append((score, p))
        best_score = max(x[0] for x in scored)
        best = [p for score, p in scored if score == best_score]
        if len(best) != 1:
            raise RuntimeError(
                f"CY{year}: ambiguous Plan Payment ZIPs: "
                + " | ".join(map(str, candidates))
            )
        return best[0]
    return candidates[0]

def find_zip_member(zf: zipfile.ZipFile, predicate, label: str) -> str:
    hits = [n for n in zf.namelist() if not n.endswith("/") and predicate(Path(n).name.lower())]
    if len(hits) != 1:
        raise RuntimeError(f"Expected exactly one {label}; found {len(hits)}: {hits}")
    return hits[0]

def load_partdplans(year: int) -> tuple[dict[tuple[str, str], dict], dict[str, set[str]], str]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError(f"openpyxl unavailable: {exc}")

    zpath = discover_plan_payment_zip(year)
    with zipfile.ZipFile(zpath) as zf:
        member = find_zip_member(
            zf,
            lambda b: (
                b.lower()
                .replace(" ", "")
                .replace("_", "")
                .replace("-", "")
                .endswith("partdplans.xlsx")
            ),
            "PartDPlans.xlsx",
        )
        data = zf.read(member)

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    records = {}
    contract_pbps = defaultdict(set)
    found_sheet = False

    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)

        # CMS workbooks can contain title and blank rows before the real header.
        # Scan narrowly for a row that contains BOTH canonical identifiers.
        header = None
        contract_col = None
        pbp_col = None
        for row_number, candidate in enumerate(rows, start=1):
            if row_number > 25:
                break
            candidate_headers = [norm(x) for x in candidate]
            candidate_contract = find_col(candidate_headers, CONTRACT_ALIASES)
            candidate_pbp = find_col(candidate_headers, PBP_ALIASES)
            if candidate_contract and candidate_pbp:
                header = candidate
                contract_col = candidate_contract
                pbp_col = candidate_pbp
                break

        if header is None or not contract_col or not pbp_col:
            continue

        headers = [norm(x) for x in header]
        found_sheet = True
        idx = {h: i for i, h in enumerate(headers)}
        ci, pi = idx[contract_col], idx[pbp_col]

        for row in rows:
            c = norm_contract(row[ci] if ci < len(row) else "")
            p = norm_pbp(row[pi] if pi < len(row) else "")
            if not c or not p:
                continue
            key = (c, p)
            if key in records:
                raise RuntimeError(f"CY{year}: duplicate PartDPlans exact key {key}")
            rec = {headers[i]: row[i] if i < len(row) else None for i in range(len(headers))}
            records[key] = rec
            contract_pbps[c].add(p)
    wb.close()

    if not found_sheet:
        raise RuntimeError(f"CY{year}: no Contract+PBP PartDPlans sheet resolved")
    return records, contract_pbps, f"{zpath}::{member}"

# ---------------------------- PBP MRx ----------------------------

def discover_pbp_zip(year: int) -> Path:
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
        raise RuntimeError(f"CY{year}: ambiguous PBP Benefits ZIPs: " + " | ".join(map(str, best)))
    return best[0]

def exact_pbp_mrx_evidence(year: int, contract: str, pbp: str) -> dict:
    zpath = discover_pbp_zip(year)
    with zipfile.ZipFile(zpath) as zf:
        member = find_zip_member(zf, lambda b: b == "pbp_mrx.txt", "pbp_mrx.txt")
        text = decode_bytes(zf.read(member))
    delim = detect_delimiter(text[:10000])
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delim)
    headers = reader.fieldnames or []
    hmap = {low(h): h for h in headers if h}
    for req in ("pbp_a_hnumber", "pbp_a_plan_identifier", PARTD_CODE_FIELD):
        if req not in hmap:
            raise RuntimeError(f"CY{year}: pbp_mrx missing {req}")
    seg = hmap.get("segment_id")
    rows = []
    for row in reader:
        if (norm_contract(row[hmap["pbp_a_hnumber"]]) == contract
                and norm_pbp(row[hmap["pbp_a_plan_identifier"]]) == pbp):
            rows.append({
                "code": norm(row[hmap[PARTD_CODE_FIELD]]),
                "segment": norm(row.get(seg)) if seg else "",
            })
    return {
        "record_count": len(rows),
        "codes": "|".join(sorted({r["code"] for r in rows})),
        "segments": "|".join(sorted({r["segment"] for r in rows if r["segment"]})),
        "source": f"{zpath}::{member}",
    }

# ---------------------------- Landscape ----------------------------

def landscape_exact_evidence(year: int, contract: str, pbp: str) -> dict:
    """
    Conservative recursive scan of the preserved Landscape master ZIP.
    We report exact same-year source rows only when a tabular descendant exposes
    recognizable Contract and PBP columns. We do not infer status from filenames
    alone and do not decode undocumented drug-benefit codes here.
    """
    masters = [p for p in LANDSCAPE_ROOT.glob("*.zip") if p.is_file()]
    if not masters:
        return {"rows": 0, "tables": "", "drug_values": "", "note": "Landscape master ZIP not found"}

    # Prefer the known large master archive.
    master = max(masters, key=lambda p: p.stat().st_size)
    evidence_rows = []
    errors = []

    def recurse_zip(data: bytes, path_prefix: str, inherited_year: Optional[int], depth: int = 0):
        if depth > 4:
            return
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except Exception:
            return
        with zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                raw = zf.read(name)
                leaf = Path(name).name
                full = f"{path_prefix}::{name}"
                this_year = inherited_year
                # Only assign year when not already inherited from an annual package.
                if this_year is None:
                    this_year = infer_year(leaf) or infer_year(name)

                if leaf.lower().endswith(".zip"):
                    recurse_zip(raw, full, this_year, depth + 1)
                    continue
                if this_year != year:
                    continue
                if not leaf.lower().endswith((".csv", ".txt")):
                    continue
                try:
                    text = decode_bytes(raw)
                    delim = detect_delimiter(text[:10000])
                    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delim)
                    headers = reader.fieldnames or []
                    cc = find_col(headers, CONTRACT_ALIASES)
                    pc = find_col(headers, PBP_ALIASES)
                    if not cc or not pc:
                        continue
                    drug_cols = [
                        h for h in headers
                        if any(x in low(h) for x in ("drug benefit", "part d", "partd", "drug_benefit"))
                    ]
                    for row in reader:
                        if norm_contract(row.get(cc)) == contract and norm_pbp(row.get(pc)) == pbp:
                            vals = []
                            for h in drug_cols:
                                v = norm(row.get(h))
                                if v:
                                    vals.append(f"{h}={v}")
                            evidence_rows.append((full, " | ".join(vals)))
                except Exception as exc:
                    errors.append(f"{full}: {exc}")

    with zipfile.ZipFile(master) as outer:
        for name in outer.namelist():
            if name.endswith("/"):
                continue
            leaf = Path(name).name
            annual_year = infer_year(leaf)
            if annual_year != year:
                continue
            raw = outer.read(name)
            if leaf.lower().endswith(".zip"):
                recurse_zip(raw, f"{master}::{name}", year, 1)
            elif leaf.lower().endswith((".csv", ".txt")):
                # Unusual direct annual table.
                recurse_zip(raw, f"{master}::{name}", year, 1)

    return {
        "rows": len(evidence_rows),
        "tables": " || ".join(sorted({x[0] for x in evidence_rows})),
        "drug_values": " || ".join(sorted({x[1] for x in evidence_rows if x[1]})),
        "note": "" if not errors else f"profile_errors={len(errors)}",
    }

# ---------------------------- CPSC ----------------------------

def cpsc_candidate_members() -> list[tuple[Path, str, int, int]]:
    """
    Build a conservative inventory of monthly CPSC-like tabular members.
    Returns (zip_path, member_name, year, month).
    """
    out = []
    month_pat = re.compile(r"(?<!\d)(20(?:1[5-9]|2[0-4]))[-_]?([01]?\d)(?!\d)")
    for zpath in CPSC_ROOT.rglob("*.zip"):
        if "validation" in {x.lower() for x in zpath.parts}:
            continue
        try:
            with zipfile.ZipFile(zpath) as zf:
                for name in zf.namelist():
                    if name.endswith("/") or not name.lower().endswith((".csv", ".txt")):
                        continue
                    base = Path(name).name.lower()
                    if not any(x in base for x in ("cpsc", "contract", "enrollment")):
                        continue
                    combined = f"{zpath.name} {name}"
                    matches = month_pat.findall(combined)
                    if not matches:
                        continue
                    y, m = map(int, matches[-1])
                    if y in YEARS_FOR_CPSC and 1 <= m <= 12:
                        out.append((zpath, name, y, m))
        except zipfile.BadZipFile:
            continue
    return out

YEARS_FOR_CPSC = set(range(2015, 2025))

def cpsc_exact_evidence(targets: list[Target]) -> dict[tuple[int, str, str], dict]:
    """
    Prefer existing certified monthly linkage detail if it exposes exact keys.
    If not, perform a targeted archive scan. Failure to locate CPSC detail is
    diagnostic only and does not invalidate payment-absence evidence.
    """
    result = {
        (t.year, t.contract, t.pbp): {
            "months": set(), "numeric_enrollment": 0, "suppressed_rows": 0,
            "plan_types": set(), "org_types": set(), "note": ""
        }
        for t in targets
    }

    # Search existing validation CSVs first.
    candidate_csvs = []
    for p in CPSC_ROOT.rglob("*.csv"):
        if "validation" not in {x.lower() for x in p.parts}:
            continue
        name = p.name.lower()
        if any(x in name for x in ("cpsc", "linkage", "coexistence")):
            candidate_csvs.append(p)

    used_existing = False
    for p in candidate_csvs:
        try:
            with p.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
                yc = find_col_contains(headers, ("year",))
                cc = find_col(headers, CONTRACT_ALIASES)
                pc = find_col(headers, PBP_ALIASES)
                mc = find_col_contains(headers, ("month",), ("member",))
                ec = (
                    find_col_contains(headers, ("numeric", "enrollment"))
                    or find_col_contains(headers, ("enrollment",), ("suppressed",))
                )
                if not yc or not cc or not pc:
                    continue
                rows = list(reader)
            target_keys = set(result)
            hit = False
            for row in rows:
                try:
                    key = (
                        int(float(norm(row.get(yc)))),
                        norm_contract(row.get(cc)),
                        norm_pbp(row.get(pc)),
                    )
                except Exception:
                    continue
                if key not in target_keys:
                    continue
                hit = True
                r = result[key]
                if mc:
                    m = safe_int(row.get(mc))
                    if m and 1 <= m <= 12:
                        r["months"].add(m)
                if ec:
                    e = safe_int(row.get(ec))
                    if e is not None:
                        r["numeric_enrollment"] += e
                pt = find_col_contains(headers, ("plan", "type"))
                ot = find_col_contains(headers, ("organization", "type"))
                if pt and norm(row.get(pt)): r["plan_types"].add(norm(row.get(pt)))
                if ot and norm(row.get(ot)): r["org_types"].add(norm(row.get(ot)))
            if hit:
                used_existing = True
        except Exception:
            continue

    if used_existing and all(result[k]["numeric_enrollment"] > 0 for k in result):
        for r in result.values():
            r["note"] = "Existing validation detail"
        return result

    # We intentionally do NOT force a broad CPSC rescan here if the repository's
    # packaging cannot be identified conservatively. Record diagnostic absence.
    for r in result.values():
        if r["numeric_enrollment"] == 0:
            r["note"] = "Exact-key CPSC detail not resolved from existing validation outputs"
    return result

# ---------------------------- Output ----------------------------

def write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("CMS MEDICARE PART D AFFIRMATIVE PAYMENT-ABSENCE INVESTIGATION v0.3")
    print("=" * 78)
    print()
    print("BOUNDARY:")
    print("  Diagnostic evidence only.")
    print("  No sibling/other-year payment propagation, imputation, reconstruction,")
    print("  DB writes, or ledger inclusion.")
    print()

    try:
        targets = load_targets()
    except Exception as exc:
        print(f"FATAL: {exc}")
        return 1

    errors = []
    plan_cache = {}
    target_years = sorted({t.year for t in targets})
    adjacent_years = sorted(
        ({t.year - 1 for t in targets} | {t.year + 1 for t in targets})
        - set(target_years)
    )

    # Primary evidence: every target year MUST resolve.
    for year in target_years:
        try:
            plan_cache[year] = load_partdplans(year)
        except Exception as exc:
            errors.append({
                "scope": f"REQUIRED PartDPlans CY{year}",
                "error": str(exc),
            })

    # Supplementary evidence only: adjacent years are attempted when available,
    # but absence does not invalidate the same-year investigation.
    for year in adjacent_years:
        if year < 2014 or year > 2025:
            continue
        try:
            plan_cache[year] = load_partdplans(year)
        except Exception as exc:
            errors.append({
                "scope": f"SUPPLEMENTARY PartDPlans CY{year}",
                "error": str(exc),
            })

    cpsc = cpsc_exact_evidence(targets)
    detail = []

    for t in targets:
        try:
            mrx = exact_pbp_mrx_evidence(t.year, t.contract, t.pbp)
        except Exception as exc:
            mrx = {"record_count": 0, "codes": "", "segments": "", "source": ""}
            errors.append({"scope": f"PBP MRx CY{t.year} {t.contract}-{t.pbp}", "error": str(exc)})

        current_records, current_contract_pbps, current_source = plan_cache.get(
            t.year, ({}, defaultdict(set), "")
        )
        exact_present = (t.contract, t.pbp) in current_records
        contract_present = t.contract in current_contract_pbps
        sibling_pbps = sorted(p for p in current_contract_pbps.get(t.contract, set()) if p != t.pbp)

        adjacent = []
        for y in (t.year - 1, t.year + 1):
            recs = plan_cache.get(y, ({}, {}, ""))[0]
            if (t.contract, t.pbp) in recs:
                adjacent.append(str(y))

        try:
            landscape = landscape_exact_evidence(t.year, t.contract, t.pbp)
        except Exception as exc:
            landscape = {"rows": 0, "tables": "", "drug_values": "", "note": "profile error"}
            errors.append({"scope": f"Landscape CY{t.year} {t.contract}-{t.pbp}", "error": str(exc)})

        ce = cpsc[(t.year, t.contract, t.pbp)]

        if exact_present:
            diagnostic = "EXACT_SAME_YEAR_PARTDPLANS_PRESENT_REVIEW_LINKAGE"
        elif contract_present:
            diagnostic = "AFFIRMATIVE_PBP_ABSENT_SAME_YEAR_PAYMENT_CONTRACT_PRESENT"
        else:
            diagnostic = "AFFIRMATIVE_PBP_AND_CONTRACT_ABSENT_SAME_YEAR_PAYMENT"

        detail.append({
            "year": t.year,
            "contract": t.contract,
            "pbp": t.pbp,
            "member_months_v0_8": t.member_months,
            "certified_mrx_code_v0_8": t.certified_codes,
            "pbp_mrx_record_count": mrx["record_count"],
            "pbp_mrx_codes": mrx["codes"],
            "pbp_mrx_segments": mrx["segments"],
            "same_year_partdplans_exact_present": exact_present,
            "same_year_partdplans_contract_present": contract_present,
            "same_year_partdplans_sibling_pbp_count": len(sibling_pbps),
            "same_year_partdplans_sibling_pbps": "|".join(sibling_pbps),
            "adjacent_year_exact_partdplans_years": "|".join(adjacent),
            "landscape_exact_rows": landscape["rows"],
            "landscape_drug_values": landscape["drug_values"],
            "landscape_note": landscape["note"],
            "cpsc_months_resolved": "|".join(f"{m:02d}" for m in sorted(ce["months"])),
            "cpsc_numeric_enrollment_resolved": ce["numeric_enrollment"],
            "cpsc_plan_type_vocabulary": "|".join(sorted(ce["plan_types"])),
            "cpsc_organization_type_vocabulary": "|".join(sorted(ce["org_types"])),
            "cpsc_note": ce["note"],
            "diagnostic_class": diagnostic,
            "partdplans_source": current_source,
            "pbp_mrx_source": mrx["source"],
        })

    # Hard checks. CPSC/Landscape are supplementary diagnostics and do not cause
    # failure if exact source-native rows cannot be conservatively resolved.
    checks = [
        ("v0.8 affirmative relationship control",
         len(targets) == EXPECTED_RELATIONSHIPS,
         f"{len(targets)} == {EXPECTED_RELATIONSHIPS}"),
        ("v0.8 affirmative member-month control",
         sum(t.member_months for t in targets) == EXPECTED_MEMBER_MONTHS,
         f"{sum(t.member_months for t in targets):,} == {EXPECTED_MEMBER_MONTHS:,}"),
        ("All targets retain exact same-year certified MRx code 1",
         all(r["pbp_mrx_codes"] == "1" and r["pbp_mrx_record_count"] >= 1 for r in detail),
         f"{sum(r['pbp_mrx_codes'] == '1' and r['pbp_mrx_record_count'] >= 1 for r in detail)}/{len(detail)}"),
        ("All required target-year PartDPlans sources resolved",
         all(y in plan_cache for y in target_years),
         f"{sum(y in plan_cache for y in target_years)}/{len(target_years)}"),
        ("No duplicate/ambiguous exact same-year payment keys encountered",
         not any(
             e["scope"].startswith("REQUIRED ")
             and "duplicate PartDPlans exact key" in e["error"]
             for e in errors
         ),
         "checked during required same-year PartDPlans load"),
    ]
    overall = all(ok for _, ok, _ in checks)

    write_csv(
        OUTPUT_DIR / "cms_partd_affirmative_payment_absence_v0_3_detail.csv",
        detail,
        [
            "year", "contract", "pbp", "member_months_v0_8",
            "certified_mrx_code_v0_8", "pbp_mrx_record_count", "pbp_mrx_codes",
            "pbp_mrx_segments", "same_year_partdplans_exact_present",
            "same_year_partdplans_contract_present",
            "same_year_partdplans_sibling_pbp_count",
            "same_year_partdplans_sibling_pbps",
            "adjacent_year_exact_partdplans_years",
            "landscape_exact_rows", "landscape_drug_values", "landscape_note",
            "cpsc_months_resolved", "cpsc_numeric_enrollment_resolved",
            "cpsc_plan_type_vocabulary", "cpsc_organization_type_vocabulary",
            "cpsc_note", "diagnostic_class", "partdplans_source", "pbp_mrx_source",
        ],
    )
    write_csv(
        OUTPUT_DIR / "cms_partd_affirmative_payment_absence_v0_3_checks.csv",
        [{"check": n, "status": "PASS" if ok else "FAIL", "detail": d}
         for n, ok, d in checks],
        ["check", "status", "detail"],
    )
    write_csv(
        OUTPUT_DIR / "cms_partd_affirmative_payment_absence_v0_3_errors.csv",
        errors,
        ["scope", "error"],
    )

    print("CONTROL:")
    print(f"  Relationships: {len(targets):,} / {EXPECTED_RELATIONSHIPS:,}")
    print(f"  Member-months: {sum(t.member_months for t in targets):,} / {EXPECTED_MEMBER_MONTHS:,}")
    print()
    print("EXCEPTIONS:")
    for r in detail:
        print(
            f"  CY{r['year']} {r['contract']}-{r['pbp']} | "
            f"{r['member_months_v0_8']:,} mm | "
            f"MRx={r['pbp_mrx_codes'] or '<none>'} | "
            f"same-year payment exact={r['same_year_partdplans_exact_present']} | "
            f"contract present={r['same_year_partdplans_contract_present']} | "
            f"adjacent exact={r['adjacent_year_exact_partdplans_years'] or '<none>'}"
        )
    print()
    print("CHECKS:")
    for n, ok, _ in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    if errors:
        print()
        print(f"DIAGNOSTIC SOURCE MESSAGES: {len(errors)}")
        for e in errors[:20]:
            print(f"  {e['scope']}: {e['error']}")
    print()
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    print()
    print("NOTE: PASS certifies the bounded investigation mechanics and controls.")
    print("It does NOT authorize assigning a payment to any affirmative exception.")
    return 0 if overall else 1

if __name__ == "__main__":
    sys.exit(main())
