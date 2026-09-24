#!/usr/bin/env python3
"""
Diagnose CMS PBP Benefits pbp_mrx.txt identifiers/header structure CY2015-CY2024.

Read-only diagnostic. Prints the first source rows, the structural-profiler
chosen header, normalized field names, and identifier-like fields. No status
classification or analytical inference.
"""
from __future__ import annotations
import csv, io, re, sys, zipfile
from pathlib import Path

ROOT=Path("data/raw/cms/medicare_partd/pbp_benefits")
YEARS=range(2015,2025)
csv.field_size_limit(min(sys.maxsize,10_000_000))

def clean(x): return "" if x is None else str(x).strip()
def norm(x): return re.sub(r"[^A-Z0-9]+","_",clean(x).upper()).strip("_")

def decode(data):
    for enc in ("utf-8-sig","cp1252","latin-1"):
        try:return data.decode(enc)
        except UnicodeDecodeError:pass
    raise RuntimeError("decode failed")

def parse(text):
    sample=text[:65536]
    try:d=csv.Sniffer().sniff(sample,delimiters=",|\t;")
    except csv.Error:d=csv.excel
    return list(csv.reader(io.StringIO(text,newline=""),d)), repr(d.delimiter)

def choose_header(raw):
    cand=[]
    for i,row in enumerate(raw[:60]):
        vals=[clean(x) for x in row]
        nonblank=sum(bool(x) for x in vals)
        textual=sum(bool(x) and not re.fullmatch(r"[-+]?\d+(?:\.\d+)?",x) for x in vals)
        identifierish=sum(any(k in norm(x) for k in ("CONTRACT","PBP","PLAN","DRUG","PART_D","BENEFIT","RX"))
                          for x in vals if x)
        cand.append((identifierish,nonblank,textual,-i,i,vals))
    *_,idx,h=max(cand)
    while h and not h[-1]:h.pop()
    return idx,h

for y in YEARS:
    zips=list((ROOT/str(y)).glob("*.zip"))
    print("\n"+"="*100)
    print(f"CY{y}")
    if len(zips)!=1:
        print(f"ERROR: expected one ZIP, found {len(zips)}");continue
    with zipfile.ZipFile(zips[0]) as z:
        names=[n for n in z.namelist() if Path(n).name.lower()=="pbp_mrx.txt"]
        if len(names)!=1:
            print(f"ERROR: pbp_mrx.txt count={len(names)}");continue
        text=decode(z.read(names[0]))
    rows,delim=parse(text)
    print(f"ZIP: {zips[0]}")
    print(f"MEMBER: {names[0]}")
    print(f"DETECTED DELIMITER: {delim}")
    print(f"PARSED ROWS: {len(rows):,}")
    for i,r in enumerate(rows[:5]):
        print(f"RAW ROW {i}: {r[:25]}")
    hi,h=choose_header(rows)
    print(f"STRUCTURAL-PROFILER HEADER ROW: {hi}")
    print(f"HEADER ({len(h)} fields): {h}")
    print("NORMALIZED:")
    print([norm(x) for x in h])
    ids=[x for x in h if any(k in norm(x) for k in ("CONTRACT","PBP","PLAN","BID","H_NUMBER","MRX"))]
    print(f"IDENTIFIER/MRX-LIKE FIELDS: {ids}")
