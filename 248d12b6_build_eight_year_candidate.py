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

OUT = ROOT / "248d12b6_eight_year_candidate.csv"
REPORT = ROOT / "248d12b6_validation.txt"
DETAIL = ROOT / "248d12b6_fy2025_component_lineage.csv"
COVERAGE = ROOT / "248d12b6_fy2025_coverage_status.csv"

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

for path in (OUT, REPORT, DETAIL, COVERAGE):
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite: {path}")

historical = load(HIST)
worksheet = load(WORK)
summary = {r["metric"]: r["value"] for r in load(SUMMARY)}
observed_rows = load(OBSERVED)
retirement_history = load(RETIREMENT_HISTORY)

if len(historical) != 7:
    raise RuntimeError("Expected exactly seven historical rows")

fields = list(historical[0])

components = fields[
    fields.index("SSA_OASDI"):
    fields.index("revised_inflows_usd")
]

if len(components) != 15:
    raise RuntimeError(
        f"Expected 15 components, found {len(components)}"
    )

if [int(r["fiscal_year"]) for r in historical] != list(range(2018, 2025)):
    raise RuntimeError("Unexpected historical fiscal years")

for row in historical:
    parts = sum((D(row[k]) for k in components), Decimal(0))
    if money(parts) != money(D(row["revised_inflows_usd"])):
        raise RuntimeError(
            f"Historical inflow mismatch FY{row['fiscal_year']}"
        )
    if money(
        D(row["revised_inflows_usd"]) - D(row["irs_net_collections_usd"])
    ) != money(D(row["revised_balance_usd"])):
        raise RuntimeError(
            f"Historical balance mismatch FY{row['fiscal_year']}"
        )

candidate = [dict(row) for row in historical]

values = {}
lineage = []
unresolved = []
coverage = []

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

# 1. FY2025 worksheet: quantified inflows only.
mapped = set()

for row in worksheet:
    if str(row["fiscal_year"]) != "2025":
        continue

    family = row["family_id"]
    side = row["side"]
    amount_text = row["amount_usd"].strip()

    if side != "INFLOW":
        continue

    if not amount_text:
        if (
            row["evidence_status"] != "NOT_QUANTIFIED_FOR_SUBTOTAL"
            or row["presentation_treatment"] != "EXCLUDED_PENDING_RECONCILIATION"
        ):
            raise RuntimeError(
                f"Unexpected blank FY2025 amount: {family}"
            )

        unresolved.append(family)

        coverage.append({
            "family_or_component": family,
            "coverage_status": "NOT_QUANTIFIED",
            "amount_usd": "",
            "treatment": "EXCLUDED_PENDING_RECONCILIATION",
            "qualification": row["limitation"]
        })
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

if money(worksheet_total) != money(
    D(summary["identified_inflows_usd"])
):
    raise RuntimeError("FY2025 worksheet subtotal mismatch")

# 2. Additional assistance excluding already counted SSI.
historical_additive = D("9614460054.83")
ssi = D("1254709344.00")
valid_additive = D("301745793.50")

additional_assistance = money(
    historical_additive - ssi + valid_additive
)

if additional_assistance != D("8661496504.33"):
    raise RuntimeError("Assistance bridge mismatch")

if "SSA_SSI" not in mapped:
    raise RuntimeError("SSI missing from FY2025 worksheet")

add(
    "USASPENDING_ASSISTANCE_ADDITIVE",
    additional_assistance,
    "ETL-248D11",
    "Historical-policy carryforward excluding SSI",
    "Provisional assistance scenario; no FY2025 ledger authorization"
)

# 3. Non-VA procurement obligations.
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
        "Obligations, not outlays; VA procurement excluded"
    )

# 4. Military retirement: independent FY2025 extension.
observed = {
    int(row["fiscal_year"]): row
    for row in observed_rows
}

with localcontext() as ctx:
    ctx.prec = 40

    s2018 = D(observed[2018]["combined_monthly_usd"])
    s2022 = D(observed[2022]["combined_monthly_usd"])

    factor = (s2022 / s2018) ** (D(1) / D(4))

    s2023 = s2022 * factor
    s2024 = s2023 * factor
    s2025 = s2024 * factor

    modeled_2023 = money(6 * (s2022 + s2023))
    modeled_2024 = money(6 * (s2023 + s2024))
    modeled_2025 = money(6 * (s2024 + s2025))

published_retirement = {
    int(row["fiscal_year"]): D(row["trend_interpolated_usd"])
    for row in retirement_history
}

difference_2023 = modeled_2023 - published_retirement[2023]
difference_2024 = modeled_2024 - published_retirement[2024]

