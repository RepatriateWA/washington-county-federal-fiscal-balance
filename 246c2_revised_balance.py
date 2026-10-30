import csv
from decimal import Decimal
from pathlib import Path

ROOT = Path.cwd()
D = Decimal
YEARS = list(range(2018, 2025))

REFERENCE = ROOT / "docs/presentations/wcffbp-244b/data/243e1_first_draft_annual_balance.csv"
RETIREMENT = ROOT / "245m14_military_retirement_consistent_scenarios.csv"

OUTPUT = ROOT / "246c2_revised_annual_balance_candidate.csv"
REPORT = ROOT / "246c2_validation.txt"

def load(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        records = list(csv.DictReader(f))
    years = [int(r["fiscal_year"]) for r in records]
    if sorted(years) != YEARS or len(years) != 7:
        raise ValueError(f"Invalid fiscal-year coverage: {path}")
    return {int(r["fiscal_year"]): r for r in records}

reference = load(REFERENCE)
retirement = load(RETIREMENT)

fields = [
    "fiscal_year",
    "original_inflows_usd",
    "dod_procurement_usd",
    "doe_procurement_usd",
    "other_non_va_procurement_usd",
    "total_non_va_procurement_usd",
    "military_retirement_trend_usd",
    "revised_inflows_usd",
    "irs_net_collections_usd",
    "original_balance_usd",
    "revised_balance_usd",
    "canonical_ledger_authorization",
]

results = []
totals = {key: D("0") for key in fields[1:-1]}

for year in YEARS:
    r = reference[year]
    m = retirement[year]

    original = D(r["partd_inclusive_inflows_usd"])
    dod = D(r["dod_procurement_obligations_usd"])
    doe = D(r["doe_procurement_obligations_usd"])
    other = D(r["other_non_va_procurement_obligations_usd"])
    procurement = D(r["total_non_va_procurement_obligations_usd"])
    military = D(m["trend_interpolated_usd"])
    taxes = D(r["irs_net_collections_candidate_usd"])
    old_balance = D(r["partd_inclusive_net_irs_balance_usd"])

    assert dod + doe + other == procurement
    assert original - taxes == old_balance
    assert r["canonical_ledger_authorization"] == "NOT_AUTHORIZED"

    revised = original + procurement + military
    balance = revised - taxes

    values = {
        "original_inflows_usd": original,
        "dod_procurement_usd": dod,
        "doe_procurement_usd": doe,
        "other_non_va_procurement_usd": other,
        "total_non_va_procurement_usd": procurement,
        "military_retirement_trend_usd": military,
        "revised_inflows_usd": revised,
        "irs_net_collections_usd": taxes,
        "original_balance_usd": old_balance,
        "revised_balance_usd": balance,
    }

    for key, value in values.items():
        totals[key] += value

    results.append({
        "fiscal_year": year,
        **{key: str(value) for key, value in values.items()},
        "canonical_ledger_authorization": "NOT_AUTHORIZED",
    })

assert totals["original_inflows_usd"] == D("586919920787.19")
assert totals["irs_net_collections_usd"] == D("785062475000.00")
assert totals["original_balance_usd"] == D("-198142554212.81")

assert (
    totals["dod_procurement_usd"]
    + totals["doe_procurement_usd"]
    + totals["other_non_va_procurement_usd"]
    == totals["total_non_va_procurement_usd"]
)

assert (
    totals["revised_inflows_usd"]
    == totals["original_inflows_usd"]
    + totals["total_non_va_procurement_usd"]
    + totals["military_retirement_trend_usd"]
)

assert (
    totals["revised_balance_usd"]
    == totals["revised_inflows_usd"]
    - totals["irs_net_collections_usd"]
)

with OUTPUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(results)

lines = [
    "ETL-246C2 - REVISED PROVISIONAL STATEWIDE BALANCE",
    "=" * 76,
    "FY2018-2024 | USD | MIXED MEASURES | NOT AUTHORIZED",
    "",
    "Year | Original inflows | Procurement | Military retirement | Revised inflows | Revised balance",
]

for row in results:
    lines.append(
        f"{row['fiscal_year']} | "
        f"{D(row['original_inflows_usd']):,.2f} | "
        f"{D(row['total_non_va_procurement_usd']):,.2f} | "
        f"{D(row['military_retirement_trend_usd']):,.2f} | "
        f"{D(row['revised_inflows_usd']):,.2f} | "
        f"{D(row['revised_balance_usd']):,.2f}"
    )

lines.extend([
    "",
    "SEVEN-YEAR CONTROLS",
    "-" * 76,
])

for key, value in totals.items():
    lines.append(f"{key}: {value:,.2f}")

lines.extend([
    "",
    "QUALIFICATIONS",
    "- Procurement amounts are federal obligations, not cash outlays.",
    "- Military retirement uses modeled trend-interpolated estimates.",
    "- VA procurement is withheld pending overlap review.",
    "- Procurement overlap and Washington economic incidence remain unresolved.",
    "- Other source timing and coverage qualifications remain.",
    "- No canonical ledger authorization or database changes.",
    "",
    "PASS: Seven annual reconciliations and aggregate controls",
])

REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("\n".join(lines))
