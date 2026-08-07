"""Shared conservative text-normalization helpers."""

from __future__ import annotations

import re


SPACE_PATTERN = re.compile(r"\s+")


def clean_optional_text(
    value: object,
) -> str | None:
    """Trim a value and normalize blanks to null."""

    if value is None:
        return None

    cleaned = str(value).strip()

    return cleaned or None


def normalize_comparison_text(
    value: str,
) -> str:
    """
    Normalize text conservatively for comparison.

    The original source wording should always be stored separately.
    """

    return SPACE_PATTERN.sub(
        " ",
        value.strip(),
    ).upper()