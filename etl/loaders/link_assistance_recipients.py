"""Link Assistance awards and transactions to canonical shared recipients."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from psycopg2.extras import execute_values

from etl.common.db import get_connection
from etl.common.identity import (
    RecipientIdentityInput,
    classify_recipient_identity,
)
from etl.common.normalization.text import (
    clean_optional_text,
)


EVIDENCE_ROOT = Path("evidence/assistance")
INSERT_PAGE_SIZE = 1_000


@dataclass(frozen=True)
class RecipientRelationshipObservation:
    """One recipient relationship observed on a raw transaction."""

    source_row_number: int
    assistance_award_unique_key: str
    assistance_transaction_unique_key: str
    action_date: date | None

    recipient_identity_key: str
    recipient_id: int


@dataclass(frozen=True)
class AwardRecipientSelection:
    """Canonical recipient selected for one Assistance award."""

    assistance_award_unique_key: str
    recipient_id: int
    recipient_identity_key: str

    source_row_number: int
    action_date: date | None

    distinct_recipient_count: int
    observation_count: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Link Assistance awards and transactions to canonical "
            "shared USAspending recipients."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()


def parse_date(value: object) -> date | None:
    """Parse an optional ISO-style source date."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError as exc:
        raise ValueError(
            f"Invalid action_date value {value!r}."
        ) from exc


def classify_raw_recipient(
    *,
    recipient_name: object,
    recipient_uei: object,
    recipient_country_code: object,
    recipient_state_code: object,
    recipient_city_name: object,
    recipient_zip_code: object,
    recipient_address_line_1: object,
    business_types_code: object,
) -> str:
    """Recompute one recipient identity using the shared engine."""

    cleaned_name = clean_optional_text(
        recipient_name
    )

    if cleaned_name is None:
        raise ValueError(
            "Recipient relationship observation has no recipient name."
        )

    identity = classify_recipient_identity(
        RecipientIdentityInput(
            recipient_name=cleaned_name,
            recipient_uei=clean_optional_text(
                recipient_uei
            ),
            recipient_country_code=clean_optional_text(
                recipient_country_code
            ),
            recipient_state_code=clean_optional_text(
                recipient_state_code
            ),
            recipient_city_name=clean_optional_text(
                recipient_city_name
            ),
            recipient_zip_code=clean_optional_text(
                recipient_zip_code
            ),
            recipient_address_line_1=clean_optional_text(
                recipient_address_line_1
            ),
            business_types_code=clean_optional_text(
                business_types_code
            ),
        )
    )

    return identity.identity_key


def load_recipient_lookup(
    cur,
) -> dict[str, int]:
    """Load canonical recipient identity-key mappings."""

    cur.execute(
        """
        SELECT
            recipient_identity_key,
            recipient_id
        FROM procurement.recipient
        WHERE recipient_identity_key IS NOT NULL;
        """
    )

    lookup: dict[str, int] = {}

    for identity_key, recipient_id in cur.fetchall():
        key = str(identity_key)

        if key in lookup:
            raise ValueError(
                f"Duplicate shared recipient identity key {key!r}."
            )

        lookup[key] = int(recipient_id)

    return lookup


def extract_relationship_observations(
    cur,
    *,
    load_batch_id: int,
    recipient_lookup: dict[str, int],
) -> tuple[int, list[RecipientRelationshipObservation]]:
    """Extract and resolve recipient relationships from raw rows."""

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    raw_row_count = int(
        cur.fetchone()[0]
    )

    if raw_row_count == 0:
        raise ValueError(
            f"No raw Assistance rows found for load batch "
            f"{load_batch_id}."
        )

    cur.execute(
        """
        SELECT
            source_row_number,
            assistance_award_unique_key,
            assistance_transaction_unique_key,

            raw_record ->> 'action_date',

            raw_record ->> 'recipient_name',
            raw_record ->> 'recipient_uei',
            raw_record ->> 'recipient_country_code',
            raw_record ->> 'recipient_state_code',
            raw_record ->> 'recipient_city_name',
            raw_record ->> 'recipient_zip_code',
            raw_record ->> 'recipient_address_line_1',
            raw_record ->> 'business_types_code'

        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
        ORDER BY source_row_number;
        """,
        (load_batch_id,),
    )

    observations: list[
        RecipientRelationshipObservation
    ] = []

    unresolved_keys: dict[str, int] = defaultdict(int)

    for row in cur.fetchall():
        source_row_number = int(row[0])

        identity_key = classify_raw_recipient(
            recipient_name=row[4],
            recipient_uei=row[5],
            recipient_country_code=row[6],
            recipient_state_code=row[7],
            recipient_city_name=row[8],
            recipient_zip_code=row[9],
            recipient_address_line_1=row[10],
            business_types_code=row[11],
        )

        recipient_id = recipient_lookup.get(
            identity_key
        )

        if recipient_id is None:
            unresolved_keys[identity_key] += 1
            continue

        observations.append(
            RecipientRelationshipObservation(
                source_row_number=source_row_number,
                assistance_award_unique_key=str(
                    row[1]
                ),
                assistance_transaction_unique_key=str(
                    row[2]
                ),
                action_date=parse_date(row[3]),
                recipient_identity_key=identity_key,
                recipient_id=recipient_id,
            )
        )

    if unresolved_keys:
        examples = sorted(
            unresolved_keys.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )[:10]

        raise ValueError(
            "Recipient relationship extraction found "
            f"{len(unresolved_keys):,} unresolved identity keys. "
            f"Examples: {examples!r}"
        )

    if len(observations) != raw_row_count:
        raise ValueError(
            "Recipient relationship extraction did not reconcile: "
            f"raw={raw_row_count:,}, "
            f"resolved={len(observations):,}."
        )

    return raw_row_count, observations


