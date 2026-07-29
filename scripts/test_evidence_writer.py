from pathlib import Path
from types import SimpleNamespace

from etl.validation.common.evidence_package import EvidencePackage
from etl.validation.common.evidence_writer import EvidenceWriter


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
        summary=summary,      # type: ignore[arg-type]
        root_directory=Path("evidence"),
    )

    writer = EvidenceWriter()

    package_dir = writer.create_package_structure(package)

    print(package_dir)

    assert package_dir.exists()
    assert (package_dir / "metadata").exists()
    assert (package_dir / "reconciliation").exists()
    assert (package_dir / "exceptions").exists()
    assert (package_dir / "logs").exists()

    print("\nDirectory builder test passed.")


if __name__ == "__main__":
    main()