"""
Publish an EPS-001 evidence package for a certified procurement batch.

Usage:
    python -m scripts.publish_procurement_evidence \
        --load-batch-id 5
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from etl.common.db import get_connection
from etl.validation.common.certification_builder import (
    CertificationBuilder,
)
from etl.validation.common.evidence_package import EvidencePackage
from etl.validation.common.evidence_publisher import EvidencePublisher
from etl.validation.common.evidence_writer import EvidenceWriter
from etl.validation.common.json_writer import JsonWriter
from etl.validation.common.manifest_builder import ManifestBuilder
from etl.validation.common.metadata_builder import MetadataBuilder
from etl.validation.common.publication_validator import (
    PublicationValidator,
)
from etl.validation.common.report_writer import ReportWriter
from etl.validation.procurement.certification import (
    run_certification,
)
from etl.validation.procurement.models import (
    CertificationCheck,
    CertificationSummary,
    CheckStatus,
)
from etl.validation.procurement.reporting import (
    print_report,
)


CERTIFICATION_VERSION = "ETL-114C.1"
ETL_VERSION = "0.5.0-alpha1"
ARCHITECTURE_VERSION = "1.0"
DATABASE_NAME = "wcffbp"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Certify a procurement load batch and publish its "
            "EPS-001 Evidence Package."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Procurement load batch ID to certify and publish.",
    )

    parser.add_argument(
        "--root-directory",
        type=Path,
        default=Path("evidence"),
        help=(
            "Evidence root directory. Defaults to the repository's "
            "evidence directory."
        ),
    )

    return parser.parse_args()


def check_status_for_publication(
    status: CheckStatus,
) -> str:
    """Map internal check status to EPS-001 publication terminology."""

    if status == CheckStatus.WARN:
        return "WARNING"

    return status.value


def check_message(check: CertificationCheck) -> str:
    """Return a human-readable publication message."""

    if check.detail:
        return check.detail

    if check.status == CheckStatus.PASS:
        return "The certification check passed."

    if check.status == CheckStatus.WARN:
        return "The certification check completed with a warning."

    return "The certification check failed."


def serialize_check(
    check: CertificationCheck,
) -> dict[str, Any]:
    """Convert one certification check into an EPS-001 check record."""

    evidence = dict(check.evidence)

    if check.observed_value is not None:
        evidence.setdefault(
            "observed_value",
            check.observed_value,
        )

    if check.expected_value is not None:
        evidence.setdefault(
            "expected_value",
            check.expected_value,
        )

    return {
        "code": check.check_code,
        "name": check.label,
        "category": check.section.lower().replace(" ", "_"),
        "status": check_status_for_publication(check.status),
        "message": check_message(check),
        "evidence": evidence,
    }


def build_statistics(
    conn,
    *,
    load_batch_id: int,
) -> dict[str, int]:
    """Build the EPS-001 source and certified row statistics."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                (
                    SELECT COUNT(*)
                    FROM procurement.raw_award_transaction
                    WHERE load_batch_id = %s
                ) AS source_rows,
                (
                    SELECT COUNT(*)
                    FROM procurement.award_transaction
                    WHERE load_batch_id = %s
                ) AS certified_rows;
            """,
            (
                load_batch_id,
                load_batch_id,
            ),
        )

        row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Procurement publication statistics query "
            "returned no result."
        )

    return {
        "source_rows": int(row[0]),
        "certified_rows": int(row[1]),
    }


def build_publisher() -> EvidencePublisher:
    """Construct the tested EPS-001 evidence publisher."""

    schema_directory = (
        Path.cwd()
        / "schemas"
        / "evidence"
    )

    return EvidencePublisher(
        evidence_writer=EvidenceWriter(),
        manifest_builder=ManifestBuilder(),
        certification_builder=CertificationBuilder(
            certification_version=CERTIFICATION_VERSION,
            etl_version=ETL_VERSION,
        ),
        metadata_builder=MetadataBuilder(
            certification_version=CERTIFICATION_VERSION,
            etl_version=ETL_VERSION,
            architecture_version=ARCHITECTURE_VERSION,
            repository_root=Path.cwd(),
            database_name=DATABASE_NAME,
        ),
        json_writer=JsonWriter(),
        report_writer=ReportWriter(),
        publication_validator=PublicationValidator(
            schema_directory
        ),
    )


def print_publication_result(
    package: EvidencePackage,
) -> None:
    """Print the generated package and artifact paths."""

    package_directory = package.package_directory

    print()
    print("=" * 76)
    print("EPS-001 PROCUREMENT EVIDENCE PACKAGE PUBLISHED")
    print("=" * 76)
    print(
        f"Evidence Package ID: "
        f"{package.evidence_package_id}"
    )
    print(f"Package directory:   {package_directory}")
    print(
        f"Manifest:            "
        f"{package_directory / 'manifest.json'}"
    )
    print(
        f"Certification:       "
        f"{package_directory / 'certification.json'}"
    )
    print(
        f"Metadata:            "
        f"{package_directory / 'metadata' / 'metadata.json'}"
    )
    print(
        f"Report:              "
        f"{package_directory / 'certification_report.txt'}"
    )
    print("Status:              CERTIFIED")
    print("=" * 76)


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            summary: CertificationSummary = run_certification(
                cur,
                load_batch_id=args.load_batch_id,
            )

        print_report(summary)

        if not summary.is_certified:
            print()
            print(
                "Evidence publication refused because the "
                "procurement batch is not certified."
            )
            raise SystemExit(1)

        checks = [
            serialize_check(check)
            for check in summary.checks
        ]

        statistics = build_statistics(
            conn,
            load_batch_id=args.load_batch_id,
        )

        package = EvidencePackage.from_summary(
            dataset="procurement",
            dataset_code="PROC",
            batch_id=args.load_batch_id,
            summary=summary,
            root_directory=args.root_directory,
        )

        publisher = build_publisher()

        published_directory = publisher.publish(
            package,
            checks=checks,
            statistics=statistics,
        )

        if published_directory != package.package_directory:
            raise ValueError(
                "Evidence publisher returned an unexpected "
                f"directory: {published_directory}"
            )

        print_publication_result(package)

    except SystemExit:
        raise

    except Exception as exc:
        print()
        print("Procurement evidence publication failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()