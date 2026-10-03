#!/usr/bin/env python3
r"""
CMS MSSP Auxiliary Geographic Estimator Feasibility Profile v1.0

Decision question
-----------------
Do the additional county assigned-beneficiary person-year fields contain
independent, usable geographic information that can materially narrow the
certified v0.9 Washington beneficiary-count bounds?

This is a DIAGNOSTIC, not an allocator.

Methodological boundary
-----------------------
* Tot_AB is a beneficiary COUNT measure and is controlled against financial N_AB.
* Tot_AB_Psn_Yrs is a PERSON-YEAR measure and is controlled against financial
  N_AB_Year_PY.
* Enrollment-type county fields (ESRD, DIS, AGDU, AGND) are person-year measures.
* Person-years are not silently converted into beneficiary counts.
* No suppressed cell is imputed.
* No '*' is universally assumed to equal 1-10.
* 2016 blank encoding remains unresolved.
* No EarnSaveLoss or other financial amount is allocated.
* No database writes or ledger decision.

The script asks whether person-year geography supplies an independently tighter
Washington-share interval than the v0.9 beneficiary-count interval, and whether
the enrollment-type person-year fields add any observable geographic coverage
beyond total person-years.

Outputs are evidence for a go/no-go estimator decision, not allocation weights.
"""
from __future__ import annotations

import csv
import io
import math
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

VERSION = "v1.0"
WA_STATE_ID = "53"
WA_NAMES = {"washington", "wa"}

COUNTY_REL = Path("data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county")
FIN_REL = Path("data/raw/cms/medicare_aco/mssp_performance_results")
EVID_REL = COUNTY_REL / "validation" / "estimator_feasibility_v1_0"

PINNED = {
    2016: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2016_01_01.csv",
    2017: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2017_01_01.csv",
    2018: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2018_01_01.csv",
}

ALIASES = {
    "tot_ab": ["Tot_AB", "Total assigned beneficiaries"],
    "tot_py": ["Tot_AB_Psn_Yrs", "Total assigned beneficiary person-years",
               "Total assigned beneficiary person years"],
    "esrd_py": ["AB_Psn_Yrs_ESRD", "ESRD assigned beneficiary person-years",
                "ESRD assigned beneficiary person years"],
    "dis_py": ["AB_Psn_Yrs_DIS", "DISABLED assigned beneficiary person-years",
               "DISABLED assigned beneficiary person years"],
    "agdu_py": ["AB_Psn_Yrs_AGDU", "AGED/DUAL assigned beneficiary person-years",
                "AGED/DUAL assigned beneficiary person years"],
    "agnd_py": ["AB_Psn_Yrs_AGND", "AGED/NON-DUAL assigned beneficiary person-years",
                "AGED/NON-DUAL assigned beneficiary person years"],
}

@dataclass
class PeriodSource:
    period: str
    year: int
    source_name: str
    fields: list[str]
    rows: list[dict[str, str]]

def root():
    starts = [Path.cwd().resolve(), Path(__file__).resolve().parent]
    for s in starts:
        for p in (s, *s.parents):
            if (p / "data").is_dir() and (p / "scripts").is_dir():
                return p
    raise RuntimeError("Repository root not found.")

def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def cnorm(s):
    return re.sub(r"[^a-z0-9]+", "_", norm(s)).strip("_")

def find_col(fields, aliases):
    m = {cnorm(f): f for f in fields}
    for a in aliases:
        if cnorm(a) in m:
            return m[cnorm(a)]
    return None

def num(v):
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

def state(v):
    if v is None or not v.strip(): return "BLANK"
    s = v.strip()
    if s == ".": return "DOT"
    if s == "*": return "STAR"
    if num(s) is not None: return "NUMERIC"
    return "OTHER"

def read_bytes(b):
    r = csv.DictReader(io.StringIO(b.decode("utf-8-sig")))
    return r.fieldnames or [], list(r)

def read_path(p):
    return read_bytes(p.read_bytes())

