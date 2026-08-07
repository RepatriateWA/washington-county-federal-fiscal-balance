"""Shared warehouse identity framework."""

from etl.common.identity.recipient_identity import (
    RecipientIdentity,
    RecipientIdentityInput,
    RecipientIdentityType,
    classify_recipient_identity,
)

from etl.common.identity.place_identity import (
    PlaceIdentity,
    PlaceIdentityInput,
    PlaceIdentityType,
    classify_place_identity,
)


__all__ = [
    "RecipientIdentity",
    "RecipientIdentityInput",
    "RecipientIdentityType",
    "classify_recipient_identity",
        "PlaceIdentity",
    "PlaceIdentityInput",
    "PlaceIdentityType",
    "classify_place_identity",
]



