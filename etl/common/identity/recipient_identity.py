"""Public API for deterministic shared recipient identity."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from etl.common.identity.exceptions import (
    UnsupportedRecipientIdentityError,
)
from etl.common.identity.fingerprint import (
    build_recipient_name_fingerprint,
)
from etl.common.identity.placeholders import (
    RecipientSourceCondition,
    identify_source_condition,
    source_condition_identity_key,
)
from etl.common.normalization.text import clean_optional_text


class RecipientIdentityType(str, Enum):
    """Supported canonical recipient identity methods."""

    UEI = "UEI"
    NAME_FINGERPRINT = "NAME_FINGERPRINT"
    SOURCE_CONDITION = "SOURCE_CONDITION"


@dataclass(frozen=True)
class RecipientIdentity:
    """Deterministic identity assigned to one recipient observation."""

    identity_key: str
    identity_type: RecipientIdentityType
    source_condition: RecipientSourceCondition | None
    recipient_uei: str | None


@dataclass(frozen=True)
class RecipientIdentityInput:
    """Source attributes used to classify recipient identity."""

    recipient_name: str
    recipient_uei: str | None = None
    recipient_country_code: str | None = None
    recipient_state_code: str | None = None
    recipient_city_name: str | None = None
    recipient_zip_code: str | None = None
    recipient_address_line_1: str | None = None
    business_types_code: str | None = None


def classify_recipient_identity(
    observation: RecipientIdentityInput,
) -> RecipientIdentity:
    """Classify one recipient using the shared warehouse rules."""

    recipient_name = clean_optional_text(
        observation.recipient_name
    )

    if recipient_name is None:
        raise UnsupportedRecipientIdentityError(
            "Recipient identity requires a populated recipient name."
        )

    source_condition = identify_source_condition(
        recipient_name
    )

    if source_condition is not None:
        return RecipientIdentity(
            identity_key=source_condition_identity_key(
                source_condition
            ),
            identity_type=(
                RecipientIdentityType.SOURCE_CONDITION
            ),
            source_condition=source_condition,
            recipient_uei=None,
        )

    recipient_uei = clean_optional_text(
        observation.recipient_uei
    )

    if recipient_uei is not None:
        recipient_uei = recipient_uei.upper()

        return RecipientIdentity(
            identity_key=f"UEI:{recipient_uei}",
            identity_type=RecipientIdentityType.UEI,
            source_condition=None,
            recipient_uei=recipient_uei,
        )

    return RecipientIdentity(
        identity_key=build_recipient_name_fingerprint(
            recipient_name=recipient_name,
            recipient_country_code=(
                observation.recipient_country_code
            ),
            recipient_state_code=(
                observation.recipient_state_code
            ),
            recipient_city_name=(
                observation.recipient_city_name
            ),
            recipient_zip_code=(
                observation.recipient_zip_code
            ),
            recipient_address_line_1=(
                observation.recipient_address_line_1
            ),
            business_types_code=(
                observation.business_types_code
            ),
        ),
        identity_type=(
            RecipientIdentityType.NAME_FINGERPRINT
        ),
        source_condition=None,
        recipient_uei=None,
    )