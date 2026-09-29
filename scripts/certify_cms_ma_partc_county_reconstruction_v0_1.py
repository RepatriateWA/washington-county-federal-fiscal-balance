#!/usr/bin/env python
"""Certify county aggregation of certified CMS MA Part C reconstruction v0.2."""
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
IN=ROOT/"data/raw/cms/medicare_advantage/validation/payment_reconstruction_v0_2"
CELLS=IN/"cms_ma_partc_payment_reconstruction_cells.csv"
ANNUAL=IN/"cms_ma_partc_payment_reconstruction_calendar_year.csv"
OUT=ROOT/"data/raw/cms/medicare_advantage/validation/partc_county_reconstruction_v0_1"
WA={"53001":"Adams","53003":"Asotin","53005":"Benton","53007":"Chelan","53009":"Clallam","53011":"Clark","53013":"Columbia","53015":"Cowlitz","53017":"Douglas","53019":"Ferry","53021":"Franklin","53023":"Garfield","53025":"Grant","53027":"Grays Harbor","53029":"Island","53031":"Jefferson","53033":"King","53035":"Kitsap","53037":"Kittitas","53039":"Klickitat","53041":"Lewis","53043":"Lincoln","53045":"Mason","53047":"Okanogan","53049":"Pacific","53051":"Pend Oreille","53053":"Pierce","53055":"San Juan","53057":"Skagit","53059":"Skamania","53061":"Snohomish","53063":"Spokane","53065":"Stevens","53067":"Thurston","53069":"Wahkiakum","53071":"Walla Walla","53073":"Whatcom","53075":"Whitman","53077":"Yakima"}
EXPECTED={**{y:12 for y in range(2015,2024)},2024:9}
TOL=.01

def norm_name(x):
    s=str(x).strip().lower()
    if s.endswith(" county"): s=s[:-7]
    return " ".join(s.split())

def check(rows,name,ok,obs):
    rows.append({"check":name,"status":"PASS" if ok else "FAIL","observed":obs})

