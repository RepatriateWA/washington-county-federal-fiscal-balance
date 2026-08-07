"""Deterministic identity-fingerprint construction."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from etl.common.normalization.text import (
    clean_optional_text,
    normalize_comparison_text,
)


NULL_COMPONENT = "<NULL>"
COMPONENT_SEPARATOR = "\x1f"


def normalize_fingerprint_component(
    value: object,
) -> str:
    """Normalize one component while representing missingness explicitly."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return NULL_COMPONENT

    return normalize_comparison_text(cleaned)


def build_sha256_fingerprint(
    components: Iterable[object],
) -> str:
    """Build a stable SHA-256 digest from ordered identity components."""

    normalized_components = [
        normalize_fingerprint_component(value)
        for value in components
    ]

    fingerprint_source = COMPONENT_SEPARATOR.join(
        normalized_components
    )

    return hashlib.sha256(
        fingerprint_source.encode("utf-8")
    ).hexdigest()


def build_recipient_name_fingerprint(
    *,
    recipient_name: str,
    recipient_country_code: str | None,
    recipient_state_code: str | None,
    recipient_city_name: str | None,
    recipient_zip_code: str | None,
    recipient_address_line_1: str | None,
    business_types_code: str | None,
) -> str:
    """Build the canonical key for a named recipient without a UEI."""

    digest = build_sha256_fingerprint(
        [
            recipient_name,
            recipient_country_code,
            recipient_state_code,
            recipient_city_name,
            recipient_zip_code,
            recipient_address_line_1,
            business_types_code,
        ]
    )

    return f"NAME:{digest}"