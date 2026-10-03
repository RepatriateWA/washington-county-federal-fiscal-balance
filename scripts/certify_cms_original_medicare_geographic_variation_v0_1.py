#!/usr/bin/env python
"""CMS Original Medicare Geographic Variation source certification v0.1.
Read-only: no DB writes, allocation, Trustees scaling, or ledger treatment.
"""
from __future__ import annotations
import csv, hashlib
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/"data"/"raw"/"cms"/"medicare_geographic_variation"
SRC=RAW/"2014-2024 Original Medicare Geographic Variation Public Use File.csv"
OUT=RAW/"validation"/"source_v0_1"
YEARS=range(2015,2025)
FIELDS=["BENES_TOTAL_CNT","BENES_WTH_PTAPTB_CNT","BENES_OM_CNT","BENES_MA_CNT",
"TOT_MDCR_PYMT_AMT","TOT_MDCR_STDZD_PYMT_AMT","IP_MDCR_PYMT_AMT","OP_MDCR_PYMT_AMT",
"SNF_MDCR_PYMT_AMT","IRF_MDCR_PYMT_AMT","LTCH_MDCR_PYMT_AMT","HH_MDCR_PYMT_AMT",
"HOSPC_MDCR_PYMT_AMT","PTB_OTHR_SRVCS_MDCR_PYMT_AMT"]
TOK={"","NA","*","."}

def num(x):
    x=(x or "").strip()
    if x in TOK:return None
    try:return Decimal(x)
    except InvalidOperation:return None

def lex(x):
    x=(x or "").strip()
    if not x:return "BLANK"
    if x=="NA":return "NA"
    if x=="*":return "STAR"
    if x==".":return "DOT"
    try: Decimal(x); return "NUMERIC"
    except InvalidOperation:return "OTHER"

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest().upper()

