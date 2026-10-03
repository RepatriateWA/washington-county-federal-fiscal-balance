"""
ETL-172B-1
Acquire IRS SOI Historic Table 2 state data and documentation.

Purpose
-------
Preserve official IRS all-state Historic Table 2 data for tax years
2015-2023, together with the corresponding annual documentation.

This is an acquisition/provenance step only.

It does NOT:
- interpret IRS variables,
- construct tax liability,
- allocate federal receipts,
- map tax years to fiscal years,
- extrapolate TY2024,
- write to PostgreSQL,
- authorize ledger inclusion.

Source
------
Internal Revenue Service, Statistics of Income (SOI),
Historic Table 2:
"Individual income and tax data, by state and size of adjusted gross income."

Acquisition universe
--------------------
TY2015-TY2023.

TY2024 is deliberately outside the acquisition universe because it is
not currently available from this IRS source. No substitute or
extrapolation is performed.

Outputs
-------
data/raw/irs/historic_table_2/source/
data/raw/irs/historic_table_2/documentation/
data/raw/irs/historic_table_2/validation/acquisition_manifest.csv
"""

from __future__ import annotations

import csv
import hashlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TAX_YEARS = tuple(range(2015, 2024))

CURRENT_PAGE = (
    "https://www.irs.gov/statistics/"
    "soi-tax-stats-historic-table-2"
)

HISTORICAL_PAGE_2015_2019 = (
    "https://www.irs.gov/statistics/"
    "soi-tax-stats-historic-table-2-2015-2019"
)

SOURCE_DIR = Path(
    "data/raw/irs/historic_table_2/source"
)

DOCUMENTATION_DIR = Path(
    "data/raw/irs/historic_table_2/documentation"
)

VALIDATION_DIR = Path(
    "data/raw/irs/historic_table_2/validation"
)

MANIFEST_PATH = VALIDATION_DIR / "acquisition_manifest.csv"

USER_AGENT = (
    "washington-county-federal-fiscal-balance/"
    "ETL-172B-1 IRS Historic Table 2 acquisition"
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiscoveredArtifact:
    tax_year: int
    artifact_type: str
    landing_page_url: str
    source_url: str
    link_text: str


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def ensure_directories() -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENTATION_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)


def fetch_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )

    with urlopen(request, timeout=120) as response:
        return response.read()


def fetch_text(url: str) -> str:
    data = fetch_bytes(url)

    return data.decode(
        "utf-8",
        errors="replace",
    )


def assert_irs_url(url: str) -> None:
    host = urlparse(url).hostname or ""

    if host.lower() not in {
        "irs.gov",
        "www.irs.gov",
    }:
        raise RuntimeError(
            f"Refusing non-IRS source URL: {url}"
        )


def normalize_link_text(text: str) -> str:
    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )

    return " ".join(text.split())


def filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name

    if not name:
        raise RuntimeError(
            f"Could not determine filename from URL: {url}"
        )

    return name


# ---------------------------------------------------------------------------
# IRS page parsing
# ---------------------------------------------------------------------------

