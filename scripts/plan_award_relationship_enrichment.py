"""
ETL-004B — Plan USAspending award relationship enrichment.

This script is read-only. It examines a procurement load batch, extracts
recipient and agency identifiers from the raw JSONB records, and determines
which normalized relationships can be resolved.

No database records are inserted or updated.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from etl.common.db import get_connection
from etl.common.validation import print_header

PLACEHOLDER_AGENCY_CODE = "999"

@dataclass(frozen=True)
class AwardRelationshipPlan:
    """
    Proposed normalized relationships for one procurement award.
    """

    award_id: int
    generated_unique_award_id: str

    recipient_uei: str | None
    recipient_id: int | None

    awarding_agency_code: str | None
    awarding_agency_id: int | None

    awarding_subagency_code: str | None
    awarding_subagency_id: int | None

    funding_agency_code: str | None
    funding_agency_id: int | None

    funding_subagency_code: str | None
    funding_subagency_id: int | None


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Plan normalized recipient and agency relationships for a "
            "USAspending procurement load batch."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=4,
        help="Procurement load batch to inspect. Defaults to Batch 4.",
    )

    return parser.parse_args()


def clean_text(value: Any) -> str | None:
    """
    Normalize a source value to stripped text or None.
    """
    if value is None:
        return None

    cleaned = str(value).strip()

    if not cleaned:
        return None

    return cleaned


def get_batch_award_sources(
    cur,
    *,
    load_batch_id: int,
) -> list[dict[str, Any]]:
    """
    Return distinct award relationship identifiers from raw JSONB records.

    Raw records are joined to normalized award transactions using both the
    load batch and original source-row number.
    """
    cur.execute(
        """
        SELECT 
            aw.award_id,
            aw.generated_unique_award_id,
            txn.action_date,
            txn.source_row_number,

            raw.raw_record ->> 'recipient_uei'
                AS recipient_uei,

            raw.raw_record ->> 'awarding_agency_code'
                AS awarding_agency_code,

            raw.raw_record ->> 'awarding_sub_agency_code'
                AS awarding_subagency_code,

            raw.raw_record ->> 'funding_agency_code'
                AS funding_agency_code,

            raw.raw_record ->> 'funding_sub_agency_code'
                AS funding_subagency_code

        FROM procurement.award_transaction AS txn

        JOIN procurement.award AS aw
          ON aw.award_id = txn.award_id

        JOIN procurement.raw_award_transaction AS raw
          ON raw.load_batch_id = txn.load_batch_id
         AND raw.source_row_number = txn.source_row_number

        WHERE txn.load_batch_id = %s

        ORDER BY
            aw.award_id,
            txn.action_date,
            txn.source_row_number;
        """,
        (load_batch_id,),
    )

    columns = [
        description[0]
        for description in cur.description
    ]

    return [
        dict(zip(columns, row))
        for row in cur.fetchall()
    ]

def collapse_identifier_values(
    *,
    award_id: int,
    field: str,
    values: set[str],
) -> str | None:
    """
    Collapse source identifiers to one authoritative value.

    Agency placeholder code 999 is ignored when a real agency code is
    available. Multiple distinct real identifiers remain an error.
    """
    if not values:
        return None

    candidate_values = set(values)

    if field in {
        "awarding_agency_code",
        "awarding_subagency_code",
        "funding_agency_code",
        "funding_subagency_code",
    }:
        real_values = {
            value
            for value in candidate_values
            if value != PLACEHOLDER_AGENCY_CODE
        }

        if real_values:
            candidate_values = real_values

    if len(candidate_values) > 1:
        raise ValueError(
            f"Award {award_id} has conflicting real values for "
            f"{field}: {sorted(candidate_values)}"
        )

    return next(iter(candidate_values))

def select_latest_value(
    rows: list[dict[str, Any]],
    *,
    field: str,
    ignored_values: set[str] | None = None,
) -> str | None:
    """
    Return the latest populated, non-ignored value for one source field.

    Rows are ranked by action date and source-row number. This defines
    award-level relationships as the latest known source relationship while
    preserving historical variation in transaction-level source data.
    """
    ignored = ignored_values or set()

    candidates: list[tuple[Any, int, str]] = []

    for row in rows:
        value = clean_text(row.get(field))

        if value is None or value in ignored:
            continue

        candidates.append(
            (
                row.get("action_date"),
                int(row.get("source_row_number") or 0),
                value,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item[0] is not None,
            item[0],
            item[1],
        )
    )

    return candidates[-1][2]

def collapse_award_sources(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Collapse transaction-level relationships to one award-level record.

    Award-level agency relationships represent the latest known populated
    source relationship. Placeholder agency code 999 and blank values are
    ignored when selecting the latest relationship.

    Recipient UEI must remain consistent because a recipient change would
    indicate a materially different award relationship requiring review.
    """
    grouped: dict[int, list[dict[str, Any]]] = {}

    for row in rows:
        award_id = int(row["award_id"])
        grouped.setdefault(award_id, []).append(row)

    collapsed: list[dict[str, Any]] = []

    for award_id in sorted(grouped):
        award_rows = grouped[award_id]

        recipient_ueis = {
            value
            for row in award_rows
            if (
                value := clean_text(row.get("recipient_uei"))
            ) is not None
        }

        if len(recipient_ueis) > 1:
            raise ValueError(
                f"Award {award_id} has conflicting recipient UEIs: "
                f"{sorted(recipient_ueis)}"
            )

        collapsed.append(
            {
                "award_id": award_id,
                "generated_unique_award_id": str(
                    award_rows[0]["generated_unique_award_id"]
                ),
                "recipient_uei": (
                    next(iter(recipient_ueis))
                    if recipient_ueis
                    else None
                ),
                "awarding_agency_code": select_latest_value(
                    award_rows,
                    field="awarding_agency_code",
                    ignored_values={"999"},
                ),
                "awarding_subagency_code": select_latest_value(
                    award_rows,
                    field="awarding_subagency_code",
                    ignored_values={"999"},
                ),
                "funding_agency_code": select_latest_value(
                    award_rows,
                    field="funding_agency_code",
                    ignored_values={"999"},
                ),
                "funding_subagency_code": select_latest_value(
                    award_rows,
                    field="funding_subagency_code",
                    ignored_values={"999"},
                ),
            }
        )

    return collapsed


