import csv
from pathlib import Path

root = Path("accounting_registry/v0_3_0_working")

before = root / "annual_accounting_matrix.csv.pre225l1.bak"
after = root / "annual_accounting_matrix.csv"
ledger = root / "canonical_annual_ledger.csv"

def load(path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)

before_fields, old_rows = load(before)
after_fields, new_rows = load(after)
ledger_fields, ledger_rows = load(ledger)

assert before_fields == after_fields, "Matrix columns changed"
assert len(old_rows) == len(new_rows) == 161, "Unexpected matrix row count"
assert len(ledger_rows) == 147, "Unexpected ledger row count"

assert all(
    old["family_id"] == new["family_id"]
    and old["source_year"] == new["source_year"]
    for old, new in zip(old_rows, new_rows)
), "Matrix row identity or order changed"

changes = []

for old, new in zip(old_rows, new_rows):

    changed_fields = {
        field for field in before_fields
        if old[field] != new[field]
    }

    if not changed_fields:
        continue

    assert changed_fields == {
        "coverage_status", "evidence_path"
    }, (
        f"Unexpected fields changed for "
        f"{old['family_id']} {old['source_year']}: "
        f"{changed_fields}"
    )

    assert old["family_id"] in {
        "IRS_GROSS_COLLECTIONS", "VA_GDX"
    }, "Unexpected family modified"

    assert (
        old["coverage_status"]
        == "REPORTED_ETL_222B_CHECKPOINT_NOT_REVERIFIED"
    ), "Unexpected prior status"

    assert (
        new["coverage_status"]
        == "ETL_225K_STATEWIDE_CONTROL_REPRODUCED"
    ), "Unexpected new status"

    assert (
        new["evidence_path"]
        == (
            "etl/sql/222b_statewide_component_matrix.sql; "
            "225k_statewide_components_stdout.txt"
        )
    ), "Unexpected evidence reference"

    changes.append(
        (new["family_id"], new["source_year"])
    )

assert len(changes) == 14, (
    f"Expected 14 changed rows, found {len(changes)}"
)

assert len(set(changes)) == 14, \
    "Duplicate changed family-year keys"

assert all(
    row["ledger_authorization"] == "NOT_YET_AUTHORIZED"
    for row in new_rows
), "Matrix authorization unexpectedly changed"

assert all(
    row["ledger_status"] == "NOT_YET_AUTHORIZED"
    for row in ledger_rows
), "Ledger status unexpectedly changed"

assert all(
    not row["authorized_amount_usd"]
    for row in ledger_rows
), "Unexpected authorized ledger amount"

print("ETL-225L2 PASS")
print(f"Matrix observations: {len(new_rows)}")
print(f"Ledger references: {len(ledger_rows)}")
print(f"Verified changes: {len(changes)}")
print("Changed fields: coverage_status, evidence_path")
print("Unexpected changes: 0")
print("Accounting authorization changes: 0")
print("Authorized ledger amounts: 0")
print("Database writes: none")
