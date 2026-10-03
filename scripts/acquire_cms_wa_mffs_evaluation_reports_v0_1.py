"""
acquire_cms_wa_mffs_evaluation_reports_v0_1.py

WCFFBP
CMS Washington MFFS Evaluation Report Acquisition v0.1

Purpose
-------
Acquire the official CMS Washington MFFS evaluation-report evidence
needed to investigate retrospective performance payments.

Required core universe:
    First Evaluation Report
    Second Evaluation Report
    Third Evaluation Report
    Fourth Evaluation Report
    Fifth Evaluation Report

Supplemental:
    Findings-at-a-Glance documents when officially linked.

Official CMS sources only.
No database writes.
No payment reconstruction.
No inferred performance payments.
No ledger inclusion.
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
import ssl
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
    / "evaluation_reports"
)

SOURCE_DIR = RAW_DIR / "v0_1"

VALIDATION_DIR = (
    RAW_DIR
    / "validation"
    / "source_acquisition_v0_1"
)

DISCOVERY_CSV = (
    VALIDATION_DIR
    / "cms_wa_mffs_evaluation_report_discovery_v0_1.csv"
)

MANIFEST_CSV = (
    VALIDATION_DIR
    / "cms_wa_mffs_evaluation_report_acquisition_manifest_v0_1.csv"
)

CHECKS_CSV = (
    VALIDATION_DIR
    / "cms_wa_mffs_evaluation_report_acquisition_checks_v0_1.csv"
)

REPORT_TXT = (
    VALIDATION_DIR
    / "cms_wa_mffs_evaluation_report_acquisition_report_v0_1.txt"
)


CMS_PAGES = [
    (
        "EVALUATIONS",
        "https://www.cms.gov/medicaid-chip/"
        "medicare-coordination/financial-alignment/evaluations",
    ),
    (
        "WASHINGTON",
        "https://www.cms.gov/medicaid-chip/"
        "medicare-coordination/financial-alignment/wa",
    ),
    (
        "FINANCIAL_ALIGNMENT",
        "https://www.cms.gov/priorities/innovation/"
        "innovation-models/financial-alignment",
    ),
]


USER_AGENT = (
    "Mozilla/5.0 WCFFBP-CMS-source-acquisition/0.1 "
    "(research; reproducible public-data acquisition)"
)


@dataclass(frozen=True)
class RequiredReport:
    slot: str
    ordinal_word: str
    ordinal_number: int


REQUIRED_REPORTS = [
    RequiredReport("EVAL_01_FIRST", "first", 1),
    RequiredReport("EVAL_02_SECOND", "second", 2),
    RequiredReport("EVAL_03_THIRD", "third", 3),
    RequiredReport("EVAL_04_FOURTH", "fourth", 4),
    RequiredReport("EVAL_05_FIFTH", "fifth", 5),
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
    ordinal_number: int
    discovery_source: str
    discovery_page_url: str
    anchor_text: str
    discovered_url: str
    resolved_url: str
    local_path: str
    bytes: int
    sha256: str
    pdf_signature_ok: bool
    text_extraction_ok: bool
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

    with urlopen(
        req,
        timeout=timeout,
        context=ssl.create_default_context(),
    ) as response:
        return (
            response.read(),
            response.geturl(),
            int(getattr(response, "status", 200)),
        )


def extract_links(
    page_name: str,
    page_url: str,
    body: bytes,
) -> list[Link]:
    text = body.decode(
        "utf-8",
        errors="replace",
    )

    pattern = re.compile(
        r"<a\b[^>]*?\bhref\s*=\s*"
        r"(?P<q>['\"])(?P<href>.*?)(?P=q)"
        r"[^>]*>(?P<text>.*?)</a>",
        re.IGNORECASE | re.DOTALL,
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

        output.append(
            Link(
                source_page=page_name,
                source_page_url=page_url,
                anchor_text=normalize_space(anchor),
                url=urljoin(page_url, href),
            )
        )

    return output


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def candidate_score(
    report: RequiredReport,
    link: Link,
) -> int:
    text = normalize_space(
        link.anchor_text + " " + link.url
    ).lower()

    score = 0

    if "washington" in text or "wa-" in text:
        score += 15

    if "evaluation" in text or "eval" in text:
        score += 15

    if "report" in text:
        score += 5

    if "managed fee" in text or "mffs" in text:
        score += 5

    ordinal = report.ordinal_word

    if re.search(
        rf"\b{ordinal}\b",
        text,
    ):
        score += 80

    compact_tokens = {
        1: ["firsteval", "first-eval", "evalreport1"],
        2: ["secondeval", "second-eval", "evalreport2"],
        3: ["thirdeval", "third-eval", "evalreport3"],
        4: ["fourtheval", "fourth-eval", "evalreport4"],
        5: ["fiftheval", "fifth-eval", "evalreport5"],
    }

    if any(
        token in text
        for token in compact_tokens[
            report.ordinal_number
        ]
    ):
        score += 80

    return score


def discover_candidates(
    links: list[Link],
) -> list[Candidate]:
    output: list[Candidate] = []

    for report in REQUIRED_REPORTS:
        for link in links:
            score = candidate_score(
                report,
                link,
            )

            if score >= 80:
                output.append(
                    Candidate(
                        slot=report.slot,
                        source_page=link.source_page,
                        source_page_url=link.source_page_url,
                        anchor_text=link.anchor_text,
                        discovered_url=link.url,
                        score=score,
                    )
                )

    return output


def cms_pdf_links(
    base_url: str,
    body: bytes,
) -> list[str]:
    text = body.decode(
        "utf-8",
        errors="replace",
    )

    hrefs = re.findall(
        r"""href\s*=\s*["']([^"']+)["']""",
        text,
        re.IGNORECASE,
    )

    output: list[str] = []

    for href in hrefs:
        url = urljoin(
            base_url,
            html.unescape(href).strip(),
        )

        if ".pdf" not in url.lower():
            continue

        if "cms.gov" not in urlparse(
            url
        ).netloc.lower():
            continue

        output.append(url)

    return list(dict.fromkeys(output))


def pdf_url_score(
    report: RequiredReport,
    url: str,
) -> int:
    low = url.lower()

    score = 0

    if "wa" in low:
        score += 5

    if "eval" in low:
        score += 10

    tokens = {
        1: [
            "first",
            "evalreport1",
            "firsteval",
        ],
        2: [
            "second",
            "evalreport2",
            "secondeval",
        ],
        3: [
            "third",
            "evalreport3",
            "thirdeval",
        ],
        4: [
            "fourth",
            "evalreport4",
            "fourtheval",
        ],
        5: [
            "fifth",
            "evalreport5",
            "fiftheval",
        ],
    }

    if any(
        token in low
        for token in tokens[
            report.ordinal_number
        ]
    ):
        score += 50

    return score


def resolve_candidate(
    report: RequiredReport,
    candidate: Candidate,
) -> tuple[bytes, str]:
    body, final_url, _ = request_bytes(
        candidate.discovered_url
    )

    if is_pdf(body):
        return body, final_url

    links = cms_pdf_links(
        final_url,
        body,
    )

    ranked = sorted(
        links,
        key=lambda url: (
            pdf_url_score(report, url),
            url,
        ),
        reverse=True,
    )

    viable = [
        url
        for url in ranked
        if pdf_url_score(report, url) >= 50
    ]

    if not viable:
        raise RuntimeError(
            "Landing page contained no PDF "
            f"matching {report.slot}"
        )

    errors: list[str] = []

    for url in viable:
        try:
            pdf, resolved, _ = request_bytes(url)

            if is_pdf(pdf):
                return pdf, resolved

            errors.append(
                f"{url}: not a PDF"
            )

        except Exception as exc:
            errors.append(
                f"{url}: "
                f"{type(exc).__name__}: {exc}"
            )

    raise RuntimeError(
        "No viable PDF resolved: "
        + " | ".join(errors[:5])
    )


def extract_pdf_text(
    data: bytes,
    slot: str,
    max_pages: int = 12,
) -> str:
    temp_dir = VALIDATION_DIR / "_tmp"
    temp_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = temp_dir / f"{slot}.pdf"
    path.write_bytes(data)

    reader = PdfReader(str(path))

    pieces: list[str] = []

    for page in reader.pages[:max_pages]:
        pieces.append(
            page.extract_text() or ""
        )

    return "\n".join(pieces)


def identity_ok(
    report: RequiredReport,
    text: str,
) -> bool:
    low = normalize_space(text).lower()

    if "washington" not in low:
        return False

    if "evaluation" not in low:
        return False

    ordinal_patterns = {
        1: [
            r"\bfirst\s+(?:annual\s+)?(?:evaluation\s+)?report\b",
            r"\bfirst\s+annual\s+report\b",
        ],
        2: [
            r"\bsecond\s+evaluation\s+report\b",
        ],
        3: [
            r"\bthird\s+evaluation\s+report\b",
        ],
        4: [
            r"\bfourth\s+evaluation\s+report\b",
        ],
        5: [
            r"\bfifth\s+evaluation\s+report\b",
        ],
    }

    return any(
        re.search(
            pattern,
            low,
            re.IGNORECASE,
        )
        for pattern in ordinal_patterns[
            report.ordinal_number
        ]
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_csv(
    path: Path,
    fields: list[str],
    rows: list[dict],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 100)
    print(
        "CMS WASHINGTON MFFS EVALUATION REPORT "
        "ACQUISITION v0.1"
    )
    print("=" * 100)
    print()
    print("Official CMS sources only.")
    print("Five required evaluation reports.")
    print("Internal PDF identity validation required.")
    print("No database writes.")
    print("No payment reconstruction.")
    print("No ledger inclusion.")
    print()

    all_links: list[Link] = []
    page_errors: list[str] = []

    for name, url in CMS_PAGES:
        print(f"Discovering: {name}")
        print(f"  {url}")

        try:
            body, final_url, status = request_bytes(url)

            links = extract_links(
                name,
                final_url,
                body,
            )

            all_links.extend(links)

            print(f"  HTTP {status}")
            print(f"  Links: {len(links):,}")

        except Exception as exc:
            message = (
                f"{name}: "
                f"{type(exc).__name__}: {exc}"
            )
            page_errors.append(message)
            print(f"  ERROR: {message}")

        print()

    candidates = discover_candidates(
        all_links
    )

    discovery_rows = [
        {
            "slot": c.slot,
            "source_page": c.source_page,
            "source_page_url": c.source_page_url,
            "anchor_text": c.anchor_text,
            "discovered_url": c.discovered_url,
            "score": c.score,
        }
        for c in candidates
    ]

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
            key=lambda c: c.score,
            reverse=True,
        )

    results: list[Result] = []

    for report in REQUIRED_REPORTS:
        print("-" * 100)
        print(report.slot)
        print("-" * 100)

        candidates_for_slot = by_slot[
            report.slot
        ]

        if not candidates_for_slot:
            print("FAIL: no candidate discovered")
            print()

            results.append(
                Result(
                    slot=report.slot,
                    ordinal_number=(
                        report.ordinal_number
                    ),
                    discovery_source="",
                    discovery_page_url="",
                    anchor_text="",
                    discovered_url="",
                    resolved_url="",
                    local_path="",
                    bytes=0,
                    sha256="",
                    pdf_signature_ok=False,
                    text_extraction_ok=False,
                    internal_identity_ok=False,
                    status="NO_CANDIDATE",
                    error="No candidate discovered",
                )
            )

            continue

        success = False
        errors: list[str] = []

        for candidate in candidates_for_slot:
            print(
                f"Trying {candidate.source_page}: "
                f"{candidate.anchor_text}"
            )
            print(
                f"  {candidate.discovered_url}"
            )

            try:
                pdf, resolved_url = (
                    resolve_candidate(
                        report,
                        candidate,
                    )
                )

                text = extract_pdf_text(
                    pdf,
                    report.slot,
                )

                text_ok = bool(
                    normalize_space(text)
                )

                internal_ok = identity_ok(
                    report,
                    text,
                )

                if not internal_ok:
                    raise RuntimeError(
                        "Internal PDF identity "
                        f"does not match {report.slot}"
                    )

                digest = sha256_bytes(pdf)

                target = (
                    SOURCE_DIR
                    / (
                        f"{report.slot}__"
                        "cms_wa_mffs_evaluation_report.pdf"
                    )
                )

                target.write_bytes(pdf)

                relative = str(
                    target.relative_to(
                        REPO_ROOT
                    )
                )

                results.append(
                    Result(
                        slot=report.slot,
                        ordinal_number=(
                            report.ordinal_number
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
                        resolved_url=resolved_url,
                        local_path=relative,
                        bytes=len(pdf),
                        sha256=digest,
                        pdf_signature_ok=True,
                        text_extraction_ok=text_ok,
                        internal_identity_ok=True,
                        status="CERTIFIED_SOURCE",
                        error="",
                    )
                )

                print(
                    f"  Resolved: {resolved_url}"
                )
                print(
                    f"  Bytes:    {len(pdf):,}"
                )
                print(
                    f"  SHA-256:  {digest}"
                )
                print("  PDF:      PASS")
                print("  Identity: PASS")
                print(
                    f"  Saved:    {relative}"
                )
                print()

                success = True
                break

            except Exception as exc:
                message = (
                    f"{candidate.source_page} | "
                    f"{candidate.discovered_url} | "
                    f"{type(exc).__name__}: {exc}"
                )

                errors.append(message)

                print(
                    "  Candidate rejected: "
                    f"{type(exc).__name__}: {exc}"
                )
                print()

        if not success:
            results.append(
                Result(
                    slot=report.slot,
                    ordinal_number=(
                        report.ordinal_number
                    ),
                    discovery_source="",
                    discovery_page_url="",
                    anchor_text="",
                    discovered_url="",
                    resolved_url="",
                    local_path="",
                    bytes=0,
                    sha256="",
                    pdf_signature_ok=False,
                    text_extraction_ok=False,
                    internal_identity_ok=False,
                    status="UNRESOLVED",
                    error=" || ".join(errors),
                )
            )

    fields = list(
        Result.__dataclass_fields__.keys()
    )

    write_csv(
        MANIFEST_CSV,
        fields,
        [
            {
                field: getattr(result, field)
                for field in fields
            }
            for result in results
        ],
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

    checks = [
        (
            "At least one official CMS discovery page resolved",
            len(page_errors) < len(CMS_PAGES),
            (
                f"{len(CMS_PAGES) - len(page_errors)}"
                f"/{len(CMS_PAGES)} pages"
            ),
        ),
        (
            "Five required evaluation-report slots defined",
            len(REQUIRED_REPORTS) == 5,
            f"{len(REQUIRED_REPORTS)} slots",
        ),
        (
            "All five evaluation reports certified",
            len(certified) == 5,
            f"{len(certified)}/5 reports",
        ),
        (
            "All certified sources are PDFs",
            (
                len(certified) == 5
                and all(
                    r.pdf_signature_ok
                    for r in certified
                )
            ),
            (
                f"{sum(r.pdf_signature_ok for r in certified)}"
                f"/{len(certified)}"
            ),
        ),
        (
            "All certified PDFs yielded text",
            (
                len(certified) == 5
                and all(
                    r.text_extraction_ok
                    for r in certified
                )
            ),
            (
                f"{sum(r.text_extraction_ok for r in certified)}"
                f"/{len(certified)}"
            ),
        ),
        (
            "All internal identities match",
            (
                len(certified) == 5
                and all(
                    r.internal_identity_ok
                    for r in certified
                )
            ),
            (
                f"{sum(r.internal_identity_ok for r in certified)}"
                f"/{len(certified)}"
            ),
        ),
        (
            "Five distinct SHA-256 hashes",
            (
                len(certified) == 5
                and len(set(hashes)) == 5
            ),
            (
                f"{len(set(hashes))}"
                f"/{len(hashes)} unique"
            ),
        ),
    ]

    write_csv(
        CHECKS_CSV,
        [
            "check",
            "status",
            "detail",
        ],
        [
            {
                "check": name,
                "status": (
                    "PASS"
                    if passed
                    else "FAIL"
                ),
                "detail": detail,
            }
            for name, passed, detail
            in checks
        ],
    )

    overall = all(
        passed
        for _, passed, _ in checks
    )

    lines: list[str] = []

    lines.append("=" * 100)
    lines.append(
        "CMS WASHINGTON MFFS EVALUATION REPORT "
        "ACQUISITION v0.1"
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("SOURCE UNIVERSE")
    lines.append("-" * 100)

    for result in results:
        lines.append(
            f"{result.slot:<20} "
            f"{result.status:<18} "
            f"{result.sha256[:16]}"
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
        "OVERALL EVALUATION REPORT "
        "ACQUISITION v0.1: "
        + (
            "PASS"
            if overall
            else "FAIL"
        )
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("Boundary:")
    lines.append(
        "  Acquisition establishes preservation "
        "and identity of the five official CMS "
        "Washington evaluation reports."
    )
    lines.append(
        "  It does NOT establish a performance-"
        "payment dollar series."
    )
    lines.append(
        "  It does NOT distinguish determined "
        "payments from cash remittances."
    )
    lines.append(
        "  It does NOT establish additivity to "
        "Original Medicare/FFS."
    )
    lines.append(
        "  It does NOT authorize ledger inclusion."
    )
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

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