def find_recipient_id(
    cur,
    recipient_uei: str | None,
) -> int | None:
    """
    Resolve a normalized recipient using UEI.
    """
    if recipient_uei is None:
        return None

    cur.execute(
        """
        SELECT recipient_id
        FROM procurement.recipient
        WHERE recipient_uei = %s
        ORDER BY recipient_id
        LIMIT 2;
        """,
        (recipient_uei,),
    )

    rows = cur.fetchall()

    if len(rows) > 1:
        raise ValueError(
            f"Multiple recipients matched UEI {recipient_uei!r}."
        )

    if not rows:
        return None

    return int(rows[0][0])


def find_agency_id(
    cur,
    agency_code: str | None,
) -> int | None:
    """
    Resolve a normalized agency using its agency code.
    """
    if agency_code is None:
        return None

    cur.execute(
        """
        SELECT agency_id
        FROM procurement.agency
        WHERE agency_code = %s
        ORDER BY agency_id
        LIMIT 2;
        """,
        (agency_code,),
    )

    rows = cur.fetchall()

    if len(rows) > 1:
        raise ValueError(
            f"Multiple agencies matched code {agency_code!r}."
        )

    if not rows:
        return None

    return int(rows[0][0])


def build_relationship_plans(
    cur,
    award_sources: list[dict[str, Any]],
) -> list[AwardRelationshipPlan]:
    """
    Resolve normalized IDs for each award source record.
    """
    plans: list[AwardRelationshipPlan] = []

    for source in award_sources:
        plans.append(
            AwardRelationshipPlan(
                award_id=int(source["award_id"]),
                generated_unique_award_id=str(
                    source["generated_unique_award_id"]
                ),
                recipient_uei=source["recipient_uei"],
                recipient_id=find_recipient_id(
                    cur,
                    source["recipient_uei"],
                ),
                awarding_agency_code=source[
                    "awarding_agency_code"
                ],
                awarding_agency_id=find_agency_id(
                    cur,
                    source["awarding_agency_code"],
                ),
                awarding_subagency_code=source[
                    "awarding_subagency_code"
                ],
                awarding_subagency_id=find_agency_id(
                    cur,
                    source["awarding_subagency_code"],
                ),
                funding_agency_code=source[
                    "funding_agency_code"
                ],
                funding_agency_id=find_agency_id(
                    cur,
                    source["funding_agency_code"],
                ),
                funding_subagency_code=source[
                    "funding_subagency_code"
                ],
                funding_subagency_id=find_agency_id(
                    cur,
                    source["funding_subagency_code"],
                ),
            )
        )

    return plans


