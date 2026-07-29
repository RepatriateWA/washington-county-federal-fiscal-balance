from copy import deepcopy

from etl.validation.common.manifest_finalizer import (
    ManifestFinalizer,
)


def main():

    manifest = {
        "schema_version": "1.0.0",
        "evidence_package_id": "PROC-B0004-EPS001",
        "package_version": "EPS-001",
        "dataset": "procurement",
        "batch_id": 4,
        "status": "CERTIFIED",
        "created_utc": "2026-07-29T19:00:00Z",
        "artifacts": [],
    }

    inventory = [

        {
            "path": "metadata/metadata.json",
            "media_type": "application/json",
            "sha256": "b" * 64,
            "size_bytes": 812,
        },

        {
            "path": "certification.json",
            "media_type": "application/json",
            "sha256": "a" * 64,
            "size_bytes": 1204,
        },

        {
            "path": "certification_report.txt",
            "media_type": "text/plain",
            "sha256": "c" * 64,
            "size_bytes": 2814,
        },

        {
            "path": "logs/example.log",
            "media_type": "text/plain",
            "sha256": "d" * 64,
            "size_bytes": 55,
        },
    ]

    original_manifest = deepcopy(manifest)
    original_inventory = deepcopy(inventory)

    finalizer = ManifestFinalizer()

    finalized = finalizer.finalize(
        manifest,
        inventory,
    )

    #
    # Inputs unchanged
    #

    assert manifest == original_manifest
    assert inventory == original_inventory

    #
    # New object
    #

    assert finalized is not manifest

    #
    # Artifact ordering
    #

    paths = [
        artifact["path"]
        for artifact in finalized["artifacts"]
    ]

    assert paths == sorted(paths)

    #
    # Descriptions injected
    #

    descriptions = {
        artifact["path"]:
            artifact.get("description")
        for artifact in finalized["artifacts"]
    }

    assert descriptions["certification.json"] == (
        "Machine-readable certification record."
    )

    assert descriptions[
        "certification_report.txt"
    ] == (
        "Human-readable certification summary."
    )

    assert descriptions[
        "metadata/metadata.json"
    ] == (
        "Runtime provenance and software metadata."
    )

    #
    # Unknown artifacts remain untouched
    #

    assert "description" not in next(
        artifact
        for artifact in finalized["artifacts"]
        if artifact["path"] == "logs/example.log"
    )

    #
    # Original metadata preserved
    #

    assert finalized["dataset"] == manifest["dataset"]
    assert finalized["status"] == manifest["status"]
    assert finalized["batch_id"] == manifest["batch_id"]

    #
    # Deterministic
    #

    finalized_again = finalizer.finalize(
        manifest,
        inventory,
    )

    assert finalized == finalized_again

    print()
    print("Finalized artifact inventory:")

    for artifact in finalized["artifacts"]:

        print(
            f"  {artifact['path']}"
        )

        if "description" in artifact:

            print(
                f"      {artifact['description']}"
            )

    print()
    print(
        "ManifestFinalizer contract test passed."
    )


if __name__ == "__main__":
    main()