"""Exceptions raised by the shared identity framework."""

from __future__ import annotations


class IdentityError(ValueError):
    """Base exception for deterministic identity operations."""


class IdentityConflictError(IdentityError):
    """Raised when observations conflict under one identity key."""


class FingerprintConstructionError(IdentityError):
    """Raised when a deterministic fingerprint cannot be constructed."""


class UnsupportedRecipientIdentityError(IdentityError):
    """Raised when a recipient observation cannot be classified."""