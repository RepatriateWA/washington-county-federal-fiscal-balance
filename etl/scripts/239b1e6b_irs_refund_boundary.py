from pathlib import Path
from decimal import Decimal
import csv

ROOT = Path(__file__).resolve().parents[2]
REFUNDS = ROOT / (
    "data/raw/irs/refunds_issued/validation/"
    "reconciliation_v0_1/refund_totals.csv"
)
LEDGER = ROOT / (
    "accounting_registry/v0_3_3_working/"
    "canonical_annual_ledger.csv"
)
OUT = ROOT / "239b1e6b_irs_refund_bridge.csv"
REPORT = ROOT / "239b1e6b_source_review.txt"

D = Decimal
years = range(2018, 2025)

def load(path):
    with path.open(
        newline="", encoding="utf-8-sig"
    ) as f:
        return list(csv.DictReader(f))

def money(value):
    return D(str(value))

refund_rows = [
    r for r in load(REFUNDS)
    if r["geography"] == "WA"
]
gross_rows = [
    r for r in load(LEDGER)
    if r["family_id"] == "IRS_GROSS_COLLECTIONS"
]

refunds = {}
gross = {}

for r in refund_rows:
    y = int(r["fiscal_year"])
    if y in refunds:
        raise ValueError(f"Duplicate refund year {y}")
    refunds[y] = r

for r in gross_rows:
    y = int(r["fiscal_year"])
    if y in gross:
        raise ValueError(f"Duplicate gross year {y}")
    gross[y] = r

rows = []
lines = [
    "ETL-239B1E6B | IRS COLLECTIONS/REFUNDS BOUNDARY",
    "READ ONLY | SCENARIO ONLY | NO AUTHORIZATION",
    "=" * 78,
]

for y in years:
    if y not in refunds or y not in gross:
        raise ValueError(f"Missing source year {y}")

    g = money(
        gross[y]["candidate_observed_amount_usd"]
    )
    r = money(refunds[y]["refund_total_usd"])
    n = g - r

    rows.append({
        "fiscal_year": y,
        "gross_collections_usd": str(g),
        "refunds_issued_usd": str(r),
        "refund_adjusted_collections_usd": str(n),
        "gross_ledger_status":
            gross[y]["ledger_status"],
        "refund_ledger_status":
            refunds[y]["ledger_authorization"],
        "scenario_status": "NOT_AUTHORIZED",
    })

    lines.append(
        f"{y}: gross={g:,.2f}; "
        f"refunds={r:,.2f}; "
        f"adjusted={n:,.2f}"
    )

with OUT.open(
    "w", newline="", encoding="utf-8"
) as f:
    writer = csv.DictWriter(
        f, fieldnames=list(rows[0])
    )
    writer.writeheader()
    writer.writerows(rows)

lines += [
    "",
    "CONTROL NOTES",
    "Refund totals are used ONCE per fiscal year.",
    "Nested EIP and CTC categories are NOT added.",
    "Refund-adjusted amounts are scenario values.",
    "Gross/refund boundary not independently certified.",
    "Cross-program overlap not fully certified.",
    "No database or canonical ledger changes.",
    "",
    "LOCAL IRS COLLECTIONS EVIDENCE INVENTORY",
]

irs_root = ROOT / "data/raw/irs"

if irs_root.exists():
    for path in sorted(irs_root.rglob("*")):
        if not path.is_file():
            continue
        name = path.name.lower()
        if (
            "collection" in name
            or "semantic" in name
            or "table_5" in name
            or "table5" in name
        ):
            lines.append(str(path.relative_to(ROOT)))
else:
    lines.append("IRS raw directory not found")

REPORT.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8"
)

print("\n".join(lines))
print()
print("Bridge:", OUT)
print("Review:", REPORT)