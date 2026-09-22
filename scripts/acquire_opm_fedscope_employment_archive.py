from __future__ import annotations

import csv
import hashlib
import json
import shutil
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REGISTRY = (
    ROOT
    / "data"
    / "interim"
    / "opm"
    / "opm_fedscope_september_employment_source_registry_2015_2024.csv"
)

RAW_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "opm"
    / "fedscope"
    / "employment"
)

USER_AGENT = (
    "WCFFBP/1.0 "
    "(Washington County Federal Fiscal Balance Project)"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def download_file(
    url: str,
    destination: Path,
) -> dict:

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=180,
    ) as response:

        content_type = (
            response.headers
            .get("Content-Type", "")
            .lower()
        )

        with destination.open("wb") as f:
            shutil.copyfileobj(
                response,
                f,
            )

    return {
        "content_type": content_type,
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
    }


def classify_url(url: str) -> str:

    path = urllib.parse.urlparse(url).path.lower()

    if path.endswith(".pdf"):
        return "documentation"

    if path.endswith(".zip"):
        return "raw_data"

    raise RuntimeError(
        f"Unexpected OPM file type: {url}"
    )


def validate_download(
    file_type: str,
    path: Path,
    metadata: dict,
) -> None:

    size = metadata["bytes"]

    if file_type == "documentation":

        if size < 100_000:
            raise RuntimeError(
                f"Suspiciously small PDF: "
                f"{path} ({size:,} bytes)"
            )

        with path.open("rb") as f:
            signature = f.read(5)

        if signature != b"%PDF-":
            raise RuntimeError(
                f"Invalid PDF signature: {path}"
            )

    elif file_type == "raw_data":

        if size < 5_000_000:
            raise RuntimeError(
                f"Suspiciously small ZIP: "
                f"{path} ({size:,} bytes)"
            )

        with path.open("rb") as f:
            signature = f.read(4)

        if signature[:2] != b"PK":
            raise RuntimeError(
                f"Invalid ZIP signature: {path}"
            )


