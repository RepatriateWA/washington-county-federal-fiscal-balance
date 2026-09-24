#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,io,re,sys,zipfile
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import openpyxl
ARCHIVE=Path("data/raw/cms/medicare_partd/landscape/cy2006-cy2025-landscape-files.zip")
OUT=Path("data/raw/cms/medicare_partd/landscape/validation/landscape_semantic_profile_v0_1")
YEARS=tuple(range(2015,2025)); MAX_DEPTH=5
def s(x): return "" if x is None else str(x).strip()
def n(x): return re.sub(r"[^A-Z0-9]+","_",s(x).upper()).strip("_")
def annual_year(name):
    m=re.match(r"^(?:CY)?(20(?:1[5-9]|2[0-4]))(?:\D|$)",Path(name).name,re.I)
    return int(m.group(1)) if m else None
def decode(data):
    for enc in ("utf-8-sig","cp1252","latin-1"):
        try: text=data.decode(enc); break
        except UnicodeDecodeError: pass
    sample=text[:65536]
    try: dialect=csv.Sniffer().sniff(sample,delimiters=",|\t;")
    except csv.Error: dialect=csv.excel
    return list(csv.reader(io.StringIO(text,newline=""),dialect))
def tables(name,data):
    ext=Path(name).suffix.lower()
    if ext in {".csv",".txt",".tsv"}:
        raw=decode(data)
        if not raw:return []
        cand=[]
        for i,row in enumerate(raw[:50]):
            v=[s(x) for x in row]; cand.append((sum(map(bool,v)),sum(bool(x) and not x.replace(".","",1).isdigit() for x in v),i,v))
        _,_,i,h=max(cand)
        while h and not h[-1]:h.pop()
        return [("",h,[r[:len(h)] for r in raw[i+1:] if any(s(x) for x in r)])]
    if ext in {".xlsx",".xlsm"}:
        wb=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True); out=[]
        try:
            for ws in wb.worksheets:
                raw=list(ws.iter_rows(values_only=True))
                if not raw:continue
                cand=[]
                for i,row in enumerate(raw[:50]):
                    v=[s(x) for x in row]; cand.append((sum(map(bool,v)),sum(bool(x) and not x.replace(".","",1).isdigit() for x in v),i,v))
                _,_,i,h=max(cand)
                while h and not h[-1]:h.pop()
                out.append((ws.title,h,[list(r[:len(h)]) for r in raw[i+1:] if any(s(x) for x in r)]))
        finally: wb.close()
        return out
    return []
def role(f):
    z=n(f)
    if z in {"CONTRACT","CONTRACT_ID","CONTRACT_NUMBER","CONTRACTID"} or ("CONTRACT" in z and "NAME" not in z):return "CONTRACT"
    if z in {"PBP","PBP_ID","PLAN_ID","PLANID","PLAN_BENEFIT_PACKAGE","PLAN_BENEFIT_PACKAGE_ID"}:return "PLAN_PBP"
    if any(k in z for k in ("DRUG_BENEFIT","PART_D","PARTD","PRESCRIPTION_DRUG","DRUG_COVERAGE","DRUG_PREMIUM","DRUG_DEDUCTIBLE","STAR_RATING_PART_D","NATIONAL_PDP")):return "PARTD_EXPLICIT"
    if z in {"PLAN_TYPE","TYPE_OF_MEDICARE_HEALTH_PLAN","ORGANIZATION_TYPE","SPECIAL_NEEDS_PLAN","SPECIAL_NEEDS_PLAN_TYPE"}:return "PLAN_TYPE_CONTEXT"
    return ""
def category(name):
    u=name.upper()
    if "PLAN AND PREMIUM" in u or "PLAN_PREMIUM" in u or "508_" in u:return "PLAN_PREMIUM_PARTD_PRODUCT"
    if re.search(r"(?:^|[^A-Z])PDP(?:[^A-Z]|$)",u):return "PDP_LANDSCAPE"
    if re.search(r"(?:^|[^A-Z])SNP(?:[^A-Z]|$)",u):return "SNP_LANDSCAPE"
    if re.search(r"(?:^|[^A-Z])MMP(?:[^A-Z]|$)",u):return "MMP_LANDSCAPE"
    if "LANDSCAPE_MA" in u or re.search(r"(?:^|[^A-Z])MA_(?:ATO|NTO|SANCTION)",u):return "MA_LANDSCAPE"
    return "OTHER"
