
"""ETL-201I v0.1 — Historical award pre-insertion audit.

FY2018 batch 20 / FY2019 batch 21.
READ ONLY. No database writes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from etl.common.db import get_connection
from etl.loaders.normalize_usaspending_assistance_awards import (
    parse_date,
    parse_decimal,
)
from etl.validation.assistance.certify_historical_award_candidates import (
    EXPECTED_CANDIDATES,
    EXPECTED_CONFLICTED_MISSING,
    EXPECTED_EXISTING,
    EXPECTED_HISTORICAL,
    EXPECTED_MISSING,
    certify_rows,
    extract_candidates,
    get_cohort_counts,
)


EXPECTED = (
    EXPECTED_HISTORICAL,
    EXPECTED_EXISTING,
    EXPECTED_MISSING,
    EXPECTED_CONFLICTED_MISSING,
    EXPECTED_CANDIDATES,
)

DATE_FIELDS = (
    "action_date",
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
)

MONEY_FIELDS = (
    "total_obligated_amount",
    "total_outlayed_amount_for_overall_award",
    "total_non_federal_funding_amount",
    "total_face_value_of_loan",
    "total_loan_subsidy_cost",
)


def report_issue(issues, samples, category, key):
    issues[category] += 1
    if len(samples[category]) < 5:
        samples[category].append(str(key))


def independent_source_profile(cur):
    """Count candidate keys and raw observations before joins."""

    cur.execute(
        """
        WITH historical AS MATERIALIZED (
            SELECT
                assistance_award_unique_key AS award_key,
                load_batch_id,
                source_row_number,
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
                COUNT(DISTINCT listing_code) AS listings,
                COUNT(DISTINCT type_code) AS types
            FROM historical
            GROUP BY award_key
        ),
        eligible AS MATERIALIZED (
            SELECT g.award_key
            FROM grouped AS g
            LEFT JOIN assistance.award AS a
              ON a.assistance_award_unique_key = g.award_key
            WHERE a.assistance_award_unique_key IS NULL
              AND g.listings <= 1
              AND g.types <= 1
        )
        SELECT
            COUNT(*) AS source_rows,
            COUNT(DISTINCT h.award_key) AS award_keys,
            COUNT(DISTINCT (
                h.load_batch_id,
                h.source_row_number
            )) AS source_identities
        FROM historical AS h
        JOIN eligible AS e
          ON e.award_key = h.award_key;
        """
    )

    return tuple(int(value) for value in cur.fetchone())


def reference_profile(cur):
    """Inspect source-code reference uniqueness."""

    references = (
        (
            "assistance_listing",
            "assistance.assistance_listing",
            "cfda_number",
        ),
        (
            "assistance_type",
            "assistance.assistance_type",
            "assistance_type_code",
        ),
        (
            "funding_opportunity",
            "assistance.funding_opportunity",
            "funding_opportunity_number",
        ),
    )

    results = {}

    for label, table, column in references:
        # Table and column identifiers are fixed source literals,
        # never supplied by users.
        cur.execute(
            f"""
            SELECT
                {column},
                COUNT(*) AS duplicate_count
            FROM {table}
            WHERE {column} IS NOT NULL
            GROUP BY {column}
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, {column}
            LIMIT 10;
            """
        )
        results[label] = cur.fetchall()

    return results


def source_quality_profile(cur):
    """Read source values independently of dimension joins."""

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
            LEFT JOIN assistance.award AS a
              ON a.assistance_award_unique_key = h.award_key
            WHERE a.assistance_award_unique_key IS NULL
            GROUP BY h.award_key
            HAVING COUNT(DISTINCT h.listing_code) <= 1
               AND COUNT(DISTINCT h.type_code) <= 1
        )
        SELECT
            raw.assistance_award_unique_key,
            raw.load_batch_id,
            raw.source_row_number,
            raw.raw_record ->> 'action_date',
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
            raw.raw_record ->> 'funding_opportunity_number'
        FROM assistance.raw_award_transaction AS raw
        JOIN eligible AS e
          ON e.award_key = raw.assistance_award_unique_key
        WHERE raw.load_batch_id IN (20, 21)
        ORDER BY
            raw.assistance_award_unique_key,
            raw.load_batch_id,
            raw.source_row_number;
        """
    )

    return cur.fetchall()


