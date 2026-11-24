import csv
import hashlib
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path

ROOT = Path.cwd()

HIST = ROOT / "246c3_stacked_components_candidate.csv"
WORK = ROOT / "evidence/statewide/provisional_fy2025/248b9s_fy2025_component_worksheet.csv"
SUMMARY = ROOT / "evidence/statewide/provisional_fy2025/248b9s_fy2025_balance_summary.csv"
OBSERVED = ROOT / "245m12_military_retirement_observed.csv"
RETIREMENT_HISTORY = ROOT / "245m14_military_retirement_consistent_scenarios.csv"

OUT = ROOT / "248d12b2_eight_year_candidate.csv"
REPORT = ROOT / "248d12b2_validation.txt"
DETAIL = ROOT / "248d12b2_fy2025_component_lineage.csv"

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

sources = (HIST, WORK, SUMMARY, OBSERVED, RETIREMENT_HISTORY)

for path in sources:
    if not path.is_file():
        raise RuntimeError(f"Missing required source: {path}")

for path in (OUT, REPORT, DETAIL):
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite: {path}")

historical = load(HIST)
worksheet = load(WORK)
summary = {r["metric"]: r["value"] for r in load(SUMMARY)}
observed_rows = load(OBSERVED)
retirement_history = load(RETIREMENT_HISTORY)

fields = list(historical[0])
components = fields[
    fields.index("SSA_OASDI"):
    fields.index("revised_inflows_usd")
]

assert len(components) == 15
assert len(historical) == 7
assert [int(r["fiscal_year"]) for r in historical] == list(range(2018, 2025))

# Validate the published historical source without modifying its values.
for row in historical:
    parts = sum((D(row[k]) for k in components), Decimal(0))
    assert money(parts) == money(D(row["revised_inflows_usd"]))
    assert money(
        D(row["revised_inflows_usd"]) - D(row["irs_net_collections_usd"])
    ) == money(D(row["revised_balance_usd"]))

candidate = [dict(row) for row in historical]

values = {}
lineage = []
unresolved = []

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

# 1. Quantified FY2025 worksheet components.
mapped = set()

for row in worksheet:
    if str(row["fiscal_year"]) != "2025":
        continue

    if row["side"] != "INFLOW":
        continue

    family = row["family_id"]
    amount_text = row["amount_usd"].strip()

    # A blank unresolved family is not a measured zero.
    if not amount_text:
        if (
            row["evidence_status"] != "NOT_QUANTIFIED_FOR_SUBTOTAL"
            or row["presentation_treatment"] != "EXCLUDED_PENDING_RECONCILIATION"
        ):
            raise RuntimeError(
                f"Unexpected blank FY2025 amount: {family}"
            )

        unresolved.append(family)
        continue

    component = (
        "USASPENDING_ASSISTANCE_ADDITIVE"
        if family == "SSA_SSI"
        else family
    )

    if component not in components:
        raise RuntimeError(
            f"Unmapped quantified FY2025 family: {family}"
        )

    add(
        component,
        amount_text,
        row["evidence_reference"],
        row["measurement_basis"],
        row["limitation"]
    )

    mapped.add(family)

worksheet_total = sum(
    (
        D(row["amount_usd"])
        for row in worksheet
        if str(row["fiscal_year"]) == "2025"
        and row["side"] == "INFLOW"
        and row["amount_usd"].strip()
    ),
    Decimal(0)
)

assert money(worksheet_total) == money(
    D(summary["identified_inflows_usd"])
)

# 2. FY2025 assistance scenario, excluding SSI already in worksheet.
historical_additive = D("9614460054.83")
ssi = D("1254709344.00")
valid_additive = D("301745793.50")

additional_assistance = money(
    historical_additive - ssi + valid_additive
)

assert additional_assistance == D("8661496504.33")
assert "SSA_SSI" in mapped

add(
    "USASPENDING_ASSISTANCE_ADDITIVE",
    additional_assistance,
    "ETL-248B9W / ETL-248D11",
    "FY2025 obligations; historical-policy carryforward excluding SSI",
    "Provisional scenario; expired FY2024 policies not extended"
)

# 3. Validated FY2025 non-VA procurement obligations.
procurement = (
    ("DOD_PROCUREMENT_OBLIGATIONS", "8709600786.41"),
    ("DOE_PROCUREMENT_OBLIGATIONS", "4395414614.01"),
    ("OTHER_NON_VA_PROCUREMENT_OBLIGATIONS", "2414229043.63")
)

for component, amount in procurement:
    add(
        component,
        amount,
        "ETL-248C9",
        "FY2025 procurement obligations",
        "Obligations, not cash outlays; VA procurement excluded"
    )

