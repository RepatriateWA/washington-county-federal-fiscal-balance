
from __future__ import annotations

import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "accounting_registry/v0_3_3_working/canonical_annual_ledger.csv"
G = ROOT / "236g_stdout.txt"
I = ROOT / "236i_stdout.txt"
OUT = ROOT / "evidence/statewide/provisional_v0_1"
OUT.mkdir(parents=True, exist_ok=True)

D = Decimal
ZERO = D("0")

INCLUDED = {
    "SSA_OASDI",
    "MEDICARE_FFS_AB",
    "MEDICARE_PART_C",
    "MEDICAID",
    "CHIP",
    "VA_GDX",
    "FEDERAL_CIVILIAN_WAGES",
    "FEDERAL_MILITARY_WAGES",
}
OUTFLOW = "IRS_GROSS_COLLECTIONS"

def read_psql_table(path, required):
    if not path.exists():
        raise FileNotFoundError(path)

    raw = path.read_bytes()

    # Detect Windows PowerShell UTF-16 output and UTF-8 BOM.
    if raw.startswith(b"\xff\xfe"):
        content = raw.decode("utf-16-le")
    elif raw.startswith(b"\xfe\xff"):
        content = raw.decode("utf-16-be")
    elif raw.startswith(b"\xef\xbb\xbf"):
        content = raw.decode("utf-8-sig")
    else:
        content = raw.decode("utf-8")

    # Remove any decoded byte-order mark.
    content = content.lstrip("\ufeff")

    rows = []
    headers = None

    for line in content.splitlines():
        if "|" not in line:
            continue

        parts = [p.strip() for p in line.split("|")]

        if parts[0] == required[0]:
            headers = parts

            if not all(x in headers for x in required):
                raise ValueError(
                    f"Missing required columns in {path}: {required}"
                )
            continue

        if not parts[0].isdigit():
            continue

        if headers is None:
            raise ValueError(
                f"Data encountered before header in {path}"
            )

        if len(parts) != len(headers):
            raise ValueError(
                f"Column count mismatch in {path}: {line}"
            )

        rows.append(dict(zip(headers, parts)))

    if not rows:
        raise ValueError(f"No data rows found in {path}")

    return rows

def money(value):
    return D(str(value).strip()) if str(value).strip() else ZERO

def write_csv(filename, rows, fields):
    with (OUT / filename).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

with REGISTRY.open(newline="", encoding="utf-8-sig") as f:
    ledger = list(csv.DictReader(f))

g_rows = read_psql_table(
    G, ["fiscal_year", "disposition", "obligations_usd"]
)
i_rows = read_psql_table(
    I, ["fiscal_year", "additive_obligations_usd",
        "covid_tagged_usd", "iija_tagged_usd", "both_tagged_usd"]
)

g = defaultdict(lambda: defaultdict(lambda: ZERO))
for r in g_rows:
    g[int(r["fiscal_year"])][r["disposition"]] += money(
        r["obligations_usd"]
    )

i = {int(r["fiscal_year"]): r for r in i_rows}

annual = defaultdict(lambda: defaultdict(lambda: ZERO))
bridge = []

for r in ledger:
    year = int(r["fiscal_year"])
    if year not in range(2018, 2025):
        continue

    family = r["family_id"]
    candidate = r["candidate_observed_amount_usd"]
    included = family in INCLUDED or family == OUTFLOW
    status = (
        "INCLUDED_PROVISIONAL"
        if included and candidate
        else "WITHHELD_OR_NOT_INCORPORATED"
    )

    if included and not candidate:
        raise ValueError(f"Missing required amount: {year} {family}")

    if included:
        annual[year][
            "outflows" if family == OUTFLOW else "core_inflows"
        ] += money(candidate)

    bridge.append({
        "fiscal_year": year,
        "family_id": family,
        "candidate_observed_amount_usd": candidate,
        "included_amount_usd": candidate if included else "",
        "treatment": status,
        "measure_basis": r["measure_basis"],
        "ledger_status": r["ledger_status"],
        "source_reference": r["source_reference"],
    })

results = []
validation = []

