
"""ETL-201H v0.2 — Historical assistance award certification.

Read-only. No canonical inserts, updates, or ledger changes.

Scope:
    FY2018 USAspending batch 20
    FY2019 USAspending batch 21
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from etl.common.db import get_connection
from etl.loaders.normalize_usaspending_assistance_awards import (
    AwardObservation,
    build_canonical_awards,
    parse_date,
    parse_decimal,
)


BATCH_IDS = (20, 21)

EXPECTED_HISTORICAL = 166710
EXPECTED_EXISTING = 10219
EXPECTED_MISSING = 156491
EXPECTED_CONFLICTED_MISSING = 90
EXPECTED_CANDIDATES = 156401


@dataclass(frozen=True)
class HistoricalObservation:
    batch_id: int
    source_row_number: int
    observation: AwardObservation


def get_cohort_counts(cur):
    """Independently reconcile historical source cohorts."""

    cur.execute(
        """
        WITH historical AS MATERIALIZED (
            SELECT
                assistance_award_unique_key AS award_key,
                NULLIF(
                    BTRIM(raw_record ->> 'cfda_number'),
                    ''
                ) AS listing_code,
                NULLIF(
                    BTRIM(
                        raw_record ->> 'assistance_type_code'
                    ),
                    ''
                ) AS type_code
            FROM assistance.raw_award_transaction
            WHERE load_batch_id IN (20, 21)
        ),
        grouped AS MATERIALIZED (
            SELECT
                award_key,
                COUNT(DISTINCT listing_code)
                    AS listing_count,
                COUNT(DISTINCT type_code)
                    AS type_count
            FROM historical
            GROUP BY award_key
        )
        SELECT
            COUNT(*) AS historical_count,
            COUNT(*) FILTER (
                WHERE a.assistance_award_unique_key
                    IS NOT NULL
            ) AS existing_count,
            COUNT(*) FILTER (
                WHERE a.assistance_award_unique_key
                    IS NULL
            ) AS missing_count,
            COUNT(*) FILTER (
                WHERE a.assistance_award_unique_key
                    IS NULL
                  AND (
                      g.listing_count > 1
                      OR g.type_count > 1
                  )
            ) AS conflicted_missing_count,
            COUNT(*) FILTER (
                WHERE a.assistance_award_unique_key
                    IS NULL
                  AND g.listing_count <= 1
                  AND g.type_count <= 1
            ) AS candidate_count
        FROM grouped AS g
        LEFT JOIN assistance.award AS a
          ON a.assistance_award_unique_key = g.award_key;
        """
    )

    return tuple(int(x) for x in cur.fetchone())


def extract_candidates(cur):
    """Extract only missing, non-conflicted historical awards."""

    cur.execute(
        """
        WITH historical AS MATERIALIZED (
            SELECT
                assistance_award_unique_key AS award_key,
                NULLIF(
                    BTRIM(raw_record ->> 'cfda_number'),
                    ''
                ) AS listing_code,
                NULLIF(
                    BTRIM(
                        raw_record ->> 'assistance_type_code'
                    ),
                    ''
                ) AS type_code
            FROM assistance.raw_award_transaction
            WHERE load_batch_id IN (20, 21)
        ),
        eligible AS MATERIALIZED (
            SELECT h.award_key
            FROM historical AS h
            GROUP BY h.award_key
            HAVING COUNT(DISTINCT h.listing_code) <= 1
               AND COUNT(DISTINCT h.type_code) <= 1
        )
        SELECT
            raw.assistance_award_unique_key,
            raw.load_batch_id,
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
            raw.raw_record ->> 'total_loan_subsidy_cost',

            NULLIF(
                BTRIM(raw.raw_record ->> 'cfda_number'),
                ''
            ) AS source_listing_code,

            NULLIF(
                BTRIM(
                    raw.raw_record ->> 'assistance_type_code'
                ),
                ''
            ) AS source_type_code

        FROM assistance.raw_award_transaction AS raw

        JOIN eligible AS e
          ON e.award_key = raw.assistance_award_unique_key

        LEFT JOIN assistance.award AS existing
          ON existing.assistance_award_unique_key
             = raw.assistance_award_unique_key

        LEFT JOIN assistance.assistance_listing AS listing
          ON listing.cfda_number = BTRIM(
              raw.raw_record ->> 'cfda_number'
          )

        LEFT JOIN assistance.assistance_type AS assistance_type
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

        WHERE raw.load_batch_id IN (20, 21)
          AND existing.assistance_award_unique_key IS NULL

        ORDER BY
            raw.assistance_award_unique_key,
            raw.load_batch_id,
            raw.source_row_number;
        """
    )

    return cur.fetchall()


def certify_rows(rows):
    """Validate source rows and construct canonical candidates."""

    errors = Counter()
    samples = defaultdict(list)
    observations = []
    award_keys = set()
    source_identities = set()

    def flag(name, key):
        errors[name] += 1
        if len(samples[name]) < 5:
            samples[name].append(key)

    for row in rows:
        (
            key, batch_id, source_row,
            action_text, fain, uri, sai,
            recipient, description,
            listing_id, type_id, opportunity_id,
            performance_start, performance_end,
            obligated, outlayed, non_federal,
            face_value, subsidy,
            listing_code, type_code,
        ) = row

        award_keys.add(key)

        identity = (batch_id, source_row)

        if identity in source_identities:
            flag("duplicate_source_identity", key)

        source_identities.add(identity)

        if listing_id is None:
            flag("unresolved_listing", key)

        if type_id is None:
            flag("unresolved_type", key)

        if listing_code is None:
            flag("missing_listing_code", key)

        if type_code is None:
            flag("missing_type_code", key)

        if listing_id is None or type_id is None:
            continue

        if action_text and parse_date(action_text) is None:
            flag("invalid_action_date", key)

        try:
            amounts = [
                parse_decimal(value)
                for value in (
                    obligated,
                    outlayed,
                    non_federal,
                    face_value,
                    subsidy,
                )
            ]
        except (ValueError, InvalidOperation):
            flag("invalid_monetary_value", key)
            continue

        # The original loader uses source_row_number to
        # break ties. Here we assign a cross-batch ordinal
        # that preserves batch ID and source row ordering.
        #
        # The source rows remain identifiable by their
        # original (batch_id, source_row_number) pair.
        tie_break_ordinal = (
            int(batch_id) * 1000000000
            + int(source_row)
        )

        observations.append(
            AwardObservation(
                assistance_award_unique_key=key,
                source_row_number=tie_break_ordinal,
                action_date=parse_date(action_text),
                award_id_fain=fain.strip() or None
                    if fain else None,
                award_id_uri=uri.strip() or None
                    if uri else None,
                sai_number=sai.strip() or None
                    if sai else None,
                recipient_name=recipient.strip() or None
                    if recipient else None,
                award_description=description.strip() or None
                    if description else None,
                assistance_listing_id=int(listing_id),
                assistance_type_id=int(type_id),
                funding_opportunity_id=(
                    int(opportunity_id)
                    if opportunity_id is not None
                    else None
                ),
                performance_start_date=parse_date(
                    performance_start
                ),
                performance_end_date=parse_date(
                    performance_end
                ),
                total_obligated_amount=amounts[0],
                total_outlayed_amount=amounts[1],
                total_non_federal_funding_amount=amounts[2],
                total_face_value_of_loan=amounts[3],
                total_loan_subsidy_cost=amounts[4],
            )
        )

    awards = build_canonical_awards(observations)

    for award in awards:
        key = award.assistance_award_unique_key

        if (
            award.award_id_fain is None
            and award.award_id_uri is None
        ):
            flag("canonical_missing_identifier", key)

        if (
            award.first_action_date is not None
            and award.last_action_date is not None
            and award.first_action_date
                > award.last_action_date
        ):
            flag("invalid_canonical_date_range", key)

    return award_keys, awards, errors, samples


def main():
    print("=" * 72)
    print("ETL-201H v0.2 — HISTORICAL AWARD CERTIFICATION")
    print("FY2018 batch 20 / FY2019 batch 21")
    print("READ ONLY — NO DATABASE WRITES")
    print("=" * 72)

    conn = get_connection()

    try:
        conn.set_session(
            readonly=True,
            autocommit=False,
        )

        with conn.cursor() as cur:
            cur.execute(
                "SET LOCAL statement_timeout = '300s'"
            )

            counts = get_cohort_counts(cur)

            print("\nHISTORICAL COHORT RECONCILIATION")
            print("-" * 72)

            labels = (
                "Historical distinct awards",
                "Existing canonical awards",
                "Missing canonical awards",
                "Conflicted missing awards",
                "Candidate awards",
            )

            expected = (
                EXPECTED_HISTORICAL,
                EXPECTED_EXISTING,
                EXPECTED_MISSING,
                EXPECTED_CONFLICTED_MISSING,
                EXPECTED_CANDIDATES,
            )

            for label, actual, target in zip(
                labels, counts, expected
            ):
                status = (
                    "PASS" if actual == target else "FAIL"
                )
                print(
                    f"{label:<34} "
                    f"{actual:>10,} "
                    f"expected={target:>10,} {status}"
                )

            if counts != expected:
                raise RuntimeError(
                    "Historical cohort reconciliation failed."
                )

            rows = extract_candidates(cur)

        print("\nCANDIDATE SOURCE VALIDATION")
        print("-" * 72)
        print(f"Extracted source rows: {len(rows):,}")

        keys, awards, errors, samples = certify_rows(rows)

        print(f"Distinct source awards: {len(keys):,}")
        print(f"Canonical candidates built: {len(awards):,}")

        if len(keys) != EXPECTED_CANDIDATES:
            errors["candidate_source_count_mismatch"] += 1

        if len(awards) != EXPECTED_CANDIDATES:
            errors["canonical_candidate_count_mismatch"] += 1

        print("\nVALIDATION EXCEPTIONS")
        print("-" * 72)

        if errors:
            for name, count in sorted(errors.items()):
                print(f"{name:<40} {count:>10,}")

                for key in samples[name]:
                    print(f"    Example: {key}")
        else:
            print("No validation exceptions detected.")

        print("\nFINAL CERTIFICATION")
        print("-" * 72)

        if errors:
            print("FAIL — CANDIDATES NOT CERTIFIED")
        else:
            print("PASS — CANDIDATES CERTIFIED FOR")
            print("FURTHER PRE-INSERTION REVIEW")

        print("\nNo database changes were made.")

        conn.rollback()

        if errors:
            raise SystemExit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
