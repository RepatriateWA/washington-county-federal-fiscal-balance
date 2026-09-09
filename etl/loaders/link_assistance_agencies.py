"""Link Assistance awards and transactions to shared federal agencies."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from psycopg2.extras import execute_values

from etl.common.db import get_connection
from etl.common.normalization.text import clean_optional_text


EVIDENCE_ROOT = Path("evidence/assistance")
PAGE_SIZE = 1_000


@dataclass(frozen=True)
class AgencyRelationshipObservation:
    """One agency relationship configuration observed on a transaction."""

    source_row_number: int
    assistance_award_unique_key: str
    assistance_transaction_unique_key: str
    action_date: date | None

    awarding_agency_id: int
    awarding_subagency_id: int

    funding_agency_id: int | None
    funding_subagency_id: int | None

    awarding_agency_code: str
    awarding_subagency_code: str
    funding_agency_code: str | None
    funding_subagency_code: str | None


@dataclass(frozen=True)
class AwardAgencySelection:
    """Canonical current agency configuration for one award."""

    assistance_award_unique_key: str

    awarding_agency_id: int
    awarding_subagency_id: int

    funding_agency_id: int | None
    funding_subagency_id: int | None

    awarding_agency_code: str
    awarding_subagency_code: str
    funding_agency_code: str | None
    funding_subagency_code: str | None

    selected_source_row_number: int
    selected_action_date: date | None

    distinct_configuration_count: int
    observation_count: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Link Assistance awards and transactions to the "
            "shared USAspending agency domain."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()


def parse_date(
    value: object,
    *,
    source_row_number: int,
) -> date | None:
    """Parse an optional ISO-style action date."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError as exc:
        raise ValueError(
            f"Source row {source_row_number:,}: "
            f"invalid action_date {value!r}."
        ) from exc


def load_agency_lookup(
    cur,
) -> dict[str, int]:
    """Load the unique shared agency-code lookup."""

    cur.execute(
        """
        SELECT
            agency_code,
            agency_id
        FROM procurement.agency
        WHERE agency_code IS NOT NULL
        ORDER BY agency_id;
        """
    )

    lookup: dict[str, int] = {}

    for agency_code, agency_id in cur.fetchall():
        code = str(agency_code).strip()

        if code in lookup:
            raise ValueError(
                f"Shared agency code {code!r} occurs more than once."
            )

        lookup[code] = int(agency_id)

    return lookup


def resolve_required_agency(
    *,
    agency_code: object,
    role: str,
    source_row_number: int,
    agency_lookup: dict[str, int],
) -> tuple[str, int]:
    """Resolve a required agency code."""

    cleaned_code = clean_optional_text(
        agency_code
    )

    if cleaned_code is None:
        raise ValueError(
            f"Source row {source_row_number:,}: "
            f"{role} is missing."
        )

    agency_id = agency_lookup.get(
        cleaned_code
    )

    if agency_id is None:
        raise ValueError(
            f"Source row {source_row_number:,}: "
            f"{role} code {cleaned_code!r} is unresolved."
        )

    return cleaned_code, agency_id


def resolve_optional_agency(
    *,
    agency_code: object,
    role: str,
    source_row_number: int,
    agency_lookup: dict[str, int],
) -> tuple[str | None, int | None]:
    """Resolve an optional agency code."""

    cleaned_code = clean_optional_text(
        agency_code
    )

    if cleaned_code is None:
        return None, None

    agency_id = agency_lookup.get(
        cleaned_code
    )

    if agency_id is None:
        raise ValueError(
            f"Source row {source_row_number:,}: "
            f"{role} code {cleaned_code!r} is unresolved."
        )

    return cleaned_code, agency_id