def audit_source_values(rows, issues, samples):
    """Identify malformed dates, amounts and source anomalies."""

    opportunity_codes = set()
    observed_awards = set()
    identities = set()

    for row in rows:
        key, batch_id, source_row = row[:3]
        dates = row[3:6]
        amounts = row[6:11]
        opportunity = row[11]

        observed_awards.add(key)

        identity = (batch_id, source_row)
        if identity in identities:
            report_issue(
                issues, samples,
                "duplicate_source_identity", key
            )
        identities.add(identity)

        for name, value in zip(DATE_FIELDS, dates):
            if value is None or not str(value).strip():
                continue

            # The existing loader parses only the first
            # 10 characters. Record unexpected suffixes
            # for manual review.
            cleaned = str(value).strip()

            if parse_date(cleaned) is None:
                report_issue(
                    issues, samples,
                    f"invalid_date:{name}", key
                )
            elif len(cleaned) != 10:
                report_issue(
                    issues, samples,
                    f"non_iso_date_shape:{name}", key
                )

        for name, value in zip(MONEY_FIELDS, amounts):
            if value is None or not str(value).strip():
                continue

            try:
                parsed = parse_decimal(value)
                if parsed is not None and not parsed.is_finite():
                    report_issue(
                        issues, samples,
                        f"nonfinite_amount:{name}", key
                    )
            except (ValueError, InvalidOperation):
                report_issue(
                    issues, samples,
                    f"invalid_amount:{name}", key
                )

        if opportunity is not None and str(opportunity).strip():
            opportunity_codes.add(str(opportunity).strip())

    return observed_awards, opportunity_codes


def check_opportunities(cur, codes, issues, samples):
    """Identify missing or ambiguous optional opportunity links."""

    if not codes:
        return

    cur.execute(
        """
        SELECT
            funding_opportunity_number,
            COUNT(*)
        FROM assistance.funding_opportunity
        WHERE funding_opportunity_number = ANY(%s)
        GROUP BY funding_opportunity_number;
        """,
        (sorted(codes),)
    )

    found = {
        str(code): int(count)
        for code, count in cur.fetchall()
    }

    for code in sorted(codes):
        count = found.get(code, 0)

        if count == 0:
            report_issue(
                issues, samples,
                "unresolved_funding_opportunity", code
            )
        elif count > 1:
            report_issue(
                issues, samples,
                "ambiguous_funding_opportunity", code
            )