def resolved_label(
    source_value: str | None,
    normalized_id: int | None,
) -> str:
    """
    Format one proposed relationship.
    """
    if source_value is None:
        return "NO SOURCE VALUE"

    if normalized_id is None:
        return f"UNRESOLVED — source {source_value}"

    return f"RESOLVED — source {source_value}, ID {normalized_id}"


def print_plan(plan: AwardRelationshipPlan) -> None:
    """
    Print one award relationship plan.
    """
    print()
    print("=" * 76)
    print(f"AWARD {plan.award_id}")
    print("=" * 76)

    print(
        f"{'Generated award ID':<28} "
        f"{plan.generated_unique_award_id}"
    )

    print(
        f"{'Recipient':<28} "
        f"{resolved_label(plan.recipient_uei, plan.recipient_id)}"
    )

    print(
        f"{'Awarding agency':<28} "
        f"{resolved_label(
            plan.awarding_agency_code,
            plan.awarding_agency_id,
        )}"
    )

    print(
        f"{'Awarding subagency':<28} "
        f"{resolved_label(
            plan.awarding_subagency_code,
            plan.awarding_subagency_id,
        )}"
    )

    print(
        f"{'Funding agency':<28} "
        f"{resolved_label(
            plan.funding_agency_code,
            plan.funding_agency_id,
        )}"
    )

    print(
        f"{'Funding subagency':<28} "
        f"{resolved_label(
            plan.funding_subagency_code,
            plan.funding_subagency_id,
        )}"
    )


def print_summary(
    plans: list[AwardRelationshipPlan],
) -> None:
    """
    Print aggregate relationship-resolution counts.
    """
    awards = len(plans)

    recipient_links = sum(
        plan.recipient_id is not None
        for plan in plans
    )

    awarding_agency_links = sum(
        plan.awarding_agency_id is not None
        for plan in plans
    )

    awarding_subagency_links = sum(
        plan.awarding_subagency_id is not None
        for plan in plans
    )

    funding_agency_links = sum(
        plan.funding_agency_id is not None
        for plan in plans
    )

    funding_subagency_links = sum(
        plan.funding_subagency_id is not None
        for plan in plans
    )

    print()
    print("=" * 76)
    print("RELATIONSHIP PLAN SUMMARY")
    print("=" * 76)

    print(f"{'Awards examined':<36} {awards}")
    print(f"{'Recipient links resolvable':<36} {recipient_links}")
    print(
        f"{'Awarding-agency links resolvable':<36} "
        f"{awarding_agency_links}"
    )
    print(
        f"{'Awarding-subagency links resolvable':<36} "
        f"{awarding_subagency_links}"
    )
    print(
        f"{'Funding-agency links resolvable':<36} "
        f"{funding_agency_links}"
    )
    print(
        f"{'Funding-subagency links resolvable':<36} "
        f"{funding_subagency_links}"
    )


def main() -> None:
    """
    Run the ETL-004B relationship planner.
    """
    args = parse_arguments()
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            source_rows = get_batch_award_sources(
                cur,
                load_batch_id=args.load_batch_id,
            )

            award_sources = collapse_award_sources(
                source_rows
            )

            plans = build_relationship_plans(
                cur,
                award_sources,
            )

            print_header(
                "ETL-004B — AWARD RELATIONSHIP ENRICHMENT PLAN",
                subtitle=f"Load batch ID: {args.load_batch_id}",
            )

            if not plans:
                print()
                print(
                    "No normalized awards were found for this batch."
                )
                return

            for plan in plans:
                print_plan(plan)

            print_summary(plans)

    except Exception as exc:
        print()
        print("Award relationship planning failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()