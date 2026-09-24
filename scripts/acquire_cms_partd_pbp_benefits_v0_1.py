#!/usr/bin/env python3
"""
Acquire official CMS PBP Benefits Data for CY2015-CY2024.

Discovery is performed from the CMS Benefits Data landing page, then each
selected CMS detail page is inspected for its downloadable ZIP. Selection:
2015-2017 annual release; 2018-2020 Q4; 2021 latest dated update shown by CMS;
2022 latest dated update shown by CMS; 2023-2024 Q4.

Read/acquisition only. No semantic classification, linkage, imputation,
payment propagation, reconstruction, DB writes, or ledger inclusion.
"""
from __future__ import annotations
import csv, hashlib, html, re, sys, urllib.parse, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path

LANDING="https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-advantagepart-d-contract-and-enrollment-data/benefits-data"
OUT=Path("data/raw/cms/medicare_partd/pbp_benefits")
YEARS=range(2015,2025)
UA="Mozilla/5.0 WCFFBP-CMS-PBP-Acquisition/0.1"

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=120) as r:
        return r.read(),r.geturl()

def links(page,base):
    text=page.decode("utf-8","replace")
    out=[]
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',text,re.I|re.S):
        href=html.unescape(m.group(1)); label=re.sub(r"<[^>]+>"," ",m.group(2))
        label=html.unescape(re.sub(r"\s+"," ",label)).strip()
        out.append((label,urllib.parse.urljoin(base,href)))
    return out

def choose(year,cands):
    def score(item):
        label,url=item; u=label.upper()
        sc=0
        if str(year) in u: sc+=100
        if year in (2018,2019,2020,2023,2024) and ("QUARTER 4" in u or "Q4" in u):sc+=50
        if year==2021:
            # CMS landing currently exposes 07/01 and 08/02 updates; prefer later.
            if "08/02/2021" in u:sc+=60
            elif "07/01/2021" in u:sc+=50
            elif "04/01/2021" in u:sc+=40
            elif "1/12/2021" in u:sc+=30
            elif "10/14/2020" in u:sc+=20
        if year==2022:
            if "07/01/2022" in u:sc+=60
            elif "01/03/2022" in u:sc+=50
            elif "10/04/2021" in u:sc+=40
        if "JSON" in u:sc-=100
        return sc
    return max(cands,key=score)

def sha256(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    landing,final=get(LANDING)
    ls=links(landing,final)
    manifest=[]; errors=[]
    for y in YEARS:
        c=[x for x in ls if str(y) in x[0] and "PBP BENEFITS" in x[0].upper()]
        if not c:
            errors.append((y,"No CMS detail-page candidate discovered"));continue
        label,detail=choose(y,c)
        try:
            page,detail_final=get(detail)
            dl=[x for x in links(page,detail_final) if ".zip" in x[1].lower()]
            # Prefer PBP-benefits ZIPs; exclude JSON if present.
            dl2=[x for x in dl if "pbp" in x[1].lower() and "benefit" in x[1].lower() and "json" not in (x[0]+" "+x[1]).lower()]
            if dl2:dl=dl2
            if len(dl)!=1:
                raise RuntimeError(f"Expected exactly one non-JSON PBP ZIP; found {len(dl)}: {dl}")
            dlabel,url=dl[0]
            raw,resolved=get(url)
            fn=Path(urllib.parse.urlparse(resolved).path).name or f"pbp-benefits-{y}.zip"
            yd=OUT/str(y);yd.mkdir(exist_ok=True)
            p=yd/fn;p.write_bytes(raw)
            if not zipfile.is_zipfile(p):raise RuntimeError("download is not a ZIP")
            with zipfile.ZipFile(p) as z:
                bad=z.testzip(); members=len(z.infolist())
            if bad:raise RuntimeError("ZIP integrity failure: "+bad)
            manifest.append(dict(
                year=y,selected_release_title=label,detail_page=detail_final,
                source_url=url,resolved_download_url=resolved,local_path=str(p),
                bytes=p.stat().st_size,sha256=sha256(p),zip_members=members,
                zip_integrity="PASS",retrieved_utc=datetime.now(timezone.utc).isoformat()
            ))
            print(f"CY{y}: PASS | {fn} | {p.stat().st_size:,} bytes | {members} members")
        except Exception as e:
            errors.append((y,f"{type(e).__name__}: {e}"))
            print(f"CY{y}: FAIL | {errors[-1][1]}")
    mp=OUT/"cms_pbp_benefits_acquisition_manifest.csv"
    fields=["year","selected_release_title","detail_page","source_url","resolved_download_url",
            "local_path","bytes","sha256","zip_members","zip_integrity","retrieved_utc"]
    with mp.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(manifest)
    ep=OUT/"cms_pbp_benefits_acquisition_errors.csv"
    with ep.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f);w.writerow(["year","error"]);w.writerows(errors)
    got={x["year"] for x in manifest}
    checks=[
        ("all CY2015-CY2024 acquired",got==set(YEARS)),
        ("exactly ten selected source ZIPs",len(manifest)==10),
        ("all selected ZIPs pass integrity",all(x["zip_integrity"]=="PASS" for x in manifest)),
        ("no acquisition errors",not errors),
    ]
    report=[
        "CMS PBP BENEFITS ACQUISITION v0.1","="*76,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"CMS landing page: {LANDING}","",
        "BOUNDARY","-"*76,
        "Official CMS Benefits Data only. Acquisition and preservation only.",
        "No semantic classification, linkage, imputation, payment propagation,",
        "reconstruction, DB writes, or ledger inclusion.","",
        "CHECKS","-"*76,
        *[f"{k}: {'PASS' if v else 'FAIL'}" for k,v in checks],"",
        "ERRORS","-"*76
    ]
    if errors:
        report += [f"CY{y}: {e}" for y,e in errors]
    else:
        report += ["None"]
    report += ["","OVERALL","-"*76,f"OVERALL: {'PASS' if all(v for _,v in checks) else 'FAIL'}",
               f"Manifest: {mp}"]
    txt="\n".join(report)+"\n"
    (OUT/"cms_pbp_benefits_acquisition_report.txt").write_text(txt,encoding="utf-8")
    print("\n"+txt)
    return 0 if all(v for _,v in checks) else 1
if __name__=="__main__":sys.exit(main())