# 4. Military retirement projection.
# Reproduce the historical trend using observed September endpoints.
#
# Historical FY2024 value must agree with the existing
# published retirement scenario before extending to FY2025.

observed = {}

for row in observed_rows:
    year = int(row["fiscal_year"])
    observed[year] = row

with localcontext() as ctx:
    ctx.prec = 40

    start = D(observed[2018]["combined_monthly_usd"])
    end = D(observed[2022]["combined_monthly_usd"])

    growth_factor = (end / start) ** (Decimal(1) / Decimal(4))

    sep_2023 = end * growth_factor
    sep_2024 = end * growth_factor ** 2
    sep_2025 = end * growth_factor ** 3

    modeled_2024 = money((sep_2023 + sep_2024) * 6)
    modeled_2025 = money((sep_2024 + sep_2025) * 6)

published_retirement = {
    int(row["fiscal_year"]): D(row["trend_interpolated_usd"])
    for row in retirement_history
}

if modeled_2024 != money(published_retirement[2024]):
    raise RuntimeError(
        "Military retirement historical method mismatch: "
        f"calculated FY2024={modeled_2024}, "
        f"published FY2024={published_retirement[2024]}"
    )

add(
    "MILITARY_RETIREMENT_MODELED",
    modeled_2025,
    "ETL-245M12 / ETL-245M14 / ETL-248D12B2",
    "September endpoint CAGR; adjacent September interpolation",
    "Modeled FY2025 projection, not observed payments"
)

# 5. Validate all quantified presentation components.
#
# A missing component is not automatically zero.
missing = sorted(set(components) - set(values))

if missing:
    print("UNQUANTIFIED PRESENTATION COMPONENTS:")
    for component in missing:
        print(f"  {component}")

    print("")
    print("UNRESOLVED WORKSHEET FAMILIES:")
    for family in unresolved:
        print(f"  {family}")

    raise RuntimeError(
        "FY2025 presentation component coverage is incomplete. "
        "No zero substitution or dataset publication authorized."
    )

# 6. Exact-cent reconciliation.
taxes = money(D(summary["irs_net_collections_usd"]))
inflows = money(sum(values.values(), Decimal(0)))
balance = money(inflows - taxes)

new = {"fiscal_year": "2025"}

for component in components:
    new[component] = f"{money(values[component]):.2f}"

new["revised_inflows_usd"] = f"{inflows:.2f}"
new["irs_net_collections_usd"] = f"{taxes:.2f}"
new["revised_balance_usd"] = f"{balance:.2f}"
new["accounting_status"] = (
    "FY2025_PROVISIONAL_SCENARIO_NOT_AUTHORIZED"
)

candidate.append(new)

assert len(candidate) == 8
assert money(
    sum((D(new[k]) for k in components), Decimal(0))
) == inflows
assert money(inflows - taxes) == balance

with OUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(candidate)

with DETAIL.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "component",
            "amount_usd",
            "source",
            "basis",
            "qualification"
        ]
    )
    writer.writeheader()
    writer.writerows(lineage)

reread = load(OUT)
assert reread[:7] == historical
assert reread[7] == new

report = [
    "ETL-248D12B2 - EIGHT-YEAR PROVISIONAL DATASET",
    "READ ONLY SOURCES - NO DATABASE OR LEDGER WRITES",
    "",
    "STATUS: PASS",
    "HISTORICAL ROWS: 7 unchanged",
    "CANDIDATE YEARS: 2018-2025",
    "PRESENTATION COMPONENTS: 15",
    f"FY2025 worksheet subtotal: {worksheet_total:.2f}",
    f"FY2025 additional assistance excluding SSI: {additional_assistance:.2f}",
    f"FY2025 military retirement modeled: {modeled_2025:.2f}",
    f"FY2025 total inflows: {inflows:.2f}",
    f"FY2025 IRS net collections: {taxes:.2f}",
    f"FY2025 provisional balance: {balance:.2f}",
    "",
    "UNRESOLVED WORKSHEET FAMILIES:",
    *unresolved,
    "",
    "QUALIFICATIONS:",
    "Historical-policy assistance is a scenario, not FY2025 authorization.",
    "Procurement represents obligations rather than cash outlays.",
    "Military retirement is modeled, not observed annual payments.",
    "Other worksheet families remain unquantified.",
    "COVID/IIJA FY2025 tags remain unquantified.",
    "No canonical ledger authorization.",
    "",
    "SOURCE SHA256:",
    *[
        f"{path.relative_to(ROOT)}: {sha(path)}"
        for path in sources
    ]
]

REPORT.write_text(
    "\n".join(report) + "\n",
    encoding="utf-8"
)

print("\n".join(report[:14]))
