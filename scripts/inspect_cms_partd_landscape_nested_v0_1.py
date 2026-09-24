#!/usr/bin/env python3
"""Read-only diagnostic of CMS Landscape outer/nested packaging."""
from __future__ import annotations
import csv, io, re, sys, zipfile
from pathlib import Path

ARCHIVE=Path("data/raw/cms/medicare_partd/landscape/cy2006-cy2025-landscape-files.zip")
OUT=Path("data/raw/cms/medicare_partd/landscape/validation/landscape_nested_diagnostic_v0_1")
TARGET=range(2015,2025)

def years(s):
    return sorted(set(int(x) for x in re.findall(r"(?<!\d)(20(?:1[5-9]|2[0-4]))(?!\d)",s)))

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    if not ARCHIVE.exists() or not zipfile.is_zipfile(ARCHIVE):
        print(f"ERROR: archive unavailable/not ZIP: {ARCHIVE}",file=sys.stderr); return 2
    with zipfile.ZipFile(ARCHIVE) as z:
        for i in z.infolist():
            if i.is_dir(): continue
            oy=years(i.filename)
            row={"outer_member":i.filename,"outer_year_tokens":";".join(map(str,oy)),
                 "outer_bytes":i.file_size,"is_zip":Path(i.filename).suffix.lower()==".zip",
                 "nested_member_count":"","nested_year_tokens":"","nested_sample":""}
            if row["is_zip"]:
                try:
                    b=z.read(i)
                    with zipfile.ZipFile(io.BytesIO(b)) as n:
                        names=[x.filename for x in n.infolist() if not x.is_dir()]
                    ny=sorted(set(y for name in names for y in years(name)))
                    row["nested_member_count"]=len(names)
                    row["nested_year_tokens"]=";".join(map(str,ny))
                    row["nested_sample"]=" || ".join(names[:8])
                except Exception as e:
                    row["nested_sample"]=f"ERROR {type(e).__name__}: {e}"
            rows.append(row)
    fields=list(rows[0])
    with (OUT/"cms_partd_landscape_nested_diagnostic.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    print("CMS PART D LANDSCAPE NESTED PACKAGING DIAGNOSTIC v0.1")
    print("="*72)
    for r in rows:
        if any(str(y) in r["outer_member"] for y in TARGET) or r["outer_year_tokens"]:
            print(f"\nOUTER: {r['outer_member']}")
            print(f"  outer year tokens: {r['outer_year_tokens'] or '(none)'}")
            print(f"  nested members: {r['nested_member_count']}")
            print(f"  nested year tokens: {r['nested_year_tokens'] or '(none)'}")
            print(f"  sample: {r['nested_sample']}")
    print(f"\nOutput: {OUT/'cms_partd_landscape_nested_diagnostic.csv'}")
    print("OVERALL: PASS (diagnostic completed; no semantic certification)")
    return 0
if __name__=="__main__":
    sys.exit(main())
