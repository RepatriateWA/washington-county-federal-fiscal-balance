from __future__ import annotations
from typing import Any
from etl.validation.assistance.models import CertificationCheck, CertificationSummary, CheckStatus

REPORT_WIDTH = 76

def format_value(value: Any) -> str:
    return "—" if value is None else str(value)

def print_header(title: str, character: str = "=") -> None:
    print(character * REPORT_WIDTH)
    print(title)
    print(character * REPORT_WIDTH)

def print_check(check: CertificationCheck) -> None:
    status = f"[{check.status.value}]"
    print(
        f"{status:<7} {check.check_code:<11} "
        f"{check.label:.<47} {format_value(check.observed_value)}"
    )
    if check.expected_value is not None and check.status != CheckStatus.PASS:
        print(f"        Expected: {format_value(check.expected_value)}")
    if check.detail:
        print(f"        {check.detail}")

def print_report(summary: CertificationSummary) -> None:
    print_header("ETL-115 — ASSISTANCE BATCH CERTIFICATION REPORT")
    print(f"Load batch ID: {summary.load_batch_id}")
    print()
    sections = []
    for check in summary.checks:
        if check.section not in sections:
            sections.append(check.section)
    for section in sections:
        print_header(section, "-")
        for check in summary.checks:
            if check.section == section:
                print_check(check)
        print()
    print_header("CERTIFICATION SUMMARY")
    print(f"Checks passed .................. {summary.passed_count}")
    print(f"Checks failed .................. {summary.failed_count}")
    print(f"Warnings ....................... {summary.warning_count}")
    print()
    print("OVERALL RESULT: CERTIFIED" if summary.is_certified else "OVERALL RESULT: NOT CERTIFIED")
