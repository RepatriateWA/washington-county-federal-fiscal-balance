from __future__ import annotations

import argparse
import csv
import hashlib
from html import parser
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse
import os

import requests


# ============================================================================
# PATHS / CONSTANTS
# ============================================================================

ROOT = Path(__file__).resolve().parents[1]

MA_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_advantage"
)

SELECTION_MANIFEST = (
    MA_ROOT
    / "validation"
    / "source_acquisition"
    / "cms_ma_partc_artifact_selection_manifest.csv"
)

ACQUISITION_DIR = (
    MA_ROOT
    / "validation"
    / "source_acquisition"
)

ACQUISITION_MANIFEST = (
    ACQUISITION_DIR
    / "cms_ma_partc_source_acquisition_manifest.csv"
)

TIMEOUT_DOWNLOAD = 180
REQUEST_DELAY_SECONDS = 0.5

RECOGNIZED_TYPES = {
    "ZIP": ".zip",
    "XLSX": ".xlsx",
    "XLS": ".xls",
    "CSV": ".csv",
    "PDF": ".pdf",
}

DESTINATIONS = {
    "CPSC": "enrollment",
    "SCC_SCP": "enrollment_controls",
    "SNP": "snp",
    "PLAN_PAYMENT": "plan_payment",
}

MANIFEST_FIELDS = [
    "source_type",
    "period",
    "payment_year",
    "discovery_status",
    "selection_status",
    "selected_url",
    "selected_type",
    "selected_link_text",
    "selection_reason",
    "candidate_count",
    "status",
    "source_mode",
    "final_url",
    "http_status",
    "content_type",
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

session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 "
            "WCFFBP CMS Medicare Advantage "
            "source acquisition"
        )
    }
)


# ============================================================================
# BASIC HELPERS
# ============================================================================

def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def recognized_extension(
    value: str,
) -> str:
    """
    Return a recognized extension from a URL path or filename.

    CMS numeric revision suffixes such as .zip-0 are normalized.
    """

    value = unquote(
        str(value)
    ).strip()

    path = urlparse(value).path

    name = Path(path).name

    lower = name.lower()

    lower = re.sub(
        r"(\.(?:zip|xlsx|xls|csv|pdf))-\d+$",
        r"\1",
        lower,
    )

    for extension in (
        ".xlsx",
        ".zip",
        ".xls",
        ".csv",
        ".pdf",
    ):
        if lower.endswith(extension):
            return extension

    return ""


def filename_from_selection(
    row: dict,
) -> str:
    """
    Determine the preserved local filename without guessing.

    1. Prefer a recognized filename in selected_url.
    2. For legacy extensionless CMS URLs, use selected_link_text
       only when it itself supplies a recognized filename.
    3. Otherwise fail closed.
    """

    selected_url = row[
        "selected_url"
    ].strip()

    selected_text = row[
        "selected_link_text"
    ].strip()

    selected_type = row[
        "selected_type"
    ].strip().upper()

    expected_extension = (
        RECOGNIZED_TYPES.get(
            selected_type
        )
    )

    if not expected_extension:
        raise ValueError(
            "Unsupported selected_type: "
            f"{selected_type!r}"
        )

    url_extension = (
        recognized_extension(
            selected_url
        )
    )

    if url_extension:

        if (
            url_extension
            != expected_extension
        ):
            raise ValueError(
                "selected_url extension "
                f"{url_extension!r} conflicts "
                "with selected_type "
                f"{selected_type!r}"
            )

        filename = Path(
            unquote(
                urlparse(
                    selected_url
                ).path
            )
        ).name

        # Normalize CMS numeric revision suffix.
        filename = re.sub(
            r"(\.(?:zip|xlsx|xls|csv|pdf))-\d+$",
            r"\1",
            filename,
            flags=re.IGNORECASE,
        )

        return filename

    text_extension = (
        recognized_extension(
            selected_text
        )
    )

    if text_extension:

        if (
            text_extension
            != expected_extension
        ):
            raise ValueError(
                "selected_link_text extension "
                f"{text_extension!r} conflicts "
                "with selected_type "
                f"{selected_type!r}"
            )

        filename = Path(
            selected_text
        ).name

        if not filename:
            raise ValueError(
                "selected_link_text did not "
                "yield a filename"
            )

        return filename

    raise ValueError(
        "Neither selected_url nor "
        "selected_link_text supplies a "
        "recognized filename extension"
    )


