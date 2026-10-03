"""
ETL-172J-3A
Acquire Specialized Remaining-Receipts Allocator Sources

Sources
-------
1. FHWA Highway Statistics 2024, Table FE-221B
   State-attributable Federal Highway Trust Fund payments.

2. NIAAA Surveillance Report #122
   Apparent per-capita alcohol consumption, United States and states,
   through 2023.

Purpose
-------
Acquire and preserve official source artifacts needed for ETL-172J-3.

This script:
    - downloads official source landing pages;
    - discovers the source artifact links from those pages;
    - downloads the artifacts;
    - calculates SHA-256 hashes;
    - records acquisition provenance;
    - writes a manifest.

This script does NOT:
    - parse allocator values;
    - calculate Washington shares;
    - allocate federal receipts;
    - write to PostgreSQL;
    - modify prior certified artifacts;
    - authorize final ledger inclusion.
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]

FHWA_SOURCE_DIR = (
    ROOT
    / "data"
    / "raw"
    / "fhwa"
    / "highway_trust_fund"
    / "source"
)

FHWA_VALIDATION_DIR = (
    ROOT
    / "data"
    / "raw"
    / "fhwa"
    / "highway_trust_fund"
    / "validation"
)

NIAAA_SOURCE_DIR = (
    ROOT
    / "data"
    / "raw"
    / "niaaa"
    / "alcohol_consumption"
    / "source"
)

NIAAA_VALIDATION_DIR = (
    ROOT
    / "data"
    / "raw"
    / "niaaa"
    / "alcohol_consumption"
    / "validation"
)

for directory in [
    FHWA_SOURCE_DIR,
    FHWA_VALIDATION_DIR,
    NIAAA_SOURCE_DIR,
    NIAAA_VALIDATION_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)


# =============================================================================
# OFFICIAL LANDING PAGES
# =============================================================================

FHWA_LANDING_URL = (
    "https://www.fhwa.dot.gov/policyinformation/statistics/2024/fe221b.cfm"
)

NIAAA_LANDING_URL = (
    "https://www.niaaa.nih.gov/publications/surveillance-reports/"
    "surveillance122"
)


# =============================================================================
# OUTPUTS
# =============================================================================

MANIFEST_FILE = (
    FHWA_VALIDATION_DIR
    / "j3_specialized_allocator_acquisition_manifest.csv"
)

REPORT_FILE = (
    FHWA_VALIDATION_DIR
    / "j3_specialized_allocator_acquisition_report.txt"
)


# =============================================================================
# HTTP
# =============================================================================

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; WCFFBP-source-acquisition/1.0; "
    "+https://github.com/)"
)


def fetch_bytes(url: str) -> tuple[bytes, str, str]:
    """
    Download URL and return:
        content bytes,
        final resolved URL,
        Content-Type.
    """
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=120,
    ) as response:
        data = response.read()
        final_url = response.geturl()
        content_type = response.headers.get(
            "Content-Type",
            "",
        )

    if not data:
        raise ValueError(
            f"Downloaded zero bytes from {url}"
        )

    return data, final_url, content_type


def decode_html(data: bytes) -> str:
    """
    Decode an HTML page conservatively.
    """
    for encoding in [
        "utf-8",
        "windows-1252",
        "latin-1",
    ]:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError("Could not decode HTML page.")


# =============================================================================
# HASHING / WRITING
# =============================================================================

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


# =============================================================================
# LINK EXTRACTION
# =============================================================================

HREF_RE = re.compile(
    r"""href\s*=\s*["']([^"']+)["']""",
    flags=re.IGNORECASE,
)


def extract_links(
    page_html: str,
    base_url: str,
) -> list[str]:
    links: list[str] = []

    for raw_href in HREF_RE.findall(page_html):
        href = html.unescape(raw_href.strip())

        if not href:
            continue

        if href.startswith("#"):
            continue

        absolute = urllib.parse.urljoin(
            base_url,
            href,
        )

        links.append(absolute)

    # Preserve source-page order while removing duplicates.
    return list(dict.fromkeys(links))


# =============================================================================
# FHWA
# =============================================================================

def choose_fhwa_artifact(
    links: list[str],
) -> str:
    """
    Find the Excel artifact associated with FE-221B.

    Preference:
        explicit FE221B Excel/XLS/XLSX link.

    Fail rather than silently choosing an unrelated workbook.
    """
    candidates = []

    for url in links:
        lower = url.lower()

        if "fe221b" not in lower:
            continue

        if (
            lower.endswith(".xlsx")
            or lower.endswith(".xls")
            or ".xlsx?" in lower
            or ".xls?" in lower
        ):
            candidates.append(url)

    if len(candidates) != 1:
        raise ValueError(
            "Expected exactly one FHWA FE-221B Excel artifact; "
            f"found {len(candidates)}: {candidates}"
        )

    return candidates[0]


def acquire_fhwa() -> dict[str, str | int]:
    landing_bytes, landing_final_url, landing_type = fetch_bytes(
        FHWA_LANDING_URL
    )

    landing_html = decode_html(landing_bytes)

    landing_path = (
        FHWA_SOURCE_DIR
        / "fhwa_highway_statistics_2024_fe221b_landing.html"
    )

    write_bytes(
        landing_path,
        landing_bytes,
    )

    links = extract_links(
        landing_html,
        landing_final_url,
    )

    artifact_url = choose_fhwa_artifact(links)

    artifact_bytes, artifact_final_url, artifact_type = fetch_bytes(
        artifact_url
    )

    parsed = urllib.parse.urlparse(
        artifact_final_url
    )

    original_name = Path(parsed.path).name

    suffix = Path(original_name).suffix.lower()

    if suffix not in {".xls", ".xlsx"}:
        raise ValueError(
            "FHWA resolved artifact does not have an Excel extension: "
            f"{artifact_final_url}"
        )

    artifact_path = (
        FHWA_SOURCE_DIR
        / f"fhwa_highway_statistics_2024_fe221b{suffix}"
    )

    write_bytes(
        artifact_path,
        artifact_bytes,
    )

    return {
        "source_agency": "FHWA",
        "source_series": "Highway Statistics 2024 Table FE-221B",
        "landing_url": FHWA_LANDING_URL,
        "landing_resolved_url": landing_final_url,
        "landing_content_type": landing_type,
        "landing_file": str(
            landing_path.relative_to(ROOT)
        ),
        "landing_bytes": len(landing_bytes),
        "landing_sha256": sha256_bytes(
            landing_bytes
        ),
        "artifact_url": artifact_url,
        "artifact_resolved_url": artifact_final_url,
        "artifact_content_type": artifact_type,
        "artifact_file": str(
            artifact_path.relative_to(ROOT)
        ),
        "artifact_bytes": len(artifact_bytes),
        "artifact_sha256": sha256_bytes(
            artifact_bytes
        ),
        "acquisition_status": "PASS",
    }


# =============================================================================
# NIAAA
# =============================================================================

def choose_niaaa_pdf(
    links: list[str],
) -> str:
    """
    Select Surveillance Report #122 PDF.

    Require the URL to look like both:
        - a PDF
        - Surveillance Report 122 / per-capita consumption material.

    Fail on ambiguity.
    """
    candidates = []

    for url in links:
        lower = url.lower()

        is_pdf = (
            lower.endswith(".pdf")
            or ".pdf?" in lower
        )

        if not is_pdf:
            continue

        relevant = (
            "122" in lower
            or "per-capita" in lower
            or "per_capita" in lower
            or "consumption" in lower
        )

        if relevant:
            candidates.append(url)

    candidates = list(dict.fromkeys(candidates))

    if len(candidates) == 1:
        return candidates[0]

    # Prefer a URL explicitly containing "122" if several PDFs exist.
    report_122 = [
        url
        for url in candidates
        if "122" in url.lower()
    ]

    if len(report_122) == 1:
        return report_122[0]

    # The current NIAAA landing page does not necessarily expose the
    # report PDF through a conventional href. Preserve link discovery
    # as the preferred route, but fall back to the verified official
    # NIAAA PDF endpoint for Surveillance Report #122.
    if len(candidates) == 0:
        return (
            "https://www.niaaa.nih.gov/sites/default/files/"
            "surveillance-report122.Per-Capita-Consumption.pdf"
        )

    raise ValueError(
        "Could not identify exactly one NIAAA Surveillance Report #122 "
        f"PDF. Candidates: {candidates}"
    )

def acquire_niaaa() -> dict[str, str | int]:
    landing_bytes, landing_final_url, landing_type = fetch_bytes(
        NIAAA_LANDING_URL
    )

    landing_html = decode_html(
        landing_bytes
    )

    landing_path = (
        NIAAA_SOURCE_DIR
        / "niaaa_surveillance_report_122_landing.html"
    )

    write_bytes(
        landing_path,
        landing_bytes,
    )

    links = extract_links(
        landing_html,
        landing_final_url,
    )

    artifact_url = choose_niaaa_pdf(
        links
    )

    artifact_bytes, artifact_final_url, artifact_type = fetch_bytes(
        artifact_url
    )

    if not artifact_bytes.startswith(b"%PDF"):
        raise ValueError(
            "NIAAA artifact does not have a PDF file signature. "
            f"Resolved URL: {artifact_final_url}"
        )

    artifact_path = (
        NIAAA_SOURCE_DIR
        / "niaaa_surveillance_report_122.pdf"
    )

    write_bytes(
        artifact_path,
        artifact_bytes,
    )

    return {
        "source_agency": "NIAAA",
        "source_series": "Surveillance Report #122",
        "landing_url": NIAAA_LANDING_URL,
        "landing_resolved_url": landing_final_url,
        "landing_content_type": landing_type,
        "landing_file": str(
            landing_path.relative_to(ROOT)
        ),
        "landing_bytes": len(landing_bytes),
        "landing_sha256": sha256_bytes(
            landing_bytes
        ),
        "artifact_url": artifact_url,
        "artifact_resolved_url": artifact_final_url,
        "artifact_content_type": artifact_type,
        "artifact_file": str(
            artifact_path.relative_to(ROOT)
        ),
        "artifact_bytes": len(artifact_bytes),
        "artifact_sha256": sha256_bytes(
            artifact_bytes
        ),
        "acquisition_status": "PASS",
    }


# =============================================================================
# MANIFEST
# =============================================================================

def write_manifest(
    rows: list[dict[str, str | int]],
) -> None:
    if not rows:
        raise ValueError(
            "Refusing to write empty acquisition manifest."
        )

    fieldnames = list(rows[0].keys())

    with MANIFEST_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    acquired_utc = datetime.now(
        timezone.utc
    ).isoformat()

    print("=" * 96)
    print(
        "ETL-172J-3A - SPECIALIZED RECEIPT ALLOCATOR SOURCE ACQUISITION"
    )
    print("=" * 96)
    print()

    print("Acquiring FHWA Table FE-221B...")
    fhwa = acquire_fhwa()
    fhwa["acquired_utc"] = acquired_utc

    print(
        "  PASS:",
        fhwa["artifact_file"],
    )
    print(
        "  Bytes:",
        f"{int(fhwa['artifact_bytes']):,}",
    )
    print(
        "  SHA256:",
        fhwa["artifact_sha256"],
    )
    print()

    print("Acquiring NIAAA Surveillance Report #122...")
    niaaa = acquire_niaaa()
    niaaa["acquired_utc"] = acquired_utc

    print(
        "  PASS:",
        niaaa["artifact_file"],
    )
    print(
        "  Bytes:",
        f"{int(niaaa['artifact_bytes']):,}",
    )
    print(
        "  SHA256:",
        niaaa["artifact_sha256"],
    )
    print()

    # Ensure identical schema after acquired_utc was added.
    ordered_fields = [
        "source_agency",
        "source_series",
        "landing_url",
        "landing_resolved_url",
        "landing_content_type",
        "landing_file",
        "landing_bytes",
        "landing_sha256",
        "artifact_url",
        "artifact_resolved_url",
        "artifact_content_type",
        "artifact_file",
        "artifact_bytes",
        "artifact_sha256",
        "acquisition_status",
        "acquired_utc",
    ]

    rows = []

    for source in [fhwa, niaaa]:
        rows.append(
            {
                field: source[field]
                for field in ordered_fields
            }
        )

    with MANIFEST_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=ordered_fields,
        )
        writer.writeheader()
        writer.writerows(rows)

    report_lines = [
        "=" * 96,
        "ETL-172J-3A - SPECIALIZED RECEIPT ALLOCATOR SOURCE ACQUISITION",
        "=" * 96,
        "",
        f"Acquired UTC: {acquired_utc}",
        "",
        "FHWA",
        "-" * 96,
        f"Series  : {fhwa['source_series']}",
        f"Artifact: {fhwa['artifact_file']}",
        f"Bytes   : {int(fhwa['artifact_bytes']):,}",
        f"SHA256  : {fhwa['artifact_sha256']}",
        f"Status  : {fhwa['acquisition_status']}",
        "",
        "NIAAA",
        "-" * 96,
        f"Series  : {niaaa['source_series']}",
        f"Artifact: {niaaa['artifact_file']}",
        f"Bytes   : {int(niaaa['artifact_bytes']):,}",
        f"SHA256  : {niaaa['artifact_sha256']}",
        f"Status  : {niaaa['acquisition_status']}",
        "",
        f"Manifest: {MANIFEST_FILE.relative_to(ROOT)}",
        "",
        "BOUNDARIES",
        "-" * 96,
        "No allocator values extracted.",
        "No Washington shares calculated.",
        "No federal receipts allocated.",
        "No PostgreSQL writes.",
        "No final-ledger authorization.",
        "",
        "ETL-172J-3A RESULT: PASS",
        "",
    ]

    report = "\n".join(report_lines)

    REPORT_FILE.write_text(
        report,
        encoding="utf-8",
    )

    print(report)


if __name__ == "__main__":
    main()