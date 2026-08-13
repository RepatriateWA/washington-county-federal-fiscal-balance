"""
EP-VA-001 — Build the VA GDX FY2015-FY2024 Evidence Package.

Creates a reproducible, fail-closed evidence package for the validated
Washington county-level Department of Veterans Affairs Geographic
Distribution of Expenditures (GDX) series.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from etl.common.db import get_connection


PACKAGE_CODE = "EP-VA-001"
DATASET_CODE = "VA_GDX_WA_COUNTY"
DATASET_NAME = "VA Geographic Distribution of Expenditures — Washington County Series"
CERTIFICATION_VERSION = "EP-VA-001.1"
ARCHITECTURE_VERSION = "1.0"

START_YEAR = 2015
END_YEAR = 2024
YEARS = tuple(range(START_YEAR, END_YEAR + 1))

EXPECTED_COUNTIES = 39
EXPECTED_EXPENDITURES = 3237
EXPECTED_METRICS = 702
EXPECTED_VALIDATION_CHECKS = 19

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "evidence"
RAW_GDX_ROOT = REPO_ROOT / "data" / "raw" / "va" / "gdx"
ACQUISITION_MANIFEST = RAW_GDX_ROOT / "acquisition_manifest.json"
SCHEMA_PROFILE = REPO_ROOT / "evidence" / "va" / "gdx" / "schema_profile.json"


@dataclass(frozen=True)
class CertificationCheck:
    code: str
    label: str
    passed: bool
    detail: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Unsupported JSON type: {type(value).__name__}")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=json_default) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Required file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build EP-VA-001 for validated FY2015-FY2024 Washington county VA GDX."
    )
    parser.add_argument(
        "--root-directory",
        type=Path,
        default=DEFAULT_EVIDENCE_ROOT,
        help=f"Evidence root directory. Default: {DEFAULT_EVIDENCE_ROOT}",
    )
    return parser.parse_args()


def add_check(
    checks: list[CertificationCheck],
    code: str,
    label: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append(CertificationCheck(code, label, passed, detail))


def run_validator() -> dict[str, Any]:
    command = [sys.executable, "-m", "scripts.validate_va_gdx"]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout
    if result.stderr:
        output += "\n" + result.stderr

    passed_match = re.search(r"Checks passed\s+\.*\s+(\d+)", output)
    failed_match = re.search(r"Checks failed\s+\.*\s+(\d+)", output)

    return {
        "command": command,
        "return_code": result.returncode,
        "overall_pass": "OVERALL RESULT: PASS" in output,
        "checks_passed": int(passed_match.group(1)) if passed_match else None,
        "checks_failed": int(failed_match.group(1)) if failed_match else None,
        "check_lines": [
            line.strip()
            for line in output.splitlines()
            if line.strip().startswith(("[PASS]", "[FAIL]"))
        ],
        "raw_output": output,
    }


def collect_database_state() -> dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    gdx_load_batch_id,
                    fiscal_year,
                    source_file,
                    source_sha256,
                    schema_regime,
                    methodology_regime,
                    methodology_break,
                    source_county_rows,
                    loaded_expenditure_rows,
                    loaded_metric_rows,
                    rejected_row_count,
                    load_status,
                    load_completed_at
                FROM va.gdx_load_batch
                WHERE fiscal_year BETWEEN 2015 AND 2024
                  AND load_status = 'COMPLETED'
                ORDER BY fiscal_year;
            """)

            batches = []
            for row in cur.fetchall():
                batches.append({
                    "gdx_load_batch_id": int(row[0]),
                    "fiscal_year": int(row[1]),
                    "source_file": str(row[2]),
                    "source_sha256": str(row[3]).upper(),
                    "schema_regime": str(row[4]),
                    "methodology_regime": str(row[5]),
                    "methodology_break": bool(row[6]),
                    "source_county_rows": int(row[7]),
                    "loaded_expenditure_rows": int(row[8]),
                    "loaded_metric_rows": int(row[9]),
                    "rejected_row_count": int(row[10]),
                    "load_status": str(row[11]),
                    "load_completed_at": row[12].isoformat() if row[12] else None,
                })

            cur.execute("""
                SELECT COUNT(*), COUNT(DISTINCT fiscal_year)
                FROM va.gdx_county_expenditure
                WHERE fiscal_year BETWEEN 2015 AND 2024;
            """)
            expenditure_rows, expenditure_years = cur.fetchone()

            cur.execute("""
                SELECT COUNT(*)
                FROM va.gdx_county_metric
                WHERE fiscal_year BETWEEN 2015 AND 2024;
            """)
            metric_rows = int(cur.fetchone()[0])

            cur.execute("""
                SELECT fiscal_year, COUNT(DISTINCT county_id)
                FROM va.gdx_county_expenditure
                WHERE fiscal_year BETWEEN 2015 AND 2024
                GROUP BY fiscal_year
                ORDER BY fiscal_year;
            """)
            county_coverage = {
                int(year): int(counties)
                for year, counties in cur.fetchall()
            }

            cur.execute("""
                SELECT fiscal_year, SUM(va_gdx_expenditure_amount)
                FROM va.v_washington_county_gdx_control_total
                WHERE fiscal_year BETWEEN 2015 AND 2024
                GROUP BY fiscal_year
                ORDER BY fiscal_year;
            """)
            annual_totals = [
                {
                    "fiscal_year": int(year),
                    "va_gdx_expenditure_amount": Decimal(amount),
                }
                for year, amount in cur.fetchall()
            ]

            cur.execute("""
                SELECT COUNT(*)
                FROM va.gdx_county_expenditure AS e
                JOIN va.gdx_expenditure_category AS c
                  ON c.gdx_category_id = e.gdx_category_id
                WHERE e.fiscal_year BETWEEN 2015 AND 2024
                  AND c.aggregation_role = 'COMPONENT'
                  AND (
                      e.source_amount IS NULL
                      OR e.expenditure_amount IS NULL
                  );
            """)
            source_blank_component_rows = int(cur.fetchone()[0])

            return {
                "completed_batches": batches,
                "completed_batch_count": len(batches),
                "expenditure_rows": int(expenditure_rows),
                "expenditure_year_count": int(expenditure_years),
                "metric_rows": metric_rows,
                "county_coverage": county_coverage,
                "annual_control_totals": annual_totals,
                "source_blank_component_rows": source_blank_component_rows,
            }
    finally:
        conn.close()


