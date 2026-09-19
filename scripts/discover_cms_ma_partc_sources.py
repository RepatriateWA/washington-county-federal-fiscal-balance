from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import calendar
import re
from bs4 import BeautifulSoup


# ============================================================================
# WCFFBP — CMS MEDICARE ADVANTAGE PART C SOURCE DISCOVERY
#
# Purpose:
#   Discover official CMS landing pages and linked binary artifacts for the
#   complete source universe required to reconstruct Washington Medicare
#   Advantage Part C for FFY2015-FFY2024.
#
# Important:
#   - Required-source universe comes from the committed local inventory.
#   - Official cms.gov pages only.
#   - No source datasets are downloaded.
#   - No database writes.
#   - Every required source slot remains in the output even if discovery fails.
# ============================================================================


ROOT = Path("data/raw/cms/medicare_advantage")

INVENTORY_CSV = (
    ROOT
    / "validation"
    / "source_inventory"
    / "cms_ma_partc_required_source_inventory.csv"
)

OUTPUT_DIR = (
    ROOT
    / "validation"
    / "source_discovery"
)

MANIFEST_CSV = (
    OUTPUT_DIR
    / "cms_ma_partc_source_discovery_manifest.csv"
)

SUMMARY_TXT = (
    OUTPUT_DIR
    / "cms_ma_partc_source_discovery_summary.txt"
)


TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 WCFFBP CMS source-discovery "
        "reproducible-research"
    )
}


# ============================================================================
# OFFICIAL CMS DISCOVERY INDEXES
# ============================================================================

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

PLAN_PAYMENT_INDEX_URL = (
    "https://www.cms.gov/medicare/health-drug-plans/"
    "plan-payment-data"
)

def plan_payment_url(year: int) -> str:
    return (
        "https://www.cms.gov/medicare/medicare-advantage/"
        f"plan-payment/plan-payment-data-items/{year}-payment-data"
    )


# ============================================================================
# HTTP HELPERS
# ============================================================================

def http_get(
    session: requests.Session,
    url: str,
):
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


def classify_href(
    href: str,
    link_text: str = "",
) -> str:
    """
    Classify linked binary artifacts.

    Prefer the URL suffix when present.  For legacy CMS download links
    whose href is extensionless, allow the visible link text to establish
    the artifact type.

    Query strings and fragments are removed before suffix testing.
    CMS may append a numeric revision suffix to file URLs, for example
    ".zip-0"; these are treated as the underlying binary type.
    """

    def classify_value(value: str) -> str:
        lower = (
            value.lower()
            .split("?", 1)[0]
            .split("#", 1)[0]
            .strip()
        )

        # CMS sometimes appends a numeric revision suffix to a file path,
        # e.g. "2022-plan-payment.zip-0".
        lower = re.sub(
            r"(\.(?:zip|xlsx|xls|csv|pdf))-\d+$",
            r"\1",
            lower,
        )

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

    # Normal/current CMS form: classify from URL.
    artifact_type = classify_value(href)

    if artifact_type != "OTHER":
        return artifact_type

    # Legacy CMS form: the href may be extensionless while the
    # authoritative visible download label contains the filename.
    return classify_value(
        normalize(link_text)
    )


# ============================================================================
# MONTHLY LANDING-PAGE DISCOVERY
# ============================================================================

def find_period_link(
    html: str,
    base_url: str,
    source_type: str,
    period: str,
) -> tuple[str, str]:
    """
    Find the period-specific official CMS link exposed by an authoritative
    CMS index.

    The function intentionally does not invent an artifact URL.
    """

    soup = BeautifulSoup(html, "html.parser")

    year, month = period.split("-")
    month_number = int(month)
    month_name = calendar.month_name[month_number]
    month_abbr = calendar.month_abbr[month_number]

    candidates: list[tuple[str, str]] = []

    for anchor in soup.find_all("a", href=True):
        text = normalize(
            anchor.get_text(" ", strip=True)
        )

        href = urljoin(
            base_url,
            anchor["href"],
        )

        parent = anchor.find_parent(["tr", "li"])

        parent_text = (
            normalize(parent.get_text(" ", strip=True))
            if parent is not None
            else ""
        )

        haystack = f"{text} {href} {parent_text}".lower()

        year_match = year in haystack

        month_match = any(
            token.lower() in haystack
            for token in (
                month_name,
                month_abbr,
                f"{year}-{month}",
                f"{year}_{month}",
                f"{year}/{month}",
                f"{month}/{year}",
                f"{month}-{year}",
                f"{month}_{year}",
            )
        )

        if not (year_match and month_match):
            continue

        candidates.append(
            (text, href)
        )

    # Prefer an HTML/detail page over a binary artifact.
    candidates.sort(
        key=lambda x: (
            classify_href(x[1]) != "OTHER",
            len(x[1]),
            x[1],
        )
    )

    if not candidates:
        return "", ""

    return candidates[0]

