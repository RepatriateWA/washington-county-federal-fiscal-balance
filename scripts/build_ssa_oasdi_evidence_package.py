"""Build EP-SSA-OASDI-001 evidence package for Washington county OASDI data."""
from __future__ import annotations

import argparse, csv, hashlib, json, re, subprocess, sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from etl.common.db import get_connection

PACKAGE_CODE = "EP-SSA-OASDI-001"
DATASET_CODE = "SSA_OASDI_WA_COUNTY"
DATASET_NAME = "SSA OASDI Beneficiaries and Benefit Amounts — Washington County Series"
YEARS = tuple(range(2015, 2025))
EXPECTED_VALIDATION_CHECKS = 17
EXPECTED_ROWS = 3510
EXPECTED_ROWS_PER_YEAR = 351
EXPECTED_COUNTIES = 39
EXPECTED_BENEFIT_TYPES = 9
EXPECTED_TOTAL_CONTROLS = 390
MONTHLY_ROUNDING_TOLERANCE_THOUSANDS = Decimal("5")
ANNUAL_ROUNDING_TOLERANCE_THOUSANDS = Decimal("60")
REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = REPO_ROOT / "data" / "raw" / "ssa" / "oasdi"
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "evidence"
SSA_SOURCE_SERIES_URL = "https://www.ssa.gov/policy/docs/statcomps/oasdi_sc/"

@dataclass(frozen=True)
class CertificationCheck:
    code: str
    label: str
    passed: bool
    detail: str

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def json_default(value: Any):
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, Path): return str(value)
    raise TypeError(type(value).__name__)

def write_json(path: Path, value: Any):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")

def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()