def extract_observations(
    cur,
    *,
    load_batch_id: int,
    agency_lookup: dict[str, int],
) -> tuple[int, list[AgencyRelationshipObservation]]:
    """Extract and resolve agency relationships for all raw rows."""

    cur.execute(
        """
        SELECT
            source_row_number,
            assistance_award_unique_key,
            assistance_transaction_unique_key,

            raw_record ->> 'action_date',

            raw_record ->> 'awarding_agency_code',
            raw_record ->> 'awarding_sub_agency_code',

            raw_record ->> 'funding_agency_code',
            raw_record ->> 'funding_sub_agency_code'

        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
        ORDER BY source_row_number;
        """,
        (load_batch_id,),
    )

    rows = cur.fetchall()

    if not rows:
        raise ValueError(
            f"No raw Assistance rows found for load batch "
            f"{load_batch_id}."
        )

    observations: list[
        AgencyRelationshipObservation
    ] = []

    for row in rows:
        source_row_number = int(row[0])

        (
            awarding_agency_code,
            awarding_agency_id,
        ) = resolve_required_agency(
            agency_code=row[4],
            role="awarding agency",
            source_row_number=source_row_number,
            agency_lookup=agency_lookup,
        )

        (
            awarding_subagency_code,
            awarding_subagency_id,
        ) = resolve_required_agency(
            agency_code=row[5],
            role="awarding subagency",
            source_row_number=source_row_number,
            agency_lookup=agency_lookup,
        )

        (
            funding_agency_code,
            funding_agency_id,
        ) = resolve_optional_agency(
            agency_code=row[6],
            role="funding agency",
            source_row_number=source_row_number,
            agency_lookup=agency_lookup,
        )

        (
            funding_subagency_code,
            funding_subagency_id,
        ) = resolve_optional_agency(
            agency_code=row[7],
            role="funding subagency",
            source_row_number=source_row_number,
            agency_lookup=agency_lookup,
        )

        if (
            funding_agency_code is None
            and funding_subagency_code is not None
        ):
            raise ValueError(
                f"Source row {source_row_number:,}: "
                "funding subagency is populated while funding "
                "agency is missing."
            )

        if (
            funding_agency_code is not None
            and funding_subagency_code is None
        ):
            raise ValueError(
                f"Source row {source_row_number:,}: "
                "funding agency is populated while funding "
                "subagency is missing."
            )

        observations.append(
            AgencyRelationshipObservation(
                source_row_number=source_row_number,
                assistance_award_unique_key=str(
                    row[1]
                ),
                assistance_transaction_unique_key=str(
                    row[2]
                ),
                action_date=parse_date(
                    row[3],
                    source_row_number=source_row_number,
                ),
                awarding_agency_id=awarding_agency_id,
                awarding_subagency_id=(
                    awarding_subagency_id
                ),
                funding_agency_id=funding_agency_id,
                funding_subagency_id=(
                    funding_subagency_id
                ),
                awarding_agency_code=(
                    awarding_agency_code
                ),
                awarding_subagency_code=(
                    awarding_subagency_code
                ),
                funding_agency_code=(
                    funding_agency_code
                ),
                funding_subagency_code=(
                    funding_subagency_code
                ),
            )
        )

    return len(rows), observations


def award_selection_sort_key(
    observation: AgencyRelationshipObservation,
) -> tuple[bool, int, int, str, str, str, str]:
    """Order award observations for deterministic selection."""

    return (
        observation.action_date is None,
        (
            -observation.action_date.toordinal()
            if observation.action_date is not None
            else 0
        ),
        -observation.source_row_number,
        observation.awarding_agency_code,
        observation.awarding_subagency_code,
        observation.funding_agency_code or "",
        observation.funding_subagency_code or "",
    )


def agency_configuration(
    observation: AgencyRelationshipObservation,
) -> tuple[int, int, int | None, int | None]:
    """Return the full agency configuration for one observation."""

    return (
        observation.awarding_agency_id,
        observation.awarding_subagency_id,
        observation.funding_agency_id,
        observation.funding_subagency_id,
    )


def build_award_selections(
    observations: list[AgencyRelationshipObservation],
) -> list[AwardAgencySelection]:
    """Select one current agency configuration per award."""

    grouped: dict[
        str,
        list[AgencyRelationshipObservation],
    ] = defaultdict(list)

    for observation in observations:
        grouped[
            observation.assistance_award_unique_key
        ].append(observation)

    selections: list[
        AwardAgencySelection
    ] = []

    for award_key in sorted(grouped):
        candidates = grouped[award_key]

        selected = sorted(
            candidates,
            key=award_selection_sort_key,
        )[0]

        distinct_configurations = {
            agency_configuration(item)
            for item in candidates
        }

        selections.append(
            AwardAgencySelection(
                assistance_award_unique_key=award_key,
                awarding_agency_id=(
                    selected.awarding_agency_id
                ),
                awarding_subagency_id=(
                    selected.awarding_subagency_id
                ),
                funding_agency_id=(
                    selected.funding_agency_id
                ),
                funding_subagency_id=(
                    selected.funding_subagency_id
                ),
                awarding_agency_code=(
                    selected.awarding_agency_code
                ),
                awarding_subagency_code=(
                    selected.awarding_subagency_code
                ),
                funding_agency_code=(
                    selected.funding_agency_code
                ),
                funding_subagency_code=(
                    selected.funding_subagency_code
                ),
                selected_source_row_number=(
                    selected.source_row_number
                ),
                selected_action_date=(
                    selected.action_date
                ),
                distinct_configuration_count=len(
                    distinct_configurations
                ),
                observation_count=len(candidates),
            )
        )

    return selections