# ============================================================================
# SELECTION MANIFEST
# ============================================================================

def read_selection_manifest() -> list[dict]:

    if not SELECTION_MANIFEST.exists():
        raise FileNotFoundError(
            SELECTION_MANIFEST
        )

    with SELECTION_MANIFEST.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        rows = list(
            csv.DictReader(f)
        )

    return rows


def validate_selection_manifest(
    rows: list[dict],
) -> None:

    if len(rows) != 371:
        raise ValueError(
            "Selection manifest row count "
            f"is {len(rows)}, expected 371"
        )

    required_fields = {
        "source_type",
        "period",
        "payment_year",
        "discovery_status",
        "selection_status",
        "selected_url",
        "selected_type",
        "selected_link_text",
        "selection_reason",
        "candidate_count",
    }

    if rows:

        missing = (
            required_fields
            - set(rows[0].keys())
        )

        if missing:
            raise ValueError(
                "Selection manifest missing "
                "fields: "
                + ", ".join(
                    sorted(missing)
                )
            )

    identities = set()

    family_counts = {
        "CPSC": 0,
        "SCC_SCP": 0,
        "SNP": 0,
        "PLAN_PAYMENT": 0,
    }

    for row in rows:

        source_type = (
            row["source_type"]
            .strip()
        )

        if source_type not in family_counts:
            raise ValueError(
                "Unexpected source_type: "
                f"{source_type!r}"
            )

        if (
            row["discovery_status"]
            .strip()
            != "AVAILABLE_OFFICIAL"
        ):
            raise ValueError(
                "Non-available discovery row: "
                f"{source_type} "
                f"{row['period']} "
                f"{row['payment_year']}"
            )

        if (
            row["selection_status"]
            .strip()
            != "PASS"
        ):
            raise ValueError(
                "Non-PASS selection row: "
                f"{source_type} "
                f"{row['period']} "
                f"{row['payment_year']}"
            )

        if (
            row["candidate_count"]
            .strip()
            != "1"
        ):
            raise ValueError(
                "candidate_count != 1: "
                f"{source_type} "
                f"{row['period']} "
                f"{row['payment_year']}"
            )

        if not row[
            "selected_url"
        ].strip():
            raise ValueError(
                "Missing selected_url"
            )

        # Exercise filename resolution now,
        # before any network operation.
        filename_from_selection(
            row
        )

        if source_type == "PLAN_PAYMENT":

            identity = (
                source_type,
                row[
                    "payment_year"
                ].strip(),
            )

        else:

            identity = (
                source_type,
                row[
                    "period"
                ].strip(),
            )

        if identity in identities:
            raise ValueError(
                "Duplicate source identity: "
                f"{identity}"
            )

        identities.add(
            identity
        )

        family_counts[
            source_type
        ] += 1

    expected = {
        "CPSC": 120,
        "SCC_SCP": 120,
        "SNP": 120,
        "PLAN_PAYMENT": 11,
    }

    if family_counts != expected:
        raise ValueError(
            "Unexpected family counts: "
            f"{family_counts}"
        )


# ============================================================================
# DESTINATION
# ============================================================================

def normalize_payment_year(
    value: str,
) -> str:
    """
    Normalize a manifest payment year to YYYY.

    Pandas may serialize an integer year as a floating-point
    string (for example 2022.0) when the source column also
    contains blank values for monthly records.
    """

    value = str(value).strip()

    if re.fullmatch(
        r"\d{4}",
        value,
    ):
        return value

    match = re.fullmatch(
        r"(\d{4})\.0+",
        value,
    )

    if match:
        return match.group(1)

    raise ValueError(
        "Invalid payment_year: "
        f"{value!r}"
    )

def destination_for_row(
    row: dict,
) -> Path:

    source_type = (
        row["source_type"]
        .strip()
    )

    destination_name = (
        DESTINATIONS[
            source_type
        ]
    )

    if source_type == "PLAN_PAYMENT":

        year = normalize_payment_year(
            row["payment_year"]
        )

        return (
            MA_ROOT
            / destination_name
            / year
        )

    period = (
        row["period"]
        .strip()
    )

    if not re.fullmatch(
        r"\d{4}-\d{2}",
        period,
    ):
        raise ValueError(
            "Invalid period: "
            f"{period!r}"
        )

    year, month = (
        period.split("-")
    )

    if not (
        1 <= int(month) <= 12
    ):
        raise ValueError(
            "Invalid month: "
            f"{month!r}"
        )

    return (
        MA_ROOT
        / destination_name
        / year
        / month
    )


