"""
Console reporting for procurement batch certification.
"""

from __future__ import annotations

from typing import Any

from etl.validation.procurement.models import (
    CertificationCheck,
    CertificationSummary,
    CheckStatus,
)


REPORT_WIDTH = 76


def format_value(value: Any) -> str:
    if value is None:
        return "—"

    return str(value)


def print_header(
    title: str,
    character: str = "=",
) -> None:
    print(character * REPORT_WIDTH)
    print(title)
    print(character * REPORT_WIDTH)


def print_check(check: CertificationCheck) -> None:
    status = f"[{check.status.value}]"
    label_width = 47

    print(
        f"{status:<7} "
        f"{check.check_code:<11} "
        f"{check.label:.<{label_width}} "
        f"{format_value(check.observed_value)}"
    )

    if (
        check.expected_value is not None
        and check.status != CheckStatus.PASS
    ):
        print(
            "        Expected: "
            f"{format_value(check.expected_value)}"
        )

    if check.detail:
        print(f"        {check.detail}")


def print_report(
    summary: CertificationSummary,
) -> None:
    print_header(
        "ETL-114 — PROCUREMENT BATCH CERTIFICATION REPORT"
    )

    print(f"Load batch ID: {summary.load_batch_id}")
    print()

    sections: list[str] = []

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

    print(
        "Checks passed .................. "
        f"{summary.passed_count}"
    )
    print(
        "Checks failed .................. "
        f"{summary.failed_count}"
    )
    print(
        "Warnings ....................... "
        f"{summary.warning_count}"
    )
    print()

    if summary.is_certified:
        print("OVERALL RESULT: CERTIFIED")
    else:
        print("OVERALL RESULT: NOT CERTIFIED")