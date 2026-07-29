from pathlib import Path
from types import SimpleNamespace

from etl.validation.common.evidence_package import EvidencePackage


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

    print(f"EPID:              {package.evidence_package_id}")
    print(f"Package directory: {package.package_directory}")
    print(f"Created UTC:       {package.created_utc.isoformat()}")
    print(f"Certified:         {package.is_certified}")

    assert package.evidence_package_id == "PROC-B0004-EPS001"
    assert package.package_directory == Path(
        "evidence/procurement/batch_0004/EPS-001"
    )
    assert package.created_utc.utcoffset().total_seconds() == 0
    assert package.is_certified is True

    print("\nEvidencePackage smoke test passed.")


if __name__ == "__main__":
    main()