def discover_download_links(
    html: str,
    base_url: str,
) -> list[dict]:
    """
    Preserve every linked binary artifact discovered on the CMS landing page.

    Artifact selection for acquisition is intentionally deferred.
    """

    soup = BeautifulSoup(html, "html.parser")

    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for anchor in soup.find_all("a", href=True):
        text = normalize(
            anchor.get_text(" ", strip=True)
        )

        href = urljoin(
            base_url,
            anchor["href"],
        )

        artifact_type = classify_href(
            href,
            text,
        )

        if artifact_type == "OTHER":
            continue

        key = (text, href)

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            {
                "download_text": text,
                "artifact_url": href,
                "artifact_type": artifact_type,
            }
        )

    return rows


def discover_monthly_slot(
    session: requests.Session,
    source_row: pd.Series,
    index_response,
    index_error: str,
) -> dict:
    source_type = str(source_row["source_type"])
    period = str(source_row["period"])

    row = base_output_row(source_row)

    row["index_url"] = INDEX_URLS[source_type]

    if index_response is None:
        row["index_error"] = index_error
        row["discovery_status"] = "REQUIRES_REVIEW"
        row["discovery_method"] = "OFFICIAL_INDEX_FAILED"
        row["notes"] = (
            "Official CMS index request failed."
        )
        return row

    row["index_http_status"] = (
        index_response.status_code
    )
    row["index_final_url"] = (
        index_response.url
    )

    if index_response.status_code != 200:
        row["discovery_status"] = "REQUIRES_REVIEW"
        row["discovery_method"] = "OFFICIAL_INDEX_FAILED"
        row["notes"] = (
            "Official CMS index returned HTTP "
            f"{index_response.status_code}."
        )
        return row

    link_text, landing_url = find_period_link(
        index_response.text,
        index_response.url,
        source_type,
        period,
    )

    row["index_link_text"] = link_text
    row["landing_url"] = landing_url

    if not landing_url:
        row["discovery_status"] = "NOT_LOCATED"
        row["discovery_method"] = "OFFICIAL_INDEX_SEARCH"
        row["notes"] = (
            "No period-specific official CMS link located "
            "on the source index."
        )
        return row

    landing_response, landing_error = http_get(
        session,
        landing_url,
    )

    if landing_response is None:
        row["landing_error"] = landing_error
        row["discovery_status"] = "REQUIRES_REVIEW"
        row["discovery_method"] = "OFFICIAL_INDEX_LINK"
        row["notes"] = (
            "Official CMS period link was located, but "
            "the landing request failed."
        )
        return row

    row["landing_http_status"] = (
        landing_response.status_code
    )
    row["landing_final_url"] = (
        landing_response.url
    )

    if landing_response.status_code != 200:
        row["discovery_status"] = "REQUIRES_REVIEW"
        row["discovery_method"] = "OFFICIAL_INDEX_LINK"
        row["notes"] = (
            "Official CMS period link located, but landing "
            "request returned HTTP "
            f"{landing_response.status_code}."
        )
        return row

    artifacts = discover_download_links(
        landing_response.text,
        landing_response.url,
    )

    preserve_artifacts(
        row,
        artifacts,
    )

    row["discovery_method"] = "OFFICIAL_INDEX_LINK"

    if artifacts:
        row["discovery_status"] = "AVAILABLE_OFFICIAL"
    else:
        row["discovery_status"] = "LANDING_ONLY"
        row["notes"] = (
            "Official CMS period landing page resolved, "
            "but no binary artifact link was extracted."
        )

    return row


# ============================================================================
# ANNUAL PLAN PAYMENT DISCOVERY
# ============================================================================

