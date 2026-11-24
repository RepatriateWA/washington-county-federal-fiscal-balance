from pathlib import Path
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import csv

SOURCE = Path(
    "accounting_registry/v0_3_0_working/annual_accounting_matrix.csv"
)

DETAIL = Path("226b2a_candidate_accounting_bridge.csv")
SUMMARY = Path("226b2a_annual_diagnostic_summary.csv")
REPORT = Path("226b2a_accounting_bridge_report.txt")

YEARS = range(2018, 2025)

# Diagnostic classifications, not ledger authorizations.
# Explicitly distinguish source observation from accounting eligibility.

FISCAL_PRIMARY = {
    "IRS_GROSS_COLLECTIONS": "TAX",
    "VA_GDX": "SPENDING",
    "MEDICAID": "SPENDING",
    "CHIP": "SPENDING",
    "FEDERAL_CIVILIAN_WAGES": "SPENDING",
    "FEDERAL_MILITARY_WAGES": "SPENDING",
}

ADDITIVE_CANDIDATES = {
    "HOUSING_CHOICE_VOUCHERS",
    "RAILROAD_RETIREMENT",
}

TEMPORAL_PROXIES = {
    "SSA_OASDI",
    "MEDICARE_CORE",
}

# All other families remain reference-only in this pass.
# Medicare Core is the parent of FFS, Part C, and Part D.

def classify(family):
    if family in FISCAL_PRIMARY:
        return (
            "FISCAL_PRIMARY_DIAGNOSTIC",
            FISCAL_PRIMARY[family]
        )

    if family in ADDITIVE_CANDIDATES:
        return ("ADDITIVE_CANDIDATE_SEPARATE", "SPENDING")

    if family in TEMPORAL_PROXIES:
        return ("TEMPORAL_PROXY_SEPARATE", "SPENDING")

    return ("REFERENCE_ONLY_NOT_SUMMED", "NONE")


def amount_or_none(value):
    value = value.strip()
    if not value:
        return None

    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(f"Invalid amount: {value!r}")


def money(value):
    return f"{value:.2f}"


with SOURCE.open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

required_columns = {
    "family_id",
    "source_year",
    "source_time_basis",
    "observed_amount_usd",
    "coverage_status",
    "accounting_status",
    "ledger_authorization",
    "evidence_path",
}

if not required_columns.issubset(rows[0]):
    raise RuntimeError("Required registry columns are missing.")

if len(rows) != 161:
    raise RuntimeError(
        f"Expected 161 registry rows, found {len(rows)}"
    )

seen = set()
detail_rows = []
annual = defaultdict(lambda: defaultdict(Decimal))
counts = defaultdict(lambda: defaultdict(int))

for row in rows:
    family = row["family_id"]
    year = int(row["source_year"])
    key = (family, year)

    if key in seen:
        raise RuntimeError(f"Duplicate family/year: {key}")

    seen.add(key)

    if year not in YEARS:
        raise RuntimeError(f"Unexpected year: {year}")

    amount = amount_or_none(row["observed_amount_usd"])
    treatment, direction = classify(family)

    # No source may be silently promoted to the ledger.
    if row["ledger_authorization"] != "NOT_YET_AUTHORIZED":
        raise RuntimeError(
            f"Unexpected ledger status for {key}: "
            f"{row['ledger_authorization']}"
        )

    # Verify expected temporal basis for diagnostic candidates.
    if treatment == "FISCAL_PRIMARY_DIAGNOSTIC":
        allowed = {
            "IRS_GROSS_COLLECTIONS": {"IRS_FISCAL_YEAR_LABEL"},
            "VA_GDX": {"SOURCE_FISCAL_YEAR"},
            "MEDICAID": {"FEDERAL_FISCAL_YEAR"},
            "CHIP": {"FEDERAL_FISCAL_YEAR"},
            "FEDERAL_CIVILIAN_WAGES": {"FEDERAL_FISCAL_YEAR"},
            "FEDERAL_MILITARY_WAGES": {"FEDERAL_FISCAL_YEAR"},
        }[family]

        if row["source_time_basis"] not in allowed:
            raise RuntimeError(
                f"Unexpected time basis for {key}: "
                f"{row['source_time_basis']}"
            )

    if amount is not None:
        if direction == "TAX":
            annual[year]["fiscal_tax_control"] += amount

        elif treatment == "FISCAL_PRIMARY_DIAGNOSTIC":
            annual[year]["fiscal_primary_spending"] += amount

        elif treatment == "ADDITIVE_CANDIDATE_SEPARATE":
            annual[year]["additive_candidate_spending"] += amount

        elif family == "SSA_OASDI":
            annual[year]["ssa_snapshot_proxy"] += amount

        elif family == "MEDICARE_CORE":
            annual[year]["medicare_calendar_proxy"] += amount

        counts[year][treatment] += 1

    detail_rows.append({
        "family_id": family,
        "source_year": year,
        "source_time_basis": row["source_time_basis"],
        "observed_amount_usd": row["observed_amount_usd"],
        "coverage_status": row["coverage_status"],
        "accounting_status": row["accounting_status"],
        "ledger_authorization": row["ledger_authorization"],
        "diagnostic_treatment": treatment,
        "direction": direction,
        "evidence_path": row["evidence_path"],
    })

