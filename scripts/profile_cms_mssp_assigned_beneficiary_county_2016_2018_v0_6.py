#!/usr/bin/env python3
r"""
CMS MSSP Assigned Beneficiary County 2016-2018 Historical Source Profiler v0.6

Read-only: no DB writes, source mutation, financial allocation, or ledger decision.
Raw beneficiary value states are inventoried before semantic interpretation.

Run:
    python .\scripts\profile_cms_mssp_assigned_beneficiary_county_2016_2018_v0_6.py
"""
from __future__ import annotations
import csv, hashlib, io, re, sys, zipfile
from collections import Counter
from pathlib import Path

VERSION = "v0.6"
SRCREL = Path("data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county")
FINREL = Path("data/raw/cms/medicare_aco/mssp_performance_results/Performance Year Financial and Quality Results.zip")
EVIDREL = SRCREL / "validation" / "profile_2016_2018_v0_6"

SOURCES = {
  2016: ("Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2016_01_01.csv",4421455,"6D745C0F28949F53B4EDA8793CF050A15AFC8A947402901F9E94A9C3EE2FEB19",432),
  2017: ("Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2017_01_01.csv",5563732,"D3C6EDF2B8B80E4244FAD4BC36E8E9E518055D97A0147ABA79DE7D3A61E6ABB3",472),
  2018: ("Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2018_01_01.csv",6503795,"ABA3135EF3CD8F7AEC46F0354D246AD30821BF53EFB9B0D738C957612CE7597F",548),
}
MEASURES = {
 "esrd assigned beneficiary person-years","disabled assigned beneficiary person-years",
 "aged/dual assigned beneficiary person-years","aged/non-dual assigned beneficiary person-years",
 "total assigned beneficiary person-years","total assigned beneficiaries"
}

def root():
    for s in [Path.cwd().resolve(), Path(__file__).resolve().parent]:
        for p in (s,*s.parents):
            if (p/"data").is_dir() and (p/"scripts").is_dir(): return p
    raise RuntimeError("Repository root not found")

def digest(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""): h.update(b)
    return h.hexdigest().upper()

def norm(s):
    s = re.sub(r"\s+", " ", s.strip().lower())
    return {
        "aco id": "aco_id",
        "aco_num": "aco_id",
        "state id": "state_id",
        "county id": "county_id",
    }.get(s, s)

def col(fields,name):
    return next((f for f in fields if norm(f)==name),None)

def read_file(p):
    with p.open("r",encoding="utf-8-sig",newline="") as f:
        r=csv.DictReader(f); return r.fieldnames or [],list(r)

def read_member(z,m):
    r=csv.DictReader(io.StringIO(z.read(m).decode("utf-8-sig",errors="replace")))
    return r.fieldnames or [],list(r)

def state(v):
    if v is None:return "<NONE>"
    if v=="":return "<BLANK>"
    if not v.strip():return "<WHITESPACE>"
    return v.strip()

def state_summary(c):
    numeric=0; other=Counter()
    for v,n in c.items():
        try: float(v.replace(",","")); numeric+=n
        except Exception: other[v]+=n
    return " ".join([f"numeric={numeric:,}"]+[f"{k!r}={v:,}" for k,v in other.most_common(20)])

def financial_candidates(z,year):
    pat=re.compile(rf"(^|[/_\-\s]){year}([/_\-\s.]|$)",re.I)
    return [n for n in z.namelist() if n.lower().endswith(".csv") and pat.search(n)]

