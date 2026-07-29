from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from etl.validation.common.evidence_package import EvidencePackage
from etl.validation.common.metadata_builder import MetadataBuilder


def main() -> None:
    summary = SimpleNamespace(
        passed=28,
        failed=0,
        warnings=0,
    )

    package = EvidencePackage.from_summary(
        dataset="procurement",
        dataset_code="PROC",
        batch_id=4,
        summary=summary,  # type: ignore[arg-type]
        root_directory=Path("evidence"),
    )

    builder = MetadataBuilder(
        certification_version="ETL-114C.1",
        etl_version="0.5.0-alpha1",
        architecture_version="1.0",
        repository_root=Path.cwd(),
        database_name="wcffbp",
    )

    metadata = builder.build(package)

    assert metadata["schema_version"] == "1.0.0"

    assert (
        metadata["evidence_package_id"]
        == "PROC-B0004-EPS001"
    )

    assert metadata["dataset"] == "procurement"
    assert metadata["batch_id"] == 4

    assert metadata["created_utc"].endswith("Z")

    versions = metadata["versions"]

    assert (
        versions["evidence_package_version"]
        == "EPS-001"
    )
    assert (
        versions["certification_version"]
        == "ETL-114C.1"
    )
    assert versions["etl_version"] == "0.5.0-alpha1"
    assert versions["architecture_version"] == "1.0"

    runtime = metadata["runtime"]

    assert runtime["python_version"]
    assert runtime["platform"]
    assert runtime["database"] == "wcffbp"

    source = metadata["source"]

    assert source["repository"]
    assert isinstance(source["source_files"], list)

    git_commit = source["git_commit"]

    if git_commit is not None:
        assert 7 <= len(git_commit) <= 40
        assert all(
            character in "0123456789abcdefABCDEF"
            for character in git_commit
        )

    git_dirty = source["git_dirty"]

    assert (
        git_dirty is None
        or isinstance(git_dirty, bool)
    )

    print()
    print(
        f"EPID:                  "
        f"{metadata['evidence_package_id']}"
    )
    print(
        f"Certification version: "
        f"{versions['certification_version']}"
    )
    print(
        f"Python version:        "
        f"{runtime['python_version']}"
    )
    print(
        f"Platform:              "
        f"{runtime['platform']}"
    )
    print(
        f"Repository:            "
        f"{source['repository']}"
    )
    print(
        f"Git commit:            "
        f"{source['git_commit']}"
    )
    print(
        f"Git dirty:             "
        f"{source['git_dirty']}"
    )

    print("\nMetadataBuilder contract test passed.")


if __name__ == "__main__":
    main()