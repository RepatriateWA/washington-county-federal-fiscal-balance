from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Iterable
from pathlib import Path
from typing import Any


class ArtifactHasher:
    """
    Computes cryptographic inventory records for Evidence Package artifacts.

    Responsibilities:
    - verify that each artifact exists and is a regular file
    - calculate SHA-256 digests
    - record file sizes
    - express paths relative to the package root
    - infer a media type when one is not explicitly supplied

    ArtifactHasher does not modify package contents.
    """

    _CHUNK_SIZE = 1024 * 1024

    _MEDIA_TYPE_OVERRIDES = {
        ".json": "application/json",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".log": "text/plain",
        ".md": "text/markdown",
        ".xlsx": (
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        ".xls": "application/vnd.ms-excel",
        ".pdf": "application/pdf",
    }

    def hash_file(
        self,
        *,
        package_directory: Path,
        artifact_path: Path,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Compute an inventory record for one artifact.

        Args:
            package_directory:
                Root directory of the Evidence Package.

            artifact_path:
                Absolute path or package-relative path to the artifact.

            media_type:
                Optional explicit media type. When omitted, the media type
                is inferred from the file extension.

        Returns:
            A dictionary containing:
            - path
            - media_type
            - size_bytes
            - sha256
        """
        package_directory = package_directory.resolve()

        resolved_artifact_path = self._resolve_artifact_path(
            package_directory=package_directory,
            artifact_path=artifact_path,
        )

        self._validate_file(
            package_directory=package_directory,
            artifact_path=resolved_artifact_path,
        )

        relative_path = resolved_artifact_path.relative_to(
            package_directory
        )

        digest = self._calculate_sha256(resolved_artifact_path)

        resolved_media_type = (
            media_type
            if media_type is not None
            else self._infer_media_type(resolved_artifact_path)
        )

        return {
            "path": relative_path.as_posix(),
            "media_type": resolved_media_type,
            "size_bytes": resolved_artifact_path.stat().st_size,
            "sha256": digest,
        }

    def hash_files(
        self,
        *,
        package_directory: Path,
        artifact_paths: Iterable[Path],
    ) -> list[dict[str, Any]]:
        """
        Compute inventory records for multiple artifacts.

        Results are sorted by relative POSIX path so repeated runs produce
        deterministic inventory ordering.
        """
        records = [
            self.hash_file(
                package_directory=package_directory,
                artifact_path=artifact_path,
            )
            for artifact_path in artifact_paths
        ]

        records.sort(
            key=lambda record: str(record["path"])
        )

        return records

    def hash_package(
        self,
        *,
        package_directory: Path,
        exclude_paths: Iterable[str | Path] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Hash every regular file beneath the package directory.

        Paths listed in exclude_paths are interpreted relative to the
        package root. manifest.json should normally be excluded because
        the manifest contains the artifact inventory and cannot hash itself
        without creating a circular dependency.
        """
        package_directory = package_directory.resolve()

        if not package_directory.exists():
            raise FileNotFoundError(
                f"Package directory does not exist: "
                f"{package_directory}"
            )

        if not package_directory.is_dir():
            raise NotADirectoryError(
                f"Package path is not a directory: "
                f"{package_directory}"
            )

        excluded = self._normalize_exclusions(
            exclude_paths or ()
        )

        artifact_paths = []

        for candidate in package_directory.rglob("*"):
            if not candidate.is_file():
                continue

            relative_path = candidate.relative_to(
                package_directory
            ).as_posix()

            if relative_path in excluded:
                continue

            artifact_paths.append(candidate)

        return self.hash_files(
            package_directory=package_directory,
            artifact_paths=artifact_paths,
        )

    def verify_file(
        self,
        *,
        package_directory: Path,
        inventory_record: dict[str, Any],
    ) -> bool:
        """
        Recompute one inventory record and compare its size and SHA-256 hash.

        Returns False when:
        - the file is missing
        - the path is invalid
        - the size differs
        - the hash differs
        """
        relative_path = inventory_record.get("path")
        expected_size = inventory_record.get("size_bytes")
        expected_sha256 = inventory_record.get("sha256")

        if not isinstance(relative_path, str):
            return False

        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
        ):
            return False

        if not isinstance(expected_sha256, str):
            return False

        try:
            actual = self.hash_file(
                package_directory=package_directory,
                artifact_path=Path(relative_path),
            )
        except (
            FileNotFoundError,
            IsADirectoryError,
            ValueError,
        ):
            return False

        return (
            actual["size_bytes"] == expected_size
            and actual["sha256"] == expected_sha256.lower()
        )

    def _calculate_sha256(
        self,
        artifact_path: Path,
    ) -> str:
        digest = hashlib.sha256()

        with artifact_path.open("rb") as artifact_file:
            while chunk := artifact_file.read(self._CHUNK_SIZE):
                digest.update(chunk)

        return digest.hexdigest()

    def _resolve_artifact_path(
        self,
        *,
        package_directory: Path,
        artifact_path: Path,
    ) -> Path:
        if artifact_path.is_absolute():
            return artifact_path.resolve()

        return (
            package_directory / artifact_path
        ).resolve()

    @staticmethod
    def _validate_file(
        *,
        package_directory: Path,
        artifact_path: Path,
    ) -> None:
        try:
            artifact_path.relative_to(package_directory)
        except ValueError as error:
            raise ValueError(
                "Artifact path must be located within the "
                "Evidence Package directory."
            ) from error

        if not artifact_path.exists():
            raise FileNotFoundError(
                f"Artifact does not exist: {artifact_path}"
            )

        if not artifact_path.is_file():
            raise IsADirectoryError(
                f"Artifact path is not a regular file: "
                f"{artifact_path}"
            )

    def _infer_media_type(
        self,
        artifact_path: Path,
    ) -> str:
        suffix = artifact_path.suffix.lower()

        if suffix in self._MEDIA_TYPE_OVERRIDES:
            return self._MEDIA_TYPE_OVERRIDES[suffix]

        inferred_type, _ = mimetypes.guess_type(
            artifact_path.name
        )

        return inferred_type or "application/octet-stream"

    @staticmethod
    def _normalize_exclusions(
        exclude_paths: Iterable[str | Path],
    ) -> set[str]:
        normalized = set()

        for path in exclude_paths:
            normalized_path = Path(path).as_posix()

            while normalized_path.startswith("./"):
                normalized_path = normalized_path[2:]

            normalized.add(normalized_path)

        return normalized