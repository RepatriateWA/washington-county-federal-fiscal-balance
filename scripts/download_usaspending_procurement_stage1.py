from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


API_URL = (
    "https://api.usaspending.gov/"
    "api/v2/search/spending_by_transaction/"
)

CONTRACT_AWARD_TYPE_CODES = ["A", "B", "C", "D"]

REPO_ROOT = Path(__file__).resolve().parents[1]

FIELDS = [
    "internal_id",
    "generated_internal_id",
    "Award ID",
    "Award Type",
    "Action Date",
    "Action Type",
    "Mod",
    "Transaction Amount",
    "Transaction Description",
    "Recipient Name",
    "Recipient UEI",
    "recipient_id",
    "pop_city_name",
    "pop_state_code",
    "pop_country_name",
    "naics_code",
    "naics_description",
    "product_or_service_code",
    "product_or_service_description",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Funding Agency",
    "Funding Sub Agency",
    "def_codes",
]


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    max_attempts: int = 8,
    initial_delay: float = 5.0,
) -> dict[str, Any]:
    """
    POST JSON to USAspending with retry/backoff for transient HTTP failures.

    Retries:
        429 Too Many Requests
        500 Internal Server Error
        502 Bad Gateway
        503 Service Unavailable
        504 Gateway Timeout

    Non-transient HTTP errors fail immediately.
    """

    retryable_statuses = {
        429,
        500,
        502,
        503,
        504,
    }

    data = json.dumps(payload).encode("utf-8")

    for attempt in range(1, max_attempts + 1):

        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "WCFFBP-USAspending-Acquisition/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=120,
            ) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            body = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            if exc.code not in retryable_statuses:
                raise RuntimeError(
                    f"USAspending HTTP {exc.code} from {url}\n{body}"
                ) from exc

            if attempt >= max_attempts:
                raise RuntimeError(
                    "USAspending transient HTTP failure exceeded retry limit.\n"
                    f"HTTP status: {exc.code}\n"
                    f"Attempts: {attempt}\n"
                    f"URL: {url}\n"
                    f"Response body:\n{body}"
                ) from exc

            retry_after = exc.headers.get(
                "Retry-After"
            )

            if retry_after:
                try:
                    delay = float(
                        retry_after
                    )
                except ValueError:
                    delay = initial_delay * (
                        2 ** (attempt - 1)
                    )
            else:
                delay = initial_delay * (
                    2 ** (attempt - 1)
                )

            # Cap individual waits at five minutes.
            delay = min(
                delay,
                300.0,
            )

            print(
                f"USAspending HTTP {exc.code}; "
                f"retry {attempt}/{max_attempts} "
                f"in {delay:.1f} seconds..."
            )

            time.sleep(
                delay
            )

        except (
            urllib.error.URLError,
            TimeoutError,
        ) as exc:

            if attempt >= max_attempts:
                raise RuntimeError(
                    "USAspending network failure exceeded retry limit.\n"
                    f"Attempts: {attempt}\n"
                    f"URL: {url}\n"
                    f"Error: {exc}"
                ) from exc

            delay = min(
                initial_delay * (
                    2 ** (attempt - 1)
                ),
                300.0,
            )

            print(
                "USAspending network error; "
                f"retry {attempt}/{max_attempts} "
                f"in {delay:.1f} seconds..."
            )

            time.sleep(
                delay
            )

    raise RuntimeError(
        "Unexpected retry-loop termination."
    )


def fiscal_year_dates(
    fiscal_year: int,
) -> tuple[str, str]:
    return (
        f"{fiscal_year - 1}-10-01",
        f"{fiscal_year}-09-30",
    )


def build_filters(
    fiscal_year: int,
) -> dict[str, Any]:
    start_date, end_date = fiscal_year_dates(
        fiscal_year
    )

    return {
        "time_period": [
            {
                "start_date": start_date,
                "end_date": end_date,
            }
        ],
        "award_type_codes": CONTRACT_AWARD_TYPE_CODES,
        "place_of_performance_locations": [
            {
                "country": "USA",
                "state": "WA",
            }
        ],
    }


