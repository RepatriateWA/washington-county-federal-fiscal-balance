from pathlib import Path
from collections import Counter
import csv

ROOT = Path("accounting_registry/v0_3_0_working")
SOURCE = ROOT / "annual_accounting_matrix.csv"

BRIDGE = Path("226b1_provisional_accounting_bridge.csv")
SUMMARY = Path("226b1_accounting_readiness_summary.txt")

# Provisional review categories only.
# These do not authorize ledger inclusion.

TREATMENTS = {
    "IRS_GROSS_COLLECTIONS": (
        "TAX_CONTROL_CANDIDATE",
        "Confirm tax scope, refunds, and reporting-year basis."
    ),
    "SSA_OASDI": (
        "PRIMARY_SPENDING_CANDIDATE",
        "Preferred SSA source; confirm time basis and USAspending exclusion."
    ),
    "VA_GDX": (
        "PRIMARY_SPENDING_CANDIDATE",
        "Preferred VA source; confirm overlap and time basis."
    ),
    "MEDICAID": (
        "PRIMARY_SPENDING_CANDIDATE",
        "Confirm federal share, time basis, and assistance overlap."
    ),
    "CHIP": (
        "PRIMARY_SPENDING_CANDIDATE",
        "Confirm federal share, time basis, and assistance overlap."
    ),
    "FEDERAL_CIVILIAN_WAGES": (
        "PRIMARY_SPENDING_CANDIDATE",
        "Confirm geographic incidence, accounting scope, and time basis."
    ),
    "FEDERAL_MILITARY_WAGES": (
        "PRIMARY_SPENDING_CANDIDATE",
        "Confirm geographic incidence, accounting scope, and time basis."
    ),
    "HOUSING_CHOICE_VOUCHERS": (
        "ADDITIVE_POLICY_CANDIDATE",
        "Historical and later-year additive policies require bridge review."
    ),
    "RAILROAD_RETIREMENT": (
        "PARTIAL_ADDITIVE_CANDIDATE",
        "2018-2019 observed; 2020-2024 require source recovery."
    ),
    "USASPENDING_ASSISTANCE": (
        "OVERLAP_RECONCILIATION_REQUIRED",
        "Full source-universe totals are not additive to preferred-source benefits."
    ),
    "USASPENDING_PROCUREMENT": (
        "OVERLAP_RECONCILIATION_REQUIRED",
        "Review VA and other agency overlap, place of performance, and timing."
    ),
    "MEDICARE_CORE": (
        "COMPOSITE_NONADDITIVE_CONTROL",
        "Parent of FFS A/B, Part C, Part D; incomplete Part D and 2024."
    ),
    "MEDICARE_FFS_AB": (
        "MEDICARE_COMPONENT_CANDIDATE",
        "Calendar-year component; FFY conversion not authorized."
    ),
    "MEDICARE_PART_C": (
        "MEDICARE_COMPONENT_CANDIDATE",
        "Calendar-year component; 2024 January-September only."
    ),
    "MEDICARE_PART_D": (
        "INCOMPLETE_MEDICARE_COMPONENT",
        "Partial dollar coverage in all years; 2024 incomplete period."
    ),
    "ROCKEFELLER_BOP": (
        "EXTERNAL_BENCHMARK_ONLY",
        "Independent comparison, never an additive ledger component."
    ),
    "MEDICARE_MFFS": (
        "UNRESOLVED_OVERLAP_OR_MISSING",
        "Determine whether amounts are already represented in Medicare core."
    ),
    "MEDICARE_MSSP": (
        "UNRESOLVED_OVERLAP_OR_MISSING",
        "Explicit policy conflict; do not add without reconciliation."
    ),
    "MEDICARE_RDS": (
        "MISSING_COMPONENT_REVIEW",
        "Potential Medicare Part D-related payment; investigate overlap."
    ),
    "FEDERAL_CIVILIAN_RETIREMENT": (
        "MISSING_COMPONENT_REVIEW",
        "Potential material federal retirement spending."
    ),
    "FEDERAL_MILITARY_RETIREMENT": (
        "MISSING_COMPONENT_REVIEW",
        "Potential material federal retirement spending."
    ),
    "SSA_SSI": (
        "MISSING_COMPONENT_REVIEW",
        "Potential material federal benefit spending."
    ),
    "REFUNDABLE_TAX_CREDITS": (
        "MISSING_COMPONENT_REVIEW",
        "Determine treatment of refunds and refundable-credit outlays."
    ),
}