def main():
    print("=" * 76)
    print("ETL-201I v0.1 — HISTORICAL AWARD PRE-INSERTION AUDIT")
    print("FY2018 batch 20 / FY2019 batch 21")
    print("READ ONLY — NO DATABASE WRITES")
    print("=" * 76)

    issues = Counter()
    samples = defaultdict(list)

    conn = get_connection()

    try:
        conn.set_session(readonly=True, autocommit=False)

        with conn.cursor() as cur:
            cur.execute(
                "SET LOCAL statement_timeout = '300s'"
            )

            counts = get_cohort_counts(cur)
            print("\nCOHORT RECONCILIATION")
            print("Actual:  ", counts)
            print("Expected:", EXPECTED)

            if counts != EXPECTED:
                report_issue(
                    issues, samples,
                    "cohort_reconciliation", counts
                )

            source_profile = independent_source_profile(cur)

            print("\nINDEPENDENT SOURCE COVERAGE")
            print("Source rows:       ", source_profile[0])
            print("Distinct awards:   ", source_profile[1])
            print("Source identities: ", source_profile[2])

            if source_profile[1] != EXPECTED_CANDIDATES:
                report_issue(
                    issues, samples,
                    "source_award_count", source_profile[1]
                )

            if source_profile[0] != source_profile[2]:
                report_issue(
                    issues, samples,
                    "source_identity_count", source_profile
                )

            refs = reference_profile(cur)

            print("\nREFERENCE UNIQUENESS")
            for name, duplicates in refs.items():
                print(
                    f"{name}: {len(duplicates)} "
                    "duplicate-key examples"
                )

                for item in duplicates:
                    print("   ", item)

                if duplicates:
                    report_issue(
                        issues, samples,
                        f"duplicate_reference:{name}",
                        duplicates[0]
                    )

            source_rows = source_quality_profile(cur)

            print("\nRAW SOURCE QUALITY")
            print("Rows independently extracted:",
                  len(source_rows))

            observed_awards, opportunity_codes = (
                audit_source_values(
                    source_rows, issues, samples
                )
            )

            print("Distinct awards independently extracted:",
                  len(observed_awards))

            if len(source_rows) != source_profile[0]:
                report_issue(
                    issues, samples,
                    "source_row_coverage",
                    (len(source_rows), source_profile[0])
                )

            if len(observed_awards) != EXPECTED_CANDIDATES:
                report_issue(
                    issues, samples,
                    "independent_award_coverage",
                    len(observed_awards)
                )

            check_opportunities(
                cur, opportunity_codes, issues, samples
            )

            # Reuse ETL-201H candidate extraction to
            # compare source coverage after dimension joins.
            joined_rows = extract_candidates(cur)

            print("\nDIMENSION-JOIN COVERAGE")
            print("Raw source rows:   ", len(source_rows))
            print("Joined source rows:", len(joined_rows))

            if len(joined_rows) != len(source_rows):
                report_issue(
                    issues, samples,
                    "dimension_join_row_count",
                    (len(source_rows), len(joined_rows))
                )

            joined_ids = [
                (row[1], row[2])
                for row in joined_rows
            ]
            raw_ids = [
                (row[1], row[2])
                for row in source_rows
            ]

            if Counter(joined_ids) != Counter(raw_ids):
                report_issue(
                    issues, samples,
                    "dimension_join_identity_mismatch",
                    "Raw/joined source identities differ"
                )

            keys, awards, prior_errors, prior_samples = (
                certify_rows(joined_rows)
            )

            for name, count in prior_errors.items():
                issues[f"ETL201H:{name}"] += count
                samples[f"ETL201H:{name}"].extend(
                    prior_samples[name][:5]
                )

            print("Canonical awards constructed:",
                  len(awards))

            if len(awards) != EXPECTED_CANDIDATES:
                report_issue(
                    issues, samples,
                    "canonical_award_count",
                    len(awards)
                )

            # A final protection check in the same
            # read-only transaction snapshot.
            cur.execute(
                """
                SELECT COUNT(*)
                FROM assistance.award
                WHERE assistance_award_unique_key = ANY(%s);
                """,
                (list(keys),)
            )

            existing_overlap = int(cur.fetchone()[0])

            print("\nEXISTING CANONICAL PROTECTION")
            print("Candidate keys already canonical:",
                  existing_overlap)

            if existing_overlap:
                report_issue(
                    issues, samples,
                    "existing_canonical_overlap",
                    existing_overlap
                )

        print("\nAUDIT EXCEPTIONS")
        print("-" * 76)

        if not issues:
            print("None detected.")
        else:
            for name, count in sorted(issues.items()):
                print(f"{name:<48} {count:>10,}")
                for sample in samples[name][:5]:
                    print("   Example:", sample)

        print("\nFINAL RESULT")
        print("-" * 76)

        if issues:
            print("FAIL — HOLD INSERTION PENDING REVIEW")
        else:
            print("PASS — PRE-INSERTION INTEGRITY AUDIT")
            print("Further insertion controls still required.")

        conn.rollback()
        print("Database changes: NONE")

        if issues:
            raise SystemExit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
