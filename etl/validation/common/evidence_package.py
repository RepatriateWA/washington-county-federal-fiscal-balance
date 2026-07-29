from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Protocol


PACKAGE_VERSION = "EPS-001"

class CertificationSummary(Protocol):
    """
    Minimum interface required by EvidencePackage.
    """

    passed: int
    failed: int
    warnings: int


@dataclass(frozen=True, slots=True)
class EvidencePackage:
    """
    Immutable in-memory representation of an EPS-001 Evidence Package.

    This object performs no file or database I/O.
    """

    evidence_package_id: str
    package_version: str
    dataset: str
    dataset_code: str
    batch_id: int | str
    created_utc: datetime
    certification: CertificationSummary
    root_directory: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_summary(
        cls,
        *,
        dataset: str,
        dataset_code: str,
        batch_id: int | str,
        summary: CertificationSummary,
        root_directory: Path = Path("evidence"),
        package_version: str = PACKAGE_VERSION,
        metadata: dict[str, Any] | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> "EvidencePackage":
        """
        Construct an EvidencePackage from a completed certification summary.
        """
        normalized_dataset = cls._normalize_dataset(dataset)
        normalized_code = cls._normalize_dataset_code(dataset_code)
        normalized_version = cls._normalize_package_version(package_version)

        evidence_package_id = cls._build_evidence_package_id(
            dataset_code=normalized_code,
            batch_id=batch_id,
            package_version=normalized_version,
        )

        return cls(
            evidence_package_id=evidence_package_id,
            package_version=normalized_version,
            dataset=normalized_dataset,
            dataset_code=normalized_code,
            batch_id=batch_id,
            created_utc=datetime.now(timezone.utc),
            certification=summary,
            root_directory=Path(root_directory),
            metadata=dict(metadata or {}),
            extensions=dict(extensions or {}),
        )

    @property
    def package_directory(self) -> Path:
        """
        Return the immutable package's intended directory.

        Example:
        evidence/procurement/batch_0004/EPS-001
        """
        return (
            self.root_directory
            / self.dataset
            / self.batch_directory_name
            / self.package_version
        )

    @property
    def batch_directory_name(self) -> str:
        if isinstance(self.batch_id, int):
            return f"batch_{self.batch_id:04d}"

        safe_batch_id = re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            str(self.batch_id).strip(),
        )
        return f"batch_{safe_batch_id}"

    @property
    def is_certified(self) -> bool:
        """
        Return True when the certification summary contains no failures.
        """
        failed = getattr(self.certification, "failed", None)

        if failed is None:
            failed = getattr(self.certification, "checks_failed", None)

        if failed is None:
            raise AttributeError(
                "CertificationSummary must expose either "
                "'failed' or 'checks_failed'."
            )

        return int(failed) == 0

    @staticmethod
    def _normalize_dataset(dataset: str) -> str:
        normalized = dataset.strip().lower().replace(" ", "_")

        if not re.fullmatch(r"[a-z][a-z0-9_-]*", normalized):
            raise ValueError(
                "dataset must begin with a lowercase letter and contain "
                "only lowercase letters, digits, underscores, or hyphens."
            )

        return normalized

    @staticmethod
    def _normalize_dataset_code(dataset_code: str) -> str:
        normalized = dataset_code.strip().upper()

        if not re.fullmatch(r"[A-Z][A-Z0-9]{1,11}", normalized):
            raise ValueError(
                "dataset_code must contain 2–12 uppercase letters or digits "
                "and begin with a letter."
            )

        return normalized

    @staticmethod
    def _normalize_package_version(package_version: str) -> str:
        normalized = package_version.strip().upper()

        if not re.fullmatch(r"EPS-[0-9]{3}", normalized):
            raise ValueError(
                "package_version must use the format EPS-001."
            )

        return normalized

    @staticmethod
    def _build_evidence_package_id(
        *,
        dataset_code: str,
        batch_id: int | str,
        package_version: str,
    ) -> str:
        version_token = package_version.replace("-", "")

        if isinstance(batch_id, int):
            batch_token = f"B{batch_id:04d}"
        else:
            safe_batch_id = re.sub(
                r"[^A-Za-z0-9]+",
                "",
                str(batch_id).upper(),
            )

            if not safe_batch_id:
                raise ValueError("batch_id cannot be empty.")

            batch_token = f"B{safe_batch_id}"

        return f"{dataset_code}-{batch_token}-{version_token}"