from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]

RAW_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "omb"
    / "object_class"
)

# ---------------------------------------------------------------------------
# WCFFBP preferred historical actual-vintage map
#
# Each target fiscal year is paired with the first normal President's Budget
# Object Class Analysis two vintages later, where that target year appears
# as ACTUAL.
# ---------------------------------------------------------------------------

TARGETS = [
    {"target_fiscal_year": 2015, "budget_vintage": 2017},
    {"target_fiscal_year": 2016, "budget_vintage": 2018},
    {"target_fiscal_year": 2017, "budget_vintage": 2019},
    {"target_fiscal_year": 2018, "budget_vintage": 2020},
    {"target_fiscal_year": 2019, "budget_vintage": 2021},
    {"target_fiscal_year": 2020, "budget_vintage": 2022},
    {"target_fiscal_year": 2021, "budget_vintage": 2023},
    {"target_fiscal_year": 2022, "budget_vintage": 2024},
    {"target_fiscal_year": 2023, "budget_vintage": 2025},
    {"target_fiscal_year": 2024, "budget_vintage": 2026},
]


OBJECT_CLASSES = [
    "11.1",
    "11.3",
    "11.5",
    "11.6",
    "11.7",
    "11.8",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def source_url(vintage: int) -> str:
    return (
        "https://www.govinfo.gov/content/pkg/"
        f"BUDGET-{vintage}-OBJCLASS/pdf/"
        f"BUDGET-{vintage}-OBJCLASS.pdf"
    )


def source_record(vintage: int) -> str:
    return (
        "https://www.govinfo.gov/app/details/"
        f"BUDGET-{vintage}-OBJCLASS"
    )


def find_existing_pdf(vintage: int) -> Path | None:
    directory = (
        RAW_ROOT
        / f"FY{vintage}"
    )

    if not directory.exists():
        return None

    matches = sorted(
        directory.glob(
            f"BUDGET-{vintage}-OBJCLASS_retrieved_*.pdf"
        )
    )

    if not matches:
        return None

    return matches[-1]


def download_pdf(
    vintage: int,
    retrieved_at: datetime,
) -> Path:

    directory = (
        RAW_ROOT
        / f"FY{vintage}"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = retrieved_at.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    path = (
        directory
        / (
            f"BUDGET-{vintage}-OBJCLASS_"
            f"retrieved_{timestamp}.pdf"
        )
    )

    url = source_url(
        vintage
    )

    print(
        f"Downloading FY{vintage} Object Class Analysis..."
    )

    print(
        f"  Source: {url}"
    )

    response = requests.get(
        url,
        timeout=180,
    )

    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type",
        "",
    )

    if "pdf" not in content_type.lower():
        raise RuntimeError(
            f"FY{vintage}: expected PDF response; "
            f"received Content-Type={content_type!r}"
        )

    content = response.content

    if not content.startswith(
        b"%PDF-"
    ):
        raise RuntimeError(
            f"FY{vintage}: response does not begin "
            "with a PDF signature."
        )

    if len(content) == 0:
        raise RuntimeError(
            f"FY{vintage}: downloaded PDF is empty."
        )

    path.write_bytes(
        content
    )

    return path


def obtain_pdf(
    vintage: int,
) -> tuple[Path, str]:

    existing = find_existing_pdf(
        vintage
    )

    if existing is not None:

        print(
            f"FY{vintage}: using existing preserved artifact."
        )

        print(
            f"  File: {existing}"
        )

        return (
            existing,
            "EXISTING",
        )

    retrieved_at = datetime.now(
        timezone.utc
    )

    path = download_pdf(
        vintage,
        retrieved_at,
    )

    return (
        path,
        "DOWNLOADED",
    )


def main() -> None:

    RAW_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    archive_rows = []

    for target in TARGETS:

        target_year = target[
            "target_fiscal_year"
        ]

        vintage = target[
            "budget_vintage"
        ]

        print()
        print("=" * 72)

        print(
            f"Target FFY{target_year} "
            f"-> FY{vintage} Budget"
        )

        print("=" * 72)

        path, acquisition_status = (
            obtain_pdf(
                vintage
            )
        )

        checksum = sha256_file(
            path
        )

        size_bytes = (
            path.stat().st_size
        )

        archive_rows.append(
            {
                "target_fiscal_year":
                    target_year,

                "budget_vintage":
                    vintage,

                "target_value_status":
                    "ACTUAL",

                "accounting_measure":
                    "OBLIGATIONS_BY_OBJECT_CLASS",

                "scope":
                    "GOVERNMENT_WIDE",

                "target_object_classes":
                    OBJECT_CLASSES,

                "source_record":
                    source_record(
                        vintage
                    ),

                "source_url":
                    source_url(
                        vintage
                    ),

                "local_file":
                    str(
                        path.relative_to(
                            ROOT
                        )
                    ),

                "sha256":
                    checksum,

                "file_size_bytes":
                    size_bytes,

                "acquisition_status":
                    acquisition_status,
            }
        )

        print(
            f"  Bytes:   {size_bytes:,}"
        )

        print(
            f"  SHA256:  {checksum}"
        )

    # -----------------------------------------------------------------------
    # Hard inventory controls
    # -----------------------------------------------------------------------

    if len(
        archive_rows
    ) != 10:

        raise RuntimeError(
            "Expected 10 OMB archive rows; "
            f"found {len(archive_rows)}."
        )

    target_years = {
        row["target_fiscal_year"]
        for row in archive_rows
    }

    if target_years != set(
        range(2015, 2025)
    ):
        raise RuntimeError(
            "OMB archive inventory does not contain "
            "exactly FFY2015-FFY2024."
        )

    vintages = {
        row["budget_vintage"]
        for row in archive_rows
    }

    if vintages != set(
        range(2017, 2027)
    ):
        raise RuntimeError(
            "OMB archive inventory does not contain "
            "exactly FY2017-FY2026 Budget vintages."
        )

    for row in archive_rows:

        if (
            row["budget_vintage"]
            != row["target_fiscal_year"] + 2
        ):
            raise RuntimeError(
                "Unexpected target/vintage relationship: "
                f"{row}"
            )

        if row["file_size_bytes"] <= 0:
            raise RuntimeError(
                "Zero-size OMB archive file: "
                f"{row['local_file']}"
            )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    manifest_path = (
        RAW_ROOT
        / (
            "omb_object_class_archive_"
            f"inventory_{timestamp}.json"
        )
    )

    manifest = {
        "generated_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "purpose":
            (
                "WCFFBP archive inventory of preferred "
                "OMB Object Class Analysis actual-value "
                "vintages for FFY2015-FFY2024 federal "
                "wage-obligation controls."
            ),

        "selection_rule":
            (
                "For the principal WCFFBP historical "
                "accounting series, use the subsequent "
                "OMB Object Class Analysis Budget vintage "
                "in which the target fiscal year is "
                "reported as ACTUAL. Preserve earlier "
                "ESTIMATE vintages separately when used "
                "for historical-methodology replication."
            ),

        "derived_wage_rules": {
            "MILITARY_WAGES":
                "11.6 + 11.7",

            "NONMILITARY_WAGES":
                "11.1 + 11.3 + 11.5 + 11.8",

            "TOTAL_WAGES":
                (
                    "MILITARY_WAGES + "
                    "NONMILITARY_WAGES"
                ),
        },

        "archive":
            archive_rows,
    }

    with manifest_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            manifest,
            f,
            indent=2,
            ensure_ascii=False,
        )

        f.write("\n")

    print()
    print("=" * 72)
    print(
        "OMB OBJECT CLASS ARCHIVE INVENTORY COMPLETE"
    )
    print("=" * 72)

    print(
        f"Target fiscal years: "
        f"{len(archive_rows)}"
    )

    print(
        "Coverage: FFY2015-FFY2024"
    )

    print(
        "Budget vintages: FY2017-FY2026"
    )

    print(
        f"Inventory manifest: "
        f"{manifest_path}"
    )


if __name__ == "__main__":
    main()