from pathlib import Path

root = Path("etl/sql")

names = [
    "221p_historical_assistance_accounting_bridge.sql",
    "221q_historical_assistance_policy_resolution.sql",
    "221j_assistance_accounting_reconciliation.sql",
    "214j_audit_seven_year_program_accounting.sql",
    "212c_profile_accounting_closure_materiality.sql",
    "213z_verify_historical_va_source_policy.sql",
    "223n5_certify_award_precedence.sql",
    "223a_reconcile_current_historical_assistance.sql",
]

output = Path("226c2_existing_accounting_sql_review.txt")

sections = [
    "ETL-226C2 - EXISTING ACCOUNTING SQL REVIEW",
    "READ ONLY - NO SQL EXECUTION OR DATABASE WRITES",
    "=" * 100,
]

missing = []

for name in names:
    path = root / name

    sections.extend([
        "",
        "=" * 100,
        f"FILE: {path.as_posix()}",
        "=" * 100,
    ])

    if not path.is_file():
        missing.append(name)
        sections.append("FILE NOT FOUND")
        continue

    content = path.read_text(
        encoding="utf-8-sig",
        errors="replace"
    )

    for number, line in enumerate(content.splitlines(), 1):
        sections.append(f"{number:04d} | {line}")

output.write_text(
    "\n".join(sections) + "\n",
    encoding="utf-8"
)

print("ETL-226C2", "PASS" if not missing else "INCOMPLETE")
print("Scripts requested:", len(names))
print("Scripts found:", len(names) - len(missing))
print("Missing:", missing)
print("Output:", output)

if missing:
    raise SystemExit(1)
