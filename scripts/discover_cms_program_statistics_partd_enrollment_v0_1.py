from __future__ import annotations

import csv
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CATALOG_URL = "https://data.cms.gov/data.json"

OUTDIR = Path(
    "data/raw/cms/medicare_rds/discovery/"
    "program_statistics_partd_enrollment_v0_1"
)

JSON_OUT = OUTDIR / "cms_partd_enrollment_catalog_matches_v0_1.json"
CSV_OUT = OUTDIR / "cms_partd_enrollment_distributions_v0_1.csv"
REPORT_OUT = OUTDIR / "cms_partd_enrollment_discovery_report_v0_1.txt"


SEARCH_TERMS = [
    "medicare part d enrollment",
    "mdcr enroll d 3",
    "retiree drug subsidy",
]


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "WCFFBP-CMS-RDS-Discovery/0.1 "
                "(Washington County Federal Fiscal Balance Project)"
            )
        },
    )

    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def text_blob(dataset: dict[str, Any]) -> str:
    pieces: list[str] = []

    for key in [
        "title",
        "description",
        "keyword",
        "theme",
        "identifier",
    ]:
        value = dataset.get(key)

        if isinstance(value, list):
            pieces.extend(str(x) for x in value)
        elif value is not None:
            pieces.append(str(value))

    return " ".join(pieces).lower()


def is_candidate(dataset: dict[str, Any]) -> bool:
    blob = text_blob(dataset)

    strong_terms = [
        "medicare part d enrollment",
        "mdcr enroll d",
        "retiree drug subsidy",
    ]

    return any(term in blob for term in strong_terms)


def flatten_distribution(
    dataset: dict[str, Any],
    distribution: dict[str, Any],
    index: int,
) -> dict[str, str]:

    temporal = distribution.get("temporal", "")

    if isinstance(temporal, dict):
        temporal = json.dumps(
            temporal,
            sort_keys=True,
        )

    return {
        "dataset_title": str(dataset.get("title", "")),
        "dataset_identifier": str(dataset.get("identifier", "")),
        "dataset_modified": str(dataset.get("modified", "")),
        "dataset_issued": str(dataset.get("issued", "")),
        "distribution_index": str(index),
        "distribution_title": str(distribution.get("title", "")),
        "description": str(distribution.get("description", "")),
        "format": str(distribution.get("format", "")),
        "media_type": str(distribution.get("mediaType", "")),
        "temporal": str(temporal),
        "access_url": str(distribution.get("accessURL", "")),
        "download_url": str(distribution.get("downloadURL", "")),
    }


