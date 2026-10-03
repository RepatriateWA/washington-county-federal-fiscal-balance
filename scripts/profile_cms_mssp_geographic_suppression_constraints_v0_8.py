#!/usr/bin/env python3
r"""
CMS MSSP Geographic Suppression Constraints Profile v0.8

Purpose
-------
Read-only empirical profile of what CMS MSSP assigned-beneficiary county
geography permits us to know about ACO geographic incidence before any
financial allocation.

This script:
  * preserves 2019 regular and off-cycle as distinct participation periods;
  * profiles visible vs suppressed/unresolved county Tot_AB and Tot_AB_Psn_Yrs;
  * separates Washington from non-Washington observations;
  * searches the corresponding CMS financial/performance PUF for candidate
    ACO-level assigned-beneficiary totals/person-years;
  * tests candidate financial fields empirically against visible county values;
  * computes residuals only when a candidate financial field is numeric;
  * DOES NOT impute suppressed county values;
  * DOES NOT allocate EarnSaveLoss or any other dollar value;
  * DOES NOT make a ledger-inclusion decision.

2015 is intentionally excluded from empirical profiling because the original
county source artifact has not been recovered.

Run from repository root:
    python .\scripts\profile_cms_mssp_geographic_suppression_constraints_v0_8.py

Optional console capture:
    python .\scripts\profile_cms_mssp_geographic_suppression_constraints_v0_8.py `
      *> .\cms_mssp_geographic_suppression_constraints_v0_8_console.txt
"""
from __future__ import annotations

import csv
import io
import math
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

VERSION = "v0.8"
WA_STATE_ID = "53"
WA_NAMES = {"washington", "wa"}

COUNTY_REL = Path("data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county")
FIN_REL = Path("data/raw/cms/medicare_aco/mssp_performance_results")
EVID_REL = COUNTY_REL / "validation" / "geographic_suppression_constraints_v0_8"

PINNED_2016_2018 = {
    2016: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2016_01_01.csv",
    2017: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2017_01_01.csv",
    2018: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2018_01_01.csv",
}

MEASURE_ALIASES = {
    "Tot_AB": [
        "Tot_AB",
        "Total assigned beneficiaries",
        "Total assigned beneficiary",
    ],
    "Tot_AB_Psn_Yrs": [
        "Tot_AB_Psn_Yrs",
        "Total assigned beneficiary person-years",
        "Total assigned beneficiary person years",
        "Total assigned beneficiaries person-years",
    ],
}

# Candidate financial/performance fields are intentionally broad. We do not
# assume equivalence from names alone; the script inventories and empirically
# compares any fields that are actually present.
FINANCIAL_CANDIDATE_PATTERNS = [
    r"^N_AB_Year_PY$",
    r"^N_AB_PY$",
    r"^N_Ben_PY$",
    r"^N_Ben$",
    r"^N_AB$",
    r"assigned.*benef",
    r"benef.*assigned",
    r"person.*year.*performance",
    r"performance.*person.*year",
]

@dataclass
class PeriodSource:
    period: str
    year: int
    source_name: str
    fields: list[str]
    rows: list[dict[str, str]]

def repo_root() -> Path:
    starts = [Path.cwd().resolve(), Path(__file__).resolve().parent]
    for start in starts:
        for p in (start, *start.parents):
            if (p / "data").is_dir() and (p / "scripts").is_dir():
                return p
    raise RuntimeError("Could not locate repository root.")

def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def compact_norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", norm(s)).strip("_")

def parse_num(v: str | None):
    if v is None:
        return None
    s = v.strip()
    if not s or s in {".", "*", "-", "NA", "N/A"}:
        return None
    try:
        x = float(s.replace(",", "").replace("$", ""))
        return x if math.isfinite(x) else None
    except ValueError:
        return None

def raw_state(v: str | None) -> str:
    if v is None or not v.strip():
        return "BLANK"
    s = v.strip()
    if s == ".":
        return "DOT"
    if s == "*":
        return "STAR"
    if parse_num(s) is not None:
        return "NUMERIC"
    return "OTHER"

def read_csv_bytes(raw: bytes):
    text = raw.decode("utf-8-sig", errors="strict")
    r = csv.DictReader(io.StringIO(text))
    return r.fieldnames or [], list(r)

def read_csv_path(path: Path):
    return read_csv_bytes(path.read_bytes())

def find_col(fields, aliases):
    cmap = {compact_norm(f): f for f in fields}
    for alias in aliases:
        hit = cmap.get(compact_norm(alias))
        if hit:
            return hit
    return None