def award_selection_sort_key(
    observation: RecipientRelationshipObservation,
) -> tuple[bool, int, int, str]:
    """
    Sort recipient observations for award-level canonical selection.

    Precedence:
        1. latest populated action date;
        2. latest source row;
        3. identity key.
    """

    return (
        observation.action_date is None,
        (
            -observation.action_date.toordinal()
            if observation.action_date is not None
            else 0
        ),
        -observation.source_row_number,
        observation.recipient_identity_key,
    )


def build_award_selections(
    observations: list[RecipientRelationshipObservation],
) -> list[AwardRecipientSelection]:
    """Select one current canonical recipient per award."""

    grouped: dict[
        str,
        list[RecipientRelationshipObservation],
    ] = defaultdict(list)

    for observation in observations:
        grouped[
            observation.assistance_award_unique_key
        ].append(observation)

    selections: list[
        AwardRecipientSelection
    ] = []

    for award_key in sorted(grouped):
        candidates = grouped[award_key]

        selected = sorted(
            candidates,
            key=award_selection_sort_key,
        )[0]

        distinct_recipient_ids = {
            item.recipient_id
            for item in candidates
        }

        selections.append(
            AwardRecipientSelection(
                assistance_award_unique_key=award_key,
                recipient_id=selected.recipient_id,
                recipient_identity_key=(
                    selected.recipient_identity_key
                ),
                source_row_number=(
                    selected.source_row_number
                ),
                action_date=selected.action_date,
                distinct_recipient_count=len(
                    distinct_recipient_ids
                ),
                observation_count=len(candidates),
            )
        )

    return selections


def link_transactions(
    cur,
    *,
    load_batch_id: int,
    observations: list[RecipientRelationshipObservation],
) -> int:
    """Populate transaction recipient foreign keys."""

    values = [
        (
            observation.source_row_number,
            observation.recipient_id,
        )
        for observation in observations
    ]

    execute_values(
        cur,
        """
        UPDATE assistance.award_transaction AS transaction
        SET recipient_id = source.recipient_id
        FROM (
            VALUES %s
        ) AS source (
            source_row_number,
            recipient_id
        )
        WHERE transaction.load_batch_id = """
        + str(int(load_batch_id))
        + """
          AND transaction.source_row_number
              = source.source_row_number
        """,
        values,
        template="(%s, %s)",
        page_size=INSERT_PAGE_SIZE,
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction
        WHERE load_batch_id = %s
          AND recipient_id IS NOT NULL;
        """,
        (load_batch_id,),
    )

    return int(cur.fetchone()[0])


def link_awards(
    cur,
    *,
    selections: list[AwardRecipientSelection],
) -> int:
    """Populate canonical award-recipient foreign keys."""

    values = [
        (
            selection.assistance_award_unique_key,
            selection.recipient_id,
        )
        for selection in selections
    ]

    execute_values(
        cur,
        """
        UPDATE assistance.award AS award
        SET
            recipient_id = source.recipient_id,
            updated_at = CASE
                WHEN award.recipient_id
                     IS DISTINCT FROM source.recipient_id
                THEN CURRENT_TIMESTAMP
                ELSE award.updated_at
            END
        FROM (
            VALUES %s
        ) AS source (
            assistance_award_unique_key,
            recipient_id
        )
        WHERE award.assistance_award_unique_key
              = source.assistance_award_unique_key
        """,
        values,
        template="(%s, %s)",
        page_size=INSERT_PAGE_SIZE,
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award
        WHERE recipient_id IS NOT NULL
          AND assistance_award_unique_key = ANY(%s);
        """,
        (
            [
                selection.assistance_award_unique_key
                for selection in selections
            ],
        ),
    )

    return int(cur.fetchone()[0])


