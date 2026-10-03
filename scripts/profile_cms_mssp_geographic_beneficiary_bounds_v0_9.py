#!/usr/bin/env python3
r"""
CMS MSSP Geographic Beneficiary Bounds Profile v0.9

Purpose
-------
Derive rigorous, suppression-aware bounds on Washington assigned-beneficiary
incidence for CMS Medicare Shared Savings Program (MSSP) ACOs, using:

  * county-level Tot_AB observations;
  * CMS financial/performance-results ACO-level N_AB control totals;
  * preserved raw suppression symbols;
  * geography of suppressed/unresolved county cells.

CRITICAL METHODOLOGICAL RULE
----------------------------
A CMS '*' cell is NOT automatically treated as 1-10 beneficiaries.
CMS uses both primary and complementary suppression. Complementary-suppressed
cells may contain values outside the primary-suppression range. Therefore this
script does not assign a 1-10 bound to every '*'.

For 2017-2024 (including 2019A), '.' and '*' retain their previously certified
lexical/documentary semantics. For Tot_AB specifically, prior profiling found
no '.' states in the total field.

For 2016, blank Tot_AB cells remain UNRESOLVED_HISTORICAL_ENCODING. They are
included in broad residual-based bounds but are not relabeled as '*'.

This script:
  * preserves 2019 regular and 2019A off-cycle as separate periods;
  * links county ACOs exactly to the corresponding financial PUF;
  * uses N_AB as the candidate ACO-level beneficiary-count control;
  * computes the exact aggregate hidden residual:
        R_a = N_AB_a - sum(visible county Tot_AB)
  * derives broad, assumption-minimal Washington bounds from residual geography;
  * never imputes an individual suppressed county value;
  * never allocates EarnSaveLoss or any other financial measure;
  * never makes a ledger-inclusion decision;
  * performs no database writes and does not modify source files.

2015 is excluded because the original county source artifact has not been
recovered.

Run from repository root:
    python .\scripts\profile_cms_mssp_geographic_beneficiary_bounds_v0_9.py

Optional console capture:
    python .\scripts\profile_cms_mssp_geographic_beneficiary_bounds_v0_9.py `
      *> .\cms_mssp_geographic_beneficiary_bounds_v0_9_console.txt
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

VERSION = "v0.9"
WA_STATE_ID = "53"
WA_NAMES = {"washington", "wa"}

COUNTY_REL = Path("data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county")
FIN_REL = Path("data/raw/cms/medicare_aco/mssp_performance_results")
EVID_REL = COUNTY_REL / "validation" / "geographic_beneficiary_bounds_v0_9"

PINNED_2016_2018 = {
    2016: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2016_01_01.csv",
    2017: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2017_01_01.csv",
    2018: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2018_01_01.csv",
}

TOT_AB_ALIASES = [
    "Tot_AB",
    "Total assigned beneficiaries",
    "Total assigned beneficiary",
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

def is_wa(row, state_id_col, state_name_col):
    if state_id_col:
        sid = (row.get(state_id_col) or "").strip()
        if sid:
            if sid.isdigit():
                sid = sid.zfill(2)
            if sid == WA_STATE_ID:
                return True
    if state_name_col and norm(row.get(state_name_col)) in WA_NAMES:
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
        raise FileNotFoundError(
            f"No county CSV member found for year={year}, offcycle={offcycle}"
        )
    return sorted(cands, key=lambda x: (-x[0], x[1].lower()))[0][1]

def load_county_periods(src: Path) -> list[PeriodSource]:
    periods = []

    for year, filename in PINNED_2016_2018.items():
        p = src / filename
        fields, rows = read_csv_path(p)
        periods.append(PeriodSource(str(year), year, filename, fields, rows))

    zips_2019 = []
    for p in src.glob("*.zip"):
        try:
            with zipfile.ZipFile(p) as z:
                lows = [n.lower() for n in z.namelist()]
                if any("2019_01_01" in n for n in lows) and any(
                    "2019_07_01" in n for n in lows
                ):
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
                score = sum(
                    any(str(y) in n and n.endswith(".csv") for n in names)
                    for y in range(2016, 2025)
                )
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

def classify_hidden_state(period: str, state: str) -> bool:
    if period == "2016":
        return state == "BLANK"
    return state == "STAR"

def build_county_profile(period: PeriodSource):
    acol = find_aco_col(period.fields)
    sid = find_state_id_col(period.fields)
    sname = find_state_name_col(period.fields)
    tot = find_col(period.fields, TOT_AB_ALIASES)

    if not acol or not tot:
        raise RuntimeError(
            f"{period.period}: missing required county column: ACO={acol}, Tot_AB={tot}"
        )

    by_aco = defaultdict(list)
    for row in period.rows:
        aco = (row.get(acol) or "").strip()
        if aco:
            by_aco[aco].append(row)

    profiles = {}
    unexpected = 0

    for aco, rows in by_aco.items():
        rec = {
            "period": period.period,
            "year": period.year,
            "aco_id": aco,
            "county_rows": len(rows),
        }

        for geo_name, pred in [
            ("all", lambda r: True),
            ("wa", lambda r: is_wa(r, sid, sname)),
            ("nonwa", lambda r: not is_wa(r, sid, sname)),
        ]:
            subset = [r for r in rows if pred(r)]
            states = Counter(raw_state(r.get(tot)) for r in subset)
            nums = [parse_num(r.get(tot)) for r in subset]
            nums = [x for x in nums if x is not None]

            rec[f"{geo_name}_rows"] = len(subset)
            rec[f"{geo_name}_numeric_rows"] = states["NUMERIC"]
            rec[f"{geo_name}_star_rows"] = states["STAR"]
            rec[f"{geo_name}_dot_rows"] = states["DOT"]
            rec[f"{geo_name}_blank_rows"] = states["BLANK"]
            rec[f"{geo_name}_other_rows"] = states["OTHER"]
            rec[f"{geo_name}_visible_sum"] = sum(nums)

            hidden = 0
            for r in subset:
                if classify_hidden_state(period.period, raw_state(r.get(tot))):
                    hidden += 1
            rec[f"{geo_name}_hidden_rows"] = hidden

            unexpected += states["OTHER"]

        profiles[aco] = rec

    return profiles, unexpected

def bound_wa(rec, n_ab):
    """
    Assumption-minimal residual allocation bounds.

    Let:
      Vwa = visible Washington Tot_AB
      Vall = visible all-county Tot_AB
      R = N_AB - Vall

    If no hidden WA cell exists, WA hidden count is exactly 0.
    If hidden WA exists and no hidden non-WA cell exists, all residual must be WA.
    If hidden cells exist in both WA and non-WA, residual may lie anywhere from
    0 to R in WA absent a stronger certified cell-level constraint.

    These are deliberately broad. They do not assume every '*' is 1-10.
    """
    vall = rec["all_visible_sum"]
    vwa = rec["wa_visible_sum"]
    residual = n_ab - vall

    if residual < -1e-9:
        return {
            "residual": residual,
            "wa_min": None,
            "wa_max": None,
            "wa_share_min": None,
            "wa_share_max": None,
            "bound_class": "INVALID_NEGATIVE_RESIDUAL",
        }

    # Tolerate floating representation; beneficiary counts should be integral.
    if abs(residual) < 1e-9:
        residual = 0.0

    hwa = rec["wa_hidden_rows"]
    hnw = rec["nonwa_hidden_rows"]

    if residual == 0:
        hidden_wa_min = hidden_wa_max = 0.0
        cls = "POINT_IDENTIFIED_ZERO_RESIDUAL"
    elif hwa == 0 and hnw > 0:
        hidden_wa_min = hidden_wa_max = 0.0
        cls = "POINT_IDENTIFIED_NO_WA_HIDDEN_CELLS"
    elif hwa > 0 and hnw == 0:
        hidden_wa_min = hidden_wa_max = residual
        cls = "POINT_IDENTIFIED_ALL_HIDDEN_CELLS_WA"
    elif hwa > 0 and hnw > 0:
        hidden_wa_min = 0.0
        hidden_wa_max = residual
        cls = "INTERVAL_BOTH_WA_AND_NONWA_HIDDEN"
    else:
        # Residual exists but no source cell is classified as hidden.
        hidden_wa_min = hidden_wa_max = None
        cls = "UNEXPLAINED_RESIDUAL_NO_HIDDEN_CELLS"

    if hidden_wa_min is None:
        return {
            "residual": residual,
            "wa_min": None,
            "wa_max": None,
            "wa_share_min": None,
            "wa_share_max": None,
            "bound_class": cls,
        }

    wa_min = vwa + hidden_wa_min
    wa_max = vwa + hidden_wa_max
    share_min = wa_min / n_ab if n_ab > 0 else None
    share_max = wa_max / n_ab if n_ab > 0 else None

    return {
        "residual": residual,
        "wa_min": wa_min,
        "wa_max": wa_max,
        "wa_share_min": share_min,
        "wa_share_max": share_max,
        "bound_class": cls,
    }

def fmt_num(x):
    return "NA" if x is None else f"{x:,.3f}"

def fmt_pct(x):
    return "NA" if x is None else f"{100*x:.3f}%"

def main():
    root = repo_root()
    county_dir = root / COUNTY_REL
    fin_dir = root / FIN_REL
    evid = root / EVID_REL
    evid.mkdir(parents=True, exist_ok=True)

    report = []
    checks = []
    detail_rows = []
    period_rows = []

    def emit(s=""):
        print(s)
        report.append(s)

    def check(code, ok, detail):
        status = "PASS" if ok else "FAIL"
        checks.append((code, status, detail))
        emit(f"{code}: {status} - {detail}")

    emit(f"CMS MSSP GEOGRAPHIC BENEFICIARY BOUNDS PROFILE {VERSION}")
    emit("=" * 112)
    emit("Read-only. No imputation, dollar allocation, DB writes, or ledger decision.")
    emit("BOUNDING RULE: '*' is NOT assumed to mean 1-10 in every cell.")
    emit("Complementary suppression prevents a universal 1-10 interpretation of '*'.")
    emit("2016 blanks remain unresolved historical encoding and are bounded separately.")
    emit("2019 and 2019A remain separate participation periods.")
    emit()

    periods = load_county_periods(county_dir)
    expected = ["2016", "2017", "2018", "2019", "2019A",
                "2020", "2021", "2022", "2023", "2024"]
    got = [p.period for p in periods]
    check("COUNTY-PERIODS", got == expected, f"periods={got}")

    fin_zip = discover_financial_zip(fin_dir)
    emit(f"Financial ZIP: {fin_zip}")
    emit()

    with zipfile.ZipFile(fin_zip) as z:
        for period in periods:
            emit(f"{period.period} BENEFICIARY BOUNDS")
            emit("-" * 112)
            emit(f"County source: {period.source_name}")

            profiles, unexpected = build_county_profile(period)
            check(
                f"{period.period}-COUNTY-LEXICAL",
                unexpected == 0,
                f"unexpected Tot_AB states={unexpected:,}"
            )

            member = choose_financial_member(z, period.period)
            f_fields, f_rows = read_csv_bytes(z.read(member))
            f_aco = find_aco_col(f_fields)
            n_ab_col = find_col(f_fields, ["N_AB"])

            check(
                f"{period.period}-FIN-SCHEMA",
                f_aco is not None and n_ab_col is not None,
                f"member={member}; ACO={f_aco}; N_AB={n_ab_col}"
            )
            if not f_aco or not n_ab_col:
                emit()
                continue

            fin_by_aco = {
                (r.get(f_aco) or "").strip(): r
                for r in f_rows if (r.get(f_aco) or "").strip()
            }

            cids = set(profiles)
            fids = set(fin_by_aco)
            check(
                f"{period.period}-ACO-LINK",
                cids == fids,
                f"county={len(cids):,}; financial={len(fids):,}; "
                f"intersection={len(cids & fids):,}; "
                f"county_only={len(cids-fids):,}; financial_only={len(fids-cids):,}"
            )

            numeric_n = 0
            negative = 0
            unexplained = 0
            class_counts = Counter()
            total_n = 0.0
            total_visible = 0.0
            total_residual = 0.0
            total_wa_visible = 0.0
            sum_wa_min = 0.0
            sum_wa_max = 0.0
            all_bounds_numeric = True

            for aco in sorted(cids & fids):
                rec = profiles[aco]
                n_ab = parse_num(fin_by_aco[aco].get(n_ab_col))
                if n_ab is None:
                    row = dict(rec)
                    row.update({
                        "n_ab": None,
                        "residual": None,
                        "wa_beneficiaries_min": None,
                        "wa_beneficiaries_max": None,
                        "wa_share_min": None,
                        "wa_share_max": None,
                        "bound_class": "N_AB_NOT_NUMERIC",
                    })
                    detail_rows.append(row)
                    all_bounds_numeric = False
                    continue

                numeric_n += 1
                b = bound_wa(rec, n_ab)
                class_counts[b["bound_class"]] += 1
                if b["residual"] is not None and b["residual"] < -1e-9:
                    negative += 1
                if b["bound_class"] == "UNEXPLAINED_RESIDUAL_NO_HIDDEN_CELLS":
                    unexplained += 1

                row = dict(rec)
                row.update({
                    "n_ab": n_ab,
                    "residual": b["residual"],
                    "wa_beneficiaries_min": b["wa_min"],
                    "wa_beneficiaries_max": b["wa_max"],
                    "wa_share_min": b["wa_share_min"],
                    "wa_share_max": b["wa_share_max"],
                    "bound_class": b["bound_class"],
                })
                detail_rows.append(row)

                total_n += n_ab
                total_visible += rec["all_visible_sum"]
                total_wa_visible += rec["wa_visible_sum"]
                if b["residual"] is not None:
                    total_residual += b["residual"]
                if b["wa_min"] is None or b["wa_max"] is None:
                    all_bounds_numeric = False
                else:
                    sum_wa_min += b["wa_min"]
                    sum_wa_max += b["wa_max"]

            check(
                f"{period.period}-N-AB-NUMERIC",
                numeric_n == len(cids & fids),
                f"numeric N_AB={numeric_n:,}/{len(cids & fids):,}"
            )
            check(
                f"{period.period}-RESIDUAL-NONNEGATIVE",
                negative == 0,
                f"negative residual ACOs={negative:,}"
            )
            check(
                f"{period.period}-RESIDUAL-EXPLAINED-BY-HIDDEN-CELLS",
                unexplained == 0,
                f"positive residual with no classified hidden cell={unexplained:,}"
            )

            period_share_min = (
                sum_wa_min / total_n if all_bounds_numeric and total_n > 0 else None
            )
            period_share_max = (
                sum_wa_max / total_n if all_bounds_numeric and total_n > 0 else None
            )

            emit(f"Financial member: {member}")
            emit(f"ACO universe: {len(cids):,}")
            emit(f"N_AB total: {total_n:,.0f}")
            emit(f"Visible county Tot_AB total: {total_visible:,.0f}")
            emit(f"Aggregate hidden residual: {total_residual:,.0f}")
            emit(f"Visible Washington Tot_AB: {total_wa_visible:,.0f}")
            emit("Bound classes:")
            for k in sorted(class_counts):
                emit(f"  {k}: {class_counts[k]:,}")
            emit(
                "Aggregate WA beneficiary bound: "
                f"{fmt_num(sum_wa_min if all_bounds_numeric else None)}"
                f" to {fmt_num(sum_wa_max if all_bounds_numeric else None)}"
            )
            emit(
                "Aggregate WA share bound: "
                f"{fmt_pct(period_share_min)} to {fmt_pct(period_share_max)}"
            )

            period_rows.append({
                "period": period.period,
                "year": period.year,
                "aco_count": len(cids),
                "n_ab_total": total_n,
                "visible_county_tot_ab": total_visible,
                "aggregate_hidden_residual": total_residual,
                "visible_wa_tot_ab": total_wa_visible,
                "wa_beneficiaries_min": sum_wa_min if all_bounds_numeric else None,
                "wa_beneficiaries_max": sum_wa_max if all_bounds_numeric else None,
                "wa_share_min": period_share_min,
                "wa_share_max": period_share_max,
                "point_zero_residual_aco_count":
                    class_counts["POINT_IDENTIFIED_ZERO_RESIDUAL"],
                "point_no_wa_hidden_aco_count":
                    class_counts["POINT_IDENTIFIED_NO_WA_HIDDEN_CELLS"],
                "point_all_hidden_wa_aco_count":
                    class_counts["POINT_IDENTIFIED_ALL_HIDDEN_CELLS_WA"],
                "interval_both_geo_hidden_aco_count":
                    class_counts["INTERVAL_BOTH_WA_AND_NONWA_HIDDEN"],
                "unexplained_residual_aco_count": unexplained,
                "negative_residual_aco_count": negative,
            })
            emit()

    emit("INTERPRETIVE BOUNDARY")
    emit("-" * 112)
    emit("The interval is an assumption-minimal feasibility bound, not a point estimate.")
    emit("No '*' cell is assigned 1-10 solely because it is suppressed.")
    emit("Complementary-suppressed cells are not presumed to satisfy the primary-suppression threshold.")
    emit("2016 blank cells remain unresolved and are not relabeled as suppression.")
    emit("N_AB residuals are not assigned to individual counties.")
    emit("No visible-WA share or interval midpoint is authorized as a financial allocation weight.")
    emit("No EarnSaveLoss or other financial amount was allocated.")
    emit()

    failures = [x for x in checks if x[1] == "FAIL"]
    emit(f"OVERALL PROFILE EXECUTION {VERSION}: {'PASS' if not failures else 'FAIL'}")
    emit(f"Checks: {len(checks)} total; {len(failures)} failed")
    emit(f"Evidence: {evid}")

    # Evidence outputs
    (evid / "cms_mssp_geographic_beneficiary_bounds_v0_9.txt").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )

    if detail_rows:
        preferred = [
            "period", "year", "aco_id", "n_ab", "all_visible_sum", "residual",
            "wa_visible_sum", "wa_beneficiaries_min", "wa_beneficiaries_max",
            "wa_share_min", "wa_share_max", "bound_class",
            "wa_hidden_rows", "nonwa_hidden_rows",
        ]
        all_fields = set().union(*(r.keys() for r in detail_rows))
        fields = [f for f in preferred if f in all_fields]
        fields += sorted(all_fields - set(fields))
        with (evid / "cms_mssp_geographic_beneficiary_bounds_detail_v0_9.csv").open(
            "w", encoding="utf-8", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(detail_rows)

    if period_rows:
        fields = list(period_rows[0].keys())
        with (evid / "cms_mssp_geographic_beneficiary_bounds_period_v0_9.csv").open(
            "w", encoding="utf-8", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(period_rows)

    with (evid / "cms_mssp_geographic_beneficiary_bounds_checks_v0_9.csv").open(
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