def find_aco_col(fields):
    return find_col(fields, ["ACO_ID", "ACO ID", "ACO_Num", "ACO Num"])

def find_state_id_col(fields):
    return find_col(fields, ["State_ID", "State ID", "State FIPS", "State_FIPS"])

def find_state_name_col(fields):
    return find_col(fields, ["State_Name", "State Name", "State"])

def find_measure_col(fields, canonical):
    return find_col(fields, MEASURE_ALIASES[canonical])

def is_wa(row, state_id_col, state_name_col):
    if state_id_col:
        sid = (row.get(state_id_col) or "").strip()
        if sid:
            sid = sid.zfill(2) if sid.isdigit() else sid
            if sid == WA_STATE_ID:
                return True
    if state_name_col:
        if norm(row.get(state_name_col)) in WA_NAMES:
            return True
    return False

def discover_modern_county_zip(src: Path) -> Path:
    candidates = []
    for p in src.glob("*.zip"):
        try:
            with zipfile.ZipFile(p) as z:
                names = [n.lower().replace("\\", "/") for n in z.namelist()]
                score = sum(
                    any(f"/{y}/" in n and n.endswith(".csv") for n in names)
                    for y in range(2020, 2025)
                )
                if score >= 5:
                    candidates.append((score, p))
        except zipfile.BadZipFile:
            pass
    if not candidates:
        raise FileNotFoundError("Could not discover 2020-2024 county ZIP.")
    return sorted(candidates, key=lambda x: (-x[0], str(x[1]).lower()))[0][1]

def choose_year_member(z: zipfile.ZipFile, year: int, offcycle: bool | None = None):
    cands = []
    for n in z.namelist():
        low = n.lower().replace("\\", "/")
        if not low.endswith(".csv") or str(year) not in low:
            continue
        oc = ("off-cycle" in low or "off_cycle" in low or "2019_07_01" in low)
        if offcycle is True and not oc:
            continue
        if offcycle is False and oc:
            continue
        score = 0
        if "beneficiar" in low: score += 3
        if "county" in low: score += 3
        if "puf" in low: score += 2
        cands.append((score, n))
    if not cands:
        raise FileNotFoundError(f"No county CSV member found for year={year}, offcycle={offcycle}")
    return sorted(cands, key=lambda x: (-x[0], x[1].lower()))[0][1]

def load_county_periods(src: Path) -> list[PeriodSource]:
    periods = []

    for year, filename in PINNED_2016_2018.items():
        p = src / filename
        fields, rows = read_csv_path(p)
        periods.append(PeriodSource(str(year), year, filename, fields, rows))

    # 2019 dedicated ZIP contains regular and off-cycle.
    zips_2019 = []
    for p in src.glob("*.zip"):
        try:
            with zipfile.ZipFile(p) as z:
                lows = [n.lower() for n in z.namelist()]
                if any("2019_01_01" in n for n in lows) and any("2019_07_01" in n for n in lows):
                    zips_2019.append(p)
        except zipfile.BadZipFile:
            pass
    if not zips_2019:
        raise FileNotFoundError("Could not discover 2019 regular/off-cycle county ZIP.")
    zip2019 = sorted(zips_2019, key=lambda p: str(p).lower())[0]
    with zipfile.ZipFile(zip2019) as z:
        for period, offcycle in [("2019", False), ("2019A", True)]:
            member = choose_year_member(z, 2019, offcycle)
            fields, rows = read_csv_bytes(z.read(member))
            periods.append(
                PeriodSource(period, 2019, f"{zip2019.name}::{member}", fields, rows)
            )

    modern = discover_modern_county_zip(src)
    with zipfile.ZipFile(modern) as z:
        for year in range(2020, 2025):
            member = choose_year_member(z, year, False)
            fields, rows = read_csv_bytes(z.read(member))
            periods.append(
                PeriodSource(str(year), year, f"{modern.name}::{member}", fields, rows)
            )

    return periods

def discover_financial_zip(fin_dir: Path) -> Path:
    zips = list(fin_dir.glob("*.zip"))
    if not zips:
        raise FileNotFoundError(f"No financial ZIP found under {fin_dir}")
    scored = []
    for p in zips:
        try:
            with zipfile.ZipFile(p) as z:
                names = [n.lower() for n in z.namelist()]
                score = sum(any(str(y) in n and n.endswith(".csv") for n in names)
                            for y in range(2016, 2025))
                scored.append((score, p))
        except zipfile.BadZipFile:
            pass
    if not scored:
        raise FileNotFoundError("No readable financial ZIP found.")
    return sorted(scored, key=lambda x: (-x[0], str(x[1]).lower()))[0][1]

