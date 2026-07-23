"""
Validate the procurement geography subsystem.

Checks the integrity of:

    procurement.award_transaction
        -> procurement.place_of_performance
        -> procurement.place

It also reconciles the retained geographic snapshot columns in
procurement.place_of_performance against the canonical place dimension.

Usage:
    python -m scripts.validate_procurement_geography

Optional explicit batch:
    python -m scripts.validate_procurement_geography --load-batch-id 2
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from etl.common.db import get_connection


@dataclass(frozen=True)
class ValidationResult:
    name: str
    actual: int
    expected: int
    passed: bool


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate procurement transaction geography."
    )
    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=None,
        help=(
            "Restrict transaction-level checks to one load batch. "
            "Defaults to all normalized procurement transactions."
        ),
    )
    return parser.parse_args()


def scalar(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    return int(cur.fetchone()[0])


def build_batch_filter(
    alias: str,
    load_batch_id: int | None,
) -> tuple[str, tuple]:
    if load_batch_id is None:
        return "", ()
    return f"WHERE {alias}.load_batch_id = %s", (load_batch_id,)


def run_validation(
    conn,
    load_batch_id: int | None,
) -> tuple[list[ValidationResult], dict[str, int]]:
    results: list[ValidationResult] = []
    metrics: dict[str, int] = {}

    at_filter, at_params = build_batch_filter("at", load_batch_id)

    with conn.cursor() as cur:
        transaction_count = scalar(
            cur,
            f"""
            SELECT COUNT(*)
            FROM procurement.award_transaction AS at
            {at_filter};
            """,
            at_params,
        )
        metrics["transactions"] = transaction_count

        if transaction_count == 0:
            scope = (
                "the selected batch"
                if load_batch_id is not None
                else "procurement.award_transaction"
            )
            raise ValueError(f"No normalized transactions found in {scope}.")

        linked_count = scalar(
            cur,
            f"""
            SELECT COUNT(*)
            FROM procurement.award_transaction AS at
            JOIN procurement.place_of_performance AS pop
              ON pop.award_transaction_id = at.award_transaction_id
            {at_filter};
            """,
            at_params,
        )
        metrics["linked_transactions"] = linked_count
        results.append(
            ValidationResult(
                "Every transaction has one place relationship",
                linked_count,
                transaction_count,
                linked_count == transaction_count,
            )
        )

        if load_batch_id is None:
            duplicate_relationships = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM (
                    SELECT award_transaction_id
                    FROM procurement.place_of_performance
                    GROUP BY award_transaction_id
                    HAVING COUNT(*) > 1
                ) AS duplicate_rows;
                """,
            )
        else:
            duplicate_relationships = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM (
                    SELECT pop.award_transaction_id
                    FROM procurement.place_of_performance AS pop
                    JOIN procurement.award_transaction AS at
                      ON at.award_transaction_id =
                         pop.award_transaction_id
                    WHERE at.load_batch_id = %s
                    GROUP BY pop.award_transaction_id
                    HAVING COUNT(*) > 1
                ) AS duplicate_rows;
                """,
                (load_batch_id,),
            )
        results.append(
            ValidationResult(
                "Duplicate transaction relationships",
                duplicate_relationships,
                0,
                duplicate_relationships == 0,
            )
        )

        orphan_transactions = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.place_of_performance AS pop
            LEFT JOIN procurement.award_transaction AS at
              ON at.award_transaction_id = pop.award_transaction_id
            WHERE at.award_transaction_id IS NULL;
            """,
        )
        results.append(
            ValidationResult(
                "Orphaned award-transaction references",
                orphan_transactions,
                0,
                orphan_transactions == 0,
            )
        )

        orphan_places = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.place_of_performance AS pop
            LEFT JOIN procurement.place AS p
              ON p.place_id = pop.place_id
            WHERE pop.place_id IS NOT NULL
              AND p.place_id IS NULL;
            """,
        )
        results.append(
            ValidationResult(
                "Orphaned canonical-place references",
                orphan_places,
                0,
                orphan_places == 0,
            )
        )

        if load_batch_id is None:
            unresolved_places = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM procurement.place_of_performance
                WHERE place_id IS NULL
                   OR location_scope = 'UNRESOLVED';
                """,
            )
        else:
            unresolved_places = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM procurement.place_of_performance AS pop
                JOIN procurement.award_transaction AS at
                  ON at.award_transaction_id =
                     pop.award_transaction_id
                WHERE at.load_batch_id = %s
                  AND (
                      pop.place_id IS NULL
                      OR pop.location_scope = 'UNRESOLVED'
                  );
                """,
                (load_batch_id,),
            )
        metrics["unresolved_places"] = unresolved_places
        results.append(
            ValidationResult(
                "Unresolved transaction places",
                unresolved_places,
                0,
                unresolved_places == 0,
            )
        )

        if load_batch_id is None:
            invalid_scope = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM procurement.place_of_performance
                WHERE location_scope NOT IN (
                    'OBSERVED',
                    'DERIVED_FROM_FIPS',
                    'DERIVED_FROM_ZIP',
                    'ALLOCATED',
                    'UNRESOLVED'
                );
                """,
            )
        else:
            invalid_scope = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM procurement.place_of_performance AS pop
                JOIN procurement.award_transaction AS at
                  ON at.award_transaction_id =
                     pop.award_transaction_id
                WHERE at.load_batch_id = %s
                  AND pop.location_scope NOT IN (
                      'OBSERVED',
                      'DERIVED_FROM_FIPS',
                      'DERIVED_FROM_ZIP',
                      'ALLOCATED',
                      'UNRESOLVED'
                  );
                """,
                (load_batch_id,),
            )
        results.append(
            ValidationResult(
                "Invalid location-scope values",
                invalid_scope,
                0,
                invalid_scope == 0,
            )
        )

        duplicate_place_identities = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    country_code,
                    state_fips,
                    county_fips,
                    city_name,
                    zip4
                FROM procurement.place
                GROUP BY
                    country_code,
                    state_fips,
                    county_fips,
                    city_name,
                    zip4
                HAVING COUNT(*) > 1
            ) AS duplicate_places;
            """,
        )
        results.append(
            ValidationResult(
                "Duplicate canonical place identities",
                duplicate_place_identities,
                0,
                duplicate_place_identities == 0,
            )
        )

        empty_places = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.place
            WHERE country_code IS NULL
              AND state_fips IS NULL
              AND county_fips IS NULL
              AND city_name IS NULL
              AND zip4 IS NULL;
            """,
        )
        results.append(
            ValidationResult(
                "Completely empty canonical places",
                empty_places,
                0,
                empty_places == 0,
            )
        )

        inconsistent_fips = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.place
            WHERE state_fips IS NOT NULL
              AND county_fips IS NOT NULL
              AND LEFT(county_fips, 2) <> state_fips;
            """,
        )
        results.append(
            ValidationResult(
                "Inconsistent state/county FIPS",
                inconsistent_fips,
                0,
                inconsistent_fips == 0,
            )
        )

        if load_batch_id is None:
            snapshot_mismatches = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM procurement.place_of_performance AS pop
                JOIN procurement.place AS p
                  ON p.place_id = pop.place_id
                WHERE
                    pop.country_code
                        IS DISTINCT FROM p.country_code
                    OR pop.state_code
                        IS DISTINCT FROM p.state_code
                    OR pop.county_code
                        IS DISTINCT FROM p.county_fips
                    OR pop.city_name
                        IS DISTINCT FROM p.city_name
                    OR pop.congressional_district
                        IS DISTINCT FROM
                           p.congressional_district_current
                    OR pop.zip_code
                        IS DISTINCT FROM p.zip4;
                """,
            )
        else:
            snapshot_mismatches = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM procurement.place_of_performance AS pop
                JOIN procurement.award_transaction AS at
                  ON at.award_transaction_id =
                     pop.award_transaction_id
                JOIN procurement.place AS p
                  ON p.place_id = pop.place_id
                WHERE at.load_batch_id = %s
                  AND (
                      pop.country_code
                          IS DISTINCT FROM p.country_code
                      OR pop.state_code
                          IS DISTINCT FROM p.state_code
                      OR pop.county_code
                          IS DISTINCT FROM p.county_fips
                      OR pop.city_name
                          IS DISTINCT FROM p.city_name
                      OR pop.congressional_district
                          IS DISTINCT FROM
                             p.congressional_district_current
                      OR pop.zip_code
                          IS DISTINCT FROM p.zip4
                  );
                """,
                (load_batch_id,),
            )
        results.append(
            ValidationResult(
                "Snapshot/canonical geography mismatches",
                snapshot_mismatches,
                0,
                snapshot_mismatches == 0,
            )
        )

        if load_batch_id is None:
            state_reference_mismatches = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM procurement.place_of_performance AS pop
                JOIN procurement.place AS p
                  ON p.place_id = pop.place_id
                LEFT JOIN reference.state_registry AS sr
                  ON sr.state_id = pop.state_id
                WHERE pop.state_id IS NOT NULL
                  AND sr.state_fips
                      IS DISTINCT FROM p.state_fips;
                """,
            )
        else:
            state_reference_mismatches = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM procurement.place_of_performance AS pop
                JOIN procurement.award_transaction AS at
                  ON at.award_transaction_id =
                     pop.award_transaction_id
                JOIN procurement.place AS p
                  ON p.place_id = pop.place_id
                LEFT JOIN reference.state_registry AS sr
                  ON sr.state_id = pop.state_id
                WHERE at.load_batch_id = %s
                  AND pop.state_id IS NOT NULL
                  AND sr.state_fips
                      IS DISTINCT FROM p.state_fips;
                """,
                (load_batch_id,),
            )
        results.append(
            ValidationResult(
                "State-reference FIPS mismatches",
                state_reference_mismatches,
                0,
                state_reference_mismatches == 0,
            )
        )

        if load_batch_id is None:
            county_reference_mismatches = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM procurement.place_of_performance AS pop
                JOIN procurement.place AS p
                  ON p.place_id = pop.place_id
                LEFT JOIN reference.county_registry AS cr
                  ON cr.county_id = pop.county_id
                WHERE pop.county_id IS NOT NULL
                  AND cr.full_fips
                      IS DISTINCT FROM p.county_fips;
                """,
            )
        else:
            county_reference_mismatches = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM procurement.place_of_performance AS pop
                JOIN procurement.award_transaction AS at
                  ON at.award_transaction_id =
                     pop.award_transaction_id
                JOIN procurement.place AS p
                  ON p.place_id = pop.place_id
                LEFT JOIN reference.county_registry AS cr
                  ON cr.county_id = pop.county_id
                WHERE at.load_batch_id = %s
                  AND pop.county_id IS NOT NULL
                  AND cr.full_fips
                      IS DISTINCT FROM p.county_fips;
                """,
                (load_batch_id,),
            )
        results.append(
            ValidationResult(
                "County-reference FIPS mismatches",
                county_reference_mismatches,
                0,
                county_reference_mismatches == 0,
            )
        )

        canonical_place_count = scalar(
            cur,
            "SELECT COUNT(*) FROM procurement.place;",
        )
        metrics["canonical_places"] = canonical_place_count

        relationship_count = scalar(
            cur,
            "SELECT COUNT(*) FROM procurement.place_of_performance;",
        )
        metrics["all_relationships"] = relationship_count

        observed_count = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.place_of_performance
            WHERE location_scope = 'OBSERVED';
            """,
        )
        metrics["observed_relationships"] = observed_count

        washington_relationships = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.place_of_performance AS pop
            JOIN procurement.place AS p
              ON p.place_id = pop.place_id
            WHERE p.state_fips = '53';
            """,
        )
        metrics["washington_relationships"] = washington_relationships

        washington_counties = scalar(
            cur,
            """
            SELECT COUNT(DISTINCT p.county_fips)
            FROM procurement.place_of_performance AS pop
            JOIN procurement.place AS p
              ON p.place_id = pop.place_id
            WHERE p.state_fips = '53'
              AND p.county_fips IS NOT NULL;
            """,
        )
        metrics["washington_counties"] = washington_counties

    return results, metrics


