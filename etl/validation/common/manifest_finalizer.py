from __future__ import annotations

from copy import deepcopy
from collections.abc import Iterable, Mapping
from typing import Any


class ManifestFinalizer:
    """
    Produces the finalized EPS-001 manifest.

    ManifestFinalizer is a pure transformer.

    It consumes:

        • an existing manifest document
        • an artifact inventory

    and produces a new manifest document.

    It performs no file I/O and never mutates its inputs.
    """

    STANDARD_DESCRIPTIONS = {
        "manifest.json":
            "Evidence Package inventory.",

        "certification.json":
            "Machine-readable certification record.",

        "certification_report.txt":
            "Human-readable certification summary.",

        "metadata/metadata.json":
            "Runtime provenance and software metadata.",
    }

    def finalize(
        self,
        manifest: Mapping[str, Any],
        inventory: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:

        manifest_copy = deepcopy(dict(manifest))

        inventory_copy = [
            deepcopy(dict(item))
            for item in inventory
        ]

        inventory_copy.sort(
            key=lambda artifact: artifact["path"]
        )

        finalized_inventory = []

        for artifact in inventory_copy:

            finalized = deepcopy(artifact)

            description = self.STANDARD_DESCRIPTIONS.get(
                finalized["path"]
            )

            if description is not None:
                finalized["description"] = description

            finalized_inventory.append(finalized)

        manifest_copy["artifacts"] = finalized_inventory

        return manifest_copy