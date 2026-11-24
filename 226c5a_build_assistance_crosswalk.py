from pathlib import Path
import csv
import re
from decimal import Decimal

source = Path("226c4_stdout.txt")
destination = Path("226c5a_assistance_program_year_evidence.csv")
report = Path("226c5a_validation_report.txt")

if not source.is_file():
    raise SystemExit("Missing 226c4_stdout.txt")

content = source.read_text(encoding="utf-16")

rows = []

for line in content.splitlines():
    # Match PostgreSQL's aligned table output.
    # Permit whitespace and an optional UTF-8 BOM.
    line = line.lstrip("\ufeff").strip()

    if not re.match(r"^20(?:18|19|20|21|22|23|24)\s*\|", line):
        continue

    parts = [part.strip() for part in line.split("|")]

    if len(parts) != 6:
        raise SystemExit(
            f"Unexpected field count ({len(parts)}): {line[:200]}"
        )

    year, code, title, count, net, absolute = parts

    if not re.fullmatch(r"\d{2}\.\d{3}", code):
        raise SystemExit(
            f"Unexpected program code: {code!r}"
        )

    rows.append({
        "fiscal_year": int(year),
        "program_code": code,
        "program_title": title,
        "transactions": int(count),
        "net_obligations_usd": Decimal(net),
        "absolute_activity_usd": Decimal(absolute),
        "source_evidence": source.name,
        "original_disposition": "INCLUDE_ADDITIVE",
        "registry_crosswalk_treatment": "REVIEW_REQUIRED",
        "registry_family_id": "",
        "crosswalk_rationale": "",
    })

if len(rows) != 216:
    raise SystemExit(
        f"Expected 216 program-year rows; found {len(rows)}. "
        "No output written."
    )

keys = [(r["fiscal_year"], r["program_code"]) for r in rows]

if len(keys) != len(set(keys)):
    raise SystemExit("Duplicate program-year keys detected.")

annual = {}

for row in rows:
    year = row["fiscal_year"]
    annual[year] = annual.get(year, Decimal("0")) + row["net_obligations_usd"]

expected = {
    2018: Decimal("7388375150.75"),
    2019: Decimal("7913240351.71"),
    2020: Decimal("15588133958.75"),
    2021: Decimal("27012354136.13"),
    2022: Decimal("11997036710.62"),
    2023: Decimal("11257319934.71"),
    2024: Decimal("11839873255.40"),
}

errors = [
    f"{year}: observed={annual.get(year)} expected={amount}"
    for year, amount in expected.items()
    if annual.get(year) != amount
]

if errors:
    raise SystemExit(
        "Annual reconciliation failed:\n" + "\n".join(errors)
    )

with destination.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

lines = [
    "ETL-226C5A - ASSISTANCE PROGRAM-YEAR EVIDENCE",
    "=" * 75,
    "Source: 226c4_stdout.txt",
    "Database writes: NONE",
    "Registry writes: NONE",
    "",
    f"Program-year rows: {len(rows)}",
    f"Unique program-year keys: {len(set(keys))}",
    "",
    "ANNUAL RECONCILIATION",
]

for year in sorted(expected):
    lines.append(
        f"{year}: ${annual[year]:,.2f} PASS"
    )

lines.extend([
    "",
    "All rows initialized as REVIEW_REQUIRED.",
    "No crosswalk accounting decisions have been made.",
    "",
    "ETL-226C5A PASS",
])

report.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("\n".join(lines))
print()
print("CSV:", destination)
print("Report:", report)