ANCHOR_PATTERN = re.compile(
    r"""
    <a
    \s+
    [^>]*?
    href=["'](?P<href>[^"']+)["']
    [^>]*?
    >
    (?P<text>.*?)
    </a>
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)


def extract_links(
    html: str,
    base_url: str,
) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []

    for match in ANCHOR_PATTERN.finditer(html):
        href = match.group("href").strip()
        text = normalize_link_text(
            match.group("text")
        )

        absolute_url = urljoin(
            base_url,
            href,
        )

        links.append(
            (
                text,
                absolute_url,
            )
        )

    return links


def year_page_url(tax_year: int) -> str:
    if 2015 <= tax_year <= 2019:
        return HISTORICAL_PAGE_2015_2019

    if 2020 <= tax_year <= 2023:
        return CURRENT_PAGE

    raise ValueError(
        f"Unsupported tax year: {tax_year}"
    )


def locate_year_section(
    html: str,
    tax_year: int,
) -> str:
    """
    Restrict link discovery to the HTML section belonging to one tax year.

    This prevents a generic link-text match from accidentally selecting
    another year's artifact.
    """

    start_pattern = re.compile(
        rf"""
        Tax
        \s+
        year
        \s+
        {tax_year}
        \s*:
        \s*
        Historic
        \s+
        table
        \s+
        2
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    start_match = start_pattern.search(html)

    if start_match is None:
        raise RuntimeError(
            f"Could not locate IRS Historic Table 2 "
            f"section for TY{tax_year}."
        )

    remainder = html[start_match.start():]

    next_year_pattern = re.compile(
        r"""
        Tax
        \s+
        year
        \s+
        \d{4}
        \s*:
        \s*
        Historic
        \s+
        table
        \s+
        2
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    matches = list(
        next_year_pattern.finditer(remainder)
    )

    if len(matches) >= 2:
        return remainder[
            :matches[1].start()
        ]

    return remainder


def discover_csv(
    tax_year: int,
    landing_page_url: str,
    section_html: str,
) -> DiscoveredArtifact:
    links = extract_links(
        section_html,
        landing_page_url,
    )

    candidates: list[
        tuple[str, str]
    ] = []

    for text, url in links:
        lower_text = text.lower()
        lower_url = url.lower()

        looks_like_state_data = (
            "historic" in lower_text
            and "table 2" in lower_text
            and "state data" in lower_text
        )

        looks_like_csv = (
            lower_url.endswith(".csv")
            or ".csv?" in lower_url
        )

        if (
            looks_like_state_data
            and looks_like_csv
        ):
            candidates.append(
                (
                    text,
                    url,
                )
            )

    if len(candidates) != 1:
        detail = "\n".join(
            f"  {text!r} -> {url}"
            for text, url in candidates
        )

        raise RuntimeError(
            f"Expected exactly one Historic Table 2 "
            f"state-data CSV for TY{tax_year}; "
            f"found {len(candidates)}.\n"
            f"{detail}"
        )

    text, url = candidates[0]

    assert_irs_url(url)

    return DiscoveredArtifact(
        tax_year=tax_year,
        artifact_type="STATE_DATA_CSV",
        landing_page_url=landing_page_url,
        source_url=url,
        link_text=text,
    )


def discover_documentation(
    tax_year: int,
    landing_page_url: str,
    section_html: str,
) -> DiscoveredArtifact:
    links = extract_links(
        section_html,
        landing_page_url,
    )

    candidates: list[
        tuple[str, str]
    ] = []

    for text, url in links:
        lower_text = text.lower()

        if (
            "documentation" in lower_text
            and "guide" in lower_text
        ):
            candidates.append(
                (
                    text,
                    url,
                )
            )

    if len(candidates) != 1:
        detail = "\n".join(
            f"  {text!r} -> {url}"
            for text, url in candidates
        )

        raise RuntimeError(
            f"Expected exactly one Historic Table 2 "
            f"documentation guide for TY{tax_year}; "
            f"found {len(candidates)}.\n"
            f"{detail}"
        )

    text, url = candidates[0]

    assert_irs_url(url)

    return DiscoveredArtifact(
        tax_year=tax_year,
        artifact_type="DOCUMENTATION",
        landing_page_url=landing_page_url,
        source_url=url,
        link_text=text,
    )


def discover_artifacts() -> list[DiscoveredArtifact]:
    page_cache: dict[str, str] = {}
    artifacts: list[DiscoveredArtifact] = []

    for tax_year in TAX_YEARS:
        landing_page_url = year_page_url(
            tax_year
        )

        if landing_page_url not in page_cache:
            print(
                f"Fetching IRS landing page: "
                f"{landing_page_url}"
            )

            page_cache[
                landing_page_url
            ] = fetch_text(
                landing_page_url
            )

        html = page_cache[
            landing_page_url
        ]

        section_html = locate_year_section(
            html,
            tax_year,
        )

        csv_artifact = discover_csv(
            tax_year,
            landing_page_url,
            section_html,
        )

        documentation_artifact = (
            discover_documentation(
                tax_year,
                landing_page_url,
                section_html,
            )
        )

        artifacts.extend(
            [
                csv_artifact,
                documentation_artifact,
            ]
        )

    return artifacts


# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------

def validate_csv(
    data: bytes,
    tax_year: int,
) -> None:
    if not data:
        raise RuntimeError(
            f"TY{tax_year} CSV is empty."
        )

    prefix = data[:500].lower()

    if b"<html" in prefix:
        raise RuntimeError(
            f"TY{tax_year} CSV download appears "
            f"to be HTML rather than CSV."
        )

    try:
        text = data.decode(
            "utf-8-sig",
            errors="strict",
        )
    except UnicodeDecodeError:
        text = data.decode(
            "latin-1",
            errors="strict",
        )

    first_line = (
        text.splitlines()[0]
        if text.splitlines()
        else ""
    )

    if "," not in first_line:
        raise RuntimeError(
            f"TY{tax_year} state-data artifact "
            f"does not look like CSV."
        )


def validate_documentation(
    data: bytes,
    tax_year: int,
) -> None:
    if not data:
        raise RuntimeError(
            f"TY{tax_year} documentation is empty."
        )

    prefix = data[:500].lower()

    if b"<html" in prefix:
        raise RuntimeError(
            f"TY{tax_year} documentation download "
            f"appears to be an HTML page."
        )


# ---------------------------------------------------------------------------
# Local naming and preservation
# ---------------------------------------------------------------------------

def documentation_extension(
    source_url: str,
) -> str:
    suffix = Path(
        urlparse(source_url).path
    ).suffix.lower()

    if suffix:
        return suffix

    return ".bin"


def destination_path(
    artifact: DiscoveredArtifact,
) -> Path:
    if (
        artifact.artifact_type
        == "STATE_DATA_CSV"
    ):
        return SOURCE_DIR / (
            f"irs_historic_table_2_"
            f"state_data_ty{artifact.tax_year}.csv"
        )

    if (
        artifact.artifact_type
        == "DOCUMENTATION"
    ):
        extension = documentation_extension(
            artifact.source_url
        )

        return DOCUMENTATION_DIR / (
            f"irs_historic_table_2_"
            f"documentation_ty"
            f"{artifact.tax_year}"
            f"{extension}"
        )

    raise RuntimeError(
        f"Unknown artifact type: "
        f"{artifact.artifact_type}"
    )


def preserve_artifact(
    artifact: DiscoveredArtifact,
) -> dict[str, str | int]:
    destination = destination_path(
        artifact
    )

    if destination.exists():
        raise FileExistsError(
            "Refusing silent overwrite of existing "
            f"artifact:\n{destination}"
        )

    print(
        f"Downloading TY{artifact.tax_year} "
        f"{artifact.artifact_type}"
    )
    print(
        f"  {artifact.source_url}"
    )

    data = fetch_bytes(
        artifact.source_url
    )

    if (
        artifact.artifact_type
        == "STATE_DATA_CSV"
    ):
        validate_csv(
            data,
            artifact.tax_year,
        )

    elif (
        artifact.artifact_type
        == "DOCUMENTATION"
    ):
        validate_documentation(
            data,
            artifact.tax_year,
        )

    destination.write_bytes(data)

    digest = sha256_bytes(data)

    print(
        f"  saved : {destination}"
    )
    print(
        f"  bytes : {len(data):,}"
    )
    print(
        f"  sha256: {digest}"
    )

    return {
        "tax_year": artifact.tax_year,
        "artifact_type": artifact.artifact_type,
        "source_title": artifact.link_text,
        "landing_page_url": (
            artifact.landing_page_url
        ),
        "source_url": artifact.source_url,
        "source_filename": filename_from_url(
            artifact.source_url
        ),
        "local_path": destination.as_posix(),
        "bytes": len(data),
        "sha256": digest,
        "retrieved_utc": utc_now_iso(),
        "acquisition_status": "DOWNLOADED",
    }


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

MANIFEST_FIELDS = [
    "tax_year",
    "artifact_type",
    "source_title",
    "landing_page_url",
    "source_url",
    "source_filename",
    "local_path",
    "bytes",
    "sha256",
    "retrieved_utc",
    "acquisition_status",
]


def write_manifest(
    rows: Iterable[
        dict[str, str | int]
    ],
) -> None:
    if MANIFEST_PATH.exists():
        raise FileExistsError(
            "Refusing silent overwrite of existing "
            f"manifest:\n{MANIFEST_PATH}"
        )

    with MANIFEST_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=MANIFEST_FIELDS,
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(
        "=" * 88
    )
    print(
        "IRS HISTORIC TABLE 2 ACQUISITION "
        "— ETL-172B-1"
    )
    print(
        "=" * 88
    )
    print()
    print(
        "Tax years       : 2015-2023"
    )
    print(
        "TY2024          : NOT ACQUIRED / "
        "SOURCE UNAVAILABLE"
    )
    print(
        "Database writes : NONE"
    )
    print(
        "Incidence model : NONE"
    )
    print(
        "FY/TY mapping   : NONE"
    )
    print(
        "Extrapolation   : NONE"
    )
    print()

    ensure_directories()

    print(
        "Discovering official IRS artifacts..."
    )
    print()

    artifacts = discover_artifacts()

    expected_count = (
        len(TAX_YEARS) * 2
    )

    if len(artifacts) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} artifacts; "
            f"discovered {len(artifacts)}."
        )

    print()
    print(
        f"Discovery PASS: "
        f"{len(artifacts)} artifacts"
    )
    print()

    manifest_rows: list[
        dict[str, str | int]
    ] = []

    for artifact in artifacts:
        row = preserve_artifact(
            artifact
        )

        manifest_rows.append(row)

        print()

    write_manifest(
        manifest_rows
    )

    csv_count = sum(
        row["artifact_type"]
        == "STATE_DATA_CSV"
        for row in manifest_rows
    )

    documentation_count = sum(
        row["artifact_type"]
        == "DOCUMENTATION"
        for row in manifest_rows
    )

    print(
        "=" * 88
    )
    print(
        "ACQUISITION SUMMARY"
    )
    print(
        "=" * 88
    )
    print()
    print(
        f"State-data CSV files : "
        f"{csv_count}"
    )
    print(
        f"Documentation files  : "
        f"{documentation_count}"
    )
    print(
        f"Total artifacts      : "
        f"{len(manifest_rows)}"
    )
    print()
    print(
        f"Manifest:"
    )
    print(
        f"  {MANIFEST_PATH}"
    )
    print()
    print(
        "TY2024 status:"
    )
    print(
        "  SOURCE UNAVAILABLE — "
        "NO EXTRAPOLATION PERFORMED"
    )
    print()
    print(
        "FINAL RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )

    except Exception as exc:
        print(
            file=sys.stderr,
        )
        print(
            "=" * 88,
            file=sys.stderr,
        )
        print(
            "FINAL RESULT: FAIL",
            file=sys.stderr,
        )
        print(
            "=" * 88,
            file=sys.stderr,
        )
        print(
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

        raise