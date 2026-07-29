from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from etl.validation.common.certification_builder import (
    CertificationBuilder,
)
from etl.validation.common.evidence_package import EvidencePackage


def main() -> None:
    summary = SimpleNamespace(
        passed=2,
        failed=0,
        warnings=1,
    )

    package = EvidencePackage.from_summary(
        dataset="procurement",
        dataset_code="PROC",
        batch_id=4,
        summary=summary,  # type: ignore[arg-type]
        root_directory=Path("evidence"),
    )

    checks = [
        {
            "code": "PROC-001",
            "name": "Expected row count",
            "category": "completeness",
            "status": "PASS",
            "message": "The expected row count was observed.",
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
            "message": "All required identifiers were present.",
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
    ]

    builder = CertificationBuilder(
        certification_version="ETL-114C.1",
        etl_version="0.5.0-alpha1",
    )

    certification = builder.build(
        package,
        checks=checks,
        statistics={
            "source_rows": 1250,
            "certified_rows": 1250,
        },
    )

    assert certification["schema_version"] == "1.0.0"

    assert (
        certification["evidence_package_id"]
        == "PROC-B0004-EPS001"
    )

    assert certification["dataset"] == "procurement"
    assert certification["batch_id"] == 4
    assert certification["status"] == "CERTIFIED"
    assert certification["created_utc"].endswith("Z")

    result_summary = certification["summary"]

    assert result_summary == {
        "passed": 2,
        "failed": 0,
        "warnings": 1,
        "total": 3,
    }

    assert len(certification["checks"]) == 3

    assert certification["checks"][0]["code"] == "PROC-001"
    assert certification["checks"][0]["status"] == "PASS"

    assert (
        certification["checks"][2]["status"]
        == "WARNING"
    )

    versions = certification["versions"]

    assert versions == {
        "etl_version": "0.5.0-alpha1",
        "certification_version": "ETL-114C.1",
        "evidence_package_version": "EPS-001",
    }

    assert certification["statistics"] == {
        "source_rows": 1250,
        "certified_rows": 1250,
    }

    print()
    print(
        f"EPID:                  "
        f"{certification['evidence_package_id']}"
    )
    print(
        f"Status:                "
        f"{certification['status']}"
    )
    print(
        f"Passed:                "
        f"{result_summary['passed']}"
    )
    print(
        f"Failed:                "
        f"{result_summary['failed']}"
    )
    print(
        f"Warnings:              "
        f"{result_summary['warnings']}"
    )
    print(
        f"Total checks:          "
        f"{result_summary['total']}"
    )
    print(
        f"Certification version: "
        f"{versions['certification_version']}"
    )

    print(
        "\nCertificationBuilder contract test passed."
    )


if __name__ == "__main__":
    main()