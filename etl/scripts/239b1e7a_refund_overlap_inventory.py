from pathlib import Path
import csv

root = Path(__file__).resolve().parents[2]
registry = root / "accounting_registry/v0_3_3_working"
families_path = registry / "source_family_registry.csv"
ledger_path = registry / "canonical_annual_ledger.csv"

output = root / "239b1e7a_refund_overlap_inventory.csv"
report = root / "239b1e7a_refund_overlap_report.txt"

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

families = read_csv(families_path)
ledger = read_csv(ledger_path)

family_by_id = {r["family_id"]: r for r in families}

focus = [
    ("REFUNDABLE_TAX_CREDITS", "Refundable credits"),
    ("USASPENDING_ASSISTANCE", "Assistance awards"),
    ("MEDICAID", "Health expenditure"),
    ("CHIP", "Health expenditure"),
    ("MEDICARE_FFS_AB", "Health expenditure"),
    ("MEDICARE_PART_C", "Health expenditure"),
    ("MEDICARE_PART_D", "Health expenditure"),
    ("VA_GDX", "Veterans expenditures"),
    ("SSA_OASDI", "Social Security"),
    ("SSA_SSI", "Supplemental Security Income"),
]

rows = []
for family_id, reason in focus:
    family = family_by_id.get(family_id, {})
    annual = [
        r for r in ledger
        if r["family_id"] == family_id
        and r["fiscal_year"] in {
            str(y) for y in range(2018, 2025)
        }
    ]

    rows.append({
        "family_id": family_id,
        "review_scope": reason,
        "registry_authorization":
            family.get("ledger_authorization", "NOT_FOUND"),
        "registry_certification":
            family.get("accounting_certification", "NOT_FOUND"),
        "annual_rows": len(annual),
        "annual_ledger_statuses":
            ";".join(sorted({
                r.get("ledger_status", "")
                for r in annual
            })),
        "overlap_evidence": "NOT_YET_TESTED",
        "disposition": "REVIEW_REQUIRED",
        "evidence_reference": "",
        "notes": "",
    })

with output.open(
    "w", newline="", encoding="utf-8"
) as f:
    writer = csv.DictWriter(
        f, fieldnames=list(rows[0])
    )
    writer.writeheader()
    writer.writerows(rows)

lines = [
    "ETL-239B1E7A - IRS REFUND OVERLAP INVENTORY",
    "READ ONLY - NO LEDGER AUTHORIZATION",
    "=" * 78,
    f"Registry families: {len(families)}",
    f"Canonical ledger rows: {len(ledger)}",
    f"Review families: {len(rows)}",
    "",
]

for r in rows:
    lines.extend([
        r["family_id"],
        f"  Registry: {r['registry_authorization']}",
        f"  Annual rows: {r['annual_rows']}",
        f"  Ledger statuses: {r['annual_ledger_statuses']}",
        "  Overlap: NOT YET TESTED",
        "",
    ])

report.write_text(
    "\n".join(lines),
    encoding="utf-8"
)
print("\n".join(lines))