for year in range(2018, 2025):
    if year not in i:
        raise ValueError(f"Missing ETL-236I year {year}")

    gross_additive = g[year]["INCLUDE_ADDITIVE"]
    program_additive = money(i[year]["additive_obligations_usd"])
    covid = money(i[year]["covid_tagged_usd"])
    iija = money(i[year]["iija_tagged_usd"])
    both = money(i[year]["both_tagged_usd"])

    # ETL-236I is a subset of ETL-236G. Preserve the
    # extraordinary tags from that subset, but do not assume
    # unexamined award-level additions have no such tags.
    award_difference = gross_additive - program_additive
    if award_difference < ZERO:
        raise ValueError(f"Negative award-level bridge: {year}")

    core = annual[year]["core_inflows"]
    outflows = annual[year]["outflows"]

    if not outflows:
        raise ValueError(f"Missing IRS outflow: {year}")

    inflows = core + gross_additive
    balance = inflows - outflows

    results.append({
        "fiscal_year": year,
        "core_inflows_usd": core,
        "assistance_additive_usd": gross_additive,
        "provisional_inflows_usd": inflows,
        "irs_gross_collections_usd": outflows,
        "provisional_balance_usd": balance,
        "assistance_covid_tagged_usd": covid,
        "balance_excluding_tagged_assistance_covid_usd": balance - covid,
        "assistance_iija_tagged_usd": iija,
        "balance_excluding_tagged_assistance_iija_usd": balance - iija,
        "assistance_both_tagged_usd": both,
        "balance_excluding_either_assistance_tag_usd":
            balance - covid - iija + both,
        "procurement_included": "NO",
        "balance_status": "PROVISIONAL_MIXED_MEASURE_PARTIAL_COVERAGE",
    })

    bridge.append({
        "fiscal_year": year,
        "family_id": "USASPENDING_ASSISTANCE_ADDITIVE",
        "candidate_observed_amount_usd": gross_additive,
        "included_amount_usd": gross_additive,
        "treatment": "INCLUDED_PROVISIONAL_POLICY_CLASSIFIED",
        "measure_basis": "FEDERAL_FISCAL_YEAR_OBLIGATION",
        "ledger_status": "NOT_YET_AUTHORIZED",
        "source_reference": "ETL-236G; ETL-236I; ETL-236J",
    })

    validation.extend([
        {
            "fiscal_year": year,
            "check": "G_MINUS_I_AWARD_LEVEL_DIFFERENCE",
            "amount_usd": award_difference,
            "status": "RECONCILED_BY_ETL_236J_RAILROAD",
        },
        {
            "fiscal_year": year,
            "check": "COVID_IIJA_INTERSECTION",
            "amount_usd": both,
            "status": "SUBTRACT_ONCE_FOR_COMBINED_EXCLUSION",
        },
        {
            "fiscal_year": year,
            "check": "PROCUREMENT_OMITTED",
            "amount_usd": "",
            "status": "MATERIAL_COVERAGE_GAP",
        },
        {
            "fiscal_year": year,
            "check": "MEDICARE_PART_C_COVERAGE",
            "amount_usd": "",
            "status": (
                "JAN_SEP_ONLY"
                if year == 2024 else "CALENDAR_YEAR_BASIS"
            ),
        },
    ])

write_csv(
    "238a_annual_balance_v0_1.csv",
    results,
    list(results[0].keys()),
)
write_csv(
    "238a_source_family_bridge_v0_1.csv",
    bridge,
    list(bridge[0].keys()),
)
write_csv(
    "238a_validation_v0_1.csv",
    validation,
    list(validation[0].keys()),
)

print("ETL-238A completed")
print(f"Registry records read: {len(ledger)}")
print(f"Years produced: {len(results)}")
print(f"Output directory: {OUT}")
print()
print("Year | Inflows ($B) | IRS ($B) | Balance ($B)")
for r in results:
    print(
        f'{r["fiscal_year"]} | '
        f'{r["provisional_inflows_usd"]/D("1e9"):.3f} | '
        f'{r["irs_gross_collections_usd"]/D("1e9"):.3f} | '
        f'{r["provisional_balance_usd"]/D("1e9"):.3f}'
    )