def link_transactions(
    cur,
    *,
    load_batch_id: int,
    observations: list[AgencyRelationshipObservation],
) -> None:
    """
    Populate all four transaction-level agency relationships.

    Canonical transaction identity is global across load batches. A
    transaction observed in the current raw batch may have been inserted
    canonically by an earlier batch, so linkage uses the stable
    assistance_transaction_unique_key rather than batch-local provenance.
    """

    values = [
        (
            item.assistance_transaction_unique_key,
            item.awarding_agency_id,
            item.awarding_subagency_id,
            item.funding_agency_id,
            item.funding_subagency_id,
        )
        for item in observations
    ]

    execute_values(
        cur,
        """
        UPDATE assistance.award_transaction AS transaction
        SET
            awarding_agency_id =
                source.awarding_agency_id,
            awarding_subagency_id =
                source.awarding_subagency_id,
            funding_agency_id =
                source.funding_agency_id,
            funding_subagency_id =
                source.funding_subagency_id,
            updated_at = CASE
                WHEN transaction.awarding_agency_id
                        IS DISTINCT FROM
                        source.awarding_agency_id
                  OR transaction.awarding_subagency_id
                        IS DISTINCT FROM
                        source.awarding_subagency_id
                  OR transaction.funding_agency_id
                        IS DISTINCT FROM
                        source.funding_agency_id
                  OR transaction.funding_subagency_id
                        IS DISTINCT FROM
                        source.funding_subagency_id
                THEN CURRENT_TIMESTAMP
                ELSE transaction.updated_at
            END
        FROM (
            VALUES %s
        ) AS source (
            assistance_transaction_unique_key,
            awarding_agency_id,
            awarding_subagency_id,
            funding_agency_id,
            funding_subagency_id
        )
        WHERE transaction.assistance_transaction_unique_key
              = source.assistance_transaction_unique_key;
        """,
        values,
        template="(%s, %s, %s, %s, %s)",
        page_size=PAGE_SIZE,
    )

def link_awards(
    cur,
    *,
    selections: list[AwardAgencySelection],
) -> None:
    """Populate all four award-level agency relationships."""

    values = [
        (
            item.assistance_award_unique_key,
            item.awarding_agency_id,
            item.awarding_subagency_id,
            item.funding_agency_id,
            item.funding_subagency_id,
        )
        for item in selections
    ]

    execute_values(
        cur,
        """
        UPDATE assistance.award AS award
        SET
            awarding_agency_id =
                source.awarding_agency_id,
            awarding_subagency_id =
                source.awarding_subagency_id,
            funding_agency_id =
                source.funding_agency_id,
            funding_subagency_id =
                source.funding_subagency_id,
            updated_at = CASE
                WHEN award.awarding_agency_id
                        IS DISTINCT FROM
                        source.awarding_agency_id
                  OR award.awarding_subagency_id
                        IS DISTINCT FROM
                        source.awarding_subagency_id
                  OR award.funding_agency_id
                        IS DISTINCT FROM
                        source.funding_agency_id
                  OR award.funding_subagency_id
                        IS DISTINCT FROM
                        source.funding_subagency_id
                THEN CURRENT_TIMESTAMP
                ELSE award.updated_at
            END
        FROM (
            VALUES %s
        ) AS source (
            assistance_award_unique_key,
            awarding_agency_id,
            awarding_subagency_id,
            funding_agency_id,
            funding_subagency_id
        )
        WHERE award.assistance_award_unique_key
              = source.assistance_award_unique_key;
        """,
        values,
        template="(%s, %s, %s, %s, %s)",
        page_size=PAGE_SIZE,
    )