def acquisition_files_by_year(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        int(record["fiscal_year"]): record
        for record in manifest.get("files", [])
    }


def verify_raw_sources(
    acquisition_manifest: dict[str, Any],
    database_state: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    acquisition = acquisition_files_by_year(acquisition_manifest)
    batches = {
        int(record["fiscal_year"]): record
        for record in database_state["completed_batches"]
    }

    records: list[dict[str, Any]] = []
    errors: list[str] = []

    for year in YEARS:
        source = acquisition.get(year)
        batch = batches.get(year)

        if source is None:
            errors.append(f"FY{year}: absent from acquisition manifest")
            continue
        if batch is None:
            errors.append(f"FY{year}: no completed database batch")
            continue

        raw_path = Path(source["local_path"])
        if not raw_path.is_absolute():
            raw_path = REPO_ROOT / raw_path

        if not raw_path.exists():
            errors.append(f"FY{year}: raw workbook missing: {raw_path}")
            continue

        actual_hash = sha256_file(raw_path)
        manifest_hash = str(source["sha256"]).upper()
        database_hash = str(batch["source_sha256"]).upper()

        if actual_hash != manifest_hash:
            errors.append(f"FY{year}: disk hash differs from acquisition manifest")
        if actual_hash != database_hash:
            errors.append(f"FY{year}: disk hash differs from database load batch")

        records.append({
            "fiscal_year": year,
            "filename": raw_path.name,
            "path": str(raw_path),
            "file_size_bytes": raw_path.stat().st_size,
            "sha256": actual_hash,
            "acquisition_manifest_sha256": manifest_hash,
            "database_load_batch_sha256": database_hash,
            "hashes_reconcile": actual_hash == manifest_hash == database_hash,
            "download_url": source.get("download_url"),
            "source_page": source.get("source_page"),
            "schema_regime": batch["schema_regime"],
            "methodology_regime": batch["methodology_regime"],
            "methodology_break": batch["methodology_break"],
            "gdx_load_batch_id": batch["gdx_load_batch_id"],
        })

    return records, errors


def build_checks(
    validation: dict[str, Any],
    database_state: dict[str, Any],
    acquisition_manifest: dict[str, Any],
    schema_profile: dict[str, Any],
    raw_source_errors: list[str],
) -> list[CertificationCheck]:
    checks: list[CertificationCheck] = []

    add_check(
        checks, "CERT-001", "Production VA validator exits successfully",
        validation["return_code"] == 0,
        f"return_code={validation['return_code']}",
    )
    add_check(
        checks, "CERT-002", "Production VA validator reports overall PASS",
        validation["overall_pass"],
        "OVERALL RESULT: PASS" if validation["overall_pass"] else "PASS not reported",
    )
    add_check(
        checks, "CERT-003", "Expected validation suite passes cleanly",
        (
            validation["checks_passed"] == EXPECTED_VALIDATION_CHECKS
            and validation["checks_failed"] == 0
        ),
        (
            f"passed={validation['checks_passed']}, "
            f"failed={validation['checks_failed']}"
        ),
    )

    completed_years = {
        int(batch["fiscal_year"])
        for batch in database_state["completed_batches"]
    }
    add_check(
        checks, "CERT-004", "Exactly ten completed FY2015-FY2024 load batches exist",
        (
            database_state["completed_batch_count"] == 10
            and completed_years == set(YEARS)
        ),
        f"batches={database_state['completed_batch_count']}, years={sorted(completed_years)}",
    )

    coverage = database_state["county_coverage"]
    coverage_ok = (
        set(coverage) == set(YEARS)
        and all(coverage[year] == EXPECTED_COUNTIES for year in YEARS)
    )
    add_check(
        checks, "CERT-005", "All years contain all 39 Washington counties",
        coverage_ok,
        str(coverage),
    )

    count_ok = (
        database_state["expenditure_rows"] == EXPECTED_EXPENDITURES
        and database_state["metric_rows"] == EXPECTED_METRICS
    )
    add_check(
        checks, "CERT-006", "Database observation counts match certified design",
        count_ok,
        (
            f"expenditures={database_state['expenditure_rows']}, "
            f"metrics={database_state['metric_rows']}"
        ),
    )

    regimes = {
        int(batch["fiscal_year"]): batch["schema_regime"]
        for batch in database_state["completed_batches"]
    }
    regime_ok = (
        all(regimes.get(year) == "LEGACY_STATE_SHEETS" for year in range(2015, 2024))
        and regimes.get(2024) == "REVISED_DIRECT_INDIRECT"
    )
    add_check(
        checks, "CERT-007", "Two-regime schema architecture is preserved",
        regime_ok,
        "FY2015-FY2023=LEGACY_STATE_SHEETS; FY2024=REVISED_DIRECT_INDIRECT",
    )

    manifest_years = set(acquisition_files_by_year(acquisition_manifest))
    add_check(
        checks, "CERT-008", "Acquisition manifest covers FY2015-FY2024",
        manifest_years == set(YEARS),
        f"years={sorted(manifest_years)}",
    )

    add_check(
        checks, "CERT-009", "Raw workbook hashes reconcile across disk, manifest, and database",
        not raw_source_errors,
        "10/10 source workbooks reconcile" if not raw_source_errors else "; ".join(raw_source_errors),
    )

    conclusion = schema_profile.get("conclusion", {})
    profile_ok = (
        conclusion.get("single_legacy_etl_mapping_safe") is True
        and conclusion.get("fy2024_requires_separate_mapping") is True
        and conclusion.get("all_years_have_valid_washington_county_population") is True
    )
    add_check(
        checks, "CERT-010", "Schema profile supports production loader design",
        profile_ok,
        str(conclusion),
    )

    return checks


def write_annual_totals(path: Path, totals: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "fiscal_year",
            "va_gdx_expenditure_amount",
            "geographic_scope",
            "measure",
        ])
        for record in totals:
            year = record["fiscal_year"]
            writer.writerow([
                year,
                format(record["va_gdx_expenditure_amount"], ".2f"),
                "Washington State — sum of 39 county control totals",
                (
                    "Legacy Total Expenditure"
                    if year <= 2023
                    else "Total Direct Expenditure + Total Indirect Expenditure"
                ),
            ])


