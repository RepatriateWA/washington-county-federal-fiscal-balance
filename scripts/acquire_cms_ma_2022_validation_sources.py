"""
Acquire and validate CMS Medicare Advantage validation sources for CY2022.

Source families
---------------
CPSC : Monthly Enrollment by Contract/Plan/State/County
SCP  : Monthly MA Enrollment by State/County/Plan Type
SNP  : SNP Comprehensive Report

Methodology
-----------
1. Attempt discovery from the official CMS monthly landing page.
2. If CMS's historical landing page is missing/broken, test the
   corresponding official cms.gov artifact URL using the established
   CMS filename pattern.
3. Preserve the source artifact locally.
4. Calculate SHA-256.
5. Validate the archive structure.
6. Write an incremental provenance manifest.
7. Require 12/12 PASS for each family and 36/36 overall.

Important
---------
* Existing source artifacts are verified and reused, not overwritten.
* Direct CMS artifact recovery is explicitly recorded in provenance.
* No database writes are performed.
* This script acquires source evidence only. It does NOT calculate
  Medicare Advantage payments.
"""

from __future__ import annotations

import csv
import hashlib
import re
import sys
import time
import zipfile

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


# ============================================================================
# CONFIGURATION
# ============================================================================

YEAR = 2022

ROOT = Path(
    r"data\raw\cms\medicare_advantage"
)

MANIFEST_DIR = (
    ROOT
    / "validation"
    / str(YEAR)
)

MANIFEST_PATH = (
    MANIFEST_DIR
    / f"cms_ma_{YEAR}_validation_source_manifest.csv"
)

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/120 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT
}

TIMEOUT_PAGE = 60
TIMEOUT_DOWNLOAD = 180

# Small delay between CMS requests.
REQUEST_DELAY_SECONDS = 0.35


# ============================================================================
# SOURCE DEFINITIONS
# ============================================================================

@dataclass(frozen=True)
class Family:
    code: str
    description: str
    destination: str
    landing_template: str
    required_tokens: tuple[str, ...]


FAMILIES = {

    "CPSC": Family(
        code="CPSC",
        description=(
            "Monthly Enrollment by "
            "Contract/Plan/State/County"
        ),
        destination="enrollment",
        landing_template=(
            "https://www.cms.gov/"
            "research-statistics-data-and-systems"
            "statistics-trends-and-reports"
            "mcradvpartdenroldatamonthly/"
            "monthly-enrollment-cpsc-{year}-{month:02d}"
        ),
        required_tokens=(
            "cpsc",
            "enrollment",
        ),
    ),

    "SCP": Family(
        code="SCP",
        description=(
            "Monthly MA Enrollment by "
            "State/County/Plan Type"
        ),
        destination="enrollment_controls",
        landing_template=(
            "https://www.cms.gov/"
            "research-statistics-data-and-systems"
            "statistics-trends-and-reports"
            "mcradvpartdenroldatamonthly-ma/"
            "ma-enrollment-scp-{year}-{month:02d}"
        ),
        required_tokens=(
            "scp",
        ),
    ),

    "SNP": Family(
        code="SNP",
        description=(
            "SNP Comprehensive Report"
        ),
        destination="snp",
        landing_template=(
            "https://www.cms.gov/"
            "research-statistics-data-and-systems"
            "statistics-trends-and-reports"
            "mcradvpartdenroldataspecial-needs/"
            "snp-comprehensive-report-{year}-{month:02d}"
        ),
        required_tokens=(
            "snp",
        ),
    ),
}


MONTH_NAMES = {
    1: "january",
    2: "february",
    3: "march",
    4: "april",
    5: "may",
    6: "june",
    7: "july",
    8: "august",
    9: "september",
    10: "october",
    11: "november",
    12: "december",
}


MANIFEST_FIELDS = [
    "family",
    "year",
    "month",
    "status",
    "discovery_method",
    "landing_url",
    "landing_http_status",
    "download_url",
    "local_path",
    "bytes",
    "sha256",
    "retrieved_utc",
    "archive_valid",
    "member_count",
    "members",
    "note",
]


session = requests.Session()
session.headers.update(HEADERS)


# ============================================================================
# BASIC UTILITIES
# ============================================================================

def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:

        while True:
            block = f.read(
                1024 * 1024
            )

            if not block:
                break

            h.update(block)

    return h.hexdigest()