def financial_member_score(name: str, period: str) -> int:
    low = name.lower().replace("\\", "/")
    if not low.endswith(".csv"):
        return -999
    year = period[:4]
    if year not in low:
        return -999
    score = 0
    if "financial" in low: score += 4
    if "quality" in low: score += 2
    if "performance" in low: score += 2
    is_a = period.endswith("A")
    off_tokens = ("off-cycle", "off_cycle", "2019a", "2019_07", "2019-07")
    has_off = any(t in low for t in off_tokens)
    if is_a:
        score += 8 if has_off else -5
    else:
        score += -8 if has_off else 3
    return score

def choose_financial_member(z: zipfile.ZipFile, period: str) -> str:
    cands = [(financial_member_score(n, period), n) for n in z.namelist()]
    cands = [x for x in cands if x[0] > -999]
    if not cands:
        raise FileNotFoundError(f"No financial member candidate for {period}")
    cands.sort(key=lambda x: (-x[0], x[1].lower()))
    return cands[0][1]

def candidate_financial_cols(fields):
    hits = []
    for f in fields:
        c = compact_norm(f)
        for pat in FINANCIAL_CANDIDATE_PATTERNS:
            if re.search(pat, f, flags=re.I) or re.search(pat, c, flags=re.I):
                hits.append(f)
                break
    # Ensure known high-value field is included if present.
    for alias in ["N_AB_Year_PY"]:
        hit = find_col(fields, [alias])
        if hit and hit not in hits:
            hits.append(hit)
    return hits

def profile_period(period: PeriodSource):
    fields, rows = period.fields, period.rows
    acol = find_aco_col(fields)
    sid = find_state_id_col(fields)
    sname = find_state_name_col(fields)
    tot_ab = find_measure_col(fields, "Tot_AB")
    tot_py = find_measure_col(fields, "Tot_AB_Psn_Yrs")
    if not all([acol, tot_ab, tot_py]):
        raise RuntimeError(
            f"{period.period}: required columns missing: "
            f"ACO={acol}, Tot_AB={tot_ab}, Tot_AB_Psn_Yrs={tot_py}"
        )

    by_aco = defaultdict(list)
    for r in rows:
        aco = (r.get(acol) or "").strip()
        if aco:
            by_aco[aco].append(r)

    out = {}
    for aco, rs in by_aco.items():
        rec = {
            "period": period.period,
            "year": period.year,
            "aco_id": aco,
            "county_rows": len(rs),
        }
        for measure, col in [("tot_ab", tot_ab), ("tot_py", tot_py)]:
            for geo_name, pred in [
                ("all", lambda r: True),
                ("wa", lambda r: is_wa(r, sid, sname)),
                ("nonwa", lambda r: not is_wa(r, sid, sname)),
            ]:
                subset = [r for r in rs if pred(r)]
                states = Counter(raw_state(r.get(col)) for r in subset)
                nums = [parse_num(r.get(col)) for r in subset]
                nums = [x for x in nums if x is not None]
                prefix = f"{measure}_{geo_name}"
                rec[f"{prefix}_rows"] = len(subset)
                rec[f"{prefix}_numeric_rows"] = states["NUMERIC"]
                rec[f"{prefix}_star_rows"] = states["STAR"]
                rec[f"{prefix}_dot_rows"] = states["DOT"]
                rec[f"{prefix}_blank_rows"] = states["BLANK"]
                rec[f"{prefix}_other_rows"] = states["OTHER"]
                rec[f"{prefix}_visible_sum"] = sum(nums)

        all_visible = rec["tot_ab_all_visible_sum"]
        wa_visible = rec["tot_ab_wa_visible_sum"]
        rec["tot_ab_visible_wa_share"] = (
            wa_visible / all_visible if all_visible > 0 else None
        )
        rec["has_wa_any_row"] = int(rec["tot_ab_wa_rows"] > 0)
        rec["has_wa_numeric"] = int(rec["tot_ab_wa_numeric_rows"] > 0)
        rec["has_wa_suppressed_or_unresolved"] = int(
            rec["tot_ab_wa_star_rows"] > 0 or rec["tot_ab_wa_blank_rows"] > 0
        )
        rec["has_nonwa_suppressed_or_unresolved"] = int(
            rec["tot_ab_nonwa_star_rows"] > 0 or rec["tot_ab_nonwa_blank_rows"] > 0
        )
        out[aco] = rec
    return out

