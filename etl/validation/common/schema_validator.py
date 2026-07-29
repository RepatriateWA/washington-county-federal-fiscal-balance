"""Deterministic JSON Schema validation for evidence-package documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


@dataclass(frozen=True)
class ValidationResult:
    """Immutable result returned by SchemaValidator."""

    valid: bool
    errors: tuple[str, ...]


class SchemaValidator:
    """Validate a document against a JSON Schema without modifying either."""

    @staticmethod
    def validate(
        document: Mapping[str, Any],
        schema: Mapping[str, Any],
    ) -> ValidationResult:
        """Return a deterministic validation result.

        Raises:
            SchemaError: If the supplied schema is itself invalid.
        """
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)

        validation_errors = sorted(
            validator.iter_errors(document),
            key=lambda error: (
                tuple(str(part) for part in error.absolute_path),
                error.message,
            ),
        )

        formatted_errors = tuple(
            SchemaValidator._format_error(error)
            for error in validation_errors
        )

        return ValidationResult(
            valid=not formatted_errors,
            errors=formatted_errors,
        )

    @staticmethod
    def _format_error(error: ValidationError) -> str:
        path = ".".join(str(part) for part in error.absolute_path)
        location = path if path else "<root>"
        return f"{location}: {error.message}"