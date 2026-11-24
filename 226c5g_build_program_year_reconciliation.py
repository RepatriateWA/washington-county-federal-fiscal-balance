import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path.cwd()

CROSSWALK = ROOT / "226c5c_assistance_registry_crosswalk.csv"
REGISTRY = ROOT / "accounting_registry/v0_3_0_working/source_family_registry.csv"

PROGRAMS = {
    "10.551": "SNAP",
    "20.106": "Transportation",
    "20.205": "Transportation",
    "20.500": "Transportation",
    "20.507": "Transportation",
    "20.509": "Transportation",
    "20.525": "Transportation",
    "21.019": "Treasury stabilization",
    "21.023": "Treasury stabilization",
    "21.027": "Treasury stabilization",
    "84.010": "Education",
    "84.027": "Education",
    "84.063": "Education",
    "84.425": "Education",
    "93.558": "TANF",
    "93.855": "NIAID research",
}

HISTORICAL_214M3 = {
    "84.010", "84.027", "84.063", "93.558"
}

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

rows = read_csv(CROSSWALK)
families = {
    row["family_id"]
    for row in read_csv(REGISTRY)
}

indexed = defaultdict(list)

for row in rows:
    key = (row["program_code"], int(row["fiscal_year"]))
    indexed[key].append(row)

print("ETL-226C5G PROGRAM-YEAR RECONCILIATION")
print("READ ONLY - NO LEDGER AUTHORIZATION")
print("=" * 100)
print("Program-year evidence records:", len(rows))
print("Selected governing programs:", len(PROGRAMS))
print("Fiscal years: 2018-2024")
print()

print("COVERAGE MATRIX")
print("-" * 100)
print(
    f'{"CODE":<9} {"GROUP":<24} ' +
    " ".join(str(y) for y in range(2018, 2025))
)

for code, group in sorted(PROGRAMS.items()):
    cells = []

    for year in range(2018, 2025):
        matching = indexed.get((code, year), [])

        if len(matching) == 0:
            cell = "-"
        elif len(matching) == 1:
            cell = "O"
        else:
            cell = f"D{len(matching)}"

        cells.append(cell)

    print(
        f"{code:<9} {group:<24} " +
        " ".join(f"{cell:>4}" for cell in cells)
    )

print()
print("O = observation present; - = absent; D = duplicate records")
print("Observation presence is not certification or authorization.")
print()

print("FY2018-FY2019 HISTORICAL AUTHORITY")
print("-" * 100)

for code in sorted(PROGRAMS):
    if code in HISTORICAL_214M3:
        status = "ETL-214M3 CERTIFIED"
    else:
        status = "REQUIRES POLICY-LINEAGE MATCH"

    print(f"{code:<9} {status}")

print()
print("CROSSWALK AND REGISTRY CHECK")
print("-" * 100)

for code in sorted(PROGRAMS):
    matching = [
        r for r in rows
        if r["program_code"] == code
    ]

    treatments = sorted({
        r["registry_crosswalk_treatment"]
        for r in matching
    })

    linked_families = sorted({
        r["registry_family_id"]
        for r in matching
        if r["registry_family_id"]
    })

    missing_families = [
        family for family in linked_families
        if family not in families
    ]

    total = sum(
        float(r["net_obligations_usd"] or 0)
        for r in matching
    )

    print(
        f"{code}: years={len(matching)} "
        f"net_obligations=${total:,.2f} "
        f"treatments={','.join(treatments) or 'NONE'} "
        f"families={','.join(linked_families) or 'NONE'}"
    )

    if missing_families:
        print(
            "  WARNING: Registry family ID not found:",
            ", ".join(missing_families)
        )

print()
print("ADDITIONAL ETL-214M3 HISTORICAL PROGRAMS")
print("-" * 100)

for code in ("10.555", "93.600"):
    matching = [
        r for r in rows
        if r["program_code"] == code
        and int(r["fiscal_year"]) in (2018, 2019)
    ]

    print(
        f"{code}: historical observations={len(matching)}; "
        "ETL-214M3 certified historical policy"
    )

print()
print("RECONCILIATION COMPLETE")
