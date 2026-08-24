from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = (
    ROOT
    / "data"
    / "raw"
    / "omb"
    / "object_class"
    / "FY2018"
)

SOURCE_URL = (
    "https://www.govinfo.gov/content/pkg/"
    "BUDGET-2018-OBJCLASS/pdf/"
    "BUDGET-2018-OBJCLASS.pdf"
)

SOURCE_RECORD = (
    "https://www.govinfo.gov/app/details/"
    "BUDGET-2018-OBJCLASS"
)


def sha256_file(path: Path) -> str:

    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    retrieved_at = datetime.now(
        timezone.utc
    )

    timestamp = retrieved_at.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    pdf_path = (
        OUTPUT_DIR
        / (
            "BUDGET-2018-OBJCLASS_"
            f"retrieved_{timestamp}.pdf"
        )
    )

    print("Requesting official GovInfo artifact...")
    print(f"  Source: {SOURCE_URL}")

    response = requests.get(
        SOURCE_URL,
        timeout=120,
    )

    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type",
        "",
    )

    if "pdf" not in content_type.lower():
        raise RuntimeError(
            "Expected PDF response; "
            f"received Content-Type={content_type!r}"
        )

    pdf_path.write_bytes(
        response.content
    )

    if pdf_path.stat().st_size == 0:
        raise RuntimeError(
            "Downloaded OMB PDF is empty."
        )

    checksum = sha256_file(
        pdf_path
    )

    manifest = {
        "retrieved_utc":
            retrieved_at.isoformat(),

        "source_agency":
            (
                "Office of Management and Budget, "
                "Executive Office of the President"
            ),

        "archive":
            "GovInfo",

        "publication_title":
            (
                "Object Class Analysis, "
                "Budget of the United States Government, "
                "Fiscal Year 2018"
            ),

        "budget_vintage":
            2018,

        "date_issued":
            "2017-05-23",

        "source_record":
            SOURCE_RECORD,

        "source_url":
            SOURCE_URL,

        "local_file":
            str(
                pdf_path.relative_to(
                    ROOT
                )
            ),

        "sha256":
            checksum,

        "file_size_bytes":
            pdf_path.stat().st_size,

        "target_accounting_year":
            2016,

        "target_value_status":
            "ACTUAL",

        "accounting_measure":
            "OBLIGATIONS_BY_OBJECT_CLASS",

        "target_scope":
            "GOVERNMENT_WIDE",

        "target_object_classes": [
            "11.1",
            "11.3",
            "11.5",
            "11.6",
            "11.7",
            "11.8",
        ],

        "wcffbp_methodology_note":
            (
                "This artifact is preserved as primary "
                "OMB accounting evidence. WCFFBP will "
                "derive FY2016 wage-obligation controls "
                "from the government-wide 2016 actual "
                "object-class observations before any "
                "comparison with Rockefeller Institute "
                "published values."
            ),
    }

    manifest_path = (
        OUTPUT_DIR
        / (
            "omb_object_class_fy2018_"
            f"manifest_{timestamp}.json"
        )
    )

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
    print("OMB OBJECT CLASS ACQUISITION COMPLETE")
    print("=" * 72)

    print(f"PDF:      {pdf_path}")
    print(f"Bytes:    {pdf_path.stat().st_size:,}")
    print(f"SHA-256:  {checksum}")
    print(f"Manifest: {manifest_path}")

    print()
    print("Accounting target:")
    print("  Budget vintage: FY2018")
    print("  Target year:    FY2016")
    print("  Status:         ACTUAL")
    print("  Measure:        OBLIGATIONS BY OBJECT CLASS")


if __name__ == "__main__":
    main()