with SOURCE.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

families = {r["family_id"] for r in rows}

missing_rules = families - set(TREATMENTS)
if missing_rules:
    raise RuntimeError(
        f"Unclassified source families: {sorted(missing_rules)}"
    )

expected_years = set(range(2018, 2025))
family_years = {}

for r in rows:
    key = (r["family_id"], int(r["source_year"]))
    if key in family_years:
        raise RuntimeError(f"Duplicate family/year: {key}")
    family_years[key] = r

for family in families:
    found = {
        year for f, year in family_years
        if f == family
    }
    if found != expected_years:
        raise RuntimeError(
            f"Incomplete year structure for {family}: {sorted(found)}"
        )

output_rows = []

for r in rows:
    family = r["family_id"]
    treatment, decision = TREATMENTS[family]

    output_rows.append({
        "family_id": family,
        "source_year": r["source_year"],
        "source_time_basis": r["source_time_basis"],
        "observed_amount_usd": r["observed_amount_usd"],
        "coverage_status": r["coverage_status"],
        "accounting_status": r["accounting_status"],
        "ledger_authorization": r["ledger_authorization"],
        "proposed_bridge_treatment": treatment,
        "required_decision": decision,
        "evidence_path": r["evidence_path"],
    })

output_rows.sort(
    key=lambda r: (r["family_id"], int(r["source_year"]))
)

fields = [
    "family_id",
    "source_year",
    "source_time_basis",
    "observed_amount_usd",
    "coverage_status",
    "accounting_status",
    "ledger_authorization",
    "proposed_bridge_treatment",
    "required_decision",
    "evidence_path",
]

with BRIDGE.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(output_rows)

counts = Counter(
    r["proposed_bridge_treatment"] for r in output_rows
)

populated = sum(
    bool(r["observed_amount_usd"].strip())
    for r in output_rows
)

lines = [
    "ETL-226B1 - SEVEN-YEAR PROVISIONAL ACCOUNTING BRIDGE",
    "=" * 90,
    "READ-ONLY SOURCE ANALYSIS; OUTPUT FILES ONLY",
    "NO LEDGER AUTHORIZATION",
    "",
    f"Source families: {len(families)}",
    f"Annual registry cells: {len(output_rows)}",
    f"Populated cells: {populated}",
    f"Missing amount cells: {len(output_rows) - populated}",
    "",
    "PROVISIONAL ACCOUNTING TREATMENTS",
    "-" * 90,
]

for treatment, count in sorted(counts.items()):
    lines.append(f"{treatment:40s} {count:3d}")

lines.extend([
    "",
    "FAMILY-LEVEL DECISION AGENDA",
    "-" * 90,
])

for family in sorted(families):
    treatment, decision = TREATMENTS[family]
    family_rows = [
        r for r in output_rows if r["family_id"] == family
    ]
    observed = sum(
        bool(r["observed_amount_usd"].strip())
        for r in family_rows
    )
    bases = sorted({
        r["source_time_basis"] for r in family_rows
    })

    lines.extend([
        f"{family}",
        f"  Treatment: {treatment}",
        f"  Observed years: {observed}/7",
        f"  Time basis: {', '.join(bases)}",
        f"  Required decision: {decision}",
        "",
    ])

SUMMARY.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8"
)

print("ETL-226B1 PASS")
print(f"Families: {len(families)}")
print(f"Annual cells: {len(output_rows)}")
print(f"Populated cells: {populated}")
print(f"Bridge: {BRIDGE}")
print(f"Summary: {SUMMARY}")
