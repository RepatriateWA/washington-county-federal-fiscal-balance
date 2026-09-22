from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


OUTPUT_DIR = Path(
    "data/raw/cms/medicare_advantage/validation/source_discovery/2015"
)

MANIFEST_CSV = OUTPUT_DIR / "cms_ma_partc_source_discovery_2015.csv"
SUMMARY_TXT = OUTPUT_DIR / "cms_ma_partc_source_discovery_2015_summary.txt"

TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 WCFFBP CMS source-discovery "
        "contact: reproducible-research"
    )
}


# ---------------------------------------------------------------------
# Official CMS index pages.
# These are discovery authorities, not source-data downloads.
# ---------------------------------------------------------------------

INDEX_URLS = {
    "CPSC": (
        "https://www.cms.gov/data-research/statistics-trends-and-reports/"
        "medicare-advantagepart-d-contract-and-enrollment-data/"
        "monthly-enrollment-contract/plan/state/county"
    ),
    "SCC_SCP": (
        "https://www.cms.gov/data-research/statistics-trends-and-reports/"
        "medicare-advantagepart-d-contract-and-enrollment-data/"
        "monthly-ma-enrollment-state/county/contract"
    ),
    "SNP": (
        "https://www.cms.gov/data-research/statistics-trends-and-reports/"
        "medicare-advantagepart-d-contract-and-enrollment-data/"
        "special-needs-plan-snp-data"
    ),
}

PLAN_PAYMENT_2015 = (
    "https://www.cms.gov/medicare/medicare-advantage/"
    "plan-payment/plan-payment-data-items/2015-payment-data"
)


def get(session: requests.Session, url: str):
    try:
        response = session.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        return response, ""

    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def normalize(text: str) -> str:
    return " ".join(str(text).split())


def classify_href(href: str) -> str:
    lower = href.lower()

    if lower.endswith(".zip"):
        return "ZIP"
    if lower.endswith(".xlsx"):
        return "XLSX"
    if lower.endswith(".xls"):
        return "XLS"
    if lower.endswith(".csv"):
        return "CSV"
    if lower.endswith(".pdf"):
        return "PDF"

    return "OTHER"


def find_period_link(
    html: str,
    base_url: str,
    source_type: str,
    period: str,
) -> tuple[str, str]:
    """
    Locate the official CMS detail/landing-page link for one report period
    from the authoritative CMS index page.
    """

    soup = BeautifulSoup(html, "html.parser")

    candidates = []

    year, month = period.split("-")

    for a in soup.find_all("a", href=True):
        text = normalize(a.get_text(" ", strip=True))
        href = urljoin(base_url, a["href"])

        haystack = f"{text} {href}".lower()

        if period.lower() not in haystack:
            continue

        if source_type == "CPSC":
            if "cpsc" not in haystack:
                continue

        elif source_type == "SCC_SCP":
            if not (
                "scc" in haystack
                or "state/county/contract" in haystack
                or "state-county-contract" in haystack
            ):
                continue

        elif source_type == "SNP":
            if not (
                "snp" in haystack
                or "special-needs" in haystack
            ):
                continue

        candidates.append((text, href))

    # Prefer a detail page rather than a direct binary if both occur.
    candidates.sort(
        key=lambda x: (
            classify_href(x[1]) != "OTHER",
            len(x[1]),
        )
    )

    if candidates:
        return candidates[0]

    return "", ""


def discover_download_links(
    html: str,
    base_url: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    rows = []

    seen = set()

    for a in soup.find_all("a", href=True):
        text = normalize(a.get_text(" ", strip=True))
        href = urljoin(base_url, a["href"])

        file_type = classify_href(href)

        if file_type == "OTHER":
            continue

        key = (text, href)

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            {
                "download_text": text,
                "artifact_url": href,
                "artifact_type": file_type,
            }
        )

    return rows


