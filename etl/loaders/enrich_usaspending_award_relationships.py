"""
ETL-004B — Enrich USAspending award relationships.

This loader resolves award-level recipient and agency foreign keys from the
raw USAspending JSONB records for a selected procurement load batch.

Award-level agency relationships are defined as the latest known populated,
non-placeholder source relationship. Historical transaction-level variation
remains preserved in the raw records.

The loader is idempotent:
- matching existing values are left unchanged,
- NULL values are populated,
- conflicting existing values stop the load unless --force is supplied.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from typing import Any

from etl.common.db import get_connection


PLACEHOLDER_AGENCY_CODES = {"999"}


@dataclass(frozen=True)
class AwardRelationshipSource:
    award_id: int
    generated_unique_award_id: str

    recipient_uei: str | None

    awarding_agency_code: str | None
    awarding_subagency_code: str | None

    funding_agency_code: str | None
    funding_subagency_code: str | None


@dataclass(frozen=True)
class AwardRelationshipResolution:
    award_id: int
    generated_unique_award_id: str

    recipient_id: int | None
    awarding_agency_id: int | None
    awarding_subagency_id: int | None
    funding_agency_id: int | None
    funding_subagency_id: int | None


@dataclass
class EnrichmentMetrics:
    awards_examined: int = 0
    awards_updated: int = 0
    awards_unchanged: int = 0

    recipient_links_written: int = 0
    awarding_agency_links_written: int = 0
    awarding_subagency_links_written: int = 0
    funding_agency_links_written: int = 0
    funding_subagency_links_written: int = 0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Enrich USAspending award recipient and agency relationships."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=4,
        help="Procurement load batch to enrich. Defaults to Batch 4.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Replace conflicting existing award relationships. "
            "Without this flag, conflicts stop the load."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and report relationships without committing updates.",
    )

    return parser.parse_args()


def clean_text(value: Any) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip()

    return cleaned or None


def get_batch_transaction_sources(
    cur,
    *,
    load_batch_id: int,
) -> list[dict[str, Any]]:
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


def select_latest_value(
    rows: list[dict[str, Any]],
    *,
    field: str,
    ignored_values: set[str] | None = None,
) -> str | None:
    ignored = ignored_values or set()

    candidates: list[tuple[date | None, int, str]] = []

    for row in rows:
        value = clean_text(row.get(field))

        if value is None or value in ignored:
            continue

        action_date = row.get("action_date")

        candidates.append(
            (
                action_date,
                int(row.get("source_row_number") or 0),
                value,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item[0] is not None,
            item[0] or date.min,
            item[1],
        )
    )

    return candidates[-1][2]


def collapse_award_sources(
    rows: list[dict[str, Any]],
) -> list[AwardRelationshipSource]:
    grouped: dict[int, list[dict[str, Any]]] = {}

    for row in rows:
        award_id = int(row["award_id"])
        grouped.setdefault(award_id, []).append(row)

    sources: list[AwardRelationshipSource] = []

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

        sources.append(
            AwardRelationshipSource(
                award_id=award_id,
                generated_unique_award_id=str(
                    award_rows[0]["generated_unique_award_id"]
                ),
                recipient_uei=(
                    next(iter(recipient_ueis))
                    if recipient_ueis
                    else None
                ),
                awarding_agency_code=select_latest_value(
                    award_rows,
                    field="awarding_agency_code",
                    ignored_values=PLACEHOLDER_AGENCY_CODES,
                ),
                awarding_subagency_code=select_latest_value(
                    award_rows,
                    field="awarding_subagency_code",
                    ignored_values=PLACEHOLDER_AGENCY_CODES,
                ),
                funding_agency_code=select_latest_value(
                    award_rows,
                    field="funding_agency_code",
                    ignored_values=PLACEHOLDER_AGENCY_CODES,
                ),
                funding_subagency_code=select_latest_value(
                    award_rows,
                    field="funding_subagency_code",
                    ignored_values=PLACEHOLDER_AGENCY_CODES,
                ),
            )
        )

    return sources


def resolve_recipient_id(
    cur,
    *,
    recipient_uei: str | None,
) -> int | None:
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

    return int(rows[0][0]) if rows else None


def resolve_agency_id(
    cur,
    *,
    agency_code: str | None,
) -> int | None:
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

    return int(rows[0][0]) if rows else None


def resolve_relationships(
    cur,
    sources: list[AwardRelationshipSource],
) -> list[AwardRelationshipResolution]:
    resolutions: list[AwardRelationshipResolution] = []

    for source in sources:
        resolution = AwardRelationshipResolution(
            award_id=source.award_id,
            generated_unique_award_id=source.generated_unique_award_id,
            recipient_id=resolve_recipient_id(
                cur,
                recipient_uei=source.recipient_uei,
            ),
            awarding_agency_id=resolve_agency_id(
                cur,
                agency_code=source.awarding_agency_code,
            ),
            awarding_subagency_id=resolve_agency_id(
                cur,
                agency_code=source.awarding_subagency_code,
            ),
            funding_agency_id=resolve_agency_id(
                cur,
                agency_code=source.funding_agency_code,
            ),
            funding_subagency_id=resolve_agency_id(
                cur,
                agency_code=source.funding_subagency_code,
            ),
        )

        unresolved = []

        if source.recipient_uei and resolution.recipient_id is None:
            unresolved.append(
                f"recipient UEI {source.recipient_uei}"
            )

        relationship_pairs = (
            (
                "awarding agency",
                source.awarding_agency_code,
                resolution.awarding_agency_id,
            ),
            (
                "awarding subagency",
                source.awarding_subagency_code,
                resolution.awarding_subagency_id,
            ),
            (
                "funding agency",
                source.funding_agency_code,
                resolution.funding_agency_id,
            ),
            (
                "funding subagency",
                source.funding_subagency_code,
                resolution.funding_subagency_id,
            ),
        )

        for label, code, normalized_id in relationship_pairs:
            if code and normalized_id is None:
                unresolved.append(f"{label} code {code}")

        if unresolved:
            raise ValueError(
                f"Award {source.award_id} has unresolved relationships: "
                + ", ".join(unresolved)
            )

        resolutions.append(resolution)

    return resolutions


def get_existing_relationships(
    cur,
    *,
    award_id: int,
) -> dict[str, int | None]:
    cur.execute(
        """
        SELECT
            recipient_id,
            awarding_agency_id,
            awarding_subagency_id,
            funding_agency_id,
            funding_subagency_id
        FROM procurement.award
        WHERE award_id = %s;
        """,
        (award_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            f"Award ID {award_id} was not found."
        )

    return {
        "recipient_id": row[0],
        "awarding_agency_id": row[1],
        "awarding_subagency_id": row[2],
        "funding_agency_id": row[3],
        "funding_subagency_id": row[4],
    }


def determine_update_values(
    *,
    existing: dict[str, int | None],
    proposed: AwardRelationshipResolution,
    force: bool,
) -> tuple[dict[str, int | None], list[str]]:
    proposed_values = {
        "recipient_id": proposed.recipient_id,
        "awarding_agency_id": proposed.awarding_agency_id,
        "awarding_subagency_id": proposed.awarding_subagency_id,
        "funding_agency_id": proposed.funding_agency_id,
        "funding_subagency_id": proposed.funding_subagency_id,
    }

    updates: dict[str, int | None] = {}
    changed_fields: list[str] = []

    for field, proposed_value in proposed_values.items():
        existing_value = existing[field]

        if proposed_value is None:
            continue

        if existing_value == proposed_value:
            continue

        if existing_value is not None and not force:
            raise ValueError(
                f"Award {proposed.award_id} has conflicting {field}: "
                f"existing={existing_value}, proposed={proposed_value}. "
                "Rerun with --force only after reviewing the conflict."
            )

        updates[field] = proposed_value
        changed_fields.append(field)

    return updates, changed_fields


def update_award_relationships(
    cur,
    *,
    award_id: int,
    updates: dict[str, int | None],
) -> None:
    if not updates:
        return

    allowed_fields = {
        "recipient_id",
        "awarding_agency_id",
        "awarding_subagency_id",
        "funding_agency_id",
        "funding_subagency_id",
    }

    unexpected_fields = set(updates) - allowed_fields

    if unexpected_fields:
        raise ValueError(
            f"Unexpected award fields: {sorted(unexpected_fields)}"
        )

    assignments = ", ".join(
        f"{field} = %s"
        for field in updates
    )

    parameters = list(updates.values())
    parameters.append(award_id)

    cur.execute(
        f"""
        UPDATE procurement.award
        SET {assignments}
        WHERE award_id = %s;
        """,
        parameters,
    )

    if cur.rowcount != 1:
        raise ValueError(
            f"Expected to update Award {award_id}, "
            f"but UPDATE affected {cur.rowcount} rows."
        )


def increment_link_metrics(
    metrics: EnrichmentMetrics,
    changed_fields: list[str],
) -> None:
    metric_map = {
        "recipient_id": "recipient_links_written",
        "awarding_agency_id": "awarding_agency_links_written",
        "awarding_subagency_id": (
            "awarding_subagency_links_written"
        ),
        "funding_agency_id": "funding_agency_links_written",
        "funding_subagency_id": (
            "funding_subagency_links_written"
        ),
    }

    for field in changed_fields:
        metric_name = metric_map[field]
        setattr(
            metrics,
            metric_name,
            getattr(metrics, metric_name) + 1,
        )


def enrich_awards(
    cur,
    *,
    resolutions: list[AwardRelationshipResolution],
    force: bool,
    dry_run: bool,
) -> EnrichmentMetrics:
    metrics = EnrichmentMetrics()

    for resolution in resolutions:
        metrics.awards_examined += 1

        existing = get_existing_relationships(
            cur,
            award_id=resolution.award_id,
        )

        updates, changed_fields = determine_update_values(
            existing=existing,
            proposed=resolution,
            force=force,
        )

        print()
        print(
            f"Award {resolution.award_id}: "
            f"{resolution.generated_unique_award_id}"
        )

        if not updates:
            print("  No changes required.")
            metrics.awards_unchanged += 1
            continue

        for field in changed_fields:
            print(
                f"  {field}: "
                f"{existing[field]} -> {updates[field]}"
            )

        if dry_run:
            print("  DRY RUN — no update written.")
        else:
            update_award_relationships(
                cur,
                award_id=resolution.award_id,
                updates=updates,
            )
            print("  Updated.")

        metrics.awards_updated += 1
        increment_link_metrics(metrics, changed_fields)

    return metrics


def print_summary(
    *,
    load_batch_id: int,
    metrics: EnrichmentMetrics,
    dry_run: bool,
) -> None:
    print()
    print("=" * 76)
    print("ETL-004B — AWARD RELATIONSHIP ENRICHMENT")
    print("=" * 76)
    print(f"Load batch ID: {load_batch_id}")
    print(f"Mode: {'DRY RUN' if dry_run else 'COMMIT'}")
    print()
    print(f"Awards examined ................ {metrics.awards_examined}")
    print(f"Awards updated ................. {metrics.awards_updated}")
    print(f"Awards unchanged ............... {metrics.awards_unchanged}")
    print()
    print(
        "Recipient links written ........ "
        f"{metrics.recipient_links_written}"
    )
    print(
        "Awarding agency links written ... "
        f"{metrics.awarding_agency_links_written}"
    )
    print(
        "Awarding subagency links written  "
        f"{metrics.awarding_subagency_links_written}"
    )
    print(
        "Funding agency links written .... "
        f"{metrics.funding_agency_links_written}"
    )
    print(
        "Funding subagency links written . "
        f"{metrics.funding_subagency_links_written}"
    )


def main() -> None:
    args = parse_arguments()
    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                transaction_rows = get_batch_transaction_sources(
                    cur,
                    load_batch_id=args.load_batch_id,
                )

                sources = collapse_award_sources(
                    transaction_rows
                )

                if not sources:
                    raise ValueError(
                        "No award relationships were found for "
                        f"load batch {args.load_batch_id}."
                    )

                resolutions = resolve_relationships(
                    cur,
                    sources,
                )

                metrics = enrich_awards(
                    cur,
                    resolutions=resolutions,
                    force=args.force,
                    dry_run=args.dry_run,
                )

                if args.dry_run:
                    conn.rollback()

        print_summary(
            load_batch_id=args.load_batch_id,
            metrics=metrics,
            dry_run=args.dry_run,
        )

    except Exception as exc:
        conn.rollback()

        print()
        print("Award relationship enrichment failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()