def main():
    print("="*100)
    print("CMS MEDICARE ADVANTAGE PART C COUNTY RECONSTRUCTION CERTIFICATION v0.1")
    print("="*100)
    print("READ-ONLY; no source modification, PMPM reconstruction, imputation, DB writes, or ledger inclusion.\n")
    if not CELLS.exists() or not ANNUAL.exists():
        raise FileNotFoundError(f"Missing certified inputs: {CELLS} / {ANNUAL}")
    OUT.mkdir(parents=True,exist_ok=True)
    c=pd.read_csv(CELLS,dtype={"fips_code":str,"plan_id":str},low_memory=False)
    a=pd.read_csv(ANNUAL,low_memory=False)
    req={"period","payment_year","county","fips_code","enrollment","ab_dollars","rebate_dollars","partc_dollars"}
    missing=req-set(c.columns)
    if missing: raise KeyError(f"Missing cell columns: {sorted(missing)}")
    c["fips_code"]=c["fips_code"].fillna("").str.strip().str.zfill(5)
    c["county"]=c["county"].fillna("").str.strip()
    c["payment_year"]=pd.to_numeric(c["payment_year"],errors="raise").astype(int)
    for x in ["enrollment","ab_dollars","rebate_dollars","partc_dollars"]:
        c[x]=pd.to_numeric(c[x],errors="raise")
    canonical=set(WA)
    bad_fips=sorted(set(c.fips_code)-canonical)
    mismatch=c[c.apply(lambda r:r.fips_code in WA and norm_name(r.county)!=norm_name(WA[r.fips_code]),axis=1)]
    geo=(c.groupby(["fips_code","county"],as_index=False)
         .agg(cell_rows=("period","size"),first_period=("period","min"),last_period=("period","max"),
              member_months=("enrollment","sum"),partc_dollars=("partc_dollars","sum")))
    geo["canonical_county"]=geo.fips_code.map(WA)
    cy=(c.groupby(["payment_year","fips_code","county"],as_index=False)
        .agg(months_represented=("period","nunique"),reconstructed_member_months=("enrollment","sum"),
             ab_dollars=("ab_dollars","sum"),rebate_dollars=("rebate_dollars","sum"),
             partc_dollars=("partc_dollars","sum"),reconstruction_cell_rows=("period","size")))
    cy["year_completeness"]=cy.payment_year.map(lambda y:"COMPLETE" if y<=2023 else "PARTIAL_JAN_SEP")
    cy["dollar_status"]="RECONSTRUCTED"
    cy["geography_basis"]="CMS_BENEFICIARY_COUNTY_OF_RESIDENCE"
    cy["methodology_version"]="CMS-MA-PARTC-COUNTY-CERT-v0.1"
    sums=(cy.groupby("payment_year",as_index=False)
          .agg(counties=("fips_code","nunique"),reconstructed_member_months=("reconstructed_member_months","sum"),
               ab_dollars=("ab_dollars","sum"),rebate_dollars=("rebate_dollars","sum"),partc_dollars=("partc_dollars","sum")))
    yearcol="payment_year" if "payment_year" in a.columns else "year"
    pcol="partc_dollars" if "partc_dollars" in a.columns else "reconstructed_partc_dollars"
    a[yearcol]=pd.to_numeric(a[yearcol],errors="raise").astype(int)
    a[pcol]=pd.to_numeric(a[pcol],errors="raise")
    # Rename county aggregates before merge so columns that also exist in the
    # certified annual control do not receive pandas _x/_y suffixes.
    sums = sums.rename(columns={
        "reconstructed_member_months": "county_reconstructed_member_months",
        "ab_dollars": "county_ab_dollars",
        "rebate_dollars": "county_rebate_dollars",
        "partc_dollars": "county_partc_dollars",
    })
    recon=a.merge(sums,left_on=yearcol,right_on="payment_year",how="outer",validate="one_to_one",indicator=True)
    recon["partc_difference"]=recon["county_partc_dollars"]-recon[pcol]
    rows=[]
    check(rows,"Payment years exactly CY2015-CY2024",set(c.payment_year)==set(EXPECTED),str(sorted(set(c.payment_year))))
    check(rows,"All reconstructed cells use canonical WA county FIPS",not bad_fips,"NONE" if not bad_fips else ",".join(bad_fips))
    check(rows,"All 39 canonical WA counties observed",set(c.fips_code)==canonical,f"{len(set(c.fips_code)&canonical)}/39")
    check(rows,"County name agrees with canonical FIPS",len(mismatch)==0,f"{len(mismatch)} mismatched rows")
    per={y:c.loc[c.payment_year==y,"period"].nunique() for y in EXPECTED}
    check(rows,"Calendar-year period coverage matches v0.2 boundary",per==EXPECTED,str(per))
    comp=(c.ab_dollars+c.rebate_dollars-c.partc_dollars).abs().max()
    check(rows,"Cell dollar component identity",comp<TOL,f"max abs difference=${comp:.9f}")
    check(rows,"Annual controls reconcile one-to-one",(recon["_merge"]=="both").all(),str(recon["_merge"].value_counts().to_dict()))
    md=recon.partc_difference.abs().max()
    check(rows,"County Part C sums reconcile to certified annual v0.2 controls",md<TOL,f"max abs difference=${md:.9f}")
    counts=dict(zip(sums.payment_year,sums.counties))
    check(rows,"All 39 counties represented in each payment year",all(int(v)==39 for v in counts.values()),str({int(k):int(v) for k,v in counts.items()}))
    checks=pd.DataFrame(rows)
    status="PASS" if (checks.status=="PASS").all() else "FAIL"
    cy.to_csv(OUT/"cms_ma_partc_county_year_reconstruction_v0_1.csv",index=False)
    geo.to_csv(OUT/"cms_ma_partc_county_geography_v0_1.csv",index=False)
    recon.to_csv(OUT/"cms_ma_partc_county_reconciliation_v0_1.csv",index=False)
    checks.to_csv(OUT/"cms_ma_partc_county_checks_v0_1.csv",index=False)
    lines=["="*100,"CMS MEDICARE ADVANTAGE PART C COUNTY RECONSTRUCTION CERTIFICATION v0.1","="*100,"",
           "Boundary: downstream certification of certified v0.2 cells; no PMPM reconstruction or imputation.",
           "Dollar status: RECONSTRUCTED, not directly observed CMS county expenditure.",
           "CY2015-CY2023 COMPLETE within certified HMO/HMOPOS + Local PPO scope; CY2024 PARTIAL_JAN_SEP.","",
           "CHECKS","-"*100]
    lines += [f"{r.status:4s} | {r.check} | {r.observed}" for r in checks.itertuples()]
    lines += ["",f"OVERALL COUNTY RECONSTRUCTION CERTIFICATION: {status}","",
              "PASS certifies canonical WA county geography and reconciliation of county sums to certified v0.2 annual controls.",
              "It does not expand the upstream reconstruction scope or authorize final ledger inclusion."]
    report="\n".join(lines)+"\n"
    (OUT/"cms_ma_partc_county_reconstruction_report_v0_1.txt").write_text(report,encoding="utf-8")
    print(report)
    print("Evidence written:")
    for p in sorted(OUT.iterdir()): print(" ",p)

if __name__=="__main__":
    main()
