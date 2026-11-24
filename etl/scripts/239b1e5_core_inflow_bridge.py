from pathlib import Path
from decimal import Decimal
import csv

ROOT = Path(__file__).resolve().parents[2]

LEDGER = ROOT / (
    "accounting_registry/v0_3_3_working/"
    "canonical_annual_ledger.csv"
)

BASELINE = ROOT / (
    "evidence/statewide/provisional_v0_1/"
    "238a_annual_balance_v0_1.csv"
)

DETAIL = ROOT / "239b1e5_family_detail.csv"
REPORT = ROOT / "239b1e5_stdout.txt"

D = Decimal
ZERO = D("0")

FAMILIES = [
    "SSA_OASDI",
    "MEDICARE_FFS_AB",
    "MEDICARE_PART_C",
    "MEDICARE_PART_D",
    "MEDICAID",
    "CHIP",
    "VA_GDX",
    "FEDERAL_CIVILIAN_WAGES",
    "FEDERAL_MILITARY_WAGES",
]

def read_csv(path):
    with path.open(
        "r", newline="", encoding="utf-8-sig"
    ) as f:
        return list(csv.DictReader(f))

def amount(value):
    if value is None or not value.strip():
        return None
    return D(value)

ledger_rows = read_csv(LEDGER)
baseline_rows = read_csv(BASELINE)

years = list(range(2018, 2025))

baseline = {}
for row in baseline_rows:
    year = int(row["fiscal_year"])
    if year in baseline:
        raise ValueError(f"Duplicate baseline year: {year}")
    baseline[year] = row

index = {}
for row in ledger_rows:
    year = int(row["fiscal_year"])
    family = row["family_id"]
    key = (year, family)

    if key in index:
        raise ValueError(f"Duplicate ledger key: {key}")

    index[key] = row

if set(years) - set(baseline):
    raise ValueError("Missing baseline fiscal years")

detail_rows = []
lines = []

lines.append(
    "ETL-239B1E5 | SEVEN-YEAR CORE INFLOW BRIDGE"
)
lines.append("FILE-BASED DIAGNOSTIC - NO DATABASE WRITES")
lines.append("=" * 100)
lines.append("")
lines.append(
    "FY | ETL-238A core | Registry sum | Difference | "
    "Missing | Result"
)

all_pass = True

for year in years:
    expected = amount(
        baseline[year]["core_inflows_usd"]
    )

    total = ZERO
    missing = []

    for family in FAMILIES:
        row = index.get((year, family))

        if row is None:
            missing.append(family)
            continue

        observed = amount(
            row["candidate_observed_amount_usd"]
        )

        if observed is None:
            missing.append(family)
        else:
            total += observed

        detail_rows.append({
            "fiscal_year": year,
            "family_id": family,
            "candidate_observed_amount_usd":
                "" if observed is None else str(observed),
            "authorized_amount_usd":
                row["authorized_amount_usd"],
            "ledger_status": row["ledger_status"],
            "measure_basis": row["measure_basis"],
            "source_reference": row["source_reference"],
        })

    difference = total - expected

    matched = (
        difference == ZERO and not missing
    )

    if not matched:
        all_pass = False

    lines.append(
        f"{year} | "
        f"{expected:,.2f} | "
        f"{total:,.2f} | "
        f"{difference:+,.2f} | "
        f"{len(missing)} | "
        f"{'MATCH' if matched else 'REVIEW'}"
    )

    if missing:
        lines.append(
            "    Missing: " + ", ".join(missing)
        )

lines.append("")
lines.append("FAMILIES INCLUDED:")
for family in FAMILIES:
    lines.append("  " + family)

lines.append("")
lines.append(
    "NOTE: Candidate observations are not equivalent "
    "to authorized ledger amounts."
)
lines.append(
    "NOTE: Arithmetic agreement does not certify "
    "time basis, completeness, or non-overlap."
)
lines.append(
    "NOTE: Medicare Part D is included only to test "
    "the historical preliminary calculation."
)
lines.append(
    "NOTE: Refundable tax credits are not added "
    "as an inflow in this diagnostic."
)
lines.append("")
lines.append(
    "RESULT: " +
    ("ALL SEVEN YEARS MATCH" if all_pass
     else "DIFFERENCES REQUIRE REVIEW")
)

with DETAIL.open(
    "w", newline="", encoding="utf-8"
) as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "fiscal_year",
            "family_id",
            "candidate_observed_amount_usd",
            "authorized_amount_usd",
            "ledger_status",
            "measure_basis",
            "source_reference",
        ]
    )
    writer.writeheader()
    writer.writerows(detail_rows)

REPORT.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8"
)

print("\n".join(lines))
print()
print(f"Detail: {DETAIL}")
print(f"Report: {REPORT}")