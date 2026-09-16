from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path("data/raw/cms/medicare_advantage")

CPSC_ZIP = ROOT / "enrollment/2014/10/cpsc-enrollment-2014-10.zip"
SCC_ZIP = ROOT / "enrollment_controls/2014/10/scc-enrollment-ma-2014-10.zip"
SNP_ZIP = ROOT / "snp/2014/10/snp-2014-10.zip"
PAYMENT_ZIP = ROOT / "plan_payment/2014/2014paymentdata.zip"

OUTDIR = (
    ROOT
    / "validation"
    / "2014"
    / "10"
    / "partc_reconstruction"
)

OUTDIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# HELPERS
# ============================================================

def read_csv_zip(path: Path, member: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        raw = z.read(member)

    for enc in ("cp1252", "latin1", "utf-8-sig"):
        try:
            return pd.read_csv(
                io.BytesIO(raw),
                dtype=str,
                encoding=enc,
                keep_default_na=False,
            )
        except UnicodeDecodeError:
            continue

    raise RuntimeError(f"Could not decode {member}")


def norm_plan_type(value) -> str:
    s = str(value).strip().upper()

    if s in {"HMO", "HMO/HMOPOS", "HMO/HMO-POS"}:
        return "HMO"

    if s == "LOCAL PPO":
        return "LOCAL PPO"

    return s


def norm_snp_type(value) -> str:
    s = str(value).strip().upper()

    if not s or s in {"NAN", "NONE"}:
        return "NON-SNP"

    if s == "DUAL-ELIGIBLE":
        return "DUAL-ELIGIBLE"

    if s == "INSTITUTIONAL":
        return "INSTITUTIONAL"

    if s in {
        "CHRONIC OR DISABLING CONDITION",
        "CHRONIC/DISABLING",
        "CHRONIC OR DISABLING",
    }:
        return "CHRONIC"

    return s


def money(x) -> str:
    return f"${x:,.2f}"


# ============================================================
# 1. CMS PART C COUNTY PAYMENT PUF
# ============================================================

with zipfile.ZipFile(PAYMENT_ZIP) as z:
    raw = z.read("2014PartCCountyLevel.xlsx")

puf = pd.read_excel(
    io.BytesIO(raw),
    sheet_name="result.srx",
    header=2,
)

# Normalize historical CMS header whitespace, including embedded line breaks.
puf.columns = [
    " ".join(str(c).split())
    for c in puf.columns
]

# Historical 2014 workbook uses this spelling.
risk_col = "Average Part Risk Score"

required_puf = [
    "County Code",
    "State Abbreviation",
    "County Name",
    "Plan Type",
    "SNP Plan Type",
    risk_col,
    "Average AB PM/PM Payment",
    "Average Rebate PM/PM Payment",
]

missing = [c for c in required_puf if c not in puf.columns]

if missing:
    raise RuntimeError(
        f"Missing expected payment PUF columns: {missing}"
    )

puf = puf[
    puf["State Abbreviation"].astype(str).str.strip().eq("WA")
].copy()

puf["county_norm"] = (
    puf["County Name"]
    .astype(str)
    .str.strip()
    .str.upper()
)

puf["plan_type_norm"] = puf["Plan Type"].map(norm_plan_type)

puf["snp_type_norm"] = (
    puf["SNP Plan Type"]
    .fillna("")
    .map(norm_snp_type)
)

puf = puf[
    puf["plan_type_norm"].isin(["HMO", "LOCAL PPO"])
].copy()

for col in (
    risk_col,
    "Average AB PM/PM Payment",
    "Average Rebate PM/PM Payment",
):
    puf[col] = pd.to_numeric(
        puf[col],
        errors="coerce",
    )

if puf[
    [
        risk_col,
        "Average AB PM/PM Payment",
        "Average Rebate PM/PM Payment",
    ]
].isna().any().any():
    raise RuntimeError(
        "Target WA payment PUF contains nonnumeric payment fields."
    )

# CMS-documented reconstruction:
# actual A/B PMPM = standardized A/B PMPM * average risk score
# total Part C PMPM = actual A/B PMPM + published rebate PMPM

puf["ab_actual_pmpm"] = (
    puf["Average AB PM/PM Payment"]
    * puf[risk_col]
)

puf["partc_pmpm"] = (
    puf["ab_actual_pmpm"]
    + puf["Average Rebate PM/PM Payment"]
)

payment_key = [
    "county_norm",
    "plan_type_norm",
    "snp_type_norm",
]

duplicate_payment_keys = int(
    puf.duplicated(payment_key, keep=False).sum()
)

if duplicate_payment_keys:
    raise RuntimeError(
        f"Duplicate payment keys found: {duplicate_payment_keys}"
    )


# ============================================================
# 2. SNP SUBTYPE RESOLUTION
# ============================================================

with zipfile.ZipFile(SNP_ZIP) as z:
    xls_member = next(
        n for n in z.namelist()
        if n.lower().endswith(".xls")
    )
    snp_raw = z.read(xls_member)

snp = pd.read_excel(
    io.BytesIO(snp_raw),
    sheet_name="Special Needs Plan Report",
    header=16,
    dtype=str,
)

snp.columns = [
    str(c).replace("\n", " ").strip()
    for c in snp.columns
]

snp = snp.rename(columns={
    "Contract Number": "contract_id",
    "Plan ID": "plan_id",
    "Special Needs Plan Type": "snp_type",
})

for col in ("contract_id", "plan_id", "snp_type"):
    snp[col] = (
        snp[col]
        .fillna("")
        .astype(str)
        .str.strip()
    )

# Exclude CMS synthetic suppression identities.
snp = snp[
    ~snp["contract_id"].str.upper().eq("UNDER-11")
    & snp["contract_id"].ne("")
    & snp["plan_id"].ne("")
].copy()

snp_resolution = (
    snp.groupby(["contract_id", "plan_id"])["snp_type"]
    .agg(
        lambda x: sorted({
            norm_snp_type(v)
            for v in x
            if str(v).strip()
        })
    )
    .reset_index(name="snp_types")
)

snp_resolution["type_count"] = (
    snp_resolution["snp_types"].map(len)
)

snp_resolution["resolved_snp_type"] = (
    snp_resolution["snp_types"].map(
        lambda x: x[0] if len(x) == 1 else None
    )
)


# ============================================================
# 3. CPSC PUBLISHED ENROLLMENT
# ============================================================

contract = read_csv_zip(
    CPSC_ZIP,
    "CPSC_Contract_Info_2014_10.csv",
)

enroll = read_csv_zip(
    CPSC_ZIP,
    "CPSC_Enrollment_Info_2014_10.csv",
)

contract = contract.rename(columns={
    "Contract ID": "contract_id",
    "Plan ID": "plan_id",
    "Plan Type": "plan_type",
    "SNP Plan": "snp_plan",
    "EGHP": "eghp",
})

enroll = enroll.rename(columns={
    "Contract Number": "contract_id",
    "Plan ID": "plan_id",
    "State": "state",
    "County": "county",
    "Enrollment": "enrollment",
})

for df in (contract, enroll):
    df["contract_id"] = (
        df["contract_id"]
        .astype(str)
        .str.strip()
    )
    df["plan_id"] = (
        df["plan_id"]
        .astype(str)
        .str.strip()
    )

contract["plan_type_norm"] = (
    contract["plan_type"].map(norm_plan_type)
)

enroll = enroll.merge(
    contract[
        [
            "contract_id",
            "plan_id",
            "plan_type_norm",
            "snp_plan",
            "eghp",
        ]
    ],
    on=["contract_id", "plan_id"],
    how="left",
    validate="many_to_one",
)

cpsc = enroll[
    enroll["state"].astype(str).str.strip().eq("WA")
    & enroll["plan_type_norm"].isin(["HMO", "LOCAL PPO"])
].copy()

cpsc["county_norm"] = (
    cpsc["county"]
    .astype(str)
    .str.strip()
    .str.upper()
)

cpsc["published_enrollment"] = pd.to_numeric(
    cpsc["enrollment"].replace({
        "*": "",
        ".": "",
        "": "",
    }),
    errors="coerce",
)

cpsc = cpsc.merge(
    snp_resolution[
        [
            "contract_id",
            "plan_id",
            "type_count",
            "resolved_snp_type",
        ]
    ],
    on=["contract_id", "plan_id"],
    how="left",
)

is_snp = (
    cpsc["snp_plan"]
    .astype(str)
    .str.strip()
    .str.upper()
    .eq("YES")
)

cpsc["snp_type_norm"] = "NON-SNP"

cpsc.loc[
    is_snp & cpsc["resolved_snp_type"].notna(),
    "snp_type_norm",
] = cpsc.loc[
    is_snp & cpsc["resolved_snp_type"].notna(),
    "resolved_snp_type",
]

cpsc["snp_resolution_missing"] = (
    is_snp
    & cpsc["resolved_snp_type"].isna()
)

published = cpsc[
    cpsc["published_enrollment"].notna()
].copy()


# ============================================================
# 4. EXACT PAYMENT FOR PUBLISHED CPSC ENROLLMENT
# ============================================================

payment_cols = payment_key + [
    "County Code",
    risk_col,
    "Average AB PM/PM Payment",
    "Average Rebate PM/PM Payment",
    "ab_actual_pmpm",
    "partc_pmpm",
]

published = published.merge(
    puf[payment_cols],
    on=payment_key,
    how="left",
    validate="many_to_one",
)

published_unlinked = int(
    published["partc_pmpm"].isna().sum()
)

published["payment_amount"] = (
    published["published_enrollment"]
    * published["partc_pmpm"]
)

published_enrollment = float(
    published["published_enrollment"].sum()
)

published_payment = float(
    published["payment_amount"].sum()
)

published_weighted_pmpm = (
    published_payment / published_enrollment
)

min_pmpm = float(puf["partc_pmpm"].min())
max_pmpm = float(puf["partc_pmpm"].max())


# ============================================================
# 5. SCC PUBLISHED SUBTOTAL
# ============================================================

with zipfile.ZipFile(SCC_ZIP) as z:
    csv_members = [
        n for n in z.namelist()
        if n.lower().endswith(".csv")
    ]

if len(csv_members) != 1:
    raise RuntimeError(
        f"Expected one SCC CSV; found {csv_members}"
    )

scc = read_csv_zip(
    SCC_ZIP,
    csv_members[0],
)

scc.columns = [str(c).strip() for c in scc.columns]

scc = scc[
    scc["State"].astype(str).str.strip().eq("WA")
].copy()

scc["plan_type_norm"] = (
    scc["Plan Type"].map(norm_plan_type)
)

scc = scc[
    scc["plan_type_norm"].isin(["HMO", "LOCAL PPO"])
].copy()

scc["county_norm"] = (
    scc["County"]
    .astype(str)
    .str.strip()
    .str.upper()
)

scc["published_enrollment"] = pd.to_numeric(
    scc["Enrolled"].replace({
        "": pd.NA,
        "*": pd.NA,
        ".": pd.NA,
    }),
    errors="coerce",
)

scc_published = float(
    scc["published_enrollment"].sum()
)

residual_enrollment = (
    scc_published - published_enrollment
)


# ============================================================
# 6. PRODUCT-SPECIFIC RESIDUAL
# ============================================================

cpsc_by_product = (
    published.groupby("plan_type_norm")
    ["published_enrollment"]
    .sum()
)

scc_by_product = (
    scc.groupby("plan_type_norm")
    ["published_enrollment"]
    .sum()
)

product_rows = []

for plan_type in ("HMO", "LOCAL PPO"):
    cpsc_n = float(cpsc_by_product.get(plan_type, 0))
    scc_n = float(scc_by_product.get(plan_type, 0))
    residual_n = scc_n - cpsc_n

    subset = published[
        published["plan_type_norm"].eq(plan_type)
    ]

    product_payment = float(
        subset["payment_amount"].sum()
    )

    product_enrollment = float(
        subset["published_enrollment"].sum()
    )

    weighted_pmpm = (
        product_payment / product_enrollment
        if product_enrollment
        else published_weighted_pmpm
    )

    product_puf = puf[
        puf["plan_type_norm"].eq(plan_type)
    ]

    product_min = float(
        product_puf["partc_pmpm"].min()
    )

    product_max = float(
        product_puf["partc_pmpm"].max()
    )

    product_rows.append({
        "plan_type_norm": plan_type,
        "cpsc_published": cpsc_n,
        "scc_published": scc_n,
        "residual_enrollment": residual_n,
        "published_weighted_pmpm": weighted_pmpm,
        "min_puf_pmpm": product_min,
        "max_puf_pmpm": product_max,
        "residual_payment_lower": (
            residual_n * product_min
        ),
        "residual_payment_central": (
            residual_n * weighted_pmpm
        ),
        "residual_payment_upper": (
            residual_n * product_max
        ),
    })

product_recon = pd.DataFrame(product_rows)

residual_payment_lower = float(
    product_recon["residual_payment_lower"].sum()
)

residual_payment_central = float(
    product_recon["residual_payment_central"].sum()
)

residual_payment_upper = float(
    product_recon["residual_payment_upper"].sum()
)


# ============================================================
# 7. RECONSTRUCTION RANGE
# ============================================================
#
# IMPORTANT:
#
# The SCC-CPSC residual is not treated as an independent second
# beneficiary population. It is treated as enrollment exposed by
# the more aggregated SCC representation but suppressed in the
# finer CPSC representation.
#
# The residual's exact hidden SNP/payment-cell composition cannot
# be recovered. Therefore:
#
# lower   = residual * minimum published WA product PMPM
# central = residual * published-enrollment-weighted product PMPM
# upper   = residual * maximum published WA product PMPM
#
# No CMS source enrollment value is modified or imputed.
# ============================================================

payment_lower = (
    published_payment
    + residual_payment_lower
)

payment_central = (
    published_payment
    + residual_payment_central
)

payment_upper = (
    published_payment
    + residual_payment_upper
)

uncertainty_width = (
    payment_upper - payment_lower
)

uncertainty_pct_central = (
    uncertainty_width / payment_central * 100
)

central_effective_pmpm = (
    payment_central / scc_published
)


# ============================================================
# 8. SUPPRESSED / MISSING-PAYMENT-CELL DIAGNOSTIC
# ============================================================

suppressed = cpsc[
    cpsc["published_enrollment"].isna()
].copy()

suppressed = suppressed.merge(
    puf[
        payment_key
        + ["partc_pmpm"]
    ],
    on=payment_key,
    how="left",
    validate="many_to_one",
)

suppressed["payment_cell_exists"] = (
    suppressed["partc_pmpm"].notna()
)

suppressed_rows = len(suppressed)

suppressed_with_payment_cell = int(
    suppressed["payment_cell_exists"].sum()
)

suppressed_without_payment_cell = int(
    (~suppressed["payment_cell_exists"]).sum()
)


# ============================================================
# 9. INVARIANTS
# ============================================================

checks = []


def check(name, condition, detail):
    checks.append((name, bool(condition), detail))


check(
    "CPSC published enrollment reproduces prior result",
    published_enrollment == 337886,
    f"{published_enrollment:,.0f}",
)

check(
    "SCC published enrollment reproduces prior result",
    scc_published == 339206,
    f"{scc_published:,.0f}",
)

check(
    "SCC-CPSC residual reproduces prior result",
    residual_enrollment == 1320,
    f"{residual_enrollment:+,.0f}",
)

check(
    "All published CPSC enrollment has a payment cell",
    published_unlinked == 0,
    f"{published_unlinked:,} unlinked rows",
)

check(
    "All SNP CPSC rows have resolved subtype",
    cpsc["snp_resolution_missing"].sum() == 0,
    (
        f"{cpsc['snp_resolution_missing'].sum():,} "
        "unresolved rows"
    ),
)

check(
    "Payment keys are unique",
    duplicate_payment_keys == 0,
    f"{duplicate_payment_keys:,} duplicates",
)

check(
    "Residual product components reconcile",
    product_recon["residual_enrollment"].sum()
    == residual_enrollment,
    (
        f"{product_recon['residual_enrollment'].sum():+,.0f}"
    ),
)

check(
    "Lower <= central",
    payment_lower <= payment_central,
    f"{money(payment_lower)} <= {money(payment_central)}",
)

check(
    "Central <= upper",
    payment_central <= payment_upper,
    f"{money(payment_central)} <= {money(payment_upper)}",
)

check(
    "Published payment <= lower corrected payment",
    published_payment <= payment_lower,
    f"{money(published_payment)} <= {money(payment_lower)}",
)

check(
    "Suppressed CPSC rows remain excluded from published count",
    (
        len(cpsc)
        == len(published) + len(suppressed)
    ),
    (
        f"{len(cpsc):,} = "
        f"{len(published):,} + {len(suppressed):,}"
    ),
)


# ============================================================
# 10. WRITE COMPACT EVIDENCE OUTPUTS
# ============================================================

published_out = published[
    [
        "county_norm",
        "contract_id",
        "plan_id",
        "plan_type_norm",
        "snp_type_norm",
        "published_enrollment",
        "County Code",
        risk_col,
        "Average AB PM/PM Payment",
        "Average Rebate PM/PM Payment",
        "ab_actual_pmpm",
        "partc_pmpm",
        "payment_amount",
    ]
].copy()

published_out.to_csv(
    OUTDIR / "published_payment_rows.csv",
    index=False,
)

product_recon.to_csv(
    OUTDIR / "product_residual_reconciliation.csv",
    index=False,
)

suppressed_out = (
    suppressed.groupby(
        [
            "county_norm",
            "plan_type_norm",
            "snp_type_norm",
            "payment_cell_exists",
        ],
        dropna=False,
    )
    .size()
    .reset_index(name="suppressed_rows")
)

suppressed_out.to_csv(
    OUTDIR / "suppressed_observation_summary.csv",
    index=False,
)


# ============================================================
# 11. REPORT
# ============================================================

lines = []

lines.append("=" * 78)
lines.append(
    "OCTOBER 2014 — WASHINGTON MEDICARE ADVANTAGE PART C RECONSTRUCTION"
)
lines.append("=" * 78)

lines.append("")
lines.append("SCOPE")
lines.append(
    "HMO/HMOPOS + Local PPO only; October 2014; Washington State"
)

lines.append("")
lines.append("PUBLISHED CPSC ENROLLMENT")
lines.append(
    f"Published enrollment:              "
    f"{published_enrollment:,.0f}"
)
lines.append(
    f"Published payment reconstruction:  "
    f"{money(published_payment)}"
)
lines.append(
    f"Published weighted PMPM:           "
    f"{money(published_weighted_pmpm)}"
)

lines.append("")
lines.append("SCC/CPSC SUPPRESSION RECONCILIATION")
lines.append(
    f"SCC published subtotal:            "
    f"{scc_published:,.0f}"
)
lines.append(
    f"CPSC published subtotal:           "
    f"{published_enrollment:,.0f}"
)
lines.append(
    f"SCC minus CPSC residual:           "
    f"{residual_enrollment:+,.0f}"
)

lines.append("")
lines.append("RESIDUAL BY PRODUCT")

for row in product_recon.itertuples(index=False):
    lines.append(
        f"{row.plan_type_norm:<10} "
        f"residual={row.residual_enrollment:+,.0f}  "
        f"weighted PMPM={money(row.published_weighted_pmpm)}  "
        f"range={money(row.min_puf_pmpm)}"
        f"–{money(row.max_puf_pmpm)}"
    )

lines.append("")
lines.append("SUPPRESSION-CORRECTED PAYMENT RANGE")
lines.append(
    f"Lower:                             "
    f"{money(payment_lower)}"
)
lines.append(
    f"Central:                           "
    f"{money(payment_central)}"
)
lines.append(
    f"Upper:                             "
    f"{money(payment_upper)}"
)
lines.append(
    f"Central effective PMPM:            "
    f"{money(central_effective_pmpm)}"
)
lines.append(
    f"Uncertainty width:                 "
    f"{money(uncertainty_width)}"
)
lines.append(
    f"Uncertainty / central:             "
    f"{uncertainty_pct_central:.6f}%"
)

lines.append("")
lines.append("SUPPRESSED CPSC OBSERVATIONS")
lines.append(
    f"Suppressed rows:                   "
    f"{suppressed_rows:,}"
)
lines.append(
    f"With published payment cell:       "
    f"{suppressed_with_payment_cell:,}"
)
lines.append(
    f"Without published payment cell:    "
    f"{suppressed_without_payment_cell:,}"
)

lines.append("")
lines.append("INVARIANTS")

for name, passed, detail in checks:
    lines.append(
        f"{'PASS' if passed else 'FAIL'}: "
        f"{name} — {detail}"
    )

passed_count = sum(1 for _, passed, _ in checks if passed)

lines.append("")
lines.append(
    f"RESULT: {passed_count}/{len(checks)} "
    "reconstruction checks PASS"
)

lines.append("")
lines.append("METHODOLOGICAL NOTES")
lines.append(
    "1. No suppressed CPSC source value is converted into an "
    "enrollment count."
)
lines.append(
    "2. The SCC-CPSC residual is not treated as a second additive "
    "beneficiary population."
)
lines.append(
    "3. The residual is a suppression-reconciliation quantity "
    "arising from two CMS enrollment representations."
)
lines.append(
    "4. Residual payment uncertainty uses published WA product-level "
    "PMPM bounds and weighted central PMPM."
)
lines.append(
    "5. No missing county or SNP payment cell is fabricated."
)
lines.append(
    "6. Suppressed observation row counts are not interpreted as "
    "beneficiary counts."
)
lines.append(
    "7. This is a methodological reconstruction, not an independent "
    "CMS statewide expenditure control."
)
lines.append(
    "8. This result does not establish complete Medicare or "
    "state-ledger readiness."
)

summary_text = "\n".join(lines)

summary_path = OUTDIR / "reconstruction_summary.txt"
summary_path.write_text(
    summary_text,
    encoding="utf-8",
)

print(summary_text)

print()
print("Evidence written to:")
print(f"  {OUTDIR}")
print()
print("Files:")
print("  published_payment_rows.csv")
print("  product_residual_reconciliation.csv")
print("  suppressed_observation_summary.csv")
print("  reconstruction_summary.txt")
