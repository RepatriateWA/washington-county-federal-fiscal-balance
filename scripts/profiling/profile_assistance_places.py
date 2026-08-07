"""Profile Assistance place-of-performance fields and identity behavior."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from etl.common.db import get_connection


@dataclass(frozen=True)
class PlaceField:
    """One raw place-of-performance field to profile."""

    label: str
    field_name: str


PLACE_FIELDS = (
    PlaceField(
        label="Country code",
        field_name=(
            "primary_place_of_performance_country_code"
        ),
    ),
    PlaceField(
        label="State code",
        field_name=(
            "primary_place_of_performance_state_code"
        ),
    ),
    PlaceField(
        label="County name",
        field_name=(
            "primary_place_of_performance_county_name"
        ),
    ),
    PlaceField(
        label="County FIPS",
        field_name=(
            "primary_place_of_performance_county_fips"
        ),
    ),
    PlaceField(
        label="City name",
        field_name=(
            "primary_place_of_performance_city_name"
        ),
    ),
    PlaceField(
        label="ZIP+4",
        field_name=(
            "primary_place_of_performance_zip_4"
        ),
    ),
    PlaceField(
        label="Current congressional district",
        field_name=(
            "primary_place_of_performance_congressional_district_current"
        ),
    ),
    PlaceField(
        label="Original congressional district",
        field_name=(
            "primary_place_of_performance_congressional_district_original"
        ),
    ),
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Profile Assistance place-of-performance fields "
            "for one raw load batch."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()


def print_field_coverage(
    cur,
    *,
    load_batch_id: int,
    field: PlaceField,
) -> None:
    """Print populated, missing, and distinct counts."""

    cur.execute(
        """
        SELECT
            COUNT(*) AS total_rows,

            COUNT(
                NULLIF(
                    BTRIM(raw_record ->> %s),
                    ''
                )
            ) AS populated_rows,

            COUNT(
                DISTINCT NULLIF(
                    BTRIM(raw_record ->> %s),
                    ''
                )
            ) AS distinct_values

        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s;
        """,
        (
            field.field_name,
            field.field_name,
            load_batch_id,
        ),
    )

    total_rows, populated_rows, distinct_values = (
        cur.fetchone()
    )

    print(
        f"{field.label:<34} "
        f"populated={populated_rows:>8,}  "
        f"missing={total_rows - populated_rows:>8,}  "
        f"distinct={distinct_values:>8,}"
    )


def print_top_place_combinations(
    cur,
    *,
    load_batch_id: int,
) -> None:
    """Print the most common observed place combinations."""

    print("=" * 104)
    print("TOP PLACE-OF-PERFORMANCE COMBINATIONS")
    print("=" * 104)

    cur.execute(
        """
        SELECT
            NULLIF(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_country_code'
                ),
                ''
            ) AS country_code,

            NULLIF(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_state_code'
                ),
                ''
            ) AS state_code,

            NULLIF(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_name'
                ),
                ''
            ) AS county_name,

            NULLIF(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_fips'
                ),
                ''
            ) AS county_fips,

            NULLIF(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_city_name'
                ),
                ''
            ) AS city_name,

            NULLIF(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_zip_4'
                ),
                ''
            ) AS zip_4,

            COUNT(*) AS row_count,

            COUNT(
                DISTINCT assistance_award_unique_key
            ) AS award_count

        FROM assistance.raw_award_transaction

        WHERE load_batch_id = %s

        GROUP BY
            country_code,
            state_code,
            county_name,
            county_fips,
            city_name,
            zip_4

        ORDER BY
            row_count DESC,
            country_code,
            state_code,
            county_fips,
            city_name

        LIMIT 75;
        """,
        (load_batch_id,),
    )

    for row in cur.fetchall():
        print(row)

    print()


def print_county_consistency(
    cur,
    *,
    load_batch_id: int,
) -> None:
    """Profile county FIPS/name/state consistency."""

    print("=" * 104)
    print("COUNTY IDENTITY CONSISTENCY")
    print("=" * 104)

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_fips'
                ) AS county_fips

            FROM assistance.raw_award_transaction

            WHERE load_batch_id = %s

              AND NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_county_fips'
                    ),
                    ''
                  ) IS NOT NULL

              AND NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_county_name'
                    ),
                    ''
                  ) IS NOT NULL

            GROUP BY
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_fips'
                )

            HAVING COUNT(
                DISTINCT BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_name'
                )
            ) > 1
        ) AS conflicts;
        """,
        (load_batch_id,),
    )

    fips_to_name_conflicts = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_name'
                ) AS county_name

            FROM assistance.raw_award_transaction

            WHERE load_batch_id = %s

              AND NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_county_fips'
                    ),
                    ''
                  ) IS NOT NULL

              AND NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_county_name'
                    ),
                    ''
                  ) IS NOT NULL

            GROUP BY
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_name'
                )

            HAVING COUNT(
                DISTINCT BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_fips'
                )
            ) > 1
        ) AS conflicts;
        """,
        (load_batch_id,),
    )

    name_to_fips_conflicts = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
          AND NULLIF(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_fips'
                ),
                ''
              ) IS NOT NULL
          AND NULLIF(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_state_code'
                ),
                ''
              ) IS NOT NULL
          AND LEFT(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_fips'
                ),
                2
              ) <> '53'
          AND BTRIM(
                raw_record
                ->> 'primary_place_of_performance_state_code'
              ) = 'WA';
        """,
        (load_batch_id,),
    )

    wa_state_non_wa_fips_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
          AND NULLIF(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_fips'
                ),
                ''
              ) IS NOT NULL
          AND NULLIF(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_state_code'
                ),
                ''
              ) IS NOT NULL
          AND LEFT(
                BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_county_fips'
                ),
                2
              ) = '53'
          AND BTRIM(
                raw_record
                ->> 'primary_place_of_performance_state_code'
              ) <> 'WA';
        """,
        (load_batch_id,),
    )

    wa_fips_non_wa_state_count = int(
        cur.fetchone()[0]
    )

    print(
        "County FIPS with multiple names .... "
        f"{fips_to_name_conflicts:,}"
    )
    print(
        "County names with multiple FIPS .... "
        f"{name_to_fips_conflicts:,}"
    )
    print(
        "WA state with non-WA county FIPS ... "
        f"{wa_state_non_wa_fips_count:,}"
    )
    print(
        "WA county FIPS with non-WA state ... "
        f"{wa_fips_non_wa_state_count:,}"
    )
    print()


def print_special_geography_inventory(
    cur,
    *,
    load_batch_id: int,
) -> None:
    """Inventory statewide, foreign, unknown, and unusual values."""

    print("=" * 104)
    print("SPECIAL OR INCOMPLETE GEOGRAPHY INVENTORY")
    print("=" * 104)

    cur.execute(
        """
        SELECT
            COALESCE(
                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_country_code'
                    ),
                    ''
                ),
                '(missing)'
            ) AS country_code,

            COALESCE(
                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_state_code'
                    ),
                    ''
                ),
                '(missing)'
            ) AS state_code,

            COALESCE(
                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_county_name'
                    ),
                    ''
                ),
                '(missing)'
            ) AS county_name,

            COALESCE(
                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_county_fips'
                    ),
                    ''
                ),
                '(missing)'
            ) AS county_fips,

            COUNT(*) AS row_count,

            COUNT(
                DISTINCT assistance_award_unique_key
            ) AS award_count

        FROM assistance.raw_award_transaction

        WHERE load_batch_id = %s

          AND (
                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_country_code'
                    ),
                    ''
                ) IS NULL

             OR BTRIM(
                    raw_record
                    ->> 'primary_place_of_performance_country_code'
                ) <> 'USA'

             OR NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_state_code'
                    ),
                    ''
                ) IS NULL

             OR NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_county_fips'
                    ),
                    ''
                ) IS NULL

             OR UPPER(
                    COALESCE(
                        raw_record
                        ->> 'primary_place_of_performance_county_name',
                        ''
                    )
                ) LIKE ANY (
                    ARRAY[
                        '%%STATEWIDE%%',
                        '%%MULTIPLE%%',
                        '%%UNKNOWN%%',
                        '%%UNDEFINED%%',
                        '%%OTHER%%'
                    ]
                )
          )

        GROUP BY
            country_code,
            state_code,
            county_name,
            county_fips

        ORDER BY
            row_count DESC,
            country_code,
            state_code,
            county_name

        LIMIT 100;
        """,
        (load_batch_id,),
    )

    rows = cur.fetchall()

    if not rows:
        print("(none)")
    else:
        for row in rows:
            print(row)

    print()


def print_existing_place_reuse(
    cur,
    *,
    load_batch_id: int,
) -> None:
    """Estimate exact reuse against procurement.place."""

    print("=" * 104)
    print("EXACT MATCHES TO EXISTING PROCUREMENT.PLACE")
    print("=" * 104)

    cur.execute(
        """
        WITH observed AS (
            SELECT DISTINCT
                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_country_code'
                    ),
                    ''
                ) AS country_code,

                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_state_code'
                    ),
                    ''
                ) AS state_code,

                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_county_name'
                    ),
                    ''
                ) AS county_name,

                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_county_fips'
                    ),
                    ''
                ) AS county_fips,

                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_city_name'
                    ),
                    ''
                ) AS city_name,

                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_zip_4'
                    ),
                    ''
                ) AS zip4,

                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_congressional_district_current'
                    ),
                    ''
                ) AS district_current,

                NULLIF(
                    BTRIM(
                        raw_record
                        ->> 'primary_place_of_performance_congressional_district_original'
                    ),
                    ''
                ) AS district_original

            FROM assistance.raw_award_transaction
            WHERE load_batch_id = %s
        )
        SELECT
            COUNT(*) AS distinct_observed_places,

            COUNT(place.place_id)
                AS exact_existing_matches,

            COUNT(*) - COUNT(place.place_id)
                AS unmatched_places

        FROM observed

        LEFT JOIN procurement.place AS place
          ON place.country_code
                IS NOT DISTINCT FROM observed.country_code
         AND place.state_code
                IS NOT DISTINCT FROM observed.state_code
         AND place.county_name
                IS NOT DISTINCT FROM observed.county_name
         AND place.county_fips
                IS NOT DISTINCT FROM observed.county_fips
         AND place.city_name
                IS NOT DISTINCT FROM observed.city_name
         AND place.zip4
                IS NOT DISTINCT FROM observed.zip4
         AND place.congressional_district_current
                IS NOT DISTINCT FROM observed.district_current
         AND place.congressional_district_original
                IS NOT DISTINCT FROM observed.district_original;
        """,
        (load_batch_id,),
    )

    (
        distinct_observed_places,
        exact_existing_matches,
        unmatched_places,
    ) = [
        int(value)
        for value in cur.fetchone()
    ]

    print(
        "Distinct observed places ......... "
        f"{distinct_observed_places:,}"
    )
    print(
        "Exact existing matches ........... "
        f"{exact_existing_matches:,}"
    )
    print(
        "Unmatched places ................. "
        f"{unmatched_places:,}"
    )
    print()


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    print("=" * 104)
    print(
        "ETL-005D.5A — ASSISTANCE PLACE-OF-PERFORMANCE PROFILE"
    )
    print("=" * 104)
    print(f"Load batch ID: {args.load_batch_id}")
    print()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM assistance.raw_award_transaction
                WHERE load_batch_id = %s;
                """,
                (args.load_batch_id,),
            )

            raw_row_count = int(
                cur.fetchone()[0]
            )

            if raw_row_count == 0:
                raise ValueError(
                    f"No raw Assistance rows found for load batch "
                    f"{args.load_batch_id}."
                )

            print(
                f"Rows examined: {raw_row_count:,}"
            )
            print()

            print("=" * 104)
            print("FIELD COVERAGE")
            print("=" * 104)

            for field in PLACE_FIELDS:
                print_field_coverage(
                    cur,
                    load_batch_id=args.load_batch_id,
                    field=field,
                )

            print()

            print_top_place_combinations(
                cur,
                load_batch_id=args.load_batch_id,
            )

            print_county_consistency(
                cur,
                load_batch_id=args.load_batch_id,
            )

            print_special_geography_inventory(
                cur,
                load_batch_id=args.load_batch_id,
            )

            print_existing_place_reuse(
                cur,
                load_batch_id=args.load_batch_id,
            )

        print("=" * 104)
        print("PROFILE COMPLETE")
        print("=" * 104)
        print(
            "This profile records place-of-performance behavior. "
            "It does not yet normalize or link places."
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()