# ============================================================================
# ARTIFACT VALIDATION
# ============================================================================

def validate_artifact(
    row: dict,
    path: Path,
) -> tuple[
    bool,
    list[str],
    str,
]:

    selected_type = (
        row["selected_type"]
        .strip()
        .upper()
    )

    if not path.exists():
        return (
            False,
            [],
            "Artifact does not exist",
        )

    if path.stat().st_size <= 0:
        return (
            False,
            [],
            "Artifact is empty",
        )

    if selected_type != "ZIP":
        return (
            True,
            [],
            (
                "Non-ZIP artifact preserved; "
                "detailed schema validation "
                "deferred"
            ),
        )

    if not zipfile.is_zipfile(
        path
    ):
        return (
            False,
            [],
            "File is not a valid ZIP archive",
        )

    try:

        with zipfile.ZipFile(
            path,
            "r",
        ) as zf:

            bad_member = (
                zf.testzip()
            )

            members = (
                zf.namelist()
            )

    except Exception as exc:

        return (
            False,
            [],
            "ZIP validation exception: "
            f"{exc}",
        )

    if bad_member is not None:
        return (
            False,
            members,
            "ZIP CRC failure: "
            f"{bad_member}",
        )

    if not members:
        return (
            False,
            [],
            "ZIP archive has no members",
        )

    return (
        True,
        members,
        "ZIP integrity PASS",
    )


# ============================================================================
# ACQUISITION
# ============================================================================

