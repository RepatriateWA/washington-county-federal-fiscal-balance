"""Contract tests for PublicationValidator."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from etl.validation.common.certification_builder import (
    CertificationBuilder,
)
from etl.validation.common.evidence_package import EvidencePackage
from etl.validation.common.manifest_builder import ManifestBuilder
from etl.validation.common.metadata_builder import MetadataBuilder
from etl.validation.common.publication_validator import (
    PublicationValidator,
)


def _build_documents() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    """Build real EPS-001 publication documents."""

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
    ]

    manifest = ManifestBuilder().build(package)

    certification = CertificationBuilder(
        certification_version="ETL-114C.1",
        etl_version="0.5.0-alpha1",
    ).build(
        package,
        checks=checks,
        statistics={
            "source_rows": 1250,
            "certified_rows": 1250,
        },
    )

    metadata = MetadataBuilder(
        certification_version="ETL-114C.1",
        etl_version="0.5.0-alpha1",
        architecture_version="1.0",
        repository_root=Path.cwd(),
        database_name="wcffbp",
    ).build(package)

    return manifest, certification, metadata


def main() -> None:
    schema_directory = (
        Path.cwd()
        / "schemas"
        / "evidence"
    )

    validator = PublicationValidator(schema_directory)

    manifest, certification, metadata = (
        _build_documents()
    )

    original_manifest = deepcopy(manifest)
    original_certification = deepcopy(certification)
    original_metadata = deepcopy(metadata)

    # Happy path: all three real builder outputs must pass.
    valid_result = validator.validate(
        manifest=manifest,
        certification=certification,
        metadata=metadata,
    )

    assert valid_result.valid is True
    assert valid_result.manifest.valid is True
    assert valid_result.certification.valid is True
    assert valid_result.metadata.valid is True

    assert valid_result.manifest.errors == ()
    assert valid_result.certification.errors == ()
    assert valid_result.metadata.errors == ()

    # Validation must not modify any input document.
    assert manifest == original_manifest
    assert certification == original_certification
    assert metadata == original_metadata

    # Manifest-only defect.
    invalid_manifest = deepcopy(manifest)
    invalid_manifest.pop("schema_version")

    manifest_failure = validator.validate(
        manifest=invalid_manifest,
        certification=certification,
        metadata=metadata,
    )

    assert manifest_failure.valid is False
    assert manifest_failure.manifest.valid is False
    assert manifest_failure.certification.valid is True
    assert manifest_failure.metadata.valid is True

    assert any(
        "'schema_version' is a required property" in error
        for error in manifest_failure.manifest.errors
    )

    # Certification-only defect.
    invalid_certification = deepcopy(certification)
    invalid_certification["status"] = "PENDING"

    certification_failure = validator.validate(
        manifest=manifest,
        certification=invalid_certification,
        metadata=metadata,
    )

    assert certification_failure.valid is False
    assert certification_failure.manifest.valid is True
    assert certification_failure.certification.valid is False
    assert certification_failure.metadata.valid is True

    assert any(
        "PENDING" in error
        for error in certification_failure.certification.errors
    )

    # Metadata-only defect.
    invalid_metadata = deepcopy(metadata)
    invalid_metadata["dataset"] = "Procurement"

    metadata_failure = validator.validate(
        manifest=manifest,
        certification=certification,
        metadata=invalid_metadata,
    )

    assert metadata_failure.valid is False
    assert metadata_failure.manifest.valid is True
    assert metadata_failure.certification.valid is True
    assert metadata_failure.metadata.valid is False

    assert any(
        "Procurement" in error
        for error in metadata_failure.metadata.errors
    )

    # Repeated validation must produce identical results.
    first_run = validator.validate(
        manifest=manifest,
        certification=certification,
        metadata=metadata,
    )

    second_run = validator.validate(
        manifest=manifest,
        certification=certification,
        metadata=metadata,
    )

    assert first_run == second_run

    # Invalid inputs must also remain unchanged.
    manifest_before = deepcopy(invalid_manifest)
    certification_before = deepcopy(invalid_certification)
    metadata_before = deepcopy(invalid_metadata)

    validator.validate(
        manifest=invalid_manifest,
        certification=invalid_certification,
        metadata=invalid_metadata,
    )

    assert invalid_manifest == manifest_before
    assert invalid_certification == certification_before
    assert invalid_metadata == metadata_before

    print("PublicationValidator contract test passed.")
    print()
    print("Validated documents:")
    print("  manifest.json:          valid")
    print("  certification.json:     valid")
    print("  metadata/metadata.json: valid")
    print()
    print("Independent failure isolation verified.")
    print("Deterministic results verified.")
    print("Input immutability verified.")


if __name__ == "__main__":
    main()