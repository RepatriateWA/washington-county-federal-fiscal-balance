from pathlib import Path
from decimal import Decimal
from collections import defaultdict
import csv

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / (
    "data/raw/irs/refunds_issued/validation/"
    "reconciliation_v0_1/refund_categories.csv"
)

OUTPUT = ROOT / "239b1e8d_refund_hierarchy_report.txt"

def money(value):
    return Decimal(str(value).strip())

with SOURCE.open(
    encoding="utf-8-sig", newline=""
) as f:
    records = list(csv.DictReader(f))

wa = [
    r for r in records
    if r["geography"].strip().upper() == "WA"
    and 2018 <= int(r["fiscal_year"]) <= 2024
]

years = defaultdict(list)
for r in wa:
    years[int(r["fiscal_year"])].append(r)

lines = [
    "ETL-239B1E8D - IRS REFUND CATEGORY HIERARCHY",
    "=" * 76,
    "READ ONLY - NO ACCOUNTING AUTHORIZATION",
    "",
]

failures = 0

for year in range(2018, 2025):
    rows = years[year]

    if not rows:
        raise ValueError(f"No Washington observations for {year}")

    by_col = {
        int(r["column_number"]): r
        for r in rows
    }

    if len(by_col) != len(rows):
        raise ValueError(
            f"Duplicate column observations for {year}"
        )

    total = money(by_col[2]["amount_usd"])

    # IRS Table 8:
    # B = total refunds
    # C = business income taxes
    # D = individual income taxes
    # Later columns vary by reporting year.
    #
    # Nested individual-income subcategories
    # are identified by the source's column
    # structure, not counted as top-level totals.

    if year == 2020:
        top_level = [3, 4] + list(range(7, max(by_col) + 1))
        nested = [5, 6]
    elif year in (2021, 2022):
        top_level = [3, 4] + list(range(8, max(by_col) + 1))
        nested = [5, 6, 7]
    else:
        top_level = list(range(3, max(by_col) + 1))
        nested = []

    component_sum = sum(
        (money(by_col[c]["amount_usd"])
         for c in top_level),
        Decimal("0")
    )

    difference = total - component_sum

    lines.extend([
        "",
        f"FY{year}",
        "-" * 76,
        f"Total refunds:             ${total:,.2f}",
        f"Top-level component sum:   ${component_sum:,.2f}",
        f"Difference:                ${difference:,.2f}",
        f"Top-level columns:         {top_level}",
        f"Nested columns excluded:   {nested}",
        "",
        "COLUMN DETAIL:",
    ])

    for col in sorted(by_col):
        r = by_col[col]
        role = (
            "TOTAL" if col == 2
            else "NESTED" if col in nested
            else "TOP_LEVEL"
        )
        header = " ".join(
            r["header_text"].split()
        ) or "[BLANK SOURCE HEADER]"

        lines.append(
            f"  {r['source_cell']:5} "
            f"{role:10} "
            f"${money(r['amount_usd']):>19,.2f} "
            f"{header}"
        )

    if difference != 0:
        failures += 1
        lines.append(
            "STATUS: RECONCILIATION DIFFERENCE"
        )
    else:
        lines.append(
            "STATUS: ARITHMETIC PASS"
        )

lines.extend([
    "",
    "=" * 76,
    f"Years with arithmetic differences: {failures}",
    "Category labels and nesting require source verification.",
    "No database changes.",
    "No ledger authorization.",
])

OUTPUT.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8"
)

print("ETL-239B1E8D completed")
print("Washington years:", len(years))
print("Arithmetic differences:", failures)
print("Report:", OUTPUT.relative_to(ROOT))