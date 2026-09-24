#!/usr/bin/env python3
"""
CMS Medicare Part D PBP Benefits ZIP-wide semantic/codebook search v0.1

READ-ONLY diagnostic.

Searches every member of the already-preserved CY2015-CY2024 PBP Benefits
source ZIPs for evidence defining mrx_drug_ben_yn and related drug-benefit
codes. It does not classify disputed plans or decode values by assumption.

Search targets include:
  mrx_drug_ben_yn
  drug_ben_yn
  drug benefit
  prescription drug
  benefit type
  part d / partd

For tabular/text members it searches decoded text. For binary Office/PDF
members it inventories names but does not OCR or infer semantics.
"""

from __future__ import annotations
import csv, hashlib, io, json, re, sys, zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("data/raw/cms/medicare_partd/pbp_benefits")
OUT = ROOT / "validation" / "pbp_benefits_codebook_search_v0_1"
YEARS = range(2015, 2025)

TERMS = [
    ("EXACT_FIELD", re.compile(r"mrx_drug_ben_yn", re.I)),
    ("FIELD_STEM", re.compile(r"drug_ben_yn", re.I)),
    ("DRUG_BENEFIT", re.compile(r"drug[\s_\-]+benefit", re.I)),
    ("PRESCRIPTION_DRUG", re.compile(r"prescription[\s_\-]+drug", re.I)),
    ("BENEFIT_TYPE", re.compile(r"benefit[\s_\-]+type", re.I)),
    ("PART_D", re.compile(r"\bpart[\s_\-]*d\b", re.I)),
]
TEXT_EXTS={".txt",".csv",".tsv",".tab",".dat",".sas",".sql",".xml",".html",".htm",".md",".json",".yaml",".yml",".log",".lst"}
INVENTORY_HINTS=re.compile(r"(code|lookup|layout|label|format|value|dict|document|readme|spec|field|data.?element|crosswalk|mrx|drug)",re.I)

def sha256_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def decode(b):
    for enc in ("utf-8-sig","cp1252","latin-1"):
        try: return b.decode(enc)
        except UnicodeDecodeError: pass
    return None

def one_zip(year):
    zs=sorted((ROOT/str(year)).glob("*.zip"))
    if len(zs)!=1: raise RuntimeError(f"CY{year}: expected one ZIP, found {len(zs)}")
    return zs[0]

def context(text, m, radius=220):
    a=max(0,m.start()-radius); b=min(len(text),m.end()+radius)
    s=text[a:b].replace("\r"," ").replace("\n"," ")
    return re.sub(r"\s+"," ",s).strip()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    hits=[]; inventory=[]; year_summary=[]; errors=[]
    for year in YEARS:
        try:
            zp=one_zip(year)
            member_count=0; searched=0; hit_members=set()
            with zipfile.ZipFile(zp) as z:
                bad=z.testzip()
                if bad: raise RuntimeError(f"ZIP integrity failure: {bad}")
                for info in z.infolist():
                    if info.is_dir(): continue
                    member_count+=1
                    name=info.filename
                    ext=Path(name).suffix.lower()
                    if INVENTORY_HINTS.search(name):
                        inventory.append({"year":year,"member_name":name,"bytes":info.file_size,"reason":"filename_hint"})
                    if ext not in TEXT_EXTS:
                        continue
                    searched+=1
                    try:
                        raw=z.read(info)
                        text=decode(raw)
                        if text is None: continue
                        member_hit=False
                        for label,pat in TERMS:
                            for idx,m in enumerate(pat.finditer(text)):
                                hits.append({
                                    "year":year,"member_name":name,"term":label,
                                    "matched_text":m.group(0),
                                    "context":context(text,m),
                                })
                                member_hit=True
                                if idx>=49:  # cap per term/member; enough for semantic discovery
                                    break
                        if member_hit: hit_members.add(name)
                    except Exception as e:
                        errors.append(f"CY{year} {name}: {type(e).__name__}: {e}")
            year_summary.append({
                "year":year,"source_zip":str(zp),"sha256":sha256_file(zp),
                "members":member_count,"text_members_searched":searched,
                "members_with_hits":len(hit_members),
            })
        except Exception as e:
            errors.append(f"CY{year}: {type(e).__name__}: {e}")

    def write(path, rows, fields):
        with path.open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

    write(OUT/"pbp_codebook_search_hits.csv",hits,
          ["year","member_name","term","matched_text","context"])
    write(OUT/"pbp_codebook_candidate_member_inventory.csv",inventory,
          ["year","member_name","bytes","reason"])
    write(OUT/"pbp_codebook_search_year_summary.csv",year_summary,
          ["year","source_zip","sha256","members","text_members_searched","members_with_hits"])

    exact=[h for h in hits if h["term"]=="EXACT_FIELD"]
    non_mrx_exact=[h for h in exact if Path(h["member_name"]).name.lower()!="pbp_mrx.txt"]
    checks={
        "all_ten_years_searched":len(year_summary)==10,
        "no_source_search_errors":len(errors)==0,
        "all_source_zips_have_members":len(year_summary)==10 and all(r["members"]>0 for r in year_summary),
    }
    overall=all(checks.values())
    report={
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "boundary":"Evidence discovery only; no code decoding by assumption and no disputed-plan classification.",
        "hit_count":len(hits),
        "exact_field_hits":len(exact),
        "exact_field_hits_outside_pbp_mrx":len(non_mrx_exact),
        "candidate_inventory_rows":len(inventory),
        "checks":checks,"errors":errors,"overall":"PASS" if overall else "FAIL"
    }
    (OUT/"pbp_codebook_search_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")

    print("CMS MEDICARE PART D PBP BENEFITS ZIP-WIDE CODEBOOK SEARCH v0.1")
    print("="*76)
    print(f"Generated UTC: {report['generated_utc']}\n")
    print("BOUNDARY\n"+"-"*76)
    print("Evidence discovery only. No code decoding by assumption; no disputed-plan classification.\n")
    print("YEAR SEARCH\n"+"-"*76)
    for r in year_summary:
        print(f"CY{r['year']}: members={r['members']:,} | text searched={r['text_members_searched']:,} | hit members={r['members_with_hits']:,}")
    print("\nHITS\n"+"-"*76)
    print(f"All search-term hits: {len(hits):,}")
    print(f"Exact mrx_drug_ben_yn hits: {len(exact):,}")
    print(f"Exact-field hits outside pbp_mrx.txt: {len(non_mrx_exact):,}")
    print(f"Candidate codebook/layout/member inventory rows: {len(inventory):,}")
    if non_mrx_exact:
        print("\nEXACT FIELD OUTSIDE pbp_mrx.txt")
        print("-"*76)
        for h in non_mrx_exact[:30]:
            print(f"CY{h['year']} | {h['member_name']} | {h['context']}")
    print("\nCHECKS\n"+"-"*76)
    for k,v in checks.items(): print(f"{k.replace('_',' ')}: {'PASS' if v else 'FAIL'}")
    print("\nERRORS\n"+"-"*76)
    print("None" if not errors else "\n".join(errors))
    print("\nOVERALL\n"+"-"*76)
    print("OVERALL:", "PASS" if overall else "FAIL")
    print(f"\nOutputs: {OUT}")
    return 0 if overall else 1

if __name__=="__main__":
    raise SystemExit(main())
