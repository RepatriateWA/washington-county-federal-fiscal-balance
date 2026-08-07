"""Authoritative recipient placeholder and source-condition definitions."""

from __future__ import annotations

from enum import Enum

from etl.common.normalization.text import (
    clean_optional_text,
    normalize_comparison_text,
)


PII_REDACTED_NAME = "REDACTED DUE TO PII"
MULTIPLE_RECIPIENTS_NAME = "MULTIPLE RECIPIENTS"


class RecipientSourceCondition(str, Enum):
    """Special source conditions that do not assert legal identity."""

    PII_REDACTED = "PII_REDACTED"
    MULTIPLE_RECIPIENTS = "MULTIPLE_RECIPIENTS"


_PLACEHOLDER_LOOKUP = {
    PII_REDACTED_NAME: RecipientSourceCondition.PII_REDACTED,
    MULTIPLE_RECIPIENTS_NAME: (
        RecipientSourceCondition.MULTIPLE_RECIPIENTS
    ),
}


def identify_source_condition(
    recipient_name: object,
) -> RecipientSourceCondition | None:
    """Return the special source condition represented by a name."""

    cleaned = clean_optional_text(recipient_name)

    if cleaned is None:
        return None

    normalized = normalize_comparison_text(cleaned)

    return _PLACEHOLDER_LOOKUP.get(normalized)


def source_condition_identity_key(
    condition: RecipientSourceCondition,
) -> str:
    """Return the canonical identity key for a source condition."""

    return f"SOURCE:{condition.value}"