"""Contract tests for SchemaValidator."""

from __future__ import annotations

from copy import deepcopy

from etl.validation.common.schema_validator import SchemaValidator


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["package_id", "artifacts"],
    "properties": {
        "package_id": {
            "type": "string",
            "minLength": 1,
        },
        "artifacts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "sha256"],
                "properties": {
                    "path": {"type": "string"},
                    "sha256": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


def main() -> None:
    valid_document = {
        "package_id": "EP-001",
        "artifacts": [
            {
                "path": "metadata/metadata.json",
                "sha256": "abc123",
            }
        ],
    }

    original_document = deepcopy(valid_document)
    original_schema = deepcopy(SCHEMA)

    valid_result = SchemaValidator.validate(valid_document, SCHEMA)

    assert valid_result.valid is True
    assert valid_result.errors == ()
    assert valid_document == original_document
    assert SCHEMA == original_schema

    missing_property = {
        "artifacts": [],
    }

    missing_result = SchemaValidator.validate(
        missing_property,
        SCHEMA,
    )

    assert missing_result.valid is False
    assert any(
        "'package_id' is a required property" in error
        for error in missing_result.errors
    )

    wrong_type = {
        "package_id": 100,
        "artifacts": [],
    }

    type_result = SchemaValidator.validate(
        wrong_type,
        SCHEMA,
    )

    assert type_result.valid is False
    assert any(
        "package_id:" in error
        and "is not of type 'string'" in error
        for error in type_result.errors
    )

    additional_property = {
        "package_id": "EP-001",
        "artifacts": [],
        "unexpected": True,
    }

    additional_result = SchemaValidator.validate(
        additional_property,
        SCHEMA,
    )

    assert additional_result.valid is False
    assert any(
        "Additional properties are not allowed" in error
        for error in additional_result.errors
    )

    empty_result = SchemaValidator.validate({}, SCHEMA)

    assert empty_result.valid is False
    assert len(empty_result.errors) >= 1

    first_run = SchemaValidator.validate(wrong_type, SCHEMA)
    second_run = SchemaValidator.validate(wrong_type, SCHEMA)

    assert first_run == second_run

    print("SchemaValidator contract test passed.")
    print()
    print("Example validation errors:")
    for error in additional_result.errors:
        print(f"  {error}")


if __name__ == "__main__":
    main()