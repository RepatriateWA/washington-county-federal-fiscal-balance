import csv
import hashlib
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path

ROOT = Path.cwd()
HIST = ROOT / "246c3_stacked_components_candidate.csv"
WORK = ROOT / "evidence/statewide/provisional_fy2025/248b9s_fy2025_component_worksheet.csv"
SUMMARY = ROOT / "evidence/statewide/provisional_fy2025/248b9s_fy2025_balance_summary.csv"
OBSERVED = ROOT / "245m12_military_retirement_observed.csv"

OUT = ROOT / "248d12b_eight_year_candidate.csv"
REPORT = ROOT / "248d12b_validation.txt"
DETAIL = ROOT / "248d12b_fy2025_component_lineage.csv"

CENT = Decimal("0.01")

def D(value):
    return Decimal(str(value))

def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

def load(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

for path in (HIST, WORK, SUMMARY, OBSERVED):
    if not path.is_file():
        raise RuntimeError(f"Missing required source: {path}")
for path in (OUT, REPORT, DETAIL):
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite: {path}")

historical = load(HIST)
worksheet = load(WORK)
summary = {r["metric"]: r["value"] for r in load(SUMMARY)}
observed = {int(r["fiscal_year"]): r for r in load(OBSERVED)}

fields = list(historical[0])
components = fields[
    fields.index("SSA_OASDI"):
    fields.index("revised_inflows_usd")
]
assert len(components) == 15
assert len(historical) == 7
assert [int(r["fiscal_year"]) for r in historical] == list(range(2018, 2025))

for r in historical:
    parts = sum((D(r[k]) for k in components), Decimal(0))
    assert money(parts) == money(D(r["revised_inflows_usd"]))
    assert money(D(r["revised_inflows_usd"]) - D(r["irs_net_collections_usd"])) == money(D(r["revised_balance_usd"]))

# Keep the historical source records and their original text representations.
candidate = [dict(r) for r in historical]

values = {}
lineage = []

def add(component, amount, source, basis, qualification):
    if component not in components:
        raise RuntimeError(f"Unknown presentation component: {component}")
    amount = money(D(amount))
    values[component] = values.get(component, Decimal(0)) + amount
    lineage.append({
        "component": component,
        "amount_usd": f"{amount:.2f}",
        "source": source,
        "basis": basis,
        "qualification": qualification
    })

# Every worksheet family must be accounted for, rather than silently dropped.
mapped = set()
for row in worksheet:
    if str(row["fiscal_year"]) != "2025" or row["side"] != "INFLOW":
        continue
    family = row["family_id"]
    if family == "SSA_SSI":
        component = "USASPENDING_ASSISTANCE_ADDITIVE"
    else:
        component = family
    if component not in components:
        raise RuntimeError(f"Unmapped FY2025 worksheet family: {family}")
    if not row["amount_usd"].strip():
        raise RuntimeError(f"Missing worksheet amount: {family}")
    add(
        component, row["amount_usd"],
        row["evidence_reference"], row["measurement_basis"],
        row["limitation"]
    )
    mapped.add(family)

worksheet_total = sum(
    (D(r["amount_usd"]) for r in worksheet
     if str(r["fiscal_year"]) == "2025"
     and r["side"] == "INFLOW"
     and r["amount_usd"].strip()),
    Decimal(0)
)
assert money(worksheet_total) == money(D(summary["identified_inflows_usd"]))

# Carryforward classification scenario, excluding SSI already in worksheet.
historical_additive = D("9614460054.83")
ssi = D("1254709344.00")
valid_additive = D("301745793.50")
additional_assistance = money(historical_additive - ssi + valid_additive)
assert additional_assistance == D("8661496504.33")
assert "SSA_SSI" in mapped

add(
    "USASPENDING_ASSISTANCE_ADDITIVE",
    additional_assistance,
    "ETL-248B9W / ETL-248D11",
    "FY2025 obligations; historical-policy carryforward net of SSI",
    "Scenario only; FY2024-only policies not renewed or ledger-authorized"
)

# Independently validated FY2025 non-VA procurement controls.
for component, amount in (
    ("DOD_PROCUREMENT_OBLIGATIONS", "8709600786.41"),
    ("DOE_PROCUREMENT_OBLIGATIONS", "4395414614.01"),
    ("OTHER_NON_VA_PROCUREMENT_OBLIGATIONS", "2414229043.63"),
):
    add(
        component, amount, "ETL-248C9",
        "FY2025 procurement obligations",
        "Obligations, not observed cash outlays; VA procurement excluded"
    )

# Consistent military-retirement extension: September endpoint CAGR,
# then average adjacent September monthly snapshots * 12.
with localcontext() as ctx:
    ctx.prec = 40
    start = D(observed[2018]["combined_monthly_usd"])
    end = D(observed[2022]["combined_monthly_usd"])
    growth = (end / start) ** (Decimal(1) / Decimal(4))
    sep_2024 = end * growth ** 2
    sep_2025 = end * growth ** 3
    retirement = money((sep_2024 + sep_2025) * 6)

add(
    "MILITARY_RETIREMENT_MODELED",
    retirement, "ETL-245M12 / ETL-245M14 / ETL-248D12B",
    "2018-2022 September endpoint CAGR; adjacent-month interpolation",
    "Modeled projection; no FY2025 observed annual cash series"
)

missing = set(components) - set(values)
if missing:
    raise RuntimeError(f"Unresolved FY2025 presentation components: {sorted(missing)}")

taxes = money(D(summary["irs_net_collections_usd"]))
inflows = money(sum(values.values(), Decimal(0)))
balance = money(inflows - taxes)

new = {"fiscal_year": "2025"}
for component in components:
    new[component] = f"{money(values[component]):.2f}"
new["revised_inflows_usd"] = f"{inflows:.2f}"
new["irs_net_collections_usd"] = f"{taxes:.2f}"
new["revised_balance_usd"] = f"{balance:.2f}"
new["accounting_status"] = "FY2025_PROVISIONAL_SCENARIO_NOT_AUTHORIZED"
candidate.append(new)

assert len(candidate) == 8
assert money(sum((D(new[k]) for k in components), Decimal(0))) == inflows
assert money(inflows - taxes) == balance

with OUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(candidate)

with DETAIL.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "component", "amount_usd", "source", "basis", "qualification"
    ])
    writer.writeheader()
    writer.writerows(lineage)

