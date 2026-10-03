"""
acquire_cms_wa_mffs_savings_reports_v0_1.py

WCFFBP
CMS Washington Managed Fee-for-Service (MFFS)
Medicare Savings / Actuarial Report Acquisition v0.1

Purpose
-------
Discover and preserve the official CMS Washington MFFS Medicare
savings-report source universe.

This script:

    * queries official CMS pages only;
    * discovers Washington MFFS Medicare savings-report links;
    * follows CMS landing pages where necessary;
    * downloads official PDF source files;
    * preserves source URLs;
    * calculates SHA-256 hashes;
    * checks PDF signatures;
    * writes a reproducible acquisition manifest;
    * performs NO database writes;
    * performs NO payment reconstruction;
    * performs NO ledger inclusion.

Important
---------
Discovery is intentionally source-driven.

The script does NOT assume in advance that CMS exposes exactly
six, seven, or any other fixed number of reports.

The CMS page inventory determines the discovered source universe.
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
import ssl
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_mffs"
    / "washington"
    / "actuarial_reports"
)

VALIDATION_DIR = (
    RAW_DIR
    / "validation"
    / "source_acquisition_v0_1"
)

MANIFEST_CSV = (
    VALIDATION_DIR
    / "cms_wa_mffs_savings_report_acquisition_manifest_v0_1.csv"
)

DISCOVERY_CSV = (
    VALIDATION_DIR
    / "cms_wa_mffs_savings_report_discovery_v0_1.csv"
)

REPORT_TXT = (
    VALIDATION_DIR
    / "cms_wa_mffs_savings_report_acquisition_report_v0_1.txt"
)


CMS_DISCOVERY_PAGES = [
    (
        "WASHINGTON",
        "https://www.cms.gov/medicaid-chip/medicare-coordination/"
        "financial-alignment/wa",
    ),
    (
        "EVALUATIONS",
        "https://www.cms.gov/medicaid-chip/medicare-coordination/"
        "financial-alignment/evaluations",
    ),
]


USER_AGENT = (
    "Mozilla/5.0 WCFFBP-CMS-source-acquisition/0.1 "
    "(research; reproducible public-data acquisition)"
)


@dataclass
class Link:
    source_page: str
    source_page_url: str
    anchor_text: str
    url: str


@dataclass
class DownloadResult:
    discovery_source: str
    discovery_page_url: str
    anchor_text: str
    discovered_url: str
    resolved_pdf_url: str
    local_path: str
    http_status: str
    bytes: int
    sha256: str
    pdf_signature_ok: bool
    status: str
    error: str


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def safe_filename(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value)
    return value.strip("._") or "cms_report.pdf"


def request_bytes(url: str, timeout: int = 90) -> tuple[bytes, str, int]:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/pdf,"
                "application/octet-stream;q=0.9,*/*;q=0.8"
            ),
        },
    )

    context = ssl.create_default_context()

    with urlopen(req, timeout=timeout, context=context) as response:
        data = response.read()
        final_url = response.geturl()
        status = getattr(response, "status", 200)

    return data, final_url, int(status)


def extract_links(page_name: str, page_url: str, body: bytes) -> list[Link]:
    text = body.decode("utf-8", errors="replace")

    pattern = re.compile(
        r"<a\b[^>]*?\bhref\s*=\s*"
        r"(?P<quote>['\"])(?P<href>.*?)(?P=quote)"
        r"[^>]*>(?P<text>.*?)</a>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    links: list[Link] = []

    for match in pattern.finditer(text):
        href = html.unescape(match.group("href")).strip()

        anchor = re.sub(
            r"<[^>]+>",
            " ",
            match.group("text"),
        )
        anchor = normalize_space(anchor)

        if not href:
            continue

        absolute = urljoin(page_url, href)

        links.append(
            Link(
                source_page=page_name,
                source_page_url=page_url,
                anchor_text=anchor,
                url=absolute,
            )
        )

    return links


def is_wa_mffs_savings_candidate(link: Link) -> bool:
    text = (
        link.anchor_text
        + " "
        + link.url
    ).lower()

    washington_signal = (
        "washington" in text
        or "fai-wa-" in text
        or "/wa-" in text
    )

    savings_signal = (
        "savings" in text
        or "medicare cost savings" in text
        or "medicare savings" in text
        or "finalyr" in text
        or "prelimyr" in text
        or "prelimdy" in text
    )

    return washington_signal and savings_signal


def is_pdf_bytes(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def looks_like_pdf_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def extract_pdf_candidates(base_url: str, body: bytes) -> list[str]:
    text = body.decode("utf-8", errors="replace")

    hrefs = re.findall(
        r"""href\s*=\s*["']([^"']+)["']""",
        text,
        flags=re.IGNORECASE,
    )

    candidates: list[str] = []

    for href in hrefs:
        absolute = urljoin(base_url, html.unescape(href).strip())
        low = absolute.lower()

        if ".pdf" not in low:
            continue

        if "cms.gov" not in urlparse(absolute).netloc.lower():
            continue

        candidates.append(absolute)

    return list(dict.fromkeys(candidates))


def score_pdf_candidate(url: str) -> int:
    low = url.lower()

    score = 0

    if "fai" in low:
        score += 3
    if "wa" in low:
        score += 3
    if "saving" in low:
        score += 3
    if "final" in low:
        score += 2
    if "prelim" in low:
        score += 2
    if "report" in low:
        score += 1
    if "financial" in low:
        score += 1

    return score


def resolve_to_pdf(
    discovered_url: str,
) -> tuple[bytes, str, int]:
    body, final_url, status = request_bytes(discovered_url)

    if is_pdf_bytes(body):
        return body, final_url, status

    pdf_candidates = extract_pdf_candidates(final_url, body)

    if not pdf_candidates:
        raise RuntimeError(
            "CMS landing page contained no CMS PDF links"
        )

    ranked = sorted(
        pdf_candidates,
        key=lambda u: (
            score_pdf_candidate(u),
            u,
        ),
        reverse=True,
    )

    errors: list[str] = []

    for candidate in ranked:
        try:
            pdf_body, pdf_final_url, pdf_status = request_bytes(candidate)

            if is_pdf_bytes(pdf_body):
                return pdf_body, pdf_final_url, pdf_status

            errors.append(
                f"{candidate}: response was not PDF"
            )

        except Exception as exc:
            errors.append(
                f"{candidate}: {type(exc).__name__}: {exc}"
            )

    raise RuntimeError(
        "No valid PDF resolved from CMS landing page. "
        + " | ".join(errors[:5])
    )


def report_identity(anchor: str, url: str) -> str:
    text = normalize_space(anchor)

    patterns = [
        (
            r"(?:final\s+)?demonstration\s+year\s+"
            r"(\d+).*?"
            r"preliminary\s+(?:demonstration\s+)?year\s+(\d+)",
            "DY{}_final_DY{}_preliminary",
        ),
        (
            r"final\s+year\s+(\d+).*?"
            r"preliminary\s+year\s+(\d+)",
            "DY{}_final_DY{}_preliminary",
        ),
        (
            r"demonstration\s+year\s+(\d+)\s+preliminary",
            "DY{}_preliminary",
        ),
        (
            r"preliminary\s+(?:demonstration\s+)?year\s+(\d+)",
            "DY{}_preliminary",
        ),
    ]

    low = text.lower()

    for pattern, template in patterns:
        match = re.search(
            pattern,
            low,
            flags=re.IGNORECASE,
        )

        if match:
            return template.format(*match.groups())

    url_low = url.lower()

    match = re.search(
        r"final(?:yr|dy)(\d+).*?pre(?:lim|yr|dy)*[_\-]?(\d+)",
        url_low,
    )
    if match:
        return (
            f"DY{match.group(1)}_final_"
            f"DY{match.group(2)}_preliminary"
        )

    match = re.search(
        r"dy(\d+).*?prelim",
        url_low,
    )
    if match:
        return f"DY{match.group(1)}_preliminary"

    digest = hashlib.sha256(
        (text + "|" + url).encode("utf-8")
    ).hexdigest()[:12]

    return f"UNRESOLVED_{digest}"


def choose_filename(
    identity: str,
    resolved_pdf_url: str,
) -> str:
    original_name = Path(
        urlparse(resolved_pdf_url).path
    ).name

    if original_name.lower().endswith(".pdf"):
        original_name = safe_filename(original_name)
    else:
        original_name = "cms_source.pdf"

    return (
        f"{identity}__{original_name}"
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_discovery_csv(links: list[Link]) -> None:
    with DISCOVERY_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.writer(handle)

        writer.writerow(
            [
                "source_page",
                "source_page_url",
                "anchor_text",
                "discovered_url",
                "candidate",
            ]
        )

        for link in links:
            writer.writerow(
                [
                    link.source_page,
                    link.source_page_url,
                    link.anchor_text,
                    link.url,
                    (
                        "YES"
                        if is_wa_mffs_savings_candidate(link)
                        else "NO"
                    ),
                ]
            )


def write_manifest(results: list[DownloadResult]) -> None:
    fields = list(DownloadResult.__dataclass_fields__.keys())

    with MANIFEST_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )
        writer.writeheader()

        for result in results:
            writer.writerow(
                {
                    field: getattr(result, field)
                    for field in fields
                }
            )


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 100)
    print(
        "CMS WASHINGTON MFFS MEDICARE SAVINGS REPORT "
        "ACQUISITION v0.1"
    )
    print("=" * 100)
    print()
    print("Official CMS sources only.")
    print("No database writes.")
    print("No payment reconstruction.")
    print("No ledger inclusion.")
    print()

    all_links: list[Link] = []
    discovery_errors: list[str] = []

    for page_name, page_url in CMS_DISCOVERY_PAGES:
        print(f"Discovering: {page_name}")
        print(f"  {page_url}")

        try:
            body, final_url, status = request_bytes(page_url)

            print(f"  HTTP {status}")
            print(f"  Final URL: {final_url}")

            links = extract_links(
                page_name,
                final_url,
                body,
            )

            print(f"  Links found: {len(links):,}")

            all_links.extend(links)

        except Exception as exc:
            message = (
                f"{page_name}: {type(exc).__name__}: {exc}"
            )
            discovery_errors.append(message)
            print(f"  ERROR: {message}")

        print()

    write_discovery_csv(all_links)

    candidates = [
        link
        for link in all_links
        if is_wa_mffs_savings_candidate(link)
    ]

    # Deduplicate by discovered URL while retaining the
    # first official discovery context.
    unique_by_url: dict[str, Link] = {}

    for link in candidates:
        unique_by_url.setdefault(link.url, link)

    candidates = list(unique_by_url.values())

    print("=" * 100)
    print("DISCOVERED CANDIDATES")
    print("=" * 100)
    print()

    if not candidates:
        print("No Washington MFFS savings-report candidates discovered.")
        print()
    else:
        for index, link in enumerate(candidates, start=1):
            print(f"{index:02d}. {link.anchor_text}")
            print(f"    {link.url}")

    print()

    results: list[DownloadResult] = []

    seen_pdf_hashes: dict[str, str] = {}

    for index, link in enumerate(candidates, start=1):
        print("-" * 100)
        print(
            f"[{index}/{len(candidates)}] "
            f"{link.anchor_text}"
        )
        print("-" * 100)

        try:
            pdf_body, pdf_url, status = resolve_to_pdf(link.url)

            digest = sha256_bytes(pdf_body)
            signature_ok = is_pdf_bytes(pdf_body)

            identity = report_identity(
                link.anchor_text,
                pdf_url,
            )

            filename = choose_filename(
                identity,
                pdf_url,
            )

            target = RAW_DIR / filename

            duplicate_of = seen_pdf_hashes.get(digest)

            if duplicate_of is None:
                target.write_bytes(pdf_body)
                seen_pdf_hashes[digest] = str(
                    target.relative_to(REPO_ROOT)
                )
                local_path = str(
                    target.relative_to(REPO_ROOT)
                )
                result_status = "DOWNLOADED_OFFICIAL"
            else:
                local_path = duplicate_of
                result_status = "DUPLICATE_OFFICIAL_CONTENT"

            results.append(
                DownloadResult(
                    discovery_source=link.source_page,
                    discovery_page_url=link.source_page_url,
                    anchor_text=link.anchor_text,
                    discovered_url=link.url,
                    resolved_pdf_url=pdf_url,
                    local_path=local_path,
                    http_status=str(status),
                    bytes=len(pdf_body),
                    sha256=digest,
                    pdf_signature_ok=signature_ok,
                    status=result_status,
                    error="",
                )
            )

            print(f"Resolved PDF: {pdf_url}")
            print(f"Bytes:        {len(pdf_body):,}")
            print(f"SHA-256:      {digest}")
            print(f"PDF header:   {'PASS' if signature_ok else 'FAIL'}")
            print(f"Status:       {result_status}")
            print(f"Local:        {local_path}")

        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"

            results.append(
                DownloadResult(
                    discovery_source=link.source_page,
                    discovery_page_url=link.source_page_url,
                    anchor_text=link.anchor_text,
                    discovered_url=link.url,
                    resolved_pdf_url="",
                    local_path="",
                    http_status="",
                    bytes=0,
                    sha256="",
                    pdf_signature_ok=False,
                    status="ERROR",
                    error=message,
                )
            )

            print(f"ERROR: {message}")

        print()

        # Be polite to CMS.
        time.sleep(0.25)

    write_manifest(results)

    successful = [
        result
        for result in results
        if result.status in {
            "DOWNLOADED_OFFICIAL",
            "DUPLICATE_OFFICIAL_CONTENT",
        }
    ]

    unique_hashes = {
        result.sha256
        for result in successful
        if result.sha256
    }

    bad_pdf = [
        result
        for result in successful
        if not result.pdf_signature_ok
    ]

    errors = [
        result
        for result in results
        if result.status == "ERROR"
    ]

    checks: list[tuple[str, bool, str]] = []

    checks.append(
        (
            "Official CMS discovery pages resolved",
            len(discovery_errors) == 0,
            (
                f"{len(CMS_DISCOVERY_PAGES) - len(discovery_errors)}"
                f"/{len(CMS_DISCOVERY_PAGES)} pages"
            ),
        )
    )

    checks.append(
        (
            "Washington MFFS savings-report candidates discovered",
            len(candidates) > 0,
            f"{len(candidates)} candidate links",
        )
    )

    checks.append(
        (
            "All discovered candidates resolved without error",
            len(errors) == 0,
            f"{len(successful)}/{len(results)} resolved",
        )
    )

    checks.append(
        (
            "All resolved sources are valid PDF files",
            len(bad_pdf) == 0 and len(successful) > 0,
            (
                f"{len(successful) - len(bad_pdf)}"
                f"/{len(successful)} valid PDFs"
            ),
        )
    )

    checks.append(
        (
            "SHA-256 recorded for every resolved source",
            (
                len(successful) > 0
                and all(result.sha256 for result in successful)
            ),
            (
                f"{sum(bool(result.sha256) for result in successful)}"
                f"/{len(successful)} hashed"
            ),
        )
    )

    checks.append(
        (
            "At least six unique official actuarial reports preserved",
            len(unique_hashes) >= 6,
            f"{len(unique_hashes)} unique PDF hashes",
        )
    )

    overall_pass = all(passed for _, passed, _ in checks)

    report_lines: list[str] = []

    report_lines.append("=" * 100)
    report_lines.append(
        "CMS WASHINGTON MFFS MEDICARE SAVINGS REPORT "
        "ACQUISITION v0.1"
    )
    report_lines.append("=" * 100)
    report_lines.append("")
    report_lines.append("OFFICIAL CMS SOURCES ONLY")
    report_lines.append("No database writes.")
    report_lines.append("No payment reconstruction.")
    report_lines.append("No ledger inclusion.")
    report_lines.append("")

    report_lines.append("SUMMARY")
    report_lines.append("-" * 100)
    report_lines.append(
        f"Discovery pages:             {len(CMS_DISCOVERY_PAGES)}"
    )
    report_lines.append(
        f"Candidate links:             {len(candidates)}"
    )
    report_lines.append(
        f"Resolved candidate links:    {len(successful)}"
    )
    report_lines.append(
        f"Unique official PDF hashes:  {len(unique_hashes)}"
    )
    report_lines.append(
        f"Resolution errors:           {len(errors)}"
    )
    report_lines.append("")

    report_lines.append("CHECKS")
    report_lines.append("-" * 100)

    for name, passed, detail in checks:
        report_lines.append(
            f"{'PASS' if passed else 'FAIL'} | {name} | {detail}"
        )

    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append(
        "OVERALL SOURCE ACQUISITION: "
        + ("PASS" if overall_pass else "FAIL")
    )
    report_lines.append("=" * 100)
    report_lines.append("")

    report_lines.append("Boundary:")
    report_lines.append(
        "  Acquisition establishes preservation of official CMS "
        "Washington MFFS savings-report sources."
    )
    report_lines.append(
        "  It does NOT establish Washington performance-payment dollars."
    )
    report_lines.append(
        "  It does NOT establish additivity to Original Medicare/FFS."
    )
    report_lines.append(
        "  It does NOT authorize ledger inclusion."
    )
    report_lines.append("")

    if discovery_errors:
        report_lines.append("DISCOVERY ERRORS")
        report_lines.append("-" * 100)
        report_lines.extend(discovery_errors)
        report_lines.append("")

    if errors:
        report_lines.append("RESOLUTION ERRORS")
        report_lines.append("-" * 100)
        for result in errors:
            report_lines.append(
                f"{result.anchor_text} | {result.error}"
            )
        report_lines.append("")

    report = "\n".join(report_lines)

    REPORT_TXT.write_text(
        report,
        encoding="utf-8",
    )

    print(report)

    print("Evidence written:")
    print(f"  {DISCOVERY_CSV.relative_to(REPO_ROOT)}")
    print(f"  {MANIFEST_CSV.relative_to(REPO_ROOT)}")
    print(f"  {REPORT_TXT.relative_to(REPO_ROOT)}")
    print()

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
