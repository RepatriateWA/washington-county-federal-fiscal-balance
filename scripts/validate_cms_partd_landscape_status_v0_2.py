#!/usr/bin/env python3
"""
CMS Medicare Part D Landscape status validation v0.2

Purpose
-------
Classify the previously certified SAME_CONTRACT_OTHER_PBP control
(5,203,895 numeric Washington CPSC member-months) using ONLY exact,
same-coverage-year Contract + PBP/Plan evidence in the official CMS Landscape
archive.

Classification hierarchy
------------------------
1 PARTD_INDICATED
  Exact same-year Contract+PBP appears in a CMS Part-D-oriented product OR
  has a populated explicit Part-D/drug-benefit field.
2 NO_PARTD_INDICATED
  Exact same-year Contract+PBP has an explicit negative Part-D/drug-benefit
  value (narrow literal vocabulary only).
3 LANDSCAPE_PRESENT_NO_PARTD_EVIDENCE
  Exact same-year Contract+PBP appears in Landscape, but neither positive nor
  explicit-negative Part-D evidence is observed.
4 STATUS_UNRESOLVED
  Exact same-year Contract+PBP is not observed in the profiled Landscape.

Hard boundaries
---------------
- Exact coverage year only.
- Exact Contract + PBP/Plan only.
- No sibling-PBP propagation.
- No adjacent/other-year propagation.
- No payment propagation.
- No imputation.
- No payment reconstruction.
- No database writes.
- No ledger inclusion.

The input control is discovered from the certified relationship-profile output
and must reproduce exactly 5,203,895 member-months before classification.
"""
from __future__ import annotations
import argparse, csv, io, re, sys, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
import openpyxl

EXPECTED = Decimal("5203895")
ARCHIVE = Path("data/raw/cms/medicare_partd/landscape/cy2006-cy2025-landscape-files.zip")
REL_DIR = Path("data/raw/cms/medicare_advantage/validation/partd_contract_pbp_relationship_v0_1")
OUT = Path("data/raw/cms/medicare_partd/landscape/validation/landscape_status_validation_v0_2")
YEARS = tuple(range(2015, 2025))
MAX_DEPTH = 5

def clean(x: Any) -> str:
    return "" if x is None else str(x).strip()

def norm(x: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", clean(x).upper()).strip("_")

def norm_contract(x: Any) -> str:
    return re.sub(r"\s+", "", clean(x).upper())

def norm_pbp(x: Any) -> str:
    v=clean(x).upper()
    # Preserve alphanumeric IDs; zero-pad purely numeric PBP to 3 digits.
    if re.fullmatch(r"\d+(?:\.0+)?", v):
        return f"{int(float(v)):03d}"
    return re.sub(r"\s+", "", v)

def dec(x: Any):
    try:
        t=clean(x).replace(",","")
        return Decimal(t) if t else None
    except InvalidOperation:
        return None

def annual_year(name: str):
    m=re.match(r"^(?:CY)?(20(?:1[5-9]|2[0-4]))(?:\D|$)",Path(name).name,re.I)
    return int(m.group(1)) if m else None

def decode(data: bytes):
    for enc in ("utf-8-sig","cp1252","latin-1"):
        try:
            text=data.decode(enc); break
        except UnicodeDecodeError: pass
    else: raise RuntimeError("unable to decode delimited file")
    sample=text[:65536]
    try: dialect=csv.Sniffer().sniff(sample,delimiters=",|\t;")
    except csv.Error: dialect=csv.excel
    return list(csv.reader(io.StringIO(text,newline=""),dialect))

def choose_header(raw):
    cand=[]
    for i,row in enumerate(raw[:50]):
        vals=[clean(x) for x in row]
        cand.append((sum(bool(x) for x in vals),
                     sum(bool(x) and not x.replace(".","",1).isdigit() for x in vals),
                     i, vals))
    if not cand: return 0,[]
    _,_,idx,h=max(cand)
    while h and not h[-1]: h.pop()
    return idx,h

def tables(name: str, data: bytes):
    ext=Path(name).suffix.lower()
    if ext in {".csv",".txt",".tsv"}:
        raw=decode(data)
        if not raw:return []
        i,h=choose_header(raw)
        return [("",h,[r[:len(h)] for r in raw[i+1:] if any(clean(x) for x in r)])]
    if ext in {".xlsx",".xlsm"}:
        wb=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True)
        out=[]
        try:
            for ws in wb.worksheets:
                raw=list(ws.iter_rows(values_only=True))
                if not raw: continue
                i,h=choose_header(raw)
                out.append((ws.title,h,[list(r[:len(h)]) for r in raw[i+1:] if any(clean(x) for x in r)]))
        finally: wb.close()
        return out
    return []