def validate_results(
    cur,
    *,
    load_batch_id: int,
    raw_row_count: int,
    expected_award_count: int,
) -> dict[str, int]:
    """Validate recipient relationship completeness and integrity."""

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    transaction_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction
        WHERE load_batch_id = %s
          AND recipient_id IS NULL;
        """,
        (load_batch_id,),
    )

    missing_transaction_recipient_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award_transaction AS transaction
        LEFT JOIN procurement.recipient AS recipient
          ON recipient.recipient_id
             = transaction.recipient_id
        WHERE transaction.load_batch_id = %s
          AND recipient.recipient_id IS NULL;
        """,
        (load_batch_id,),
    )

    orphan_transaction_recipient_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award
        WHERE assistance_award_unique_key IN (
            SELECT DISTINCT assistance_award_unique_key
            FROM assistance.raw_award_transaction
            WHERE load_batch_id = %s
        )
          AND recipient_id IS NULL;
        """,
        (load_batch_id,),
    )

    missing_award_recipient_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award AS award
        LEFT JOIN procurement.recipient AS recipient
          ON recipient.recipient_id
             = award.recipient_id
        WHERE award.assistance_award_unique_key IN (
            SELECT DISTINCT assistance_award_unique_key
            FROM assistance.raw_award_transaction
            WHERE load_batch_id = %s
        )
          AND recipient.recipient_id IS NULL;
        """,
        (load_batch_id,),
    )

    orphan_award_recipient_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(DISTINCT assistance_award_unique_key)
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    raw_award_count = int(
        cur.fetchone()[0]
    )

    if transaction_count != raw_row_count:
        raise ValueError(
            "Recipient transaction validation failed: "
            f"raw={raw_row_count:,}, "
            f"transactions={transaction_count:,}."
        )

    if raw_award_count != expected_award_count:
        raise ValueError(
            "Recipient award validation failed: "
            f"raw awards={raw_award_count:,}, "
            f"selections={expected_award_count:,}."
        )

    failure_counts = {
        "missing_transaction_recipient_count": (
            missing_transaction_recipient_count
        ),
        "orphan_transaction_recipient_count": (
            orphan_transaction_recipient_count
        ),
        "missing_award_recipient_count": (
            missing_award_recipient_count
        ),
        "orphan_award_recipient_count": (
            orphan_award_recipient_count
        ),
    }

    failures = {
        key: value
        for key, value in failure_counts.items()
        if value
    }

    if failures:
        raise ValueError(
            "Recipient relationship validation failed: "
            f"{failures!r}"
        )

    return {
        "transaction_count": transaction_count,
        "raw_award_count": raw_award_count,
        **failure_counts,
    }


