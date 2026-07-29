from pathlib import Path
from types import SimpleNamespace

from etl.validation.common.evidence_package import EvidencePackage
from etl.validation.common.manifest_builder import ManifestBuilder


summary = SimpleNamespace(
    passed=28,
    failed=0,
    warnings=0,
)

package = EvidencePackage.from_summary(
    dataset="procurement",
    dataset_code="PROC",
    batch_id=4,
    summary=summary,
    root_directory=Path("evidence"),
)

builder = ManifestBuilder()

manifest = builder.build(package)

assert manifest["schema_version"] == "1.0.0"
assert manifest["package_version"] == "EPS-001"
assert manifest["evidence_package_id"] == "PROC-B0004-EPS001"
assert manifest["dataset"] == "procurement"
assert manifest["batch_id"] == 4
assert manifest["status"] == "CERTIFIED"
assert manifest["artifacts"] == []

print()

for key, value in manifest.items():
    print(f"{key:22} {value}")

print("\nManifestBuilder smoke test passed.")