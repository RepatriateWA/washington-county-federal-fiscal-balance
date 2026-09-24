#!/usr/bin/env python3
"""Memory-safe CMS Part D CPSC linkage profiler v0.3.

Scope: Washington, Jan 2015-Sep 2024 (117 months).

Key change from v0.2: source indexing retains metadata only. Selected monthly
CPSC files are streamed one at a time and released. No full CSV corpus is held
in memory.

READ ONLY: no payment reconstruction, imputation, DB writes, or ledger inclusion.
RDS remains out of scope.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, re, sys, zipfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import openpyxl

START=(2015,1); END=(2024,9)
PAYMENT_FIELDS={"CONTRACT_NUMBER","PLAN_BENEFIT_PACKAGE","CONTRACT_NAME",
"ORGANIZATION_TYPE","AVERAGE_PART_D_DIRECT_SUBSIDY_PM_PM_PAYMENT",
"AVERAGE_PART_D_RISK_SCORE","AVERAGE_REINSURANCE_PM_PM_PAYMENT",
"AVERAGE_LOW_INCOME_COST_SHARING_PM_PM_PAYMENT"}
REQ={"contract":{"CONTRACT_NUMBER","CONTRACT_ID","CONTRACT"},
"pbp":{"PLAN_ID","PLAN_BENEFIT_PACKAGE","PBP","PLAN_BENEFIT_PACKAGE_ID"},
"state":{"STATE","STATE_ABBREVIATION","STATE_ABBR"},
"county":{"COUNTY","COUNTY_NAME"},
"enrollment":{"ENROLLMENT","ENROLLMENT_COUNT","ENROLLEES"}}
OPT={"plan_type":{"PLAN_TYPE","PLAN_TYPE_DESCRIPTION"},
"organization_type":{"ORGANIZATION_TYPE","ORG_TYPE"}}
MONTHS={1:("JAN","JANUARY"),2:("FEB","FEBRUARY"),3:("MAR","MARCH"),
4:("APR","APRIL"),5:("MAY",),6:("JUN","JUNE"),7:("JUL","JULY"),
8:("AUG","AUGUST"),9:("SEP","SEPT","SEPTEMBER"),10:("OCT","OCTOBER"),
11:("NOV","NOVEMBER"),12:("DEC","DECEMBER")}

def clean(v): return "" if v is None else str(v).strip()
def norm(v):
    return re.sub(r"[^A-Z0-9]+","_",clean(v).upper().replace("/"," ")).strip("_")
def pbp(v):
    s=clean(v)
    if not s:return ""
    try:return f"{int(float(s)):03d}"
    except:return s.upper()
def enrollment(v):
    s=clean(v).replace(",","")
    if re.fullmatch(r"\d+",s): return int(s),"NUMERIC"
    return None,"NONNUMERIC"
def month_iter():
    y,m=START
    while (y,m)<=END:
        yield y,m
        m+=1
        if m==13:y,m=y+1,1
def sha_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def sha_member(p,n):
    h=hashlib.sha256()
    with zipfile.ZipFile(p) as z, z.open(n) as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()

def infer_date(text):
    u=text.upper(); c=re.sub(r"[^A-Z0-9]","",u)
    a={(int(y),int(m)) for y,m in re.findall(r"(20(?:1[4-9]|2[0-4]))(0[1-9]|1[0-2])",c)}
    if len(a)==1:return (*next(iter(a)),"YYYYMM")
    a={(int(y),int(m)) for m,y in re.findall(r"(0[1-9]|1[0-2])(20(?:1[4-9]|2[0-4]))",c)}
    if len(a)==1:return (*next(iter(a)),"MMYYYY")
    ys={int(x) for x in re.findall(r"20(?:1[4-9]|2[0-4])",u)}
    ms={m for m,names in MONTHS.items() if any(re.search(rf"(?<![A-Z]){n}(?![A-Z])",u) for n in names)}
    if len(ys)==len(ms)==1:return next(iter(ys)),next(iter(ms)),"YEAR_MONTH_NAME"
    return None,None,"UNRESOLVED"

@contextmanager
def text_source(path,member=None):
    if path.suffix.lower()==".zip":
        z=zipfile.ZipFile(path); raw=z.open(member)
        t=io.TextIOWrapper(raw,encoding="utf-8-sig",errors="replace",newline="")
        try:yield t
        finally:t.close(); z.close()
    else:
        f=path.open("r",encoding="utf-8-sig",errors="replace",newline="")
        try:yield f
        finally:f.close()

def header_info(path,member):
    with text_source(path,member) as f:
        sample=f.read(8192)
        delim=max([",","\t","|"],key=lambda x:sample.count(x))
        f.seek(0); r=csv.reader(f,delimiter=delim)
        for rn,row in enumerate(r,1):
            if rn>50:break
            h=[norm(x) for x in row]; mp={}; ok=True
            for k,aliases in REQ.items():
                pos=next((h.index(a) for a in aliases if a in h),None)
                if pos is None:ok=False;break
                mp[k]=pos
            if ok:
                for k,aliases in OPT.items():
                    mp[k]=next((h.index(a) for a in aliases if a in h),None)
                return rn,mp,delim
    return None,None,None

def build_index(root):
    out=[]; scanned=0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".zip",".csv",".txt"}:continue
        parts={x.lower() for x in path.parts}
        if "validation" in parts or "plan_payment" in parts:continue
        scanned+=1
        if path.suffix.lower()==".zip":
            try:
                with zipfile.ZipFile(path) as z:
                    members=[n for n in z.namelist() if Path(n).suffix.lower() in {".csv",".txt"}]
            except:continue
        else:members=[None]
        for member in members:
            try:rn,mp,d=header_info(path,member)
            except:continue
            if rn is None:continue
            y,m,method=infer_date(f"{path} {member or path.name}")
            out.append({"path":path,"member":member,"year":y,"month":m,
                        "method":method,"header":rn,"map":mp,"delim":d})
    return out,scanned

def choose(idx,y,m):
    a=[x for x in idx if x["year"]==y and x["month"]==m]
    def rank(x):
        s=re.sub(r"[^a-z0-9]","",f"{x['path']} {x['member'] or ''}".lower())
        score=(1000 if "cpsc" in s else 0)+(1000 if "contractplanstatecounty" in s else 0)+(100 if "enrollment" in s else 0)
        if "snp" in s:score-=500
        if "scc" in s and "cpsc" not in s:score-=500
        return -score,str(x["path"]),(x["member"] or "")
    a.sort(key=rank)
    return (a[0] if a else None),a

def wa_rows(src):
    with text_source(src["path"],src["member"]) as f:
        r=csv.reader(f,delimiter=src["delim"]); mp=src["map"]
        for rn,row in enumerate(r,1):
            if rn<=src["header"]:continue
            def g(k):
                i=mp.get(k); return row[i] if i is not None and i<len(row) else ""
            if clean(g("state")).upper() not in {"WA","WASHINGTON"}:continue
            yield {"contract":clean(g("contract")).upper(),"pbp":pbp(g("pbp")),
                   "county":clean(g("county")),"enrollment":clean(g("enrollment")),
                   "plan_type":clean(g("plan_type")),"org":clean(g("organization_type"))}

def classify_payment(v):
    s=clean(v)
    if not s:return "BLANK"
    try:x=float(s.replace(",","").replace("$",""))
    except:return "NONNUMERIC_OTHER"
    if x>0:return "NUMERIC_POSITIVE"
    if x<0:return "NUMERIC_NEGATIVE"
    return "NUMERIC_ZERO"

def payment_keys(root,y):
    found=[]
    for zpath in sorted((root/str(y)).glob("*.zip")):
        try:
            with zipfile.ZipFile(zpath) as z:
                for n in z.namelist():
                    b=Path(n).name.lower().replace(" ","")
                    if b.endswith(".xlsx") and "partdplans" in b and "recon" not in b:
                        data=z.read(n); found.append((zpath,n,data,hashlib.sha256(data).hexdigest()))
        except:pass
    if not found:raise RuntimeError(f"{y}: PartDPlans workbook not found")
    if len({x[3] for x in found})!=1:raise RuntimeError(f"{y}: conflicting PartDPlans workbook bytes")
    zp,n,data,mhash=sorted(found,key=lambda x:(str(x[0]),x[1]))[0]
    wb=openpyxl.load_workbook(io.BytesIO(data),data_only=True,read_only=True)
    try:
        for ws in wb.worksheets:
            for hr,row in enumerate(ws.iter_rows(min_row=1,max_row=30,values_only=True),1):
                h=[norm(x) for x in row]
                if not PAYMENT_FIELDS.issubset(set(h)):continue
                pos={k:h.index(k) for k in PAYMENT_FIELDS}; keys={}; dups=[]
                for vals in ws.iter_rows(min_row=hr+1,values_only=True):
                    def v(k):
                        i=pos[k]; return vals[i] if i<len(vals) else None
                    key=(clean(v("CONTRACT_NUMBER")).upper(),pbp(v("PLAN_BENEFIT_PACKAGE")))
                    if not all(key):continue
                    classes={
                        "DIRECT_SUBSIDY":classify_payment(v("AVERAGE_PART_D_DIRECT_SUBSIDY_PM_PM_PAYMENT")),
                        "RISK_SCORE":classify_payment(v("AVERAGE_PART_D_RISK_SCORE")),
                        "REINSURANCE":classify_payment(v("AVERAGE_REINSURANCE_PM_PM_PAYMENT")),
                        "LICS":classify_payment(v("AVERAGE_LOW_INCOME_COST_SHARING_PM_PM_PAYMENT")),
                    }
                    rec={"name":clean(v("CONTRACT_NAME")),"org":clean(v("ORGANIZATION_TYPE")),
                         "classes":classes,
                         "missing_fields":";".join(k for k,x in classes.items() if x in {"BLANK","NONNUMERIC_OTHER"})}
                    rec["has_missing_input"]=bool(rec["missing_fields"])
                    rec["pattern"]="|".join(f"{k}={classes[k]}" for k in ("DIRECT_SUBSIDY","RISK_SCORE","REINSURANCE","LICS"))
                    if key in keys:dups.append(key)
                    else:keys[key]=rec
                return keys,dups,{"zip_path":str(zp),"zip_sha256":sha_file(zp),
                    "member_name":n,"member_sha256":mhash,"sheet_name":ws.title,"header_row":hr}
    finally:wb.close()
    raise RuntimeError(f"{y}: PartDPlans semantic table not found")

def write_csv(p,rows,fields):
    with p.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cpsc-root",type=Path,default=Path("data/raw/cms/medicare_advantage"))
    ap.add_argument("--plan-payment-root",type=Path,default=Path("data/raw/cms/medicare_advantage/plan_payment"))
    ap.add_argument("--output-dir",type=Path,default=Path("data/raw/cms/medicare_partd/validation/partd_payment_missingness_wa_exposure_v0_2"))
    a=ap.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
    errors=[];warnings=[]
    print("="*78)
    print("CMS PART D — WA EXPOSURE TO MISSING PAYMENT INPUTS v0.2")
    print("="*78)
    print()
    print("BOUNDARY:")
    print("  Certified v0.3 CPSC source-selection/parsing mechanics reused.")
    print("  Measurement only: no blank-to-zero conversion, imputation, payment")
    print("  reconstruction, database writes, or ledger inclusion.")
    print()
    print("Building metadata-only CPSC source index...",flush=True)
    idx,scanned=build_index(a.cpsc_root)
    print(f"Scanned {scanned:,} candidate files; admitted {len(idx):,} CPSC-like members.",flush=True)

    pkeys={}; pmanifest=[]; dups=[]
    for y in range(2015,2025):
        try:
            k,d,meta=payment_keys(a.plan_payment_root,y);pkeys[y]=k
            pmanifest.append({"payment_year":y,"payment_key_count":len(k),**meta})
            dups += [{"payment_year":y,"contract":x[0],"pbp":x[1]} for x in d]
        except Exception as e:
            errors.append(f"PartDPlans CY{y}: {e}");pkeys[y]={}

    monthly=[]; manifest=[]; detail=[]; field_mm=Counter(); pattern_mm=Counter()
    for y,m in month_iter():
        print(f"{y}-{m:02d}: starting...",flush=True)
        src,cands=choose(idx,y,m)
        if not src:
            errors.append(f"{y}-{m:02d}: no indexed CPSC source resolved")
            monthly.append({"year":y,"month":m,"source_status":"MISSING","wa_rows":0,
                "numeric_enrollment":0,"exact_payment_match_numeric_enrollment":0,
                "complete_input_numeric_enrollment":0,"missing_input_numeric_enrollment":0,
                "no_exact_payment_match_numeric_enrollment":0,"nonnumeric_rows":0,
                "exact_match_accounting_difference":0,"numeric_accounting_difference":0})
            continue
        hashes=[]
        for c in cands:
            try:hashes.append(sha_member(c["path"],c["member"]) if c["path"].suffix.lower()==".zip" else sha_file(c["path"]))
            except Exception as e:warnings.append(f"{y}-{m:02d}: candidate hash error: {e}")
        if len(set(hashes))>1:warnings.append(f"{y}-{m:02d}: {len(cands)} candidates / {len(set(hashes))} distinct hashes")
        sh=sha_member(src["path"],src["member"]) if src["path"].suffix.lower()==".zip" else sha_file(src["path"])
        manifest.append({"year":y,"month":m,"selected_path":str(src["path"]),
            "selected_member":src["member"] or "","selected_source_sha256":sh,
            "date_inference_method":src["method"],"candidate_count":len(cands),
            "distinct_candidate_hashes":len(set(hashes))})
        keys=pkeys[y]; wr=tot=match=complete=miss=no=nonnum=0
        try:
            for r in wa_rows(src):
                wr+=1;n,status=enrollment(r["enrollment"]);key=(r["contract"],r["pbp"])
                if status!="NUMERIC":
                    nonnum+=1;continue
                tot+=n
                rec=keys.get(key)
                if rec is None:
                    no+=n;continue
                match+=n
                if rec["has_missing_input"]:
                    miss+=n
                    for fld in rec["missing_fields"].split(";"):
                        if fld:field_mm[(y,fld)]+=n
                    pattern_mm[(y,rec["pattern"])]+=n
                    detail.append({"year":y,"month":m,"contract":key[0],"pbp":key[1],
                        "cpsc_plan_type":r["plan_type"],"cpsc_organization_type":r["org"],
                        "payment_organization_type":rec["org"],"numeric_enrollment":n,
                        "missing_fields":rec["missing_fields"],"missingness_pattern":rec["pattern"]})
                else:complete+=n
        except Exception as e:
            errors.append(f"{y}-{m:02d}: streaming parse failed: {e}");continue
        monthly.append({"year":y,"month":m,"source_status":"PARSED","wa_rows":wr,
            "numeric_enrollment":tot,"exact_payment_match_numeric_enrollment":match,
            "complete_input_numeric_enrollment":complete,"missing_input_numeric_enrollment":miss,
            "no_exact_payment_match_numeric_enrollment":no,"nonnumeric_rows":nonnum,
            "exact_match_accounting_difference":match-complete-miss,
            "numeric_accounting_difference":tot-match-no})
        print(f"{y}-{m:02d}: complete | WA numeric={tot:,} | exact={match:,} | complete={complete:,} | missing-input={miss:,} | no-exact={no:,}",flush=True)

    parsed=sum(r["source_status"]=="PARSED" for r in monthly)
    total=sum(r["numeric_enrollment"] for r in monthly)
    match=sum(r["exact_payment_match_numeric_enrollment"] for r in monthly)
    complete=sum(r["complete_input_numeric_enrollment"] for r in monthly)
    miss=sum(r["missing_input_numeric_enrollment"] for r in monthly)
    no=sum(r["no_exact_payment_match_numeric_enrollment"] for r in monthly)
    nonnum=sum(r["nonnumeric_rows"] for r in monthly)
    ediff=sum(r["exact_match_accounting_difference"] for r in monthly)
    ndiff=sum(r["numeric_accounting_difference"] for r in monthly)

    annual=[]
    for y in range(2015,2025):
        rr=[r for r in monthly if r["year"]==y]
        annual.append({"year":y,"coverage":"JAN-SEP" if y==2024 else "JAN-DEC",
            "numeric_enrollment":sum(r["numeric_enrollment"] for r in rr),
            "exact_payment_match_numeric_enrollment":sum(r["exact_payment_match_numeric_enrollment"] for r in rr),
            "complete_input_numeric_enrollment":sum(r["complete_input_numeric_enrollment"] for r in rr),
            "missing_input_numeric_enrollment":sum(r["missing_input_numeric_enrollment"] for r in rr),
            "no_exact_payment_match_numeric_enrollment":sum(r["no_exact_payment_match_numeric_enrollment"] for r in rr),
            "nonnumeric_rows":sum(r["nonnumeric_rows"] for r in rr)})

    checks=[
        ("All 117 required CPSC months resolved and parsed",parsed==117,f"{parsed}/117"),
        ("All 10 PartDPlans years resolved",len(pmanifest)==10,f"{len(pmanifest)}/10"),
        ("Certified WA numeric CPSC enrollment regression control",total==111380906,f"{total:,} == 111,380,906"),
        ("Certified exact PartDPlans match regression control",match==106176965,f"{match:,} == 106,176,965"),
        ("Certified no-exact-payment-match regression control",no==5203941,f"{no:,} == 5,203,941"),
        ("Exact-match missingness accounting identity",ediff==0,f"difference={ediff:,}"),
        ("Total numeric enrollment accounting identity",ndiff==0,f"difference={ndiff:,}"),
        ("No duplicate annual Part D payment keys",not dups,f"duplicates={len(dups)}"),
        ("No processing/source errors",not errors,f"errors={len(errors)}"),
    ]
    overall=all(ok for _,ok,_ in checks)

    write_csv(a.output_dir/"cms_partd_wa_missing_input_exposure_monthly_v0_2.csv",monthly,
        ["year","month","source_status","wa_rows","numeric_enrollment","exact_payment_match_numeric_enrollment",
         "complete_input_numeric_enrollment","missing_input_numeric_enrollment","no_exact_payment_match_numeric_enrollment",
         "nonnumeric_rows","exact_match_accounting_difference","numeric_accounting_difference"])
    write_csv(a.output_dir/"cms_partd_wa_missing_input_exposure_annual_v0_2.csv",annual,
        ["year","coverage","numeric_enrollment","exact_payment_match_numeric_enrollment","complete_input_numeric_enrollment",
         "missing_input_numeric_enrollment","no_exact_payment_match_numeric_enrollment","nonnumeric_rows"])
    write_csv(a.output_dir/"cms_partd_wa_missing_input_exposure_detail_v0_2.csv",detail,
        ["year","month","contract","pbp","cpsc_plan_type","cpsc_organization_type","payment_organization_type",
         "numeric_enrollment","missing_fields","missingness_pattern"])
    write_csv(a.output_dir/"cms_partd_wa_missing_input_exposure_by_field_v0_2.csv",
        [{"year":y,"field":f,"member_months":n} for (y,f),n in sorted(field_mm.items())],
        ["year","field","member_months"])
    write_csv(a.output_dir/"cms_partd_wa_missing_input_exposure_patterns_v0_2.csv",
        [{"year":y,"missingness_pattern":p,"member_months":n} for (y,p),n in sorted(pattern_mm.items())],
        ["year","missingness_pattern","member_months"])
    write_csv(a.output_dir/"cms_partd_cpsc_source_manifest_v0_2.csv",manifest,
        ["year","month","selected_path","selected_member","selected_source_sha256","date_inference_method","candidate_count","distinct_candidate_hashes"])
    write_csv(a.output_dir/"cms_partd_payment_source_manifest_v0_2.csv",pmanifest,
        ["payment_year","payment_key_count","zip_path","zip_sha256","member_name","member_sha256","sheet_name","header_row"])
    write_csv(a.output_dir/"cms_partd_wa_missing_input_exposure_checks_v0_2.csv",
        [{"check":n,"status":"PASS" if ok else "FAIL","detail":d} for n,ok,d in checks],
        ["check","status","detail"])
    write_csv(a.output_dir/"cms_partd_wa_missing_input_exposure_errors_v0_2.csv",
        [{"message":e} for e in errors],["message"])

    print()
    print("SOURCE RESOLUTION:")
    print(f"  Candidate files scanned once: {scanned:,}")
    print(f"  Required CPSC months parsed: {parsed}/117")
    print(f"  PartDPlans years resolved: {len(pmanifest)}/10")
    print()
    print("WASHINGTON NUMERIC ENROLLMENT:")
    print(f"  Total numeric enrollment:             {total:,}")
    print(f"  Exact PartDPlans match:               {match:,}")
    print(f"    Complete payment inputs:            {complete:,}")
    print(f"    >=1 missing payment input:          {miss:,}")
    print(f"  No exact PartDPlans match:            {no:,}")
    print(f"  Suppressed/non-numeric rows:          {nonnum:,}")
    print(f"  Exact-match accounting difference:    {ediff:,}")
    print(f"  Numeric accounting difference:        {ndiff:,}")
    print()
    print("ANNUAL WA EXPOSURE:")
    for r in annual:
        print(f"  CY{r['year']} {r['coverage']}: numeric={r['numeric_enrollment']:,} | exact={r['exact_payment_match_numeric_enrollment']:,} | complete={r['complete_input_numeric_enrollment']:,} | missing-input={r['missing_input_numeric_enrollment']:,} | no-exact={r['no_exact_payment_match_numeric_enrollment']:,}")
    print()
    print("MISSING-INPUT MEMBER-MONTH EXPOSURE BY FIELD:")
    rows=[(y,f,n) for (y,f),n in sorted(field_mm.items())]
    if rows:
        for y,f,n in rows:print(f"  CY{y} {f:<16} {n:,}")
    else:print("  NONE")
    print()
    print("CHECKS:")
    for n,ok,d in checks:print(f"  [{'PASS' if ok else 'FAIL'}] {n} — {d}")
    if warnings:
        print();print(f"WARNINGS: {len(warnings)}")
        for x in warnings[:30]:print(f"  {x}")
    if errors:
        print();print(f"ERRORS: {len(errors)}")
        for x in errors[:30]:print(f"  {x}")
    print()
    print(f"Output directory: {a.output_dir}")
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    print()
    print("NOTE:")
    print("  Nonzero missing-input exposure does not cause FAIL.")
    print("  PASS certifies certified-CPSC regression controls and exposure accounting only.")
    print("  No missing-value substitution rule is authorized.")
    return 0 if overall else 1

if __name__=="__main__":sys.exit(main())
