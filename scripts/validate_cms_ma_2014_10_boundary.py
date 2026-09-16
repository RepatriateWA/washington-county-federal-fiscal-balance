from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd


ROOT = Path("data/raw/cms/medicare_advantage")

CPSC_ZIP = ROOT / "enrollment/2014/10/cpsc-enrollment-2014-10.zip"
SCC_ZIP = ROOT / "enrollment_controls/2014/10/scc-enrollment-ma-2014-10.zip"
SNP_ZIP = ROOT / "snp/2014/10/snp-2014-10.zip"
PAYMENT_ZIP = ROOT / "plan_payment/2014/2014paymentdata.zip"


def read_csv_from_zip(path: Path, member: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        raw = z.read(member)

    # Historical CMS CSVs are commonly Windows encoded.
    for encoding in ("cp1252", "latin1", "utf-8-sig"):
        try:
            return pd.read_csv(
                io.BytesIO(raw),
                dtype=str,
                encoding=encoding,
                keep_default_na=False,
            )
        except UnicodeDecodeError:
            continue

    raise RuntimeError(f"Could not decode {member}")


def norm_plan_type(value: str) -> str:
    s = str(value).strip().upper()

    if s in {"HMO", "HMO/HMOPOS", "HMO/HMO-POS"}:
        return "HMO"

    if s in {"LOCAL PPO", "LOCAL_PPO"}:
        return "LOCAL PPO"

    return s


print("=" * 78)
print("CMS MEDICARE ADVANTAGE — OCTOBER 2014 BOUNDARY VALIDATOR")
print("=" * 78)
print("Read-only validation; no database writes.")
print()


# ---------------------------------------------------------------------
# 1. PLAN PAYMENT PUF
# ---------------------------------------------------------------------

with zipfile.ZipFile(PAYMENT_ZIP) as z:
    payment_bytes = z.read("2014PartCCountyLevel.xlsx")

payment = pd.read_excel(
    io.BytesIO(payment_bytes),
    sheet_name="result.srx",
    header=2,
    dtype={"County Code": str},
)

payment.columns = [
    str(c).replace("\n", " ").strip()
    for c in payment.columns
]

payment = payment[
    payment["State Abbreviation"].astype(str).str.strip().eq("WA")
].copy()

payment["plan_type_norm"] = payment["Plan Type"].map(norm_plan_type)

payment_target = payment[
    payment["plan_type_norm"].isin(["HMO", "LOCAL PPO"])
].copy()

print("=== 2014 PART C COUNTY PAYMENT PUF — WASHINGTON ===")
print(f"All WA payment cells:       {len(payment):,}")
print(f"Target HMO/Local PPO cells: {len(payment_target):,}")
print(f"Distinct WA counties:       {payment['County Name'].nunique():,}")

print("\nWA plan types:")
print(payment["Plan Type"].value_counts(dropna=False).to_string())

print("\nWA SNP types within target:")
print(
    payment_target["SNP Plan Type"]
    .fillna("<NON-SNP>")
    .replace("", "<NON-SNP>")
    .value_counts(dropna=False)
    .to_string()
)


# ---------------------------------------------------------------------
# 2. CPSC CONTRACT INFO + ENROLLMENT
# ---------------------------------------------------------------------

contract = read_csv_from_zip(
    CPSC_ZIP,
    "CPSC_Contract_Info_2014_10.csv",
)

enrollment = read_csv_from_zip(
    CPSC_ZIP,
    "CPSC_Enrollment_Info_2014_10.csv",
)

print("\n=== CPSC SOURCE ===")
print(f"Contract-info rows: {len(contract):,}")
print(f"Enrollment rows:    {len(enrollment):,}")

contract = contract.rename(
    columns={
        "Contract ID": "contract_id",
        "Plan ID": "plan_id",
        "Plan Type": "plan_type",
        "SNP Plan": "snp_plan",
        "EGHP": "eghp",
    }
)

enrollment = enrollment.rename(
    columns={
        "Contract Number": "contract_id",
        "Contract ID": "contract_id",
        "Plan ID": "plan_id",
        "SSA State County Code": "ssa_code",
        "FIPS State County Code": "fips_code",
        "State": "state",
        "County": "county",
        "Enrollment": "enrollment",
        "Enrolled": "enrollment",
    }
)

for df in (contract, enrollment):
    df["contract_id"] = df["contract_id"].astype(str).str.strip()
    df["plan_id"] = df["plan_id"].astype(str).str.strip()

contract_keys = contract[["contract_id", "plan_id"]].copy()

duplicate_contract_keys = int(
    contract_keys.duplicated(["contract_id", "plan_id"], keep=False).sum()
)

enrollment = enrollment.merge(
    contract[
        [
            "contract_id",
            "plan_id",
            "plan_type",
            "snp_plan",
            "eghp",
        ]
    ],
    on=["contract_id", "plan_id"],
    how="left",
    validate="many_to_one",
    indicator=True,
)

unresolved_contract_rows = int(
    (enrollment["_merge"] != "both").sum()
)

wa = enrollment[
    enrollment["state"].astype(str).str.strip().eq("WA")
].copy()

wa["plan_type_norm"] = wa["plan_type"].map(norm_plan_type)

wa_target = wa[
    wa["plan_type_norm"].isin(["HMO", "LOCAL PPO"])
].copy()

wa_target["published_enrollment"] = pd.to_numeric(
    wa_target["enrollment"].replace({"*": "", ".": ""}),
    errors="coerce",
)

suppressed_target_rows = int(
    wa_target["published_enrollment"].isna().sum()
)

print(f"Duplicate contract/plan metadata keys: {duplicate_contract_keys:,}")
print(f"Unresolved enrollment→contract rows:   {unresolved_contract_rows:,}")
print(f"WA enrollment rows:                    {len(wa):,}")
print(f"WA target HMO/Local PPO rows:           {len(wa_target):,}")
print(f"WA target suppressed rows:              {suppressed_target_rows:,}")
print(
    "WA target published enrollment:        "
    f"{wa_target['published_enrollment'].sum():,.0f}"
)
print(
    "WA target counties represented:        "
    f"{wa_target['county'].replace('', pd.NA).nunique(dropna=True):,}"
)


# ---------------------------------------------------------------------
# 3. SCC — INDEPENDENT CMS PUBLISHED ENROLLMENT OBSERVATION
# ---------------------------------------------------------------------

with zipfile.ZipFile(SCC_ZIP) as z:
    csv_members = [
        n for n in z.namelist()
        if n.lower().endswith(".csv")
    ]

if len(csv_members) != 1:
    raise RuntimeError(
        f"Expected one SCC CSV; found {csv_members}"
    )

scc = read_csv_from_zip(
    SCC_ZIP,
    csv_members[0],
)

scc.columns = [str(c).strip() for c in scc.columns]

print("\n=== SCC SOURCE ===")
print(f"CSV member: {csv_members[0]}")
print(f"Rows:       {len(scc):,}")
print("Columns:")
print(" | ".join(scc.columns))

state_col = next(
    c for c in scc.columns
    if c.strip().lower() == "state"
)

plan_col = next(
    c for c in scc.columns
    if c.strip().lower() == "plan type"
)

enrolled_col = next(
    c for c in scc.columns
    if c.strip().lower() in {"enrolled", "enrollment"}
)

county_col = next(
    c for c in scc.columns
    if c.strip().lower() == "county"
)

scc_wa = scc[
    scc[state_col].astype(str).str.strip().eq("WA")
].copy()

scc_wa["plan_type_norm"] = scc_wa[plan_col].map(norm_plan_type)

scc_target = scc_wa[
    scc_wa["plan_type_norm"].isin(["HMO", "LOCAL PPO"])
].copy()

scc_target["published_enrollment"] = pd.to_numeric(
    scc_target[enrolled_col].replace(
        {
            "": pd.NA,
            "*": pd.NA,
            ".": pd.NA,
        }
    ),
    errors="coerce",
)

scc_suppressed = int(
    scc_target["published_enrollment"].isna().sum()
)

print(f"WA SCC rows:                   {len(scc_wa):,}")
print(f"WA target HMO/Local PPO rows:  {len(scc_target):,}")
print(f"WA target suppressed rows:     {scc_suppressed:,}")
print(
    "WA target published enrollment: "
    f"{scc_target['published_enrollment'].sum():,.0f}"
)
print(
    "WA target counties represented: "
    f"{scc_target[county_col].replace('', pd.NA).nunique(dropna=True):,}"
)


# ---------------------------------------------------------------------
# 4. BASIC DIMENSIONAL TESTS
# ---------------------------------------------------------------------

print("\n=== BASIC BOUNDARY TESTS ===")

checks = []

def check(name: str, passed: bool, detail: str = "") -> None:
    checks.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"{status}: {name}{suffix}")


