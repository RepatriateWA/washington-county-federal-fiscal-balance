#!/usr/bin/env python3
"""Acquire and inventory official CMS State Health Expenditure Accounts (SHEA),
State-of-Residence files for an independent Medicare Advantage control investigation.

Read-only with respect to existing repository data: downloads/preserves official CMS
artifacts, hashes them, inventories ZIP/spreadsheet contents, and searches for semantic
terms. Performs no reconciliation, reconstruction, imputation, or database writes.
"""
from __future__ import annotations
import csv, hashlib, io, re, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path
try:
    import openpyxl
except ImportError:
    openpyxl=None
try:
    import xlrd
except ImportError:
    xlrd=None

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"data"/"raw"/"cms"/"state_health_expenditures"/"residence"
SOURCE=BASE/"source"; DOC=BASE/"documentation"; VAL=BASE/"validation"
LANDING="https://www.cms.gov/data-research/statistics-trends-and-reports/national-health-expenditure-data/state-residence"
ARTIFACTS=[
 ("RESIDENCE_ESTIMATES","SOURCE",
  "https://www.cms.gov/research-statistics-data-and-systems/statistics-trends-and-reports/nationalhealthexpenddata/downloads/resident-state-estimates.zip",
  "resident-state-estimates.zip"),
 ("STATE_DSM","DOCUMENTATION",
  "https://www.cms.gov/research-statistics-data-and-systems/statistics-trends-and-reports/nationalhealthexpenddata/downloads/state-dsm-14.zip",
  "state-dsm-14.zip"),
]
TERMS=["medicare","managed care","medicare advantage","advantage","part c","capitated",
       "capitation","hmo","ppo","enrollment","enrollee","source of funds",
       "source of funding","washington"]
UA="WCFFBP-CMS-SHEA-Acquisition/0.1"

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def write_csv(path,rows,fields):
    with path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def acquire(aid,role,url,name):
    d=SOURCE if role=="SOURCE" else DOC; path=d/name
    row=dict(artifact_id=aid,role=role,source_url=url,local_path=str(path.relative_to(ROOT)),
             acquired_utc=datetime.now(timezone.utc).isoformat(),status="",bytes="",sha256="",
             content_type="",last_modified="",etag="",error="")
    try:
        if path.exists(): row["status"]="PREEXISTING"
        else:
            req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
            with urllib.request.urlopen(req,timeout=120) as r:
                data=r.read(); path.write_bytes(data); row["status"]="DOWNLOAD"
                row["content_type"]=r.headers.get("Content-Type","")
                row["last_modified"]=r.headers.get("Last-Modified",""); row["etag"]=r.headers.get("ETag","")
        if not zipfile.is_zipfile(path): raise ValueError("Artifact is not a valid ZIP")
        row["bytes"]=path.stat().st_size; row["sha256"]=sha(path)
    except Exception as e:
        row["status"]="ERROR"; row["error"]=f"{type(e).__name__}: {e}"
    return row

def search(value,aid,member,sheet,loc,hits,count):
    s=re.sub(r"\s+"," ",str(value)).strip()
    low=s.lower()
    for term in TERMS:
        key=(sheet,term)
        if term in low and count.get(key,0)<25:
            hits.append(dict(artifact_id=aid,member_name=member,sheet_name=sheet,
                             location=loc,search_term=term,matched_text=s[:2000]))
            count[key]=count.get(key,0)+1

def profile_xlsx(data,aid,member):
    prof=[]; hits=[]
    if openpyxl is None:
        return [dict(artifact_id=aid,member_name=member,sheet_name="",rows_observed="",
                     columns_observed="",cells_scanned=0,status="SKIPPED_OPENPYXL_NOT_INSTALLED",error="")],[]
    wb=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True)
    for ws in wb.worksheets:
        count={}; scanned=0; mr=mc=0; status="PROFILED"
        search(ws.title,aid,member,ws.title,"SHEET_NAME",hits,count)
        stop=False
        for ri,row in enumerate(ws.iter_rows(values_only=True),1):
            mr=ri
            for ci,v in enumerate(row,1):
                if v is None: continue
                scanned+=1; mc=max(mc,ci); search(v,aid,member,ws.title,f"R{ri}C{ci}",hits,count)
                if scanned>=250000: status="PROFILED_SCAN_LIMIT_REACHED"; stop=True; break
            if stop: break
        prof.append(dict(artifact_id=aid,member_name=member,sheet_name=ws.title,
                         rows_observed=mr,columns_observed=mc,cells_scanned=scanned,status=status,error=""))
    wb.close(); return prof,hits

def profile_xls(data,aid,member):
    prof=[]; hits=[]
    if xlrd is None:
        return [dict(artifact_id=aid,member_name=member,sheet_name="",rows_observed="",
                     columns_observed="",cells_scanned=0,status="SKIPPED_XLRD_NOT_INSTALLED",error="")],[]
    b=xlrd.open_workbook(file_contents=data)
    for sh in b.sheets():
        count={}; scanned=0; status="PROFILED"; search(sh.name,aid,member,sh.name,"SHEET_NAME",hits,count); stop=False
        for r in range(sh.nrows):
            for c in range(sh.ncols):
                v=sh.cell_value(r,c)
                if v in ("",None): continue
                scanned+=1; search(v,aid,member,sh.name,f"R{r+1}C{c+1}",hits,count)
                if scanned>=250000: status="PROFILED_SCAN_LIMIT_REACHED"; stop=True; break
            if stop: break
        prof.append(dict(artifact_id=aid,member_name=member,sheet_name=sh.name,
                         rows_observed=sh.nrows,columns_observed=sh.ncols,cells_scanned=scanned,status=status,error=""))
    return prof,hits