def main():
    base=root(); src=base/SRCREL; fin=base/FINREL; evid=base/EVIDREL
    evid.mkdir(parents=True,exist_ok=True)
    lines=[]; checks=[]; county_sets={}
    def emit(x=""): print(x); lines.append(x)
    def ck(code,ok,detail):
        checks.append((code,"PASS" if ok else "FAIL",detail))
        emit(f"{code}: {'PASS' if ok else 'FAIL'} - {detail}")

    emit(f"CMS MSSP ASSIGNED BENEFICIARY COUNTY 2016-2018 HISTORICAL SOURCE PROFILE {VERSION}")
    emit("="*96)
    emit("Read-only. Raw beneficiary value states are inventoried without semantic coercion.\n")

    for y,(name,nbytes,sha,expected) in SOURCES.items():
        emit(f"{y} COUNTY SOURCE"); emit("-"*96)
        p=src/name
        if not p.exists():
            ck(f"{y}-SOURCE-01",False,f"missing {p}"); emit(); continue
        ck(f"{y}-SOURCE-01",p.stat().st_size==nbytes,f"bytes={p.stat().st_size:,} expected={nbytes:,}")
        actual=digest(p); ck(f"{y}-SOURCE-02",actual==sha,f"SHA256={actual}")
        fields,rows=read_file(p)
        emit(f"rows={len(rows):,}")
        emit(f"exact headers ({len(fields)}): {fields}")
        emit(f"normalized headers ({len(fields)}): {[norm(f) for f in fields]}")
        ac=col(fields,"aco_id"); yc=col(fields,"year"); sc=col(fields,"state_id"); cc=col(fields,"county_id")
        if not ac:
            ck(f"{y}-STRUCT-01",False,"ACO_ID column not found"); emit(); continue
        vals=[(r.get(ac) or "").strip() for r in rows]; blanks=vals.count(""); aset=set(vals); aset.discard("")
        county_sets[y]=aset
        ck(f"{y}-STRUCT-01",len(aset)==expected and blanks==0,
           f"ACO universe={len(aset):,} expected={expected:,}; blank={blanks:,}")
        bad=sum(1 for r in rows if (r.get(yc) or "").strip()!=str(y)) if yc else len(rows)
        ck(f"{y}-STRUCT-02",yc is not None and bad==0,f"Year column present={yc is not None}; mismatched rows={bad:,}")
        dup=0
        if sc and cc:
            keys=Counter(((r.get(ac)or"").strip(),(r.get(sc)or"").strip(),(r.get(cc)or"").strip()) for r in rows)
            dup=sum(n-1 for n in keys.values() if n>1)
        emit(f"duplicate ACO+state_id+county_id rows={dup:,}")
        emit("RAW BENEFICIARY VALUE STATES")
        found=0
        for f in fields:
            if norm(f) in MEASURES:
                found+=1; c=Counter(state(r.get(f)) for r in rows)
                emit(f"  {f!r}: {state_summary(c)}")
        ck(f"{y}-SEM-01",found==6,f"beneficiary measure columns found={found}/6")
        emit()

    emit("FINANCIAL PUF LINKAGE"); emit("-"*96)
    if not fin.exists(): ck("FIN-01",False,f"missing {fin}")
    else:
        with zipfile.ZipFile(fin) as z:
            for y in SOURCES:
                cand=financial_candidates(z,y); emit(f"{y}: candidate CSV members={len(cand)}")
                usable=exact=0
                for m in cand:
                    fields,rows=read_member(z,m); ac=col(fields,"aco_id")
                    if not ac: continue
                    usable+=1; fs={(r.get(ac)or"").strip() for r in rows}; fs.discard("")
                    cs=county_sets.get(y,set()); eq=bool(cs) and cs==fs; exact+=int(eq)
                    emit(f"  {m}")
                    emit(f"    rows={len(rows):,} financial_ACOs={len(fs):,}")
                    emit(f"    county={len(cs):,} intersection={len(cs&fs):,} county_only={len(cs-fs):,} financial_only={len(fs-cs):,} exact_equal={'YES' if eq else 'NO'}")
                ck(f"{y}-FIN-01",usable>=1,f"financial candidates with ACO_ID={usable}")
                ck(f"{y}-FIN-02",exact==1,f"exact county-financial ACO-set matches={exact}")
                emit()

    emit("INTERPRETATION GUARDRAILS"); emit("-"*96)
    emit("PROFILE-ONLY: Blank, '*', and '.' states are lexical observations; no meaning is assigned here.")
    emit("PROFILE-ONLY: No suppressed observation is treated as zero.")
    emit("PROFILE-ONLY: No EarnSaveLoss or other financial measure is allocated.")
    emit("PROFILE-ONLY: No Washington dollar incidence or ledger-inclusion decision is made.\n")
    failures=[x for x in checks if x[1]=="FAIL"]
    emit(f"OVERALL PROFILE EXECUTION {VERSION}: {'PASS' if not failures else 'FAIL'}")
    emit(f"Checks: {len(checks)} total; {len(failures)} failed")
    emit(f"Evidence: {evid}")
    (evid/"cms_mssp_assigned_beneficiary_county_2016_2018_profile_v0_6.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    with (evid/"cms_mssp_assigned_beneficiary_county_2016_2018_checks_v0_6.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.writer(f); w.writerow(["check_code","status","detail"]); w.writerows(checks)
    return 0 if not failures else 1

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"\nFATAL: {type(exc).__name__}: {exc}",file=sys.stderr); raise
