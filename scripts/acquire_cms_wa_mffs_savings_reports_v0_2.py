"""
acquire_cms_wa_mffs_savings_reports_v0_2.py

WCFFBP
CMS Washington Managed Fee-for-Service (MFFS)
Medicare Savings / Actuarial Report Acquisition v0.2

Purpose
-------
Acquire and certify the seven-report Washington MFFS Medicare
savings-report chain.

v0.2 changes
------------
* Seven required semantic report slots are explicit.
* Uses official CMS pages only.
* Discovers links from BOTH the Financial Alignment Initiative page
  and Washington-specific page.
* Resolves each required report independently.
* Does NOT choose an arbitrary PDF from a generic landing page.
* Validates downloaded PDF identity from extracted PDF text.
* Requires CMS catalog identity, PDF identity, and local identity to agree.
* Requires seven distinct SHA-256 hashes.
* Preserves v0.1 unchanged.
* No database writes.
* No payment reconstruction.
* No ledger inclusion.

Important
---------
This is source acquisition and source-identity certification only.
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
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader


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

V02_DIR = RAW_DIR / "v0_2"

VALIDATION_DIR = (
    RAW_DIR
    / "validation"
    / "source_acquisition_v0_2"
)

DISCOVERY_CSV = (
    VALIDATION_DIR
    / "cms_wa_mffs_savings_report_discovery_v0_2.csv"
)

MANIFEST_CSV = (
    VALIDATION_DIR
    / "cms_wa_mffs_savings_report_acquisition_manifest_v0_2.csv"
)

CHECKS_CSV = (
    VALIDATION_DIR
    / "cms_wa_mffs_savings_report_acquisition_checks_v0_2.csv"
)

REPORT_TXT = (
    VALIDATION_DIR
    / "cms_wa_mffs_savings_report_acquisition_report_v0_2.txt"
)


CMS_PAGES = [
    (
        "FINANCIAL_ALIGNMENT",
        "https://www.cms.gov/priorities/innovation/"
        "innovation-models/financial-alignment",
    ),
    (
        "WASHINGTON",
        "https://www.cms.gov/medicaid-chip/"
        "medicare-coordination/financial-alignment/wa",
    ),
    (
        "EVALUATIONS",
        "https://www.cms.gov/medicaid-chip/"
        "medicare-coordination/financial-alignment/evaluations",
    ),
]


USER_AGENT = (
    "Mozilla/5.0 WCFFBP-CMS-source-acquisition/0.2 "
    "(research; reproducible public-data acquisition)"
)


@dataclass(frozen=True)
class RequiredReport:
    slot: str
    final_dy: int
    preliminary_dy: int


REQUIRED_REPORTS = [
    RequiredReport("DY1_FINAL_DY2_PRELIM", 1, 2),
    RequiredReport("DY2_FINAL_DY3_PRELIM", 2, 3),
    RequiredReport("DY3_FINAL_DY4_PRELIM", 3, 4),
    RequiredReport("DY4_FINAL_DY5_PRELIM", 4, 5),
    RequiredReport("DY5_FINAL_DY6_PRELIM", 5, 6),
    RequiredReport("DY6_FINAL_DY7_PRELIM", 6, 7),
    RequiredReport("DY7_FINAL_DY8_PRELIM", 7, 8),
]


@dataclass
class Link:
    source_page: str
    source_page_url: str
    anchor_text: str
    url: str


@dataclass
class Candidate:
    slot: str
    source_page: str
    source_page_url: str
    anchor_text: str
    discovered_url: str
    score: int


@dataclass
class Result:
    slot: str
    expected_final_dy: int
    expected_preliminary_dy: int
    discovery_source: str
    discovery_page_url: str
    anchor_text: str
    discovered_url: str
    resolved_url: str
    local_path: str
    http_status: str
    bytes: int
    sha256: str
    pdf_signature_ok: bool
    text_extraction_ok: bool
    internal_final_dy: str
    internal_preliminary_dy: str
    internal_identity_ok: bool
    status: str
    error: str


def normalize_space(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        html.unescape(value or ""),
    ).strip()


def request_bytes(
    url: str,
    timeout: int = 90,
) -> tuple[bytes, str, int]:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/pdf,application/octet-stream;"
                "q=0.9,*/*;q=0.8"
            ),
        },
    )

    context = ssl.create_default_context()

    with urlopen(
        req,
        timeout=timeout,
        context=context,
    ) as response:
        body = response.read()
        final_url = response.geturl()
        status = int(getattr(response, "status", 200))

    return body, final_url, status


def extract_links(
    page_name: str,
    page_url: str,
    body: bytes,
) -> list[Link]:
    text = body.decode("utf-8", errors="replace")

    pattern = re.compile(
        r"<a\b[^>]*?\bhref\s*=\s*"
        r"(?P<quote>['\"])(?P<href>.*?)(?P=quote)"
        r"[^>]*>(?P<text>.*?)</a>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    output: list[Link] = []

    for match in pattern.finditer(text):
        href = html.unescape(
            match.group("href")
        ).strip()

        if not href:
            continue

        anchor = re.sub(
            r"<[^>]+>",
            " ",
            match.group("text"),
        )

        anchor = normalize_space(anchor)

        output.append(
            Link(
                source_page=page_name,
                source_page_url=page_url,
                anchor_text=anchor,
                url=urljoin(page_url, href),
            )
        )

    return output


def slot_match_score(
    report: RequiredReport,
    link: Link,
) -> int:
    text = normalize_space(
        link.anchor_text + " " + link.url
    ).lower()

    score = 0

    if "washington" in text or "fai-wa" in text:
        score += 10

    if "medicare" in text:
        score += 3

    if "saving" in text:
        score += 4

    if "managed fee" in text or "mffs" in text:
        score += 2

    f = report.final_dy
    p = report.preliminary_dy

    final_patterns = [
        rf"final\s+(?:demonstration\s+)?year\s+{f}\b",
        rf"(?:demonstration\s+)?year\s+{f}\s+final\b",
        rf"final\s+dy\s*{f}\b",
        rf"finalyr{f}\b",
        rf"finaldy{f}\b",
    ]

    prelim_patterns = [
        rf"preliminary\s+(?:demonstration\s+)?year\s+{p}\b",
        rf"(?:demonstration\s+)?year\s+{p}\s+preliminary\b",
        rf"prelim(?:inary)?\s+dy\s*{p}\b",
        rf"prelimyr{p}\b",
        rf"preyr{p}\b",
        rf"prelimdy{p}\b",
    ]

    final_hit = any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in final_patterns
    )

    prelim_hit = any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in prelim_patterns
    )

    if final_hit:
        score += 40

    if prelim_hit:
        score += 40

    if final_hit and prelim_hit:
        score += 100

    return score


def discover_candidates(
    all_links: list[Link],
) -> list[Candidate]:
    candidates: list[Candidate] = []

    for report in REQUIRED_REPORTS:
        for link in all_links:
            score = slot_match_score(report, link)

            if score >= 100:
                candidates.append(
                    Candidate(
                        slot=report.slot,
                        source_page=link.source_page,
                        source_page_url=link.source_page_url,
                        anchor_text=link.anchor_text,
                        discovered_url=link.url,
                        score=score,
                    )
                )

    return candidates


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def html_pdf_links(
    base_url: str,
    body: bytes,
) -> list[str]:
    text = body.decode("utf-8", errors="replace")

    hrefs = re.findall(
        r"""href\s*=\s*["']([^"']+)["']""",
        text,
        flags=re.IGNORECASE,
    )

    output: list[str] = []

    for href in hrefs:
        absolute = urljoin(
            base_url,
            html.unescape(href).strip(),
        )

        if ".pdf" not in absolute.lower():
            continue

        if "cms.gov" not in urlparse(
            absolute
        ).netloc.lower():
            continue

        output.append(absolute)

    return list(dict.fromkeys(output))


def url_slot_score(
    report: RequiredReport,
    url: str,
) -> int:
    low = url.lower()

    f = report.final_dy
    p = report.preliminary_dy

    score = 0

    if "wa" in low:
        score += 3

    if "fai" in low:
        score += 3

    if "saving" in low:
        score += 2

    final_tokens = [
        f"finalyr{f}",
        f"finaldy{f}",
        f"final-yr-{f}",
        f"final-dy-{f}",
        f"dy{f}",
    ]

    prelim_tokens = [
        f"prelimyr{p}",
        f"preyr{p}",
        f"prelimdy{p}",
        f"prelim-yr-{p}",
        f"prelim-dy-{p}",
        f"dy{p}",
    ]

    final_hit = any(
        token in low
        for token in final_tokens
    )

    prelim_hit = any(
        token in low
        for token in prelim_tokens
    )

    if final_hit:
        score += 20

    if prelim_hit:
        score += 20

    if final_hit and prelim_hit:
        score += 50

    return score


def resolve_candidate(
    report: RequiredReport,
    candidate: Candidate,
) -> tuple[bytes, str, int]:
    body, final_url, status = request_bytes(
        candidate.discovered_url
    )

    if is_pdf(body):
        return body, final_url, status

    pdf_links = html_pdf_links(
        final_url,
        body,
    )

    if not pdf_links:
        raise RuntimeError(
            "CMS landing page contained no CMS PDF links"
        )

    ranked = sorted(
        pdf_links,
        key=lambda url: (
            url_slot_score(report, url),
            url,
        ),
        reverse=True,
    )

    # v0.2 deliberately refuses to take an arbitrary
    # first PDF from a generic CMS page.
    positive = [
        url
        for url in ranked
        if url_slot_score(report, url) >= 40
    ]

    if not positive:
        raise RuntimeError(
            "Landing page contained PDFs, but none matched "
            f"required slot {report.slot}"
        )

    errors: list[str] = []

    for pdf_url in positive:
        try:
            pdf_body, pdf_final, pdf_status = request_bytes(
                pdf_url
            )

            if is_pdf(pdf_body):
                return (
                    pdf_body,
                    pdf_final,
                    pdf_status,
                )

            errors.append(
                f"{pdf_url}: response not PDF"
            )

        except Exception as exc:
            errors.append(
                f"{pdf_url}: "
                f"{type(exc).__name__}: {exc}"
            )

    raise RuntimeError(
        "No valid slot-matched PDF resolved: "
        + " | ".join(errors[:5])
    )


def write_temp_pdf(
    data: bytes,
    slot: str,
) -> Path:
    temp_dir = VALIDATION_DIR / "_tmp"
    temp_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = temp_dir / f"{slot}.pdf"
    path.write_bytes(data)

    return path


def extract_pdf_text(
    data: bytes,
    slot: str,
    max_pages: int = 8,
) -> str:
    temp_path = write_temp_pdf(
        data,
        slot,
    )

    reader = PdfReader(str(temp_path))

    pieces: list[str] = []

    for page in reader.pages[:max_pages]:
        text = page.extract_text() or ""
        pieces.append(text)

    return "\n".join(pieces)


def internal_identity(
    text: str,
    expected_final: int,
    expected_prelim: int,
) -> tuple[str, str, bool]:
    normalized = normalize_space(text).lower()

    f = expected_final
    p = expected_prelim

    final_patterns = [
        rf"final\s+(?:demonstration\s+)?year\s+{f}\b",
        rf"(?:demonstration\s+)?year\s+{f}\s+final\b",
        rf"demonstration\s+year\s+{f}.*?final",
        rf"year\s+{f}.*?final",
    ]

    prelim_patterns = [
        rf"preliminary\s+(?:demonstration\s+)?year\s+{p}\b",
        rf"(?:demonstration\s+)?year\s+{p}\s+preliminary\b",
        rf"demonstration\s+year\s+{p}.*?preliminary",
        rf"year\s+{p}.*?preliminary",
    ]

    final_ok = any(
        re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )
        for pattern in final_patterns
    )

    prelim_ok = any(
        re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )
        for pattern in prelim_patterns
    )

    return (
        str(f) if final_ok else "",
        str(p) if prelim_ok else "",
        final_ok and prelim_ok,
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def filename_for(report: RequiredReport) -> str:
    return (
        f"{report.slot}__"
        "cms_wa_mffs_medicare_cost_savings_report.pdf"
    )


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    V02_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 100)
    print(
        "CMS WASHINGTON MFFS MEDICARE SAVINGS REPORT "
        "ACQUISITION v0.2"
    )
    print("=" * 100)
    print()
    print("Seven-slot source universe.")
    print("Official CMS sources only.")
    print("Internal PDF identity validation required.")
    print("No database writes.")
    print("No payment reconstruction.")
    print("No ledger inclusion.")
    print()

    all_links: list[Link] = []
    page_errors: list[str] = []

    for page_name, page_url in CMS_PAGES:
        print(f"Discovering: {page_name}")
        print(f"  {page_url}")

        try:
            body, final_url, status = request_bytes(
                page_url
            )

            links = extract_links(
                page_name,
                final_url,
                body,
            )

            all_links.extend(links)

            print(f"  HTTP {status}")
            print(f"  Links: {len(links):,}")

        except Exception as exc:
            message = (
                f"{page_name}: "
                f"{type(exc).__name__}: {exc}"
            )
            page_errors.append(message)
            print(f"  ERROR: {message}")

        print()

    candidates = discover_candidates(all_links)

    discovery_rows: list[dict] = []

    for candidate in candidates:
        discovery_rows.append(
            {
                "slot": candidate.slot,
                "source_page": candidate.source_page,
                "source_page_url": candidate.source_page_url,
                "anchor_text": candidate.anchor_text,
                "discovered_url": candidate.discovered_url,
                "score": candidate.score,
            }
        )

    write_csv(
        DISCOVERY_CSV,
        [
            "slot",
            "source_page",
            "source_page_url",
            "anchor_text",
            "discovered_url",
            "score",
        ],
        discovery_rows,
    )

    by_slot: dict[str, list[Candidate]] = {
        report.slot: []
        for report in REQUIRED_REPORTS
    }

    for candidate in candidates:
        by_slot[candidate.slot].append(
            candidate
        )

    for slot in by_slot:
        by_slot[slot].sort(
            key=lambda c: (
                c.score,
                c.source_page == "FINANCIAL_ALIGNMENT",
            ),
            reverse=True,
        )

    results: list[Result] = []

    for report in REQUIRED_REPORTS:
        print("-" * 100)
        print(report.slot)
        print("-" * 100)

        slot_candidates = by_slot.get(
            report.slot,
            [],
        )

        if not slot_candidates:
            print("FAIL: no official CMS candidate discovered")
            print()

            results.append(
                Result(
                    slot=report.slot,
                    expected_final_dy=report.final_dy,
                    expected_preliminary_dy=report.preliminary_dy,
                    discovery_source="",
                    discovery_page_url="",
                    anchor_text="",
                    discovered_url="",
                    resolved_url="",
                    local_path="",
                    http_status="",
                    bytes=0,
                    sha256="",
                    pdf_signature_ok=False,
                    text_extraction_ok=False,
                    internal_final_dy="",
                    internal_preliminary_dy="",
                    internal_identity_ok=False,
                    status="NO_CANDIDATE",
                    error=(
                        "No official CMS candidate discovered "
                        "for required slot"
                    ),
                )
            )
            continue

        slot_success = False
        slot_errors: list[str] = []

        for candidate in slot_candidates:
            print(
                f"Trying {candidate.source_page}: "
                f"{candidate.anchor_text}"
            )
            print(
                f"  {candidate.discovered_url}"
            )

            try:
                pdf_body, pdf_url, status = resolve_candidate(
                    report,
                    candidate,
                )

                signature_ok = is_pdf(pdf_body)

                try:
                    pdf_text = extract_pdf_text(
                        pdf_body,
                        report.slot,
                    )
                    text_ok = bool(
                        normalize_space(pdf_text)
                    )
                except Exception as exc:
                    pdf_text = ""
                    text_ok = False
                    raise RuntimeError(
                        "PDF text extraction failed: "
                        f"{type(exc).__name__}: {exc}"
                    )

                (
                    internal_final,
                    internal_prelim,
                    identity_ok,
                ) = internal_identity(
                    pdf_text,
                    report.final_dy,
                    report.preliminary_dy,
                )

                if not identity_ok:
                    raise RuntimeError(
                        "Downloaded PDF internal identity "
                        f"does not match {report.slot}"
                    )

                digest = sha256_bytes(pdf_body)

                target = (
                    V02_DIR
                    / filename_for(report)
                )

                target.write_bytes(pdf_body)

                relative_target = str(
                    target.relative_to(REPO_ROOT)
                )

                results.append(
                    Result(
                        slot=report.slot,
                        expected_final_dy=report.final_dy,
                        expected_preliminary_dy=(
                            report.preliminary_dy
                        ),
                        discovery_source=(
                            candidate.source_page
                        ),
                        discovery_page_url=(
                            candidate.source_page_url
                        ),
                        anchor_text=(
                            candidate.anchor_text
                        ),
                        discovered_url=(
                            candidate.discovered_url
                        ),
                        resolved_url=pdf_url,
                        local_path=relative_target,
                        http_status=str(status),
                        bytes=len(pdf_body),
                        sha256=digest,
                        pdf_signature_ok=signature_ok,
                        text_extraction_ok=text_ok,
                        internal_final_dy=internal_final,
                        internal_preliminary_dy=internal_prelim,
                        internal_identity_ok=identity_ok,
                        status="CERTIFIED_SOURCE",
                        error="",
                    )
                )

                print(f"  Resolved: {pdf_url}")
                print(f"  Bytes:    {len(pdf_body):,}")
                print(f"  SHA-256:  {digest}")
                print("  PDF:      PASS")
                print("  Identity: PASS")
                print(f"  Saved:    {relative_target}")
                print()

                slot_success = True
                break

            except Exception as exc:
                message = (
                    f"{candidate.source_page} | "
                    f"{candidate.discovered_url} | "
                    f"{type(exc).__name__}: {exc}"
                )

                slot_errors.append(message)

                print(
                    f"  Candidate rejected: "
                    f"{type(exc).__name__}: {exc}"
                )
                print()

                time.sleep(0.20)

        if not slot_success:
            results.append(
                Result(
                    slot=report.slot,
                    expected_final_dy=report.final_dy,
                    expected_preliminary_dy=(
                        report.preliminary_dy
                    ),
                    discovery_source="",
                    discovery_page_url="",
                    anchor_text="",
                    discovered_url="",
                    resolved_url="",
                    local_path="",
                    http_status="",
                    bytes=0,
                    sha256="",
                    pdf_signature_ok=False,
                    text_extraction_ok=False,
                    internal_final_dy="",
                    internal_preliminary_dy="",
                    internal_identity_ok=False,
                    status="UNRESOLVED",
                    error=" || ".join(slot_errors),
                )
            )

    manifest_fields = list(
        Result.__dataclass_fields__.keys()
    )

    manifest_rows = [
        {
            field: getattr(result, field)
            for field in manifest_fields
        }
        for result in results
    ]

    write_csv(
        MANIFEST_CSV,
        manifest_fields,
        manifest_rows,
    )

    certified = [
        result
        for result in results
        if result.status == "CERTIFIED_SOURCE"
    ]

    hashes = [
        result.sha256
        for result in certified
    ]

    required_slots = {
        report.slot
        for report in REQUIRED_REPORTS
    }

    certified_slots = {
        result.slot
        for result in certified
    }

    checks: list[tuple[str, bool, str]] = []

    checks.append(
        (
            "At least one official CMS discovery page resolved",
            len(page_errors) < len(CMS_PAGES),
            (
                f"{len(CMS_PAGES) - len(page_errors)}"
                f"/{len(CMS_PAGES)} pages"
            ),
        )
    )

    checks.append(
        (
            "Seven required semantic slots defined",
            len(REQUIRED_REPORTS) == 7,
            f"{len(REQUIRED_REPORTS)} slots",
        )
    )

    checks.append(
        (
            "All seven slots discovered and certified",
            certified_slots == required_slots,
            (
                f"{len(certified_slots)}"
                f"/{len(required_slots)} slots"
            ),
        )
    )

    checks.append(
        (
            "All certified files have PDF signatures",
            (
                len(certified) == 7
                and all(
                    result.pdf_signature_ok
                    for result in certified
                )
            ),
            (
                f"{sum(r.pdf_signature_ok for r in certified)}"
                f"/{len(certified)}"
            ),
        )
    )

    checks.append(
        (
            "All certified PDFs yielded extractable text",
            (
                len(certified) == 7
                and all(
                    result.text_extraction_ok
                    for result in certified
                )
            ),
            (
                f"{sum(r.text_extraction_ok for r in certified)}"
                f"/{len(certified)}"
            ),
        )
    )

    checks.append(
        (
            "All internal PDF identities match required slots",
            (
                len(certified) == 7
                and all(
                    result.internal_identity_ok
                    for result in certified
                )
            ),
            (
                f"{sum(r.internal_identity_ok for r in certified)}"
                f"/{len(certified)}"
            ),
        )
    )

    checks.append(
        (
            "Seven distinct SHA-256 hashes",
            (
                len(certified) == 7
                and len(set(hashes)) == 7
            ),
            (
                f"{len(set(hashes))}"
                f"/{len(hashes)} unique"
            ),
        )
    )

    checks.append(
        (
            "Every certified source has nonzero bytes",
            (
                len(certified) == 7
                and all(
                    result.bytes > 0
                    for result in certified
                )
            ),
            (
                f"{sum(r.bytes > 0 for r in certified)}"
                f"/{len(certified)}"
            ),
        )
    )

    checks_rows = [
        {
            "check": name,
            "status": (
                "PASS"
                if passed
                else "FAIL"
            ),
            "detail": detail,
        }
        for name, passed, detail in checks
    ]

    write_csv(
        CHECKS_CSV,
        [
            "check",
            "status",
            "detail",
        ],
        checks_rows,
    )

    overall_pass = all(
        passed
        for _, passed, _ in checks
    )

    lines: list[str] = []

    lines.append("=" * 100)
    lines.append(
        "CMS WASHINGTON MFFS MEDICARE SAVINGS REPORT "
        "ACQUISITION v0.2"
    )
    lines.append("=" * 100)
    lines.append("")
    lines.append(
        "Seven-slot source universe."
    )
    lines.append(
        "Official CMS sources only."
    )
    lines.append(
        "Internal PDF identity validation required."
    )
    lines.append(
        "No database writes."
    )
    lines.append(
        "No payment reconstruction."
    )
    lines.append(
        "No ledger inclusion."
    )
    lines.append("")

    lines.append("SOURCE UNIVERSE")
    lines.append("-" * 100)

    for report in REQUIRED_REPORTS:
        result = next(
            (
                r
                for r in results
                if r.slot == report.slot
            ),
            None,
        )

        if result is None:
            status = "MISSING"
            digest = ""
        else:
            status = result.status
            digest = result.sha256[:16]

        lines.append(
            f"{report.slot:<24} "
            f"{status:<18} "
            f"{digest}"
        )

    lines.append("")
    lines.append("CHECKS")
    lines.append("-" * 100)

    for name, passed, detail in checks:
        lines.append(
            f"{'PASS' if passed else 'FAIL'} | "
            f"{name} | {detail}"
        )

    lines.append("")
    lines.append("=" * 100)
    lines.append(
        "OVERALL SOURCE ACQUISITION v0.2: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("Certified boundary:")
    lines.append(
        "  PASS establishes a complete seven-slot "
        "official CMS actuarial-report chain from "
        "DY1-final/DY2-preliminary through "
        "DY7-final/DY8-preliminary."
    )
    lines.append(
        "  PASS establishes catalog-to-document "
        "identity for the preserved PDFs."
    )
    lines.append(
        "  It does NOT establish performance-payment "
        "amounts."
    )
    lines.append(
        "  It does NOT establish payment timing."
    )
    lines.append(
        "  It does NOT establish additivity to "
        "Original Medicare/FFS."
    )
    lines.append(
        "  It does NOT authorize ledger inclusion."
    )
    lines.append("")

    unresolved = [
        result
        for result in results
        if result.status != "CERTIFIED_SOURCE"
    ]

    if unresolved:
        lines.append("UNRESOLVED SLOTS")
        lines.append("-" * 100)

        for result in unresolved:
            lines.append(
                f"{result.slot}: {result.error}"
            )

        lines.append("")

    if page_errors:
        lines.append(
            "DISCOVERY PAGE WARNINGS"
        )
        lines.append("-" * 100)
        lines.extend(page_errors)
        lines.append("")

    report_text = "\n".join(lines)

    REPORT_TXT.write_text(
        report_text,
        encoding="utf-8",
    )

    print()
    print(report_text)

    print("Evidence written:")
    print(
        f"  {DISCOVERY_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"  {MANIFEST_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"  {CHECKS_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"  {REPORT_TXT.relative_to(REPO_ROOT)}"
    )
    print()

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
