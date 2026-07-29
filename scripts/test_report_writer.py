from __future__ import annotations

import tempfile
from pathlib import Path

from etl.validation.common.report_writer import ReportWriter


def main() -> None:
    certification = {
        "schema_version": "1.0.0",
        "evidence_package_id": "PROC-B0004-EPS001",
        "dataset": "procurement",
        "batch_id": 4,
        "status": "CERTIFIED",
        "created_utc": "2026-07-29T17:00:00Z",
        "summary": {
            "passed": 2,
            "failed": 0,
            "warnings": 1,
            "total": 3,
        },
        "checks": [
            {
                "code": "PROC-001",
                "name": "Expected row count",
                "category": "completeness",
                "status": "PASS",
                "message": (
                    "The expected row count was observed."
                ),
                "evidence": {
                    "expected_rows": 1250,
                    "observed_rows": 1250,
                },
            },
            {
                "code": "PROC-002",
                "name": "Required identifiers",
                "category": "integrity",
                "status": "PASS",
                "message": (
                    "All required identifiers were present."
                ),
                "evidence": {
                    "missing_identifiers": 0,
                },
            },
            {
                "code": "PROC-003",
                "name": "Optional description coverage",
                "category": "quality",
                "status": "WARNING",
                "message": (
                    "A small number of optional descriptions "
                    "were blank."
                ),
                "evidence": {
                    "blank_descriptions": 3,
                },
            },
        ],
        "statistics": {
            "source_rows": 1250,
            "certified_rows": 1250,
        },
        "versions": {
            "etl_version": "0.5.0-alpha1",
            "certification_version": "ETL-114C.1",
            "evidence_package_version": "EPS-001",
        },
    }

    writer = ReportWriter()
    report = writer.render(certification)

    assert "EPS-001 CERTIFICATION REPORT" in report
    assert "PROC-B0004-EPS001" in report
    assert "Status:              CERTIFIED" in report
    assert "Passed:              2" in report
    assert "Warnings:            1" in report
    assert "[PASS] PROC-001" in report
    assert "[WARNING] PROC-003" in report
    assert "Source Rows: 1250" in report
    assert "End of certification report." in report

    with tempfile.TemporaryDirectory() as temporary_directory:
        report_path = (
            Path(temporary_directory)
            / "certification_report.txt"
        )

        writer.write(
            report_path,
            certification,
        )

        assert report_path.exists()
        assert report_path.is_file()

        report_bytes = report_path.read_bytes()

        assert report_bytes.endswith(b"\n")
        assert b"\r\n" not in report_bytes

        persisted_report = report_path.read_text(
            encoding="utf-8"
        )

        assert persisted_report == report

        print()
        print(f"Report: {report_path}")
        print()
        print(report)
        print("ReportWriter contract test passed.")


if __name__ == "__main__":
    main()