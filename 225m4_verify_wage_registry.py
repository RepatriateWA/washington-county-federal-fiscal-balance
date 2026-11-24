import csv
from pathlib import Path

root = Path("accounting_registry/v0_3_0_working")
before = root / "annual_accounting_matrix.csv.pre225m3.bak"
after = root / "annual_accounting_matrix.csv"

def load(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)

old_fields, old_rows = load(before)
new_fields, new_rows = load(after)

assert old_fields == new_fields
assert len(old_rows) == len(new_rows) == 161

expected_families = {
    "FEDERAL_CIVILIAN_WAGES",
    "FEDERAL_MILITARY_WAGES"
}

changes = []

for old, new in zip(old_rows, new_rows):
    assert (
        old["family_id"], old["source_year"]
    ) == (
        new["family_id"], new["source_year"]
    ), "Row identity changed"

    changed = {
        field for field in old_fields
        if old[field] != new[field]
    }

    if not changed:
        continue

    assert changed == {
        "coverage_status", "evidence_path"
    }, f"Unexpected field changes: {changed}"

    assert new["family_id"] in expected_families
    assert old["coverage_status"] == "PRIOR_STATEWIDE_AUDIT_REPORTED"
    assert new["coverage_status"] == "ETL_225M2_WAGE_COMPONENT_REPRODUCED"
    assert old["accounting_status"] == new["accounting_status"]
    assert old["ledger_authorization"] == new["ledger_authorization"]
    assert old["observed_amount_usd"] == new["observed_amount_usd"]

    changes.append((new["family_id"], new["source_year"]))

assert len(changes) == 14, f"Expected 14 changes; found {len(changes)}"
assert len(set(changes)) == 14, "Duplicate family-year keys"

print("ETL-225M4 PASS")
print("Matrix observations: 161")
print("Verified wage changes: 14")
print("Unexpected field changes: 0")
print("Observed amount changes: 0")
print("Accounting status changes: 0")
print("Ledger authorization changes: 0")
print("Database writes: none")
