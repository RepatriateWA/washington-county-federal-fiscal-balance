from __future__ import annotations

from copy import deepcopy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from etl.validation.common import publication_validator
from etl.validation.common.certification_builder import (
    CertificationBuilder,
)
from etl.validation.common.evidence_package import EvidencePackage
from etl.validation.common.evidence_publisher import EvidencePublisher
from etl.validation.common.evidence_writer import EvidenceWriter
from etl.validation.common.json_writer import JsonWriter
from etl.validation.common.manifest_builder import ManifestBuilder
from etl.validation.common.metadata_builder import MetadataBuilder
from etl.validation.common.publication_validator import (
    PublicationValidator,
)
from etl.validation.common.report_writer import ReportWriter


def main() -> None:
    """
    Run the EPS-001 end-to-end acceptance test.

    Burn 14A verifies the valid publication path:

    1. Construct an EvidencePackage.
    2. Publish the package.
    3. Confirm the expected filesystem structure.
    4. Reload all JSON documents from disk.
    5. Independently validate the published documents.
    6. Verify cross-document consistency.
    """

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

    schema_directory = (
        Path.cwd()
        / "schemas"
        / "evidence"
    )

    publication_validator = PublicationValidator(
        schema_directory
    )

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
            publication_validator=publication_validator,
        )

        package_directory = publisher.publish(
            package,
            checks=checks,
            statistics=statistics,
        )

        manifest_path = (
            package_directory
            / "manifest.json"
        )

        certification_path = (
            package_directory
            / "certification.json"
        )

        metadata_path = (
            package_directory
            / "metadata"
            / "metadata.json"
        )

        report_path = (
            package_directory
            / "certification_report.txt"
        )

        expected_directories = [
            package_directory,
            package_directory / "metadata",
            package_directory / "reconciliation",
            package_directory / "exceptions",
            package_directory / "logs",
        ]

        for directory in expected_directories:
            assert directory.exists(), (
                f"Expected directory does not exist: "
                f"{directory}"
            )

            assert directory.is_dir(), (
                f"Expected path is not a directory: "
                f"{directory}"
            )

        expected_files = [
            manifest_path,
            certification_path,
            metadata_path,
            report_path,
        ]

        for path in expected_files:
            assert path.exists(), (
                f"Expected publication artifact does not exist: "
                f"{path}"
            )

            assert path.is_file(), (
                f"Expected publication artifact is not a file: "
                f"{path}"
            )

        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        certification = json.loads(
            certification_path.read_text(
                encoding="utf-8"
            )
        )

        metadata = json.loads(
            metadata_path.read_text(
                encoding="utf-8"
            )
        )

        report = report_path.read_text(
            encoding="utf-8"
        )

        validation_result = publication_validator.validate(
            manifest=manifest,
            certification=certification,
            metadata=metadata,
        )

        assert validation_result.valid, (
            "Published Evidence Package documents failed "
            "independent schema validation."
        )

        assert validation_result.manifest.valid, (
            "Published manifest.json failed validation."
        )

        assert validation_result.certification.valid, (
            "Published certification.json failed validation."
        )

        assert validation_result.metadata.valid, (
            "Published metadata.json failed validation."
        )
        #
# Burn 14B
# Verify that an invalid manifest is rejected.
#

        invalid_manifest = deepcopy(manifest)

        del invalid_manifest["schema_version"]

        invalid_result = publication_validator.validate(
            manifest=invalid_manifest,
            certification=certification,
            metadata=metadata,
        )

        assert not invalid_result.valid

        assert not invalid_result.manifest.valid

        assert invalid_result.certification.valid

        assert invalid_result.metadata.valid

        assert len(
            invalid_result.manifest.errors
        ) > 0

        print()
        print("Burn 14B rejection test passed.")
        print(
            f"Manifest validation errors: "
            f"{len(invalid_result.manifest.errors)}"
        )


        expected_epid = package.evidence_package_id

        assert (
            manifest["evidence_package_id"]
            == expected_epid
        )

        assert (
            certification["evidence_package_id"]
            == expected_epid
        )

        assert (
            metadata["evidence_package_id"]
            == expected_epid
        )

        assert (
            manifest["evidence_package_id"]
            == certification["evidence_package_id"]
            == metadata["evidence_package_id"]
        )

        assert manifest["status"] == "CERTIFIED"
        assert certification["status"] == "CERTIFIED"

        assert (
            manifest["schema_version"]
            == certification["schema_version"]
            == metadata["schema_version"]
        )

        assert certification["summary"] == {
            "passed": 2,
            "failed": 0,
            "warnings": 1,
            "total": 3,
        }

        assert certification["statistics"] == {
            "source_rows": 1250,
            "certified_rows": 1250,
        }

        assert metadata["dataset"] == "procurement"
        assert metadata["batch_id"] == 4

        assert (
            metadata["versions"]["certification_version"]
            == "ETL-114C.1"
        )

        assert (
            metadata["versions"]["etl_version"]
            == "0.5.0-alpha1"
        )

        assert (
            metadata["versions"]["architecture_version"]
            == "1.0"
        )

        assert metadata["runtime"]["database"] == "wcffbp"

        assert (
            metadata["source"]["repository"]
            == Path.cwd().name
        )

        assert "EPS-001 CERTIFICATION REPORT" in report

        assert (
            f"Evidence Package ID: {expected_epid}"
            in report
        )

        assert "Status:              CERTIFIED" in report
        assert "Passed:              2" in report
        assert "Failed:              0" in report
        assert "Warnings:            1" in report
        assert "[PASS] PROC-001" in report
        assert "[PASS] PROC-002" in report
        assert "[WARNING] PROC-003" in report
        assert "Source Rows: 1250" in report

        for path in expected_files:
            content = path.read_bytes()

            assert content.endswith(b"\n"), (
                f"Artifact does not end with a newline: "
                f"{path}"
            )

            assert b"\r\n" not in content, (
                f"Artifact contains CRLF newlines: "
                f"{path}"
            )

        print()
        print("EPS-001 Evidence Package Acceptance Test")
        print("----------------------------------------")
        print(f"Package directory: {package_directory}")
        print(f"Manifest:          {manifest_path}")
        print(f"Certification:     {certification_path}")
        print(f"Metadata:          {metadata_path}")
        print(f"Report:            {report_path}")
        print(f"EPID:              {expected_epid}")
        print(f"Status:            {certification['status']}")
        print(
            "Schema validation: manifest, certification, "
            "and metadata valid"
        )
        print(
            "Cross-document consistency: verified"
        )
        print(
            "Filesystem structure: verified"
        )
        print()
        print(
            "Burn 14A acceptance test passed."
        )


if __name__ == "__main__":
    main()