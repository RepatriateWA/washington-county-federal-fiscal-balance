import csv
import io
from decimal import Decimal
from pathlib import Path

ROOT = Path.cwd()
D = Decimal

BASE = ROOT / "docs/presentations/wcffbp-244b"
SOURCE = BASE / "evidence/244a5_chart_component_inputs.txt"
REVISED = ROOT / "246c2_revised_annual_balance_candidate.csv"

OUTPUT = ROOT / "246c3_stacked_components_candidate.csv"
REPORT = ROOT / "246c3_validation.txt"

def section(text, name):
    chunk = text.split(name, 1)[1].split("\n=== ", 1)[0].strip()
    return list(csv.DictReader(io.StringIO(chunk)))

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

text = SOURCE.read_text(encoding="utf-8-sig")
included = section(text, "=== INCLUDED SOURCE-FAMILY RECORDS ===")
extra = section(text, "=== EXPANDED ASSISTANCE ADJUSTMENTS ===")
controls = section(text, "=== FINAL REFERENCE CONTROLS ===")
revised = read_csv(REVISED)

names = [
    "SSA_OASDI",
    "MEDICARE_FFS_AB",
    "MEDICARE_PART_C",
    "MEDICARE_PART_D",
    "MEDICAID",
    "CHIP",
    "VA_GDX",
    "FEDERAL_CIVILIAN_WAGES",
    "FEDERAL_MILITARY_WAGES",
    "USASPENDING_ASSISTANCE_ADDITIVE",
    "ADDITIONAL_QUALIFIED_ASSISTANCE",
    "DOD_PROCUREMENT_OBLIGATIONS",
    "DOE_PROCUREMENT_OBLIGATIONS",
    "OTHER_NON_VA_PROCUREMENT_OBLIGATIONS",
    "MILITARY_RETIREMENT_MODELED",
]

fields = ["fiscal_year"] + names + [
    "revised_inflows_usd",
    "irs_net_collections_usd",
    "revised_balance_usd",
    "accounting_status",
]

rows = []
report = [
    "ETL-246C3 - FIFTEEN-COMPONENT INFLOW RECONCILIATION",
    "=" * 76,
    "No database writes. No canonical ledger authorization.",
    "",
]

for year in range(2018, 2025):
    y = str(year)

    m = {
        r["family_id"]: D(r["included_amount_usd"])
        for r in included
        if r["fiscal_year"] == y
        and r["family_id"] in names
    }

    e = next(r for r in extra if r["fiscal_year"] == y)
    c = next(r for r in controls if r["fiscal_year"] == y)
    r = next(r for r in revised if r["fiscal_year"] == y)

    m["MEDICARE_PART_D"] = D(c["partd_qualified_addition_usd"])
    m["ADDITIONAL_QUALIFIED_ASSISTANCE"] = D(
        e["additional_qualified_assistance_usd"]
    )

    m["DOD_PROCUREMENT_OBLIGATIONS"] = D(r["dod_procurement_usd"])
    m["DOE_PROCUREMENT_OBLIGATIONS"] = D(r["doe_procurement_usd"])
    m["OTHER_NON_VA_PROCUREMENT_OBLIGATIONS"] = D(
        r["other_non_va_procurement_usd"]
    )
    m["MILITARY_RETIREMENT_MODELED"] = D(
        r["military_retirement_trend_usd"]
    )

    missing = [name for name in names if name not in m]
    if missing:
        raise ValueError(f"FY{year}: missing components {missing}")

    total = sum((m[name] for name in names), D("0"))
    expected = D(r["revised_inflows_usd"])
    taxes = D(r["irs_net_collections_usd"])
    balance = D(r["revised_balance_usd"])

    assert total == expected, f"FY{year}: inflow mismatch"
    assert total - taxes == balance, f"FY{year}: balance mismatch"
    assert r["canonical_ledger_authorization"] == "NOT_AUTHORIZED"

    rows.append({
        "fiscal_year": year,
        **{name: str(m[name]) for name in names},
        "revised_inflows_usd": str(total),
        "irs_net_collections_usd": str(taxes),
        "revised_balance_usd": str(balance),
        "accounting_status": "QUALIFIED_PROVISIONAL_MIXED_MEASURE",
    })

    report.append(
        f"FY{year}: 15 components | "
        f"inflows ${total:,.2f} | "
        f"balance ${balance:,.2f} | PASS"
    )

assert len(rows) == 7

with OUTPUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

report.extend([
    "",
    "PASS: 7 years x 15 components; exact annual reconciliation.",
    "Procurement obligations are not cash outlays.",
    "Military retirement is modeled.",
    "VA procurement withheld pending overlap review.",
    "No canonical ledger authorization.",
])

REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report))
