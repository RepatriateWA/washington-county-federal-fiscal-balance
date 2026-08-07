"""Profile Assistance awarding and funding agency identities."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from etl.common.db import get_connection


@dataclass(frozen=True)
class AgencyFieldPair:
    """One code-name agency field pair."""

    label: str
    code_field: str
    name_field: str


AGENCY_PAIRS = (
    AgencyFieldPair(
        label="Awarding agency",
        code_field="awarding_agency_code",
        name_field="awarding_agency_name",
    ),
    AgencyFieldPair(
        label="Awarding subagency",
        code_field="awarding_sub_agency_code",
        name_field="awarding_sub_agency_name",
    ),
    AgencyFieldPair(
        label="Funding agency",
        code_field="funding_agency_code",
        name_field="funding_agency_name",
    ),
    AgencyFieldPair(
        label="Funding subagency",
        code_field="funding_sub_agency_code",
        name_field="funding_sub_agency_name",
    ),
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Profile Assistance awarding and funding agency "
            "identity fields for one raw load batch."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()


def print_coverage(
    cur,
    *,
    load_batch_id: int,
    pair: AgencyFieldPair,
) -> None:
    """Print coverage for one code-name pair."""

    cur.execute(
        """
        SELECT
            COUNT(*) AS total_rows,

            COUNT(
                NULLIF(
                    BTRIM(raw_record ->> %s),
                    ''
                )
            ) AS code_populated,

            COUNT(
                DISTINCT NULLIF(
                    BTRIM(raw_record ->> %s),
                    ''
                )
            ) AS distinct_codes,

            COUNT(
                NULLIF(
                    BTRIM(raw_record ->> %s),
                    ''
                )
            ) AS name_populated,

            COUNT(
                DISTINCT NULLIF(
                    BTRIM(raw_record ->> %s),
                    ''
                )
            ) AS distinct_names

        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s;
        """,
        (
            pair.code_field,
            pair.code_field,
            pair.name_field,
            pair.name_field,
            load_batch_id,
        ),
    )

    (
        total_rows,
        code_populated,
        distinct_codes,
        name_populated,
        distinct_names,
    ) = cur.fetchone()

    print(pair.label)
    print("-" * 88)
    print(
        f"Code populated={code_populated:>8,}  "
        f"missing={total_rows - code_populated:>8,}  "
        f"distinct={distinct_codes:>6,}"
    )
    print(
        f"Name populated={name_populated:>8,}  "
        f"missing={total_rows - name_populated:>8,}  "
        f"distinct={distinct_names:>6,}"
    )
    print()


def print_multiplicity(
    cur,
    *,
    load_batch_id: int,
    pair: AgencyFieldPair,
) -> None:
    """Print code-to-name and name-to-code multiplicity."""

    print(pair.label.upper())
    print("-" * 88)

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                BTRIM(raw_record ->> %s) AS agency_code
            FROM assistance.raw_award_transaction
            WHERE load_batch_id = %s
              AND NULLIF(
                    BTRIM(raw_record ->> %s),
                    ''
                  ) IS NOT NULL
              AND NULLIF(
                    BTRIM(raw_record ->> %s),
                    ''
                  ) IS NOT NULL
            GROUP BY
                BTRIM(raw_record ->> %s)
            HAVING COUNT(
                DISTINCT BTRIM(
                    raw_record ->> %s
                )
            ) > 1
        ) AS conflicts;
        """,
        (
            pair.code_field,
            load_batch_id,
            pair.code_field,
            pair.name_field,
            pair.code_field,
            pair.name_field,
        ),
    )

    code_to_name_conflicts = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                BTRIM(raw_record ->> %s) AS agency_name
            FROM assistance.raw_award_transaction
            WHERE load_batch_id = %s
              AND NULLIF(
                    BTRIM(raw_record ->> %s),
                    ''
                  ) IS NOT NULL
              AND NULLIF(
                    BTRIM(raw_record ->> %s),
                    ''
                  ) IS NOT NULL
            GROUP BY
                BTRIM(raw_record ->> %s)
            HAVING COUNT(
                DISTINCT BTRIM(
                    raw_record ->> %s
                )
            ) > 1
        ) AS conflicts;
        """,
        (
            pair.name_field,
            load_batch_id,
            pair.name_field,
            pair.code_field,
            pair.name_field,
            pair.code_field,
        ),
    )

    name_to_code_conflicts = int(
        cur.fetchone()[0]
    )

    print(
        "Codes with multiple names ........ "
        f"{code_to_name_conflicts:,}"
    )
    print(
        "Names with multiple codes ........ "
        f"{name_to_code_conflicts:,}"
    )
    print()

    print("TOP CODE-NAME PAIRS")
    print("-" * 88)

    cur.execute(
        """
        SELECT
            NULLIF(
                BTRIM(raw_record ->> %s),
                ''
            ) AS agency_code,

            NULLIF(
                BTRIM(raw_record ->> %s),
                ''
            ) AS agency_name,

            COUNT(*) AS row_count,
            COUNT(
                DISTINCT assistance_award_unique_key
            ) AS award_count

        FROM assistance.raw_award_transaction

        WHERE load_batch_id = %s

        GROUP BY
            NULLIF(
                BTRIM(raw_record ->> %s),
                ''
            ),
            NULLIF(
                BTRIM(raw_record ->> %s),
                ''
            )

        ORDER BY
            row_count DESC,
            agency_code,
            agency_name

        LIMIT 25;
        """,
        (
            pair.code_field,
            pair.name_field,
            load_batch_id,
            pair.code_field,
            pair.name_field,
        ),
    )

    for row in cur.fetchall():
        print(row)

    print()


def print_conflict_examples(
    cur,
    *,
    load_batch_id: int,
    pair: AgencyFieldPair,
) -> None:
    """Print examples of code-to-name conflicts."""

    print(
        f"{pair.label.upper()} — CODE TO NAME CONFLICTS"
    )
    print("-" * 88)

    cur.execute(
        """
        SELECT
            BTRIM(raw_record ->> %s) AS agency_code,
            COUNT(
                DISTINCT BTRIM(
                    raw_record ->> %s
                )
            ) AS distinct_names,
            COUNT(*) AS row_count,
            STRING_AGG(
                DISTINCT BTRIM(
                    raw_record ->> %s
                ),
                ' | '
                ORDER BY BTRIM(
                    raw_record ->> %s
                )
            ) AS observed_names

        FROM assistance.raw_award_transaction

        WHERE load_batch_id = %s
          AND NULLIF(
                BTRIM(raw_record ->> %s),
                ''
              ) IS NOT NULL
          AND NULLIF(
                BTRIM(raw_record ->> %s),
                ''
              ) IS NOT NULL

        GROUP BY
            BTRIM(raw_record ->> %s)

        HAVING COUNT(
            DISTINCT BTRIM(
                raw_record ->> %s
            )
        ) > 1

        ORDER BY
            distinct_names DESC,
            row_count DESC,
            agency_code

        LIMIT 25;
        """,
        (
            pair.code_field,
            pair.name_field,
            pair.name_field,
            pair.name_field,
            load_batch_id,
            pair.code_field,
            pair.name_field,
            pair.code_field,
            pair.name_field,
        ),
    )

    rows = cur.fetchall()

    if not rows:
        print("(none)")
    else:
        for row in rows:
            print(row)

    print()


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    print("=" * 88)
    print(
        "ETL-005D.4A — ASSISTANCE AGENCY IDENTITY PROFILE"
    )
    print("=" * 88)
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
                    f"No raw Assistance rows found for "
                    f"load batch {args.load_batch_id}."
                )

            print(
                f"Rows examined: {raw_row_count:,}"
            )
            print()

            print("=" * 88)
            print("FIELD COVERAGE")
            print("=" * 88)
            print()

            for pair in AGENCY_PAIRS:
                print_coverage(
                    cur,
                    load_batch_id=(
                        args.load_batch_id
                    ),
                    pair=pair,
                )

            print("=" * 88)
            print("IDENTITY MULTIPLICITY")
            print("=" * 88)
            print()

            for pair in AGENCY_PAIRS:
                print_multiplicity(
                    cur,
                    load_batch_id=(
                        args.load_batch_id
                    ),
                    pair=pair,
                )

            print("=" * 88)
            print("CONFLICT EXAMPLES")
            print("=" * 88)
            print()

            for pair in AGENCY_PAIRS:
                print_conflict_examples(
                    cur,
                    load_batch_id=(
                        args.load_batch_id
                    ),
                    pair=pair,
                )

        print("=" * 88)
        print("PROFILE COMPLETE")
        print("=" * 88)
        print(
            "This profile records source identity behavior. "
            "It does not yet normalize or link agencies."
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()