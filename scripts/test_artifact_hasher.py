from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from etl.validation.common.artifact_hasher import (
    ArtifactHasher,
)


def main() -> None:
    hasher = ArtifactHasher()

    with tempfile.TemporaryDirectory() as temporary_directory:
        package_directory = (
            Path(temporary_directory)
            / "evidence"
            / "procurement"
            / "batch_0004"
            / "EPS-001"
        )

        metadata_directory = (
            package_directory / "metadata"
        )

        metadata_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest_path = (
            package_directory / "manifest.json"
        )

        certification_path = (
            package_directory / "certification.json"
        )

        report_path = (
            package_directory / "certification_report.txt"
        )

        metadata_path = (
            metadata_directory / "metadata.json"
        )

        manifest_content = (
            '{\n'
            '  "artifacts": []\n'
            '}\n'
        )

        certification_content = (
            '{\n'
            '  "status": "CERTIFIED"\n'
            '}\n'
        )

        report_content = (
            "EPS-001 CERTIFICATION REPORT\n"
            "Status: CERTIFIED\n"
        )

        metadata_content = (
            '{\n'
            '  "database": "wcffbp"\n'
            '}\n'
        )

        manifest_path.write_text(
            manifest_content,
            encoding="utf-8",
            newline="\n",
        )

        certification_path.write_text(
            certification_content,
            encoding="utf-8",
            newline="\n",
        )

        report_path.write_text(
            report_content,
            encoding="utf-8",
            newline="\n",
        )

        metadata_path.write_text(
            metadata_content,
            encoding="utf-8",
            newline="\n",
        )

        single_record = hasher.hash_file(
            package_directory=package_directory,
            artifact_path=certification_path,
        )

        expected_digest = hashlib.sha256(
            certification_content.encode("utf-8")
        ).hexdigest()

        assert single_record == {
            "path": "certification.json",
            "media_type": "application/json",
            "size_bytes": len(
                certification_content.encode("utf-8")
            ),
            "sha256": expected_digest,
        }

        inventory = hasher.hash_package(
            package_directory=package_directory,
            exclude_paths=["manifest.json"],
        )

        assert [
            record["path"]
            for record in inventory
        ] == [
            "certification.json",
            "certification_report.txt",
            "metadata/metadata.json",
        ]

        assert all(
            len(record["sha256"]) == 64
            for record in inventory
        )

        assert all(
            record["sha256"]
            == record["sha256"].lower()
            for record in inventory
        )

        assert inventory[0]["media_type"] == (
            "application/json"
        )

        assert inventory[1]["media_type"] == (
            "text/plain"
        )

        assert inventory[2]["media_type"] == (
            "application/json"
        )

        for record in inventory:
            assert hasher.verify_file(
                package_directory=package_directory,
                inventory_record=record,
            )

        certification_record = next(
            record
            for record in inventory
            if record["path"] == "certification.json"
        )

        certification_path.write_text(
            certification_content
            + "altered\n",
            encoding="utf-8",
            newline="\n",
        )

        assert not hasher.verify_file(
            package_directory=package_directory,
            inventory_record=certification_record,
        )

        try:
            hasher.hash_file(
                package_directory=package_directory,
                artifact_path=Path("missing.json"),
            )
        except FileNotFoundError:
            pass
        else:
            raise AssertionError(
                "Missing artifacts must raise "
                "FileNotFoundError."
            )

        outside_file = (
            Path(temporary_directory) / "outside.txt"
        )

        outside_file.write_text(
            "outside package\n",
            encoding="utf-8",
            newline="\n",
        )

        try:
            hasher.hash_file(
                package_directory=package_directory,
                artifact_path=outside_file,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Files outside the package must be rejected."
            )

        print()
        print("Artifact inventory:")

        for record in inventory:
            print()
            print(f"Path:       {record['path']}")
            print(
                f"Media type: {record['media_type']}"
            )
            print(
                f"Size:       {record['size_bytes']} bytes"
            )
            print(f"SHA-256:    {record['sha256']}")

        print()
        print(
            "Tamper test: altered certification.json "
            "was correctly rejected."
        )
        print()
        print("ArtifactHasher contract test passed.")


if __name__ == "__main__":
    main()