def atomic_write_json(
    path: Path,
    value: Any,
) -> None:
    """
    Write JSON to a temporary file in the same directory,
    then atomically replace the destination.

    This protects checkpoint/provenance files from partial writes.
    """
    temp_path = path.with_name(
        f"{path.name}.tmp"
    )

    text = json.dumps(
        value,
        indent=2,
        sort_keys=True,
    )

    with temp_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(
        temp_path,
        path,
    )


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def provisional_identity(
    row: dict[str, Any],
) -> tuple[Any, ...]:
    """
    Stage-1 provisional identity only.

    This is NOT the canonical USAspending transaction ID.
    Stage 2 will resolve true transaction identity.
    """
    return (
        row.get("generated_internal_id"),
        row.get("Action Date"),
        row.get("Mod"),
        row.get("Transaction Amount"),
        row.get("Transaction Description"),
    )


def load_json(
    path: Path,
) -> dict[str, Any]:
    return json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )


def get_page_number(
    path: Path,
) -> int:
    stem = path.stem

    if not stem.startswith("page_"):
        raise ValueError(
            f"Unexpected page filename: {path.name}"
        )

    return int(
        stem.split("_", 1)[1]
    )


def inspect_page_archive(
    pages_dir: Path,
) -> tuple[list[Path], int, int]:
    """
    Validate the archived page sequence.

    Returns:
        page_paths
        highest_contiguous_page
        archived_row_count
    """
    page_paths = sorted(
        pages_dir.glob("page_*.json"),
        key=get_page_number,
    )

    if not page_paths:
        return [], 0, 0

    expected_page = 1
    archived_row_count = 0

    for page_path in page_paths:
        page_number = get_page_number(
            page_path
        )

        if page_number != expected_page:
            raise RuntimeError(
                "Archived USAspending page sequence contains a gap.\n"
                f"Expected page {expected_page:,}, "
                f"found page {page_number:,}.\n"
                "Acquisition stopped to preserve audit integrity."
            )

        response = load_json(
            page_path
        )

        results = response.get(
            "results"
        )

        if not isinstance(
            results,
            list,
        ):
            raise RuntimeError(
                f"Archived page {page_number:,} "
                "does not contain a valid results list."
            )

        metadata = response.get(
            "page_metadata",
            {},
        )

        metadata_page = metadata.get(
            "page"
        )

        if (
            metadata_page is not None
            and int(metadata_page) != page_number
        ):
            raise RuntimeError(
                f"Archived page filename/page metadata mismatch: "
                f"{page_path.name} reports page {metadata_page}."
            )

        archived_row_count += len(
            results
        )

        expected_page += 1

    highest_page = (
        get_page_number(page_paths[-1])
    )

    return (
        page_paths,
        highest_page,
        archived_row_count,
    )