def main():
    for d in (SOURCE,DOC,VAL): d.mkdir(parents=True,exist_ok=True)
    print("="*92); print("CMS SHEA STATE-OF-RESIDENCE ACQUISITION / INVENTORY v0.1"); print("="*92)
    print("No reconciliation, reconstruction, imputation, or database writes are performed.\n")
    arts=[acquire(*a) for a in ARTIFACTS]
    write_csv(VAL/"cms_shea_residence_acquisition_manifest.csv",arts,
              ["artifact_id","role","source_url","local_path","acquired_utc","status","bytes","sha256",
               "content_type","last_modified","etag","error"])
    inv=[]; prof=[]; hits=[]; errors=[]
    for a in arts:
        if a["status"]=="ERROR": continue
        path=ROOT/a["local_path"]
        with zipfile.ZipFile(path) as z:
            for i in z.infolist():
                if i.is_dir(): continue
                ext=Path(i.filename).suffix.lower()
                inv.append(dict(artifact_id=a["artifact_id"],role=a["role"],zip_path=a["local_path"],
                                member_name=i.filename,member_bytes=i.file_size,compressed_bytes=i.compress_size,
                                crc32=f"{i.CRC:08x}",extension=ext))
                if ext not in (".xlsx",".xls",".xlsm"): continue
                try:
                    data=z.read(i)
                    p,h=profile_xls(data,a["artifact_id"],i.filename) if ext==".xls" else profile_xlsx(data,a["artifact_id"],i.filename)
                    prof+=p; hits+=h
                except Exception as e:
                    errors.append(dict(artifact_id=a["artifact_id"],member_name=i.filename,
                                       error=f"{type(e).__name__}: {e}"))
    write_csv(VAL/"cms_shea_residence_zip_inventory.csv",inv,
              ["artifact_id","role","zip_path","member_name","member_bytes","compressed_bytes","crc32","extension"])
    write_csv(VAL/"cms_shea_residence_spreadsheet_inventory.csv",prof,
              ["artifact_id","member_name","sheet_name","rows_observed","columns_observed","cells_scanned","status","error"])
    write_csv(VAL/"cms_shea_residence_semantic_hits.csv",hits,
              ["artifact_id","member_name","sheet_name","location","search_term","matched_text"])
    write_csv(VAL/"cms_shea_residence_profile_errors.csv",errors,["artifact_id","member_name","error"])
    ae=[a for a in arts if a["status"]=="ERROR"]
    src=[x for x in inv if x["artifact_id"]=="RESIDENCE_ESTIMATES"]
    docs=[x for x in inv if x["artifact_id"]=="STATE_DSM"]
    ma_terms={"managed care","medicare advantage","advantage","part c","capitated","capitation","hmo","ppo"}
    mah=[x for x in hits if x["search_term"] in ma_terms]
    checks=[("Official artifacts acquired/preserved",not ae),
            ("Residence estimates ZIP valid and inventoried",bool(src)),
            ("Methodology ZIP valid and inventoried",bool(docs)),
            ("Spreadsheet profile errors",not errors)]
    ok=all(x[1] for x in checks)
    lines=["="*92,"CMS SHEA STATE-OF-RESIDENCE ACQUISITION / INVENTORY v0.1","="*92,"",
           "Research question: Does the official CMS SHEA package expose a separately identifiable",
           "Medicare managed-care / Medicare Advantage expenditure series suitable for an independent",
           "Washington CY2015-CY2020 reconciliation?","",
           f"Official landing page              : {LANDING}",
           f"Artifacts required                  : {len(ARTIFACTS)}",
           f"Artifacts acquired/preserved        : {len(ARTIFACTS)-len(ae)}",
           f"ZIP members inventoried             : {len(inv)}",
           f"Spreadsheet sheets profiled         : {len(prof)}",
           f"Semantic hits recorded              : {len(hits)}",
           f"MA/managed-care-related hits         : {len(mah)}",
           f"Profile/read errors                 : {len(errors)}","",
           "SEARCH TERMS FOUND","-"*92,
           ", ".join(sorted({x["search_term"] for x in hits})) if hits else "NONE","",
           "VALIDATION CHECKS","-"*92]
    lines += [f"{'PASS' if v else 'FAIL'}  {k}" for k,v in checks]
    lines += ["",f"OVERALL ACQUISITION / INVENTORY STATUS: {'PASS' if ok else 'FAIL'}","",
              "IMPORTANT: PASS establishes source preservation/readable inventory only. It does not",
              "establish a separable MA control, definitional comparability, or successful reconciliation.","",
              "OUTPUTS","-"*92,
              str(VAL/"cms_shea_residence_acquisition_manifest.csv"),
              str(VAL/"cms_shea_residence_zip_inventory.csv"),
              str(VAL/"cms_shea_residence_spreadsheet_inventory.csv"),
              str(VAL/"cms_shea_residence_semantic_hits.csv"),
              str(VAL/"cms_shea_residence_profile_errors.csv")]
    (VAL/"cms_shea_residence_acquisition_inventory_summary.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
