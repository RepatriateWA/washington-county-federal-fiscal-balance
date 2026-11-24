import csv
import shutil
from pathlib import Path

root = Path("accounting_registry/v0_3_0_working")
matrix = root / "annual_accounting_matrix.csv"
ledger = root / "canonical_annual_ledger.csv"

original_matrix = matrix.read_bytes()
original_ledger = ledger.read_bytes()

with matrix.open("r", newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames
    rows = list(reader)

targets = [
    row for row in rows
    if row["family_id"] in {"IRS_GROSS_COLLECTIONS", "VA_GDX"}
]

assert len(targets) == 14, "Expected 14 IRS/VA records"
assert all(
    row["coverage_status"] ==
    "REPORTED_ETL_222B_CHECKPOINT_NOT_REVERIFIED"
    for row in targets
), "Unexpected existing verification status"

assert all(
    row["ledger_authorization"] == "NOT_YET_AUTHORIZED"
    for row in targets
), "Unexpected ledger authorization"

for row in targets:
    row["coverage_status"] = "ETL_225K_STATEWIDE_CONTROL_REPRODUCED"
    row["evidence_path"] = (
        "etl/sql/222b_statewide_component_matrix.sql; "
        "225k_statewide_components_stdout.txt"
    )

shutil.copy2(matrix, matrix.with_suffix(".csv.pre225l1.bak"))

with matrix.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

assert ledger.read_bytes() == original_ledger, \
    "Canonical ledger changed unexpectedly"

print("ETL-225L1 PASS")
print("IRS/VA evidence statuses updated: 14")
print("Observed dollar amounts: unchanged")
print("Accounting statuses: unchanged")
print("Ledger authorizations: unchanged")
print("Canonical annual ledger: unchanged")
print("Database writes: none")
