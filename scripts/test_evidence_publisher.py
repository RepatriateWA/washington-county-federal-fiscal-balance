from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from etl.validation.common.certification_builder import (
    CertificationBuilder,
)
from etl.validation.common.evidence_package import EvidencePackage
from etl.validation.common.evidence_publisher import EvidencePublisher
from etl.validation.common.evidence_writer import EvidenceWriter
from etl.validation.common.json_writer import JsonWriter
from etl.validation.common.manifest_builder import ManifestBuilder
from etl.validation.common.metadata_builder import MetadataBuilder
from etl.validation.common.report_writer import ReportWriter


def main() -> None:
    summary = SimpleNamespace(
        passed=2,
        failed=0,
        warnings=1,
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

    statistics = {
        "source_rows": 1250,
        "certified_rows": 1250,
    }

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)

        package = EvidencePackage.from_summary(
            dataset="procurement",
            dataset_code="PROC",
            batch_id=4,
            summary=summary,  # type: ignore[arg-type]
            root_directory=temporary_root / "evidence",
        )

        publisher = EvidencePublisher(
            evidence_writer=EvidenceWriter(),
            manifest_builder=ManifestBuilder(),
            certification_builder=CertificationBuilder(
                certification_version="ETL-114C.1",
                etl_version="0.5.0-alpha1",
            ),
            metadata_builder=MetadataBuilder(
                certification_version="ETL-114C.1",
                etl_version="0.5.0-alpha1",
                architecture_version="1.0",
                repository_root=Path.cwd(),
                database_name="wcffbp",
            ),
            json_writer=JsonWriter(),
            report_writer=ReportWriter(),
        )

        package_directory = publisher.publish(
            package,
            checks=checks,
            statistics=statistics,
        )

        manifest_path = package_directory / "manifest.json"

        certification_path = (
            package_directory / "certification.json"
        )

        report_path = (
            package_directory / "certification_report.txt"
        )

        metadata_path = (
            package_directory
            / "metadata"
            / "metadata.json"
        )

        report = report_path.read_text(
           encoding="utf-8"
        )

        
        assert package_directory.exists()
        assert package_directory.is_dir()

        assert manifest_path.exists()
        assert manifest_path.is_file()

        assert certification_path.exists()
        assert certification_path.is_file()

        assert metadata_path.exists()
        assert metadata_path.is_file()

        assert report_path.exists()
        assert report_path.is_file()

        assert "EPS-001 CERTIFICATION REPORT" in report

        assert (
            f"Evidence Package ID: "
            f"{package.evidence_package_id}"
            in report
        )

        assert "Status:              CERTIFIED" in report
        assert "Passed:              2" in report
        assert "Failed:              0" in report
        assert "Warnings:            1" in report
        assert "[PASS] PROC-001" in report
        assert "[WARNING] PROC-003" in report
        assert "Source Rows: 1250" in report

        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

        certification = json.loads(
            certification_path.read_text(encoding="utf-8")
        )

        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )

        assert (
            manifest["evidence_package_id"]
            == package.evidence_package_id
        )

        assert manifest["status"] == "CERTIFIED"
        assert manifest["artifacts"] == []

        assert (
            certification["evidence_package_id"]
            == package.evidence_package_id
        )

        assert certification["status"] == "CERTIFIED"

        assert certification["summary"] == {
            "passed": 2,
            "failed": 0,
            "warnings": 1,
            "total": 3,
        }

        assert len(certification["checks"]) == 3

        assert certification["statistics"] == {
            "source_rows": 1250,
            "certified_rows": 1250,
        }

        assert (
            metadata["evidence_package_id"]
            == package.evidence_package_id
        )

        assert metadata["dataset"] == "procurement"
        assert metadata["batch_id"] == 4

        assert (
            metadata["versions"]["certification_version"]
            == "ETL-114C.1"
        )

        assert metadata["runtime"]["database"] == "wcffbp"

        assert (
            metadata["source"]["repository"]
            == Path.cwd().name
        )

        artifact_paths = [
            manifest_path,
            certification_path,
            metadata_path,
            report_path,
        ]

        for path in artifact_paths:
            content = path.read_bytes()

            assert content.endswith(b"\n")
            assert b"\r\n" not in content
        
        expected_directories = [
            package_directory / "metadata",
            package_directory / "reconciliation",
            package_directory / "exceptions",
            package_directory / "logs",
        ]

        for directory in expected_directories:
            assert directory.exists()
            assert directory.is_dir()

        print()
        print(f"Report:            {report_path}")
        print(f"Package directory: {package_directory}")
        print(f"Manifest:          {manifest_path}")
        print(f"Certification:     {certification_path}")
        print(f"Metadata:          {metadata_path}")
        print(f"Status:            {certification['status']}")
        print(
            f"Checks:            "
            f"{certification['summary']['total']}"
        )
        print(
            f"EPID:              "
            f"{certification['evidence_package_id']}"
        )
        print(
            f"Git commit:        "
            f"{metadata['source']['git_commit']}"
        )
        print(
            f"Git dirty:         "
            f"{metadata['source']['git_dirty']}"
        )

        print(
            "\nEvidencePublisher integration test passed."
        )


if __name__ == "__main__":
    main()