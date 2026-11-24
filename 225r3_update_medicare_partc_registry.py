from pathlib import Path
import csv
import io
import sys

registry = Path(
    "accounting_registry/v0_3_0_working/"
    "annual_accounting_matrix.csv"
)

backup = registry.with_name(
    "annual_accounting_matrix_pre_225r3.csv"
)

evidence_file = Path("225r1_medicare_partc_stdout.txt")
precision_script = Path("225r2a_precision_check.py")

if backup.exists():
    sys.exit("STOP: backup already exists; refusing overwrite")

if not evidence_file.exists() or not precision_script.exists():
    sys.exit("STOP: required reconciliation evidence missing")

original = registry.read_bytes()

encoding = "utf-8-sig" if original.startswith(b"\xef\xbb\xbf") else "utf-8"
content = original.decode(encoding)

newline = "\r\n" if "\r\n" in content else "\n"

reader = csv.DictReader(io.StringIO(content, newline=""))

fields = reader.fieldnames
rows = list(reader)

required = {
    "family_id", "source_year", "coverage_status",
    "evidence_path", "observed_amount_usd",
    "source_time_basis", "accounting_status",
    "ledger_authorization"
}

if not required.issubset(set(fields or [])):
    sys.exit("STOP: unexpected registry schema")

partc = [
    row for row in rows
    if row["family_id"] == "MEDICARE_PART_C"
]

if len(partc) != 7:
    sys.exit("STOP: expected exactly seven Part C rows")

years = {int(row["source_year"]) for row in partc}

if years != set(range(2018, 2025)):
    sys.exit("STOP: unexpected Part C year coverage")

for row in partc:
    if row["source_time_basis"] != "CALENDAR_YEAR":
        sys.exit("STOP: unexpected Part C time basis")

    if row["ledger_authorization"] != "NOT_YET_AUTHORIZED":
        sys.exit("STOP: unexpected ledger authorization")

    if not row["observed_amount_usd"].strip():
        sys.exit("STOP: missing observed amount")

evidence = (
    "data/raw/cms/medicare/validation/"
    "accounting_integration_v0_1/"
    "cms_medicare_accounting_integration_report_v0_1.txt"
    "; 225r1_medicare_partc_stdout.txt"
    "; 225r2a_precision_check.py"
)

for row in partc:
    year = int(row["source_year"])

    if year <= 2023:
        row["coverage_status"] = (
            "ETL_225R_PART_C_FULL_CY_CONTROL_REPRODUCED"
        )
    else:
        row["coverage_status"] = (
            "ETL_225R_PART_C_PARTIAL_JAN_SEP_CONTROL_REPRODUCED"
        )

    row["evidence_path"] = evidence

output = io.StringIO(newline="")
writer = csv.DictWriter(
    output,
    fieldnames=fields,
    lineterminator=newline
)

writer.writeheader()
writer.writerows(rows)

updated = output.getvalue().encode(encoding)

backup.write_bytes(original)
registry.write_bytes(updated)

print("ETL-225R3 PASS")
print("Updated Medicare Part C observations:", len(partc))
print("Complete CY observations:", 6)
print("Partial Jan-Sep 2024 observations:", 1)
print("Registry rows preserved:", len(rows))
print("Observed amounts changed: 0")
print("Accounting statuses changed: 0")
print("Ledger authorizations changed: 0")
print("Backup:", backup)
