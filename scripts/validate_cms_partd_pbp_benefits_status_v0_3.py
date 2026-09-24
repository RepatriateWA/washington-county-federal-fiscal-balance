#!/usr/bin/env python3
"""
CMS Medicare Part D PBP Benefits exact-status validation v0.3

Applies a pre-declared, same-year exact (CY, Contract, PBP) evidence test to
the 241 relationships / 5,203,829 member-months not positively resolved by
the prior CMS Landscape validation.

Positive PBP evidence:
  exact same-year Contract+PBP occurs in CMS pbp_mrx.txt and has a populated
  mrx_benefit_type and/or mrx_partd_network_loc value.

Absence is NOT interpreted as explicit evidence of no Part D.

No sibling-PBP propagation. No other-year propagation. No payment propagation.
No imputation, payment reconstruction, DB writes, or ledger inclusion.
"""
from __future__ import annotations
import csv, io, re, sys, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PBP_ROOT=Path("data/raw/cms/medicare_partd/pbp_benefits")
REL=Path("data/raw/cms/medicare_advantage/validation/partd_contract_pbp_relationship_v0_1/partd_contract_pbp_relationship.csv")
LAND=Path("data/raw/cms/medicare_partd/landscape/validation/landscape_status_validation_v0_2")
OUT=PBP_ROOT/"validation"/"pbp_benefits_status_validation_v0_3"
ORIGINAL=5_203_895
LAND_POSITIVE=66
TARGET=5_203_829
YEARS=range(2015,2025)
csv.field_size_limit(min(sys.maxsize,10_000_000))

def clean(x): return "" if x is None else str(x).strip()
def ncol(x): return re.sub(r"[^a-z0-9]+","_",clean(x).lower()).strip("_")
def canon_contract(x): return clean(x).upper()
def canon_pbp(x):
    s=clean(x)
    if re.fullmatch(r"\d+(?:\.0+)?",s): return f"{int(float(s)):03d}"
    return s.upper()

def read_csv_rows(p):
    with p.open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def fieldmap(row):
    return {ncol(k):k for k in row.keys()}

def pick(fm, candidates):
    for c in candidates:
        if c in fm:return fm[c]
    return None

def find_landscape_detail():
    if not LAND.exists(): raise RuntimeError(f"Landscape output dir not found: {LAND}")
    candidates=[]
    for p in LAND.glob("*.csv"):
        try:
            rows=read_csv_rows(p)
            if not rows: continue
            fm=fieldmap(rows[0])
            cy=pick(fm,["year","coverage_year","cy"])
            con=pick(fm,["contract","contract_id","contract_number"])
            pbp=pick(fm,["pbp","pbp_id","plan_id","plan_benefit_package"])
            cls=pick(fm,["classification","status","landscape_status","partd_status"])
            mm=pick(fm,["numeric_enrollment","member_months","member_month_control","same_contract_other_pbp_numeric_enrollment"])
            if not all([cy,con,pbp,cls,mm]):continue
            pos=sum(int(float(clean(r[mm]) or 0)) for r in rows if clean(r[cls]).upper()=="PARTD_INDICATED")
            if pos==LAND_POSITIVE:candidates.append((p,rows,(cy,con,pbp,cls,mm)))
        except Exception: pass
    if len(candidates)!=1:
        raise RuntimeError(f"Expected exactly one Landscape detail CSV with {LAND_POSITIVE} PARTD_INDICATED member-months; found {[str(x[0]) for x in candidates]}")
    return candidates[0]

def relationship_input():
    rows=read_csv_rows(REL)
    if not rows: raise RuntimeError("Relationship control is empty")
    fm=fieldmap(rows[0])
    cy=pick(fm,["year","coverage_year","cy"])
    con=pick(fm,["contract","contract_id","contract_number"])
    pbp=pick(fm,["pbp","pbp_id","plan_id","plan_benefit_package","unmatched_cpsc_pbp"])
    mm=pick(fm,["numeric_enrollment","member_months","member_month_control","same_contract_other_pbp_numeric_enrollment"])
    if not all([cy,con,pbp,mm]): raise RuntimeError(f"Required relationship columns not found. Columns={list(rows[0])}")
    total=sum(int(float(clean(r[mm]) or 0)) for r in rows)
    if total!=ORIGINAL: raise RuntimeError(f"Relationship control {total:,} != expected {ORIGINAL:,}")
    return rows,(cy,con,pbp,mm)

def decode(data):
    for enc in ("utf-8-sig","cp1252","latin-1"):
        try:return data.decode(enc)
        except UnicodeDecodeError:pass
    raise RuntimeError("Could not decode pbp_mrx.txt")

