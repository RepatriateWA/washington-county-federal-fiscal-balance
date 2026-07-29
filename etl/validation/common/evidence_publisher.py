"""Publish EPS-001 Evidence Package artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .certification_builder import CertificationBuilder
from .evidence_package import EvidencePackage
from .evidence_writer import EvidenceWriter
from .json_writer import JsonWriter
from .manifest_builder import ManifestBuilder
from .metadata_builder import MetadataBuilder
from .publication_validator import PublicationValidator
from .report_writer import ReportWriter


class EvidencePublisher:
    """
    Publish the current EPS-001 package artifacts.

    Responsibilities:
    - create the package directory structure
    - build manifest.json
    - build certification.json
    - build metadata/metadata.json
    - validate all three JSON documents
    - write the validated JSON documents
    - render and write certification_report.txt
    """

    def __init__(
        self,
        *,
        evidence_writer: EvidenceWriter,
        manifest_builder: ManifestBuilder,
        certification_builder: CertificationBuilder,
        metadata_builder: MetadataBuilder,
        json_writer: JsonWriter,
        report_writer: ReportWriter,
        publication_validator: PublicationValidator,
    ) -> None:
        self._evidence_writer = evidence_writer
        self._manifest_builder = manifest_builder
        self._certification_builder = certification_builder
        self._metadata_builder = metadata_builder
        self._json_writer = json_writer
        self._report_writer = report_writer
        self._publication_validator = publication_validator

    def publish(
        self,
        package: EvidencePackage,
        *,
        checks: Iterable[Mapping[str, Any]] | None = None,
        statistics: Mapping[str, Any] | None = None,
    ) -> Path:
        """
        Publish the current EPS-001 artifact set.

        Returns:
            The Evidence Package directory.

        Raises:
            ValueError: If any publication document fails schema
                validation.
        """
        package_directory = (
            self._evidence_writer.create_package_structure(package)
        )

        manifest = self._manifest_builder.build(package)

        certification = self._certification_builder.build(
            package,
            checks=checks,
            statistics=statistics,
        )

        metadata = self._metadata_builder.build(package)

        validation_result = self._publication_validator.validate(
            manifest=manifest,
            certification=certification,
            metadata=metadata,
        )

        if not validation_result.valid:
            raise ValueError(
                "Evidence Package publication validation failed."
            )

        self._write_json(
            package_directory / "manifest.json",
            manifest,
        )

        self._write_json(
            package_directory / "certification.json",
            certification,
        )

        self._write_json(
            package_directory / "metadata" / "metadata.json",
            metadata,
        )

        self._report_writer.write(
            package_directory / "certification_report.txt",
            certification,
        )

        return package_directory

    def _write_json(
        self,
        path: Path,
        document: Mapping[str, Any],
    ) -> None:
        """Write one JSON publication document."""
        self._json_writer.write(
            path,
            dict(document),
        )