check(
    "Payment PUF contains Washington",
    len(payment) > 0,
    f"{len(payment):,} cells",
)

check(
    "Payment PUF contains HMO/Local PPO",
    len(payment_target) > 0,
    f"{len(payment_target):,} cells",
)

check(
    "Payment PUF covers 39 WA counties",
    payment["County Name"].nunique() == 39,
    f"{payment['County Name'].nunique()} counties",
)

check(
    "CPSC contract/plan metadata keys unique",
    duplicate_contract_keys == 0,
    f"{duplicate_contract_keys} duplicate rows",
)

check(
    "CPSC enrollment joins completely to contract metadata",
    unresolved_contract_rows == 0,
    f"{unresolved_contract_rows} unresolved rows",
)

check(
    "CPSC target contains WA enrollment",
    len(wa_target) > 0,
    f"{len(wa_target):,} rows",
)

check(
    "SCC target contains WA enrollment",
    len(scc_target) > 0,
    f"{len(scc_target):,} rows",
)

check(
    "CPSC target has all 39 WA counties",
    wa_target["county"].replace("", pd.NA).nunique(dropna=True) == 39,
    (
        f"{wa_target['county'].replace('', pd.NA).nunique(dropna=True)} "
        "counties"
    ),
)

check(
    "SCC target has all 39 WA counties",
    scc_target[county_col].replace("", pd.NA).nunique(dropna=True) == 39,
    (
        f"{scc_target[county_col].replace('', pd.NA).nunique(dropna=True)} "
        "counties"
    ),
)

passed = sum(1 for _, ok, _ in checks if ok)

print()
print(f"RESULT: {passed}/{len(checks)} basic checks PASS")

if passed == len(checks):
    print(
        "OCTOBER 2014 BASIC SOURCE/LINKAGE ARCHITECTURE: PASS"
    )
else:
    print(
        "OCTOBER 2014 BASIC SOURCE/LINKAGE ARCHITECTURE: REVIEW REQUIRED"
    )

print()
print(
    "NOTE: This validator does not calculate Medicare Advantage payments "
    "and does not establish final-ledger eligibility."
)