def inspect_landing(
    session: requests.Session,
    source_type: str,
    period: str,
    landing_url: str,
    landing_text: str,
) -> dict:
    row = {
        "source_type": source_type,
        "period": period,
        "payment_year": "",
        "index_url": INDEX_URLS.get(source_type, ""),
        "index_link_text": landing_text,
        "landing_url": landing_url,
        "landing_http_status": "",
        "landing_final_url": "",
        "landing_error": "",
        "artifact_count": 0,
        "artifact_urls": "",
        "artifact_types": "",
        "artifact_link_texts": "",
        "discovery_status": "",
        "notes": "",
    }

    if not landing_url:
        row["discovery_status"] = "NOT_LOCATED"
        row["notes"] = "No period-specific link located on official CMS index."
        return row

    response, error = get(session, landing_url)

    if response is None:
        row["landing_error"] = error
        row["discovery_status"] = "REQUIRES_REVIEW"
        return row

    row["landing_http_status"] = response.status_code
    row["landing_final_url"] = response.url

    if response.status_code != 200:
        row["discovery_status"] = "REQUIRES_REVIEW"
        row["notes"] = (
            "Official CMS period link located, but landing request "
            f"returned HTTP {response.status_code}."
        )
        return row

    artifacts = discover_download_links(
        response.text,
        response.url,
    )

    row["artifact_count"] = len(artifacts)

    if artifacts:
        row["artifact_urls"] = " | ".join(
            x["artifact_url"] for x in artifacts
        )
        row["artifact_types"] = " | ".join(
            x["artifact_type"] for x in artifacts
        )
        row["artifact_link_texts"] = " | ".join(
            x["download_text"] for x in artifacts
        )
        row["discovery_status"] = "AVAILABLE_OFFICIAL"
    else:
        row["discovery_status"] = "LANDING_ONLY"
        row["notes"] = (
            "Official CMS landing page resolved, but no binary "
            "artifact link was extracted."
        )

    return row


def inspect_plan_payment(
    session: requests.Session,
) -> dict:
    row = {
        "source_type": "PLAN_PAYMENT",
        "period": "",
        "payment_year": 2015,
        "index_url": PLAN_PAYMENT_2015,
        "index_link_text": "2015 payment data",
        "landing_url": PLAN_PAYMENT_2015,
        "landing_http_status": "",
        "landing_final_url": "",
        "landing_error": "",
        "artifact_count": 0,
        "artifact_urls": "",
        "artifact_types": "",
        "artifact_link_texts": "",
        "discovery_status": "",
        "notes": "",
    }

    response, error = get(session, PLAN_PAYMENT_2015)

    if response is None:
        row["landing_error"] = error
        row["discovery_status"] = "REQUIRES_REVIEW"
        return row

    row["landing_http_status"] = response.status_code
    row["landing_final_url"] = response.url

    if response.status_code != 200:
        row["discovery_status"] = "REQUIRES_REVIEW"
        row["notes"] = (
            f"Official CMS Plan Payment page returned "
            f"HTTP {response.status_code}."
        )
        return row

    artifacts = discover_download_links(
        response.text,
        response.url,
    )

    row["artifact_count"] = len(artifacts)

    if artifacts:
        row["artifact_urls"] = " | ".join(
            x["artifact_url"] for x in artifacts
        )
        row["artifact_types"] = " | ".join(
            x["artifact_type"] for x in artifacts
        )
        row["artifact_link_texts"] = " | ".join(
            x["download_text"] for x in artifacts
        )
        row["discovery_status"] = "AVAILABLE_OFFICIAL"
    else:
        row["discovery_status"] = "LANDING_ONLY"
        row["notes"] = (
            "Official CMS Plan Payment page resolved, but no binary "
            "artifact link was extracted."
        )

    return row