# Verify historical values survived the CSV round trip.
reread = load(OUT)
assert reread[:7] == historical
assert reread[7] == new

report = [
    "ETL-248D12B - EIGHT-YEAR PROVISIONAL DATASET",
    "READ ONLY SOURCES - NO DATABASE OR LEDGER WRITES",
    "",
    "STATUS: PASS",
    "HISTORICAL ROWS: 7 unchanged",
    "CANDIDATE YEARS: 2018-2025",
    "PRESENTATION COMPONENTS: 15",
    f"FY2025 worksheet subtotal: {worksheet_total:.2f}",
    f"FY2025 additional assistance excluding SSI: {additional_assistance:.2f}",
    f"FY2025 military retirement modeled: {retirement:.2f}",
    f"FY2025 total inflows: {inflows:.2f}",
    f"FY2025 IRS net collections: {taxes:.2f}",
    f"FY2025 provisional balance: {balance:.2f}",
    "",
    "QUALIFICATIONS:",
    "Historical-policy assistance carryforward is a scenario, not FY2025 authorization.",
    "FY2025 procurement represents obligations rather than cash outlays.",
    "Military retirement is modeled, not observed FY2025 annual payments.",
    "Worksheet includes forecasts, proxies and mixed measurement periods.",
    "COVID/IIJA FY2025 tags remain unquantified; do not substitute zeros.",
    "No canonical ledger authorization.",
    "",
    "SOURCE SHA256:",
    *[f"{p.relative_to(ROOT)}: {sha(p)}"
      for p in (HIST, WORK, SUMMARY, OBSERVED)],
    "",
    f"OUTPUT: {OUT.name}",
    f"LINEAGE: {DETAIL.name}"
]
REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")

print("\n".join(report[:14]))
