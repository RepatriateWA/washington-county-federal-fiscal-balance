from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = (
    ROOT
    / "data"
    / "raw"
    / "opm"
    / "fedscope"
    / "employment"
    / "2016-09"
)

FILES = {
    "documentation": {
        "url": (
            "https://www.opm.gov/data/datasets/Files/490/"
            "fac44a8f-dc3d-403d-8ddc-2d457c1f91a2.pdf"
        ),
        "extension": ".pdf",
    },
    "raw_data": {
        "url": (
            "https://www.opm.gov/data/datasets/Files/490/"
            "ae0351fd-58d1-47d5-b1aa-2ca3bf977d30.zip"
        ),
        "extension": ".zip",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "WCFFBP research acquisition "
                "(Washington County Federal Fiscal Balance Project)"
            )
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=120,
    ) as response:

        with destination.open("wb") as f:
            while True:
                block = response.read(
                    1024 * 1024
                )

                if not block:
                    break

                f.write(block)


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    retrieved = datetime.now(
        timezone.utc
    )

    stamp = retrieved.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    manifest = {
        "dataset": (
            "OPM FedScope Employment Cube"
        ),
        "snapshot": "September 2016",
        "datecode": "201609",
        "retrieved_utc":
            retrieved.isoformat(),
        "source_agency": (
            "U.S. Office of Personnel Management"
        ),
        "purpose": (
            "WCFFBP civilian federal wage "
            "allocation methodology research"
        ),
        "files": [],
    }

    for role, metadata in FILES.items():

        destination = (
            OUTPUT_DIR
            / (
                "opm_fedscope_employment_"
                f"201609_{role}_"
                f"retrieved_{stamp}"
                f"{metadata['extension']}"
            )
        )

        print(
            f"Downloading {role}:"
        )
        print(
            f"  {metadata['url']}"
        )

        download(
            metadata["url"],
            destination,
        )

        size_bytes = (
            destination.stat().st_size
        )

        digest = sha256_file(
            destination
        )

        print(
            f"  Saved: {destination}"
        )
        print(
            f"  Bytes: {size_bytes:,}"
        )
        print(
            f"  SHA-256: {digest}"
        )
        print()

        manifest["files"].append(
            {
                "role": role,
                "source_url":
                    metadata["url"],
                "local_path": str(
                    destination.relative_to(
                        ROOT
                    )
                ),
                "size_bytes":
                    size_bytes,
                "sha256":
                    digest,
            }
        )

    manifest_path = (
        OUTPUT_DIR
        / (
            "opm_fedscope_employment_"
            f"201609_acquisition_manifest_"
            f"{stamp}.json"
        )
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 72)
    print(
        "OPM FEDSCOPE FY2016 ACQUISITION COMPLETE"
    )
    print("=" * 72)

    print(
        f"Manifest: {manifest_path}"
    )

    print(
        f"Manifest SHA-256: "
        f"{sha256_file(manifest_path)}"
    )


if __name__ == "__main__":
    main()