def main():
    root = repo_root()
    county_dir = root / COUNTY_REL
    fin_dir = root / FIN_REL
    evid = root / EVID_REL
    evid.mkdir(parents=True, exist_ok=True)

    report = []
    checks = []
    detail_rows = []
    candidate_rows = []

    def emit(s=""):
        print(s)
        report.append(s)

    def check(code, ok, detail):
        checks.append((code, "PASS" if ok else "FAIL", detail))
        emit(f"{code}: {'PASS' if ok else 'FAIL'} - {detail}")

    emit(f"CMS MSSP GEOGRAPHIC SUPPRESSION CONSTRAINTS PROFILE {VERSION}")
    emit("=" * 108)
    emit("Read-only. No imputation, financial allocation, DB writes, or ledger decision.")
    emit("2015 excluded: original county artifact not recovered.")
    emit("2016 blanks remain unresolved historical encoding.")
    emit("2019 regular and off-cycle are separate participation periods.")
    emit()

    periods = load_county_periods(county_dir)
    expected_periods = ["2016", "2017", "2018", "2019", "2019A",
                        "2020", "2021", "2022", "2023", "2024"]
    got = [p.period for p in periods]
    check("COUNTY-PERIODS", got == expected_periods, f"periods={got}")

    fin_zip = discover_financial_zip(fin_dir)
    emit(f"Financial ZIP: {fin_zip}")
    emit()

    with zipfile.ZipFile(fin_zip) as z:
        for p in periods:
            emit(f"{p.period} SUPPRESSION CONSTRAINT PROFILE")
            emit("-" * 108)
            emit(f"County source: {p.source_name}")
            profiles = profile_period(p)
            emit(f"County ACO universe: {len(profiles):,}")

            member = choose_financial_member(z, p.period)
            f_fields, f_rows = read_csv_bytes(z.read(member))
            f_aco = find_aco_col(f_fields)
            check(f"{p.period}-FIN-ACO-COL", f_aco is not None,
                  f"financial member={member}; ACO column={f_aco}")
            if not f_aco:
                emit()
                continue

            fin_by_aco = {
                (r.get(f_aco) or "").strip(): r
                for r in f_rows if (r.get(f_aco) or "").strip()
            }
            county_ids = set(profiles)
            fin_ids = set(fin_by_aco)
            check(
                f"{p.period}-ACO-LINK",
                county_ids == fin_ids,
                f"county={len(county_ids):,}; financial={len(fin_ids):,}; "
                f"intersection={len(county_ids & fin_ids):,}; "
                f"county_only={len(county_ids-fin_ids):,}; "
                f"financial_only={len(fin_ids-county_ids):,}"
            )

            cand_cols = candidate_financial_cols(f_fields)
            emit(f"Financial member: {member}")
            emit(f"Candidate assigned-beneficiary fields ({len(cand_cols)}):")
            for c in cand_cols:
                emit(f"  {c}")
            if not cand_cols:
                emit("  [none detected]")
            emit()

            # Candidate diagnostics across exact-linked ACOs.
            for col in cand_cols:
                pairs_ab = []
                pairs_py = []
                residual_ab = []
                residual_py = []
                negative_ab = 0
                negative_py = 0
                numeric_fin = 0

                for aco in sorted(county_ids & fin_ids):
                    fv = parse_num(fin_by_aco[aco].get(col))
                    if fv is None:
                        continue
                    numeric_fin += 1
                    rec = profiles[aco]
                    vab = rec["tot_ab_all_visible_sum"]
                    vpy = rec["tot_py_all_visible_sum"]
                    pairs_ab.append((fv, vab))
                    pairs_py.append((fv, vpy))
                    rab = fv - vab
                    rpy = fv - vpy
                    residual_ab.append(rab)
                    residual_py.append(rpy)
                    if rab < -1e-9: negative_ab += 1
                    if rpy < -1e-9: negative_py += 1

                candidate_rows.append({
                    "period": p.period,
                    "financial_member": member,
                    "candidate_field": col,
                    "linked_aco_count": len(county_ids & fin_ids),
                    "financial_numeric_aco_count": numeric_fin,
                    "negative_residual_vs_visible_tot_ab": negative_ab,
                    "negative_residual_vs_visible_tot_py": negative_py,
                    "mean_residual_vs_visible_tot_ab": (
                        sum(residual_ab)/len(residual_ab) if residual_ab else None
                    ),
                    "mean_residual_vs_visible_tot_py": (
                        sum(residual_py)/len(residual_py) if residual_py else None
                    ),
                    "exact_equal_vs_visible_tot_ab_count": sum(
                        abs(a-b) < 1e-9 for a,b in pairs_ab
                    ),
                    "exact_equal_vs_visible_tot_py_count": sum(
                        abs(a-b) < 1e-9 for a,b in pairs_py
                    ),
                })

                emit(
                    f"CANDIDATE {col}: numeric_ACOs={numeric_fin:,}; "
                    f"negative residual vs visible Tot_AB={negative_ab:,}; "
                    f"vs visible Tot_AB_Psn_Yrs={negative_py:,}"
                )

            # Attach candidate values/residuals to ACO detail.
            for aco, rec in profiles.items():
                row = dict(rec)
                frow = fin_by_aco.get(aco, {})
                for col in cand_cols:
                    key = compact_norm(col)
                    fv = parse_num(frow.get(col))
                    row[f"fin__{key}"] = fv
                    if fv is not None:
                        row[f"resid_ab__{key}"] = fv - rec["tot_ab_all_visible_sum"]
                        row[f"resid_py__{key}"] = fv - rec["tot_py_all_visible_sum"]
                    else:
                        row[f"resid_ab__{key}"] = None
                        row[f"resid_py__{key}"] = None
                detail_rows.append(row)

            # Period-level facts most relevant to WA allocation feasibility.
            vals = list(profiles.values())
            emit()
            emit(f"ACOs with any WA county row: "
                 f"{sum(r['has_wa_any_row'] for r in vals):,}")
            emit(f"ACOs with WA numeric Tot_AB: "
                 f"{sum(r['has_wa_numeric'] for r in vals):,}")
            emit(f"ACOs with WA suppressed/unresolved Tot_AB: "
                 f"{sum(r['has_wa_suppressed_or_unresolved'] for r in vals):,}")
            emit(f"ACOs with non-WA suppressed/unresolved Tot_AB: "
                 f"{sum(r['has_nonwa_suppressed_or_unresolved'] for r in vals):,}")
            emit(f"Visible WA Tot_AB sum: "
                 f"{sum(r['tot_ab_wa_visible_sum'] for r in vals):,.3f}")
            emit(f"Visible all-geography Tot_AB sum: "
                 f"{sum(r['tot_ab_all_visible_sum'] for r in vals):,.3f}")
            emit()

    emit("INTERPRETIVE BOUNDARY")
    emit("-" * 108)
    emit("Candidate financial fields are profiled, not certified as equivalent to county Tot_AB.")
    emit("A nonnegative residual is a mathematical difference, not permission to impute its geography.")
    emit("A negative residual is evidence that the candidate field is not a simple governing total")
    emit("for that county measure (or differs in timing/definition/rounding).")
    emit("Visible WA share is descriptive only and MUST NOT be used as a financial allocation weight yet.")
    emit("No EarnSaveLoss or other financial amount was allocated.")
    emit()

    failures = [x for x in checks if x[1] == "FAIL"]
    emit(f"OVERALL PROFILE EXECUTION {VERSION}: {'PASS' if not failures else 'FAIL'}")
    emit(f"Checks: {len(checks)} total; {len(failures)} failed")
    emit(f"Evidence: {evid}")

    # Write report.
    (evid / "cms_mssp_geographic_suppression_constraints_v0_8.txt").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )

    # Union all detail columns.
    if detail_rows:
        preferred = [
            "period", "year", "aco_id", "county_rows",
            "has_wa_any_row", "has_wa_numeric",
            "has_wa_suppressed_or_unresolved",
            "has_nonwa_suppressed_or_unresolved",
            "tot_ab_visible_wa_share",
        ]
        all_fields = set().union(*(r.keys() for r in detail_rows))
        rest = sorted(all_fields - set(preferred))
        fields = [f for f in preferred if f in all_fields] + rest
        with (evid / "cms_mssp_geographic_suppression_constraints_detail_v0_8.csv").open(
            "w", encoding="utf-8", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(detail_rows)

    if candidate_rows:
        fields = list(candidate_rows[0].keys())
        with (evid / "cms_mssp_financial_total_candidate_diagnostics_v0_8.csv").open(
            "w", encoding="utf-8", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(candidate_rows)

    with (evid / "cms_mssp_geographic_suppression_constraints_checks_v0_8.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        w = csv.writer(f)
        w.writerow(["check_code", "status", "detail"])
        w.writerows(checks)

    return 0 if not failures else 1

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nFATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