def main() -> None:

    if not REGISTRY.exists():
        raise RuntimeError(
            f"Source registry not found: {REGISTRY}"
        )

    retrieved_at = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    print("=" * 92)
    print(
        "OPM FEDSCOPE SEPTEMBER EMPLOYMENT "
        "ARCHIVE ACQUISITION 2015-2024"
    )
    print("=" * 92)
    print(f"Registry: {REGISTRY}")
    print()

    with REGISTRY.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as f:
        records = list(
            csv.DictReader(f)
        )

    expected_years = {
        str(y)
        for y in range(2015, 2025)
    }

    found_years = {
        row["year"].strip()
        for row in records
        if row["status"].strip() == "FOUND"
    }

    if found_years != expected_years:

        missing = sorted(
            expected_years
            - found_years
        )

        raise RuntimeError(
            "Registry is incomplete. "
            f"Missing: {missing}"
        )

    manifest_records = []

    seen_hashes: dict[str, str] = {}

    for row in sorted(
        records,
        key=lambda r: int(r["year"]),
    ):

        year = int(row["year"])

        snapshot = row["snapshot"].strip()

        links = [
            x.strip()
            for x in row["file_links"].split("|")
            if x.strip()
        ]

        if len(links) != 2:
            raise RuntimeError(
                f"{snapshot}: expected exactly "
                f"2 file links, found {len(links)}"
            )

        year_dir = (
            RAW_ROOT
            / snapshot
        )

        year_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        print("-" * 92)
        print(f"{snapshot}")

        for url in links:

            file_type = classify_url(url)

            extension = (
                ".pdf"
                if file_type == "documentation"
                else ".zip"
            )

            filename = (
                f"opm_fedscope_employment_"
                f"{year}09_"
                f"{file_type}_"
                f"retrieved_{retrieved_at}"
                f"{extension}"
            )

            destination = (
                year_dir
                / filename
            )

            #
            # Special handling for our previously
            # preserved September 2016 specimen.
            #
            existing_matches = sorted(
                year_dir.glob(
                    f"opm_fedscope_employment_"
                    f"{year}09_"
                    f"{file_type}_retrieved_*"
                    f"{extension}"
                )
            )

            if existing_matches:

                existing = (
                    existing_matches[-1]
                )

                metadata = {
                    "content_type":
                        "existing_preserved_file",
                    "bytes":
                        existing.stat().st_size,
                    "sha256":
                        sha256_file(existing),
                }

                path_used = existing

                print(
                    f"VERIFY EXISTING "
                    f"{file_type:14s} "
                    f"{existing.name}"
                )

            else:

                print(
                    f"DOWNLOAD        "
                    f"{file_type:14s} "
                    f"{url}"
                )

                metadata = download_file(
                    url,
                    destination,
                )

                validate_download(
                    file_type,
                    destination,
                    metadata,
                )

                path_used = destination

            digest = metadata["sha256"]

            duplicate_of = None

            if digest in seen_hashes:

                duplicate_of = (
                    seen_hashes[digest]
                )

                print(
                    "  WARNING: duplicate SHA-256 "
                    f"with {duplicate_of}"
                )

            else:
                seen_hashes[digest] = (
                    str(path_used.relative_to(ROOT))
                )

            print(
                f"  bytes:  "
                f"{metadata['bytes']:,}"
            )

            print(
                f"  sha256: "
                f"{digest}"
            )

            manifest_records.append(
                {
                    "snapshot":
                        snapshot,
                    "year":
                        year,
                    "dataset_title":
                        row["dataset_title"],
                    "index_url":
                        row["index_url"],
                    "source_url":
                        url,
                    "file_type":
                        file_type,
                    "local_path":
                        str(
                            path_used
                            .relative_to(ROOT)
                        ),
                    "retrieved_utc":
                        retrieved_at,
                    "bytes":
                        metadata["bytes"],
                    "sha256":
                        digest,
                    "content_type":
                        metadata[
                            "content_type"
                        ],
                    "duplicate_of":
                        duplicate_of,
                }
            )

    #
    # Hard validation:
    # exactly 20 artifacts =
    # 10 PDFs + 10 ZIPs.
    #
    pdf_count = sum(
        1
        for x in manifest_records
        if x["file_type"]
        == "documentation"
    )

    zip_count = sum(
        1
        for x in manifest_records
        if x["file_type"]
        == "raw_data"
    )

    if pdf_count != 10:
        raise RuntimeError(
            f"Expected 10 PDFs; "
            f"found {pdf_count}"
        )

    if zip_count != 10:
        raise RuntimeError(
            f"Expected 10 ZIPs; "
            f"found {zip_count}"
        )

    manifest = {
        "project":
            "Washington County Federal "
            "Fiscal Balance Project",
        "source":
            "U.S. Office of Personnel "
            "Management FedScope",
        "dataset":
            "September Employment Cube",
        "coverage":
            "2015-09 through 2024-09",
        "generated_utc":
            retrieved_at,
        "registry":
            str(
                REGISTRY.relative_to(ROOT)
            ),
        "artifact_count":
            len(manifest_records),
        "documentation_count":
            pdf_count,
        "raw_zip_count":
            zip_count,
        "records":
            manifest_records,
    }

    manifest_path = (
        RAW_ROOT
        / (
            "opm_fedscope_employment_"
            "archive_manifest_"
            f"{retrieved_at}.json"
        )
    )

    with manifest_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            manifest,
            f,
            indent=2,
        )

        f.write("\n")

    manifest_sha = sha256_file(
        manifest_path
    )

    print()
    print("=" * 92)
    print("ACQUISITION COMPLETE")
    print("=" * 92)

    print(
        f"Artifacts:      "
        f"{len(manifest_records)}"
    )

    print(
        f"Documentation:  "
        f"{pdf_count}"
    )

    print(
        f"Raw ZIPs:       "
        f"{zip_count}"
    )

    print(
        f"Manifest:       "
        f"{manifest_path}"
    )

    print(
        f"Manifest SHA256:"
        f" {manifest_sha}"
    )


if __name__ == "__main__":
    main()