def acquire_one(
    selection_row: dict,
) -> dict:

    row = {
        field: ""
        for field in MANIFEST_FIELDS
    }

    for field in (
        "source_type",
        "period",
        "payment_year",
        "discovery_status",
        "selection_status",
        "selected_url",
        "selected_type",
        "selected_link_text",
        "selection_reason",
        "candidate_count",
    ):
        row[field] = (
            selection_row.get(
                field,
                "",
            )
        )

    row["status"] = "FAIL"

    source_type = (
        row["source_type"]
        .strip()
    )

    identity = (
        row["payment_year"]
        if source_type
        == "PLAN_PAYMENT"
        else row["period"]
    )

    print()
    print(
        f"[{source_type} {identity}]"
    )

    try:

        filename = (
            filename_from_selection(
                selection_row
            )
        )

        destination = (
            destination_for_row(
                selection_row
            )
        )

    except Exception as exc:

        row["note"] = (
            "Selection/destination "
            f"exception: {exc}"
        )

        print(
            "  FAIL:",
            row["note"],
        )

        return row

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    target = (
        destination
        / filename
    )

    selected_url = (
        row["selected_url"]
        .strip()
    )

    # ------------------------------------------------------------
    # Existing exact artifact is reused.
    #
    # We intentionally do not substitute another file merely
    # because one happens to exist in the destination directory.
    # ------------------------------------------------------------

    if target.exists():

        local_path = target

        row[
            "source_mode"
        ] = "PREEXISTING_EXACT"

        row[
            "final_url"
        ] = selected_url

        row[
            "retrieved_utc"
        ] = "PREEXISTING_ARTIFACT"

        print(
            "  Existing:",
            local_path,
        )

    else:

        local_path = target

        partial = (
            target.with_name(
                target.name
                + ".partial"
            )
        )

        if partial.exists():
            partial.unlink()

        try:

            with session.get(
                selected_url,
                timeout=TIMEOUT_DOWNLOAD,
                stream=True,
                allow_redirects=True,
            ) as response:

                row[
                    "http_status"
                ] = str(
                    response.status_code
                )

                row[
                    "final_url"
                ] = str(
                    response.url
                )

                row[
                    "content_type"
                ] = (
                    response.headers.get(
                        "Content-Type",
                        "",
                    )
                )

                response.raise_for_status()

                with partial.open(
                    "wb"
                ) as f:

                    for chunk in (
                        response.iter_content(
                            chunk_size=(
                                1024 * 1024
                            )
                        )
                    ):

                        if chunk:
                            f.write(
                                chunk
                            )

            partial.replace(
                target
            )

            row[
                "source_mode"
            ] = "DOWNLOAD"

            row[
                "retrieved_utc"
            ] = utc_now()

            print(
                "  Selected:",
                selected_url,
            )

            if (
                row["final_url"]
                != selected_url
            ):
                print(
                    "  Final URL:",
                    row["final_url"],
                )

        except Exception as exc:

            if partial.exists():

                try:
                    partial.unlink()
                except OSError:
                    pass

            row["note"] = (
                "Download exception: "
                f"{exc}"
            )

            print(
                "  FAIL:",
                row["note"],
            )

            return row

    # ------------------------------------------------------------
    # Validate, checksum, preserve provenance.
    # ------------------------------------------------------------

    try:

        (
            valid,
            members,
            validation_note,
        ) = validate_artifact(
            selection_row,
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
    ] = str(
        local_path.stat().st_size
    )

    row[
        "sha256"
    ] = sha256_file(
        local_path
    )

    row[
        "archive_valid"
    ] = (
        "YES"
        if valid
        else "NO"
    )

    row[
        "member_count"
    ] = str(
        len(members)
    )

    row[
        "members"
    ] = " | ".join(
        members
    )

    row[
        "note"
    ] = validation_note

    if valid:

        row["status"] = "PASS"

        print(
            "  PASS:",
            f"{local_path.stat().st_size:,}",
            "bytes",
        )

        print(
            "  SHA256:",
            row["sha256"],
        )

        print(
            "  Mode:",
            row["source_mode"],
        )

    else:

        print(
            "  FAIL:",
            validation_note,
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
    """
    Write the acquisition manifest atomically.

    The completed CSV is first written to a sibling temporary
    file and then atomically replaces the live manifest. This
    avoids repeatedly truncating the live manifest during a
    long acquisition run.
    """

    ACQUISITION_MANIFEST.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_manifest = (
        ACQUISITION_MANIFEST.with_name(
            ACQUISITION_MANIFEST.name
            + ".tmp"
        )
    )

    fieldnames = [
        "source_type",
        "period",
        "payment_year",
        "discovery_status",
        "selection_status",
        "selected_url",
        "selected_type",
        "selected_link_text",
        "selection_reason",
        "candidate_count",
        "status",
        "source_mode",
        "final_url",
        "http_status",
        "content_type",
        "local_path",
        "bytes",
        "sha256",
        "retrieved_utc",
        "archive_valid",
        "member_count",
        "members",
        "note",
    ]

    try:

        with temp_manifest.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )

            writer.writeheader()

            writer.writerows(rows)

            f.flush()

            os.fsync(
                f.fileno()
            )

        os.replace(
            temp_manifest,
            ACQUISITION_MANIFEST,
        )

    finally:

        if temp_manifest.exists():

            try:
                temp_manifest.unlink()
            except OSError:
                pass

def preflight_destinations(
    rows: list[dict],
) -> None:
    """
    Resolve every selected source to its canonical local artifact path
    before acquisition begins.

    Fail closed if two required source identities would map to the same
    local path.
    """

    paths: dict[str, tuple[str, str]] = {}

    for row in rows:

        source_type = row[
            "source_type"
        ].strip()

        identity = (
            normalize_payment_year(
                row["payment_year"]
            )
            if source_type == "PLAN_PAYMENT"
            else row["period"].strip()
        )

        destination = (
            destination_for_row(row)
        )

        filename = (
            filename_from_selection(row)
        )

        target = str(
            (
                destination
                / filename
            ).resolve()
        )

        key = target.lower()

        if key in paths:

            previous = paths[key]

            raise ValueError(
                "Canonical destination collision: "
                f"{previous} and "
                f"{(source_type, identity)} "
                f"both map to {target}"
            )

        paths[key] = (
            source_type,
            identity,
        )

    if len(paths) != 371:
        raise ValueError(
            "Canonical destination count "
            f"is {len(paths)}, expected 371"
        )
# ============================================================================
# TEST SELECTION
# ============================================================================

