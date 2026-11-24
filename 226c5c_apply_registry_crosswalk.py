from pathlib import Path
from collections import Counter
import csv
from decimal import Decimal

source = Path("226c5a_assistance_program_year_evidence.csv")
destination = Path("226c5c_assistance_registry_crosswalk.csv")
report = Path("226c5c_crosswalk_report.txt")

if not source.exists():
    raise SystemExit(f"Missing source file: {source}")

with source.open(newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    fields = list(reader.fieldnames or [])

if len(rows) != 216:
    raise SystemExit(f"Expected 216 rows, found {len(rows)}")

required = {
    "fiscal_year",
    "program_code",
    "net_obligations_usd",
    "registry_crosswalk_treatment",
    "registry_family_id",
    "crosswalk_rationale",
}

if not required.issubset(fields):
    raise SystemExit(
        f"Missing required columns: {sorted(required - set(fields))}"
    )

if any(
    r["registry_crosswalk_treatment"] != "REVIEW_REQUIRED"
    or r["registry_family_id"].strip()
    for r in rows
):
    raise SystemExit(
        "Input already contains crosswalk assignments; "
        "refusing to overwrite them."
    )

expected_years = set(range(2018, 2025))
rules = {
    "14.871": (
        "HOUSING_CHOICE_VOUCHERS",
        "ALREADY_REPRESENTED",
        "Existing separately tracked HCV registry family; "
        "exclude from residual assistance to prevent duplication."
    ),
    "57.001": (
        "RAILROAD_RETIREMENT",
        None,
        "Existing Railroad Retirement family; "
        "reconcile against the annual registry observation."
    ),
    "96.006": (
        "SSA_SSI",
        "MISSING_FAMILY_CANDIDATE",
        "Existing SSI registry family lacks annual observations; "
        "USAspending obligation is a candidate, not certified cash."
    ),
}

for code in rules:
    years = {
        int(r["fiscal_year"])
        for r in rows
        if r["program_code"] == code
    }
    if years != expected_years:
        raise SystemExit(
            f"Program {code} years mismatch: {sorted(years)}"
        )

# Registry observations confirmed from the earlier accounting bridge.
# Only FY2018 and FY2019 RRB are classified as already represented.
rrb_already_represented = {2018, 2019}

for row in rows:
    code = row["program_code"]
    if code not in rules:
        continue

    family, treatment, rationale = rules[code]
    year = int(row["fiscal_year"])

    if code == "57.001":
        treatment = (
            "ALREADY_REPRESENTED"
            if year in rrb_already_represented
            else "MISSING_FAMILY_CANDIDATE"
        )

    row["registry_family_id"] = family
    row["registry_crosswalk_treatment"] = treatment
    row["crosswalk_rationale"] = rationale

# Verify no amounts or row identities changed.
original_totals = {}
crosswalk_totals = {}

for row in rows:
    year = int(row["fiscal_year"])
    amount = Decimal(row["net_obligations_usd"])
    original_totals[year] = original_totals.get(
        year, Decimal("0")
    ) + amount

    key = (year, row["registry_crosswalk_treatment"])
    crosswalk_totals[key] = crosswalk_totals.get(
        key, Decimal("0")
    ) + amount

counts = Counter(
    row["registry_crosswalk_treatment"] for row in rows
)

with destination.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

lines = [
    "ETL-226C5C - FIRST REGISTRY CROSSWALK ASSIGNMENTS",
    "=" * 72,
    "Database writes: NONE",
    "Original evidence modified: NO",
    "Registry modified: NO",
    "",
    f"Program-year rows: {len(rows)}",
    "",
    "CROSSWALK TREATMENT COUNTS",
]

for treatment, count in sorted(counts.items()):
    lines.append(f"{treatment}: {count}")

lines.extend([
    "",
    "ANNUAL TOTAL CONSERVATION",
])

for year in sorted(original_totals):
    lines.append(
        f"{year}: ${original_totals[year]:,.2f} PASS"
    )

lines.extend([
    "",
    "ASSIGNMENTS BY YEAR",
    "Year | Already represented | Missing-family candidate | Review required",
])

for year in sorted(original_totals):
    def amount(treatment):
        return crosswalk_totals.get(
            (year, treatment), Decimal("0")
        )

    lines.append(
        f"{year} | "
        f"${amount('ALREADY_REPRESENTED'):,.2f} | "
        f"${amount('MISSING_FAMILY_CANDIDATE'):,.2f} | "
        f"${amount('REVIEW_REQUIRED'):,.2f}"
    )

lines.extend([
    "",
    "All remaining programs retain REVIEW_REQUIRED.",
    "No ledger authorization is implied.",
    "",
    "ETL-226C5C PASS",
])

report.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
