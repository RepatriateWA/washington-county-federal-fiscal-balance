#!/usr/bin/env python3
"""WCFFBP: Medicare Trustees revision materiality profiler v0.1 (read-only)."""
from __future__ import annotations
import csv, math
from collections import defaultdict
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"data"/"raw"/"cms"/"medicare_trustees"/"validation"
OBS=BASE/"source_determined_revision_profile_v0_4"/"trustees_source_determined_observations.csv"
SER=BASE/"source_determined_revision_profile_v0_4"/"trustees_source_determined_series_summary.csv"
CERT=BASE/"status_boundary_certification_v0_2"/"trustees_status_boundary_certification.csv"
OUT=BASE/"revision_materiality_v0_1"
YEARS=set(range(2015,2025)); TABLES={"IV.C2","IV.C3"}; LATEST=2026
KEY=["table_id","observation_year","accounting_scope","plan_type_normalized","component_normalized","unit","basis"]

def rd(p):
    with p.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))
def wr(p,rows,fields):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)
def ii(x):
    try:return int(float(str(x).strip()))
    except:return None
def ff(x):
    try:
        v=float(str(x).strip().replace(",","").replace("$",""))
        return v if math.isfinite(v) else None
    except:return None
def qs(vals):
    a=sorted(abs(x) for x in vals if math.isfinite(x))
    if not a:return ("","","")
    def q(p):return a[round((len(a)-1)*p)]
    return median(a),q(.9),max(a)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    missing=[p for p in (OBS,SER,CERT) if not p.exists()]
    if missing:
        print("FAIL: missing required input(s)");[print(p) for p in missing];return 1
    obs,series,cert=rd(OBS),rd(SER),rd(CERT)
    c26=next((r for r in cert if ii(r.get("trustees_vintage"))==LATEST),None)
    through=ii(c26.get("source_determined_through_year")) if c26 else None
    status=c26.get("resolution_status","") if c26 else ""
    bykey=defaultdict(list)
    for r in obs:
        if ii(r.get("observation_year")) in YEARS and r.get("table_id") in TABLES:
            bykey[tuple(str(r.get(k,"")) for k in KEY)].append(r)
    detail=[]; errors=[]
    for s in series:
        y=ii(s.get("observation_year"))
        if y not in YEARS or s.get("table_id") not in TABLES:continue
        k=tuple(str(s.get(d,"")) for d in KEY)
        rows=sorted(bykey.get(k,[]),key=lambda r:ii(r.get("trustees_vintage")) or -1)
        if not rows:
            errors.append({"table_id":s.get("table_id",""),"observation_year":y,"plan_type_normalized":s.get("plan_type_normalized",""),"component_normalized":s.get("component_normalized",""),"error":"No matching observations"});continue
        a,b=rows[0],rows[-1]; av,bv=ff(a.get("value")),ff(b.get("value"))
        if av is None or bv is None:continue
        changes=[]
        for x,z in zip(rows,rows[1:]):
            xv,zv=ff(x.get("value")),ff(z.get("value"))
            if xv is not None and zv is not None and not math.isclose(xv,zv,rel_tol=0,abs_tol=1e-12):
                changes.append(ii(z.get("trustees_vintage")))
        lv=ii(b.get("trustees_vintage")); last=max([x for x in changes if x is not None],default=None)
        pct="" if av==0 else (bv-av)/av*100
        has26=any(ii(r.get("trustees_vintage"))==LATEST for r in rows)
        detail.append({**{d:s.get(d,"") for d in KEY},
          "first_source_determined_vintage":ii(a.get("trustees_vintage")),"latest_source_determined_vintage":lv,
          "first_source_determined_value":av,"latest_source_determined_value":bv,
          "net_revision_amount":bv-av,"net_revision_percent":pct,"absolute_net_revision_amount":abs(bv-av),
          "absolute_net_revision_percent":"" if pct=="" else abs(pct),"changed_revision_steps":len(changes),
          "last_change_vintage":"" if last is None else last,
          "changed_in_latest_observed_vintage":"YES" if last==lv else "NO",
          "vintages_after_last_change":"" if last is None else lv-last,
          "latest_preserved_2026_observation_present":"YES" if has26 else "NO",
          "latest_preserved_2026_source_determined_for_year":"YES" if status=="SOURCE_RESOLVED" and through is not None and y<=through else "NO",
          "preferred_vintage":"UNASSIGNED","selection_policy":"UNASSIGNED"})
    groups=defaultdict(list)
    for r in detail:
        groups[(r["table_id"],r["component_normalized"])].append(r);groups[(r["table_id"],"ALL_COMPONENTS")].append(r)
    agg=[]
    for (t,c),rr in sorted(groups.items()):
        pa=[float(r["absolute_net_revision_percent"]) for r in rr if r["absolute_net_revision_percent"]!=""]
        aa=[float(r["absolute_net_revision_amount"]) for r in rr]; mp,p90p,maxp=qs(pa);ma,p90a,maxa=qs(aa)
        rev=[r for r in rr if r["changed_revision_steps"]>0]; late=[r for r in rr if r["changed_in_latest_observed_vintage"]=="YES"]
        agg.append({"table_id":t,"component_normalized":c,"series_count":len(rr),"series_revised_after_first_source_determined":len(rev),
          "revision_rate_percent":100*len(rev)/len(rr),"series_changed_in_latest_observed_vintage":len(late),
          "median_absolute_net_revision_amount":ma,"p90_absolute_net_revision_amount":p90a,"max_absolute_net_revision_amount":maxa,
          "median_absolute_net_revision_percent":mp,"p90_absolute_net_revision_percent":p90p,"max_absolute_net_revision_percent":maxp})
    elig=[]
    for y in sorted(YEARS):
      for t in sorted(TABLES):
        rr=[r for r in detail if ii(r["observation_year"])==y and r["table_id"]==t]
        if rr:
          p=sum(r["latest_preserved_2026_observation_present"]=="YES" for r in rr); e=sum(r["latest_preserved_2026_source_determined_for_year"]=="YES" for r in rr)
          elig.append({"observation_year":y,"table_id":t,"series_count":len(rr),"series_with_2026_observation":p,"series_without_2026_observation":len(rr)-p,
            "series_for_which_2026_is_source_determined":e,"all_series_have_2026_observation":"YES" if p==len(rr) else "NO",
            "2026_source_status_covers_control_year":"YES" if e==len(rr) else "NO"})
    df=KEY+["first_source_determined_vintage","latest_source_determined_vintage","first_source_determined_value","latest_source_determined_value","net_revision_amount","net_revision_percent","absolute_net_revision_amount","absolute_net_revision_percent","changed_revision_steps","last_change_vintage","changed_in_latest_observed_vintage","vintages_after_last_change","latest_preserved_2026_observation_present","latest_preserved_2026_source_determined_for_year","preferred_vintage","selection_policy"]
    af=["table_id","component_normalized","series_count","series_revised_after_first_source_determined","revision_rate_percent","series_changed_in_latest_observed_vintage","median_absolute_net_revision_amount","p90_absolute_net_revision_amount","max_absolute_net_revision_amount","median_absolute_net_revision_percent","p90_absolute_net_revision_percent","max_absolute_net_revision_percent"]
    ef=["observation_year","table_id","series_count","series_with_2026_observation","series_without_2026_observation","series_for_which_2026_is_source_determined","all_series_have_2026_observation","2026_source_status_covers_control_year"]
    wr(OUT/"trustees_revision_materiality_series.csv",detail,df);wr(OUT/"trustees_revision_materiality_by_table_component.csv",agg,af);wr(OUT/"trustees_latest_vintage_2026_eligibility.csv",elig,ef)
    wr(OUT/"trustees_revision_materiality_errors.csv",errors,["table_id","observation_year","plan_type_normalized","component_normalized","error"])
    checks=[("v0.4 observations loaded",bool(obs)),("v0.4 series summary loaded",bool(series)),("2026 certification row present",c26 is not None),("2026 certification is SOURCE_RESOLVED",status=="SOURCE_RESOLVED"),("2026 source-determined boundary covers CY2024",through is not None and through>=2024),("Both IV.C2 and IV.C3 represented",{r["table_id"] for r in detail}==TABLES),("CY2015-CY2024 represented",{ii(r["observation_year"]) for r in detail}==YEARS),("No profiler errors",not errors)]
    overall=all(x[1] for x in checks); revised=sum(r["changed_revision_steps"]>0 for r in detail); late=sum(r["changed_in_latest_observed_vintage"]=="YES" for r in detail); p26=sum(r["latest_preserved_2026_observation_present"]=="YES" for r in detail)
    lines=["="*120,"CMS MEDICARE TRUSTEES REVISION MATERIALITY + LATEST-VINTAGE ELIGIBILITY PROFILE v0.1","="*120,"","READ-ONLY FINAL TRUSTEES-METHODOLOGY PROFILER","preferred_vintage = UNASSIGNED","selection_policy = UNASSIGNED","",f"Source-determined series analyzed             : {len(detail):,}",f"Series revised after first source-determined  : {revised:,}",f"Series unchanged after first source-determined: {len(detail)-revised:,}",f"Series changed in latest observed vintage     : {late:,}",f"Series with a 2026 source-determined obs      : {p26:,}",f"Series without a 2026 observation             : {len(detail)-p26:,}",f"2026 certified source-determined through year : {through}",f"Profiler errors                               : {len(errors):,}","","TABLE / COMPONENT MATERIALITY","-"*120]
    for r in agg: lines.append(f"{r['table_id']} {r['component_normalized']}: series={r['series_count']} revised={r['series_revised_after_first_source_determined']} changed-latest={r['series_changed_in_latest_observed_vintage']} median-|net %|={r['median_absolute_net_revision_percent']} p90-|net %|={r['p90_absolute_net_revision_percent']} max-|net %|={r['max_absolute_net_revision_percent']}")
    lines+=["","2026 ELIGIBILITY / PRESENCE BY CONTROL YEAR AND TABLE","-"*120]
    for r in elig: lines.append(f"CY{r['observation_year']} {r['table_id']}: series={r['series_count']} 2026-present={r['series_with_2026_observation']} 2026-missing={r['series_without_2026_observation']} source-status-covers-year={r['2026_source_status_covers_control_year']}")
    lines+=["","VALIDATION CHECKS","-"*120]+[f"{'PASS' if ok else 'FAIL'}  {lab}" for lab,ok in checks]+["",f"OVERALL PROFILER STATUS: {'PASS' if overall else 'FAIL'}","","PASS measures revision materiality and latest-vintage eligibility only.","It does NOT establish a preferred-vintage policy or authorize WA reconciliation/ledger inclusion.","Next gate: explicit preferred-vintage policy decision, then Washington-vs-Trustees reconciliation."]
    text="\n".join(lines)+"\n";(OUT/"trustees_revision_materiality_summary.txt").write_text(text,encoding="utf-8");print(text);return 0 if overall else 1
if __name__=="__main__":raise SystemExit(main())
