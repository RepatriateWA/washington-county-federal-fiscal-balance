import csv
from decimal import Decimal
from pathlib import Path

ROOT = Path.cwd()
EVIDENCE = ROOT / "evidence/statewide/provisional_v0_1"
IRS_FILE = ROOT / "239b1g2_irs_net_balance_scenario.csv"
PARTD_FILE = EVIDENCE / "242a5_partd_inclusive_balance.csv"
PROC_FILE = ROOT / "243d1_procurement_bridge.txt"

OUTPUT = EVIDENCE / "243e1_first_draft_annual_balance.csv"
VALIDATION = EVIDENCE / "243e1_validation.txt"

YEARS = list(range(2018, 2025))
D = Decimal
CENT = D("0.01")

def money(value):
    return D(str(value)).quantize(CENT)

def read_csv(path, year_column):
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        records = list(csv.DictReader(f))
    rows = {int(r[year_column]): r for r in records}
    if len(records) != 7 or sorted(rows) != YEARS:
        raise ValueError(f"Expected seven unique years in {path}")
    return rows

irs = read_csv(IRS_FILE, "fiscal_year")
partd = read_csv(PARTD_FILE, "reporting_year")

if not PROC_FILE.is_file():
    raise FileNotFoundError(PROC_FILE)

# Read the verified ETL-243D1 annual procurement bridge.
proc = {}
raw_bytes = PROC_FILE.read_bytes()

if raw_bytes.startswith(b"\xff\xfe"):
    procurement_text = raw_bytes.decode("utf-16")
elif raw_bytes.startswith(b"\xfe\xff"):
    procurement_text = raw_bytes.decode("utf-16")
else:
    procurement_text = raw_bytes.decode("utf-8-sig")

for line in procurement_text.splitlines():
    cells = [x.strip() for x in line.split("|")]
    if len(cells) != 13 or not cells[0].isdigit():
        continue
    year = int(cells[0])
    if year not in YEARS:
        continue
    if year in proc:
        raise ValueError(f"Duplicate procurement year {year}")
    proc[year] = {
        "dod": money(cells[2]),
        "doe": money(cells[3]),
        "other": money(cells[4]),
        "va": money(cells[5]),
        "non_va": money(cells[6]),
        "all": money(cells[7]),
        "difference": money(cells[8]),
        "exceptions": [int(x) for x in cells[9:13]],
    }

if sorted(proc) != YEARS:
    raise ValueError(
        f"Procurement annual records incomplete: {sorted(proc)}"
    )

columns = [
    "fiscal_year",
    "expanded_inflows_before_partd_usd",
    "irs_gross_collections_usd",
    "irs_refunds_usd",
    "irs_net_collections_candidate_usd",
    "net_irs_balance_before_partd_usd",
    "partd_qualified_addition_usd",
    "partd_inclusive_inflows_usd",
    "partd_inclusive_net_irs_balance_usd",
    "dod_procurement_obligations_usd",
    "doe_procurement_obligations_usd",
    "other_non_va_procurement_obligations_usd",
    "total_non_va_procurement_obligations_usd",
    "procurement_sensitivity_balance_usd",
    "reference_status",
    "procurement_status",
    "canonical_ledger_authorization",
]

results = []
totals = {
    "refunds": D(0),
    "baseline": D(0),
    "partd": D(0),
    "reference": D(0),
    "procurement": D(0),
    "sensitivity": D(0),
}

