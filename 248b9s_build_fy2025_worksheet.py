import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

D = Decimal
CENT = D("0.01")

ROOT = Path.cwd()
OUT = ROOT / "evidence/statewide/provisional_fy2025"

COMPONENT_FILE = OUT / "248b9s_fy2025_component_worksheet.csv"
SUMMARY_FILE = OUT / "248b9s_fy2025_balance_summary.csv"
VALIDATION_FILE = OUT / "248b9s_validation.txt"

for path in (COMPONENT_FILE, SUMMARY_FILE, VALIDATION_FILE):
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")

def money(value):
    return D(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)

# Source-derived values and explicitly provisional estimates.
# No missing family is assigned a zero-dollar value.

components = [
    {
        "family": "SSA_OASDI",
        "amount": "37774728000.00",
        "evidence": "FY2025 SSA December monthly benefit proxy",
        "measurement": "DECEMBER_2025_MONTHLY_X12",
        "status": "ANNUALIZED_PROXY",
        "limitation": "Not observed federal-fiscal-year cash",
    },
    {
        "family": "MEDICARE_FFS_AB",
        "amount": "7341400281.54",
        "evidence": "ETL-248B9L central model",
        "measurement": "2024_BASELINE_PLUS_1.27_PERCENT",
        "status": "MODELED",
        "limitation": "Calendar-year basis; not FY2025 observed",
    },
    {
        "family": "MEDICARE_PART_C",
        "amount": "10225483566.68",
        "evidence": "ETL-248B9L central model",
        "measurement": "2024_JAN_SEP_ANNUALIZED_PLUS_10_PERCENT",
        "status": "MODELED",
        "limitation": "Partial-year baseline annualized",
    },
    {
        "family": "MEDICARE_PART_D",
        "amount": "1969637454.91",
        "evidence": "ETL-248B9L central model",
        "measurement": "2024_JAN_SEP_ANNUALIZED_ZERO_GROWTH",
        "status": "MODELED",
        "limitation": "Partial-dollar coverage; benefit redesign uncertainty",
    },
    {
        "family": "MEDICAID",
        "amount": "12584822794.00",
        "evidence": "FY2025 provisional Medicaid forecast",
        "measurement": "FEDERAL_FISCAL_YEAR_FORECAST",
        "status": "FORECAST",
        "limitation": "Not actual MBES expenditure",
    },
    {
        "family": "CHIP",
        "amount": "115798708.00",
        "evidence": "FY2025 provisional CHIP forecast",
        "measurement": "FEDERAL_FISCAL_YEAR_FORECAST",
        "status": "FORECAST",
        "limitation": "Not actual MBES expenditure",
    },
    {
        "family": "FEDERAL_CIVILIAN_WAGES",
        "amount": "6557205860.87",
        "evidence": "ETL-248B9P central model",
        "measurement": "FY2024_OMB_OPM_ALLOCATION_PLUS_3_PERCENT",
        "status": "MODELED",
        "limitation": "Allocated obligations, not cash wages",
    },
    {
        "family": "FEDERAL_MILITARY_WAGES",
        "amount": "5053895098.84",
        "evidence": "ETL-248B9P central model",
        "measurement": "FY2024_OMB_BEA_ALLOCATION_PLUS_2_5_PERCENT",
        "status": "MODELED",
        "limitation": "Allocated obligations, not cash wages",
    },
    {
        "family": "VA_GDX",
        "amount": "8027511780.84",
        "evidence": "FY2025 VA GDX source-derived control",
        "measurement": "VA_SOURCE_FISCAL_YEAR",
        "status": "SOURCE_DERIVED",
        "limitation": "VA reporting scope and overlap qualifications",
    },
    {
        "family": "SSA_SSI",
        "amount": "1254709344.00",
        "evidence": "FY2025 USAspending SSI transaction analysis",
        "measurement": "FEDERAL_FISCAL_YEAR_OBLIGATIONS",
        "status": "SOURCE_DERIVED",
        "limitation": "Obligations; FY2024 additive policy expired",
    },
]

outflows = [
    {
        "family": "IRS_NET_COLLECTIONS",
        "amount": "161613973000.00",
        "evidence": "FY2025 provisional IRS gross/refund reconstruction",
        "measurement": "IRS_FISCAL_YEAR_LABEL",
        "status": "QUALIFIED_PROVISIONAL",
        "limitation": "IRS net-collection methodology qualifications",
    }
]

unresolved = [
    "USASPENDING_ASSISTANCE_REMAINDER",
    "USASPENDING_PROCUREMENT",
    "FEDERAL_CIVILIAN_RETIREMENT",
    "FEDERAL_MILITARY_RETIREMENT",
    "RAILROAD_RETIREMENT",
    "REFUNDABLE_TAX_CREDITS",
    "OTHER_UNRESOLVED_FAMILIES",
]

rows = []