def discover_plan_payment_slot(
    session: requests.Session,
    source_row: pd.Series,
    index_response,
    index_error: str,
) -> dict:
    """
    Discover an annual Plan Payment source from the authoritative CMS
    Plan Payment Data index rather than constructing a year-specific URL.

    CMS has changed Plan Payment URL structures over time, so the index
    is treated as authoritative routing evidence.
    """

    year = int(source_row["payment_year"])
    year_text = str(year)

    row = base_output_row(source_row)

    row["index_url"] = PLAN_PAYMENT_INDEX_URL

    if index_response is None:
        row["index_error"] = index_error
        row["discovery_status"] = "REQUIRES_REVIEW"
        row["discovery_method"] = "OFFICIAL_PLAN_PAYMENT_INDEX_FAILED"
        row["notes"] = (
            "Official CMS Plan Payment index request failed."
        )
        return row

    row["index_http_status"] = index_response.status_code
    row["index_final_url"] = index_response.url

    if index_response.status_code != 200:
        row["discovery_status"] = "REQUIRES_REVIEW"
        row["discovery_method"] = "OFFICIAL_PLAN_PAYMENT_INDEX_FAILED"
        row["notes"] = (
            "Official CMS Plan Payment index returned HTTP "
            f"{index_response.status_code}."
        )
        return row

    soup = BeautifulSoup(
        index_response.text,
        "html.parser",
    )

    candidates: list[tuple[str, str]] = []

    for anchor in soup.find_all("a", href=True):
        text = normalize(
            anchor.get_text(" ", strip=True)
        )

        href = urljoin(
            index_response.url,
            anchor["href"],
        )

        parsed = urlparse(href)
        href_path = parsed.path.lower().rstrip("/")

        # Match the explicit CMS Plan Year identity, not arbitrary
        # surrounding text such as a release date.
        text_is_year = text.strip() == year_text

        # Narrow historical-route fallback.  The requested year must
        # identify a Plan Payment URL path.
        href_is_plan_payment_year = (
            "plan-payment" in href_path
            and (
                href_path.endswith(f"/{year_text}")
                or href_path.endswith(f"/{year_text}-payment-data")
                or href_path.endswith(f"/{year_text}paymentdata")
            )
        )

        if not (
            text_is_year
            or href_is_plan_payment_year
        ):
            continue

        candidates.append(
            (text, href)
        )

    # Prefer a CMS HTML landing page over a directly linked binary.
    candidates.sort(
        key=lambda x: (
            classify_href(x[1]) != "OTHER",
            len(x[1]),
            x[1],
        )
    )

    if not candidates:
        row["discovery_status"] = "NOT_LOCATED"
        row["discovery_method"] = "OFFICIAL_PLAN_PAYMENT_INDEX"
        row["notes"] = (
            f"Plan year {year} was not resolved to an official CMS "
            "landing link from the Plan Payment Data index."
        )
        return row

    link_text, landing_url = candidates[0]

    row["index_link_text"] = link_text
    row["landing_url"] = landing_url

    landing_response, landing_error = http_get(
        session,
        landing_url,
    )

    if landing_response is None:
        row["landing_error"] = landing_error
        row["discovery_status"] = "REQUIRES_REVIEW"
        row["discovery_method"] = "OFFICIAL_PLAN_PAYMENT_INDEX"
        row["notes"] = (
            "Official CMS Plan Payment landing link was located, "
            "but the landing request failed."
        )
        return row

    row["landing_http_status"] = landing_response.status_code
    row["landing_final_url"] = landing_response.url

    if landing_response.status_code != 200:
        row["discovery_status"] = "REQUIRES_REVIEW"
        row["discovery_method"] = "OFFICIAL_PLAN_PAYMENT_INDEX"
        row["notes"] = (
            "Official CMS Plan Payment landing link was located, "
            "but returned HTTP "
            f"{landing_response.status_code}."
        )
        return row

    artifacts = discover_download_links(
        landing_response.text,
        landing_response.url,
    )

    # Preserve every discovered binary link for provenance.
    preserve_artifacts(
        row,
        artifacts,
    )

    # A Plan Payment year is AVAILABLE_OFFICIAL only when at least
    # one discovered binary is semantically identifiable as the
    # requested year's Plan Payment/payment-data artifact.
    relevant_artifacts: list[dict] = []

    year_text = str(year)

    for artifact in artifacts:
        artifact_url = normalize(
            artifact.get("artifact_url", "")
        ).lower()

        download_text = normalize(
            artifact.get("download_text", "")
        ).lower()

        semantic_text = (
            f"{download_text} {artifact_url}"
        )

        year_identified = year_text in semantic_text

        payment_identified = any(
            token in semantic_text
            for token in (
                "plan payment",
                "plan-payment",
                "plan_payment",
                "payment data",
                "payment-data",
                "payment_data",
                "paymentdata",
            )
        )

        if year_identified and payment_identified:
            relevant_artifacts.append(
                artifact
            )

    row["discovery_method"] = "OFFICIAL_PLAN_PAYMENT_INDEX"

    if relevant_artifacts:
        row["discovery_status"] = "AVAILABLE_OFFICIAL"
        row["notes"] = (
            f"{len(relevant_artifacts)} Plan Payment-relevant binary "
            f"artifact(s) identified from {len(artifacts)} total "
            "binary link(s) preserved from the official CMS landing page."
        )
    else:
        row["discovery_status"] = "LANDING_ONLY"

        if artifacts:
            row["notes"] = (
                f"Official CMS Plan Payment landing page resolved and "
                f"{len(artifacts)} binary link(s) were preserved, but "
                f"none was identified as a Plan Payment artifact for "
                f"plan year {year}."
            )
        else:
            row["notes"] = (
                "Official CMS Plan Payment landing page resolved, "
                "but no binary artifact link was extracted."
            )

    return row