for year in YEARS:
    a = irs[year]
    b = partd[year]
    p = proc[year]

    inflows = money(a["expanded_inflows_usd"])
    gross = money(a["irs_gross_collections_usd"])
    refunds = money(a["irs_refunds_usd"])
    net = money(a["irs_net_collections_candidate_usd"])
    baseline = money(a["net_basis_candidate_balance_usd"])
    addition = money(b["partd_qualified_addition_usd"])
    partd_inflows = money(b["partd_inclusive_inflows_usd"])
    reference = money(baseline + addition)
    sensitivity = money(reference + p["non_va"])

    assert gross - refunds == net
    assert inflows - net == baseline
    assert money(b["existing_expanded_inflows_usd"]) == inflows
    assert inflows + addition == partd_inflows
    assert p["dod"] + p["doe"] + p["other"] == p["non_va"]
    assert p["non_va"] + p["va"] == p["all"]
    assert p["difference"] == 0
    assert p["exceptions"] == [0, 0, 0, 0]
    assert a["canonical_ledger_authorization"] == "NOT_AUTHORIZED"

    results.append({
        "fiscal_year": year,
        "expanded_inflows_before_partd_usd": inflows,
        "irs_gross_collections_usd": gross,
        "irs_refunds_usd": refunds,
        "irs_net_collections_candidate_usd": net,
        "net_irs_balance_before_partd_usd": baseline,
        "partd_qualified_addition_usd": addition,
        "partd_inclusive_inflows_usd": partd_inflows,
        "partd_inclusive_net_irs_balance_usd": reference,
        "dod_procurement_obligations_usd": p["dod"],
        "doe_procurement_obligations_usd": p["doe"],
        "other_non_va_procurement_obligations_usd": p["other"],
        "total_non_va_procurement_obligations_usd": p["non_va"],
        "procurement_sensitivity_balance_usd": sensitivity,
        "reference_status": "QUALIFIED_PROVISIONAL",
        "procurement_status": "HYPOTHETICAL_OBLIGATIONS_NOT_CASH",
        "canonical_ledger_authorization": "NOT_AUTHORIZED",
    })

    for key, value in [
        ("refunds", refunds),
        ("baseline", baseline),
        ("partd", addition),
        ("reference", reference),
        ("procurement", p["non_va"]),
        ("sensitivity", sensitivity),
    ]:
        totals[key] += value

# Independent seven-year control checks.
assert totals["refunds"] == D("92094284000.00")
assert totals["baseline"] == D("-208011901827.46")
assert totals["reference"] == D("-198142554212.81")
assert totals["reference"] == totals["baseline"] + totals["partd"]
assert totals["sensitivity"] == (
    totals["reference"] + totals["procurement"]
)

# Write only after all checks have passed.
EVIDENCE.mkdir(parents=True, exist_ok=True)

with OUTPUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    writer.writerows(results)

report = [
    "ETL-243E1 - FIRST DRAFT STATEWIDE ANNUAL BALANCE",
    "=" * 65,
    "FY2018-2024 | USD | QUALIFIED PROVISIONAL",
    "",
    "Fiscal year | Reference balance | Procurement sensitivity",
]
for row in results:
    report.append(
        f"{row['fiscal_year']} | "
        f"{row['partd_inclusive_net_irs_balance_usd']:,.2f} | "
        f"{row['procurement_sensitivity_balance_usd']:,.2f}"
    )

report += [
    "",
    f"Seven-year net IRS baseline: {totals['baseline']:,.2f}",
    f"Part D qualified addition: {totals['partd']:,.2f}",
    f"Part D-inclusive reference: {totals['reference']:,.2f}",
    f"Non-VA procurement obligations: {totals['procurement']:,.2f}",
    f"Procurement sensitivity: {totals['sensitivity']:,.2f}",
    "",
    "PASS: Seven annual IRS reconciliations",
    "PASS: Seven annual Part D reconciliations",
    "PASS: Seven annual procurement reconciliations",
    "PASS: Seven-year aggregate controls",
    "PASS: Procurement geography and funding-code checks",
    "",
    "SOURCE FILES:",
    str(IRS_FILE.relative_to(ROOT)),
    str(PARTD_FILE.relative_to(ROOT)),
    str(PROC_FILE.relative_to(ROOT)),
    "",
    "QUALIFICATIONS:",
    "- IRS net collections remain qualified provisional.",
    "- Part D addition remains qualified provisional.",
    "- FY2024 Medicare Part C evidence has partial-year coverage.",
    "- Procurement obligations are not cash expenditures.",
    "- Procurement overlap and economic incidence are unresolved.",
    "- The procurement scenario is illustrative, not an upper bound.",
    "- Mixed source timing and incomplete coverage remain.",
    "- COVID-related payment effects materially affect comparisons.",
    "- No canonical ledger authorization or database changes.",
    "",
    "PASS: ETL-243E1 reporting-only validation",
]

VALIDATION.write_text(
    "\n".join(report) + "\n", encoding="utf-8"
)
print("\n".join(report))