def main():
    if not SRC.exists(): raise SystemExit(f"ERROR source missing: {SRC}")
    OUT.mkdir(parents=True,exist_ok=True)
    counts=Counter(); states=defaultdict(list); counties=defaultdict(list); lx=defaultdict(Counter)
    with SRC.open(encoding="utf-8-sig",newline="") as f:
        rd=csv.DictReader(f); cols=rd.fieldnames or []
        req={"YEAR","BENE_GEO_LVL","BENE_GEO_DESC","BENE_GEO_CD","BENE_AGE_LVL",*FIELDS}
        miss=sorted(req-set(cols))
        if miss: raise SystemExit("ERROR missing columns: "+", ".join(miss))
        for r in rd:
            try:y=int(r["YEAR"])
            except:continue
            counts[y]+=1
            if y not in YEARS or r["BENE_AGE_LVL"].strip()!="All":continue
            lvl=r["BENE_GEO_LVL"].strip(); code=r["BENE_GEO_CD"].strip()
            if lvl=="State" and code=="53":states[y].append(r)
            if lvl=="County" and len(code)==5 and code.startswith("53"):
                counties[y].append(r)
                for c in cols:lx[(y,c)][lex(r.get(c,""))]+=1

    checks=[]; rec=[]; detail=[]
    def ck(n,ok,d):checks.append((n,"PASS" if ok else "FAIL",d))
    ck("source_year_min",min(counts)==2014,f"observed={min(counts)} expected=2014")
    ck("source_year_max",max(counts)==2024,f"observed={max(counts)} expected=2024")
    ck("study_years_present",all(y in counts for y in YEARS),"FY2015-FY2024")
    for y in YEARS:
        ss=states[y]; cc=counties[y]; codes=[r["BENE_GEO_CD"].strip() for r in cc]
        ck(f"{y}_wa_state_all_unique",len(ss)==1,f"rows={len(ss)}")
        ck(f"{y}_wa_county_all_count",len(cc)==39,f"rows={len(cc)} expected=39")
        ck(f"{y}_wa_county_fips_unique",len(set(codes))==39,f"distinct={len(set(codes))} expected=39")
        if len(ss)!=1:continue
        s=ss[0]
        for fld in FIELDS:
            sv=num(s[fld]); vals=[num(r[fld]) for r in cc]; good=[v for v in vals if v is not None]
            sm=sum(good,Decimal(0)); missing=len(vals)-len(good); delta=None if sv is None else sm-sv
            exact=sv is not None and len(cc)==39 and missing==0 and delta==0
            ck(f"{y}_{fld}_county_to_state_exact",exact,f"state={sv} county_sum={sm} delta={delta} missing={missing}")
            rec.append({"year":y,"field":fld,"state_value":"" if sv is None else str(sv),
            "county_numeric_count":len(good),"county_missing_count":missing,"county_sum":str(sm),
            "county_minus_state":"" if delta is None else str(delta),"exact_reconciliation":"PASS" if exact else "FAIL"})
        for r in sorted(cc,key=lambda z:z["BENE_GEO_CD"]):
            detail.append({"year":y,"county_fips":r["BENE_GEO_CD"],"county_desc":r["BENE_GEO_DESC"],
            "benes_total_cnt":r["BENES_TOTAL_CNT"],"benes_om_cnt":r["BENES_OM_CNT"],"benes_ma_cnt":r["BENES_MA_CNT"],
            "tot_mdcr_pymt_amt":r["TOT_MDCR_PYMT_AMT"],"tot_mdcr_stdzd_pymt_amt":r["TOT_MDCR_STDZD_PYMT_AMT"]})

    with (OUT/"checks.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(["check","status","detail"]);w.writerows(checks)
    with (OUT/"reconciliation.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rec[0]));w.writeheader();w.writerows(rec)
    with (OUT/"wa_county_all_detail.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(detail[0]));w.writeheader();w.writerows(detail)
    lexrows=[]
    for (y,fld),c in sorted(lx.items()):
        lexrows.append({"year":y,"field":fld,"numeric":c["NUMERIC"],"na":c["NA"],"star":c["STAR"],"dot":c["DOT"],"blank":c["BLANK"],"other":c["OTHER"]})
    with (OUT/"wa_county_lexical_inventory.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(lexrows[0]));w.writeheader();w.writerows(lexrows)

    passed=sum(s=="PASS" for _,s,_ in checks); failed=len(checks)-passed
    lines=["="*100,"CMS ORIGINAL MEDICARE GEOGRAPHIC VARIATION SOURCE CERTIFICATION v0.1","="*100,
    "Read-only certification. No DB writes, allocation, Trustees scaling, or ledger treatment.","",
    f"Source: {SRC}",f"Bytes: {SRC.stat().st_size:,}",f"SHA256: {digest(SRC)}",f"Columns: {len(cols)}",
    f"Observed years: {min(counts)}-{max(counts)}","","SOURCE ROW COUNTS","-"*100]
    lines += [f"{y}: {counts[y]:,}" for y in sorted(counts)]
    lines += ["","WASHINGTON ALL-AGE GEOGRAPHY","-"*100]
    for y in YEARS: lines.append(f"{y}: state rows={len(states[y])}; county rows={len(counties[y])}; distinct county FIPS={len(set(r['BENE_GEO_CD'].strip() for r in counties[y]))}")
    lines += ["","WASHINGTON COUNTY -> STATE RECONCILIATION","-"*100]
    for y in YEARS:
        lines.append(f"\n{y}")
        for r in [x for x in rec if x["year"]==y]:
            lines.append(f"  {r['field']:<34} {r['exact_reconciliation']:<4} state={r['state_value']:<18} county_sum={r['county_sum']:<18} delta={r['county_minus_state']:<16} missing={r['county_missing_count']}")
    lines += ["","CHECK SUMMARY","-"*100,f"Checks: {len(checks)}",f"PASS:   {passed}",f"FAIL:   {failed}"]
    if failed:
        lines += ["","FAILED CHECKS"]
        lines += [f"  {n}: {d}" for n,s,d in checks if s=="FAIL"]
    lines += ["","INTERPRETIVE BOUNDARY","-"*100,
    "* Source structure and mathematical reconciliation only.",
    "* Actual *_MDCR_PYMT_AMT fields remain distinct from standardized payment fields.",
    "* BENES_MA_CNT does not make Original Medicare payment fields Medicare Advantage payments.",
    "* NA, *, ., blank, and other lexical states are inventoried; none is silently converted to zero.",
    "* No county allocation model, Trustees scaling, accounting additivity decision, or ledger value is created.","",
    f"OVERALL SOURCE CERTIFICATION v0.1: {'PASS' if failed==0 else 'FAIL'}"]
    txt="\n".join(lines)+"\n";(OUT/"report.txt").write_text(txt,encoding="utf-8");print(txt);print(f"Evidence written to: {OUT}")
    return 0 if failed==0 else 1
if __name__=="__main__":raise SystemExit(main())