def validate_results(
    cur,
    *,
    load_batch_id: int,
    raw_row_count: int,
    expected_award_count: int,
) -> dict[str, int]:
    """Validate transaction- and award-level agency enrichment."""

    cur.execute(
        """
        SELECT
            COUNT(*) AS transaction_count,

            COUNT(awarding_agency_id)
                AS awarding_agency_count,

            COUNT(awarding_subagency_id)
                AS awarding_subagency_count,

            COUNT(funding_agency_id)
                AS funding_agency_count,

            COUNT(funding_subagency_id)
                AS funding_subagency_count,

            COUNT(*) FILTER (
                WHERE funding_agency_id IS NULL
                  AND funding_subagency_id IS NULL
            ) AS missing_funding_pair_count,

            COUNT(*) FILTER (
                WHERE (
                    funding_agency_id IS NULL
                    AND funding_subagency_id IS NOT NULL
                )
                OR (
                    funding_agency_id IS NOT NULL
                    AND funding_subagency_id IS NULL
                )
            ) AS partial_funding_pair_count

        FROM assistance.award_transaction AS transaction

        WHERE transaction.assistance_transaction_unique_key IN (
            SELECT raw.assistance_transaction_unique_key
            FROM assistance.raw_award_transaction AS raw
            WHERE raw.load_batch_id = %s
        );
        """,
        (load_batch_id,),
    )

    (
        transaction_count,
        awarding_agency_count,
        awarding_subagency_count,
        funding_agency_count,
        funding_subagency_count,
        missing_funding_pair_count,
        partial_funding_pair_count,
    ) = [
        int(value)
        for value in cur.fetchone()
    ]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction AS transaction

        LEFT JOIN procurement.agency AS awarding_agency
          ON awarding_agency.agency_id
             = transaction.awarding_agency_id

        LEFT JOIN procurement.agency AS awarding_subagency
          ON awarding_subagency.agency_id
             = transaction.awarding_subagency_id

        LEFT JOIN procurement.agency AS funding_agency
          ON funding_agency.agency_id
             = transaction.funding_agency_id

        LEFT JOIN procurement.agency AS funding_subagency
          ON funding_subagency.agency_id
             = transaction.funding_subagency_id

        WHERE transaction.assistance_transaction_unique_key IN (
            SELECT raw.assistance_transaction_unique_key
            FROM assistance.raw_award_transaction AS raw
            WHERE raw.load_batch_id = %s
        )
          AND (
                awarding_agency.agency_id IS NULL
             OR awarding_subagency.agency_id IS NULL
             OR (
                    transaction.funding_agency_id
                    IS NOT NULL
                AND funding_agency.agency_id IS NULL
                )
             OR (
                    transaction.funding_subagency_id
                    IS NOT NULL
                AND funding_subagency.agency_id IS NULL
                )
          );
        """,
        (load_batch_id,),
    )

    orphan_transaction_agency_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT
            COUNT(*) AS award_count,

            COUNT(*) FILTER (
                WHERE awarding_agency_id IS NULL
                   OR awarding_subagency_id IS NULL
            ) AS missing_required_award_agency_count,

            COUNT(*) FILTER (
                WHERE (
                    funding_agency_id IS NULL
                    AND funding_subagency_id IS NOT NULL
                )
                OR (
                    funding_agency_id IS NOT NULL
                    AND funding_subagency_id IS NULL
                )
            ) AS partial_award_funding_pair_count

        FROM assistance.award

        WHERE assistance_award_unique_key IN (
            SELECT DISTINCT
                assistance_award_unique_key
            FROM assistance.raw_award_transaction
            WHERE load_batch_id = %s
        );
        """,
        (load_batch_id,),
    )

    (
        award_count,
        missing_required_award_agency_count,
        partial_award_funding_pair_count,
    ) = [
        int(value)
        for value in cur.fetchone()
    ]

    if transaction_count != raw_row_count:
        raise ValueError(
            "Agency transaction reconciliation failed: "
            f"raw={raw_row_count:,}, "
            f"transactions={transaction_count:,}."
        )

    if award_count != expected_award_count:
        raise ValueError(
            "Agency award reconciliation failed: "
            f"expected={expected_award_count:,}, "
            f"stored={award_count:,}."
        )

    failure_counts = {
        "missing_awarding_agency_count": (
            transaction_count
            - awarding_agency_count
        ),
        "missing_awarding_subagency_count": (
            transaction_count
            - awarding_subagency_count
        ),
        "partial_funding_pair_count": (
            partial_funding_pair_count
        ),
        "orphan_transaction_agency_count": (
            orphan_transaction_agency_count
        ),
        "missing_required_award_agency_count": (
            missing_required_award_agency_count
        ),
        "partial_award_funding_pair_count": (
            partial_award_funding_pair_count
        ),
    }

    failures = {
        key: value
        for key, value in failure_counts.items()
        if value
    }

    if failures:
        raise ValueError(
            "Agency relationship validation failed: "
            f"{failures!r}"
        )

    return {
        "transaction_count": transaction_count,
        "awarding_agency_count": awarding_agency_count,
        "awarding_subagency_count": (
            awarding_subagency_count
        ),
        "funding_agency_count": funding_agency_count,
        "funding_subagency_count": (
            funding_subagency_count
        ),
        "missing_funding_pair_count": (
            missing_funding_pair_count
        ),
        "orphan_transaction_agency_count": (
            orphan_transaction_agency_count
        ),
        "award_count": award_count,
    }