def write(path,rows,fields):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--archive",type=Path,default=ARCHIVE);ap.add_argument("--output-dir",type=Path,default=OUT)
    a=ap.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
    sem=[];vals=[];summ=[];errs=[];annual=Counter();tc=Counter()
    def rec(blob,y,chain,d):
        if d>MAX_DEPTH: raise RuntimeError("maximum recursion depth exceeded")
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            bad=z.testzip()
            if bad:raise RuntimeError("nested ZIP integrity failure: "+bad)
            for inf in z.infolist():
                if inf.is_dir():continue
                name=inf.filename; ext=Path(name).suffix.lower()
                try:
                    b=z.read(inf)
                    if ext==".zip":rec(b,y,chain+" -> "+name,d+1)
                    elif ext in {".csv",".txt",".tsv",".xlsx",".xlsm"}:
                        cat=category(name)
                        for sh,h,rows in tables(name,b):
                            tc[y]+=1; rs=[role(x) for x in h]
                            con=[h[i] for i,r in enumerate(rs) if r=="CONTRACT"]; plan=[h[i] for i,r in enumerate(rs) if r=="PLAN_PBP"]
                            exp=[h[i] for i,r in enumerate(rs) if r=="PARTD_EXPLICIT"]; ctx=[h[i] for i,r in enumerate(rs) if r=="PLAN_TYPE_CONTEXT"]
                            summ.append(dict(year=y,file_category=cat,member_name=name,sheet_name=sh,row_count=len(rows),contract_fields=" | ".join(con),plan_pbp_fields=" | ".join(plan),explicit_partd_fields=" | ".join(exp),plan_type_context_fields=" | ".join(ctx),has_contract="YES" if con else "NO",has_plan_pbp="YES" if plan else "NO",has_explicit_partd="YES" if exp else "NO"))
                            for i,f in enumerate(h):
                                r=rs[i]
                                if not r:continue
                                c=Counter(s(row[i]) if i<len(row) else "" for row in rows)
                                sem.append(dict(year=y,file_category=cat,member_name=name,sheet_name=sh,field_name=f,field_role=r,row_count=len(rows),nonblank_count=sum(v for k,v in c.items() if k),distinct_nonblank_values=sum(1 for k in c if k)))
                                if r in {"PARTD_EXPLICIT","PLAN_TYPE_CONTEXT"}:
                                    for v,cnt in c.most_common():
                                        if v:vals.append(dict(year=y,file_category=cat,member_name=name,sheet_name=sh,field_name=f,field_role=r,value=v,count=cnt))
                except Exception as e:errs.append(dict(year=y,source=chain+" -> "+name,error=f"{type(e).__name__}: {e}"))
    if not a.archive.exists() or not zipfile.is_zipfile(a.archive):print("ERROR: archive missing/not ZIP",file=sys.stderr);return 2
    with zipfile.ZipFile(a.archive) as z:
        outer_bad=z.testzip()
        for inf in z.infolist():
            if inf.is_dir():continue
            y=annual_year(inf.filename)
            if y not in YEARS:continue
            annual[y]+=1
            try:rec(z.read(inf),y,Path(inf.filename).name,1)
            except Exception as e:errs.append(dict(year=y,source=inf.filename,error=f"{type(e).__name__}: {e}"))
    ys=[]
    for y in YEARS:
        x=[q for q in summ if q["year"]==y]; ids=[q for q in x if q["has_contract"]=="YES" and q["has_plan_pbp"]=="YES"]
        ys.append(dict(year=y,annual_packages=annual[y],tables_profiled=tc[y],tables_with_contract_and_plan_pbp=len(ids),tables_with_contract_plan_pbp_and_explicit_partd=sum(q["has_explicit_partd"]=="YES" for q in ids),partd_product_tables_with_contract_plan_pbp=sum(q["file_category"] in {"PLAN_PREMIUM_PARTD_PRODUCT","PDP_LANDSCAPE"} for q in ids)))
    checks=[("outer archive ZIP integrity",outer_bad is None),("exactly one annual package each CY2015-CY2024",all(annual[y]==1 for y in YEARS)),("all years have profiled tables",all(tc[y]>0 for y in YEARS)),("all years expose Contract + Plan/PBP together in >=1 table",all(any(q["year"]==y and q["has_contract"]=="YES" and q["has_plan_pbp"]=="YES" for q in summ) for y in YEARS)),("all years expose a Part-D-oriented product with Contract + Plan/PBP",all(any(q["year"]==y and q["has_contract"]=="YES" and q["has_plan_pbp"]=="YES" and q["file_category"] in {"PLAN_PREMIUM_PARTD_PRODUCT","PDP_LANDSCAPE"} for q in summ) for y in YEARS)),("no semantic-profile errors",not errs)]
    write(a.output_dir/"cms_partd_landscape_semantic_fields.csv",sem,["year","file_category","member_name","sheet_name","field_name","field_role","row_count","nonblank_count","distinct_nonblank_values"])
    write(a.output_dir/"cms_partd_landscape_semantic_values.csv",vals,["year","file_category","member_name","sheet_name","field_name","field_role","value","count"])
    write(a.output_dir/"cms_partd_landscape_table_semantic_summary.csv",summ,["year","file_category","member_name","sheet_name","row_count","contract_fields","plan_pbp_fields","explicit_partd_fields","plan_type_context_fields","has_contract","has_plan_pbp","has_explicit_partd"])
    write(a.output_dir/"cms_partd_landscape_year_semantic_summary.csv",ys,["year","annual_packages","tables_profiled","tables_with_contract_and_plan_pbp","tables_with_contract_plan_pbp_and_explicit_partd","partd_product_tables_with_contract_plan_pbp"])
    write(a.output_dir/"cms_partd_landscape_semantic_errors.csv",errs,["year","source","error"])
    L=["CMS MEDICARE PART D LANDSCAPE SEMANTIC PROFILE v0.1","="*76,f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",f"Archive: {a.archive}","","BOUNDARY","-"*76,"Evidence profiling only. No Contract+PBP is classified as Part D here.","No use of another year or sibling PBP to infer status. No payment propagation,","imputation, reconstruction, DB writes, or ledger inclusion.","","YEAR EVIDENCE SUMMARY","-"*76]
    for x in ys:L.append(f"CY{x['year']}: tables={x['tables_profiled']}, Contract+Plan/PBP tables={x['tables_with_contract_and_plan_pbp']}, with explicit Part-D fields={x['tables_with_contract_plan_pbp_and_explicit_partd']}, Part-D-product Contract+Plan/PBP tables={x['partd_product_tables_with_contract_plan_pbp']}")
    L+=["","CHECKS","-"*76]+[f"{k}: {'PASS' if v else 'FAIL'}" for k,v in checks]+["","ERRORS","-"*76]+(["None"] if not errs else [f"CY{x['year']} | {x['source']} | {x['error']}" for x in errs])+["","INTERPRETIVE BOUNDARY","-"*76,"A PASS means the Landscape archive exposes reproducible same-year plan-level","evidence suitable for designing a later Contract+PBP status validator.","It does NOT itself establish a status rule or classify unmatched enrollment.","","OVERALL","-"*76,f"OVERALL: {'PASS' if all(v for _,v in checks) else 'FAIL'}"]
    report="\n".join(L)+"\n";(a.output_dir/"cms_partd_landscape_semantic_profile_report.txt").write_text(report,encoding="utf-8");print(report);print(f"Outputs: {a.output_dir}")
    return 0 if all(v for _,v in checks) else 1
if __name__=="__main__":sys.exit(main())
