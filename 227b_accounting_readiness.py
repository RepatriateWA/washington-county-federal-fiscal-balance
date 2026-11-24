import csv
from pathlib import Path

ROOT = Path("accounting_registry/v0_3_0_working")

def load(filename):
    with (ROOT / filename).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

families = load("source_family_registry.csv")
matrix = load("annual_accounting_matrix.csv")
ledger = load("canonical_annual_ledger.csv")

matrix_by_key = {
    (r["family_id"], r["source_year"]): r
    for r in matrix
}

ledger_by_key = {
    (r["family_id"], r["fiscal_year"]): r
    for r in ledger
}

print("=" * 105)
print("ETL-227B - ACCOUNTING READINESS DECISION QUEUE")
print("READ ONLY - NO LEDGER AUTHORIZATION")
print("=" * 105)

print()
print("FAMILY READINESS")
print("-" * 105)

for family in families:
    if family["registry_role"] != "CANDIDATE_PAYMENT_STREAM":
        continue

    fid = family["family_id"]

    rows = [
        ledger_by_key[(fid, str(y))]
        for y in range(2018, 2025)
    ]

    observed = sum(
        bool(r["candidate_observed_amount_usd"].strip())
        for r in rows
    )

    amount = sum(
        abs(float(r["candidate_observed_amount_usd"]))
        for r in rows
        if r["candidate_observed_amount_usd"].strip()
    )

    if observed == 0:
        classification = "MISSING_SOURCE_CONTROL"
    elif observed < 7:
        classification = "INCOMPLETE_ANNUAL_COVERAGE"
    else:
        classification = "REQUIRES_ACCOUNTING_REVIEW"

    print()
    print(f"FAMILY: {fid}")
    print(f"SIDE: {family['side']}")
    print(f"OBSERVED YEARS: {observed}/7")
    print(f"SEVEN-YEAR ABSOLUTE OBSERVATION: ${amount:,.2f}")
    print(f"READINESS: {classification}")
    print(f"TIME BASIS: {family['time_basis']}")
    print(f"ACCOUNTING CERTIFICATION: {family['accounting_certification']}")
    print(f"LIMITATION: {family['next_review_or_limitation']}")
    print(f"PRIMARY REFERENCE: {family['primary_readiness_reference']}")

    for year in range(2018, 2025):
        record = matrix_by_key[(fid, str(year))]
        print(
            f"  {year}: "
            f"coverage={record['coverage_status']} "
            f"accounting={record['accounting_status']} "
            f"evidence={record['evidence_path']}"
        )

print()
print("=" * 105)
print("REVIEW PRIORITY BY OBSERVED MAGNITUDE")
print("This is a diagnostic ranking, not an additive fiscal total.")
print("=" * 105)

ranking = []

for family in families:
    if family["registry_role"] != "CANDIDATE_PAYMENT_STREAM":
        continue

    fid = family["family_id"]
    records = [
        ledger_by_key[(fid, str(y))]
        for y in range(2018, 2025)
    ]

    magnitude = sum(
        abs(float(r["candidate_observed_amount_usd"]))
        for r in records
        if r["candidate_observed_amount_usd"].strip()
    )

    ranking.append((magnitude, fid))

for rank, (amount, fid) in enumerate(
    sorted(ranking, reverse=True), 1
):
    print(f"{rank:2d}. {fid:<32} ${amount/1e9:,.3f}B")

print()
print("NO REGISTRY OR DATABASE WRITES")
print("ETL-227B COMPLETE")