def field_role(field: str):
    z=norm(field)
    if z in {"CONTRACT","CONTRACT_ID","CONTRACT_NUMBER","CONTRACTID"} or ("CONTRACT" in z and "NAME" not in z):
        return "CONTRACT"
    if z in {"PBP","PBP_ID","PLAN_ID","PLANID","PLAN_BENEFIT_PACKAGE","PLAN_BENEFIT_PACKAGE_ID"}:
        return "PLAN_PBP"
    if any(k in z for k in (
        "DRUG_BENEFIT","PART_D","PARTD","PRESCRIPTION_DRUG","DRUG_COVERAGE",
        "DRUG_PREMIUM","DRUG_DEDUCTIBLE","STAR_RATING_PART_D","NATIONAL_PDP"
    )):
        return "PARTD_EXPLICIT"
    return ""

def file_category(name: str):
    u=name.upper()
    if "PLAN AND PREMIUM" in u or "PLAN_PREMIUM" in u or "508_" in u:
        return "PLAN_PREMIUM_PARTD_PRODUCT"
    if re.search(r"(?:^|[^A-Z])PDP(?:[^A-Z]|$)",u):
        return "PDP_LANDSCAPE"
    if re.search(r"(?:^|[^A-Z])SNP(?:[^A-Z]|$)",u):
        return "SNP_LANDSCAPE"
    if re.search(r"(?:^|[^A-Z])MMP(?:[^A-Z]|$)",u):
        return "MMP_LANDSCAPE"
    if "LANDSCAPE_MA" in u or re.search(r"(?:^|[^A-Z])MA_(?:ATO|NTO|SANCTION)",u):
        return "MA_LANDSCAPE"
    return "OTHER"

POS_PRODUCT={"PLAN_PREMIUM_PARTD_PRODUCT","PDP_LANDSCAPE"}
NEGATIVE_LITERALS={
    "NO","NONE","NO DRUG BENEFIT","NO DRUG BENEFITS","NO DRUG COVERAGE",
    "NOT OFFERED","NO PART D","NO PART D COVERAGE"
}
NULLISH={"","N/A","NA","NOT APPLICABLE","NULL","NONE"}

def find_col(fields, kind):
    scored=[]
    for f in fields:
        z=norm(f)
        score=-1
        if kind=="year":
            if z in {"YEAR","CY","COVERAGE_YEAR","PAYMENT_YEAR"}:score=100
            elif "YEAR" in z:score=50
        elif kind=="contract":
            if z in {"CONTRACT","CONTRACT_ID","CONTRACT_NUMBER","CONTRACTID"}:score=100
            elif "CONTRACT" in z and "NAME" not in z:score=60
        elif kind=="pbp":
            if z in {"PBP","PBP_ID","PLAN_ID","PLANID","PLAN_BENEFIT_PACKAGE","PLAN_BENEFIT_PACKAGE_ID"}:score=100
            elif "PBP" in z:score=80
            elif z=="PLAN":score=40
        elif kind=="mm":
            if z in {"MEMBER_MONTHS","MEMBER_MONTH","NUMERIC_ENROLLMENT","NUMERIC_MEMBER_MONTHS","ENROLLMENT"}:score=100
            elif "MEMBER" in z and "MONTH" in z:score=90
            elif "NUMERIC" in z and "ENROLL" in z:score=80
            elif "ENROLL" in z:score=40
        if score>=0: scored.append((score,f))
    return max(scored)[1] if scored else None

