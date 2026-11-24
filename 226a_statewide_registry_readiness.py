from pathlib import Path
from collections import defaultdict
import csv

base = Path("accounting_registry/v0_3_0_working")
source = base / "annual_accounting_matrix.csv"
output = Path("226a_statewide_registry_readiness.txt")

with source.open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

families = defaultdict(list)

for row in rows:
    families[row["family_id"]].append(row)

lines = [
    "ETL-226A - STATEWIDE REGISTRY READINESS",
    "READ ONLY - NO DATABASE OR REGISTRY WRITES",
    "=" * 100,
    f"Total annual registry observations: {len(rows)}",
    f"Source families: {len(families)}",
    ""
]

for family in sorted(families):
    entries = sorted(
        families[family],
        key=lambda r: int(r["source_year"])
    )

    observed = [
        r for r in entries
        if r["observed_amount_usd"].strip()
    ]

    authorized = [
        r for r in entries
        if r["ledger_authorization"] not in
        ("", "NOT_YET_AUTHORIZED")
    ]

    lines.extend([
        "-" * 100,
        f"FAMILY: {family}",
        f"Observed years: {len(observed)}/{len(entries)}",
        f"Ledger authorization entries requiring review: {len(authorized)}",
        "Annual detail:"
    ])

    for r in entries:
        lines.append(
            f"  {r['source_year']} | "
            f"amount={r['observed_amount_usd'] or 'MISSING'} | "
            f"coverage={r['coverage_status']} | "
            f"accounting={r['accounting_status']} | "
            f"ledger={r['ledger_authorization']}"
        )

output.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("ETL-226A PASS")
print("Families:", len(families))
print("Annual observations:", len(rows))
print("Output:", output)