def main() -> None:
    print("=" * 100)
    print("CMS PROGRAM STATISTICS PART D / RDS CATALOG DISCOVERY v0.1")
    print("=" * 100)
    print()
    print("DISCOVERY ONLY")
    print("No CMS source dataset is downloaded.")
    print("No database writes.")
    print()

    OUTDIR.mkdir(parents=True, exist_ok=True)

    print(f"Catalog: {CATALOG_URL}")
    print("Retrieving CMS catalog...")

    try:
        catalog = fetch_json(CATALOG_URL)
    except Exception as exc:
        print()
        print("FAIL: CMS catalog request failed.")
        print(repr(exc))
        raise SystemExit(1)

    datasets = catalog.get("dataset", [])

    if not isinstance(datasets, list):
        print("FAIL: CMS catalog did not contain a dataset list.")
        raise SystemExit(1)

    print(f"Catalog datasets: {len(datasets):,}")
    print()

    candidates = [
        dataset
        for dataset in datasets
        if isinstance(dataset, dict)
        and is_candidate(dataset)
    ]

    # Preserve raw candidate metadata exactly as returned by CMS.
    JSON_OUT.write_text(
        json.dumps(
            {
                "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "catalog_url": CATALOG_URL,
                "search_terms": SEARCH_TERMS,
                "candidate_count": len(candidates),
                "datasets": candidates,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows: list[dict[str, str]] = []

    for dataset in candidates:
        distributions = dataset.get("distribution", [])

        if not isinstance(distributions, list):
            distributions = []

        if not distributions:
            rows.append(
                flatten_distribution(
                    dataset,
                    {},
                    0,
                )
            )
            continue

        for i, distribution in enumerate(distributions):
            if isinstance(distribution, dict):
                rows.append(
                    flatten_distribution(
                        dataset,
                        distribution,
                        i,
                    )
                )

    fields = [
        "dataset_title",
        "dataset_identifier",
        "dataset_modified",
        "dataset_issued",
        "distribution_index",
        "distribution_title",
        "description",
        "format",
        "media_type",
        "temporal",
        "access_url",
        "download_url",
    ]

    with CSV_OUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)

    print("=" * 100)
    print("CANDIDATE DATASETS")
    print("=" * 100)

    if not candidates:
        print("NONE")
    else:
        for i, dataset in enumerate(candidates, start=1):
            print()
            print(f"[{i}] {dataset.get('title', '')}")
            print(f"    Identifier: {dataset.get('identifier', '')}")
            print(f"    Issued:     {dataset.get('issued', '')}")
            print(f"    Modified:   {dataset.get('modified', '')}")

            description = str(dataset.get("description", ""))
            if description:
                clean = " ".join(description.split())
                print(f"    Description: {clean[:500]}")

            distributions = dataset.get("distribution", [])
            if not isinstance(distributions, list):
                distributions = []

            print(f"    Distributions: {len(distributions)}")

            for j, distro in enumerate(distributions):
                if not isinstance(distro, dict):
                    continue

                print()
                print(f"      Distribution {j}")
                print(
                    f"        description: "
                    f"{distro.get('description', '')}"
                )
                print(
                    f"        format:      "
                    f"{distro.get('format', '')}"
                )
                print(
                    f"        mediaType:   "
                    f"{distro.get('mediaType', '')}"
                )
                print(
                    f"        temporal:    "
                    f"{distro.get('temporal', '')}"
                )
                print(
                    f"        accessURL:   "
                    f"{distro.get('accessURL', '')}"
                )
                print(
                    f"        downloadURL: "
                    f"{distro.get('downloadURL', '')}"
                )

    print()
    print("=" * 100)
    print("DISCOVERY CHECKS")
    print("=" * 100)

    checks: list[tuple[str, bool, str]] = []

    checks.append(
        (
            "CMS catalog retrieved",
            len(datasets) > 0,
            f"{len(datasets):,} datasets",
        )
    )

    checks.append(
        (
            "At least one Part D/RDS candidate discovered",
            len(candidates) > 0,
            f"{len(candidates)} candidate datasets",
        )
    )

    has_distribution = any(
        isinstance(dataset.get("distribution"), list)
        and len(dataset.get("distribution", [])) > 0
        for dataset in candidates
    )

    checks.append(
        (
            "Candidate distribution metadata exposed",
            has_distribution,
            f"{len(rows)} distribution rows",
        )
    )

    has_programmatic_path = any(
        row["access_url"].strip()
        or row["download_url"].strip()
        for row in rows
    )

    checks.append(
        (
            "At least one programmatic access/download path exposed",
            has_programmatic_path,
            (
                "CMS accessURL/downloadURL present"
                if has_programmatic_path
                else "No accessURL/downloadURL found"
            ),
        )
    )

    for label, passed, detail in checks:
        print(
            f"{'PASS' if passed else 'FAIL':4} | "
            f"{label} | {detail}"
        )

    overall = all(passed for _, passed, _ in checks)

    # Report is descriptive; source acquisition is deliberately deferred.
    report_lines = [
        "CMS PROGRAM STATISTICS PART D / RDS CATALOG DISCOVERY v0.1",
        "=" * 78,
        "",
        f"Retrieved UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Catalog: {CATALOG_URL}",
        f"Catalog datasets: {len(datasets)}",
        f"Candidate datasets: {len(candidates)}",
        f"Distribution rows: {len(rows)}",
        "",
        "CHECKS",
        "-" * 78,
    ]

    for label, passed, detail in checks:
        report_lines.append(
            f"{'PASS' if passed else 'FAIL'} | {label} | {detail}"
        )

    report_lines.extend(
        [
            "",
            "BOUNDARY",
            "-" * 78,
            (
                "This stage performs catalog discovery only. "
                "No source distribution has been selected, "
                "downloaded, transformed, or interpreted."
            ),
            (
                "A programmatic URL is evidence of accessibility, "
                "not evidence that the distribution contains the "
                "required MDCR ENROLL D 3 residence-based RDS table."
            ),
            (
                "Historical coverage and table semantics must be "
                "certified before acquisition or ledger use."
            ),
        ]
    )

    REPORT_OUT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 100)
    print(
        "OVERALL DISCOVERY: "
        + ("PASS" if overall else "FAIL")
    )
    print("=" * 100)

    print()
    print("Evidence written:")
    print(f"  {JSON_OUT}")
    print(f"  {CSV_OUT}")
    print(f"  {REPORT_OUT}")

    print()
    print("No source files were downloaded.")

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