def print_report(
    results: list[ValidationResult],
    metrics: dict[str, int],
    load_batch_id: int | None,
) -> None:
    print("=" * 76)
    print("PROCUREMENT GEOGRAPHY VALIDATION")
    print("=" * 76)
    print(
        "Scope:",
        (
            f"load batch {load_batch_id}"
            if load_batch_id is not None
            else "all normalized procurement transactions"
        ),
    )
    print()
    print(f"Transactions in scope .............. {metrics['transactions']:,}")
    print(f"Linked transactions ................ {metrics['linked_transactions']:,}")
    print(f"Canonical places ................... {metrics['canonical_places']:,}")
    print(f"All place relationships ............ {metrics['all_relationships']:,}")
    print(f"Observed relationships ............. {metrics['observed_relationships']:,}")
    print(f"Washington relationships ........... {metrics['washington_relationships']:,}")
    print(f"Washington counties represented .... {metrics['washington_counties']:,}")
    print()
    print("-" * 76)

    failures = 0
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        if not result.passed:
            failures += 1
        print(
            f"{status:4}  {result.name:<48} "
            f"actual={result.actual:,} expected={result.expected:,}"
        )

    print("-" * 76)
    if failures:
        print(f"OVERALL RESULT: FAIL ({failures} validation check(s) failed)")
    else:
        print("OVERALL RESULT: PASS")
    print("=" * 76)

    if failures:
        raise SystemExit(1)


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    try:
        results, metrics = run_validation(
            conn,
            args.load_batch_id,
        )
        print_report(
            results,
            metrics,
            args.load_batch_id,
        )
    except Exception as exc:
        print()
        print("Procurement geography validation failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    finally:
        conn.close()


if __name__ == "__main__":
    main()