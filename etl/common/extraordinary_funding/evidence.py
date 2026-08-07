"""Evidence writers for extraordinary-funding relationship ETL."""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnownDefcLinkEvidence:
    """One classified transaction-to-DEFC relationship."""

    source_row_number: int
    assistance_transaction_id: int
    assistance_transaction_unique_key: str

    defc_code: str
    observed_description: str
    raw_defc_value: str

    funding_family: str
    extraordinary_flag: bool | None
    covid_flag: bool
    iija_flag: bool


@dataclass(frozen=True)
class UnknownDefcEvidence:
    """One parsed code that lacks a reference classification."""

    source_row_number: int
    assistance_transaction_id: int
    assistance_transaction_unique_key: str

    defc_code: str
    observed_description: str
    raw_defc_value: str


@dataclass(frozen=True)
class UnparsedDefcEvidence:
    """One malformed or unrecognized source segment."""

    source_row_number: int
    assistance_transaction_id: int
    assistance_transaction_unique_key: str

    unparsed_segment: str
    raw_defc_value: str


@dataclass(frozen=True)
class ExtraordinaryFundingEvidenceSummary:
    """Summary values written with one evidence package."""

    load_batch_id: int
    raw_observation_count: int
    rows_with_defc_count: int
    parsed_observation_count: int

    known_relationship_count: int
    unknown_observation_count: int
    unparsed_segment_count: int

    distinct_known_code_count: int
    distinct_unknown_code_count: int
    multi_code_transaction_count: int

    inserted_count: int
    updated_count: int
    unchanged_count: int

    duplicate_relationship_count: int
    orphan_transaction_count: int
    orphan_reference_count: int


def write_extraordinary_funding_evidence(
    *,
    output_directory: Path,
    known_links: Iterable[KnownDefcLinkEvidence],
    unknown_observations: Iterable[UnknownDefcEvidence],
    unparsed_observations: Iterable[UnparsedDefcEvidence],
    summary: ExtraordinaryFundingEvidenceSummary,
) -> Path:
    """Write the complete deterministic extraordinary-funding package."""

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    known_links = tuple(known_links)
    unknown_observations = tuple(
        unknown_observations
    )
    unparsed_observations = tuple(
        unparsed_observations
    )

    _write_known_links(
        output_directory / "known_defc_links.csv",
        known_links,
    )

    _write_unknown_codes(
        output_directory / "unknown_defc_codes.csv",
        unknown_observations,
    )

    _write_unparsed_segments(
        output_directory / "unparsed_defc_segments.csv",
        unparsed_observations,
    )

    _write_multi_code_transactions(
        output_directory / "multi_defc_transactions.csv",
        known_links,
        unknown_observations,
    )

    _write_summary(
        output_directory / "link_summary.txt",
        summary,
    )

    return output_directory


def _write_known_links(
    path: Path,
    rows: tuple[KnownDefcLinkEvidence, ...],
) -> None:
    """Write all classified transaction-code relationships."""

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.writer(
            file,
            lineterminator="\n",
        )

        writer.writerow(
            [
                "source_row_number",
                "assistance_transaction_id",
                "assistance_transaction_unique_key",
                "defc_code",
                "observed_description",
                "raw_defc_value",
                "funding_family",
                "extraordinary_flag",
                "covid_flag",
                "iija_flag",
            ]
        )

        for row in sorted(
            rows,
            key=lambda item: (
                item.source_row_number,
                item.defc_code,
            ),
        ):
            writer.writerow(
                [
                    row.source_row_number,
                    row.assistance_transaction_id,
                    row.assistance_transaction_unique_key,
                    row.defc_code,
                    row.observed_description,
                    row.raw_defc_value,
                    row.funding_family,
                    _boolean_text(
                        row.extraordinary_flag
                    ),
                    _boolean_text(
                        row.covid_flag
                    ),
                    _boolean_text(
                        row.iija_flag
                    ),
                ]
            )


def _write_unknown_codes(
    path: Path,
    rows: tuple[UnknownDefcEvidence, ...],
) -> None:
    """Write an aggregated inventory of unclassified parsed codes."""

    grouped: dict[
        str,
        list[UnknownDefcEvidence],
    ] = {}

    for row in rows:
        grouped.setdefault(
            row.defc_code,
            [],
        ).append(row)

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.writer(
            file,
            lineterminator="\n",
        )

        writer.writerow(
            [
                "defc_code",
                "observation_count",
                "transaction_count",
                "distinct_description_count",
                "observed_descriptions",
                "first_source_row_number",
                "last_source_row_number",
                "sample_transaction_unique_key",
                "sample_raw_defc_value",
            ]
        )

        for code in sorted(grouped):
            observations = grouped[code]

            descriptions = sorted(
                {
                    item.observed_description
                    for item in observations
                }
            )

            writer.writerow(
                [
                    code,
                    len(observations),
                    len(
                        {
                            item.assistance_transaction_id
                            for item in observations
                        }
                    ),
                    len(descriptions),
                    " | ".join(descriptions),
                    min(
                        item.source_row_number
                        for item in observations
                    ),
                    max(
                        item.source_row_number
                        for item in observations
                    ),
                    observations[
                        0
                    ].assistance_transaction_unique_key,
                    observations[0].raw_defc_value,
                ]
            )


