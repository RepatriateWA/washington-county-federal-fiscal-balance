import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(".")
REGISTRY = ROOT / "accounting_registry/v0_3_3_working"
MATRIX = REGISTRY / "annual_accounting_matrix.csv"
FAMILIES = REGISTRY / "source_family_registry.csv"
BALANCE = ROOT / "evidence/statewide/provisional_v0_1/238b8_expanded_balance.csv"
REPORT = ROOT / "240a1_inflow_materiality_inventory.txt"

YEARS = set(range(2018, 2025))
D = Decimal

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def money(value):
    if not value or not value.strip():
        return None
    try:
        return D(value)
    except InvalidOperation:
        return None

family_rows = read_csv(FAMILIES)
matrix_rows = read_csv(MATRIX)
balance_rows = read_csv(BALANCE)

family_index = {r["family_id"]: r for r in family_rows}
grouped = defaultdict(list)

for row in matrix_rows:
    year = int(row["source_year"])
    if year in YEARS:
        grouped[row["family_id"]].append(row)

results = []

for family_id, info in family_index.items():
    if info["side"] != "INFLOW":
        continue

    rows = grouped.get(family_id, [])
    observed = [
        (int(r["source_year"]), money(r["observed_amount_usd"]))
        for r in rows
    ]
    valid = [(y, amount) for y, amount in observed if amount is not None]

    total = sum((amount for _, amount in valid), D(0))
    years = sorted({y for y, _ in valid})
    missing = sorted(YEARS - set(years))

    results.append({
        "family": family_id,
        "total": total,
        "years": years,
        "missing": missing,
        "role": info["registry_role"],
        "status": info["provisional_status"],
        "authorization": info["ledger_authorization"],
        "limitation": info["next_review_or_limitation"],
        "observations": len(valid),
    })

results.sort(key=lambda r: r["total"], reverse=True)

expanded_inflows = sum(
    D(r["expanded_inflows_usd"]) for r in balance_rows
)

with REPORT.open("w", encoding="utf-8") as out:
    def emit(text=""):
        print(text, file=out)

    emit("ETL-240A1 - LARGE-MAGNITUDE INFLOW MATERIALITY INVENTORY")
    emit("=" * 78)
    emit("READ ONLY - NO ACCOUNTING AUTHORIZATION")
    emit("Amounts are observed controls, NOT established omissions.")
    emit()

    emit(f"Registry families: {len(family_rows)}")
    emit(f"Registry annual observations: {len(matrix_rows)}")
    emit(f"Expanded seven-year inflows: ${expanded_inflows:,.2f}")
    emit()

    emit("RANKED INFLOW FAMILY INVENTORY")
    emit("-" * 78)

    for r in results:
        emit(f"FAMILY: {r['family']}")
        emit(f"  Observed seven-year amount: ${r['total']:,.2f}")
        emit(f"  Years with amounts: {r['years']}")
        emit(f"  Missing years: {r['missing']}")
        emit(f"  Registry role: {r['role']}")
        emit(f"  Provisional status: {r['status']}")
        emit(f"  Ledger authorization: {r['authorization']}")
        emit(f"  Limitation: {r['limitation']}")
        emit()

    emit("IMPORTANT ACCOUNTING WARNINGS")
    emit("-" * 78)
    emit("1. Medicare core is a non-additive reporting parent.")
    emit("2. Housing Choice Vouchers may be within USAspending assistance.")
    emit("3. Procurement may overlap VA and other federal expenditures.")
    emit("4. Medicare annual controls may use calendar-year timing.")
    emit("5. Blank observations are unknown, not zero.")
    emit("6. Registry amounts must not be summed as additional inflows.")
    emit("7. Inclusion in expanded inflows is not established by this report.")
    emit()
    emit("No database changes.")
    emit("No ledger authorization.")

print(f"Report written: {REPORT}")