def discover_control(rel_dir: Path):
    candidates=[]
    diagnostics=[]
    for p in sorted(rel_dir.glob("*.csv")):
        try:
            with p.open("r",encoding="utf-8-sig",newline="") as f:
                r=csv.DictReader(f); fields=r.fieldnames or []
                yc=find_col(fields,"year"); cc=find_col(fields,"contract")
                pc=find_col(fields,"pbp"); mc=find_col(fields,"mm")
                if not all((yc,cc,pc,mc)):
                    diagnostics.append((p.name,"missing required columns")); continue
                agg=defaultdict(Decimal); rows=0
                for row in r:
                    yv=clean(row.get(yc))
                    try:y=int(float(yv))
                    except:continue
                    if y not in YEARS:continue
                    c=norm_contract(row.get(cc)); pb=norm_pbp(row.get(pc)); m=dec(row.get(mc))
                    if not c or not pb or m is None:continue
                    agg[(y,c,pb)]+=m; rows+=1
                total=sum(agg.values(),Decimal(0))
                diagnostics.append((p.name,f"rows={rows}; relationships={len(agg)}; total={total}"))
                if total==EXPECTED:
                    candidates.append((p,agg,yc,cc,pc,mc,rows))
        except Exception as e:
            diagnostics.append((p.name,f"ERROR {type(e).__name__}: {e}"))
    # v0.1 correctly refused to choose when both the 183-row contract-year
    # summary and the 242-row Contract+PBP relationship detail reproduced the
    # same 5,203,895 control. This validator requires exact Contract+PBP grain,
    # so select the canonical relationship-detail artifact by filename and
    # still require it independently to reproduce the hard control.
    preferred=[c for c in candidates if c[0].name.lower()=="partd_contract_pbp_relationship.csv"]
    if len(preferred)!=1:
        msg=("Expected exactly one canonical partd_contract_pbp_relationship.csv "
             "reproducing 5,203,895; found "+str(len(preferred)))
        msg+="\n"+"".join(f"\n  {a}: {b}" for a,b in diagnostics)
        raise RuntimeError(msg)
    return preferred[0], diagnostics

def build_landscape_evidence(archive: Path, target_keys: set):
    ev=defaultdict(lambda: {"present":False,"positive":False,"negative":False,"sources":set(),"positive_sources":set(),"negative_sources":set(),"values":set()})
    errors=[]
    def rec(blob,y,chain,d):
        if d>MAX_DEPTH: raise RuntimeError("maximum recursion depth exceeded")
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            bad=z.testzip()
            if bad: raise RuntimeError("nested ZIP integrity failure: "+bad)
            for inf in z.infolist():
                if inf.is_dir():continue
                name=inf.filename; ext=Path(name).suffix.lower()
                try:
                    b=z.read(inf)
                    if ext==".zip":
                        rec(b,y,chain+" -> "+name,d+1)
                    elif ext in {".csv",".txt",".tsv",".xlsx",".xlsm"}:
                        cat=file_category(name)
                        for sheet,h,rows in tables(name,b):
                            roles=[field_role(x) for x in h]
                            cis=[i for i,r in enumerate(roles) if r=="CONTRACT"]
                            pis=[i for i,r in enumerate(roles) if r=="PLAN_PBP"]
                            eis=[i for i,r in enumerate(roles) if r=="PARTD_EXPLICIT"]
                            if not cis or not pis:continue
                            ci,pi=cis[0],pis[0]
                            src=f"{cat}|{name}|{sheet}"
                            for row in rows:
                                if ci>=len(row) or pi>=len(row):continue
                                key=(y,norm_contract(row[ci]),norm_pbp(row[pi]))
                                if key not in target_keys:continue
                                e=ev[key]; e["present"]=True; e["sources"].add(src)
                                # Product membership is positive evidence only for explicitly Part-D-oriented products.
                                if cat in POS_PRODUCT:
                                    e["positive"]=True; e["positive_sources"].add(src+"|PRODUCT_MEMBERSHIP")
                                for i in eis:
                                    if i>=len(row):continue
                                    v=clean(row[i]); vu=v.upper().strip()
                                    if not v or vu in NULLISH:continue
                                    e["values"].add(f"{h[i]}={v}")
                                    if vu in NEGATIVE_LITERALS:
                                        e["negative"]=True; e["negative_sources"].add(src+"|"+h[i]+"="+v)
                                    else:
                                        e["positive"]=True; e["positive_sources"].add(src+"|"+h[i]+"="+v)
                except Exception as ex:
                    errors.append({"year":y,"source":chain+" -> "+name,"error":f"{type(ex).__name__}: {ex}"})
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip()
        if bad:raise RuntimeError("outer ZIP integrity failure: "+bad)
        annual=Counter()
        for inf in z.infolist():
            if inf.is_dir():continue
            y=annual_year(inf.filename)
            if y not in YEARS:continue
            annual[y]+=1
            rec(z.read(inf),y,Path(inf.filename).name,1)
    return ev,errors,annual