# ============================================================================
# OUTPUT ROW HELPERS
# ============================================================================

def clean_scalar(value):
    if pd.isna(value):
        return ""
    return value


def base_output_row(
    source_row: pd.Series,
) -> dict:
    """
    Start every discovery row with the committed inventory metadata.

    This preserves the separation between:
      required source universe,
      local acquisition status,
      official CMS discovery status.
    """

    return {
        "source_grain": clean_scalar(
            source_row["source_grain"]
        ),
        "period": clean_scalar(
            source_row["period"]
        ),
        "year": clean_scalar(
            source_row["year"]
        ),
        "month": clean_scalar(
            source_row["month"]
        ),
        "payment_year": clean_scalar(
            source_row["payment_year"]
        ),
        "source_type": clean_scalar(
            source_row["source_type"]
        ),
        "required_for_ffy": clean_scalar(
            source_row["required_for_ffy"]
        ),
        "local_status": clean_scalar(
            source_row["local_status"]
        ),
        "local_path": clean_scalar(
            source_row["local_path"]
        ),
        "local_filename": clean_scalar(
            source_row["filename"]
        ),
        "local_bytes": clean_scalar(
            source_row["bytes"]
        ),
        "local_sha256": clean_scalar(
            source_row["sha256"]
        ),
        "local_zip_status": clean_scalar(
            source_row["zip_status"]
        ),
        "index_url": "",
        "index_http_status": "",
        "index_final_url": "",
        "index_error": "",
        "index_link_text": "",
        "landing_url": "",
        "landing_http_status": "",
        "landing_final_url": "",
        "landing_error": "",
        "artifact_count": 0,
        "artifact_urls": "",
        "artifact_types": "",
        "artifact_link_texts": "",
        "discovery_method": "",
        "discovery_status": "",
        "notes": "",
    }


def preserve_artifacts(
    row: dict,
    artifacts: list[dict],
) -> None:
    row["artifact_count"] = len(artifacts)

    if not artifacts:
        return

    row["artifact_urls"] = " | ".join(
        artifact["artifact_url"]
        for artifact in artifacts
    )

    row["artifact_types"] = " | ".join(
        artifact["artifact_type"]
        for artifact in artifacts
    )

    row["artifact_link_texts"] = " | ".join(
        artifact["download_text"]
        for artifact in artifacts
    )


# ============================================================================
# VALIDATION
# ============================================================================