def aco_col(fields):
    return find_col(fields, ["ACO_ID", "ACO ID", "ACO_Num", "ACO Num"])

def state_id_col(fields):
    return find_col(fields, ["State_ID", "State ID", "State FIPS"])

def state_name_col(fields):
    return find_col(fields, ["State_Name", "State Name", "State"])

def is_wa(row, sid, sname):
    if sid:
        x = (row.get(sid) or "").strip()
        if x:
            if x.isdigit(): x = x.zfill(2)
            if x == WA_STATE_ID: return True
    return bool(sname and norm(row.get(sname)) in WA_NAMES)

def modern_zip(d):
    scored = []
    for p in d.glob("*.zip"):
        try:
            with zipfile.ZipFile(p) as z:
                ns = [n.lower().replace("\\", "/") for n in z.namelist()]
                sc = sum(any(f"/{y}/" in n and n.endswith(".csv") for n in ns)
                         for y in range(2020, 2025))
                if sc >= 5: scored.append((sc, p))
        except zipfile.BadZipFile:
            pass
    if not scored: raise FileNotFoundError("Modern county ZIP not found.")
    return sorted(scored, key=lambda x: (-x[0], str(x[1]).lower()))[0][1]

def member_for_year(z, year, off=False):
    out = []
    for n in z.namelist():
        low = n.lower().replace("\\", "/")
        if not low.endswith(".csv") or str(year) not in low: continue
        oc = ("off-cycle" in low or "off_cycle" in low or "2019_07_01" in low)
        if off != oc: continue
        sc = (3 if "beneficiar" in low else 0) + (3 if "county" in low else 0) + (2 if "puf" in low else 0)
        out.append((sc, n))
    if not out: raise FileNotFoundError(f"County member {year}, off={off} not found.")
    return sorted(out, key=lambda x: (-x[0], x[1].lower()))[0][1]

def county_periods(d):
    out = []
    for y, fn in PINNED.items():
        f, r = read_path(d / fn)
        out.append(PeriodSource(str(y), y, fn, f, r))
    z19 = None
    for p in d.glob("*.zip"):
        try:
            with zipfile.ZipFile(p) as z:
                ns = [n.lower() for n in z.namelist()]
                if any("2019_01_01" in n for n in ns) and any("2019_07_01" in n for n in ns):
                    z19 = p; break
        except zipfile.BadZipFile:
            pass
    if not z19: raise FileNotFoundError("2019 county ZIP not found.")
    with zipfile.ZipFile(z19) as z:
        for per, off in [("2019", False), ("2019A", True)]:
            m = member_for_year(z, 2019, off)
            f, r = read_bytes(z.read(m))
            out.append(PeriodSource(per, 2019, f"{z19.name}::{m}", f, r))
    mz = modern_zip(d)
    with zipfile.ZipFile(mz) as z:
        for y in range(2020, 2025):
            m = member_for_year(z, y, False)
            f, r = read_bytes(z.read(m))
            out.append(PeriodSource(str(y), y, f"{mz.name}::{m}", f, r))
    return out

def financial_zip(d):
    zips = list(d.glob("*.zip"))
    if not zips: raise FileNotFoundError("Financial ZIP not found.")
    scored = []
    for p in zips:
        try:
            with zipfile.ZipFile(p) as z:
                ns = [n.lower() for n in z.namelist()]
                scored.append((sum(any(str(y) in n and n.endswith(".csv") for n in ns)
                                   for y in range(2016, 2025)), p))
        except zipfile.BadZipFile:
            pass
    return sorted(scored, key=lambda x: (-x[0], str(x[1]).lower()))[0][1]

def fin_member(z, period):
    year = period[:4]
    c = []
    for n in z.namelist():
        low = n.lower().replace("\\", "/")
        if not low.endswith(".csv") or year not in low: continue
        off = any(t in low for t in ("off-cycle", "off_cycle", "2019a", "2019_07"))
        sc = (4 if "financial" in low else 0) + (2 if "quality" in low else 0) + (2 if "performance" in low else 0)
        if period.endswith("A"): sc += 8 if off else -5
        else: sc += -8 if off else 3
        c.append((sc, n))
    if not c: raise FileNotFoundError(f"Financial member not found for {period}")
    return sorted(c, key=lambda x: (-x[0], x[1].lower()))[0][1]

