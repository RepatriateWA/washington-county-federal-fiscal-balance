from __future__ import annotations

import platform
import socket
import subprocess
from pathlib import Path
from typing import Any

from .evidence_package import EvidencePackage


SCHEMA_VERSION = "1.0.0"


class MetadataBuilder:
    """
    Builds EPS-001 provenance metadata.

    The builder performs read-only runtime and Git inspection.
    It does not write files or modify the repository.
    """

    def __init__(
        self,
        *,
        certification_version: str,
        etl_version: str | None = None,
        architecture_version: str | None = None,
        repository_root: Path | None = None,
        repository_name: str | None = None,
        database_name: str | None = None,
    ) -> None:
        if not certification_version.strip():
            raise ValueError("certification_version cannot be empty.")

        self._certification_version = certification_version.strip()
        self._etl_version = self._clean_optional(etl_version)
        self._architecture_version = self._clean_optional(
            architecture_version
        )
        self._repository_root = Path(
            repository_root or Path.cwd()
        ).resolve()
        self._repository_name = (
            self._clean_optional(repository_name)
            or self._repository_root.name
        )
        self._database_name = self._clean_optional(database_name)

    def build(
        self,
        package: EvidencePackage,
    ) -> dict[str, Any]:
        """
        Build a metadata document conforming to metadata.schema.json.
        """
        git_commit = self._get_git_commit()
        git_dirty = self._get_git_dirty_status()

        return {
            "schema_version": SCHEMA_VERSION,
            "evidence_package_id": package.evidence_package_id,
            "dataset": package.dataset,
            "batch_id": package.batch_id,
            "created_utc": self._format_utc(package.created_utc),
            "versions": {
                "evidence_package_version": package.package_version,
                "certification_version": (
                    self._certification_version
                ),
                "etl_version": self._etl_version,
                "architecture_version": (
                    self._architecture_version
                ),
            },
            "runtime": {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "hostname": self._get_hostname(),
                "database": self._database_name,
            },
            "source": {
                "git_commit": git_commit,
                "git_dirty": git_dirty,
                "repository": self._repository_name,
                "source_files": [],
            },
        }

    def _get_git_commit(self) -> str | None:
        result = self._run_git(
            "rev-parse",
            "HEAD",
        )

        if result is None:
            return None

        commit = result.strip()

        if not commit:
            return None

        return commit

    def _get_git_dirty_status(self) -> bool | None:
        result = self._run_git(
            "status",
            "--porcelain",
        )

        if result is None:
            return None

        return bool(result.strip())

    def _run_git(
        self,
        *arguments: str,
    ) -> str | None:
        try:
            completed = subprocess.run(
                ["git", *arguments],
                cwd=self._repository_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (
            FileNotFoundError,
            OSError,
            subprocess.TimeoutExpired,
        ):
            return None

        if completed.returncode != 0:
            return None

        return completed.stdout

    @staticmethod
    def _get_hostname() -> str | None:
        try:
            hostname = socket.gethostname().strip()
        except OSError:
            return None

        return hostname or None

    @staticmethod
    def _format_utc(value: object) -> str:
        iso_value = value.isoformat(timespec="seconds")

        if iso_value.endswith("+00:00"):
            return iso_value[:-6] + "Z"

        return iso_value

    @staticmethod
    def _clean_optional(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        cleaned = value.strip()

        return cleaned or None