def status(checks: list[CertificationCheck]) -> str:
    return "CERTIFIED" if all(check.passed for check in checks) else "FAILED"


def write_report(
    path: Path,
    generated_at: str,
    checks: list[CertificationCheck],
    database_state: dict[str, Any],
    validation: dict[str, Any],
) -> None:
    lines = [
        "EP-VA-001 — VA GDX FY2015-FY2024 CERTIFICATION REPORT",
        "=" * 88,
        "",
        f"Generated UTC: {generated_at}",
        f"Dataset: {DATASET_NAME}",
        "Geography: Washington State — 39 counties",
        "Fiscal years: FY2015-FY2024",
        "",
        "CERTIFICATION CHECKS",
        "-" * 88,
    ]

    for check in checks:
        label = "PASS" if check.passed else "FAIL"
        lines.append(f"[{label}] {check.code:<10} {check.label}")
        lines.append(f"       {check.detail}")

    lines.extend([
        "",
        "DATABASE STATISTICS",
        "-" * 88,
        f"Completed load batches ............ {database_state['completed_batch_count']}",
        f"Expenditure observations ......... {database_state['expenditure_rows']:,}",
        f"Metric observations .............. {database_state['metric_rows']:,}",
        f"Source-blank component rows ....... {database_state['source_blank_component_rows']:,}",
        "",
        "WASHINGTON VA GDX ANNUAL CONTROL TOTALS",
        "-" * 88,
    ])

    for record in database_state["annual_control_totals"]:
        lines.append(
            f"FY{record['fiscal_year']} ${record['va_gdx_expenditure_amount']:,.2f}"
        )

    lines.extend([
        "",
        "METHODOLOGY REGIMES",
        "-" * 88,
        "FY2015-FY2023  LEGACY_STATE_SHEETS; source expenditures in $000s.",
        "FY2024         REVISED_DIRECT_INDIRECT; source expenditures in dollars.",
        "",
        "SOURCE-BLANK POLICY",
        "-" * 88,
        "Blank component cells are preserved as NULL rather than silently converted to zero.",
        "All control totals are numeric and component reconciliations pass.",
        "",
        "ANALYTICAL LIMITATION",
        "-" * 88,
        "This certification does NOT declare VA GDX additive to USAspending.",
        "Overlap reconciliation is required before combining the two expenditure domains.",
        "",
        "UNDERLYING VALIDATION",
        "-" * 88,
        f"Validation checks passed .......... {validation['checks_passed']}",
        f"Validation checks failed .......... {validation['checks_failed']}",
        "",
        "=" * 88,
        f"OVERALL RESULT: {status(checks)}",
        "=" * 88,
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


def write_readme(path: Path, generated_at: str) -> None:
    path.write_text(f"""# EP-VA-001 — Washington County VA GDX Evidence Package

**Dataset:** {DATASET_NAME}  
**Coverage:** FY2015–FY2024  
**Geography:** All 39 Washington counties  
**Generated:** {generated_at}

## Certified Scope

This package certifies official-source workbook provenance and SHA-256 identity,
complete FY2015–FY2024 and 39-county coverage, source-unit preservation,
legacy `$000s` normalization to dollars, the FY2024 Direct/Indirect
methodology break, financial reconciliation, and annual Washington GDX
county-control totals.

## Critical Limitation

**VA GDX is not yet certified as additive to the final federal
fiscal-balance ledger.**

Some GDX categories may overlap USAspending-derived federal spending. A
separate overlap/deduplication reconciliation must determine the controlling
source for each expenditure domain before the totals are combined.

## Reproduction

```powershell
python -m scripts.validate_va_gdx
python -m scripts.build_va_gdx_evidence_package
```
""", encoding="utf-8")


def write_methodology(path: Path) -> None:
    path.write_text("""# EP-VA-001 Methodology Note

## Source and Scope
The source domain is the U.S. Department of Veterans Affairs Geographic
Distribution of Expenditures (GDX) series for all 39 Washington counties.

## FY2015–FY2023
These years use the legacy `WA` worksheet structure. Published expenditure
amounts are in thousands of dollars. The normalized database preserves the
high-precision source value and source unit while also storing dollars.

## FY2024
FY2024 uses separate `County Direct Exp` and `County Indirect Exp` tables.
Direct and Indirect classifications remain explicit in the database.

## Source Blanks
Blank FY2024 component cells are preserved as NULL, not silently converted
to zero. Control totals are numeric and component reconciliations pass.

## County Control
FY2015–FY2023 use `Total Expenditure`.
FY2024 uses `Total Direct Expenditure + Total Indirect Expenditure`.

## USAspending Overlap Warning
This package does not establish additivity with USAspending-derived VA
activity. An explicit source-control and deduplication methodology is required
before combining the two domains.
""", encoding="utf-8")


def artifact_manifest(package_directory: Path) -> dict[str, Any]:
    artifacts = []
    for item in sorted(package_directory.rglob("*")):
        if item.is_file() and item.name != "manifest.json":
            artifacts.append({
                "path": item.relative_to(package_directory).as_posix(),
                "size_bytes": item.stat().st_size,
                "sha256": sha256_file(item),
            })
    return {
        "package_code": PACKAGE_CODE,
        "dataset_code": DATASET_CODE,
        "manifest_version": "1.0",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def main() -> None:
    args = parse_arguments()

    package_directory = args.root_directory / "va" / "gdx" / PACKAGE_CODE
    metadata_directory = package_directory / "metadata"
    package_directory.mkdir(parents=True, exist_ok=True)
    metadata_directory.mkdir(parents=True, exist_ok=True)

    print("=" * 88)
    print("EP-VA-001 — BUILD VA GDX EVIDENCE PACKAGE")
    print("=" * 88)
    print(f"Package directory ................. {package_directory}")
    print()

    print("Running production VA validator...")
    validation = run_validator()
    print(f"Validator return code ............. {validation['return_code']}")
    print(f"Validator checks passed ........... {validation['checks_passed']}")
    print(f"Validator checks failed ........... {validation['checks_failed']}")

    database_state = collect_database_state()
    acquisition_manifest = load_json(ACQUISITION_MANIFEST)
    schema_profile = load_json(SCHEMA_PROFILE)

    source_records, source_errors = verify_raw_sources(
        acquisition_manifest,
        database_state,
    )

    checks = build_checks(
        validation,
        database_state,
        acquisition_manifest,
        schema_profile,
        source_errors,
    )

    print()
    print("Certification preflight:")
    print("-" * 88)

    for check in checks:
        label = "PASS" if check.passed else "FAIL"
        print(f"[{label}] {check.code:<10} {check.label}")

    failed = [check for check in checks if not check.passed]
    if failed:
        print()
        print("=" * 88)
        print("EP-VA-001 PUBLICATION REFUSED — CERTIFICATION CHECKS FAILED")
        print("=" * 88)
        for check in failed:
            print(f"{check.code}: {check.detail}")
        raise SystemExit(1)

    generated_at = utc_now()

    certification = {
        "package_code": PACKAGE_CODE,
        "dataset_code": DATASET_CODE,
        "dataset_name": DATASET_NAME,
        "certification_version": CERTIFICATION_VERSION,
        "generated_at_utc": generated_at,
        "fiscal_year_start": START_YEAR,
        "fiscal_year_end": END_YEAR,
        "geographic_scope": "Washington State — 39 counties",
        "status": status(checks),
        "certified_for": [
            "source provenance",
            "raw workbook identity",
            "county coverage",
            "schema-regime preservation",
            "source-unit preservation",
            "normalization to dollars",
            "component-to-control reconciliation",
            "annual Washington GDX control totals",
        ],
        "not_certified_for": [
            "additivity with USAspending-derived VA expenditures",
            "final fiscal-balance inclusion before overlap reconciliation",
        ],
        "checks": [asdict(check) for check in checks],
        "validator": {
            "checks_passed": validation["checks_passed"],
            "checks_failed": validation["checks_failed"],
            "overall_pass": validation["overall_pass"],
        },
        "database_statistics": {
            "completed_batches": database_state["completed_batch_count"],
            "expenditure_rows": database_state["expenditure_rows"],
            "metric_rows": database_state["metric_rows"],
            "source_blank_component_rows": database_state["source_blank_component_rows"],
        },
    }

    validation_results = {
        "package_code": PACKAGE_CODE,
        "captured_at_utc": generated_at,
        "validator_module": "scripts.validate_va_gdx",
        **validation,
    }

    source_manifest = {
        "package_code": PACKAGE_CODE,
        "source_domain": "U.S. Department of Veterans Affairs Geographic Distribution of Expenditures",
        "source_page": acquisition_manifest.get("source_page"),
        "fiscal_year_start": START_YEAR,
        "fiscal_year_end": END_YEAR,
        "source_file_count": len(source_records),
        "files": source_records,
    }

    metadata = {
        "package_code": PACKAGE_CODE,
        "dataset_code": DATASET_CODE,
        "dataset_name": DATASET_NAME,
        "certification_version": CERTIFICATION_VERSION,
        "architecture_version": ARCHITECTURE_VERSION,
        "generated_at_utc": generated_at,
        "repository_root": str(REPO_ROOT),
        "source_root": str(RAW_GDX_ROOT),
        "database_schema": "va",
        "primary_tables": [
            "va.gdx_load_batch",
            "va.gdx_expenditure_category",
            "va.gdx_county_expenditure",
            "va.gdx_county_metric",
        ],
        "control_view": "va.v_washington_county_gdx_control_total",
        "schema_regimes": {
            "FY2015-FY2023": "LEGACY_STATE_SHEETS",
            "FY2024": "REVISED_DIRECT_INDIRECT",
        },
        "methodology_break_fiscal_year": 2024,
    }

    write_json(package_directory / "certification.json", certification)
    write_json(package_directory / "validation_results.json", validation_results)
    write_json(package_directory / "source_manifest.json", source_manifest)
    write_json(package_directory / "schema_profile.json", schema_profile)
    write_json(metadata_directory / "metadata.json", metadata)

    write_annual_totals(
        package_directory / "annual_control_totals.csv",
        database_state["annual_control_totals"],
    )
    write_report(
        package_directory / "certification_report.txt",
        generated_at,
        checks,
        database_state,
        validation,
    )
    write_readme(package_directory / "README.md", generated_at)
    write_methodology(package_directory / "methodology_note.md")

    manifest = artifact_manifest(package_directory)
    manifest["generated_at_utc"] = generated_at
    manifest["certification_status"] = certification["status"]
    write_json(package_directory / "manifest.json", manifest)

    print()
    print("=" * 88)
    print("EP-VA-001 EVIDENCE PACKAGE PUBLISHED")
    print("=" * 88)
    print(f"Certification status .............. {certification['status']}")
    print(f"Published artifacts ............... {manifest['artifact_count'] + 1}")
    print(f"Source workbooks reconciled ....... {len(source_records)}/10")
    print(f"Package directory ................. {package_directory}")
    print()
    print("Important: certification does not declare VA GDX additive to USAspending.")
    print("=" * 88)


if __name__ == "__main__":
    main()