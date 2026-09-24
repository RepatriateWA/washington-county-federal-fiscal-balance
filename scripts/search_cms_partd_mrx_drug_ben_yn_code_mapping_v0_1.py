#!/usr/bin/env python3
"""
CMS Medicare Part D PBP MRx Drug Benefit Y/N code-mapping search v0.1

READ-ONLY evidence discovery.

Purpose
-------
Search the already-preserved CY2015-CY2024 CMS PBP Benefits ZIPs for an
authoritative mapping of mrx_drug_ben_yn / "MRx Drug Benefit YN", especially
evidence mapping source values 1 and 2 to meanings such as Yes/No.

This utility:
  * searches every text-like ZIP member;
  * targets exact field/label references plus nearby value-label syntax;
  * searches SAS FORMAT/VALUE statements and common codebook patterns;
  * inventories likely format/lookup/codebook members;
  * emits context around candidate mappings;
  * DOES NOT assume 1=Yes or 2=No;
  * DOES NOT inspect/classify the disputed Contract+PBP population;
  * DOES NOT reconstruct payments, impute, write DB rows, or authorize ledger use.
"""

from __future__ import annotations
import csv, hashlib, io, json, re, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("data/raw/cms/medicare_partd/pbp_benefits")
OUT = ROOT / "validation" / "mrx_drug_ben_yn_code_mapping_search_v0_1"
YEARS = range(2015, 2025)
TEXT_EXTS = {
    ".txt",".csv",".tsv",".tab",".dat",".sas",".sas7bdat",".sql",".xml",
    ".html",".htm",".md",".json",".yaml",".yml",".log",".lst",".fmt"
}
FIELD_PATTERNS = [
    re.compile(r"mrx_drug_ben_yn", re.I),
    re.compile(r"MRx\s+Drug\s+Benefit\s+YN", re.I),
    re.compile(r"MRx\s+Drug\s+Benefit", re.I),
]
MAPPING_PATTERNS = [
    re.compile(r"\b1\b\s*(?:=|:|-|means?|is)\s*['\"]?\s*(yes|no|y|n)\b", re.I),
    re.compile(r"\b2\b\s*(?:=|:|-|means?|is)\s*['\"]?\s*(yes|no|y|n)\b", re.I),
    re.compile(r"['\"]?(yes|no|y|n)['\"]?\s*(?:=|:|-)\s*\b[12]\b", re.I),
    re.compile(r"\bvalue\b.{0,120}\b[12]\b", re.I | re.S),
    re.compile(r"\bformat\b.{0,120}\b[12]\b", re.I | re.S),
]
LIKELY_MEMBER = re.compile(
    r"(format|lookup|code|value|label|layout|dict|data.?element|readme|spec|mrx|drug)",
    re.I
)

csv.field_size_limit(min(sys.maxsize, 10_000_000))

def one_zip(year):
    z = sorted((ROOT / str(year)).glob("*.zip"))
    if len(z) != 1:
        raise RuntimeError(f"CY{year}: expected exactly one source ZIP; found {len(z)}")
    return z[0]

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

def ctx(text, start, end, radius=500):
    a=max(0,start-radius); b=min(len(text),end+radius)
    return re.sub(r"\s+"," ",text[a:b].replace("\x00"," ")).strip()