def write(path,rows,fields):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--archive",type=Path,default=ARCHIVE)
    ap.add_argument("--relationship-dir",type=Path,default=REL_DIR)
    ap.add_argument("--output-dir",type=Path,default=OUT)
    a=ap.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
    if not a.archive.exists() or not zipfile.is_zipfile(a.archive):
        print(f"ERROR: Landscape archive unavailable/not ZIP: {a.archive}",file=sys.stderr);return 2
    try:
        (control,discovery)=discover_control(a.relationship_dir)
    except Exception as e:
        print(f"CONTROL DISCOVERY FAIL\n{e}",file=sys.stderr);return 2
    p,agg,yc,cc,pc,mc,input_rows=control
    target=set(agg)
    try:
        ev,errors,annual=build_landscape_evidence(a.archive,target)
    except Exception as e:
        print(f"LANDSCAPE EVIDENCE BUILD FAIL\n{e}",file=sys.stderr);return 2

    detail=[]; cats=Counter(); catmm=defaultdict(Decimal); yearmm=defaultdict(lambda:defaultdict(Decimal))
    conflicts=0
    for key in sorted(target):
        y,c,pb=key; m=agg[key]; e=ev.get(key,{})
        pos=bool(e.get("positive")); neg=bool(e.get("negative")); present=bool(e.get("present"))
        if pos and neg:
            status="EVIDENCE_CONFLICT"; conflicts+=1
        elif pos: status="PARTD_INDICATED"
        elif neg: status="NO_PARTD_INDICATED"
        elif present: status="LANDSCAPE_PRESENT_NO_PARTD_EVIDENCE"
        else: status="STATUS_UNRESOLVED"
        cats[status]+=1;catmm[status]+=m;yearmm[y][status]+=m
        detail.append({
            "year":y,"contract":c,"pbp":pb,"member_months":str(m),
            "classification":status,"landscape_present":"YES" if present else "NO",
            "positive_partd_evidence":"YES" if pos else "NO",
            "explicit_negative_partd_evidence":"YES" if neg else "NO",
            "source_count":len(e.get("sources",set())),
            "sources":" || ".join(sorted(e.get("sources",set()))),
            "positive_sources":" || ".join(sorted(e.get("positive_sources",set()))),
            "negative_sources":" || ".join(sorted(e.get("negative_sources",set()))),
            "observed_partd_values":" || ".join(sorted(e.get("values",set())))
        })
    classified=sum(catmm.values(),Decimal(0))
    summary=[]
    for st in ("PARTD_INDICATED","NO_PARTD_INDICATED","LANDSCAPE_PRESENT_NO_PARTD_EVIDENCE","STATUS_UNRESOLVED","EVIDENCE_CONFLICT"):
        summary.append({"classification":st,"relationships":cats[st],"member_months":str(catmm[st]),
                        "percent_of_control":f"{(catmm[st]/EXPECTED*100 if EXPECTED else 0):.6f}"})
    annual_rows=[]
    for y in YEARS:
        for st in ("PARTD_INDICATED","NO_PARTD_INDICATED","LANDSCAPE_PRESENT_NO_PARTD_EVIDENCE","STATUS_UNRESOLVED","EVIDENCE_CONFLICT"):
            if yearmm[y][st]:
                annual_rows.append({"year":y,"classification":st,"member_months":str(yearmm[y][st])})

    checks=[
        ("relationship input control equals 5,203,895",sum(agg.values(),Decimal(0))==EXPECTED),
        ("classification accounting identity equals input control",classified==EXPECTED),
        ("every target relationship receives exactly one classification",len(detail)==len(target)),
        ("exactly one annual Landscape package for every CY2015-CY2024",all(annual[y]==1 for y in YEARS)),
        ("no Landscape recursive/profile errors",not errors),
        ("no contradictory positive/negative Part-D evidence",conflicts==0),
    ]
    overall=all(v for _,v in checks)

    write(a.output_dir/"cms_partd_landscape_status_detail.csv",detail,
          ["year","contract","pbp","member_months","classification","landscape_present",
           "positive_partd_evidence","explicit_negative_partd_evidence","source_count","sources",
           "positive_sources","negative_sources","observed_partd_values"])
    write(a.output_dir/"cms_partd_landscape_status_summary.csv",summary,
          ["classification","relationships","member_months","percent_of_control"])
    write(a.output_dir/"cms_partd_landscape_status_by_year.csv",annual_rows,
          ["year","classification","member_months"])
    write(a.output_dir/"cms_partd_landscape_status_errors.csv",errors,["year","source","error"])
    with (a.output_dir/"cms_partd_landscape_control_discovery.txt").open("w",encoding="utf-8") as f:
        f.write(f"Selected input: {p}\nYear column: {yc}\nContract column: {cc}\nPBP column: {pc}\nMember-month column: {mc}\nInput rows used: {input_rows}\n\n")
        for x,msg in discovery:f.write(f"{x}: {msg}\n")

    lines=[
        "CMS MEDICARE PART D LANDSCAPE STATUS VALIDATION v0.2","="*76,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Landscape archive: {a.archive}",
        f"Control input: {p}","",
        "BOUNDARY","-"*76,
        "Exact same-year Contract+PBP evidence only. The canonical 242-row",
        "partd_contract_pbp_relationship.csv is required; the 183-row contract-year",
        "summary is retained as a control but is not valid input grain for this validator.",
        "No sibling-PBP or other-year",
        "propagation. No payment propagation, imputation, reconstruction, DB writes,",
        "or ledger inclusion.","",
        "CONTROL","-"*76,
        f"Expected SAME_CONTRACT_OTHER_PBP member-months: {EXPECTED:,}",
        f"Input member-months: {sum(agg.values(),Decimal(0)):,}",
        f"Distinct Contract+PBP+year relationships: {len(target):,}","",
        "CLASSIFICATION","-"*76]
    for x in summary:
        lines.append(f"{x['classification']}: relationships={x['relationships']:,}, member-months={Decimal(x['member_months']):,}, percent={x['percent_of_control']}%")
    lines += ["","ACCOUNTING","-"*76,
              f"Classified member-months: {classified:,}",
              f"Accounting difference: {classified-EXPECTED:,}","",
              "CHECKS","-"*76]
    lines += [f"{k}: {'PASS' if v else 'FAIL'}" for k,v in checks]
    lines += ["","ERRORS","-"*76]
    lines += ["None"] if not errors else [f"CY{x['year']} | {x['source']} | {x['error']}" for x in errors]
    lines += ["","INTERPRETIVE BOUNDARY","-"*76,
              "PARTD_INDICATED means exact same-year plan-level CMS Landscape evidence",
              "positively indicates Part D. LANDSCAPE_PRESENT_NO_PARTD_EVIDENCE means",
              "the exact plan is observed but positive Part-D evidence is absent; it is",
              "not automatically equivalent to an affirmative CMS 'no Part D' status.",
              "STATUS_UNRESOLVED remains unresolved. No payment may be propagated from",
              "a sibling PBP or another year.","",
              "OVERALL","-"*76,f"OVERALL: {'PASS' if overall else 'FAIL'}"]
    report="\n".join(lines)+"\n"
    (a.output_dir/"cms_partd_landscape_status_validation_report.txt").write_text(report,encoding="utf-8")
    print(report);print(f"Outputs: {a.output_dir}")
    return 0 if overall else 1

if __name__=="__main__":
    sys.exit(main())
