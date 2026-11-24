import csv
from decimal import Decimal
from pathlib import Path

BASE = Path(".")
BALANCE = BASE / "evidence/statewide/provisional_v0_1/238b8_expanded_balance.csv"
REFUNDS = BASE / "data/raw/irs/refunds_issued/validation/reconciliation_v0_1/refund_totals.csv"
OUTPUT = BASE / "239b1g1_irs_accounting_comparison.txt"

D = Decimal

with BALANCE.open(newline="", encoding="utf-8-sig") as f:
    balances = list(csv.DictReader(f))

with REFUNDS.open(newline="", encoding="utf-8-sig") as f:
    refund_rows = list(csv.DictReader(f))

if len(balances) != 7:
    raise ValueError(f"Expected 7 balance rows; found {len(balances)}")

# Inspect refund control schema before assuming column names.
refund_columns = list(refund_rows[0]) if refund_rows else []

with OUTPUT.open("w", encoding="utf-8") as out:
    def emit(s=""):
        print(s, file=out)

    emit("ETL-239B1G1 - IRS ACCOUNTING COMPARISON")
    emit("=" * 72)
    emit("READ ONLY - PROVISIONAL SCENARIO - NO LEDGER AUTHORIZATION")
    emit()
    emit("REFUND CONTROL COLUMNS")
    emit(", ".join(refund_columns))
    emit()
    emit("REFUND CONTROL ROWS")
    for row in refund_rows:
        emit(str(row))
    emit()
    emit("EXPANDED BALANCE CONTROLS")
    emit(
        "YEAR | GROSS IRS | EXPANDED INFLOWS | "
        "GROSS-BASIS BALANCE"
    )

    gross_total = D("0")
    inflow_total = D("0")
    balance_total = D("0")

    for row in balances:
        year = row["fiscal_year"]
        gross = D(row["irs_gross_collections_usd"])
        inflows = D(row["expanded_inflows_usd"])
        balance = D(row["expanded_provisional_balance_usd"])

        if inflows - gross != balance:
            raise ValueError(f"Balance reconciliation failed: {year}")

        if row["refund_adjustment_applied"] != "NO":
            raise ValueError(f"Unexpected refund treatment: {year}")

        gross_total += gross
        inflow_total += inflows
        balance_total += balance

        emit(f"{year} | {gross:.2f} | {inflows:.2f} | {balance:.2f}")

    emit()
    emit(f"TOTAL GROSS IRS: {gross_total:.2f}")
    emit(f"TOTAL EXPANDED INFLOWS: {inflow_total:.2f}")
    emit(f"TOTAL GROSS-BASIS BALANCE: {balance_total:.2f}")
    emit()
    emit("No source files modified.")
    emit("No database changes.")
    emit("No canonical ledger authorization.")

print(f"ETL-239B1G1 completed: {OUTPUT}")