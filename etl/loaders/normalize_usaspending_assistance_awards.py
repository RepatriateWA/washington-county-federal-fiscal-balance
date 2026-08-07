"""Normalize canonical USAspending Assistance awards."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from etl.common.db import get_connection
from etl.common.normalization.canonical import (
    select_canonical,
)
from etl.common.normalization.text import (
    clean_optional_text,
)


@dataclass(frozen=True)
class AwardObservation:
    """One raw observation contributing to a canonical award."""

    assistance_award_unique_key: str
    source_row_number: int
    action_date: date | None

    award_id_fain: str | None
    award_id_uri: str | None
    sai_number: str | None

    recipient_name: str | None
    award_description: str | None

    assistance_listing_id: int
    assistance_type_id: int
    funding_opportunity_id: int | None

    performance_start_date: date | None
    performance_end_date: date | None

    total_obligated_amount: Decimal | None
    total_outlayed_amount: Decimal | None
    total_non_federal_funding_amount: Decimal | None
    total_face_value_of_loan: Decimal | None
    total_loan_subsidy_cost: Decimal | None


@dataclass(frozen=True)
class CanonicalAward:
    """One deterministic canonical Assistance award."""

    assistance_award_unique_key: str

    award_id_fain: str | None
    award_id_uri: str | None
    sai_number: str | None

    assistance_listing_id: int
    assistance_type_id: int
    funding_opportunity_id: int | None

    period_of_performance_start_date: date | None
    period_of_performance_current_end_date: date | None

    total_obligated_amount: Decimal | None
    total_outlayed_amount: Decimal | None
    total_non_federal_funding_amount: Decimal | None
    total_face_value_of_loan: Decimal | None
    total_loan_subsidy_cost: Decimal | None

    canonical_recipient_name: str | None
    canonical_award_description: str | None

    first_action_date: date | None
    last_action_date: date | None


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize canonical Assistance awards from one "
            "raw USAspending Assistance load batch."
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
    """Parse an ISO-style source date."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    try:
        return date.fromisoformat(
            cleaned[:10]
        )
    except ValueError:
        return None


def parse_decimal(
    value: object,
) -> Decimal | None:
    """Parse one source monetary value exactly."""

    cleaned = clean_optional_text(value)

    if cleaned is None:
        return None

    cleaned = (
        cleaned
        .replace(",", "")
        .replace("$", "")
    )

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(
            f"Invalid monetary value: {value!r}"
        )