def parse_args():
    p = argparse.ArgumentParser(description="Build EP-SSA-OASDI-001 evidence package.")
    p.add_argument("--root-directory", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    return p.parse_args()

def add_check(checks, code, label, passed, detail):
    checks.append(CertificationCheck(code, label, passed, detail))

def run_validator():
    command = [sys.executable, "-m", "scripts.validate_ssa_oasdi"]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    output = result.stdout + (("\n" + result.stderr) if result.stderr else "")
    pm = re.search(r"Checks passed\s+\.*\s+(\d+)", output)
    fm = re.search(r"Checks failed\s+\.*\s+(\d+)", output)
    return {
        "command": command,
        "return_code": result.returncode,
        "overall_pass": "OVERALL RESULT: PASS" in output,
        "checks_passed": int(pm.group(1)) if pm else None,
        "checks_failed": int(fm.group(1)) if fm else None,
        "check_lines": [x.strip() for x in output.splitlines() if x.strip().startswith(("[PASS]", "[FAIL]"))],
        "raw_output": output,
    }

def discover_source_files():
    records, errors = [], []
    for year in YEARS:
        year_dir = RAW_ROOT / str(year)
        candidates = [year_dir / f"ssa_oasdi_wa_{year}.xlsx", year_dir / f"ssa_oasdi_wa_{year}.xls"]
        existing = [p for p in candidates if p.exists()]
        if len(existing) != 1:
            errors.append(f"{year}: expected exactly one source workbook; found {len(existing)}")
            continue
        p = existing[0]
        records.append({
            "report_year": year,
            "filename": p.name,
            "path": str(p),
            "relative_path": str(p.relative_to(REPO_ROOT)),
            "file_size_bytes": p.stat().st_size,
            "sha256": sha256_file(p),
            "source_series_url": SSA_SOURCE_SERIES_URL,
            "file_identity_note": "SHA-256 captured at certification time.",
        })
    return records, errors

def collect_database_state():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT report_year, COUNT(*), COUNT(DISTINCT county_id), COUNT(DISTINCT ssa_benefit_type_id)
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024 AND agency_code='SSA'
                GROUP BY report_year ORDER BY report_year;
            """)
            coverage = [
                {"report_year": int(y), "rows": int(r), "counties": int(c), "benefit_types": int(t)}
                for y, r, c, t in cur.fetchall()
            ]
            cur.execute("""SELECT COUNT(*) FROM ssa.benefit_payments WHERE report_year BETWEEN 2015 AND 2024 AND agency_code='SSA';""")
            total_rows = int(cur.fetchone()[0])
            cur.execute("""SELECT COUNT(*) FROM ssa.benefit_payments WHERE report_year BETWEEN 2015 AND 2024 AND agency_code='SSA' AND UPPER(TRIM(benefit_type))='TOTAL';""")
            total_controls = int(cur.fetchone()[0])
            cur.execute("""
                SELECT report_year, SUM(beneficiary_count), SUM(monthly_benefits_thousands), SUM(annual_benefits_thousands)
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024 AND agency_code='SSA' AND UPPER(TRIM(benefit_type))='TOTAL'
                GROUP BY report_year ORDER BY report_year;
            """)
            annual_controls = [
                {
                    "report_year": int(y),
                    "beneficiaries": int(b),
                    "december_benefits_dollars": Decimal(m) * Decimal("1000"),
                    "annualized_benefits_dollars": Decimal(a) * Decimal("1000"),
                }
                for y, b, m, a in cur.fetchall()
            ]
            cur.execute("""
                SELECT report_year, MAX(ABS(total_monthly-component_monthly))
                FROM (
                    SELECT report_year, county_id,
                           MAX(monthly_benefits_thousands) FILTER (WHERE UPPER(TRIM(benefit_type))='TOTAL') AS total_monthly,
                           SUM(monthly_benefits_thousands) FILTER (WHERE UPPER(TRIM(benefit_type))<>'TOTAL') AS component_monthly
                    FROM ssa.benefit_payments
                    WHERE report_year BETWEEN 2015 AND 2024 AND agency_code='SSA'
                    GROUP BY report_year, county_id
                ) x
                GROUP BY report_year ORDER BY report_year;
            """)
            rounding_by_year = [
                {"report_year": int(y), "max_abs_monthly_difference_thousands": Decimal(v)}
                for y, v in cur.fetchall()
            ]
            cur.execute("""
                WITH controls AS (
                    SELECT report_year, SUM(annual_benefits_thousands)*1000 AS control_dollars
                    FROM ssa.benefit_payments
                    WHERE report_year BETWEEN 2015 AND 2024 AND agency_code='SSA' AND UPPER(TRIM(benefit_type))='TOTAL'
                    GROUP BY report_year
                ), reporting AS (
                    SELECT report_year, SUM(annualized_benefits_dollars) AS reporting_dollars
                    FROM reporting.v_washington_ssa_summary
                    WHERE report_year BETWEEN 2015 AND 2024
                    GROUP BY report_year
                )
                SELECT c.report_year, c.control_dollars, r.reporting_dollars,
                       r.reporting_dollars-c.control_dollars
                FROM controls c JOIN reporting r USING(report_year)
                ORDER BY c.report_year;
            """)
            reporting_reconciliation = [
                {
                    "report_year": int(y),
                    "published_total_control_dollars": Decimal(c),
                    "component_reporting_dollars": Decimal(r),
                    "difference_dollars": Decimal(d),
                }
                for y, c, r, d in cur.fetchall()
            ]
            cur.execute("""
                SELECT ssa_benefit_type_id, benefit_type, COUNT(*)
                FROM ssa.benefit_payments
                WHERE report_year BETWEEN 2015 AND 2024 AND agency_code='SSA'
                GROUP BY ssa_benefit_type_id, benefit_type
                ORDER BY ssa_benefit_type_id;
            """)
            benefit_types = [
                {"ssa_benefit_type_id": int(i), "benefit_type": str(n), "rows": int(r)}
                for i, n, r in cur.fetchall()
            ]
            return {
                "coverage": coverage,
                "total_rows": total_rows,
                "total_controls": total_controls,
                "annual_controls": annual_controls,
                "rounding_by_year": rounding_by_year,
                "reporting_reconciliation": reporting_reconciliation,
                "benefit_types": benefit_types,
            }
    finally:
        conn.close()

def build_checks(validator, db, source_records, source_errors):
    checks = []
    add_check(checks, "CERT-001", "Production SSA validator exits successfully", validator["return_code"] == 0, f"return_code={validator['return_code']}")
    add_check(checks, "CERT-002", "Production SSA validator reports overall PASS", validator["overall_pass"], "OVERALL RESULT: PASS" if validator["overall_pass"] else "PASS not reported")
    add_check(checks, "CERT-003", "Dedicated validation suite passes all 17 checks", validator["checks_passed"] == EXPECTED_VALIDATION_CHECKS and validator["checks_failed"] == 0, f"passed={validator['checks_passed']}, failed={validator['checks_failed']}")
    coverage = {r["report_year"]: r for r in db["coverage"]}
    add_check(checks, "CERT-004", "Database covers report years 2015-2024", set(coverage) == set(YEARS), f"years={sorted(coverage)}")
    pop_ok = db["total_rows"] == EXPECTED_ROWS and all(coverage.get(y, {}).get("rows") == EXPECTED_ROWS_PER_YEAR for y in YEARS)
    add_check(checks, "CERT-005", "Observation population matches certified design", pop_ok, f"total={db['total_rows']:,}; expected={EXPECTED_ROWS:,}")
    cov_ok = all(coverage.get(y, {}).get("counties") == EXPECTED_COUNTIES and coverage.get(y, {}).get("benefit_types") == EXPECTED_BENEFIT_TYPES for y in YEARS)
    add_check(checks, "CERT-006", "Every year contains 39 counties and 9 benefit types", cov_ok, "10/10 years" if cov_ok else "coverage exception")
    add_check(checks, "CERT-007", "Published TOTAL control population is complete", db["total_controls"] == EXPECTED_TOTAL_CONTROLS, f"actual={db['total_controls']}; expected={EXPECTED_TOTAL_CONTROLS}")
    src_ok = not source_errors and len(source_records) == 10
    add_check(checks, "CERT-008", "Exactly one raw source workbook exists for every year", src_ok, "10/10 source workbooks hashed" if src_ok else "; ".join(source_errors))
    annual_ok = len(db["annual_controls"]) == 10 and {r["report_year"] for r in db["annual_controls"]} == set(YEARS)
    add_check(checks, "CERT-009", "Annual Washington published TOTAL controls are complete", annual_ok, "10/10 years" if annual_ok else "incomplete")
    observed = max(r["max_abs_monthly_difference_thousands"] for r in db["rounding_by_year"])
    add_check(checks, "CERT-010", "Observed source rounding remains inside documented bound", observed <= MONTHLY_ROUNDING_TOLERANCE_THOUSANDS, f"observed_max=${observed*1000:,.0f}; bound=±${MONTHLY_ROUNDING_TOLERANCE_THOUSANDS*1000:,.0f}")
    return checks

def status(checks):
    return "CERTIFIED" if all(c.passed for c in checks) else "FAILED"

def write_annual_controls(path, controls):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["report_year", "beneficiaries", "december_benefits_dollars", "annualized_benefits_dollars", "measure_note"])
        for r in controls:
            w.writerow([r["report_year"], r["beneficiaries"], format(r["december_benefits_dollars"], ".2f"), format(r["annualized_benefits_dollars"], ".2f"), "Annualized value = December monthly benefit amount x 12; not observed FFY cash outlay."])

def write_methodology(path):
    path.write_text("""# EP-SSA-OASDI-001 Methodology Note

## Source and Scope
The dataset is the Social Security Administration county-level OASDI beneficiary and benefit-amount series for Washington State, report years 2015 through 2024.

## Published TOTAL Is the Authoritative County Monetary Control
SSA monetary values are published in thousands of dollars. Benefit-type amounts and TOTAL amounts are independently rounded by SSA. Therefore, component monetary sums are expected to differ slightly from the separately published TOTAL.

For certification purposes, the published TOTAL is retained as the authoritative county control value. Component-to-TOTAL reconciliation is evaluated using a documented tolerance derived from the maximum expected accumulation of source rounding.

The validator uses a conservative monthly county tolerance of +/- $5,000. The annualized tolerance is +/- $60,000 because annualized values are the monthly amount multiplied by 12.

## Beneficiary Counts
Published TOTAL beneficiary counts reconcile exactly to the sum of the eight component benefit categories for every county/year observation.

## Annualization Convention
The normalized annualized measure is:

    annualized benefit amount = December monthly benefit amount x 12

This is an annualized December run-rate. It is not a direct observation of benefits actually paid during the corresponding federal fiscal year.

## Balance-of-Payments Limitation
This package certifies faithful acquisition, normalization, structure, reference integrity, reconciliation, and reporting of the SSA OASDI county series. It does NOT, by itself, certify the December-x-12 amount as the final ledger measure for federal fiscal-year balance-of-payments accounting.

## Program Mapping
The eight component benefit types map to federal program categories. The published TOTAL is intentionally not assigned to one federal program because it combines multiple OASDI program categories.
""", encoding="utf-8")

def write_readme(path, generated_at):
    path.write_text(f"""# EP-SSA-OASDI-001 — Washington County SSA OASDI Evidence Package

**Dataset:** {DATASET_NAME}  
**Coverage:** Report years 2015-2024  
**Geography:** All 39 Washington counties  
**Generated:** {generated_at}

## Certification Scope
This package certifies 2015-2024 coverage, 3,510 normalized observations, 39 counties per year, 9 benefit types per year, 390 published county/year TOTAL controls, reference/program mapping integrity, December x 12 annualization integrity, documented SSA source-rounding treatment, annual Washington control totals, and SHA-256 identity of the ten local raw workbooks.

## Important Accounting Limitation
The annualized amount is the published December monthly benefit amount multiplied by 12. It is an annualized run-rate, not observed federal-fiscal-year cash outlay.

## Reproduction
```powershell
python -m scripts.validate_ssa_oasdi
python -m scripts.build_ssa_oasdi_evidence_package
```
""", encoding="utf-8")

def write_report(path, generated_at, checks, validator, db):
    lines = ["EP-SSA-OASDI-001 — CERTIFICATION REPORT", "="*96, "", f"Generated UTC: {generated_at}", f"Dataset: {DATASET_NAME}", "Report years: 2015-2024", "Geography: Washington State — 39 counties", "", "CERTIFICATION CHECKS", "-"*96]
    for c in checks:
        lines += [f"[{'PASS' if c.passed else 'FAIL'}] {c.code:<10} {c.label}", f"       {c.detail}"]
    lines += ["", "DATABASE STATISTICS", "-"*96, f"Normalized observations ........... {db['total_rows']:,}", f"Published TOTAL controls .......... {db['total_controls']:,}", "", "WASHINGTON ANNUAL PUBLISHED TOTAL CONTROLS", "-"*96]
    for r in db["annual_controls"]:
        lines.append(f"{r['report_year']}  beneficiaries={r['beneficiaries']:,}  December=${r['december_benefits_dollars']:,.2f}  annualized=${r['annualized_benefits_dollars']:,.2f}")
    lines += ["", "MEASURE NOTE", "-"*96, "Annualized amount = December monthly benefit amount x 12; not observed FFY cash outlay.", "", "ROUNDING NOTE", "-"*96, "SSA monetary values are published in $000s. Component and TOTAL amounts are independently rounded.", "Published TOTAL is the authoritative county monetary control. Validator tolerance: +/- $5,000 monthly, +/- $60,000 annualized.", "", "UNDERLYING VALIDATOR", "-"*96, f"Checks passed ..................... {validator['checks_passed']}", f"Checks failed ..................... {validator['checks_failed']}", "", "="*96, f"OVERALL RESULT: {status(checks)}", "="*96, ""]
    path.write_text("\n".join(lines), encoding="utf-8")

def build_manifest(package_dir):
    artifacts = []
    for p in sorted(package_dir.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            artifacts.append({"path": p.relative_to(package_dir).as_posix(), "size_bytes": p.stat().st_size, "sha256": sha256_file(p)})
    return {"package_code": PACKAGE_CODE, "dataset_code": DATASET_CODE, "manifest_version": "1.0", "artifact_count": len(artifacts), "artifacts": artifacts}

def main():
    args = parse_args()
    package_dir = args.root_directory / "ssa" / "oasdi" / PACKAGE_CODE
    metadata_dir = package_dir / "metadata"
    package_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    print("="*96)
    print("EP-SSA-OASDI-001 — BUILD SSA OASDI EVIDENCE PACKAGE")
    print("="*96)
    print(f"\nPackage directory ................. {package_dir}\n")

    print("Running dedicated SSA OASDI validator...")
    validator = run_validator()
    print(f"Validator return code ............. {validator['return_code']}")
    print(f"Validator checks passed ........... {validator['checks_passed']}")
    print(f"Validator checks failed ........... {validator['checks_failed']}")

    db = collect_database_state()
    source_records, source_errors = discover_source_files()
    checks = build_checks(validator, db, source_records, source_errors)

    print("\nCertification preflight:")
    print("-"*96)
    for c in checks:
        print(f"[{'PASS' if c.passed else 'FAIL'}] {c.code:<10} {c.label}")

    failed = [c for c in checks if not c.passed]
    if failed:
        print("\n" + "="*96)
        print("EP-SSA-OASDI-001 PUBLICATION REFUSED — CERTIFICATION CHECKS FAILED")
        print("="*96)
        for c in failed:
            print(f"{c.code}: {c.detail}")
        raise SystemExit(1)

    generated_at = utc_now()
    certification = {
        "package_code": PACKAGE_CODE,
        "dataset_code": DATASET_CODE,
        "dataset_name": DATASET_NAME,
        "generated_at_utc": generated_at,
        "report_year_start": 2015,
        "report_year_end": 2024,
        "geographic_scope": "Washington State — 39 counties",
        "status": status(checks),
        "certified_for": ["source-file identity at certification time", "county coverage", "benefit-type coverage", "database population", "reference integrity", "program mapping integrity", "December x 12 annualization integrity", "published TOTAL control integrity", "documented source-rounding reconciliation", "annual Washington control totals"],
        "not_certified_for": ["interpretation of December x 12 as observed FFY cash outlay", "final ledger measure selection for FFY balance-of-payments accounting"],
        "checks": [asdict(c) for c in checks],
        "validator": {"checks_passed": validator["checks_passed"], "checks_failed": validator["checks_failed"], "overall_pass": validator["overall_pass"]},
        "database_statistics": {"observations": db["total_rows"], "published_total_controls": db["total_controls"]},
    }
    validation_results = {"package_code": PACKAGE_CODE, "captured_at_utc": generated_at, "validator_module": "scripts.validate_ssa_oasdi", **validator}
    source_manifest = {"package_code": PACKAGE_CODE, "source_agency": "Social Security Administration", "source_series": "OASDI Beneficiaries by State and County", "source_series_url": SSA_SOURCE_SERIES_URL, "report_year_start": 2015, "report_year_end": 2024, "source_file_count": len(source_records), "provenance_note": "Raw source workbook SHA-256 hashes were captured at certification time. This package does not claim that a prior acquisition-time hash manifest existed.", "files": source_records}
    rounding = {"package_code": PACKAGE_CODE, "source_unit": "USD_THOUSANDS", "published_total_is_authoritative_control": True, "monthly_county_tolerance_thousands": MONTHLY_ROUNDING_TOLERANCE_THOUSANDS, "annualized_county_tolerance_thousands": ANNUAL_ROUNDING_TOLERANCE_THOUSANDS, "county_maximum_absolute_difference_by_year": db["rounding_by_year"], "state_reporting_vs_published_total": db["reporting_reconciliation"]}
    metadata = {"package_code": PACKAGE_CODE, "dataset_code": DATASET_CODE, "dataset_name": DATASET_NAME, "generated_at_utc": generated_at, "repository_root": str(REPO_ROOT), "raw_source_root": str(RAW_ROOT), "database_table": "ssa.benefit_payments", "benefit_type_reference": "reference.ssa_benefit_type", "federal_program_reference": "reference.federal_program", "reporting_view": "reporting.v_washington_ssa_summary", "annualization_rule": "annual_benefits_thousands = monthly_benefits_thousands * 12", "authoritative_monetary_control": "published county benefit_type='Total'", "benefit_types": db["benefit_types"]}

    write_json(package_dir / "certification.json", certification)
    write_json(package_dir / "validation_results.json", validation_results)
    write_json(package_dir / "source_manifest.json", source_manifest)
    write_json(package_dir / "rounding_reconciliation.json", rounding)
    write_json(metadata_dir / "metadata.json", metadata)
    write_annual_controls(package_dir / "annual_control_totals.csv", db["annual_controls"])
    write_methodology(package_dir / "methodology_note.md")
    write_readme(package_dir / "README.md", generated_at)
    write_report(package_dir / "certification_report.txt", generated_at, checks, validator, db)
    manifest = build_manifest(package_dir)
    manifest["generated_at_utc"] = generated_at
    manifest["certification_status"] = certification["status"]
    write_json(package_dir / "manifest.json", manifest)

    print("\n" + "="*96)
    print("EP-SSA-OASDI-001 EVIDENCE PACKAGE PUBLISHED")
    print("="*96)
    print(f"Certification status .............. {certification['status']}")
    print(f"Published artifacts ............... {manifest['artifact_count'] + 1}")
    print(f"Source workbooks hashed ........... {len(source_records)}/10")
    print(f"Package directory ................. {package_dir}")
    print("\nImportant: certification does not treat December x 12 as observed FFY cash outlay.")
    print("="*96)

if __name__ == "__main__":
    main()