def write_evidence(
    *,
    load_batch_id: int,
    raw_row_count: int,
    observations: list[RecipientRelationshipObservation],
    selections: list[AwardRecipientSelection],
    validation: dict[str, int],
) -> Path:
    """Write recipient-relationship evidence artifacts."""

    output_directory = (
        EVIDENCE_ROOT
        / f"batch_{load_batch_id:04d}"
        / "enrichment"
        / "recipients"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    award_selection_file = (
        output_directory
        / "award_recipient_selections.csv"
    )

    multi_recipient_file = (
        output_directory
        / "award_recipient_multiplicity.csv"
    )

    summary_file = (
        output_directory
        / "enrichment_summary.txt"
    )

    with award_selection_file.open(
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
                "recipient_id",
                "recipient_identity_key",
                "selected_source_row_number",
                "selected_action_date",
                "distinct_recipient_count",
                "observation_count",
            ]
        )

        for selection in selections:
            writer.writerow(
                [
                    selection.assistance_award_unique_key,
                    selection.recipient_id,
                    selection.recipient_identity_key,
                    selection.source_row_number,
                    (
                        selection.action_date.isoformat()
                        if selection.action_date is not None
                        else ""
                    ),
                    selection.distinct_recipient_count,
                    selection.observation_count,
                ]
            )

    multi_recipient_award_count = 0

    with multi_recipient_file.open(
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
                "distinct_recipient_count",
                "recipient_id",
                "recipient_identity_key",
                "source_row_number",
                "action_date",
                "selected_as_canonical",
            ]
        )

        observations_by_award: dict[
            str,
            list[RecipientRelationshipObservation],
        ] = defaultdict(list)

        for observation in observations:
            observations_by_award[
                observation.assistance_award_unique_key
            ].append(observation)

        selection_lookup = {
            selection.assistance_award_unique_key: selection
            for selection in selections
        }

        for award_key in sorted(
            observations_by_award
        ):
            award_observations = (
                observations_by_award[award_key]
            )

            distinct_recipient_ids = {
                item.recipient_id
                for item in award_observations
            }

            if len(distinct_recipient_ids) <= 1:
                continue

            multi_recipient_award_count += 1

            selection = selection_lookup[
                award_key
            ]

            for observation in sorted(
                award_observations,
                key=lambda item: (
                    item.source_row_number,
                    item.recipient_identity_key,
                ),
            ):
                writer.writerow(
                    [
                        award_key,
                        len(distinct_recipient_ids),
                        observation.recipient_id,
                        observation.recipient_identity_key,
                        observation.source_row_number,
                        (
                            observation.action_date.isoformat()
                            if observation.action_date
                            is not None
                            else ""
                        ),
                        str(
                            observation.source_row_number
                            == selection.source_row_number
                            and observation.recipient_id
                            == selection.recipient_id
                        ).upper(),
                    ]
                )

    summary_lines = [
        "=" * 72,
        "ETL-005D.2 — ASSISTANCE RECIPIENT RELATIONSHIP ENRICHMENT",
        "=" * 72,
        f"Load batch ID .................. {load_batch_id}",
        f"Raw observations examined ...... {raw_row_count:,}",
        f"Transaction relationships ...... {len(observations):,}",
        f"Award relationships ............ {len(selections):,}",
        (
            "Awards with multiple recipients "
            f"{multi_recipient_award_count:,}"
        ),
        (
            "Missing transaction recipients . "
            f"{validation['missing_transaction_recipient_count']:,}"
        ),
        (
            "Orphan transaction recipients .. "
            f"{validation['orphan_transaction_recipient_count']:,}"
        ),
        (
            "Missing award recipients ........ "
            f"{validation['missing_award_recipient_count']:,}"
        ),
        (
            "Orphan award recipients ......... "
            f"{validation['orphan_award_recipient_count']:,}"
        ),
        "Validation ..................... PASS",
        "=" * 72,
        "",
        (
            "Transaction recipient relationships preserve the "
            "recipient identity observed on each raw source row."
        ),
        (
            "Award recipient relationships use the latest populated "
            "action date, latest source row, and identity key as "
            "deterministic selection precedence."
        ),
        (
            "All observed recipient changes remain preserved in the "
            "raw layer and multiplicity evidence artifact."
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
    print(
        "ETL-005D.2 — Link Assistance Recipients"
    )
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            recipient_lookup = load_recipient_lookup(
                cur
            )

            (
                raw_row_count,
                observations,
            ) = extract_relationship_observations(
                cur,
                load_batch_id=args.load_batch_id,
                recipient_lookup=recipient_lookup,
            )

            selections = build_award_selections(
                observations
            )

            transaction_coverage = link_transactions(
                cur,
                load_batch_id=args.load_batch_id,
                observations=observations,
            )

            award_coverage = link_awards(
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

        multi_recipient_award_count = sum(
            selection.distinct_recipient_count > 1
            for selection in selections
        )

        print()
        print("=" * 72)
        print("ETL-005D.2 SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Transaction relationships ...... "
            f"{transaction_coverage:,}"
        )
        print(
            "Award relationships ............ "
            f"{award_coverage:,}"
        )
        print(
            "Awards with multiple recipients "
            f"{multi_recipient_award_count:,}"
        )
        print(
            "Missing transaction recipients . "
            f"{validation['missing_transaction_recipient_count']:,}"
        )
        print(
            "Orphan transaction recipients .. "
            f"{validation['orphan_transaction_recipient_count']:,}"
        )
        print(
            "Missing award recipients ........ "
            f"{validation['missing_award_recipient_count']:,}"
        )
        print(
            "Orphan award recipients ......... "
            f"{validation['orphan_award_recipient_count']:,}"
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
            "Assistance recipient relationships linked "
            "successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance recipient relationship enrichment failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()