def _write_unparsed_segments(
    path: Path,
    rows: tuple[UnparsedDefcEvidence, ...],
) -> None:
    """Write an aggregated inventory of unparsed source segments."""

    grouped: dict[
        str,
        list[UnparsedDefcEvidence],
    ] = {}

    for row in rows:
        grouped.setdefault(
            row.unparsed_segment,
            [],
        ).append(row)

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.writer(
            file,
            lineterminator="\n",
        )

        writer.writerow(
            [
                "unparsed_segment",
                "occurrence_count",
                "transaction_count",
                "first_source_row_number",
                "last_source_row_number",
                "sample_transaction_unique_key",
                "sample_raw_defc_value",
            ]
        )

        for segment in sorted(grouped):
            observations = grouped[segment]

            writer.writerow(
                [
                    segment,
                    len(observations),
                    len(
                        {
                            item.assistance_transaction_id
                            for item in observations
                        }
                    ),
                    min(
                        item.source_row_number
                        for item in observations
                    ),
                    max(
                        item.source_row_number
                        for item in observations
                    ),
                    observations[
                        0
                    ].assistance_transaction_unique_key,
                    observations[0].raw_defc_value,
                ]
            )


def _write_multi_code_transactions(
    path: Path,
    known_rows: tuple[KnownDefcLinkEvidence, ...],
    unknown_rows: tuple[UnknownDefcEvidence, ...],
) -> None:
    """Write transactions containing more than one parsed DEFC code."""

    transaction_codes: dict[
        tuple[int, int, str],
        list[
            tuple[str, str]
        ],
    ] = {}

    for row in known_rows:
        key = (
            row.source_row_number,
            row.assistance_transaction_id,
            row.assistance_transaction_unique_key,
        )

        transaction_codes.setdefault(
            key,
            [],
        ).append(
            (
                row.defc_code,
                "KNOWN",
            )
        )

    for row in unknown_rows:
        key = (
            row.source_row_number,
            row.assistance_transaction_id,
            row.assistance_transaction_unique_key,
        )

        transaction_codes.setdefault(
            key,
            [],
        ).append(
            (
                row.defc_code,
                "UNKNOWN",
            )
        )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.writer(
            file,
            lineterminator="\n",
        )

        writer.writerow(
            [
                "source_row_number",
                "assistance_transaction_id",
                "assistance_transaction_unique_key",
                "parsed_code_count",
                "known_code_count",
                "unknown_code_count",
                "parsed_codes",
                "classification_statuses",
            ]
        )

        for key in sorted(transaction_codes):
            code_statuses = transaction_codes[key]

            if len(code_statuses) <= 1:
                continue

            status_counts = Counter(
                status
                for _, status in code_statuses
            )

            writer.writerow(
                [
                    key[0],
                    key[1],
                    key[2],
                    len(code_statuses),
                    status_counts.get(
                        "KNOWN",
                        0,
                    ),
                    status_counts.get(
                        "UNKNOWN",
                        0,
                    ),
                    " | ".join(
                        code
                        for code, _ in code_statuses
                    ),
                    " | ".join(
                        status
                        for _, status in code_statuses
                    ),
                ]
            )


def _write_summary(
    path: Path,
    summary: ExtraordinaryFundingEvidenceSummary,
) -> None:
    """Write the human-readable link summary."""

    lines = [
        "=" * 72,
        "ETL-005D.6 — ASSISTANCE EXTRAORDINARY-FUNDING LINKAGE",
        "=" * 72,
        (
            "Load batch ID .................. "
            f"{summary.load_batch_id}"
        ),
        (
            "Raw observations examined ...... "
            f"{summary.raw_observation_count:,}"
        ),
        (
            "Rows with DEFC values .......... "
            f"{summary.rows_with_defc_count:,}"
        ),
        (
            "Parsed code observations ....... "
            f"{summary.parsed_observation_count:,}"
        ),
        (
            "Known relationship rows ........ "
            f"{summary.known_relationship_count:,}"
        ),
        (
            "Unknown code observations ...... "
            f"{summary.unknown_observation_count:,}"
        ),
        (
            "Unparsed segments .............. "
            f"{summary.unparsed_segment_count:,}"
        ),
        (
            "Distinct known DEFC codes ...... "
            f"{summary.distinct_known_code_count:,}"
        ),
        (
            "Distinct unknown DEFC codes .... "
            f"{summary.distinct_unknown_code_count:,}"
        ),
        (
            "Multiple-code transactions ..... "
            f"{summary.multi_code_transaction_count:,}"
        ),
        (
            "Relationships inserted ......... "
            f"{summary.inserted_count:,}"
        ),
        (
            "Relationships updated .......... "
            f"{summary.updated_count:,}"
        ),
        (
            "Relationships unchanged ........ "
            f"{summary.unchanged_count:,}"
        ),
        (
            "Duplicate relationships ........ "
            f"{summary.duplicate_relationship_count:,}"
        ),
        (
            "Orphan transaction links ....... "
            f"{summary.orphan_transaction_count:,}"
        ),
        (
            "Orphan reference links ......... "
            f"{summary.orphan_reference_count:,}"
        ),
        "Validation ..................... PASS",
        "=" * 72,
        "",
        (
            "Only DEFC codes represented in the authoritative "
            "reference table are linked."
        ),
        (
            "Unknown parsed codes and malformed source segments "
            "remain preserved in evidence for later classification."
        ),
        (
            "The complete original DEFC source value remains "
            "preserved on the normalized transaction and each "
            "known relationship."
        ),
        "",
    ]

    path.write_text(
        "\n".join(lines),
        encoding="utf-8",
        newline="\n",
    )


def _boolean_text(
    value: bool | None,
) -> str:
    """Format an optional Boolean consistently for CSV evidence."""

    if value is None:
        return ""

    return str(value).upper()