def main() -> None:
    session = requests.Session()
    session.headers.update(HEADERS)

    periods = [
        f"2015-{month:02d}"
        for month in range(1, 13)
    ]

    rows = []

    print("=" * 80)
    print("CMS MEDICARE ADVANTAGE PART C — CY2015 SOURCE DISCOVERY")
    print("=" * 80)
    print()
    print("Network activity: official cms.gov pages only")
    print("Dataset downloads: NO")
    print("Database writes: NO")
    print()

    for source_type in (
        "CPSC",
        "SCC_SCP",
        "SNP",
    ):
        index_url = INDEX_URLS[source_type]

        print(f"Reading {source_type} CMS index...")

        response, error = get(session, index_url)

        if response is None:
            print(f"  ERROR: {error}")

            for period in periods:
                rows.append(
                    {
                        "source_type": source_type,
                        "period": period,
                        "payment_year": "",
                        "index_url": index_url,
                        "index_link_text": "",
                        "landing_url": "",
                        "landing_http_status": "",
                        "landing_final_url": "",
                        "landing_error": error,
                        "artifact_count": 0,
                        "artifact_urls": "",
                        "artifact_types": "",
                        "artifact_link_texts": "",
                        "discovery_status": "REQUIRES_REVIEW",
                        "notes": "Official CMS index request failed.",
                    }
                )

            continue

        print(
            f"  HTTP {response.status_code}: "
            f"{response.url}"
        )

        if response.status_code != 200:
            for period in periods:
                rows.append(
                    {
                        "source_type": source_type,
                        "period": period,
                        "payment_year": "",
                        "index_url": index_url,
                        "index_link_text": "",
                        "landing_url": "",
                        "landing_http_status": "",
                        "landing_final_url": "",
                        "landing_error": "",
                        "artifact_count": 0,
                        "artifact_urls": "",
                        "artifact_types": "",
                        "artifact_link_texts": "",
                        "discovery_status": "REQUIRES_REVIEW",
                        "notes": (
                            "Official CMS index returned "
                            f"HTTP {response.status_code}."
                        ),
                    }
                )

            continue

        for period in periods:
            link_text, landing_url = find_period_link(
                response.text,
                response.url,
                source_type,
                period,
            )

            row = inspect_landing(
                session,
                source_type,
                period,
                landing_url,
                link_text,
            )

            rows.append(row)

            print(
                f"  {period}: "
                f"{row['discovery_status']}"
                + (
                    f" | HTTP {row['landing_http_status']}"
                    if row["landing_http_status"] != ""
                    else ""
                )
                + (
                    f" | artifacts={row['artifact_count']}"
                    if row["artifact_count"]
                    else ""
                )
            )

    print()
    print("Reading 2015 Plan Payment CMS page...")

    plan_row = inspect_plan_payment(session)
    rows.append(plan_row)

    print(
        "  2015: "
        f"{plan_row['discovery_status']}"
        + (
            f" | HTTP {plan_row['landing_http_status']}"
            if plan_row["landing_http_status"] != ""
            else ""
        )
        + (
            f" | artifacts={plan_row['artifact_count']}"
            if plan_row["artifact_count"]
            else ""
        )
    )

    manifest = pd.DataFrame(rows)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest.to_csv(
        MANIFEST_CSV,
        index=False,
    )

    counts = (
        manifest["discovery_status"]
        .value_counts(dropna=False)
        .to_dict()
    )

    expected_rows = 37

    available = int(
        manifest["discovery_status"]
        .eq("AVAILABLE_OFFICIAL")
        .sum()
    )

    landing_only = int(
        manifest["discovery_status"]
        .eq("LANDING_ONLY")
        .sum()
    )

    not_located = int(
        manifest["discovery_status"]
        .eq("NOT_LOCATED")
        .sum()
    )

    review = int(
        manifest["discovery_status"]
        .eq("REQUIRES_REVIEW")
        .sum()
    )

    lines = [
        "=" * 80,
        "CMS MEDICARE ADVANTAGE PART C — CY2015 SOURCE DISCOVERY SUMMARY",
        "=" * 80,
        "",
        "SCOPE",
        "CY2015 only",
        "Monthly source families: CPSC, SCC/SCP, SNP",
        "Annual source family: Plan Payment",
        "",
        "EXPECTED SOURCE SLOTS",
        "CPSC:        12",
        "SCC/SCP:     12",
        "SNP:         12",
        "Plan Payment: 1",
        "Total:       37",
        "",
        "DISCOVERY RESULTS",
        f"AVAILABLE_OFFICIAL: {available}",
        f"LANDING_ONLY:       {landing_only}",
        f"NOT_LOCATED:        {not_located}",
        f"REQUIRES_REVIEW:    {review}",
        "",
        "INVARIANTS",
        (
            "PASS"
            if len(manifest) == expected_rows
            else "FAIL"
        )
        + f": manifest rows = {len(manifest)}; expected {expected_rows}",
        (
            "PASS"
            if len(manifest[manifest['source_type'].eq('CPSC')]) == 12
            else "FAIL"
        )
        + ": CPSC has 12 monthly rows",
        (
            "PASS"
            if len(manifest[manifest['source_type'].eq('SCC_SCP')]) == 12
            else "FAIL"
        )
        + ": SCC/SCP has 12 monthly rows",
        (
            "PASS"
            if len(manifest[manifest['source_type'].eq('SNP')]) == 12
            else "FAIL"
        )
        + ": SNP has 12 monthly rows",
        (
            "PASS"
            if len(manifest[manifest['source_type'].eq('PLAN_PAYMENT')]) == 1
            else "FAIL"
        )
        + ": Plan Payment has one annual row",
        "",
        "INTERPRETATION",
        (
            "AVAILABLE_OFFICIAL means an official CMS landing page resolved "
            "and at least one linked binary artifact was discovered."
        ),
        (
            "LANDING_ONLY means the official CMS landing page resolved but "
            "no binary artifact link was extracted."
        ),
        (
            "NOT_LOCATED means this discovery pass did not locate a "
            "period-specific official CMS landing link."
        ),
        (
            "REQUIRES_REVIEW means an official CMS URL was identified but "
            "the HTTP/discovery result requires manual investigation."
        ),
        "",
        (
            "No source dataset was downloaded and no database write was "
            "performed by this discovery script."
        ),
        "",
    ]

    summary = "\n".join(lines)

    SUMMARY_TXT.write_text(
        summary,
        encoding="utf-8",
    )

    print()
    print(summary)

    print("Evidence written to:")
    print(f"  {OUTPUT_DIR}")
    print()
    print("Files:")
    print(f"  {MANIFEST_CSV.name}")
    print(f"  {SUMMARY_TXT.name}")


if __name__ == "__main__":
    main()