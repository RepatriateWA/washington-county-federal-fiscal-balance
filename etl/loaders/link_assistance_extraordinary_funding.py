"""Link Assistance transactions to extraordinary-funding classifications."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from psycopg2.extras import execute_values

from etl.common.db import get_connection
from etl.common.extraordinary_funding.defc_parser import (
    parse_defc_value,
)
from etl.common.extraordinary_funding.evidence import (
    ExtraordinaryFundingEvidenceSummary,
    KnownDefcLinkEvidence,
    UnknownDefcEvidence,
    UnparsedDefcEvidence,
    write_extraordinary_funding_evidence,
)
from etl.common.extraordinary_funding.validation import (
    require_equal_count,
    require_no_database_failures,
    require_unique_relationships,
)
from etl.common.normalization.text import clean_optional_text


EVIDENCE_ROOT = Path("evidence/assistance")
PAGE_SIZE = 1_000


@dataclass(frozen=True)
class DefcReference:
    """One authoritative extraordinary-funding classification."""

    extraordinary_funding_code_id: int
    defc_code: str
    funding_family: str
    extraordinary_flag: bool | None
    covid_flag: bool
    iija_flag: bool


@dataclass(frozen=True)
class TransactionDefcSource:
    """One normalized Assistance transaction and its raw DEFC value."""

    source_row_number: int
    assistance_transaction_id: int
    assistance_transaction_unique_key: str
    raw_defc_value: str | None


@dataclass(frozen=True)
class KnownRelationship:
    """One classified transaction-to-DEFC relationship."""

    source_row_number: int
    assistance_transaction_id: int
    assistance_transaction_unique_key: str

    extraordinary_funding_code_id: int
    defc_code: str
    observed_description: str
    raw_defc_value: str

    funding_family: str
    extraordinary_flag: bool | None
    covid_flag: bool
    iija_flag: bool


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Link normalized Assistance transactions to authoritative "
            "extraordinary-funding classifications."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Normalized Assistance load batch ID.",
    )

    return parser.parse_args()


def load_reference_lookup(
    cur,
) -> dict[str, DefcReference]:
    """Load authoritative DEFC classifications by uppercase code."""

    cur.execute(
        """
        SELECT
            extraordinary_funding_code_id,
            defc_code,
            funding_family,
            extraordinary_flag,
            covid_flag,
            iija_flag
        FROM reference.extraordinary_funding_code
        ORDER BY defc_code;
        """
    )

    lookup: dict[str, DefcReference] = {}

    for row in cur.fetchall():
        code = str(row[1]).strip().upper()

        if code in lookup:
            raise ValueError(
                f"Duplicate extraordinary-funding reference code "
                f"{code!r}."
            )

        lookup[code] = DefcReference(
            extraordinary_funding_code_id=int(row[0]),
            defc_code=code,
            funding_family=str(row[2]),
            extraordinary_flag=(
                bool(row[3])
                if row[3] is not None
                else None
            ),
            covid_flag=bool(row[4]),
            iija_flag=bool(row[5]),
        )

    if not lookup:
        raise ValueError(
            "The extraordinary-funding reference table is empty."
        )

    return lookup


def extract_transaction_sources(
    cur,
    *,
    load_batch_id: int,
) -> list[TransactionDefcSource]:
    """
    Resolve every current-batch raw observation to its globally canonical
    Assistance transaction and preserve the DEFC value observed in that raw
    source row.
    """

    cur.execute(
        """
        SELECT
            raw.source_row_number,
            transaction.assistance_transaction_id,
            raw.assistance_transaction_unique_key,
            raw.raw_record
                ->> 'disaster_emergency_fund_codes_for_overall_award'

        FROM assistance.raw_award_transaction AS raw

        JOIN assistance.award_transaction AS transaction
          ON transaction.assistance_transaction_unique_key
             = raw.assistance_transaction_unique_key

        WHERE raw.load_batch_id = %s
        ORDER BY raw.source_row_number;
        """,
        (load_batch_id,),
    )

    rows = cur.fetchall()

    if not rows:
        raise ValueError(
            f"No raw Assistance observations resolved for "
            f"load batch {load_batch_id}."
        )

    return [
        TransactionDefcSource(
            source_row_number=int(row[0]),
            assistance_transaction_id=int(row[1]),
            assistance_transaction_unique_key=str(row[2]),
            raw_defc_value=clean_optional_text(row[3]),
        )
        for row in rows
    ]

def classify_sources(
    *,
    sources: list[TransactionDefcSource],
    reference_lookup: dict[str, DefcReference],
) -> tuple[
    list[KnownRelationship],
    list[UnknownDefcEvidence],
    list[UnparsedDefcEvidence],
    int,
    int,
]:
    """
    Parse all source values and separate known, unknown, and unparsed data.

    Returns:
        known relationships;
        unknown parsed-code evidence;
        unparsed-segment evidence;
        rows containing a nonblank DEFC value;
        total parsed code observations.
    """

    known_relationships: list[
        KnownRelationship
    ] = []

    unknown_observations: list[
        UnknownDefcEvidence
    ] = []

    unparsed_observations: list[
        UnparsedDefcEvidence
    ] = []

    rows_with_defc_count = 0
    parsed_observation_count = 0

    for source in sources:
        raw_value = source.raw_defc_value

        if raw_value is None:
            continue

        rows_with_defc_count += 1

        result = parse_defc_value(
            raw_value
        )

        parsed_observation_count += len(
            result.observations
        )

        for observation in result.observations:
            code = observation.code.upper()

            reference = reference_lookup.get(
                code
            )

            if reference is None:
                unknown_observations.append(
                    UnknownDefcEvidence(
                        source_row_number=(
                            source.source_row_number
                        ),
                        assistance_transaction_id=(
                            source.assistance_transaction_id
                        ),
                        assistance_transaction_unique_key=(
                            source
                            .assistance_transaction_unique_key
                        ),
                        defc_code=code,
                        observed_description=(
                            observation.description
                        ),
                        raw_defc_value=raw_value,
                    )
                )
                continue

            known_relationships.append(
                KnownRelationship(
                    source_row_number=(
                        source.source_row_number
                    ),
                    assistance_transaction_id=(
                        source.assistance_transaction_id
                    ),
                    assistance_transaction_unique_key=(
                        source
                        .assistance_transaction_unique_key
                    ),
                    extraordinary_funding_code_id=(
                        reference
                        .extraordinary_funding_code_id
                    ),
                    defc_code=reference.defc_code,
                    observed_description=(
                        observation.description
                    ),
                    raw_defc_value=raw_value,
                    funding_family=(
                        reference.funding_family
                    ),
                    extraordinary_flag=(
                        reference.extraordinary_flag
                    ),
                    covid_flag=(
                        reference.covid_flag
                    ),
                    iija_flag=(
                        reference.iija_flag
                    ),
                )
            )

        for segment in result.unparsed_segments:
            unparsed_observations.append(
                UnparsedDefcEvidence(
                    source_row_number=(
                        source.source_row_number
                    ),
                    assistance_transaction_id=(
                        source.assistance_transaction_id
                    ),
                    assistance_transaction_unique_key=(
                        source
                        .assistance_transaction_unique_key
                    ),
                    unparsed_segment=segment,
                    raw_defc_value=raw_value,
                )
            )

    require_unique_relationships(
        (
            relationship.assistance_transaction_id,
            relationship.extraordinary_funding_code_id,
        )
        for relationship in known_relationships
    )

    return (
        known_relationships,
        unknown_observations,
        unparsed_observations,
        rows_with_defc_count,
        parsed_observation_count,
    )


def load_existing_relationships(
    cur,
    *,
    load_batch_id: int,
) -> dict[
    tuple[int, int],
    tuple[str, str],
]:
    """
    Load existing classified relationships for one batch.

    Returns:
        (transaction ID, reference ID) ->
        (observed description, raw DEFC value).
    """

    cur.execute(
        """
        SELECT
            relationship.assistance_transaction_id,
            relationship.extraordinary_funding_code_id,
            relationship.observed_description,
            relationship.raw_defc_value

        FROM assistance.award_transaction_defc AS relationship

        JOIN assistance.award_transaction AS transaction
          ON transaction.assistance_transaction_id
             = relationship.assistance_transaction_id

        WHERE transaction.assistance_transaction_unique_key IN (
            SELECT raw.assistance_transaction_unique_key
            FROM assistance.raw_award_transaction AS raw
            WHERE raw.load_batch_id = %s
        );
        """,
        (load_batch_id,),
    )

    existing: dict[
        tuple[int, int],
        tuple[str, str],
    ] = {}

    for row in cur.fetchall():
        key = (
            int(row[0]),
            int(row[1]),
        )

        if key in existing:
            raise ValueError(
                f"Duplicate stored extraordinary-funding "
                f"relationship {key!r}."
            )

        existing[key] = (
            str(row[2]),
            str(row[3]),
        )

    return existing


def upsert_relationships(
    cur,
    *,
    relationships: list[KnownRelationship],
    existing: dict[
        tuple[int, int],
        tuple[str, str],
    ],
) -> tuple[int, int, int]:
    """Insert or update known extraordinary-funding relationships."""

    inserted = 0
    updated = 0
    unchanged = 0

    changed_values: list[
        tuple[int, int, str, str]
    ] = []

    expected_keys: set[
        tuple[int, int]
    ] = set()

    for relationship in relationships:
        key = (
            relationship.assistance_transaction_id,
            relationship.extraordinary_funding_code_id,
        )

        expected_keys.add(key)

        proposed = (
            relationship.observed_description,
            relationship.raw_defc_value,
        )

        stored = existing.get(
            key
        )

        if stored is None:
            inserted += 1
            changed_values.append(
                (
                    relationship
                    .assistance_transaction_id,
                    relationship
                    .extraordinary_funding_code_id,
                    relationship.observed_description,
                    relationship.raw_defc_value,
                )
            )
        elif stored == proposed:
            unchanged += 1
        else:
            updated += 1
            changed_values.append(
                (
                    relationship
                    .assistance_transaction_id,
                    relationship
                    .extraordinary_funding_code_id,
                    relationship.observed_description,
                    relationship.raw_defc_value,
                )
            )

    stale_keys = set(existing) - expected_keys

    if stale_keys:
        examples = sorted(
            stale_keys
        )[:20]

        raise ValueError(
            "Stored extraordinary-funding relationships exist "
            "that are no longer produced by the parser or reference "
            f"table. Examples: {examples!r}"
        )

    if changed_values:
        execute_values(
            cur,
            """
            INSERT INTO assistance.award_transaction_defc (
                assistance_transaction_id,
                extraordinary_funding_code_id,
                observed_description,
                raw_defc_value
            )
            VALUES %s

            ON CONFLICT (
                assistance_transaction_id,
                extraordinary_funding_code_id
            )
            DO UPDATE SET
                observed_description =
                    EXCLUDED.observed_description,
                raw_defc_value =
                    EXCLUDED.raw_defc_value;
            """,
            changed_values,
            template="(%s, %s, %s, %s)",
            page_size=PAGE_SIZE,
        )

    return (
        inserted,
        updated,
        unchanged,
    )


def validate_database_results(
    cur,
    *,
    load_batch_id: int,
    expected_relationship_count: int,
) -> dict[str, int]:
    """Validate stored relationship completeness and referential integrity."""

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction_defc AS relationship
        JOIN assistance.award_transaction AS transaction
          ON transaction.assistance_transaction_id
             = relationship.assistance_transaction_id
        WHERE transaction.assistance_transaction_unique_key IN (
            SELECT raw.assistance_transaction_unique_key
            FROM assistance.raw_award_transaction AS raw
            WHERE raw.load_batch_id = %s
        );
        """,
        (load_batch_id,),
    )

    stored_relationship_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                relationship.assistance_transaction_id,
                relationship.extraordinary_funding_code_id
            FROM assistance.award_transaction_defc AS relationship
            JOIN assistance.award_transaction AS transaction
              ON transaction.assistance_transaction_id
                 = relationship.assistance_transaction_id
            WHERE transaction.assistance_transaction_unique_key IN (
                SELECT raw.assistance_transaction_unique_key
                FROM assistance.raw_award_transaction AS raw
                WHERE raw.load_batch_id = %s
            )
            GROUP BY
                relationship.assistance_transaction_id,
                relationship.extraordinary_funding_code_id
            HAVING COUNT(*) > 1
        ) AS duplicates;
        """,
        (load_batch_id,),
    )

    duplicate_relationship_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction_defc AS relationship

        LEFT JOIN assistance.award_transaction AS transaction
          ON transaction.assistance_transaction_id
             = relationship.assistance_transaction_id

        WHERE transaction.assistance_transaction_id IS NULL;
        """
    )

    orphan_transaction_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction_defc AS relationship

        LEFT JOIN reference.extraordinary_funding_code AS reference
          ON reference.extraordinary_funding_code_id
             = relationship.extraordinary_funding_code_id

        WHERE reference.extraordinary_funding_code_id IS NULL;
        """
    )

    orphan_reference_count = int(
        cur.fetchone()[0]
    )

    require_equal_count(
        label="Stored extraordinary-funding relationships",
        expected=expected_relationship_count,
        actual=stored_relationship_count,
    )

    require_no_database_failures(
        {
            "duplicate_relationship_count": (
                duplicate_relationship_count
            ),
            "orphan_transaction_count": (
                orphan_transaction_count
            ),
            "orphan_reference_count": (
                orphan_reference_count
            ),
        }
    )

    return {
        "stored_relationship_count": (
            stored_relationship_count
        ),
        "duplicate_relationship_count": (
            duplicate_relationship_count
        ),
        "orphan_transaction_count": (
            orphan_transaction_count
        ),
        "orphan_reference_count": (
            orphan_reference_count
        ),
    }


def count_multi_code_transactions(
    *,
    known_relationships: list[KnownRelationship],
    unknown_observations: list[UnknownDefcEvidence],
) -> int:
    """Count transactions with more than one parsed DEFC code."""

    counts: Counter[int] = Counter()

    for relationship in known_relationships:
        counts[
            relationship.assistance_transaction_id
        ] += 1

    for observation in unknown_observations:
        counts[
            observation.assistance_transaction_id
        ] += 1

    return sum(
        count > 1
        for count in counts.values()
    )


def build_known_evidence(
    relationships: list[KnownRelationship],
) -> list[KnownDefcLinkEvidence]:
    """Convert persistence relationships to evidence records."""

    return [
        KnownDefcLinkEvidence(
            source_row_number=(
                relationship.source_row_number
            ),
            assistance_transaction_id=(
                relationship.assistance_transaction_id
            ),
            assistance_transaction_unique_key=(
                relationship
                .assistance_transaction_unique_key
            ),
            defc_code=relationship.defc_code,
            observed_description=(
                relationship.observed_description
            ),
            raw_defc_value=(
                relationship.raw_defc_value
            ),
            funding_family=(
                relationship.funding_family
            ),
            extraordinary_flag=(
                relationship.extraordinary_flag
            ),
            covid_flag=(
                relationship.covid_flag
            ),
            iija_flag=(
                relationship.iija_flag
            ),
        )
        for relationship in relationships
    ]


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    print("=" * 72)
    print(
        "ETL-005D.6 — Link Assistance Extraordinary Funding"
    )
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            reference_lookup = load_reference_lookup(
                cur
            )

            sources = extract_transaction_sources(
                cur,
                load_batch_id=args.load_batch_id,
            )

            (
                known_relationships,
                unknown_observations,
                unparsed_observations,
                rows_with_defc_count,
                parsed_observation_count,
            ) = classify_sources(
                sources=sources,
                reference_lookup=reference_lookup,
            )

            existing = load_existing_relationships(
                cur,
                load_batch_id=args.load_batch_id,
            )

            (
                inserted,
                updated,
                unchanged,
            ) = upsert_relationships(
                cur,
                relationships=known_relationships,
                existing=existing,
            )

            validation = validate_database_results(
                cur,
                load_batch_id=args.load_batch_id,
                expected_relationship_count=len(
                    known_relationships
                ),
            )

        conn.commit()

        multi_code_transaction_count = (
            count_multi_code_transactions(
                known_relationships=(
                    known_relationships
                ),
                unknown_observations=(
                    unknown_observations
                ),
            )
        )

        distinct_known_codes = {
            relationship.defc_code
            for relationship in known_relationships
        }

        distinct_unknown_codes = {
            observation.defc_code
            for observation in unknown_observations
        }

        summary = ExtraordinaryFundingEvidenceSummary(
            load_batch_id=args.load_batch_id,
            raw_observation_count=len(sources),
            rows_with_defc_count=rows_with_defc_count,
            parsed_observation_count=(
                parsed_observation_count
            ),
            known_relationship_count=len(
                known_relationships
            ),
            unknown_observation_count=len(
                unknown_observations
            ),
            unparsed_segment_count=len(
                unparsed_observations
            ),
            distinct_known_code_count=len(
                distinct_known_codes
            ),
            distinct_unknown_code_count=len(
                distinct_unknown_codes
            ),
            multi_code_transaction_count=(
                multi_code_transaction_count
            ),
            inserted_count=inserted,
            updated_count=updated,
            unchanged_count=unchanged,
            duplicate_relationship_count=(
                validation[
                    "duplicate_relationship_count"
                ]
            ),
            orphan_transaction_count=(
                validation[
                    "orphan_transaction_count"
                ]
            ),
            orphan_reference_count=(
                validation[
                    "orphan_reference_count"
                ]
            ),
        )

        evidence_directory = (
            EVIDENCE_ROOT
            / f"batch_{args.load_batch_id:04d}"
            / "enrichment"
            / "extraordinary_funding"
        )

        write_extraordinary_funding_evidence(
            output_directory=(
                evidence_directory
            ),
            known_links=build_known_evidence(
                known_relationships
            ),
            unknown_observations=(
                unknown_observations
            ),
            unparsed_observations=(
                unparsed_observations
            ),
            summary=summary,
        )

        print()
        print("=" * 72)
        print("ETL-005D.6 SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{len(sources):,}"
        )
        print(
            "Rows with DEFC values .......... "
            f"{rows_with_defc_count:,}"
        )
        print(
            "Parsed code observations ....... "
            f"{parsed_observation_count:,}"
        )
        print(
            "Known relationship rows ........ "
            f"{len(known_relationships):,}"
        )
        print(
            "Unknown code observations ...... "
            f"{len(unknown_observations):,}"
        )
        print(
            "Unparsed segments .............. "
            f"{len(unparsed_observations):,}"
        )
        print(
            "Distinct known DEFC codes ...... "
            f"{len(distinct_known_codes):,}"
        )
        print(
            "Distinct unknown DEFC codes .... "
            f"{len(distinct_unknown_codes):,}"
        )
        print(
            "Multiple-code transactions ..... "
            f"{multi_code_transaction_count:,}"
        )
        print(
            "Relationships inserted ......... "
            f"{inserted:,}"
        )
        print(
            "Relationships updated .......... "
            f"{updated:,}"
        )
        print(
            "Relationships unchanged ........ "
            f"{unchanged:,}"
        )
        print(
            "Duplicate relationships ........ "
            f"{validation['duplicate_relationship_count']:,}"
        )
        print(
            "Orphan transaction links ....... "
            f"{validation['orphan_transaction_count']:,}"
        )
        print(
            "Orphan reference links ......... "
            f"{validation['orphan_reference_count']:,}"
        )
        print(
            "Validation ..................... PASS"
        )
        print(
            "Evidence directory ............. "
            f"{evidence_directory}"
        )
        print("=" * 72)
        print()
        print(
            "Assistance extraordinary-funding "
            "relationships linked successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance extraordinary-funding "
            "relationship enrichment failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()