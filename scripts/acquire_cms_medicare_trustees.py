#!/usr/bin/env python3
"""
Acquire official CMS Medicare Trustees source artifacts, vintages 2015-2026 (v0.2).

WCFFBP purpose
--------------
Preserve an independent CMS actuarial control family for later Medicare
Advantage / Part C reconciliation.

This acquisition stage:
  * discovers links from official CMS Trustees pages;
  * downloads each annual Medicare Trustees Report (PDF);
  * downloads Expanded/Supplementary Tables ZIPs when CMS publishes them;
  * preserves source bytes unchanged;
  * records SHA-256, size, URL, retrieval time, and discovery page;
  * inventories ZIP members;
  * makes NO payment extraction;
  * makes NO actual/projected classification;
  * makes NO reconciliation;
  * makes NO database writes.

Run from repository root:
    python scripts/acquire_cms_medicare_trustees.py
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees"
REPORT_DIR = BASE / "reports"
TABLE_DIR = BASE / "expanded_tables"
VALIDATION_DIR = BASE / "validation"

YEARS = list(range(2015, 2027))

DISCOVERY_PAGES = [
    "https://www.cms.gov/data-research/statistics-trends-and-reports/trustees-report-trust-funds",
    "https://www.cms.gov/data-research/statistics-trends-and-reports/trustees-report-trust-funds/trustees-reports-current-and-prior",
    "https://www.cms.gov/data-research/statistics-trends-and-reports/trustees-report-trust-funds/trustees-reports-current-and-prior/2021-2025",
    # Verified legacy CMS archive pages:
    "https://www.cms.gov/research-statistics-data-and-systems/statistics-trends-and-reports/reportstrustfunds/trustees-reports-items/2016-2019",
    "https://www.cms.gov/research-statistics-data-and-systems/statistics-trends-and-reports/reportstrustfunds/trustees-reports-items/2012-2015",
]

USER_AGENT = "WCFFBP-CMS-Medicare-Trustees-Acquisition/0.2"
TIMEOUT = 120

HREF_RE = re.compile(
    r"""<a\b[^>]*?\bhref\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>]+))[^>]*>(.*?)</a>""",
    re.I | re.S,
)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    for d in (REPORT_DIR, TABLE_DIR, VALIDATION_DIR):
        d.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def request_bytes(url: str) -> tuple[bytes, dict[str, str], str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = resp.read()
        headers = {k.lower(): v for k, v in resp.headers.items()}
        final_url = resp.geturl()
    return data, headers, final_url


def fetch_html(url: str) -> str:
    data, _, _ = request_bytes(url)
    return data.decode("utf-8", errors="replace")


def clean_text(raw: str) -> str:
    return SPACE_RE.sub(" ", html.unescape(TAG_RE.sub(" ", raw))).strip()


def extract_links(page_url: str, page_html: str) -> list[dict[str, str]]:
    links = []
    for m in HREF_RE.finditer(page_html):
        href = m.group(1) or m.group(2) or m.group(3) or ""
        text = clean_text(m.group(4))
        href = html.unescape(href.strip())
        if not href:
            continue
        links.append(
            {
                "discovery_page": page_url,
                "anchor_text": text,
                "url": urllib.parse.urljoin(page_url, href),
            }
        )
    return links


def classify_link(link: dict[str, str]) -> tuple[int | None, str | None]:
    text = link["anchor_text"]
    url = link["url"]
    combined = f"{text} {url}".lower()

    year = None
    for y in YEARS:
        if str(y) in combined:
            year = y
            break
    if year is None:
        return None, None

    # Annual report links can resolve to CMS /oact/tr/YYYY pages which CMS serves
    # as the official PDF content, so do not require ".pdf" in the URL.
    if "medicare trustees report" in text.lower():
        return year, "REPORT"

    if (
        ("expanded" in combined and "supplement" in combined)
        or ("supplementary" in combined and ("table" in combined or "figure" in combined))
    ):
        return year, "EXPANDED_TABLES"

    return None, None


def discover() -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    all_links: list[dict[str, str]] = []
    page_status: list[dict[str, Any]] = []

    for page in DISCOVERY_PAGES:
        try:
            body = fetch_html(page)
            links = extract_links(page, body)
            all_links.extend(links)
            page_status.append(
                {
                    "discovery_page": page,
                    "status": "PASS",
                    "links_found": len(links),
                    "error": "",
                }
            )
        except Exception as exc:
            page_status.append(
                {
                    "discovery_page": page,
                    "status": "FAIL",
                    "links_found": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    candidates: dict[tuple[int, str], list[dict[str, str]]] = {}
    for link in all_links:
        year, kind = classify_link(link)
        if year is not None and kind is not None:
            candidates.setdefault((year, kind), []).append(link)

    discovered: list[dict[str, str]] = []
    for year in YEARS:
        for kind in ("REPORT", "EXPANDED_TABLES"):
            options = candidates.get((year, kind), [])
            # De-duplicate URL while preserving discovery order.
            seen = set()
            unique = []
            for x in options:
                if x["url"] not in seen:
                    unique.append(x)
                    seen.add(x["url"])
            if unique:
                chosen = unique[0]
                discovered.append(
                    {
                        "year": str(year),
                        "artifact_type": kind,
                        "discovery_page": chosen["discovery_page"],
                        "anchor_text": chosen["anchor_text"],
                        "source_url": chosen["url"],
                    }
                )
    return discovered, page_status


def infer_extension(data: bytes, headers: dict[str, str], final_url: str, kind: str) -> str:
    ctype = headers.get("content-type", "").lower()
    path_ext = Path(urllib.parse.urlparse(final_url).path).suffix.lower()

    if data[:4] == b"%PDF" or "application/pdf" in ctype:
        return ".pdf"
    if data[:4] == b"PK\x03\x04" or "zip" in ctype:
        return ".zip"
    if path_ext in (".pdf", ".zip"):
        return path_ext

    # The report's /oact/tr/YYYY endpoint may be surfaced as application/pdf
    # by CMS even without a .pdf suffix. If not, preserve unknown bytes.
    return ".bin"


def acquire_one(item: dict[str, str]) -> dict[str, Any]:
    year = int(item["year"])
    kind = item["artifact_type"]
    row: dict[str, Any] = {
        **item,
        "final_url": "",
        "local_path": "",
        "retrieved_utc": "",
        "status": "",
        "http_content_type": "",
        "last_modified": "",
        "etag": "",
        "bytes": "",
        "sha256": "",
        "file_type": "",
        "error": "",
    }

    try:
        data, headers, final_url = request_bytes(item["source_url"])
        ext = infer_extension(data, headers, final_url, kind)

        if kind == "REPORT":
            target = REPORT_DIR / f"medicare_trustees_{year}{ext}"
        else:
            target = TABLE_DIR / f"medicare_trustees_{year}_expanded_tables{ext}"

        # Preserve exact newly retrieved bytes. If an identical file already
        # exists, this is idempotent; otherwise overwrite the same named
        # acquisition artifact with the currently official CMS response.
        existing_same = target.exists() and target.read_bytes() == data
        if not existing_same:
            target.write_bytes(data)

        row["final_url"] = final_url
        row["local_path"] = str(target.relative_to(ROOT))
        row["retrieved_utc"] = now_utc()
        row["status"] = "PREEXISTING_IDENTICAL" if existing_same else "DOWNLOAD"
        row["http_content_type"] = headers.get("content-type", "")
        row["last_modified"] = headers.get("last-modified", "")
        row["etag"] = headers.get("etag", "")
        row["bytes"] = target.stat().st_size
        row["sha256"] = sha256_file(target)
        row["file_type"] = ext.lstrip(".").upper()

        if kind == "REPORT" and ext != ".pdf":
            raise ValueError(f"Report did not resolve to PDF bytes; detected {ext}")
        if kind == "EXPANDED_TABLES" and ext != ".zip":
            raise ValueError(f"Expanded tables did not resolve to ZIP bytes; detected {ext}")

    except Exception as exc:
        row["status"] = "ERROR"
        row["error"] = f"{type(exc).__name__}: {exc}"

    return row


def inventory_zip(row: dict[str, Any]) -> list[dict[str, Any]]:
    if row["status"] == "ERROR" or row["artifact_type"] != "EXPANDED_TABLES":
        return []
    path = ROOT / row["local_path"]
    if not zipfile.is_zipfile(path):
        return []

    result = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            result.append(
                {
                    "year": row["year"],
                    "artifact_type": row["artifact_type"],
                    "zip_path": row["local_path"],
                    "member_name": info.filename,
                    "extension": Path(info.filename).suffix.lower(),
                    "member_bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                }
            )
    return result


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ensure_dirs()

    print("=" * 96)
    print("CMS MEDICARE TRUSTEES SOURCE ACQUISITION v0.2")
    print("=" * 96)
    print("Scope: official CMS Trustees vintages CY2015-CY2026")
    print("No payment extraction, classification, reconciliation, imputation, or DB writes.\n")

    discovered, page_status = discover()

    discovery_path = VALIDATION_DIR / "cms_medicare_trustees_discovery_manifest.csv"
    write_csv(
        discovery_path,
        discovered,
        ["year", "artifact_type", "discovery_page", "anchor_text", "source_url"],
    )

    page_path = VALIDATION_DIR / "cms_medicare_trustees_discovery_pages.csv"
    write_csv(
        page_path,
        page_status,
        ["discovery_page", "status", "links_found", "error"],
    )

    by_key = {(int(x["year"]), x["artifact_type"]): x for x in discovered}

    missing = []
    requested = []
    for year in YEARS:
        report = by_key.get((year, "REPORT"))
        if report:
            requested.append(report)
        else:
            missing.append((year, "REPORT"))

        expanded = by_key.get((year, "EXPANDED_TABLES"))
        if expanded:
            requested.append(expanded)
        else:
            missing.append((year, "EXPANDED_TABLES"))

    acquired = [acquire_one(x) for x in requested]

    acquisition_path = VALIDATION_DIR / "cms_medicare_trustees_acquisition_manifest.csv"
    write_csv(
        acquisition_path,
        acquired,
        [
            "year", "artifact_type", "discovery_page", "anchor_text",
            "source_url", "final_url", "local_path", "retrieved_utc", "status",
            "http_content_type", "last_modified", "etag", "bytes", "sha256",
            "file_type", "error",
        ],
    )

    inventory = []
    for row in acquired:
        inventory.extend(inventory_zip(row))

    inventory_path = VALIDATION_DIR / "cms_medicare_trustees_zip_inventory.csv"
    write_csv(
        inventory_path,
        inventory,
        [
            "year", "artifact_type", "zip_path", "member_name", "extension",
            "member_bytes", "compressed_bytes", "crc32",
        ],
    )

    errors = [x for x in acquired if x["status"] == "ERROR"]
    report_years = sorted(
        int(x["year"]) for x in acquired
        if x["artifact_type"] == "REPORT" and x["status"] != "ERROR"
    )
    expanded_years = sorted(
        int(x["year"]) for x in acquired
        if x["artifact_type"] == "EXPANDED_TABLES" and x["status"] != "ERROR"
    )

    checks = [
        ("All four official CMS discovery pages readable",
         all(x["status"] == "PASS" for x in page_status)),
        ("All required annual reports CY2015-CY2026 discovered",
         report_years == YEARS),
        ("All required expanded packages CY2015-CY2026 discovered",
         expanded_years == YEARS),
        ("All discovered artifacts acquired and type-validated",
         len(errors) == 0),
    ]
    overall = all(ok for _, ok in checks)

    lines = [
        "=" * 96,
        "CMS MEDICARE TRUSTEES SOURCE ACQUISITION v0.2",
        "=" * 96,
        "",
        f"Required annual report years        : {len(YEARS)}",
        f"Annual reports acquired             : {len(report_years)}",
        f"Expanded-table packages discovered  : {len(expanded_years)}",
        f"Expanded-table years                : {', '.join(map(str, expanded_years)) if expanded_years else 'NONE'}",
        f"ZIP members inventoried             : {len(inventory)}",
        f"Acquisition/type errors             : {len(errors)}",
        "",
        "REPORT YEARS ACQUIRED",
        "-" * 96,
        ", ".join(map(str, report_years)) if report_years else "NONE",
        "",
        "DISCOVERY GAPS",
        "-" * 96,
    ]

    if missing:
        lines.extend(f"{year} {kind}" for year, kind in missing)
    else:
        lines.append("NONE")

    lines += ["", "VALIDATION CHECKS", "-" * 96]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)

    lines += [
        "",
        f"OVERALL ACQUISITION STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "IMPORTANT:",
        "For this source universe, both the annual Trustees Report PDF and the official",
        "Expanded/Supplementary Tables package are required for every CY2015-CY2026 vintage.",
        "",
        "A PASS establishes source discovery, preservation, hashing, and file-type validation only.",
        "It does NOT establish which observations are actual versus projected, which Private Health",
        "Plans values are definitionally comparable to WCFFBP, or successful reconciliation.",
        "",
        "OUTPUTS",
        "-" * 96,
        str(discovery_path),
        str(page_path),
        str(acquisition_path),
        str(inventory_path),
    ]

    summary_path = VALIDATION_DIR / "cms_medicare_trustees_acquisition_summary.txt"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