def write_csv(path, rows, fields):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    field_hits=[]; mapping_hits=[]; inventory=[]; years=[]; errors=[]

    for year in YEARS:
        try:
            zp=one_zip(year)
            member_count=searched=0
            field_members=set(); mapping_members=set()
            with zipfile.ZipFile(zp) as z:
                bad=z.testzip()
                if bad is not None:
                    raise RuntimeError(f"ZIP integrity failure at {bad}")
                for info in z.infolist():
                    if info.is_dir(): continue
                    member_count += 1
                    name=info.filename
                    if LIKELY_MEMBER.search(name):
                        inventory.append({
                            "year":year,"member_name":name,
                            "bytes":info.file_size,
                            "filename_reason":"format/lookup/code/value/label/layout/dictionary/spec/MRx/drug hint"
                        })
                    if Path(name).suffix.lower() not in TEXT_EXTS:
                        continue
                    searched += 1
                    try:
                        text=decode(z.read(info))
                        if text is None: continue

                        local_field_spans=[]
                        for pat in FIELD_PATTERNS:
                            for m in pat.finditer(text):
                                local_field_spans.append((m.start(),m.end()))
                                field_hits.append({
                                    "year":year,"member_name":name,
                                    "matched_text":m.group(0),
                                    "context":ctx(text,m.start(),m.end())
                                })
                                field_members.add(name)

                        # Candidate mapping syntax anywhere in likely metadata members,
                        # and especially within 1500 chars of a field reference.
                        likely = bool(LIKELY_MEMBER.search(name))
                        for pat in MAPPING_PATTERNS:
                            for m in pat.finditer(text):
                                near_field = any(abs(m.start()-s) <= 1500 for s,e in local_field_spans)
                                if likely or near_field:
                                    mapping_hits.append({
                                        "year":year,"member_name":name,
                                        "pattern":pat.pattern,
                                        "matched_text":m.group(0),
                                        "near_mrx_drug_ben_yn":str(near_field).upper(),
                                        "context":ctx(text,m.start(),m.end(),700)
                                    })
                                    mapping_members.add(name)
                                    if len(mapping_hits) > 20000:
                                        raise RuntimeError("mapping-hit safety cap exceeded")

                    except Exception as e:
                        errors.append(f"CY{year} {name}: {type(e).__name__}: {e}")

            years.append({
                "year":year,"source_zip":str(zp),"sha256":sha256_file(zp),
                "members":member_count,"text_members_searched":searched,
                "members_with_field_reference":len(field_members),
                "members_with_candidate_mapping_syntax":len(mapping_members),
            })
        except Exception as e:
            errors.append(f"CY{year}: {type(e).__name__}: {e}")

    near=[r for r in mapping_hits if r["near_mrx_drug_ben_yn"]=="TRUE"]
    checks={
        "all_ten_years_searched":len(years)==10,
        "no_source_search_errors":len(errors)==0,
        "all_source_zips_have_members":len(years)==10 and all(r["members"]>0 for r in years),
        "field_reference_found":len(field_hits)>0,
    }
    overall=all(checks.values())

    write_csv(OUT/"mrx_drug_ben_yn_field_reference_hits.csv",field_hits,
              ["year","member_name","matched_text","context"])
    write_csv(OUT/"mrx_drug_ben_yn_candidate_mapping_hits.csv",mapping_hits,
              ["year","member_name","pattern","matched_text","near_mrx_drug_ben_yn","context"])
    write_csv(OUT/"mrx_drug_ben_yn_candidate_member_inventory.csv",inventory,
              ["year","member_name","bytes","filename_reason"])
    write_csv(OUT/"mrx_drug_ben_yn_code_mapping_year_summary.csv",years,
              ["year","source_zip","sha256","members","text_members_searched",
               "members_with_field_reference","members_with_candidate_mapping_syntax"])

    report={
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "boundary":"Evidence discovery only; no code mapping is assumed or applied.",
        "field_reference_hits":len(field_hits),
        "candidate_mapping_hits":len(mapping_hits),
        "candidate_mapping_hits_near_field":len(near),
        "candidate_inventory_rows":len(inventory),
        "checks":checks,"errors":errors,"overall":"PASS" if overall else "FAIL"
    }
    (OUT/"mrx_drug_ben_yn_code_mapping_search_report.json").write_text(
        json.dumps(report,indent=2),encoding="utf-8"
    )

    print("CMS MEDICARE PART D PBP MRx DRUG BENEFIT Y/N CODE-MAPPING SEARCH v0.1")
    print("="*76)
    print(f"Generated UTC: {report['generated_utc']}\n")
    print("BOUNDARY\n"+"-"*76)
    print("Evidence discovery only. No 1/2 meaning is assumed or applied.")
    print("The disputed Contract+PBP population is not inspected or classified.\n")
    print("YEAR SEARCH\n"+"-"*76)
    for r in years:
        print(
            f"CY{r['year']}: members={r['members']:,} | text searched={r['text_members_searched']:,} | "
            f"field-ref members={r['members_with_field_reference']:,} | "
            f"mapping-syntax members={r['members_with_candidate_mapping_syntax']:,}"
        )
    print("\nRESULTS\n"+"-"*76)
    print(f"Field-reference hits: {len(field_hits):,}")
    print(f"Candidate mapping-syntax hits: {len(mapping_hits):,}")
    print(f"Candidate mapping hits within 1,500 chars of field reference: {len(near):,}")
    print(f"Candidate metadata/codebook inventory rows: {len(inventory):,}")

    if near:
        print("\nNEAR-FIELD CANDIDATE MAPPINGS (first 30)")
        print("-"*76)
        for r in near[:30]:
            print(f"CY{r['year']} | {r['member_name']} | {r['matched_text']} | {r['context']}")

    print("\nCHECKS\n"+"-"*76)
    for k,v in checks.items():
        print(f"{k.replace('_',' ')}: {'PASS' if v else 'FAIL'}")
    print("\nERRORS\n"+"-"*76)
    print("None" if not errors else "\n".join(errors))
    print("\nOVERALL\n"+"-"*76)
    print("OVERALL:", "PASS" if overall else "FAIL")
    print(f"\nOutputs: {OUT}")
    return 0 if overall else 1

if __name__=="__main__":
    raise SystemExit(main())