def rebuild_jsonl_from_pages(
    page_paths: list[Path],
    jsonl_path: Path,
) -> int:
    """
    Rebuild the combined Stage-1 JSONL entirely from the
    preserved page archive.

    This makes the page archive authoritative and prevents
    duplicate JSONL rows after interrupted runs.
    """
    temp_path = jsonl_path.with_name(
        f"{jsonl_path.name}.tmp"
    )

    row_count = 0

    with temp_path.open(
        "w",
        encoding="utf-8",
    ) as output:
        for page_path in page_paths:
            response = load_json(
                page_path
            )

            results = response["results"]

            for row in results:
                output.write(
                    json.dumps(
                        row,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )

                row_count += 1

        output.flush()
        os.fsync(output.fileno())

    os.replace(
        temp_path,
        jsonl_path,
    )

    return row_count


def read_checkpoint(
    checkpoint_path: Path,
) -> dict[str, Any] | None:
    if not checkpoint_path.exists():
        return None

    return load_json(
        checkpoint_path
    )


def reconcile_existing_state(
    *,
    fiscal_year: int,
    expected_count: int,
    pages_dir: Path,
    jsonl_path: Path,
    checkpoint_path: Path,
) -> tuple[int, int]:
    """
    Reconcile archived pages, combined JSONL, and checkpoint.

    Returns:
        next_page
        collected_rows
    """
    (
        page_paths,
        highest_page,
        archived_rows,
    ) = inspect_page_archive(
        pages_dir
    )

    checkpoint = read_checkpoint(
        checkpoint_path
    )

    print("-" * 96)
    print("RECOVERY / RECONCILIATION")
    print("-" * 96)

    if checkpoint is None:
        checkpoint_last_page = 0
        checkpoint_rows = 0

        print(
            "Checkpoint ........................ NONE"
        )

    else:
        checkpoint_last_page = int(
            checkpoint.get(
                "last_completed_page",
                0,
            )
            or 0
        )

        checkpoint_rows = int(
            checkpoint.get(
                "collected_rows",
                0,
            )
            or 0
        )

        print(
            f"Checkpoint last completed page .... "
            f"{checkpoint_last_page:,}"
        )

        print(
            f"Checkpoint collected rows .......... "
            f"{checkpoint_rows:,}"
        )

    print()
    print(
        f"Highest archived page .............. "
        f"{highest_page:,}"
    )

    print(
        f"Archived transaction rows .......... "
        f"{archived_rows:,}"
    )

    if archived_rows > expected_count:
        raise RuntimeError(
            "Archived page population exceeds expected transaction count. "
            f"Expected {expected_count:,}; "
            f"archived {archived_rows:,}."
        )

    if page_paths:
        rebuilt_rows = rebuild_jsonl_from_pages(
            page_paths,
            jsonl_path,
        )

        print(
            f"JSONL rebuilt from page archive .... "
            f"{rebuilt_rows:,}"
        )

        if rebuilt_rows != archived_rows:
            raise RuntimeError(
                "JSONL rebuild did not reconcile to archived pages."
            )

    else:
        if jsonl_path.exists():
            jsonl_path.unlink()

        rebuilt_rows = 0

        print(
            "JSONL rebuilt from page archive .... 0"
        )

    checkpoint_is_stale = (
        checkpoint is None
        or checkpoint_last_page != highest_page
        or checkpoint_rows != archived_rows
    )

    if checkpoint_is_stale:
        print(
            "Checkpoint status .................. STALE / ABSENT"
        )

        next_page = (
            highest_page + 1
            if highest_page > 0
            else 1
        )

        atomic_write_json(
            checkpoint_path,
            {
                "fiscal_year": fiscal_year,
                "last_completed_page": highest_page,
                "next_page": next_page,
                "collected_rows": archived_rows,
                "expected_count": expected_count,
            },
        )

        print(
            "Recovery action .................... "
            "Checkpoint repaired from page archive"
        )

    else:
        print(
            "Checkpoint status .................. CURRENT"
        )

        next_page = int(
            checkpoint.get(
                "next_page",
                highest_page + 1,
            )
        )

    print()
    print(
        f"Resume page ........................ "
        f"{next_page:,}"
    )

    print(
        f"Already collected .................. "
        f"{archived_rows:,}"
    )

    print("-" * 96)
    print()

    return (
        next_page,
        archived_rows,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 1 paged acquisition of Washington "
            "USAspending contract transactions."
        )
    )

    parser.add_argument(
        "--fiscal-year",
        type=int,
        required=True,
        help="Federal fiscal year to acquire.",
    )

    parser.add_argument(
        "--expected-count",
        type=int,
        required=True,
        help="Previously validated transaction population.",
    )

    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help=(
            "USAspending page size. "
            "Maximum supported by this endpoint is 100."
        ),
    )

    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.25,
        help="Delay between API requests. Default: 0.25 seconds.",
    )

    parser.add_argument(
        "--restart",
        action="store_true",
        help=(
            "Delete existing Stage-1 page archive and begin again."
        ),
    )

    args = parser.parse_args()

    if args.page_size < 1:
        raise ValueError(
            "--page-size must be at least 1."
        )

    if args.page_size > 100:
        raise ValueError(
            "--page-size cannot exceed 100 for "
            "spending_by_transaction."
        )

    fiscal_year = args.fiscal_year

    target_dir = (
        REPO_ROOT
        / "data"
        / "raw"
        / "usaspending"
        / "procurement"
        / f"FY{fiscal_year}"
        / "stage1_paged"
    )

    pages_dir = (
        target_dir
        / "pages"
    )

    target_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    pages_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    request_spec_path = (
        target_dir
        / "request_specification.json"
    )

    checkpoint_path = (
        target_dir
        / "checkpoint.json"
    )

    jsonl_path = (
        target_dir
        / "transactions_stage1.jsonl"
    )

    summary_path = (
        target_dir
        / "stage1_summary.json"
    )

    filters = build_filters(
        fiscal_year
    )

    request_spec = {
        "endpoint": API_URL,
        "fiscal_year": fiscal_year,
        "expected_count": args.expected_count,
        "page_size": args.page_size,
        "sort": "Action Date",
        "order": "asc",
        "fields": FIELDS,
        "filters": filters,
        "important_note": (
            "Stage 1 does not expose the canonical "
            "USAspending transaction ID. "
            "Stage 2 must resolve transaction identity."
        ),
    }

    atomic_write_json(
        request_spec_path,
        request_spec,
    )

    if args.restart:
        print(
            "RESTART requested: removing existing Stage-1 acquisition."
        )

        if checkpoint_path.exists():
            checkpoint_path.unlink()

        if jsonl_path.exists():
            jsonl_path.unlink()

        if summary_path.exists():
            summary_path.unlink()

        for page_file in pages_dir.glob(
            "page_*.json"
        ):
            page_file.unlink()

    print("=" * 96)
    print(
        "WCFFBP - USASPENDING PROCUREMENT STAGE 1 PAGED ACQUISITION"
    )
    print("=" * 96)
    print()
    print(
        f"Federal fiscal year ............... FY{fiscal_year}"
    )
    print(
        "Place of performance .............. Washington"
    )
    print(
        "Award population .................. Contracts"
    )
    print(
        f"Expected transaction count ........ "
        f"{args.expected_count:,}"
    )
    print(
        f"Page size ......................... "
        f"{args.page_size:,}"
    )
    print()

    (
        page,
        collected_rows,
    ) = reconcile_existing_state(
        fiscal_year=fiscal_year,
        expected_count=args.expected_count,
        pages_dir=pages_dir,
        jsonl_path=jsonl_path,
        checkpoint_path=checkpoint_path,
    )

    # If everything was already acquired, skip network calls.
    if collected_rows == args.expected_count:
        print(
            "Expected transaction population already acquired."
        )

    else:
        with jsonl_path.open(
            "a",
            encoding="utf-8",
        ) as output:

            while True:
                existing_page_path = (
                    pages_dir
                    / f"page_{page:06d}.json"
                )

                if existing_page_path.exists():
                    raise RuntimeError(
                        "Refusing to overwrite an already archived page:\n"
                        f"  {existing_page_path}"
                    )

                payload = {
                    "filters": filters,
                    "fields": FIELDS,
                    "page": page,
                    "limit": args.page_size,
                    "sort": "Action Date",
                    "order": "asc",
                    "subawards": False,
                }

                response = post_json(
                    API_URL,
                    payload,
                )

                results = response.get(
                    "results"
                )

                if not isinstance(
                    results,
                    list,
                ):
                    raise RuntimeError(
                        f"Page {page:,} did not return a results list."
                    )

                metadata = response.get(
                    "page_metadata",
                    {},
                )

                metadata_page = metadata.get(
                    "page"
                )

                if (
                    metadata_page is not None
                    and int(metadata_page) != page
                ):
                    raise RuntimeError(
                        f"Requested page {page:,}, "
                        f"USAspending returned page {metadata_page}."
                    )

                # ------------------------------------------------------
                # Preserve page FIRST.
                # If anything fails afterward, restart reconstruction
                # will use this page as authoritative.
                # ------------------------------------------------------

                atomic_write_json(
                    existing_page_path,
                    response,
                )

                # ------------------------------------------------------
                # Append page observations to combined JSONL.
                # ------------------------------------------------------

                for row in results:
                    output.write(
                        json.dumps(
                            row,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )

                output.flush()
                os.fsync(
                    output.fileno()
                )

                collected_rows += len(
                    results
                )

                has_next = bool(
                    metadata.get(
                        "hasNext"
                    )
                )

                next_api_page = metadata.get(
                    "next"
                )

                print(
                    f"Page {page:>6,} | "
                    f"rows {len(results):>4,} | "
                    f"collected {collected_rows:>8,} | "
                    f"hasNext={has_next}"
                )

                if collected_rows > args.expected_count:
                    raise RuntimeError(
                        "Collected transaction population exceeded "
                        "the expected count. "
                        f"Expected {args.expected_count:,}; "
                        f"collected {collected_rows:,}."
                    )

                checkpoint_next_page = (
                    int(next_api_page)
                    if has_next
                    and next_api_page is not None
                    else page + 1
                )

                atomic_write_json(
                    checkpoint_path,
                    {
                        "fiscal_year": fiscal_year,
                        "last_completed_page": page,
                        "next_page": checkpoint_next_page,
                        "collected_rows": collected_rows,
                        "expected_count": args.expected_count,
                    },
                )

                if not has_next:
                    break

                if next_api_page is None:
                    raise RuntimeError(
                        "USAspending reported hasNext=true "
                        "but supplied no next page number."
                    )

                page = int(
                    next_api_page
                )

                time.sleep(
                    args.sleep_seconds
                )

    # ==================================================================
    # FINAL ARCHIVE RECONCILIATION
    # ==================================================================

    (
        final_page_paths,
        final_highest_page,
        final_archived_rows,
    ) = inspect_page_archive(
        pages_dir
    )

    final_jsonl_rows = rebuild_jsonl_from_pages(
        final_page_paths,
        jsonl_path,
    )

    print()
    print("=" * 96)
    print("STAGE 1 FINAL RECONCILIATION")
    print("=" * 96)
    print()

    print(
        f"Highest archived page ............. "
        f"{final_highest_page:,}"
    )

    print(
        f"Archived page rows ................ "
        f"{final_archived_rows:,}"
    )

    print(
        f"Rebuilt JSONL rows ................ "
        f"{final_jsonl_rows:,}"
    )

    if final_archived_rows != args.expected_count:
        raise RuntimeError(
            "Stage 1 row-count reconciliation FAILED. "
            f"Expected {args.expected_count:,}; "
            f"archived {final_archived_rows:,}."
        )

    if final_jsonl_rows != args.expected_count:
        raise RuntimeError(
            "Stage 1 JSONL reconciliation FAILED. "
            f"Expected {args.expected_count:,}; "
            f"JSONL contains {final_jsonl_rows:,}."
        )

    print(
        "Row-count reconciliation .......... PASS "
        f"({final_archived_rows:,})"
    )

    # ==================================================================
    # IDENTITY PROFILE
    # ==================================================================

    provisional_counter: Counter[
        tuple[Any, ...]
    ] = Counter()

    generated_awards: set[Any] = set()
    internal_awards: set[Any] = set()

    audit_rows = 0

    with jsonl_path.open(
        "r",
        encoding="utf-8",
    ) as handle:

        for line in handle:
            row = json.loads(
                line
            )

            audit_rows += 1

            provisional_counter[
                provisional_identity(row)
            ] += 1

            generated_awards.add(
                row.get(
                    "generated_internal_id"
                )
            )

            internal_awards.add(
                row.get(
                    "internal_id"
                )
            )

    duplicate_groups = sum(
        1
        for count in provisional_counter.values()
        if count > 1
    )

    duplicate_extra_rows = sum(
        count - 1
        for count in provisional_counter.values()
        if count > 1
    )

    jsonl_sha256 = sha256_file(
        jsonl_path
    )

    summary = {
        "fiscal_year": fiscal_year,
        "expected_count": args.expected_count,
        "collected_rows": final_archived_rows,
        "audit_rows": audit_rows,
        "row_difference": (
            final_archived_rows
            - args.expected_count
        ),
        "highest_archived_page": final_highest_page,
        "distinct_generated_award_ids": len(
            generated_awards
        ),
        "distinct_internal_award_ids": len(
            internal_awards
        ),
        "provisional_identity_groups": len(
            provisional_counter
        ),
        "provisional_duplicate_groups": (
            duplicate_groups
        ),
        "provisional_duplicate_extra_rows": (
            duplicate_extra_rows
        ),
        "jsonl_sha256": jsonl_sha256,
        "jsonl_path": str(
            jsonl_path
        ),
        "pages_directory": str(
            pages_dir
        ),
        "request_specification": str(
            request_spec_path
        ),
        "important_note": (
            "Provisional identity is not a certified "
            "USAspending transaction identity. "
            "Stage 2 must resolve canonical transaction IDs."
        ),
    }

    atomic_write_json(
        summary_path,
        summary,
    )

    atomic_write_json(
        checkpoint_path,
        {
            "fiscal_year": fiscal_year,
            "last_completed_page": final_highest_page,
            "next_page": None,
            "collected_rows": final_archived_rows,
            "expected_count": args.expected_count,
            "status": "COMPLETE",
        },
    )

    print()
    print(
        f"Distinct generated awards ......... "
        f"{len(generated_awards):,}"
    )

    print(
        f"Distinct internal awards .......... "
        f"{len(internal_awards):,}"
    )

    print(
        f"Provisional duplicate groups ...... "
        f"{duplicate_groups:,}"
    )

    print(
        f"Provisional duplicate extra rows .. "
        f"{duplicate_extra_rows:,}"
    )

    print(
        f"Stage-1 JSONL SHA-256 ............. "
        f"{jsonl_sha256}"
    )

    print(
        f"Summary ........................... "
        f"{summary_path}"
    )

    print()
    print("=" * 96)
    print("STAGE 1 RESULT: COMPLETE")
    print("=" * 96)


if __name__ == "__main__":
    main()