def select_test_rows(
    rows: list[dict],
) -> list[dict]:
    """
    Three deliberately different CMS source cases:

    1. Legacy extensionless CPSC URL.
    2. Legacy extensionless SCC/SCP URL.
    3. Annual Plan Payment source.
    """

    wanted = {
        (
            "CPSC",
            "2016-12",
        ),
        (
            "SCC_SCP",
            "2016-02",
        ),
        (
            "PLAN_PAYMENT",
            "2022",
        ),
    }

    selected = []

    for row in rows:

        source_type = (
            row["source_type"]
            .strip()
        )

        identity = (
            normalize_payment_year(
                row["payment_year"]
            )
            if source_type 
            == "PLAN_PAYMENT"
            else row["period"].strip()
        )

        if (
            source_type,
            identity,
        ) in wanted:

            selected.append(
                row
            )

    found = {
        (
            r["source_type"].strip(),
            (
                normalize_payment_year(
                    r["payment_year"]
            )
                if r[
                    "source_type"
                ].strip()
                == "PLAN_PAYMENT"
                else r["period"].strip()
            ),
        )
        for r in selected
    }

    if found != wanted:
        raise ValueError(
            "Test source selection "
            "incomplete. Found: "
            f"{sorted(found)}"
        )

    return selected


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Acquire selected CMS Medicare "
            "Advantage Part C source artifacts."
        )
    )

    parser.add_argument(
        "--select-only",
        action="store_true",
        help=(
            "Validate the 371-row selection "
            "manifest without downloading."
        ),
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help=(
            "Acquire only the three "
            "controlled test artifacts."
        ),
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Acquire or validate all 371 "
            "required source artifacts."
        ),
    )

    args = parser.parse_args()

    modes_selected = sum(
        (
            args.select_only,
            args.test,
            args.all,
        )
    )

    if modes_selected != 1:
        parser.error(
            "Choose exactly one mode: "
            "--select-only, --test, or --all."
        )

    print("=" * 96)
    print(
        "CMS MEDICARE ADVANTAGE PART C "
        "— SOURCE ACQUISITION"
    )
    print("=" * 96)

    rows = (
        read_selection_manifest()
    )

    validate_selection_manifest(
        rows
    )

    preflight_destinations(
    rows
    )

    print()
    print(
        "Selection manifest: PASS"
    )

    print(
        "Required source slots:",
        len(rows),
    )

    print(
        "Canonical local paths:",
        len(rows),
        "unique"
    )

    print(
        "CPSC=120 | SCC_SCP=120 | "
        "SNP=120 | PLAN_PAYMENT=11"
    )

    if args.select_only:

        print()
        print(
            "RESULT: SELECTION MANIFEST "
            "VALIDATED; NO NETWORK "
            "ACQUISITION PERFORMED"
        )

        return 0

    if args.test:

        acquisition_source_rows = (
            select_test_rows(
                rows
            )
        )

        run_label = "TEST"

    else:

        acquisition_source_rows = rows

        run_label = "FULL"

    print()
    print(
        f"{run_label} MODE: "
        f"{len(acquisition_source_rows)} artifacts"
    )

    acquisition_rows = []

    for selection_row in acquisition_source_rows:

        result = acquire_one(
            selection_row
        )

        acquisition_rows.append(
            result
        )

        # Incremental manifest protects
        # provenance if execution is interrupted.
        write_manifest(
            acquisition_rows
        )

    passed = sum(
        row["status"] == "PASS"
        for row in acquisition_rows
    )

    print()
    print("=" * 96)
    print(
        f"{run_label} ACQUISITION SUMMARY"
    )
    print("=" * 96)

    for row in acquisition_rows:

        identity = (
            row["payment_year"]
            if row["source_type"]
            == "PLAN_PAYMENT"
            else row["period"]
        )

        print(
            f"{row['source_type']:12} "
            f"{identity:7} "
            f"{row['status']:4} "
            f"{row['source_mode']}"
        )

    print("-" * 96)

    print(
        f"TOTAL {passed}/"
        f"{len(acquisition_rows)} PASS"
    )

    print()
    print(
        "Manifest:",
        ACQUISITION_MANIFEST,
    )

    if passed != len(
        acquisition_rows
    ):
        print()
        print(
            f"RESULT: {run_label} ACQUISITION "
            "FAILED"
        )

        return 1

    print()
    print(
        f"RESULT: {run_label} ACQUISITION PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