def parse_mrx(year):
    zips=list((PBP_ROOT/str(year)).glob("*.zip"))
    if len(zips)!=1:raise RuntimeError(f"CY{year}: expected one ZIP, found {len(zips)}")
    with zipfile.ZipFile(zips[0]) as z:
        names=[n for n in z.namelist() if Path(n).name.lower()=="pbp_mrx.txt"]
        if len(names)!=1:raise RuntimeError(f"CY{year}: expected one pbp_mrx.txt, found {names}")
        text=decode(z.read(names[0]))
    # CMS .txt members are not assumed to be comma-delimited. Reuse the
    # structural profiler's delimiter-discovery principle so parsing is
    # consistent with the already-certified source profile.
    sample=text[:65536]
    try:
        dialect=csv.Sniffer().sniff(sample, delimiters=",|\\t;")
    except csv.Error:
        dialect=csv.excel
    rows=list(csv.reader(io.StringIO(text,newline=""), dialect))
    # find header containing contract and plan/pbp
    hi=None
    for i,r in enumerate(rows[:60]):
        nn=[ncol(x) for x in r]
        if any("contract" in x for x in nn) and any(x in {"pbp","pbp_id","plan_id","plan_benefit_package"} or "pbp" in x for x in nn):
            hi=i;break
    if hi is None:raise RuntimeError(f"CY{year}: no Contract+PBP header in pbp_mrx.txt")
    hdr=[clean(x) for x in rows[hi]]
    fm={ncol(k):i for i,k in enumerate(hdr)}
    ci=next((i for k,i in fm.items() if "contract" in k and "name" not in k),None)
    pi=next((i for k,i in fm.items() if k in {"pbp","pbp_id","plan_id","plan_benefit_package"} or "pbp" in k),None)
    bi=fm.get("mrx_benefit_type")
    ni=fm.get("mrx_partd_network_loc")
    if ci is None or pi is None or (bi is None and ni is None):
        raise RuntimeError(f"CY{year}: required fields absent; header={hdr}")
    evidence={}
    duplicate_keys=0
    for r in rows[hi+1:]:
        if not any(clean(x) for x in r):continue
        def at(i):return clean(r[i]) if i is not None and i<len(r) else ""
        key=(canon_contract(at(ci)),canon_pbp(at(pi)))
        if not all(key):continue
        ev=(at(bi),at(ni))
        if key in evidence and evidence[key]!=ev:duplicate_keys+=1
        # Preserve positive if any row has populated evidence.
        old=evidence.get(key,("",""))
        evidence[key]=(old[0] or ev[0],old[1] or ev[1])
    return evidence,duplicate_keys,str(zips[0])

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rel,rc=relationship_input(); cy,con,pbp,mm=rc
    lp,lrows,lc=find_landscape_detail(); lcy,lcon,lpbp,lcls,lmm=lc
    landscape_positive={(int(float(clean(r[lcy]))),canon_contract(r[lcon]),canon_pbp(r[lpbp]))
                        for r in lrows if clean(r[lcls]).upper()=="PARTD_INDICATED"}
    landscape_positive_mm=sum(int(float(clean(r[lmm]) or 0)) for r in lrows if clean(r[lcls]).upper()=="PARTD_INDICATED")
    if landscape_positive_mm!=LAND_POSITIVE:raise RuntimeError("Landscape positive control mismatch")

    mrx={}; dup=0; sources={}
    errors=[]
    for y in YEARS:
        try:
            ev,d,s=parse_mrx(y);mrx[y]=ev;dup+=d;sources[y]=s
        except Exception as e:errors.append(f"CY{y}: {type(e).__name__}: {e}")

    detail=[]; cats=Counter(); relcats=Counter()
    excluded_land_mm=0
    for r in rel:
        y=int(float(clean(r[cy]))); c=canon_contract(r[con]); p=canon_pbp(r[pbp]); n=int(float(clean(r[mm]) or 0))
        key=(y,c,p)
        if key in landscape_positive:
            excluded_land_mm+=n
            continue
        ev=mrx.get(y,{}).get((c,p))
        if ev and (ev[0] or ev[1]):
            status="PBP_PARTD_EVIDENCE"
            reason="Exact same-year Contract+PBP occurs in pbp_mrx.txt with populated Part-D/Rx evidence field."
        elif ev:
            status="PBP_PRESENT_NO_POSITIVE_PARTD_EVIDENCE"
            reason="Exact same-year Contract+PBP occurs in pbp_mrx.txt but designated evidence fields are blank."
        else:
            status="PBP_STATUS_UNRESOLVED"
            reason="No exact same-year Contract+PBP record found in pbp_mrx.txt; absence is not treated as negative Part-D evidence."
        cats[status]+=n;relcats[status]+=1
        detail.append(dict(year=y,contract=c,pbp=p,member_months=n,status=status,
                           mrx_benefit_type="" if not ev else ev[0],
                           mrx_partd_network_loc="" if not ev else ev[1],reason=reason))
    classified=sum(cats.values())
    checks=[
        ("canonical relationship control equals 5,203,895",sum(int(float(clean(r[mm]) or 0)) for r in rel)==ORIGINAL),
        ("Landscape positive exclusion equals 66 member-months",excluded_land_mm==LAND_POSITIVE),
        ("PBP validation target equals 5,203,829 member-months",classified==TARGET),
        ("classification accounting identity is exact",sum(cats.values())==TARGET),
        ("all 241 post-Landscape relationships classified",len(detail)==241),
        ("all ten pbp_mrx.txt sources resolved",len(mrx)==10),
        ("no conflicting duplicate exact keys in pbp_mrx.txt",dup==0),
        ("no source/profile errors",not errors),
    ]
    with (OUT/"cms_partd_pbp_status_detail.csv").open("w",encoding="utf-8-sig",newline="") as f:
        fields=["year","contract","pbp","member_months","status","mrx_benefit_type","mrx_partd_network_loc","reason"]
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(detail)
    with (OUT/"cms_partd_pbp_status_summary.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f);w.writerow(["status","relationships","member_months","percent_of_target"])
        for s in ("PBP_PARTD_EVIDENCE","PBP_PRESENT_NO_POSITIVE_PARTD_EVIDENCE","PBP_STATUS_UNRESOLVED"):
            w.writerow([s,relcats[s],cats[s],f"{cats[s]/TARGET*100:.6f}"])
    lines=[
      "CMS MEDICARE PART D PBP BENEFITS EXACT-STATUS VALIDATION v0.3","="*76,
      f"Generated UTC: {datetime.now(timezone.utc).isoformat()}","",
      "BOUNDARY","-"*76,
      "Exact same-year (CY, Contract, PBP) evidence only.",
      "Canonical relationship PBP field: unmatched_cpsc_pbp (schema alias only).",
      "pbp_mrx.txt delimiter is discovered from source bytes; comma is not assumed.",
      "Positive evidence requires exact presence in CMS pbp_mrx.txt with populated",
      "mrx_benefit_type and/or mrx_partd_network_loc. Absence is NOT negative evidence.",
      "No sibling-PBP or other-year propagation. No payment propagation, imputation,",
      "reconstruction, DB writes, or ledger inclusion.","",
      "CONTROL","-"*76,
      f"Original SAME_CONTRACT_OTHER_PBP member-months: {ORIGINAL:,}",
      f"Prior Landscape PARTD_INDICATED excluded: {excluded_land_mm:,}",
      f"PBP Benefits validation target: {classified:,}",
      f"Post-Landscape relationships classified: {len(detail):,}","",
      "CLASSIFICATION","-"*76]
    for s in ("PBP_PARTD_EVIDENCE","PBP_PRESENT_NO_POSITIVE_PARTD_EVIDENCE","PBP_STATUS_UNRESOLVED"):
        lines.append(f"{s}: {relcats[s]:,} relationships | {cats[s]:,} member-months | {cats[s]/TARGET*100:.6f}%")
    lines += ["","ACCOUNTING","-"*76,
              f"{TARGET:,} = {cats['PBP_PARTD_EVIDENCE']:,} + {cats['PBP_PRESENT_NO_POSITIVE_PARTD_EVIDENCE']:,} + {cats['PBP_STATUS_UNRESOLVED']:,}",
              f"Difference: {TARGET-sum(cats.values()):,}","",
              "CHECKS","-"*76]
    lines += [f"{a}: {'PASS' if b else 'FAIL'}" for a,b in checks]
    lines += ["","ERRORS","-"*76]+(errors or ["None"])+["","OVERALL","-"*76,f"OVERALL: {'PASS' if all(b for _,b in checks) else 'FAIL'}"]
    report="\n".join(lines)+"\n"
    (OUT/"cms_partd_pbp_status_validation_report.txt").write_text(report,encoding="utf-8")
    print(report);print(f"Outputs: {OUT}")
    return 0 if all(b for _,b in checks) else 1
if __name__=="__main__":sys.exit(main())
