import csv
import io
import json
import subprocess
import sys
import zipfile
from collections import defaultdict
from decimal import Decimal

ZIP_PATH = sys.argv[1]
PSQL = r"C:\Program Files\PostgreSQL\18\bin\psql.exe"
ZERO = Decimal("0")

sql = """
SELECT row_to_json(x)
FROM (
    SELECT
        source_program_code,
        resolved_accounting_disposition,
        methodology_version,
        valid_from_fiscal_year,
        valid_through_fiscal_year,
        federal_inflow_source_policy_id,
        mapping_basis
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND (valid_from_fiscal_year IS NULL
           OR valid_from_fiscal_year <= 2025)
) x
ORDER BY source_program_code,
         valid_from_fiscal_year DESC NULLS LAST,
         valid_through_fiscal_year DESC NULLS FIRST,
         methodology_version DESC
"""

cmd = [
    PSQL, "-X", "-A", "-t",
    "-v", "ON_ERROR_STOP=1",
    "-h", "localhost",
    "-p", "5432",
    "-U", "postgres",
    "-d", "wcffbp",
    "-c", sql
]

result = subprocess.run(
    cmd, capture_output=True, text=True, check=True
)

history = defaultdict(list)
for line in result.stdout.splitlines():
    if line.strip():
        item = json.loads(line)
        history[item["source_program_code"]].append(item)

def choose_mapping(program):
    rows = history.get(program, [])
    if not rows:
        return None
    return rows[0]

def category(mapping):
    if mapping is None:
        return "NO_HISTORICAL_MAPPING"

    through = mapping["valid_through_fiscal_year"]
    valid = through is None or through >= 2025

    disposition = mapping["resolved_accounting_disposition"]

    if valid and disposition == "INCLUDE_ADDITIVE":
        return "VALID_FY2025_ADDITIVE"

    if disposition == "INCLUDE_ADDITIVE":
        return "HISTORICAL_ADDITIVE_EXPIRED"

    if disposition == "EXCLUDE_DUPLICATE":
        return "HISTORICAL_DUPLICATE_EXPIRED"

    if disposition in ("WITHHOLD_UNRESOLVED", "REFERENCE_ONLY"):
        return "HISTORICAL_WITHHELD_OR_REFERENCE"

    return "OTHER_HISTORICAL_DISPOSITION"

totals = defaultdict(lambda: [0, ZERO])
programs = defaultdict(lambda: [0, ZERO])
details = {}

with zipfile.ZipFile(ZIP_PATH) as archive:
    members = [
        name for name in archive.namelist()
        if "Assistance_PrimeTransactions_" in name
        and name.lower().endswith(".csv")
    ]
    if len(members) != 1:
        raise RuntimeError(
            f"Expected one prime CSV; found {len(members)}"
        )

    with archive.open(members[0]) as raw:
        with io.TextIOWrapper(
            raw, encoding="utf-8-sig", newline=""
        ) as stream:
            reader = csv.DictReader(stream)

            for row in reader:
                if row["action_date_fiscal_year"].strip() != "2025":
                    raise RuntimeError("Unexpected fiscal year")

                program = row["cfda_number"].strip()
                amount = Decimal(
                    row["federal_action_obligation"].strip()
                )

                mapping = choose_mapping(program)
                group = category(mapping)

                totals[group][0] += 1
                totals[group][1] += amount

                key = (group, program)
                programs[key][0] += 1
                programs[key][1] += amount

                if key not in details:
                    details[key] = mapping

print("ETL-248B8H7D2 — HISTORICAL POLICY MATERIALITY")
print("READ ONLY — NO DATABASE OR LEDGER WRITES")
print("=" * 76)

print("\n=== FY2025 CATEGORY RECONCILIATION ===")
grand_rows = 0
grand_amount = ZERO

for group in sorted(totals):
    count, amount = totals[group]
    grand_rows += count
    grand_amount += amount
    print(f"{group:40} {count:>8,}  ${amount:>22,.2f}")

print("-" * 76)
print(f"{'TOTAL':40} {grand_rows:>8,}  ${grand_amount:>22,.2f}")

expected_rows = 83464
expected_amount = Decimal("73717461133.21")

assert grand_rows == expected_rows, (
    grand_rows, expected_rows
)
assert grand_amount == expected_amount, (
    grand_amount, expected_amount
)

print("\nCONTROL RECONCILIATION: PASS")

print("\n=== TOP 60 PROGRAMS BY ABSOLUTE NET OBLIGATIONS ===")

ranked = sorted(
    programs.items(),
    key=lambda item: abs(item[1][1]),
    reverse=True
)

for (group, program), (count, amount) in ranked[:60]:
    mapping = details[(group, program)]
    method = (
        mapping["methodology_version"]
        if mapping else "NONE"
    )
    through = (
        mapping["valid_through_fiscal_year"]
        if mapping else None
    )

    print(
        f"AL={program:8} "
        f"rows={count:>6,} "
        f"net=${amount:>19,.2f} "
        f"group={group} "
        f"through={through} "
        f"method={method}"
    )

print("\n=== HISTORICAL MAPPING COVERAGE ===")
print(f"Historical program codes: {len(history)}")
print(f"FY2025 program codes: {len(set(p for _, p in programs))}")
print(f"Programs in ranked report: {len(programs)}")

print("\nRESULT: PASS")
