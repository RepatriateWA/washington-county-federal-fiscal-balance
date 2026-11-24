from pathlib import Path
import csv
import re
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[2]
REFUNDS = ROOT / (
    "data/raw/irs/refunds_issued/validation/"
    "reconciliation_v0_1/refund_totals.csv"
)
CATEGORIES = ROOT / (
    "data/raw/irs/refunds_issued/validation/"
    "reconciliation_v0_1/refund_categories.csv"
)
BALANCE = ROOT / (
    "evidence/statewide/provisional_v0_1/"
    "238b8_expanded_balance.csv"
)
PROFILE = ROOT / "239b1e7d_stdout.txt"
OUTPUT = ROOT / (
    "accounting_registry/v0_3_3_working/"
    "IRS_REFUND_OVERLAP_REVIEW_239B1E8_WORKING.md"
)

def load_csv(path):
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)

def markdown_table(headers, rows):
    result = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        result.append(
            "| " + " | ".join(str(v).replace("|", "/")
                           for v in row) + " |"
        )
    return "\n".join(result)

refund_cols, refund_rows = load_csv(REFUNDS)
category_cols, category_rows = load_csv(CATEGORIES)
balance_cols, balance_rows = load_csv(BALANCE)

if len(balance_rows) != 7:
    raise ValueError("Expected seven expanded-balance years.")

if any(r["refund_adjustment_applied"] != "NO"
       for r in balance_rows):
    raise ValueError("Unexpected existing refund adjustment.")

raw_profile = PROFILE.read_bytes()

if raw_profile.startswith((b"\xff\xfe", b"\xfe\xff")):
    profile_text = raw_profile.decode("utf-16")
else:
    profile_text = raw_profile.decode("utf-8-sig")
codes = re.findall(
    r"^\s*(\d{2}\.\d{3})\s*\|",
    profile_text,
    flags=re.MULTILINE
)
codes = sorted(set(codes))

if len(codes) != 38:
    raise ValueError(
        f"Expected 38 additive program codes; found {len(codes)}"
    )

annual = []
for r in balance_rows:
    annual.append([
        r["fiscal_year"],
        r["irs_gross_collections_usd"],
        r["expanded_provisional_balance_usd"],
        r["refund_adjustment_applied"],
    ])

sections = [
    "# ETL-239B1E8 — IRS Refund Overlap Review",
    "",
    "**Status:** WORKING EVIDENCE REVIEW — NOT AUTHORIZED",
    "",
    "**Period:** FY2018–FY2024",
    "",
    "## 1. Scope and evidence",
    "",
    "This review evaluates IRS refunds against independently "
    "included federal inflows. It does not alter the ledger.",
    "",
    f"- Refund totals: `{REFUNDS.relative_to(ROOT)}`",
    f"- Refund categories: `{CATEGORIES.relative_to(ROOT)}`",
    f"- Expanded balance: `{BALANCE.relative_to(ROOT)}`",
    f"- Assistance program profile: `{PROFILE.name}`",
    "",
    f"Refund totals: {len(refund_rows)} rows.",
    f"Refund categories: {len(category_rows)} rows.",
    f"Additive assistance program codes: {len(codes)}.",
    "",
    "## 2. Current expanded-balance controls",
    "",
    markdown_table(
        ["FY", "IRS gross USD", "Balance USD",
         "Refund adjustment"],
        annual
    ),
    "",
    "The expanded balance uses gross IRS collections.",
    "No refund adjustment is currently applied.",
    "",
    "## 3. IRS refund-category evidence inventory",
    "",
    "The following table preserves the source columns and "
    "values without imposing an unsupported interpretation.",
    "",
    markdown_table(
        category_cols,
        [[r.get(c, "") for c in category_cols]
         for r in category_rows]
    ),
    "",
    "## 4. Cross-program overlap dispositions",
    "",
    markdown_table(
        ["Refund category", "Current disposition",
         "Evidence / remaining question"],
        [
            [
                "Economic Impact Payments",
                "UNRESOLVED — REVIEW",
                "Nested within IRS refunds; verify no "
                "independent inclusion in assistance or "
                "another inflow family."
            ],
            [
                "Advance Child Tax Credit",
                "UNRESOLVED — REVIEW",
                "Nested within IRS refunds; verify treatment "
                "relative to independently included payments."
            ],
            [
                "Other refundable credits",
                "UNRESOLVED — REVIEW",
                "Check credit/payment definitions, including "
                "premium tax credit interactions."
            ],
            [
                "Remaining IRS refunds",
                "UNRESOLVED — REVIEW",
                "Confirm refund coverage, timing, and "
                "potential program intersections."
            ],
        ]
    ),
    "",
    "## 5. Additive assistance program codes",
    "",
    ", ".join(codes),
    "",
    "The program-code inventory is not, by itself, "
    "proof of non-overlap.",
    "",
    "## 6. Decision gates",
    "",
    "- [ ] Reconcile refund totals and nested categories.",
    "- [ ] Reconcile additive assistance to annual balance.",
    "- [ ] Resolve or qualify material overlap questions.",
    "- [ ] Document cash-versus-obligation and year-basis "
    "limitations.",
    "- [ ] Review proposed IRS net-collections treatment.",
    "- [ ] Explicitly authorize any ledger change.",
    "",
    "## 7. Current disposition",
    "",
    "**IRS gross collections:** existing treatment unchanged.",
    "",
    "**IRS net collections:** NOT YET AUTHORIZED.",
    "",
    "**Refundable tax credits as separate inflow:** "
    "NOT YET AUTHORIZED.",
    "",
    "**Expanded balance:** unchanged.",
    "",
    "No database writes or ledger changes.",
    "",
    "Measure first. Explain later.",
    "",
]

OUTPUT.write_text(
    "\n".join(sections),
    encoding="utf-8"
)

print("ETL-239B1E8A - WORKING DECISION RECORD")
print("Refund rows:", len(refund_rows))
print("Category rows:", len(category_rows))
print("Additive program codes:", len(codes))
print("Expanded balance years:", len(balance_rows))
print("Decision: NOT YET AUTHORIZED")
print("Output:", OUTPUT.relative_to(ROOT))