for side, items in (("INFLOW", components), ("OUTFLOW", outflows)):
    for item in items:
        rows.append({
            "fiscal_year": 2025,
            "family_id": item["family"],
            "side": side,
            "amount_usd": str(money(item["amount"])),
            "evidence_reference": item["evidence"],
            "measurement_basis": item["measurement"],
            "evidence_status": item["status"],
            "presentation_treatment": "IDENTIFIED_COMPONENT_CANDIDATE",
            "limitation": item["limitation"],
            "ledger_authorization": "NOT_AUTHORIZED",
        })

for family in unresolved:
    rows.append({
        "fiscal_year": 2025,
        "family_id": family,
        "side": "INFLOW",
        "amount_usd": "",
        "evidence_reference": "REGISTRY_OR_FY2025_COVERAGE_REVIEW",
        "measurement_basis": "UNRESOLVED",
        "evidence_status": "NOT_QUANTIFIED_FOR_SUBTOTAL",
        "presentation_treatment": "EXCLUDED_PENDING_RECONCILIATION",
        "limitation": "Missing from subtotal does not mean zero",
        "ledger_authorization": "NOT_AUTHORIZED",
    })

inflows = sum((money(x["amount"]) for x in components), D("0"))
irs_net = money(outflows[0]["amount"])
balance = money(inflows - irs_net)

expected_inflows = D("90905192889.68")
expected_balance = D("-70708780110.32")

assert inflows == expected_inflows
assert balance == expected_balance
assert len(components) == 10
assert len(outflows) == 1
assert len(unresolved) == 7

# Medicare and wage component reconciliations.
by_family = {x["family"]: money(x["amount"]) for x in components}

medicare = sum(
    by_family[k] for k in
    ("MEDICARE_FFS_AB", "MEDICARE_PART_C", "MEDICARE_PART_D")
)

wages = sum(
    by_family[k] for k in
    ("FEDERAL_CIVILIAN_WAGES", "FEDERAL_MILITARY_WAGES")
)

medicaid_chip = (
    by_family["MEDICAID"] + by_family["CHIP"]
)

assert medicare == D("19536521303.13")
assert wages == D("11611100959.71")
assert medicaid_chip == D("12700621502.00")

# One-cent rounding difference between independently rounded
# Medicare components and the original aggregate model output.
medicare_original_aggregate = D("19536521303.12")
assert medicare - medicare_original_aggregate == D("0.01")

OUT.mkdir(parents=True, exist_ok=True)

with COMPONENT_FILE.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

summary = [
    ("fiscal_year", "2025"),
    ("identified_inflows_usd", str(inflows)),
    ("irs_net_collections_usd", str(irs_net)),
    ("identified_component_balance_usd", str(balance)),
    ("medicare_component_sum_usd", str(medicare)),
    ("federal_wages_usd", str(wages)),
    ("medicaid_chip_usd", str(medicaid_chip)),
    ("balance_status", "INCOMPLETE_PROVISIONAL_SUBTOTAL"),
    ("canonical_ledger_authorization", "NOT_AUTHORIZED"),
]

with SUMMARY_FILE.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["metric", "value"])
    writer.writerows(summary)

report = [
    "ETL-248B9S - FY2025 PROVISIONAL COMPONENT WORKSHEET",
    "=" * 72,
    "READ ONLY SOURCE ACCESS - REPORTING FILE OUTPUTS ONLY",
    "",
    f"Identified inflows: ${inflows:,.2f}",
    f"IRS net collections: ${irs_net:,.2f}",
    f"Identified-component balance: ${balance:,.2f}",
    "",
    f"Medicare component sum: ${medicare:,.2f}",
    f"Medicare original aggregate: ${medicare_original_aggregate:,.2f}",
    "Medicare rounding reconciliation: +$0.01",
    f"Federal civilian/military wages: ${wages:,.2f}",
    f"Medicaid plus CHIP: ${medicaid_chip:,.2f}",
    "",
    "PASS: Inflow subtotal arithmetic",
    "PASS: IRS net balance arithmetic",
    "PASS: Medicare component reconciliation",
    "PASS: Federal compensation reconciliation",
    "PASS: Medicaid/CHIP reconciliation",
    "PASS: Unresolved components remain NULL, not zero",
    "",
    "QUALIFICATIONS:",
    "- This is an incomplete identified-component subtotal.",
    "- Mixed fiscal-year and calendar-year measurement bases.",
    "- Modeled values are not observed FY2025 expenditures.",
    "- SSI and wage allocations use obligation-based measures.",
    "- Potential cross-family overlaps remain to be audited.",
    "- Assistance, procurement, retirement and other gaps remain.",
    "- No historical ETL-243E1 modification.",
    "- No database or accounting registry changes.",
    "- No canonical ledger authorization.",
    "",
    f"WORKSHEET: {COMPONENT_FILE.relative_to(ROOT)}",
    f"SUMMARY: {SUMMARY_FILE.relative_to(ROOT)}",
    "",
    "PASS: ETL-248B9S reporting-only validation",
]

VALIDATION_FILE.write_text("\n".join(report) + "\n", encoding="utf-8")

print("\n".join(report))