def hidden(period, rawstate):
    return rawstate == ("BLANK" if period == "2016" else "STAR")

def metric_profile(rows, col, period, sid, sname):
    result = {}
    for g, pred in [
        ("all", lambda r: True),
        ("wa", lambda r: is_wa(r, sid, sname)),
        ("nonwa", lambda r: not is_wa(r, sid, sname)),
    ]:
        sub = [r for r in rows if pred(r)]
        st = Counter(state(r.get(col)) for r in sub)
        vals = [num(r.get(col)) for r in sub]
        vals = [x for x in vals if x is not None]
        result[f"{g}_visible"] = sum(vals)
        result[f"{g}_numeric"] = st["NUMERIC"]
        result[f"{g}_hidden"] = sum(hidden(period, state(r.get(col))) for r in sub)
        result[f"{g}_star"] = st["STAR"]
        result[f"{g}_dot"] = st["DOT"]
        result[f"{g}_blank"] = st["BLANK"]
        result[f"{g}_other"] = st["OTHER"]
    return result

def residual_bounds(p, control):
    residual = control - p["all_visible"]
    if residual < -1e-8:
        return residual, None, None, "NEGATIVE_RESIDUAL"
    residual = max(0.0, residual)
    hw, hn = p["wa_hidden"], p["nonwa_hidden"]
    if residual == 0:
        lo = hi = p["wa_visible"]; cls = "POINT_ZERO_RESIDUAL"
    elif hw == 0 and hn > 0:
        lo = hi = p["wa_visible"]; cls = "POINT_NO_WA_HIDDEN"
    elif hw > 0 and hn == 0:
        lo = hi = p["wa_visible"] + residual; cls = "POINT_ALL_HIDDEN_WA"
    elif hw > 0 and hn > 0:
        lo = p["wa_visible"]; hi = p["wa_visible"] + residual; cls = "INTERVAL_BOTH_GEO"
    else:
        return residual, None, None, "UNEXPLAINED_RESIDUAL"
    return residual, lo, hi, cls

def pct(x):
    return "NA" if x is None else f"{100*x:.3f}%"

def fnum(x):
    return "NA" if x is None else f"{x:,.3f}"

