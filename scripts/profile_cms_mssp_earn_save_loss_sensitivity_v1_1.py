#!/usr/bin/env python3
r"""
CMS MSSP EarnSaveLoss Geographic Allocation Sensitivity v1.1

Purpose
-------
Translate the certified beneficiary-geography uncertainty into EarnSaveLoss
financial sensitivity without adopting an allocation estimator or ledger policy.

Inputs are reconstructed from preserved CMS county and financial PUFs using the
same assumption-minimal beneficiary-count bounds as v0.9.

Financial certification performed here
---------------------------------------
* Exact ACO linkage for each participation period.
* EarnSaveLoss field discovery and numeric/blank/non-numeric inventory.
* Positive / negative / zero counts and period totals.
* No blank or non-numeric EarnSaveLoss is silently treated as zero.

Geographic sensitivity
----------------------
For each ACO-period:
  s_L = certified assumption-minimal WA beneficiary-share lower bound
  s_U = certified assumption-minimal WA beneficiary-share upper bound

Endpoint dollar products:
  p_L = EarnSaveLoss * s_L
  p_U = EarnSaveLoss * s_U

Because EarnSaveLoss may be negative:
  dollar_min = min(p_L, p_U)
  dollar_max = max(p_L, p_U)

MODELED_SENSITIVITY_SCENARIO
----------------------------
A central sensitivity scenario is computed only where mathematically defined.

For each ACO with a positive hidden beneficiary residual, distribute that
residual across hidden county observations in proportion to the ACO's visible
beneficiary geography, using the visible WA share among all visible counties.
Equivalently:

  hidden_WA_scenario = residual * visible_WA / visible_all

Then:
  scenario_WA = visible_WA + hidden_WA_scenario
  scenario_share = scenario_WA / N_AB

If visible_all <= 0, or if the scenario falls outside the certified v0.9 bound,
the scenario remains NULL. No fallback is invented.

This scenario is NOT an estimate and is NOT an adopted allocation weight.

Boundaries
----------
* 2015 excluded: original county source artifact not recovered.
* 2016 retained but explicitly flagged UNRESOLVED_HISTORICAL_ENCODING.
* 2019 and 2019A remain separate participation periods.
* '*' is not universally interpreted as 1-10.
* No suppressed county cell is individually imputed.
* No database writes.
* No ledger inclusion decision.
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

VERSION = "v1.1"
WA_STATE_ID = "53"
WA_NAMES = {"washington", "wa"}

COUNTY_REL = Path("data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county")
FIN_REL = Path("data/raw/cms/medicare_aco/mssp_performance_results")
EVID_REL = COUNTY_REL / "validation" / "earn_save_loss_sensitivity_v1_1"

PINNED = {
    2016: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2016_01_01.csv",
    2017: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2017_01_01.csv",
    2018: "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2018_01_01.csv",
}

TOT_AB_ALIASES = ["Tot_AB", "Total assigned beneficiaries"]

@dataclass
class PeriodSource:
    period: str
    year: int
    source_name: str
    fields: list[str]
    rows: list[dict[str, str]]

def root() -> Path:
    starts = [Path.cwd().resolve(), Path(__file__).resolve().parent]
    for s in starts:
        for p in (s, *s.parents):
            if (p / "data").is_dir() and (p / "scripts").is_dir():
                return p
    raise RuntimeError("Repository root not found.")

def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def cnorm(s: str | None) -> str:
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

def lexical(v):
    if v is None or not v.strip():
        return "BLANK"
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
            if x == WA_STATE_ID:
                return True
    return bool(sname and norm(row.get(sname)) in WA_NAMES)

def hidden(period, raw_state):
    # Preserve v0.9 semantics.
    return raw_state == ("BLANK" if period == "2016" else "STAR")

def modern_zip(d):
    scored = []
    for p in d.glob("*.zip"):
        try:
            with zipfile.ZipFile(p) as z:
                ns = [n.lower().replace("\\", "/") for n in z.namelist()]
                sc = sum(any(f"/{y}/" in n and n.endswith(".csv") for n in ns)
                         for y in range(2020, 2025))
                if sc >= 5:
                    scored.append((sc, p))
        except zipfile.BadZipFile:
            pass
    if not scored:
        raise FileNotFoundError("Modern county ZIP not found.")
    return sorted(scored, key=lambda x: (-x[0], str(x[1]).lower()))[0][1]

def member_for_year(z, year, off=False):
    out = []
    for n in z.namelist():
        low = n.lower().replace("\\", "/")
        if not low.endswith(".csv") or str(year) not in low:
            continue
        oc = ("off-cycle" in low or "off_cycle" in low or "2019_07_01" in low)
        if off != oc:
            continue
        sc = ((3 if "beneficiar" in low else 0)
              + (3 if "county" in low else 0)
              + (2 if "puf" in low else 0))
        out.append((sc, n))
    if not out:
        raise FileNotFoundError(f"County member {year}, off={off} not found.")
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
                if (any("2019_01_01" in n for n in ns)
                        and any("2019_07_01" in n for n in ns)):
                    z19 = p
                    break
        except zipfile.BadZipFile:
            pass
    if not z19:
        raise FileNotFoundError("2019 county ZIP not found.")

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
    if not zips:
        raise FileNotFoundError("Financial ZIP not found.")
    scored = []
    for p in zips:
        try:
            with zipfile.ZipFile(p) as z:
                ns = [n.lower() for n in z.namelist()]
                sc = sum(any(str(y) in n and n.endswith(".csv") for n in ns)
                         for y in range(2016, 2025))
                scored.append((sc, p))
        except zipfile.BadZipFile:
            pass
    return sorted(scored, key=lambda x: (-x[0], str(x[1]).lower()))[0][1]

def fin_member(z, period):
    year = period[:4]
    c = []
    for n in z.namelist():
        low = n.lower().replace("\\", "/")
        if not low.endswith(".csv") or year not in low:
            continue
        off = any(t in low for t in ("off-cycle", "off_cycle", "2019a", "2019_07"))
        sc = ((4 if "financial" in low else 0)
              + (2 if "quality" in low else 0)
              + (2 if "performance" in low else 0))
        if period.endswith("A"):
            sc += 8 if off else -5
        else:
            sc += -8 if off else 3
        c.append((sc, n))
    if not c:
        raise FileNotFoundError(f"Financial member not found for {period}")
    return sorted(c, key=lambda x: (-x[0], x[1].lower()))[0][1]

def geo_for_aco(rows, tot_col, period, sid, sname, n_ab):
    visible_all = 0.0
    visible_wa = 0.0
    wa_hidden = 0
    nonwa_hidden = 0
    unexpected = 0

    for r in rows:
        st = lexical(r.get(tot_col))
        wa = is_wa(r, sid, sname)
        if st == "NUMERIC":
            x = num(r.get(tot_col))
            visible_all += x
            if wa:
                visible_wa += x
        elif hidden(period, st):
            if wa: wa_hidden += 1
            else: nonwa_hidden += 1
        elif st in {"DOT", "STAR", "BLANK"}:
            # Expected non-hidden lexical state under the period's encoding.
            pass
        else:
            unexpected += 1

    residual = n_ab - visible_all
    if residual < -1e-8:
        return dict(status="NEGATIVE_RESIDUAL", residual=residual,
                    visible_all=visible_all, visible_wa=visible_wa,
                    wa_hidden=wa_hidden, nonwa_hidden=nonwa_hidden,
                    unexpected=unexpected)

    residual = max(0.0, residual)

    if residual == 0:
        lo = hi = visible_wa
        bound_class = "POINT_ZERO_RESIDUAL"
    elif wa_hidden == 0 and nonwa_hidden > 0:
        lo = hi = visible_wa
        bound_class = "POINT_NO_WA_HIDDEN"
    elif wa_hidden > 0 and nonwa_hidden == 0:
        lo = hi = visible_wa + residual
        bound_class = "POINT_ALL_HIDDEN_WA"
    elif wa_hidden > 0 and nonwa_hidden > 0:
        lo, hi = visible_wa, visible_wa + residual
        bound_class = "INTERVAL_BOTH_WA_AND_NONWA_HIDDEN"
    else:
        return dict(status="UNEXPLAINED_RESIDUAL", residual=residual,
                    visible_all=visible_all, visible_wa=visible_wa,
                    wa_hidden=wa_hidden, nonwa_hidden=nonwa_hidden,
                    unexpected=unexpected)

    s_lo = lo / n_ab if n_ab > 0 else None
    s_hi = hi / n_ab if n_ab > 0 else None

    scenario_share = None
    scenario_wa = None
    scenario_status = "NULL"
    if n_ab > 0 and visible_all > 0:
        hidden_wa = residual * (visible_wa / visible_all)
        scenario_wa = visible_wa + hidden_wa
        scenario_share = scenario_wa / n_ab
        if (s_lo is not None and s_hi is not None
                and s_lo - 1e-12 <= scenario_share <= s_hi + 1e-12):
            scenario_status = "MODELED_SENSITIVITY_SCENARIO"
        else:
            scenario_share = None
            scenario_wa = None
            scenario_status = "NULL_OUTSIDE_CERTIFIED_BOUND"
    elif residual == 0 and n_ab > 0:
        scenario_wa = visible_wa
        scenario_share = visible_wa / n_ab
        scenario_status = "MODELED_SENSITIVITY_SCENARIO"
    else:
        scenario_status = "NULL_VISIBLE_DENOMINATOR_UNAVAILABLE"

    return dict(
        status="OK", residual=residual, visible_all=visible_all,
        visible_wa=visible_wa, wa_hidden=wa_hidden,
        nonwa_hidden=nonwa_hidden, unexpected=unexpected,
        wa_min=lo, wa_max=hi, share_min=s_lo, share_max=s_hi,
        bound_class=bound_class, scenario_wa=scenario_wa,
        scenario_share=scenario_share, scenario_status=scenario_status,
    )

def money(x):
    return "NA" if x is None else f"${x:,.2f}"

def pct(x):
    return "NA" if x is None else f"{100*x:.3f}%"

def main():
    rr = root()
    cd, fd = rr / COUNTY_REL, rr / FIN_REL
    ev = rr / EVID_REL
    ev.mkdir(parents=True, exist_ok=True)

    report = []
    checks = []
    detail = []
    periods_out = []

    def emit(x=""):
        print(x)
        report.append(x)

    def check(code, ok, detail_text):
        status = "PASS" if ok else "FAIL"
        checks.append((code, status, detail_text))
        emit(f"{code}: {status} - {detail_text}")

    emit(f"CMS MSSP EARNSAVELOSS GEOGRAPHIC ALLOCATION SENSITIVITY {VERSION}")
    emit("=" * 118)
    emit("Read-only. Financial-field certification + sensitivity analysis; NOT ledger adoption.")
    emit("Certified beneficiary bounds remain controlling; modeled scenario is not an estimate.")
    emit("2015 excluded. 2016 retained with unresolved historical-encoding caveat.")
    emit("No suppressed county cell is individually imputed. No DB writes.")
    emit()

    cps = county_periods(cd)
    expected = ["2016","2017","2018","2019","2019A","2020","2021","2022","2023","2024"]
    check("PERIODS", [x.period for x in cps] == expected,
          f"periods={[x.period for x in cps]}")

    fzip = financial_zip(fd)
    emit(f"Financial ZIP: {fzip}")
    emit()

    with zipfile.ZipFile(fzip) as z:
        for ps in cps:
            emit(f"{ps.period} FINANCIAL SENSITIVITY")
            emit("-" * 118)

            ac = aco_col(ps.fields)
            sid = state_id_col(ps.fields)
            sname = state_name_col(ps.fields)
            tot = find_col(ps.fields, TOT_AB_ALIASES)
            check(f"{ps.period}-COUNTY-SCHEMA", bool(ac and tot),
                  f"ACO={ac}; Tot_AB={tot}")
            if not ac or not tot:
                emit()
                continue

            byaco = defaultdict(list)
            for r in ps.rows:
                a = (r.get(ac) or "").strip()
                if a:
                    byaco[a].append(r)

            fm = fin_member(z, ps.period)
            ff, fr = read_bytes(z.read(fm))
            fac = aco_col(ff)
            nab_col = find_col(ff, ["N_AB"])
            esl_col = find_col(ff, [
                "EarnSaveLoss", "Earn Save Loss", "Earn_Save_Loss",
                "Earned Savings Loss", "Earned Savings/Loss"
            ])

            check(f"{ps.period}-FIN-SCHEMA",
                  bool(fac and nab_col and esl_col),
                  f"member={fm}; ACO={fac}; N_AB={nab_col}; EarnSaveLoss={esl_col}")
            if not fac or not nab_col or not esl_col:
                emit()
                continue

            fby = {(r.get(fac) or "").strip(): r
                   for r in fr if (r.get(fac) or "").strip()}
            check(f"{ps.period}-ACO-LINK", set(byaco) == set(fby),
                  f"county={len(byaco)}; financial={len(fby)}; "
                  f"intersection={len(set(byaco)&set(fby))}; "
                  f"county_only={len(set(byaco)-set(fby))}; "
                  f"financial_only={len(set(fby)-set(byaco))}")

            esl_states = Counter(lexical(r.get(esl_col)) for r in fby.values())
            nab_states = Counter(lexical(r.get(nab_col)) for r in fby.values())
            check(f"{ps.period}-NAB-NUMERIC",
                  nab_states["NUMERIC"] == len(fby),
                  f"numeric={nab_states['NUMERIC']}/{len(fby)}; "
                  f"blank={nab_states['BLANK']}; other={nab_states['OTHER']}")
            check(f"{ps.period}-EARNSAVELOSS-NUMERIC",
                  esl_states["NUMERIC"] == len(fby),
                  f"numeric={esl_states['NUMERIC']}/{len(fby)}; "
                  f"blank={esl_states['BLANK']}; star={esl_states['STAR']}; "
                  f"dot={esl_states['DOT']}; other={esl_states['OTHER']}")

            vals = [num(r.get(esl_col)) for r in fby.values()]
            numeric_vals = [x for x in vals if x is not None]
            pos = sum(x > 0 for x in numeric_vals)
            neg = sum(x < 0 for x in numeric_vals)
            zero = sum(x == 0 for x in numeric_vals)
            esl_total = sum(numeric_vals)

            bad_geo = 0
            bad_scenario = 0
            scenario_null = 0
            period_min = 0.0
            period_max = 0.0
            period_scenario = 0.0
            scenario_complete = True
            period_abs_esl = 0.0

            for a in sorted(set(byaco) & set(fby)):
                fr0 = fby[a]
                nab = num(fr0.get(nab_col))
                esl = num(fr0.get(esl_col))
                if nab is None or esl is None:
                    continue

                g = geo_for_aco(byaco[a], tot, ps.period, sid, sname, nab)
                if g["status"] != "OK" or g["unexpected"]:
                    bad_geo += 1
                    continue

                p1 = esl * g["share_min"]
                p2 = esl * g["share_max"]
                dmin = min(p1, p2)
                dmax = max(p1, p2)

                dscenario = None
                if g["scenario_share"] is not None:
                    dscenario = esl * g["scenario_share"]
                    if dscenario < dmin - 1e-7 or dscenario > dmax + 1e-7:
                        bad_scenario += 1
                        dscenario = None
                if dscenario is None:
                    scenario_null += 1
                    scenario_complete = False

                period_min += dmin
                period_max += dmax
                if dscenario is not None:
                    period_scenario += dscenario
                period_abs_esl += abs(esl)

                detail.append({
                    "period": ps.period,
                    "year": ps.year,
                    "aco_id": a,
                    "historical_encoding_status":
                        "UNRESOLVED_HISTORICAL_ENCODING" if ps.period == "2016"
                        else "STANDARD_DOCUMENTED_SUPPRESSION_ENCODING",
                    "n_ab": nab,
                    "earn_save_loss": esl,
                    "earn_save_loss_sign":
                        "POSITIVE" if esl > 0 else "NEGATIVE" if esl < 0 else "ZERO",
                    "visible_all_tot_ab": g["visible_all"],
                    "visible_wa_tot_ab": g["visible_wa"],
                    "hidden_residual": g["residual"],
                    "wa_hidden_rows": g["wa_hidden"],
                    "nonwa_hidden_rows": g["nonwa_hidden"],
                    "bound_class": g["bound_class"],
                    "wa_beneficiary_min": g["wa_min"],
                    "wa_beneficiary_max": g["wa_max"],
                    "wa_share_min": g["share_min"],
                    "wa_share_max": g["share_max"],
                    "endpoint_product_at_share_min": p1,
                    "endpoint_product_at_share_max": p2,
                    "wa_dollar_min": dmin,
                    "wa_dollar_max": dmax,
                    "scenario_status": g["scenario_status"],
                    "scenario_wa_beneficiaries": g["scenario_wa"],
                    "scenario_share": g["scenario_share"],
                    "scenario_dollars": dscenario,
                })

            check(f"{ps.period}-GEO-RECONSTRUCTION",
                  bad_geo == 0,
                  f"ACO rows with invalid/unexpected geographic reconstruction={bad_geo}")
            check(f"{ps.period}-SCENARIO-WITHIN-BOUNDS",
                  bad_scenario == 0,
                  f"scenario dollar values outside certified endpoint interval={bad_scenario}")

            width = period_max - period_min
            rel_abs = width / period_abs_esl if period_abs_esl else None
            rel_total = width / abs(esl_total) if esl_total else None

            emit(f"Financial member: {fm}")
            emit(f"EarnSaveLoss inventory: positive={pos}; negative={neg}; zero={zero}; total={money(esl_total)}")
            emit(f"Absolute EarnSaveLoss magnitude: {money(period_abs_esl)}")
            emit(f"Washington certified dollar interval: {money(period_min)} to {money(period_max)}")
            emit(f"Washington certified interval width: {money(width)}")
            emit(f"Width / absolute EarnSaveLoss magnitude: {pct(rel_abs)}")
            emit(f"Width / |net EarnSaveLoss total|: {pct(rel_total)}")
            emit(f"Modeled scenario coverage: {len(byaco)-scenario_null}/{len(byaco)} ACOs")
            emit("Modeled scenario dollars: "
                 + (money(period_scenario) if scenario_complete
                    else f"INCOMPLETE ({scenario_null} NULL ACO scenarios; no fallback)"))
            if ps.period == "2016":
                emit("2016 STATUS: UNRESOLVED_HISTORICAL_ENCODING - sensitivity retained but not promoted to certified allocation.")
            emit()

            periods_out.append({
                "period": ps.period,
                "year": ps.year,
                "aco_count": len(byaco),
                "earn_save_loss_positive_count": pos,
                "earn_save_loss_negative_count": neg,
                "earn_save_loss_zero_count": zero,
                "earn_save_loss_total": esl_total,
                "earn_save_loss_absolute_total": period_abs_esl,
                "wa_dollar_min": period_min,
                "wa_dollar_max": period_max,
                "wa_dollar_interval_width": width,
                "interval_width_over_abs_esl": rel_abs,
                "interval_width_over_abs_net_esl": rel_total,
                "scenario_complete": scenario_complete,
                "scenario_null_aco_count": scenario_null,
                "scenario_dollars": period_scenario if scenario_complete else None,
                "historical_encoding_status":
                    "UNRESOLVED_HISTORICAL_ENCODING" if ps.period == "2016"
                    else "STANDARD_DOCUMENTED_SUPPRESSION_ENCODING",
            })

    emit("INTERPRETIVE BOUNDARY")
    emit("-" * 118)
    emit("Certified dollar endpoints are sensitivity products of EarnSaveLoss and certified beneficiary-share bounds.")
    emit("They are not yet ledger values and do not decide whether EarnSaveLoss is an additive federal inflow.")
    emit("The modeled central scenario is explicitly a sensitivity scenario, NOT an estimate.")
    emit("No midpoint or modeled scenario is adopted as the principal allocation weight.")
    emit("Negative EarnSaveLoss values use min/max of endpoint products so interval ordering remains correct.")
    emit("2015 remains NOT ESTIMATED due to unrecovered county source.")
    emit("2016 remains separately caveated because blank county encoding is unresolved.")
    emit()

    failures = [x for x in checks if x[1] == "FAIL"]
    emit(f"OVERALL PROFILE EXECUTION {VERSION}: {'PASS' if not failures else 'FAIL'}")
    emit(f"Checks: {len(checks)} total; {len(failures)} failed")
    emit(f"Evidence: {ev}")

    (ev / "cms_mssp_earn_save_loss_sensitivity_v1_1.txt").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )

    with (ev / "cms_mssp_earn_save_loss_sensitivity_checks_v1_1.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.writer(f)
        w.writerow(["check_code", "status", "detail"])
        w.writerows(checks)

    if detail:
        fields = list(detail[0].keys())
        with (ev / "cms_mssp_earn_save_loss_sensitivity_detail_v1_1.csv").open(
            "w", newline="", encoding="utf-8"
        ) as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(detail)

    if periods_out:
        fields = list(periods_out[0].keys())
        with (ev / "cms_mssp_earn_save_loss_sensitivity_period_v1_1.csv").open(
            "w", newline="", encoding="utf-8"
        ) as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(periods_out)

    return 0 if not failures else 1

if __name__ == "__main__":
    raise SystemExit(main())