# Differences are documented; historical values remain unchanged.
add(
    "MILITARY_RETIREMENT_MODELED",
    modeled_2025,
    "ETL-245M12 / ETL-245M14 / ETL-248D12B4",
    "Full-precision September CAGR; adjacent endpoint interpolation",
    "Provisional modeled FY2025; historical precision differences documented"
)

# 5. Explicit missing-value handling.
missing = sorted(set(components) - set(values))

allowed_unquantified = {"ADDITIONAL_QUALIFIED_ASSISTANCE"}

unexpected_missing = set(missing) - allowed_unquantified

if unexpected_missing:
    raise RuntimeError(
        f"Unexpected missing presentation components: "
        f"{sorted(unexpected_missing)}"
    )

for component in missing:
    coverage.append({
        "family_or_component": component,
        "coverage_status": "NOT_QUANTIFIED",
        "amount_usd": "",
        "treatment": "EXCLUDED_FROM_IDENTIFIED_SUBTOTAL",
        "qualification": (
            "No separately quantified FY2025 candidate; "
            "blank does not mean zero"
        )
    })

# 6. Exact-cent reconciliation of identified FY2025 components.
taxes = money(D(summary["irs_net_collections_usd"]))
inflows = money(sum(values.values(), Decimal(0)))
balance = money(inflows - taxes)

expected_inflows = D("117533635347.03")
expected_balance = D("-44080337652.97")

if inflows != expected_inflows:
    raise RuntimeError(
        f"FY2025 inflow mismatch: {inflows} vs {expected_inflows}"
    )

if balance != expected_balance:
    raise RuntimeError(
        f"FY2025 balance mismatch: {balance} vs {expected_balance}"
    )

new = {"fiscal_year": "2025"}

for component in components:
    if component in values:
        new[component] = f"{money(values[component]):.2f}"
    else:
        new[component] = ""

new["revised_inflows_usd"] = f"{inflows:.2f}"
new["irs_net_collections_usd"] = f"{taxes:.2f}"
new["revised_balance_usd"] = f"{balance:.2f}"
new["accounting_status"] = (
    "FY2025_IDENTIFIED_AND_MODELED_SUBTOTAL_NOT_AUTHORIZED"
)

candidate.append(new)

if len(candidate) != 8:
    raise RuntimeError("Eight-year candidate row count mismatch")

# 7. Write candidate and supporting evidence.
with OUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(candidate)

with DETAIL.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "component", "amount_usd", "source",
            "basis", "qualification"
        ]
    )
    writer.writeheader()
    writer.writerows(lineage)

with COVERAGE.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "family_or_component", "coverage_status",
            "amount_usd", "treatment", "qualification"
        ]
    )
    writer.writeheader()
    writer.writerows(coverage)

reread = load(OUT)

if reread[:7] != historical:
    raise RuntimeError("Historical rows changed during output")

if reread[7] != new:
    raise RuntimeError("FY2025 row changed during output")

report = [
    "ETL-248D12B6 - EIGHT-YEAR PROVISIONAL DATASET",
    "NO DATABASE WRITES / NO LEDGER AUTHORIZATION",
    "",
    "STATUS: PASS",
    "HISTORICAL ROWS: 7 preserved exactly",
    "FISCAL YEARS: 2018-2025",
    "PRESENTATION COMPONENTS: 15",
    "",
    f"FY2025 worksheet identified subtotal: {worksheet_total:.2f}",
    f"FY2025 additional assistance excluding SSI: {additional_assistance:.2f}",
    f"FY2025 military retirement projection: {modeled_2025:.2f}",
    f"FY2025 total identified/modeled inflows: {inflows:.2f}",
    f"FY2025 IRS net collections: {taxes:.2f}",
    f"FY2025 provisional balance: {balance:.2f}",
    "",
    "MILITARY RETIREMENT PRECISION DOCUMENTATION:",
    f"FY2023 calculated minus historical: {difference_2023:.2f}",
    f"FY2024 calculated minus historical: {difference_2024:.2f}",
    "Historical values retained unchanged.",
    "",
    "UNQUANTIFIED FY2025 FAMILIES:",
    *unresolved,
    "",
    "UNQUANTIFIED PRESENTATION COMPONENTS:",
    *missing,
    "",
    "LIMITATIONS:",
    "FY2025 total is an identified and modeled subtotal.",
    "Missing amounts are not zero.",
    "Assistance classification is provisional.",
    "Procurement obligations are not cash outlays.",
    "Military retirement is modeled.",
    "FY2025 COVID/IIJA tagging remains unavailable.",
    "No canonical ledger authorization.",
    "",
    "SOURCE SHA256:",
    *[
        f"{p.relative_to(ROOT)}: {sha(p)}"
        for p in sources
    ]
]

REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")

print("\n".join(report))
print("")
print("OUTPUT FILES:")
for path in (OUT, REPORT, DETAIL, COVERAGE):
    print(f"  {path.name}")
