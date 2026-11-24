import csv
from decimal import Decimal
from pathlib import Path

ROOT = Path(".")
BALANCE = ROOT / "evidence/statewide/provisional_v0_1/238b8_expanded_balance.csv"
REFUNDS = ROOT / "data/raw/irs/refunds_issued/validation/reconciliation_v0_1/refund_totals.csv"

OUTPUT = ROOT / "239b1g2_irs_net_balance_scenario.csv"
REPORT = ROOT / "239b1g2_validation.txt"

D = Decimal
YEARS = set(range(2018, 2025))

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

balances = read_csv(BALANCE)
refund_records = read_csv(REFUNDS)

assert len(balances) == 7
assert {int(r["fiscal_year"]) for r in balances} == YEARS

wa_refunds = [
    r for r in refund_records if r["geography"] == "WA"
]

assert len(wa_refunds) == 7
assert {int(r["fiscal_year"]) for r in wa_refunds} == YEARS

refund_by_year = {
    int(r["fiscal_year"]): D(r["refund_total_usd"])
    for r in wa_refunds
}

results = []

for row in sorted(balances, key=lambda r: int(r["fiscal_year"])):
    year = int(row["fiscal_year"])

    inflows = D(row["expanded_inflows_usd"])
    gross = D(row["irs_gross_collections_usd"])
    refunds = refund_by_year[year]
    gross_balance = D(row["expanded_provisional_balance_usd"])

    assert row["refund_adjustment_applied"] == "NO"
    assert gross_balance == inflows - gross
    assert refunds >= 0
    assert refunds <= gross

    net_collections = gross - refunds
    net_balance = inflows - net_collections

    assert net_balance == gross_balance + refunds

    results.append({
        "fiscal_year": year,
        "expanded_inflows_usd": str(inflows),
        "irs_gross_collections_usd": str(gross),
        "irs_refunds_usd": str(refunds),
        "irs_net_collections_candidate_usd": str(net_collections),
        "gross_basis_balance_usd": str(gross_balance),
        "net_basis_candidate_balance_usd": str(net_balance),
        "scenario_status": "QUALIFIED_PROVISIONAL_CANDIDATE",
        "canonical_ledger_authorization": "NOT_AUTHORIZED",
    })

fields = list(results[0])

with OUTPUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(results)

def total(column):
    return sum((D(r[column]) for r in results), D(0))

with REPORT.open("w", encoding="utf-8") as f:
    print("ETL-239B1G2 - IRS NET BALANCE SCENARIO", file=f)
    print("=" * 68, file=f)
    print("READ ONLY - NO CANONICAL LEDGER AUTHORIZATION", file=f)
    print(file=f)

    for r in results:
        print(
            f'{r["fiscal_year"]}: '
            f'Gross={r["irs_gross_collections_usd"]}; '
            f'Refunds={r["irs_refunds_usd"]}; '
            f'Net={r["irs_net_collections_candidate_usd"]}; '
            f'Balance={r["net_basis_candidate_balance_usd"]}',
            file=f
        )

    print(file=f)
    for col in [
        "expanded_inflows_usd",
        "irs_gross_collections_usd",
        "irs_refunds_usd",
        "irs_net_collections_candidate_usd",
        "gross_basis_balance_usd",
        "net_basis_candidate_balance_usd",
    ]:
        print(f"{col}: {total(col):.2f}", file=f)

    assert (
        total("irs_gross_collections_usd")
        - total("irs_refunds_usd")
        == total("irs_net_collections_candidate_usd")
    )
    assert (
        total("expanded_inflows_usd")
        - total("irs_net_collections_candidate_usd")
        == total("net_basis_candidate_balance_usd")
    )

    print(file=f)
    print("PASS: Seven annual reconciliations.", file=f)
    print("PASS: Seven-year aggregate reconciliations.", file=f)
    print("No source files modified.", file=f)
    print("No database changes.", file=f)
    print("No canonical ledger authorization.", file=f)

print(f"ETL-239B1G2 complete: {REPORT}")
print(f"Scenario CSV: {OUTPUT}")