def main():
    rr = root()
    cd, fd = rr / COUNTY_REL, rr / FIN_REL
    ev = rr / EVID_REL
    ev.mkdir(parents=True, exist_ok=True)
    report, checks, detail, summary = [], [], [], []

    def emit(x=""):
        print(x); report.append(x)
    def check(code, ok, d):
        s = "PASS" if ok else "FAIL"
        checks.append((code, s, d)); emit(f"{code}: {s} - {d}")

    emit(f"CMS MSSP AUXILIARY GEOGRAPHIC ESTIMATOR FEASIBILITY PROFILE {VERSION}")
    emit("=" * 116)
    emit("Read-only diagnostic. No imputation, dollar allocation, DB writes, or ledger decision.")
    emit("Beneficiary counts and person-years remain distinct measurement domains.")
    emit("Person-year geography is tested as independent evidence, not presumed to be a beneficiary-count allocator.")
    emit("2016 blank encoding remains unresolved. 2019 and 2019A remain separate.")
    emit()

    periods = county_periods(cd)
    exp = ["2016","2017","2018","2019","2019A","2020","2021","2022","2023","2024"]
    check("PERIODS", [p.period for p in periods] == exp, f"periods={[p.period for p in periods]}")
    fzip = financial_zip(fd)
    emit(f"Financial ZIP: {fzip}")
    emit()

    with zipfile.ZipFile(fzip) as z:
        for ps in periods:
            emit(f"{ps.period} ESTIMATOR FEASIBILITY")
            emit("-" * 116)
            ac = aco_col(ps.fields); sid = state_id_col(ps.fields); sn = state_name_col(ps.fields)
            cols = {k: find_col(ps.fields, v) for k,v in ALIASES.items()}
            check(f"{ps.period}-COUNTY-SCHEMA", ac is not None and all(cols.values()),
                  f"ACO={ac}; " + "; ".join(f"{k}={v}" for k,v in cols.items()))
            if not ac or not all(cols.values()):
                emit(); continue

            byaco = defaultdict(list)
            for r in ps.rows:
                a = (r.get(ac) or "").strip()
                if a: byaco[a].append(r)

            fm = fin_member(z, ps.period)
            ff, fr = read_bytes(z.read(fm))
            fac = aco_col(ff)
            n_ab = find_col(ff, ["N_AB"])
            n_py = find_col(ff, ["N_AB_Year_PY"])
            subtype_fin = {
                "esrd_py": find_col(ff, ["N_AB_Year_ESRD_PY"]),
                "dis_py": find_col(ff, ["N_AB_Year_DIS_PY"]),
                "agdu_py": find_col(ff, ["N_AB_Year_AGED_Dual_PY"]),
                "agnd_py": find_col(ff, ["N_AB_Year_AGED_NonDual_PY"]),
            }
            check(f"{ps.period}-FIN-CONTROLS", bool(fac and n_ab and n_py),
                  f"member={fm}; ACO={fac}; N_AB={n_ab}; N_AB_Year_PY={n_py}")
            if not fac or not n_ab or not n_py:
                emit(); continue
            fby = {(r.get(fac) or "").strip(): r for r in fr if (r.get(fac) or "").strip()}
            check(f"{ps.period}-ACO-LINK", set(byaco)==set(fby),
                  f"county={len(byaco)}; financial={len(fby)}; intersection={len(set(byaco)&set(fby))}")

            neg_count = neg_py = 0
            unexpl_count = unexpl_py = 0
            py_tighter = py_equal = py_wider = py_incomparable = 0
            wa_extra_numeric = Counter()
            subtype_control_present = sum(v is not None for v in subtype_fin.values())
            subtype_negative = Counter()

            agg = dict(n_ab=0.0, n_py=0.0, count_lo=0.0, count_hi=0.0,
                       py_lo=0.0, py_hi=0.0)
            agg_ok = True

            for a in sorted(set(byaco)&set(fby)):
                row = fby[a]
                nab, npy = num(row.get(n_ab)), num(row.get(n_py))
                metrics = {k: metric_profile(byaco[a], c, ps.period, sid, sn)
                           for k,c in cols.items()}
                rec = {"period": ps.period, "year": ps.year, "aco_id": a,
                       "n_ab": nab, "n_ab_year_py": npy}

                if nab is None or npy is None:
                    agg_ok = False
                    rec["status"] = "NONNUMERIC_CONTROL"
                    detail.append(rec); continue

                cr, clo, chi, cc = residual_bounds(metrics["tot_ab"], nab)
                pr, plo, phi, pc = residual_bounds(metrics["tot_py"], npy)
                if cr < -1e-8: neg_count += 1
                if pr < -1e-8: neg_py += 1
                if cc == "UNEXPLAINED_RESIDUAL": unexpl_count += 1
                if pc == "UNEXPLAINED_RESIDUAL": unexpl_py += 1

                csl = clo/nab if clo is not None and nab else None
                csh = chi/nab if chi is not None and nab else None
                psl = plo/npy if plo is not None and npy else None
                psh = phi/npy if phi is not None and npy else None
                cw = (csh-csl) if csl is not None and csh is not None else None
                pw = (psh-psl) if psl is not None and psh is not None else None
                if cw is None or pw is None:
                    py_incomparable += 1
                elif pw < cw - 1e-12: py_tighter += 1
                elif abs(pw-cw) <= 1e-12: py_equal += 1
                else: py_wider += 1

                # Does an enrollment-type PY field expose a numeric WA cell where total PY is hidden?
                for sk in ("esrd_py","dis_py","agdu_py","agnd_py"):
                    sm = metrics[sk]
                    tm = metrics["tot_py"]
                    # ACO-level count of extra observable WA numeric cells cannot be recovered
                    # from aggregates alone, so inspect source rows directly.
                    scol = cols[sk]; tcol = cols["tot_py"]
                    extra = 0
                    for rr0 in byaco[a]:
                        if is_wa(rr0, sid, sn) and state(rr0.get(scol))=="NUMERIC" and hidden(ps.period, state(rr0.get(tcol))):
                            extra += 1
                    wa_extra_numeric[sk] += extra

                    fc = subtype_fin.get(sk)
                    if fc and num(row.get(fc)) is not None:
                        sr = num(row.get(fc)) - sm["all_visible"]
                        if sr < -1e-8: subtype_negative[sk] += 1

                rec.update({
                    "count_residual": cr, "count_wa_min": clo, "count_wa_max": chi,
                    "count_share_min": csl, "count_share_max": csh,
                    "count_share_width": cw, "count_bound_class": cc,
                    "py_residual": pr, "py_wa_min": plo, "py_wa_max": phi,
                    "py_share_min": psl, "py_share_max": psh,
                    "py_share_width": pw, "py_bound_class": pc,
                    "py_interval_tighter_than_count": (pw is not None and cw is not None and pw < cw-1e-12),
                })
                for sk in ("esrd_py","dis_py","agdu_py","agnd_py"):
                    rec[f"{sk}_wa_visible"] = metrics[sk]["wa_visible"]
                    rec[f"{sk}_wa_hidden_rows"] = metrics[sk]["wa_hidden"]
                detail.append(rec)

                if None in (clo,chi,plo,phi):
                    agg_ok=False
                else:
                    agg["n_ab"] += nab; agg["n_py"] += npy
                    agg["count_lo"] += clo; agg["count_hi"] += chi
                    agg["py_lo"] += plo; agg["py_hi"] += phi

            check(f"{ps.period}-COUNT-RESIDUAL", neg_count==0 and unexpl_count==0,
                  f"negative={neg_count}; unexplained={unexpl_count}")
            check(f"{ps.period}-PY-RESIDUAL", neg_py==0 and unexpl_py==0,
                  f"negative={neg_py}; unexplained={unexpl_py}")

            subtype_diag = "; ".join(
                f"{k}:fin={subtype_fin[k] or 'NONE'},negative={subtype_negative[k]},extra_WA_numeric={wa_extra_numeric[k]}"
                for k in ("esrd_py","dis_py","agdu_py","agnd_py")
            )
            emit(f"Financial member: {fm}")
            emit(f"Subtype financial controls present: {subtype_control_present}/4")
            emit(f"Subtype diagnostics: {subtype_diag}")
            emit(f"ACO-level interval comparison: PY tighter={py_tighter}; equal={py_equal}; wider={py_wider}; incomparable={py_incomparable}")

            if agg_ok and agg["n_ab"] and agg["n_py"]:
                c_lo, c_hi = agg["count_lo"]/agg["n_ab"], agg["count_hi"]/agg["n_ab"]
                p_lo, p_hi = agg["py_lo"]/agg["n_py"], agg["py_hi"]/agg["n_py"]
                emit(f"Aggregate beneficiary-count WA share bound: {pct(c_lo)} to {pct(c_hi)}; width={pct(c_hi-c_lo)}")
                emit(f"Aggregate person-year WA share bound:       {pct(p_lo)} to {pct(p_hi)}; width={pct(p_hi-p_lo)}")
                emit(f"Person-year interval narrower by:           {pct((c_hi-c_lo)-(p_hi-p_lo))}")
                summary.append({
                    "period": ps.period, "aco_count": len(byaco),
                    "count_share_min": c_lo, "count_share_max": c_hi,
                    "count_share_width": c_hi-c_lo,
                    "py_share_min": p_lo, "py_share_max": p_hi,
                    "py_share_width": p_hi-p_lo,
                    "py_width_improvement": (c_hi-c_lo)-(p_hi-p_lo),
                    "aco_py_tighter": py_tighter, "aco_equal": py_equal,
                    "aco_py_wider": py_wider, "aco_incomparable": py_incomparable,
                    "subtype_controls_present": subtype_control_present,
                    "extra_wa_numeric_esrd": wa_extra_numeric["esrd_py"],
                    "extra_wa_numeric_dis": wa_extra_numeric["dis_py"],
                    "extra_wa_numeric_agdu": wa_extra_numeric["agdu_py"],
                    "extra_wa_numeric_agnd": wa_extra_numeric["agnd_py"],
                })
            emit()

    # Conservative go/no-go classification. This does NOT authorize an estimator.
    comparable = [r for r in summary if r["period"] != "2016"]
    material = [r for r in comparable if r["py_width_improvement"] > 0.0025]  # >0.25 percentage point
    consistent = len(material) >= max(1, math.ceil(0.75 * len(comparable))) if comparable else False
    extra_any = any(
        r[k] > 0 for r in comparable
        for k in ("extra_wa_numeric_esrd","extra_wa_numeric_dis","extra_wa_numeric_agdu","extra_wa_numeric_agnd")
    )

    emit("GO / NO-GO DIAGNOSTIC")
    emit("-" * 116)
    emit("This classification concerns whether auxiliary fields merit further estimator design; it does NOT authorize allocation.")
    emit(f"Post-2016 periods with >0.25 percentage-point narrower PY interval: {len(material)}/{len(comparable)}")
    emit(f"Enrollment-type fields expose any extra numeric WA cells beyond hidden total-PY cells: {'YES' if extra_any else 'NO'}")
    if consistent or extra_any:
        decision = "GO_FOR_LIMITED_ESTIMATOR_REVIEW"
        rationale = "Auxiliary person-year information shows potentially material independent geographic information."
    else:
        decision = "NO_GO_AUXILIARY_FIELDS_DO_NOT_MATERIALLY_NARROW_IDENTIFICATION"
        rationale = "Auxiliary person-year information does not consistently provide material independent narrowing."
    emit(f"DIAGNOSTIC RESULT: {decision}")
    emit(f"Rationale: {rationale}")
    emit()
    emit("INTERPRETIVE BOUNDARY")
    emit("-" * 116)
    emit("A narrower person-year interval is not automatically a beneficiary-count interval.")
    emit("Enrollment-type person-years are not converted to beneficiary counts.")
    emit("No midpoint, visible share, person-year share, or subtype share is authorized as an EarnSaveLoss allocation weight.")
    emit("No suppressed county value was imputed. No financial amount was allocated.")
    emit("2016 remains subject to its unresolved blank-encoding caveat.")
    emit()

    failures = [x for x in checks if x[1]=="FAIL"]
    emit(f"OVERALL PROFILE EXECUTION {VERSION}: {'PASS' if not failures else 'FAIL'}")
    emit(f"Checks: {len(checks)} total; {len(failures)} failed")
    emit(f"Evidence: {ev}")

    (ev/"cms_mssp_estimator_feasibility_v1_0.txt").write_text("\n".join(report)+"\n", encoding="utf-8")
    with (ev/"cms_mssp_estimator_feasibility_checks_v1_0.csv").open("w", newline="", encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["check_code","status","detail"]); w.writerows(checks)
    if detail:
        fs=sorted(set().union(*(r.keys() for r in detail)))
        with (ev/"cms_mssp_estimator_feasibility_detail_v1_0.csv").open("w", newline="", encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=fs); w.writeheader(); w.writerows(detail)
    if summary:
        fs=list(summary[0].keys())
        with (ev/"cms_mssp_estimator_feasibility_period_v1_0.csv").open("w", newline="", encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=fs); w.writeheader(); w.writerows(summary)

    return 0 if not failures else 1

if __name__ == "__main__":
    raise SystemExit(main())
