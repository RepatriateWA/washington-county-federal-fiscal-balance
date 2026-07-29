"""Validate all Evidence Package publication documents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .schema_validator import SchemaValidator, ValidationResult


@dataclass(frozen=True)
class PublicationValidationResult:
    """Combined validation result for an Evidence Package."""

    valid: bool
    manifest: ValidationResult
    certification: ValidationResult
    metadata: ValidationResult


class PublicationValidator:
    """Validate all publication artifacts against their JSON Schemas."""

    def __init__(self, schema_directory: Path) -> None:
        self._schema_directory = schema_directory

    def validate(
        self,
        *,
        manifest: Mapping[str, Any],
        certification: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> PublicationValidationResult:
        """Validate all publication documents."""

        manifest_result = SchemaValidator.validate(
            manifest,
            self._load_schema("manifest.schema.json"),
        )

        certification_result = SchemaValidator.validate(
            certification,
            self._load_schema("certification.schema.json"),
        )

        metadata_result = SchemaValidator.validate(
            metadata,
            self._load_schema("metadata.schema.json"),
        )

        return PublicationValidationResult(
            valid=(
                manifest_result.valid
                and certification_result.valid
                and metadata_result.valid
            ),
            manifest=manifest_result,
            certification=certification_result,
            metadata=metadata_result,
        )

    def _load_schema(self, filename: str) -> Mapping[str, Any]:
        schema_path = self._schema_directory / filename

        with schema_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)