def write_evidence(
    *,
    load_batch_id: int,
    raw_row_count: int,
    observations: list[AgencyRelationshipObservation],
    selections: list[AwardAgencySelection],
    validation: dict[str, int],
) -> Path:
    """Write deterministic agency-enrichment evidence."""

    output_directory = (
        EVIDENCE_ROOT
        / f"batch_{load_batch_id:04d}"
        / "enrichment"
        / "agencies"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    selection_file = (
        output_directory
        / "award_agency_selections.csv"
    )

    multiplicity_file = (
        output_directory
        / "award_agency_multiplicity.csv"
    )

    summary_file = (
        output_directory
        / "enrichment_summary.txt"
    )

    with selection_file.open(
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
                "assistance_award_unique_key",
                "awarding_agency_code",
                "awarding_subagency_code",
                "funding_agency_code",
                "funding_subagency_code",
                "selected_source_row_number",
                "selected_action_date",
                "distinct_configuration_count",
                "observation_count",
            ]
        )

        for selection in selections:
            writer.writerow(
                [
                    selection.assistance_award_unique_key,
                    selection.awarding_agency_code,
                    selection.awarding_subagency_code,
                    selection.funding_agency_code,
                    selection.funding_subagency_code,
                    selection.selected_source_row_number,
                    (
                        selection
                        .selected_action_date
                        .isoformat()
                        if selection.selected_action_date
                        is not None
                        else ""
                    ),
                    selection.distinct_configuration_count,
                    selection.observation_count,
                ]
            )

    observation_lookup: dict[
        str,
        list[AgencyRelationshipObservation],
    ] = defaultdict(list)

    for observation in observations:
        observation_lookup[
            observation.assistance_award_unique_key
        ].append(observation)

    selection_lookup = {
        selection.assistance_award_unique_key: selection
        for selection in selections
    }

    multiple_configuration_award_count = 0

    with multiplicity_file.open(
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
                "assistance_award_unique_key",
                "distinct_configuration_count",
                "source_row_number",
                "action_date",
                "awarding_agency_code",
                "awarding_subagency_code",
                "funding_agency_code",
                "funding_subagency_code",
                "selected_as_canonical",
            ]
        )

        for award_key in sorted(
            observation_lookup
        ):
            award_observations = (
                observation_lookup[award_key]
            )

            distinct_configurations = {
                agency_configuration(item)
                for item in award_observations
            }

            if len(distinct_configurations) <= 1:
                continue

            multiple_configuration_award_count += 1

            selected = selection_lookup[
                award_key
            ]

            for observation in sorted(
                award_observations,
                key=lambda item: (
                    item.source_row_number,
                    item.awarding_agency_code,
                    item.awarding_subagency_code,
                ),
            ):
                writer.writerow(
                    [
                        award_key,
                        len(distinct_configurations),
                        observation.source_row_number,
                        (
                            observation.action_date.isoformat()
                            if observation.action_date
                            is not None
                            else ""
                        ),
                        observation.awarding_agency_code,
                        observation.awarding_subagency_code,
                        observation.funding_agency_code,
                        observation.funding_subagency_code,
                        str(
                            observation.source_row_number
                            == selected
                            .selected_source_row_number
                            and agency_configuration(
                                observation
                            )
                            == (
                                selected.awarding_agency_id,
                                selected.awarding_subagency_id,
                                selected.funding_agency_id,
                                selected.funding_subagency_id,
                            )
                        ).upper(),
                    ]
                )

    summary_lines = [
        "=" * 72,
        "ETL-005D.4C — ASSISTANCE AGENCY RELATIONSHIP ENRICHMENT",
        "=" * 72,
        f"Load batch ID .................. {load_batch_id}",
        f"Raw observations examined ...... {raw_row_count:,}",
        (
            "Awarding agencies linked ....... "
            f"{validation['awarding_agency_count']:,}"
        ),
        (
            "Awarding subagencies linked .... "
            f"{validation['awarding_subagency_count']:,}"
        ),
        (
            "Funding agencies linked ........ "
            f"{validation['funding_agency_count']:,}"
        ),
        (
            "Funding subagencies linked ..... "
            f"{validation['funding_subagency_count']:,}"
        ),
        (
            "Missing funding pairs .......... "
            f"{validation['missing_funding_pair_count']:,}"
        ),
        (
            "Award relationships ............ "
            f"{validation['award_count']:,}"
        ),
        (
            "Awards with agency changes ..... "
            f"{multiple_configuration_award_count:,}"
        ),
        (
            "Orphan transaction agencies .... "
            f"{validation['orphan_transaction_agency_count']:,}"
        ),
        "Validation ..................... PASS",
        "=" * 72,
        "",
        (
            "Transaction relationships preserve the agency "
            "configuration observed on each raw source row."
        ),
        (
            "Award relationships use latest action date, latest "
            "source row, and agency codes as deterministic precedence."
        ),
        (
            "Missing funding agency pairs remain null and are not "
            "replaced with invented placeholder agencies."
        ),
        "",
    ]

    summary_file.write_text(
        "\n".join(summary_lines),
        encoding="utf-8",
        newline="\n",
    )

    return output_directory


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    print("=" * 72)
    print("ETL-005D.4C — Link Assistance Agencies")
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            agency_lookup = load_agency_lookup(
                cur
            )

            (
                raw_row_count,
                observations,
            ) = extract_observations(
                cur,
                load_batch_id=args.load_batch_id,
                agency_lookup=agency_lookup,
            )

            selections = build_award_selections(
                observations
            )

            link_transactions(
                cur,
                load_batch_id=args.load_batch_id,
                observations=observations,
            )

            link_awards(
                cur,
                selections=selections,
            )

            validation = validate_results(
                cur,
                load_batch_id=args.load_batch_id,
                raw_row_count=raw_row_count,
                expected_award_count=len(selections),
            )

        conn.commit()

        evidence_directory = write_evidence(
            load_batch_id=args.load_batch_id,
            raw_row_count=raw_row_count,
            observations=observations,
            selections=selections,
            validation=validation,
        )

        multiple_configuration_award_count = sum(
            item.distinct_configuration_count > 1
            for item in selections
        )

        print()
        print("=" * 72)
        print("ETL-005D.4C SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Awarding agencies linked ....... "
            f"{validation['awarding_agency_count']:,}"
        )
        print(
            "Awarding subagencies linked .... "
            f"{validation['awarding_subagency_count']:,}"
        )
        print(
            "Funding agencies linked ........ "
            f"{validation['funding_agency_count']:,}"
        )
        print(
            "Funding subagencies linked ..... "
            f"{validation['funding_subagency_count']:,}"
        )
        print(
            "Missing funding pairs .......... "
            f"{validation['missing_funding_pair_count']:,}"
        )
        print(
            "Award relationships ............ "
            f"{validation['award_count']:,}"
        )
        print(
            "Awards with agency changes ..... "
            f"{multiple_configuration_award_count:,}"
        )
        print(
            "Orphan transaction agencies .... "
            f"{validation['orphan_transaction_agency_count']:,}"
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
            "Assistance agency relationships linked "
            "successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance agency relationship enrichment failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()