def safe_filename_from_url(
    url: str,
) -> str:

    name = Path(
        urlparse(url).path
    ).name

    if not name:
        raise RuntimeError(
            "Could not derive filename "
            f"from URL: {url}"
        )

    return name


def extract_hrefs(
    html: str,
) -> list[str]:

    return re.findall(
        r'href=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )


# ============================================================================
# LANDING-PAGE DISCOVERY
# ============================================================================

def score_candidate(
    family: Family,
    url: str,
) -> int:

    u = url.lower()

    score = 0

    for token in family.required_tokens:

        if token in u:
            score += 10

    if ".zip" in u:
        score += 5

    if family.code == "SNP":

        if (
            ".xlsx" in u
            or ".xls" in u
        ):
            score += 3

    return score


def discover_download(
    family: Family,
    landing_url: str,
) -> tuple[int, str, str]:

    r = session.get(
        landing_url,
        timeout=TIMEOUT_PAGE,
    )

    status = r.status_code

    if status != 200:

        return (
            status,
            "",
            f"Landing page HTTP {status}",
        )

    hrefs = extract_hrefs(
        r.text
    )

    candidates = []

    for href in hrefs:

        absolute = urljoin(
            r.url,
            href,
        )

        lower = absolute.lower()

        if (
            ".zip" not in lower
            and ".xlsx" not in lower
            and ".xls" not in lower
        ):
            continue

        score = score_candidate(
            family,
            absolute,
        )

        if score > 0:

            candidates.append(
                (
                    score,
                    absolute,
                )
            )

    # Deduplicate candidates while retaining
    # the highest score for each URL.
    dedup = {}

    for score, url in candidates:

        dedup[url] = max(
            score,
            dedup.get(
                url,
                0,
            ),
        )

    ranked = sorted(
        (
            (score, url)
            for url, score
            in dedup.items()
        ),
        reverse=True,
    )

    if not ranked:

        return (
            status,
            "",
            (
                "No downloadable CMS "
                "artifact discovered"
            ),
        )

    best_score = ranked[0][0]

    best = [
        url
        for score, url
        in ranked
        if score == best_score
    ]

    if len(best) != 1:

        return (
            status,
            "",
            (
                "Ambiguous top-ranked "
                "downloads: "
                + " | ".join(best)
            ),
        )

    return (
        status,
        best[0],
        "",
    )


# ============================================================================
# DIRECT CMS ARTIFACT RECOVERY
# ============================================================================

def build_fallback_url(
    family: Family,
    month: int,
) -> str:

    month_name = MONTH_NAMES[
        month
    ]

    if family.code == "CPSC":

        return (
            "https://www.cms.gov/files/zip/"
            f"monthly-enrollment-cpsc-"
            f"{month_name}-{YEAR}.zip"
        )

    if family.code == "SCP":

        return (
            "https://www.cms.gov/files/zip/"
            f"ma-enrollment-statecountyplan-"
            f"{month_name}-{YEAR}.zip"
        )

    if family.code == "SNP":

        return (
            "https://www.cms.gov/files/zip/"
            f"snp-comprehensive-report-"
            f"{month_name}-{YEAR}.zip"
        )

    raise RuntimeError(
        f"Unsupported family: {family.code}"
    )


def test_official_artifact(
    url: str,
) -> tuple[bool, str]:

    try:

        r = session.get(
            url,
            timeout=TIMEOUT_PAGE,
            stream=True,
        )

        status = r.status_code

        content_type = (
            r.headers.get(
                "Content-Type",
                "",
            )
            .lower()
        )

        first = next(
            r.iter_content(
                chunk_size=4
            ),
            b"",
        )

        r.close()

        valid = (
            status == 200
            and first[:2] == b"PK"
        )

        if valid:

            return (
                True,
                (
                    f"HTTP {status}; "
                    f"{content_type}; "
                    "ZIP signature confirmed"
                ),
            )

        return (
            False,
            (
                f"HTTP {status}; "
                f"{content_type}; "
                "ZIP signature not confirmed"
            ),
        )

    except Exception as exc:

        return (
            False,
            str(exc),
        )


# ============================================================================
# ARCHIVE VALIDATION
# ============================================================================

def validate_archive(
    family: Family,
    path: Path,
) -> tuple[bool, list[str], str]:

    suffix = path.suffix.lower()

    # Historical SNP files could theoretically
    # be direct workbook artifacts.
    if suffix != ".zip":

        if (
            family.code == "SNP"
            and suffix
            in {".xls", ".xlsx"}
        ):

            return (
                True,
                [path.name],
                "Direct SNP workbook",
            )

        return (
            False,
            [],
            "Artifact is not ZIP",
        )

    if not zipfile.is_zipfile(
        path
    ):

        return (
            False,
            [],
            "Invalid ZIP archive",
        )

    with zipfile.ZipFile(
        path
    ) as z:

        members = [
            n
            for n in z.namelist()
            if not n.endswith("/")
        ]

    lower_members = [
        n.lower()
        for n in members
    ]

    if family.code == "CPSC":

        contract = [
            n
            for n in lower_members
            if (
                "contract_info" in n
                and n.endswith(".csv")
            )
        ]

        enrollment = [
            n
            for n in lower_members
            if (
                "enrollment_info" in n
                and n.endswith(".csv")
            )
        ]

        readme = [
            n
            for n in lower_members
            if (
                "read" in n
                and n.endswith(".txt")
            )
        ]

        if len(contract) != 1:

            return (
                False,
                members,
                (
                    "Expected exactly one "
                    "CPSC contract-info CSV"
                ),
            )

        if len(enrollment) != 1:

            return (
                False,
                members,
                (
                    "Expected exactly one "
                    "CPSC enrollment-info CSV"
                ),
            )

        if len(readme) < 1:

            return (
                False,
                members,
                "Expected CPSC README",
            )

    elif family.code == "SCP":

        csvs = [
            n
            for n in lower_members
            if n.endswith(".csv")
        ]

        if len(csvs) < 1:

            return (
                False,
                members,
                (
                    "Expected at least "
                    "one SCP CSV"
                ),
            )

    elif family.code == "SNP":

        workbooks = [
            n
            for n in lower_members
            if (
                n.endswith(".xlsx")
                or n.endswith(".xls")
            )
        ]

        if len(workbooks) < 1:

            return (
                False,
                members,
                (
                    "Expected at least "
                    "one SNP workbook"
                ),
            )

    return (
        True,
        members,
        "",
    )


# ============================================================================
# EXISTING ARTIFACT DISCOVERY
# ============================================================================

def existing_artifact_candidates(
    destination: Path,
    family: Family,
) -> list[Path]:

    if not destination.exists():
        return []

    files = []

    for p in destination.iterdir():

        if not p.is_file():
            continue

        lower = p.name.lower()

        if family.code == "CPSC":

            if (
                "cpsc" in lower
                and lower.endswith(".zip")
            ):
                files.append(p)

        elif family.code == "SCP":

            if (
                (
                    "scp" in lower
                    or "statecountyplan"
                    in lower
                )
                and lower.endswith(".zip")
            ):
                files.append(p)

        elif family.code == "SNP":

            if (
                "snp" in lower
                and (
                    lower.endswith(".zip")
                    or lower.endswith(".xlsx")
                    or lower.endswith(".xls")
                )
            ):
                files.append(p)

    return sorted(
        files
    )


# ============================================================================
# SINGLE SOURCE-MONTH ACQUISITION
# ============================================================================

def acquire_one(
    family: Family,
    month: int,
) -> dict:

    landing_url = (
        family
        .landing_template
        .format(
            year=YEAR,
            month=month,
        )
    )

    destination = (
        ROOT
        / family.destination
        / str(YEAR)
        / f"{month:02d}"
    )

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    row = {
        "family": family.code,
        "year": YEAR,
        "month": f"{month:02d}",
        "status": "FAIL",
        "discovery_method": "",
        "landing_url": landing_url,
        "landing_http_status": "",
        "download_url": "",
        "local_path": "",
        "bytes": "",
        "sha256": "",
        "retrieved_utc": "",
        "archive_valid": "",
        "member_count": "",
        "members": "",
        "note": "",
    }

    print()
    print(
        f"[{family.code} "
        f"{YEAR}-{month:02d}]"
    )

    # ----------------------------------------------------------------
    # STEP 1
    # Attempt normal discovery from official CMS landing page.
    # ----------------------------------------------------------------

    try:

        (
            http_status,
            download_url,
            discovery_note,
        ) = discover_download(
            family,
            landing_url,
        )

    except Exception as exc:

        http_status = ""
        download_url = ""
        discovery_note = (
            "Landing discovery exception: "
            f"{exc}"
        )

    row[
        "landing_http_status"
    ] = http_status

    # ----------------------------------------------------------------
    # STEP 2
    # If landing-page discovery fails, test the corresponding official
    # cms.gov artifact URL. This is explicitly recorded as recovery.
    # ----------------------------------------------------------------

    if download_url:

        row[
            "discovery_method"
        ] = "LANDING_PAGE_DISCOVERY"

        row[
            "download_url"
        ] = download_url

        print(
            "  Landing:",
            http_status,
        )

        print(
            "  Source:",
            download_url,
        )

    else:

        print(
            "  Landing discovery failed:",
            discovery_note,
        )

        fallback_url = (
            build_fallback_url(
                family,
                month,
            )
        )

        print(
            (
                "  Testing official CMS "
                "artifact fallback:"
            ),
            fallback_url,
        )

        (
            fallback_valid,
            fallback_note,
        ) = test_official_artifact(
            fallback_url
        )

        if not fallback_valid:

            row["note"] = (
                discovery_note
                + "; official CMS artifact "
                "fallback failed: "
                + fallback_note
            )

            print(
                "  FAIL:",
                row["note"],
            )

            return row

        download_url = fallback_url

        row[
            "download_url"
        ] = download_url

        row[
            "discovery_method"
        ] = (
            "DIRECT_CMS_ARTIFACT_RECOVERY"
        )

        row["note"] = (
            discovery_note
            + "; "
            + fallback_note
        )

        print(
            "  Recovery: "
            "DIRECT_CMS_ARTIFACT_RECOVERY"
        )

        print(
            "  Source:",
            download_url,
        )

    # ----------------------------------------------------------------
    # STEP 3
    # Determine expected local artifact.
    # ----------------------------------------------------------------

    filename = safe_filename_from_url(
        download_url
    )

    target = (
        destination
        / filename
    )

    existing = (
        existing_artifact_candidates(
            destination,
            family,
        )
    )

    if target.exists():

        local_path = target

        source_mode = (
            "EXISTING_EXACT"
        )

    elif len(existing) == 1:

        local_path = existing[0]

        source_mode = (
            "EXISTING_MONTH_ARTIFACT"
        )

    elif len(existing) > 1:

        row["note"] = (
            row["note"]
            + (
                "; "
                if row["note"]
                else ""
            )
            + (
                "Multiple existing "
                "candidate artifacts: "
            )
            + " | ".join(
                str(p)
                for p in existing
            )
        )

        print(
            "  FAIL:",
            row["note"],
        )

        return row

    else:

        local_path = target

        source_mode = "DOWNLOAD"

    # ----------------------------------------------------------------
    # STEP 4
    # Download only if necessary.
    # ----------------------------------------------------------------

    if source_mode == "DOWNLOAD":

        try:

            with session.get(
                download_url,
                timeout=TIMEOUT_DOWNLOAD,
                stream=True,
            ) as r:

                r.raise_for_status()

                with local_path.open(
                    "wb"
                ) as f:

                    for chunk in (
                        r.iter_content(
                            chunk_size=1024 * 1024
                        )
                    ):

                        if chunk:
                            f.write(chunk)

            retrieved = utc_now()

        except Exception as exc:

            # Remove a partial download if one exists.
            if local_path.exists():

                try:
                    local_path.unlink()
                except OSError:
                    pass

            row["note"] = (
                row["note"]
                + (
                    "; "
                    if row["note"]
                    else ""
                )
                + (
                    "Download exception: "
                    f"{exc}"
                )
            )

            print(
                "  FAIL:",
                row["note"],
            )

            return row

    else:

        retrieved = (
            "PREEXISTING_ARTIFACT"
        )

    # ----------------------------------------------------------------
    # STEP 5
    # Validate the preserved artifact.
    # ----------------------------------------------------------------

    try:

        (
            valid,
            members,
            validation_note,
        ) = validate_archive(
            family,
            local_path,
        )

    except Exception as exc:

        valid = False
        members = []

        validation_note = (
            "Validation exception: "
            f"{exc}"
        )

    row[
        "local_path"
    ] = str(local_path)

    row[
        "bytes"
    ] = local_path.stat().st_size

    row[
        "sha256"
    ] = sha256_file(
        local_path
    )

    row[
        "retrieved_utc"
    ] = retrieved

    row[
        "archive_valid"
    ] = (
        "YES"
        if valid
        else "NO"
    )

    row[
        "member_count"
    ] = len(members)

    row[
        "members"
    ] = " | ".join(
        members
    )

    # ----------------------------------------------------------------
    # STEP 6
    # Final source-month result.
    # ----------------------------------------------------------------

    if valid:

        row["status"] = "PASS"

        notes = []

        if row["note"]:
            notes.append(
                row["note"]
            )

        notes.append(
            source_mode
        )

        if validation_note:
            notes.append(
                validation_note
            )

        row["note"] = "; ".join(
            notes
        )

        print(
            "  PASS:",
            (
                f"{local_path.stat().st_size:,} "
                "bytes"
            ),
        )

        print(
            "  SHA256:",
            row["sha256"],
        )

        print(
            "  Discovery:",
            row["discovery_method"],
        )

    else:

        row["note"] = (
            row["note"]
            + (
                "; "
                if row["note"]
                else ""
            )
            + validation_note
        )

        print(
            "  FAIL:",
            row["note"],
        )

    time.sleep(
        REQUEST_DELAY_SECONDS
    )

    return row


# ============================================================================
# MANIFEST
# ============================================================================

def write_manifest(
    rows: list[dict],
) -> None:

    MANIFEST_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with MANIFEST_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=MANIFEST_FIELDS,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    print("=" * 96)

    print(
        "CMS MEDICARE ADVANTAGE "
        "2022 VALIDATION-SOURCE ACQUISITION"
    )

    print("=" * 96)

    print()

    print(
        "Required inventory: "
        "CPSC 12 + SCP 12 + SNP 12 "
        "= 36 source-months"
    )

    rows = []

    for family_code in (
        "CPSC",
        "SCP",
        "SNP",
    ):

        family = FAMILIES[
            family_code
        ]

        print()
        print("=" * 96)

        print(
            f"{family.code}: "
            f"{family.description}"
        )

        print("=" * 96)

        for month in range(
            1,
            13,
        ):

            row = acquire_one(
                family,
                month,
            )

            rows.append(
                row
            )

            # Incremental manifest protects provenance
            # if execution is interrupted.
            write_manifest(
                rows
            )

    # ----------------------------------------------------------------
    # COMPLETENESS
    # ----------------------------------------------------------------

    print()
    print("=" * 96)
    print("COMPLETENESS")
    print("=" * 96)

    family_counts = {}

    for family_code in (
        "CPSC",
        "SCP",
        "SNP",
    ):

        subset = [
            r
            for r in rows
            if (
                r["family"]
                == family_code
            )
        ]

        passed = sum(
            r["status"] == "PASS"
            for r in subset
        )

        family_counts[
            family_code
        ] = passed

        print(
            f"{family_code:5} "
            f"{passed:>2}/12 PASS"
        )

    total_pass = sum(
        r["status"] == "PASS"
        for r in rows
    )

    print("-" * 96)

    print(
        f"TOTAL {total_pass:>2}/36 PASS"
    )

    print()

    print(
        "Manifest:",
        MANIFEST_PATH,
    )

    # ----------------------------------------------------------------
    # RECOVERY PROVENANCE SUMMARY
    # ----------------------------------------------------------------

    recovered = [
        r
        for r in rows
        if (
            r["discovery_method"]
            == "DIRECT_CMS_ARTIFACT_RECOVERY"
        )
    ]

    print()
    print("=" * 96)
    print("DIRECT CMS ARTIFACT RECOVERIES")
    print("=" * 96)

    if recovered:

        for row in recovered:

            print(
                f"{row['family']} "
                f"{row['year']}-"
                f"{row['month']} "
                f"{row['status']} "
                f"{row['download_url']}"
            )

    else:

        print("None")

    # ----------------------------------------------------------------
    # FINAL STATUS
    # ----------------------------------------------------------------

    complete = (
        family_counts.get(
            "CPSC",
            0,
        ) == 12
        and family_counts.get(
            "SCP",
            0,
        ) == 12
        and family_counts.get(
            "SNP",
            0,
        ) == 12
    )

    print()
    print("=" * 96)

    if complete:

        print(
            "STATUS: 2022 CMS MA "
            "VALIDATION-SOURCE "
            "ACQUISITION COMPLETE"
        )

        print("=" * 96)

        return 0

    print(
        "STATUS: INCOMPLETE — "
        "DO NOT PROCEED TO "
        "PAYMENT RECONSTRUCTION"
    )

    print("=" * 96)

    print()
    print("FAILED SOURCE-MONTHS")
    print("-" * 96)

    for row in rows:

        if row["status"] != "PASS":

            print(
                f"{row['family']} "
                f"{row['year']}-"
                f"{row['month']}: "
                f"{row['note']}"
            )

    return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )