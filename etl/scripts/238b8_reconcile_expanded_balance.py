from pathlib import Path
from decimal import Decimal
import csv

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "evidence/statewide/provisional_v0_1/238a_annual_balance_v0_1.csv"
OUTPUT = ROOT / "evidence/statewide/provisional_v0_1/238b8_expanded_balance.csv"

D = Decimal

# Verified ETL-238B5B controls, USD.
# Each pair: established additive, additional qualified.
CONTROLS = {
    2018: ("7388375150.75", "0"),
    2019: ("7913240351.71", "0"),
    2020: ("15588133958.75", "991541734.03"),
    2021: ("27012354136.13", "2560720942.41"),
    2022: ("11997036710.62", "1794448658.11"),
    2023: ("11257319934.71", "2400384414.22"),
    2024: ("11839873255.40", "1356271681.25"),
}

with SOURCE.open(newline="", encoding="utf-8-sig") as f:
    source_rows = list(csv.DictReader(f))

if len(source_rows) != 7:
    raise ValueError("Expected exactly seven ETL-238A annual rows")

results = []
seen = set()

for row in source_rows:
    year = int(row["fiscal_year"])

    if year not in CONTROLS or year in seen:
        raise ValueError(f"Unexpected or duplicate fiscal year: {year}")

    seen.add(year)

    established, additional = map(D, CONTROLS[year])

    baseline_assistance = D(row["assistance_additive_usd"])
    baseline_inflows = D(row["provisional_inflows_usd"])
    baseline_balance = D(row["provisional_balance_usd"])
    irs_gross = D(row["irs_gross_collections_usd"])

    if baseline_assistance != established:
        raise ValueError(f"Assistance mismatch for {year}")

    if baseline_inflows - irs_gross != baseline_balance:
        raise ValueError(f"Baseline arithmetic mismatch for {year}")

    expanded_assistance = established + additional
    expanded_inflows = baseline_inflows + additional
    expanded_balance = expanded_inflows - irs_gross

    results.append({
        "fiscal_year": year,
        "baseline_assistance_usd": established,
        "additional_qualified_assistance_usd": additional,
        "expanded_assistance_usd": expanded_assistance,
        "baseline_inflows_usd": baseline_inflows,
        "expanded_inflows_usd": expanded_inflows,
        "irs_gross_collections_usd": irs_gross,
        "baseline_balance_usd": baseline_balance,
        "expanded_provisional_balance_usd": expanded_balance,
        "refund_adjustment_applied": "NO",
        "additional_assistance_status": "QUALIFIED_PROVISIONAL",
        "balance_status": "PROVISIONAL_MIXED_MEASURE_PARTIAL_COVERAGE",
    })

if seen != set(CONTROLS):
    raise ValueError("Incomplete fiscal-year coverage")

total_additional = sum(
    (D(r["additional_qualified_assistance_usd"]) for r in results),
    D("0"),
)

if total_additional != D("9103367430.02"):
    raise ValueError("Additional assistance control total mismatch")

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

with OUTPUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(results[0]))
    writer.writeheader()
    writer.writerows(results)

print("ETL-238B8 — PASS")
print("Seven fiscal years reconciled")
print(f"Additional assistance: ${total_additional:,.2f}")
print()
print("Year | Baseline ($B) | Additional ($B) | Expanded ($B)")

for r in results:
    print(
        f'{r["fiscal_year"]} | '
        f'{D(r["baseline_balance_usd"])/D("1e9"):.3f} | '
        f'{D(r["additional_qualified_assistance_usd"])/D("1e9"):.3f} | '
        f'{D(r["expanded_provisional_balance_usd"])/D("1e9"):.3f}'
    )

print(f"\nOutput: {OUTPUT}")