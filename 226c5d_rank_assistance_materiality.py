from pathlib import Path
from collections import defaultdict, Counter
from decimal import Decimal
import csv

SOURCE = Path("226c5c_assistance_registry_crosswalk.csv")
PREFIX = "226c5d"

ZERO = Decimal("0")
YEARS = range(2018, 2025)

if not SOURCE.exists():
    raise SystemExit(f"Missing source: {SOURCE}")

with SOURCE.open(newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

if len(rows) != 216:
    raise SystemExit(f"Expected 216 source rows; found {len(rows)}")

keys = [(r["fiscal_year"], r["program_code"]) for r in rows]
if len(set(keys)) != len(keys):
    raise SystemExit("Duplicate program-year keys detected")

if Counter(r["registry_crosswalk_treatment"] for r in rows) != {
    "REVIEW_REQUIRED": 195,
    "MISSING_FAMILY_CANDIDATE": 12,
    "ALREADY_REPRESENTED": 9,
}:
    raise SystemExit("Unexpected source crosswalk status counts")

def money(value):
    return Decimal(value)

def write_csv(path, fieldnames, data):
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

unresolved = [
    r for r in rows
    if r["registry_crosswalk_treatment"] == "REVIEW_REQUIRED"
]

programs = {}

for r in unresolved:
    code = r["program_code"]
    year = int(r["fiscal_year"])

    if year not in YEARS:
        raise SystemExit(f"Unexpected fiscal year: {year}")

    if code not in programs:
        programs[code] = {
            "program_code": code,
            "program_title": r["program_title"],
            "years": set(),
            "observations": 0,
            "transactions": 0,
            "net": ZERO,
            "absolute": ZERO,
        }

    p = programs[code]

    if p["program_title"] != r["program_title"]:
        raise SystemExit(f"Inconsistent program title: {code}")

    p["years"].add(year)
    p["observations"] += 1
    p["transactions"] += int(r["transactions"])
    p["net"] += money(r["net_obligations_usd"])
    p["absolute"] += money(r["absolute_activity_usd"])

ranking = sorted(
    programs.values(),
    key=lambda p: (-p["absolute"], p["program_code"])
)

ranked_rows = []

for rank, p in enumerate(ranking, 1):
    ranked_rows.append({
        "materiality_rank": rank,
        "program_code": p["program_code"],
        "program_title": p["program_title"],
        "years_observed": len(p["years"]),
        "program_year_observations": p["observations"],
        "transactions": p["transactions"],
        "net_obligations_usd": str(p["net"]),
        "absolute_activity_usd": str(p["absolute"]),
        "existing_policy_disposition": "INCLUDE_ADDITIVE",
        "registry_crosswalk_treatment": "REVIEW_REQUIRED",
    })

write_csv(
    f"{PREFIX}_program_materiality_ranking.csv",
    list(ranked_rows[0]) if ranked_rows else [],
    ranked_rows,
)

# Rank unresolved programs independently within each fiscal year.
annual_rows = []

for year in YEARS:
    year_rows = sorted(
        (
            r for r in unresolved
            if int(r["fiscal_year"]) == year
        ),
        key=lambda r: (
            -money(r["absolute_activity_usd"]),
            r["program_code"]
        )
    )

    for rank, r in enumerate(year_rows, 1):
        annual_rows.append({
            "fiscal_year": year,
            "annual_materiality_rank": rank,
            "program_code": r["program_code"],
            "program_title": r["program_title"],
            "net_obligations_usd": r["net_obligations_usd"],
            "absolute_activity_usd": r["absolute_activity_usd"],
            "transactions": r["transactions"],
            "registry_crosswalk_treatment": "REVIEW_REQUIRED",
        })

write_csv(
    f"{PREFIX}_annual_materiality.csv",
    [
        "fiscal_year",
        "annual_materiality_rank",
        "program_code",
        "program_title",
        "net_obligations_usd",
        "absolute_activity_usd",
        "transactions",
        "registry_crosswalk_treatment",
    ],
    annual_rows,
)

# No accounting decisions here: this is an evidence-review queue.
review_rows = []

for r in ranked_rows:
    review_rows.append({
        "materiality_rank": r["materiality_rank"],
        "program_code": r["program_code"],
        "program_title": r["program_title"],
        "net_obligations_usd": r["net_obligations_usd"],
        "absolute_activity_usd": r["absolute_activity_usd"],
        "registry_family_match": "NOT_YET_CHECKED",
        "prior_overlap_evidence": "NOT_YET_CHECKED",
        "obligation_cash_basis_review": "REQUIRED",
        "recommended_next_action": "REVIEW_EXISTING_EVIDENCE",
        "ledger_authorization": "NOT_AUTHORIZED",
    })

write_csv(
    f"{PREFIX}_review_queue.csv",
    list(review_rows[0]) if review_rows else [],
    review_rows,
)

# Exact signed-amount conservation.
annual_source = defaultdict(lambda: ZERO)
annual_review = defaultdict(lambda: ZERO)

for r in rows:
    annual_source[int(r["fiscal_year"])] += money(
        r["net_obligations_usd"]
    )

for r in unresolved:
    annual_review[int(r["fiscal_year"])] += money(
        r["net_obligations_usd"]
    )

report = [
    "ETL-226C5D - MATERIALITY-RANKED ASSISTANCE REVIEW",
    "=" * 76,
    "Database writes: NONE",
    "Registry writes: NONE",
    "Source crosswalk modified: NO",
    "",
    f"Source program-year observations: {len(rows)}",
    f"Unresolved program-year observations: {len(unresolved)}",
    f"Distinct unresolved programs: {len(programs)}",
    "",
    "ANNUAL RECONCILIATION",
]

for year in YEARS:
    classified = sum(
        (
            money(r["net_obligations_usd"])
            for r in rows
            if int(r["fiscal_year"]) == year
            and r["registry_crosswalk_treatment"] != "REVIEW_REQUIRED"
        ),
        ZERO,
    )

    if annual_review[year] + classified != annual_source[year]:
        raise SystemExit(f"Annual reconciliation failed: {year}")

    report.append(
        f"{year}: "
        f"source=${annual_source[year]:,.2f}; "
        f"review=${annual_review[year]:,.2f}; "
        f"classified=${classified:,.2f}; PASS"
    )

report.extend([
    "",
    "TOP 25 UNRESOLVED PROGRAMS BY ABSOLUTE ACTIVITY",
    "",
])

for p in ranked_rows[:25]:
    report.append(
        f"{int(p['materiality_rank']):2d}. "
        f"{p['program_code']:8s} "
        f"absolute=${money(p['absolute_activity_usd']):>18,.2f} "
        f"net=${money(p['net_obligations_usd']):>18,.2f} "
        f"{p['program_title']}"
    )

top10_abs = sum(
    (money(r["absolute_activity_usd"]) for r in ranked_rows[:10]),
    ZERO,
)
total_abs = sum(
    (money(r["absolute_activity_usd"]) for r in ranked_rows),
    ZERO,
)

share = (top10_abs / total_abs * 100) if total_abs else ZERO

report.extend([
    "",
    f"Top 10 share of unresolved absolute activity: {share:.2f}%",
    "",
    "No accounting dispositions changed.",
    "No ledger amounts authorized.",
    "",
    "ETL-226C5D PASS",
])

Path(f"{PREFIX}_materiality_report.txt").write_text(
    "\n".join(report) + "\n",
    encoding="utf-8",
)

print("\n".join(report))