def extract_observations(
    cur,
    *,
    load_batch_id: int,
) -> tuple[int, list[AwardObservation]]:
    """Extract award observations with resolved native dimensions."""

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
            raw.assistance_award_unique_key,
            raw.source_row_number,

            raw.raw_record ->> 'action_date',

            raw.raw_record ->> 'award_id_fain',
            raw.raw_record ->> 'award_id_uri',
            raw.raw_record ->> 'sai_number',

            raw.raw_record ->> 'recipient_name',
            raw.raw_record
                ->> 'prime_award_base_transaction_description',

            listing.assistance_listing_id,
            assistance_type.assistance_type_id,
            opportunity.funding_opportunity_id,

            raw.raw_record
                ->> 'period_of_performance_start_date',
            raw.raw_record
                ->> 'period_of_performance_current_end_date',

            raw.raw_record ->> 'total_obligated_amount',
            raw.raw_record
                ->> 'total_outlayed_amount_for_overall_award',
            raw.raw_record
                ->> 'total_non_federal_funding_amount',
            raw.raw_record ->> 'total_face_value_of_loan',
            raw.raw_record ->> 'total_loan_subsidy_cost'

        FROM assistance.raw_award_transaction AS raw

        JOIN assistance.assistance_listing AS listing
          ON listing.cfda_number = BTRIM(
                raw.raw_record ->> 'cfda_number'
             )

        JOIN assistance.assistance_type AS assistance_type
          ON assistance_type.assistance_type_code = BTRIM(
                raw.raw_record ->> 'assistance_type_code'
             )

        LEFT JOIN assistance.funding_opportunity AS opportunity
          ON opportunity.funding_opportunity_number = NULLIF(
                BTRIM(
                    raw.raw_record
                    ->> 'funding_opportunity_number'
                ),
                ''
             )

        WHERE raw.load_batch_id = %s

        ORDER BY
            raw.assistance_award_unique_key,
            raw.source_row_number;
        """,
        (load_batch_id,),
    )

    observations: list[AwardObservation] = []

    for row in cur.fetchall():
        observations.append(
            AwardObservation(
                assistance_award_unique_key=str(row[0]),
                source_row_number=int(row[1]),
                action_date=parse_date(row[2]),

                award_id_fain=clean_optional_text(row[3]),
                award_id_uri=clean_optional_text(row[4]),
                sai_number=clean_optional_text(row[5]),

                recipient_name=clean_optional_text(row[6]),
                award_description=clean_optional_text(row[7]),

                assistance_listing_id=int(row[8]),
                assistance_type_id=int(row[9]),
                funding_opportunity_id=(
                    int(row[10])
                    if row[10] is not None
                    else None
                ),

                performance_start_date=parse_date(row[11]),
                performance_end_date=parse_date(row[12]),

                total_obligated_amount=parse_decimal(row[13]),
                total_outlayed_amount=parse_decimal(row[14]),
                total_non_federal_funding_amount=(
                    parse_decimal(row[15])
                ),
                total_face_value_of_loan=parse_decimal(row[16]),
                total_loan_subsidy_cost=parse_decimal(row[17]),
            )
        )

    if len(observations) != raw_row_count:
        raise ValueError(
            "Award observation extraction did not reconcile: "
            f"raw={raw_row_count:,}, "
            f"resolved={len(observations):,}."
        )

    return raw_row_count, observations


def latest_observation(
    observations: list[AwardObservation],
) -> AwardObservation:
    """Select the latest observation deterministically."""

    return select_canonical(
        observations,
        key=lambda item: (
            item.action_date is None,
            -item.action_date.toordinal()
            if item.action_date is not None
            else 0,
            -item.source_row_number,
        ),
    ).selected


def latest_non_null(
    observations: list[AwardObservation],
    attribute: str,
):
    """Select the latest populated value for one attribute."""

    populated = [
        item
        for item in observations
        if getattr(item, attribute) is not None
    ]

    if not populated:
        return None

    selected = latest_observation(populated)

    return getattr(
        selected,
        attribute,
    )


def build_canonical_awards(
    observations: list[AwardObservation],
) -> list[CanonicalAward]:
    """Aggregate raw observations into canonical awards."""

    grouped: dict[
        str,
        list[AwardObservation],
    ] = {}

    for observation in observations:
        grouped.setdefault(
            observation.assistance_award_unique_key,
            [],
        ).append(observation)

    awards: list[CanonicalAward] = []

    for award_key in sorted(grouped):
        candidates = grouped[award_key]
        latest = latest_observation(candidates)

        action_dates = [
            item.action_date
            for item in candidates
            if item.action_date is not None
        ]

        performance_starts = [
            item.performance_start_date
            for item in candidates
            if item.performance_start_date is not None
        ]

        performance_ends = [
            item.performance_end_date
            for item in candidates
            if item.performance_end_date is not None
        ]

        awards.append(
            CanonicalAward(
                assistance_award_unique_key=award_key,

                award_id_fain=latest_non_null(
                    candidates,
                    "award_id_fain",
                ),
                award_id_uri=latest_non_null(
                    candidates,
                    "award_id_uri",
                ),
                sai_number=latest_non_null(
                    candidates,
                    "sai_number",
                ),

                assistance_listing_id=(
                    latest.assistance_listing_id
                ),
                assistance_type_id=(
                    latest.assistance_type_id
                ),
                funding_opportunity_id=(
                    latest_non_null(
                        candidates,
                        "funding_opportunity_id",
                    )
                ),

                period_of_performance_start_date=(
                    min(performance_starts)
                    if performance_starts
                    else None
                ),
                period_of_performance_current_end_date=(
                    max(performance_ends)
                    if performance_ends
                    else None
                ),

                total_obligated_amount=latest_non_null(
                    candidates,
                    "total_obligated_amount",
                ),
                total_outlayed_amount=latest_non_null(
                    candidates,
                    "total_outlayed_amount",
                ),
                total_non_federal_funding_amount=(
                    latest_non_null(
                        candidates,
                        "total_non_federal_funding_amount",
                    )
                ),
                total_face_value_of_loan=latest_non_null(
                    candidates,
                    "total_face_value_of_loan",
                ),
                total_loan_subsidy_cost=latest_non_null(
                    candidates,
                    "total_loan_subsidy_cost",
                ),

                canonical_recipient_name=latest_non_null(
                    candidates,
                    "recipient_name",
                ),
                canonical_award_description=latest_non_null(
                    candidates,
                    "award_description",
                ),

                first_action_date=(
                    min(action_dates)
                    if action_dates
                    else None
                ),
                last_action_date=(
                    max(action_dates)
                    if action_dates
                    else None
                ),
            )
        )

    return awards


def upsert_awards(
    cur,
    awards: list[CanonicalAward],
) -> tuple[int, int, int]:
    """Insert, update, or leave canonical awards unchanged."""

    inserted = 0
    updated = 0
    unchanged = 0

    columns = (
        "award_id_fain",
        "award_id_uri",
        "sai_number",
        "assistance_listing_id",
        "assistance_type_id",
        "funding_opportunity_id",
        "period_of_performance_start_date",
        "period_of_performance_current_end_date",
        "total_obligated_amount",
        "total_outlayed_amount",
        "total_non_federal_funding_amount",
        "total_face_value_of_loan",
        "total_loan_subsidy_cost",
        "canonical_recipient_name",
        "canonical_award_description",
        "first_action_date",
        "last_action_date",
    )

    for award in awards:
        proposed = tuple(
            getattr(award, column)
            for column in columns
        )

        cur.execute(
            f"""
            SELECT {", ".join(columns)}
            FROM assistance.award
            WHERE assistance_award_unique_key = %s;
            """,
            (
                award.assistance_award_unique_key,
            ),
        )

        existing = cur.fetchone()

        if existing is None:
            placeholders = ", ".join(
                ["%s"] * (len(columns) + 1)
            )

            cur.execute(
                f"""
                INSERT INTO assistance.award (
                    assistance_award_unique_key,
                    {", ".join(columns)}
                )
                VALUES ({placeholders});
                """,
                (
                    award.assistance_award_unique_key,
                    *proposed,
                ),
            )

            inserted += 1

        elif existing == proposed:
            unchanged += 1

        else:
            assignments = ", ".join(
                f"{column} = %s"
                for column in columns
            )

            cur.execute(
                f"""
                UPDATE assistance.award
                SET
                    {assignments},
                    updated_at = CURRENT_TIMESTAMP
                WHERE assistance_award_unique_key = %s;
                """,
                (
                    *proposed,
                    award.assistance_award_unique_key,
                ),
            )

            updated += 1

    return inserted, updated, unchanged


def validate_results(
    cur,
    *,
    load_batch_id: int,
    expected_award_count: int,
) -> None:
    """Validate canonical award representation."""

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

    if raw_award_count != expected_award_count:
        raise ValueError(
            "Raw award count changed during normalization."
        )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award
        WHERE assistance_award_unique_key IN (
            SELECT DISTINCT assistance_award_unique_key
            FROM assistance.raw_award_transaction
            WHERE load_batch_id = %s
        );
        """,
        (load_batch_id,),
    )

    represented_count = int(
        cur.fetchone()[0]
    )

    if represented_count != expected_award_count:
        raise ValueError(
            "Canonical Assistance award validation failed: "
            f"expected={expected_award_count:,}, "
            f"represented={represented_count:,}."
        )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.award
        WHERE award_id_fain IS NULL
          AND award_id_uri IS NULL;
        """
    )

    missing_identity_count = int(
        cur.fetchone()[0]
    )

    if missing_identity_count:
        raise ValueError(
            f"{missing_identity_count:,} canonical awards "
            "lack both FAIN and URI."
        )


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    print("=" * 72)
    print("ETL-005C.4 — Normalize Assistance Awards")
    print("=" * 72)
    print(f"Target load batch: {args.load_batch_id}")

    try:
        with conn.cursor() as cur:
            (
                raw_row_count,
                observations,
            ) = extract_observations(
                cur,
                load_batch_id=args.load_batch_id,
            )

            awards = build_canonical_awards(
                observations
            )

            inserted, updated, unchanged = (
                upsert_awards(
                    cur,
                    awards,
                )
            )

            validate_results(
                cur,
                load_batch_id=args.load_batch_id,
                expected_award_count=len(awards),
            )

        conn.commit()

        print()
        print("=" * 72)
        print("ETL-005C.4 SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Canonical awards discovered .... "
            f"{len(awards):,}"
        )
        print(
            "Awards inserted ................ "
            f"{inserted:,}"
        )
        print(
            "Awards updated ................. "
            f"{updated:,}"
        )
        print(
            "Awards unchanged ............... "
            f"{unchanged:,}"
        )
        print(
            "Validation ..................... PASS"
        )
        print("=" * 72)
        print()
        print(
            "Assistance Award normalization "
            "completed successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance Award normalization failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()