def validate_inventory(
    inventory: pd.DataFrame,
) -> None:
    required_columns = {
        "source_grain",
        "period",
        "year",
        "month",
        "payment_year",
        "source_type",
        "required_for_ffy",
        "local_status",
        "local_path",
        "filename",
        "bytes",
        "sha256",
        "zip_status",
    }

    missing = (
        required_columns
        - set(inventory.columns)
    )

    if missing:
        raise RuntimeError(
            "Inventory missing required columns: "
            + ", ".join(sorted(missing))
        )

    if len(inventory) != 371:
        raise RuntimeError(
            "Required-source inventory must contain exactly "
            f"371 rows; found {len(inventory)}."
        )

    monthly = inventory[
        inventory["source_grain"].eq("MONTHLY")
    ]

    annual = inventory[
        inventory["source_grain"].eq("ANNUAL")
    ]

    if len(monthly) != 360:
        raise RuntimeError(
            "Monthly inventory must contain exactly "
            f"360 rows; found {len(monthly)}."
        )

    if len(annual) != 11:
        raise RuntimeError(
            "Annual inventory must contain exactly "
            f"11 rows; found {len(annual)}."
        )

    for source_type in (
        "CPSC",
        "SCC_SCP",
        "SNP",
    ):
        source = monthly[
            monthly["source_type"].eq(source_type)
        ]

        if len(source) != 120:
            raise RuntimeError(
                f"{source_type} must contain exactly "
                f"120 monthly rows; found {len(source)}."
            )

        if source["period"].nunique() != 120:
            raise RuntimeError(
                f"{source_type} does not contain "
                "120 unique monthly periods."
            )

    if annual["payment_year"].nunique() != 11:
        raise RuntimeError(
            "Plan Payment inventory does not contain "
            "11 unique payment years."
        )


