"""Contract tests for extraordinary-funding evidence writing."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from etl.common.extraordinary_funding.evidence import (
    ExtraordinaryFundingEvidenceSummary,
    KnownDefcLinkEvidence,
    UnknownDefcEvidence,
    UnparsedDefcEvidence,
    write_extraordinary_funding_evidence,
)


def read_csv(
    path: Path,
) -> list[list[str]]:
    """Read a generated CSV file."""

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        return list(
            csv.reader(file)
        )


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output_directory = Path(directory) / "evidence"

        known = [
            KnownDefcLinkEvidence(
                source_row_number=1,
                assistance_transaction_id=101,
                assistance_transaction_unique_key="TX-101",
                defc_code="L",
                observed_description="Emergency P.L. 116-123",
                raw_defc_value=(
                    "L: Emergency P.L. 116-123; "
                    "AAA: Emergency P.L. 117-180"
                ),
                funding_family="COVID",
                extraordinary_flag=True,
                covid_flag=True,
                iija_flag=False,
            )
        ]

        unknown = [
            UnknownDefcEvidence(
                source_row_number=1,
                assistance_transaction_id=101,
                assistance_transaction_unique_key="TX-101",
                defc_code="AAA",
                observed_description="Emergency P.L. 117-180",
                raw_defc_value=(
                    "L: Emergency P.L. 116-123; "
                    "AAA: Emergency P.L. 117-180"
                ),
            ),
            UnknownDefcEvidence(
                source_row_number=2,
                assistance_transaction_id=102,
                assistance_transaction_unique_key="TX-102",
                defc_code="AAA",
                observed_description="Emergency P.L. 117-180",
                raw_defc_value=(
                    "AAA: Emergency P.L. 117-180"
                ),
            ),
        ]

        unparsed = [
            UnparsedDefcEvidence(
                source_row_number=3,
                assistance_transaction_id=103,
                assistance_transaction_unique_key="TX-103",
                unparsed_segment="malformed value",
                raw_defc_value="malformed value",
            )
        ]

        summary = ExtraordinaryFundingEvidenceSummary(
            load_batch_id=6,
            raw_observation_count=3,
            rows_with_defc_count=3,
            parsed_observation_count=3,
            known_relationship_count=1,
            unknown_observation_count=2,
            unparsed_segment_count=1,
            distinct_known_code_count=1,
            distinct_unknown_code_count=1,
            multi_code_transaction_count=1,
            inserted_count=1,
            updated_count=0,
            unchanged_count=0,
            duplicate_relationship_count=0,
            orphan_transaction_count=0,
            orphan_reference_count=0,
        )

        result = write_extraordinary_funding_evidence(
            output_directory=output_directory,
            known_links=known,
            unknown_observations=unknown,
            unparsed_observations=unparsed,
            summary=summary,
        )

        expected_files = {
            "known_defc_links.csv",
            "unknown_defc_codes.csv",
            "unparsed_defc_segments.csv",
            "multi_defc_transactions.csv",
            "link_summary.txt",
        }

        actual_files = {
            path.name
            for path in result.iterdir()
            if path.is_file()
        }

        if actual_files != expected_files:
            raise AssertionError(
                "Evidence package file set differed: "
                f"{actual_files!r}."
            )

        unknown_rows = read_csv(
            result / "unknown_defc_codes.csv"
        )

        if unknown_rows[1][0] != "AAA":
            raise AssertionError(
                "Unknown DEFC code was not written."
            )

        if unknown_rows[1][1] != "2":
            raise AssertionError(
                "Unknown DEFC occurrences were not aggregated."
            )

        multi_rows = read_csv(
            result / "multi_defc_transactions.csv"
        )

        if len(multi_rows) != 2:
            raise AssertionError(
                "Multiple-code transaction was not written."
            )

        summary_text = (
            result / "link_summary.txt"
        ).read_text(
            encoding="utf-8"
        )

        if "Validation ..................... PASS" not in summary_text:
            raise AssertionError(
                "Evidence summary did not record validation."
            )

    print(
        "Extraordinary-funding evidence "
        "contract test passed."
    )
    print()
    print("Verified:")
    print("  stable evidence file set")
    print("  known relationship inventory")
    print("  unknown-code aggregation")
    print("  unparsed-segment inventory")
    print("  multi-code transaction evidence")
    print("  human-readable validation summary")


if __name__ == "__main__":
    main()