if len(seen) != 161:
    raise RuntimeError("Registry family/year uniqueness failed.")

detail_rows.sort(
    key=lambda r: (int(r["source_year"]), r["family_id"])
)

with DETAIL.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=list(detail_rows[0])
    )
    writer.writeheader()
    writer.writerows(detail_rows)

annual_rows = []

for year in YEARS:
    a = annual[year]

    taxes = a["fiscal_tax_control"]
    primary = a["fiscal_primary_spending"]
    additive = a["additive_candidate_spending"]
    ssa = a["ssa_snapshot_proxy"]
    medicare = a["medicare_calendar_proxy"]

    # These are diagnostic differences, NOT final fiscal balances.
    primary_gap = taxes - primary
    expanded_gap = taxes - primary - additive

    annual_rows.append({
        "year": year,
        "tax_control_usd": money(taxes),
        "fiscal_primary_spending_usd": money(primary),
        "additive_candidate_spending_usd": money(additive),
        "ssa_snapshot_proxy_usd": money(ssa),
        "medicare_calendar_proxy_usd": money(medicare),
        "tax_less_primary_diagnostic_usd": money(primary_gap),
        "tax_less_primary_and_additive_diagnostic_usd": money(
            expanded_gap
        ),
        "status": "DIAGNOSTIC_ONLY_NOT_LEDGER_AUTHORIZED",
    })

with SUMMARY.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=list(annual_rows[0])
    )
    writer.writeheader()
    writer.writerows(annual_rows)

lines = [
    "ETL-226B2A - SEVEN-YEAR CANDIDATE ACCOUNTING BRIDGE",
    "=" * 100,
    "READ-ONLY SOURCE; OUTPUT FILES ONLY",
    "NO DATABASE WRITES",
    "NO REGISTRY MODIFICATIONS",
    "NO LEDGER AUTHORIZATION",
    "",
    "CAUTION:",
    "Diagnostic differences are not federal fiscal balances.",
    "SSA observations are annualized December snapshots.",
    "Medicare Core observations are calendar-year composites.",
    "Medicare Part D has partial dollar coverage.",
    "Medicare 2024 Part C and Part D are Jan-Sep only.",
    "USAspending source-universe totals are not additive.",
    "Additive candidates remain separately identified.",
    "IRS gross collections are not automatically net tax receipts.",
    "",
    "ANNUAL DIAGNOSTIC RESULTS (USD BILLIONS)",
    "-" * 100,
    (
        "Year | Taxes | Fiscal primary spending | "
        "Additive candidates | SSA proxy | Medicare proxy"
    ),
]

for r in annual_rows:
    vals = [
        Decimal(r["tax_control_usd"]),
        Decimal(r["fiscal_primary_spending_usd"]),
        Decimal(r["additive_candidate_spending_usd"]),
        Decimal(r["ssa_snapshot_proxy_usd"]),
        Decimal(r["medicare_calendar_proxy_usd"]),
    ]

    lines.append(
        f"{r['year']} | " +
        " | ".join(
            f"{v / Decimal('1000000000'):.3f}"
            for v in vals
        )
    )

lines.extend([
    "",
    "DIAGNOSTIC DIFFERENCES (USD BILLIONS)",
    "-" * 100,
    "Year | Taxes less primary | Taxes less primary and additive",
])

for r in annual_rows:
    first = Decimal(
        r["tax_less_primary_diagnostic_usd"]
    ) / Decimal("1000000000")

    second = Decimal(
        r["tax_less_primary_and_additive_diagnostic_usd"]
    ) / Decimal("1000000000")

    lines.append(
        f"{r['year']} | {first:.3f} | {second:.3f}"
    )

lines.extend([
    "",
    "ACCOUNTING CONTROL NOTES",
    "-" * 100,
    "1. Medicare Core is never summed with its component families.",
    "2. SSA and Medicare are not silently mixed with FFY controls.",
    "3. HCV and Railroad Retirement remain separate candidates.",
    "4. USAspending assistance and procurement remain excluded.",
    "5. All registry ledger authorizations remain unchanged.",
    "",
    "NEXT: Evaluate material omissions, overlap, and timing.",
])

REPORT.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8"
)

print("ETL-226B2A PASS")
print("Annual years:", len(annual_rows))
print("Registry rows:", len(detail_rows))
print("Detail:", DETAIL)
print("Annual summary:", SUMMARY)
print("Report:", REPORT)