def validate_manifest(
    manifest: pd.DataFrame,
) -> list[str]:
    checks: list[str] = []

    def add(
        condition: bool,
        description: str,
    ) -> None:
        checks.append(
            ("PASS: " if condition else "FAIL: ")
            + description
        )

    monthly = manifest[
        manifest["source_grain"].eq("MONTHLY")
    ]

    annual = manifest[
        manifest["source_grain"].eq("ANNUAL")
    ]

    add(
        len(manifest) == 371,
        f"manifest rows = {len(manifest)}; expected 371",
    )

    add(
        len(monthly) == 360,
        f"monthly rows = {len(monthly)}; expected 360",
    )

    add(
        len(annual) == 11,
        f"annual rows = {len(annual)}; expected 11",
    )

    for source_type in (
        "CPSC",
        "SCC_SCP",
        "SNP",
    ):
        source = monthly[
            monthly["source_type"].eq(source_type)
        ]

        add(
            len(source) == 120,
            f"{source_type} rows = {len(source)}; expected 120",
        )

        add(
            source["period"].nunique() == 120,
            (
                f"{source_type} unique periods = "
                f"{source['period'].nunique()}; expected 120"
            ),
        )

    add(
        annual["payment_year"].nunique() == 11,
        (
            "Plan Payment unique years = "
            f"{annual['payment_year'].nunique()}; expected 11"
        ),
    )

    add(
        manifest["discovery_status"]
        .fillna("")
        .ne("")
        .all(),
        "every required source slot has a discovery status",
    )

    add(
        manifest[
            [
                "source_grain",
                "period",
                "payment_year",
                "source_type",
            ]
        ]
        .duplicated()
        .sum()
        == 0,
        "no duplicate required-source identities",
    )

    return checks


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    if not INVENTORY_CSV.exists():
        raise FileNotFoundError(
            "Required-source inventory not found:\n"
            f"  {INVENTORY_CSV}\n"
            "Run build_cms_ma_partc_source_inventory.py first."
        )

    inventory = pd.read_csv(
        INVENTORY_CSV,
        dtype={
            "period": "string",
            "source_type": "string",
            "source_grain": "string",
        },
    )

    validate_inventory(inventory)

    session = requests.Session()
    session.headers.update(HEADERS)

    print("=" * 80)
    print(
        "CMS MEDICARE ADVANTAGE PART C — FULL SOURCE DISCOVERY"
    )
    print("=" * 80)
    print()
    print(
        "Required universe: October 2014 through September 2024"
    )
    print(
        "Plan Payment years: CY2014 through CY2024"
    )
    print(
        "Required source slots: 371"
    )
    print()
    print(
        "Network activity: official cms.gov pages only"
    )
    print("Dataset downloads: NO")
    print("Database writes: NO")
    print()

    # ------------------------------------------------------------------
    # Fetch each monthly index once.
    # ------------------------------------------------------------------

    index_results: dict[str, tuple] = {}

    for source_type in (
        "CPSC",
        "SCC_SCP",
        "SNP",
    ):
        url = INDEX_URLS[source_type]

        print(
            f"Reading {source_type} CMS index..."
        )

        response, error = http_get(
            session,
            url,
        )

        index_results[source_type] = (
            response,
            error,
        )

        if response is None:
            print(
                f"  ERROR: {error}"
            )
        else:
            print(
                f"  HTTP {response.status_code}: "
                f"{response.url}"
            )

    print()

    output_rows: list[dict] = []

    # ------------------------------------------------------------------
    # Monthly discovery.
    # ------------------------------------------------------------------

    monthly_inventory = inventory[
        inventory["source_grain"].eq("MONTHLY")
    ].copy()

    monthly_inventory = monthly_inventory.sort_values(
        ["source_type", "period"]
    )

    for source_type in (
        "CPSC",
        "SCC_SCP",
        "SNP",
    ):
        print(
            f"Discovering {source_type} monthly sources..."
        )

        response, error = index_results[
            source_type
        ]

        source_rows = monthly_inventory[
            monthly_inventory["source_type"].eq(
                source_type
            )
        ]

        for _, source_row in source_rows.iterrows():
            result = discover_monthly_slot(
                session,
                source_row,
                response,
                error,
            )

            output_rows.append(result)

            print(
                f"  {result['period']}: "
                f"{result['discovery_status']}"
                + (
                    f" | HTTP {result['landing_http_status']}"
                    if result["landing_http_status"] != ""
                    else ""
                )
                + (
                    f" | artifacts={result['artifact_count']}"
                    if result["artifact_count"]
                    else ""
                )
            )

        print()

    # ------------------------------------------------------------------
    # Annual Plan Payment discovery.
    # ------------------------------------------------------------------

    print(
    "Reading Plan Payment CMS index..."
    )

    plan_payment_index_response, plan_payment_index_error = http_get(
        session,
        PLAN_PAYMENT_INDEX_URL,
    )

    if plan_payment_index_response is None:
        print(
            f"  ERROR: {plan_payment_index_error}"
        )
    else:
        print(
            f"  HTTP {plan_payment_index_response.status_code}: "
            f"{plan_payment_index_response.url}"
        )

    print()

    print(
        "Discovering annual Plan Payment sources..."
    )

    annual_inventory = inventory[
        inventory["source_grain"].eq("ANNUAL")
    ].copy()

    annual_inventory = annual_inventory.sort_values(
        "payment_year"
    )

    for _, source_row in annual_inventory.iterrows():
        result = discover_plan_payment_slot(
            session,
            source_row,
            plan_payment_index_response,
            plan_payment_index_error,
        )

        output_rows.append(result)

        print(
            f"  {int(result['payment_year'])}: "
            f"{result['discovery_status']}"
            + (
                f" | HTTP {result['landing_http_status']}"
                if result["landing_http_status"] != ""
                else ""
            )
            + (
                f" | artifacts={result['artifact_count']}"
                if result["artifact_count"]
                else ""
            )
        )

    manifest = pd.DataFrame(output_rows)

    # Restore deterministic source-universe order:
    # monthly chronologically within source family, then Plan Payment.
    source_order = {
        "CPSC": 1,
        "SCC_SCP": 2,
        "SNP": 3,
        "PLAN_PAYMENT": 4,
    }

    manifest["_source_order"] = (
        manifest["source_type"]
        .map(source_order)
    )

    manifest["_period_sort"] = (
        manifest["period"]
        .astype(str)
    )

    manifest["_year_sort"] = pd.to_numeric(
        manifest["payment_year"],
        errors="coerce",
    ).fillna(0)

    manifest = (
        manifest
        .sort_values(
            [
                "_source_order",
                "_period_sort",
                "_year_sort",
            ]
        )
        .drop(
            columns=[
                "_source_order",
                "_period_sort",
                "_year_sort",
            ]
        )
        .reset_index(drop=True)
    )

    checks = validate_manifest(
        manifest
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest.to_csv(
        MANIFEST_CSV,
        index=False,
    )

    # ------------------------------------------------------------------
    # Summary accounting.
    # ------------------------------------------------------------------

    status_counts = (
        manifest["discovery_status"]
        .value_counts(dropna=False)
        .to_dict()
    )

    available = int(
        status_counts.get(
            "AVAILABLE_OFFICIAL",
            0,
        )
    )

    landing_only = int(
        status_counts.get(
            "LANDING_ONLY",
            0,
        )
    )

    not_located = int(
        status_counts.get(
            "NOT_LOCATED",
            0,
        )
    )

    review = int(
        status_counts.get(
            "REQUIRES_REVIEW",
            0,
        )
    )

    present_local = int(
        manifest["local_status"]
        .eq("PRESENT")
        .sum()
    )

    not_present_local = int(
        manifest["local_status"]
        .eq("NOT_PRESENT")
        .sum()
    )

    all_checks_pass = all(
        check.startswith("PASS:")
        for check in checks
    )

    lines: list[str] = []

    lines.append("=" * 80)
    lines.append(
        "CMS MEDICARE ADVANTAGE PART C — FULL SOURCE DISCOVERY SUMMARY"
    )
    lines.append("=" * 80)
    lines.append("")

    lines.append("REQUIRED SOURCE UNIVERSE")
    lines.append(
        "Monthly reconstruction window: October 2014 through September 2024"
    )
    lines.append(
        "Plan Payment years: CY2014-CY2024"
    )
    lines.append(
        "Monthly source slots: 360"
    )
    lines.append(
        "Annual Plan Payment slots: 11"
    )
    lines.append(
        "Total required source slots: 371"
    )
    lines.append("")

    lines.append("LOCAL ACQUISITION STATUS")
    lines.append(
        f"PRESENT:     {present_local}"
    )
    lines.append(
        f"NOT_PRESENT: {not_present_local}"
    )
    lines.append("")

    lines.append("OFFICIAL CMS DISCOVERY STATUS")
    lines.append(
        f"AVAILABLE_OFFICIAL: {available}"
    )
    lines.append(
        f"LANDING_ONLY:       {landing_only}"
    )
    lines.append(
        f"NOT_LOCATED:        {not_located}"
    )
    lines.append(
        f"REQUIRES_REVIEW:    {review}"
    )
    lines.append("")

    lines.append("DISCOVERY BY SOURCE FAMILY")

    for source_type in (
        "CPSC",
        "SCC_SCP",
        "SNP",
        "PLAN_PAYMENT",
    ):
        subset = manifest[
            manifest["source_type"].eq(
                source_type
            )
        ]

        counts = (
            subset["discovery_status"]
            .value_counts()
            .to_dict()
        )

        lines.append(
            f"{source_type:<12} "
            f"required={len(subset):>3}  "
            f"available={counts.get('AVAILABLE_OFFICIAL', 0):>3}  "
            f"landing_only={counts.get('LANDING_ONLY', 0):>3}  "
            f"not_located={counts.get('NOT_LOCATED', 0):>3}  "
            f"review={counts.get('REQUIRES_REVIEW', 0):>3}"
        )

    lines.append("")
    lines.append("MANIFEST INVARIANTS")

    lines.extend(checks)

    lines.append("")
    lines.append(
        "RESULT: "
        + (
            "ALL MANIFEST INVARIANTS PASS"
            if all_checks_pass
            else "ONE OR MORE MANIFEST INVARIANTS FAIL"
        )
    )

    lines.append("")
    lines.append("INTERPRETATION")
    lines.append(
        "AVAILABLE_OFFICIAL means an official CMS landing page resolved "
        "and the source-family availability criterion was satisfied."
    )
    lines.append(
        "For monthly CPSC, SCC/SCP, and SNP sources, this requires at "
        "least one linked binary artifact."
    )
    lines.append(
        "For annual Plan Payment sources, this additionally requires at "
        "least one binary artifact semantically identifiable as Plan "
        "Payment/payment data for the requested year."
    )
    lines.append(
        "LANDING_ONLY means an official CMS landing page resolved but "
        "no binary artifact link was extracted."
    )
    lines.append(
        "NOT_LOCATED means this discovery pass did not locate a "
        "period-specific official CMS landing link."
    )
    lines.append(
        "REQUIRES_REVIEW means an official CMS URL was identified but "
        "the HTTP/discovery result requires investigation."
    )
    lines.append(
        "PRESENT and NOT_PRESENT describe local repository acquisition "
        "status and are independent of official CMS availability."
    )
    lines.append(
        "Artifact links are preserved as discovered. This script does "
        "not select the authoritative dataset artifact for acquisition."
    )
    lines.append(
        "No source dataset was downloaded and no database write was performed."
    )
    lines.append("")

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