from __future__ import annotations

from pathlib import Path

from .evidence_package import EvidencePackage


class EvidenceWriter:
    """
    Creates the directory structure for an EPS-001 Evidence Package.
    """

    def create_package_structure(self, package: EvidencePackage) -> Path:
        package_dir = package.package_directory

        directories = [
            package_dir,
            package_dir / "metadata",
            package_dir / "reconciliation",
            package_dir / "exceptions",
            package_dir / "logs",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        return package_dir