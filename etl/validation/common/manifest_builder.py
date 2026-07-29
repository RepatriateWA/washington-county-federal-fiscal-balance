from __future__ import annotations

from typing import Any

from .evidence_package import EvidencePackage


SCHEMA_VERSION = "1.0.0"


class ManifestBuilder:
    """
    Builds the in-memory manifest for an EPS-001 Evidence Package.

    This class performs no file I/O.
    """

    def build(self, package: EvidencePackage) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "package_version": package.package_version,
            "evidence_package_id": package.evidence_package_id,
            "dataset": package.dataset,
            "batch_id": package.batch_id,
            "status": (
                "CERTIFIED"
                if package.is_certified
                else "NOT_CERTIFIED"
            ),
            "created_utc": (
                package.created_utc
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "artifacts": [],
        }