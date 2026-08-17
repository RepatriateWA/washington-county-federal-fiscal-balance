"""
ETL-004A.3D — Normalize USAspending recipients.

Builds canonical recipient records from immutable USAspending award
transaction observations.

Identity precedence:
    1. UEI
    2. DUNS
    3. Normalized recipient name, only when both identifiers are absent

Rows that share a UEI or DUNS are consolidated. A recipient name is never
used to collapse two identified entities, because separate legal entities can
share the same display name.

Usage:
    python -m etl.loaders.normalize_usaspending_recipients

Optional explicit batch:
    python -m etl.loaders.normalize_usaspending_recipients \
        --load-batch-id 2
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from etl.common.usaspending import parse_date
from etl.validation.common.normalization_exception_recorder import (
    NormalizationExceptionRecorder,
)
from etl.validation.common.recipient_parent_relationship_recorder import (
    RecipientParentRelationship,
    RecipientParentRelationshipRecorder,
)

from etl.common.db import get_connection


COMPLETED_STATUSES = {"COMPLETED", "COMPLETED_WITH_REJECTIONS"}

@dataclass(frozen=True)
class RawRecipientObservation:
    source_row_number: int
    action_date: date | None
    recipient_uei: str | None
    recipient_duns: str | None
    recipient_name: str
    recipient_parent_uei: str | None
    recipient_parent_name: str | None

@dataclass(frozen=True)
class ParentRelationshipObservation:
    """One parent relationship observed on one source row."""

    recipient_uei: str
    parent_uei: str
    parent_name: str | None
    action_date: date | None
    source_row_number: int

@dataclass(frozen=True)
class RecipientParentResolution:
    """Canonical and historical parent relationships for a recipient."""

    canonical_parent_uei: str | None
    canonical_parent_name: str | None
    relationships: tuple[RecipientParentRelationship, ...]
    anomaly: dict[str, Any] | None    

@dataclass
class RecipientCandidate:
    recipient_uei: str | None
    recipient_duns: str | None
    recipient_name: str
    recipient_name_normalized: str
    recipient_parent_uei: str | None
    recipient_parent_name: str | None
    source_rows: set[int] = field(default_factory=set)

    def absorb(self, other: "RecipientCandidate") -> None:
        self.recipient_uei = choose_identifier(
            self.recipient_uei,
            other.recipient_uei,
            "UEI",
        )

        self.recipient_duns = choose_identifier(
            self.recipient_duns,
            other.recipient_duns,
            "DUNS",
        )

        if len(other.recipient_name) > len(self.recipient_name):
            self.recipient_name = other.recipient_name

        self.recipient_name_normalized = normalize_name(
            self.recipient_name
        )

        # Parent relationships are resolved separately because they can
        # legitimately change over time.
        self.source_rows.update(other.source_rows)

@dataclass(frozen=True)
class ExistingRecipient:
    recipient_id: int
    recipient_uei: str | None
    recipient_duns: str | None
    recipient_name: str
    recipient_name_normalized: str | None
    recipient_parent_uei: str | None
    recipient_parent_name: str | None


@dataclass(frozen=True)
class LoadSummary:
    raw_observations: int
    distinct_candidates: int
    inserted: int
    updated: int
    unchanged: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize USAspending recipients."
    )
    parser.add_argument(
        "--load-batch-id",
        type=int,
        default=None,
        help=(
            "Raw procurement load batch to normalize. Defaults to the latest "
            "completed batch containing raw observations."
        ),
    )
    return parser.parse_args()


def normalize_null(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NULL", "NONE", "N/A", "NA", "NAN"}:
        return None
    return text


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value: str) -> str:
    return collapse_whitespace(value).upper()


def normalize_uei(value: Any) -> str | None:
    text = normalize_null(value)
    if text is None:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    if len(normalized) != 12:
        raise ValueError(f"Invalid UEI {text!r}; expected 12 characters.")
    return normalized


def normalize_duns(value: Any) -> str | None:
    text = normalize_null(value)
    if text is None:
        return None
    normalized = re.sub(r"\D", "", text)
    if not normalized:
        return None
    if len(normalized) > 9:
        raise ValueError(f"Invalid DUNS {text!r}; expected at most 9 digits.")
    return normalized.zfill(9)


def choose_identifier(
    current: str | None,
    incoming: str | None,
    label: str,
) -> str | None:
    if current is None:
        return incoming
    if incoming is None:
        return current
    if current != incoming:
        raise ValueError(
            f"Conflicting {label} values: {current!r} and {incoming!r}."
        )
    return current


def choose_preferred_text(
    current: str | None,
    incoming: str | None,
) -> str | None:
    if current is None:
        return incoming
    if incoming is None:
        return current
    return incoming if len(incoming) > len(current) else current


def get_target_batch(conn, requested_batch_id: int | None) -> tuple[int, str]:
    with conn.cursor() as cur:
        if requested_batch_id is not None:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id)
                FROM procurement.load_batch lb
                LEFT JOIN procurement.raw_award_transaction raw
                    ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_batch_id = %s
                GROUP BY
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status;
                """,
                (requested_batch_id,),
            )
        else:
            cur.execute(
                """
                SELECT
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status,
                    COUNT(raw.raw_award_transaction_id)
                FROM procurement.load_batch lb
                JOIN procurement.raw_award_transaction raw
                    ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_status IN (
                    'COMPLETED',
                    'COMPLETED_WITH_REJECTIONS'
                )
                GROUP BY
                    lb.load_batch_id,
                    lb.source_file,
                    lb.load_status
                ORDER BY lb.load_batch_id DESC
                LIMIT 1;
                """
            )
        row = cur.fetchone()

    if row is None:
        if requested_batch_id is None:
            raise ValueError(
                "No completed procurement batch containing raw rows was found."
            )
        raise ValueError(f"Load batch {requested_batch_id} does not exist.")

    load_batch_id, source_file, load_status, raw_count = row
    if load_status not in COMPLETED_STATUSES:
        raise ValueError(
            f"Load batch {load_batch_id} has status {load_status!r}; "
            "a completed batch is required."
        )
    if int(raw_count) == 0:
        raise ValueError(f"Load batch {load_batch_id} contains no raw rows.")
    return int(load_batch_id), str(source_file)


def read_raw_recipient_observations(
    conn,
    load_batch_id: int,
) -> list[RawRecipientObservation]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                source_row_number,
                raw_record ->> 'action_date',
                raw_record ->> 'recipient_uei',
                raw_record ->> 'recipient_duns',
                raw_record ->> 'recipient_name',
                raw_record ->> 'recipient_parent_uei',
                raw_record ->> 'recipient_parent_name'
            FROM procurement.raw_award_transaction
            WHERE load_batch_id = %s
            ORDER BY source_row_number, raw_award_transaction_id;
            """,
            (load_batch_id,),
        )
        rows = cur.fetchall()

    observations: list[RawRecipientObservation] = []
    for (
        source_row_number,
        raw_action_date,
        recipient_uei,
        recipient_duns,
        recipient_name,
        recipient_parent_uei,
        recipient_parent_name,
    ) in rows:
        clean_name = normalize_null(recipient_name)
        if clean_name is None:
            raise ValueError(
                f"Missing recipient_name at source row {source_row_number}."
            )
        parent_name = normalize_null(recipient_parent_name)

        try:
            action_date = parse_date(
                normalize_null(raw_action_date)
            )

        except ValueError as exc:
            raise ValueError(
                f"Invalid action_date at source row "
                f"{source_row_number}: {raw_action_date!r}."
            ) from exc

        observations.append(
            RawRecipientObservation(
                source_row_number=int(source_row_number),
                action_date=action_date,
                recipient_uei=normalize_uei(recipient_uei),
                recipient_duns=normalize_duns(recipient_duns),
                recipient_name=collapse_whitespace(clean_name),
                recipient_parent_uei=normalize_uei(recipient_parent_uei),
                recipient_parent_name=(
                    collapse_whitespace(parent_name)
                    if parent_name is not None
                    else None
                ),
            )
        )
    return observations

def build_parent_relationship_observations(
    observations: Iterable[RawRecipientObservation],
) -> list[ParentRelationshipObservation]:
    """Return valid recipient-parent observations from raw rows."""
    relationships: list[ParentRelationshipObservation] = []

    for observation in observations:
        if (
            observation.recipient_uei is None
            or observation.recipient_parent_uei is None
        ):
            continue

        relationships.append(
            ParentRelationshipObservation(
                recipient_uei=observation.recipient_uei,
                parent_uei=observation.recipient_parent_uei,
                parent_name=observation.recipient_parent_name,
                action_date=observation.action_date,
                source_row_number=observation.source_row_number,
            )
        )

    return relationships


def resolve_parent_relationships(
    observations: Iterable[ParentRelationshipObservation],
    *,
    load_batch_id: int,
) -> dict[str, RecipientParentResolution]:
    """
    Resolve canonical and historical parent relationships by recipient UEI.

    Canonical-selection policy:
    - latest action date wins;
    - highest source-row number breaks equal-date ties.
    """
    grouped: dict[
        str,
        dict[str, list[ParentRelationshipObservation]],
    ] = {}

    for observation in observations:
        recipient_group = grouped.setdefault(
            observation.recipient_uei,
            {},
        )

        parent_group = recipient_group.setdefault(
            observation.parent_uei,
            [],
        )

        parent_group.append(observation)

    resolutions: dict[str, RecipientParentResolution] = {}

    for recipient_uei in sorted(grouped):
        parents = grouped[recipient_uei]

        parent_summaries: list[
            tuple[
                RecipientParentRelationship,
                ParentRelationshipObservation,
            ]
        ] = []

        for parent_uei in sorted(parents):
            values = parents[parent_uei]

            latest_observation = max(
                values,
                key=lambda item: (
                    item.action_date or date.min,
                    item.source_row_number,
                ),
            )

            action_dates = [
                item.action_date
                for item in values
                if item.action_date is not None
            ]

            source_rows = sorted(
                item.source_row_number
                for item in values
            )

            relationship = RecipientParentRelationship(
                recipient_uei=recipient_uei,
                parent_uei=parent_uei,
                observed_parent_name=(
                    latest_observation.parent_name
                ),
                occurrence_count=len(values),
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
                first_source_row_number=source_rows[0],
                last_source_row_number=source_rows[-1],
            )

            parent_summaries.append(
                (
                    relationship,
                    latest_observation,
                )
            )

        (
            canonical_relationship,
            canonical_observation,
        ) = max(
            parent_summaries,
            key=lambda item: (
                item[1].action_date or date.min,
                item[1].source_row_number,
            ),
        )

        anomaly: dict[str, Any] | None = None

        if len(parent_summaries) > 1:
            all_source_rows = sorted(
                {
                    observation.source_row_number
                    for values in parents.values()
                    for observation in values
                }
            )

            observed_relationships = []

            for relationship, _latest in parent_summaries:
                observed_relationships.append(
                    {
                        "parent_uei": relationship.parent_uei,
                        "observed_parent_name": (
                            relationship.observed_parent_name
                        ),
                        "occurrence_count": (
                            relationship.occurrence_count
                        ),
                        "first_action_date": (
                            relationship.first_action_date.isoformat()
                            if relationship.first_action_date
                            is not None
                            else None
                        ),
                        "last_action_date": (
                            relationship.last_action_date.isoformat()
                            if relationship.last_action_date
                            is not None
                            else None
                        ),
                        "first_source_row_number": (
                            relationship.first_source_row_number
                        ),
                        "last_source_row_number": (
                            relationship.last_source_row_number
                        ),
                    }
                )

            anomaly = {
                "load_batch_id": load_batch_id,
                "entity_type": "recipient",
                "entity_key": recipient_uei,
                "anomaly_code": "PARENT_UEI_ALIAS",
                "severity": "WARNING",
                "source_row_numbers": all_source_rows,
                "raw_values": {
                    "observed_parent_relationships": (
                        observed_relationships
                    ),
                },
                "normalized_action": {
                    "canonical_parent_uei": (
                        canonical_relationship.parent_uei
                    ),
                    "canonical_parent_name": (
                        canonical_relationship.observed_parent_name
                    ),
                    "selection_rule": (
                        "Select the parent relationship from the "
                        "latest action date, breaking ties with "
                        "the highest source-row number."
                    ),
                },
                "message": (
                    "Multiple parent UEIs were observed for "
                    f"recipient UEI {recipient_uei!r}. All "
                    "relationships were preserved and the most "
                    "recent observation was selected as canonical."
                ),
            }

        resolutions[recipient_uei] = RecipientParentResolution(
            canonical_parent_uei=(
                canonical_relationship.parent_uei
            ),
            canonical_parent_name=(
                canonical_relationship.observed_parent_name
            ),
            relationships=tuple(
                relationship
                for relationship, _latest
                in parent_summaries
            ),
            anomaly=anomaly,
        )

    return resolutions

def candidate_from_observation(
    observation: RawRecipientObservation,
) -> RecipientCandidate:
    return RecipientCandidate(
        recipient_uei=observation.recipient_uei,
        recipient_duns=observation.recipient_duns,
        recipient_name=observation.recipient_name,
        recipient_name_normalized=normalize_name(
            observation.recipient_name
        ),
        recipient_parent_uei=None,
        recipient_parent_name=None,
        source_rows={observation.source_row_number},
    )

def consolidate_candidates(
    observations: Iterable[RawRecipientObservation],
) -> list[RecipientCandidate]:
    candidates: list[RecipientCandidate] = []
    uei_index: dict[str, RecipientCandidate] = {}
    duns_index: dict[str, RecipientCandidate] = {}
    name_only_index: dict[str, RecipientCandidate] = {}

    def reindex(candidate: RecipientCandidate) -> None:
        if candidate.recipient_uei is not None:
            uei_index[candidate.recipient_uei] = candidate
        if candidate.recipient_duns is not None:
            duns_index[candidate.recipient_duns] = candidate

    def merge_candidates(
        survivor: RecipientCandidate,
        absorbed: RecipientCandidate,
    ) -> RecipientCandidate:
        if survivor is absorbed:
            return survivor
        survivor.absorb(absorbed)
        for key, value in list(uei_index.items()):
            if value is absorbed:
                uei_index[key] = survivor
        for key, value in list(duns_index.items()):
            if value is absorbed:
                duns_index[key] = survivor
        for key, value in list(name_only_index.items()):
            if value is absorbed:
                name_only_index[key] = survivor
        if absorbed in candidates:
            candidates.remove(absorbed)
        reindex(survivor)
        return survivor

    for observation in observations:
        incoming = candidate_from_observation(observation)

        if incoming.recipient_uei is None and incoming.recipient_duns is None:
            existing = name_only_index.get(incoming.recipient_name_normalized)
            if existing is None:
                candidates.append(incoming)
                name_only_index[incoming.recipient_name_normalized] = incoming
            else:
                existing.absorb(incoming)
            continue

        by_uei = (
            uei_index.get(incoming.recipient_uei)
            if incoming.recipient_uei is not None
            else None
        )
        by_duns = (
            duns_index.get(incoming.recipient_duns)
            if incoming.recipient_duns is not None
            else None
        )

        if by_uei is not None and by_duns is not None and by_uei is not by_duns:
            target = merge_candidates(by_uei, by_duns)
        else:
            target = by_uei or by_duns

        if target is None:
            candidates.append(incoming)
            target = incoming
        else:
            target.absorb(incoming)
        reindex(target)

    return sorted(
        candidates,
        key=lambda item: (
            item.recipient_uei or "",
            item.recipient_duns or "",
            item.recipient_name_normalized,
        ),
    )

def apply_parent_resolutions(
    candidates: list[RecipientCandidate],
    resolutions: dict[str, RecipientParentResolution],
) -> None:
    """Attach canonical parent values to recipient candidates."""
    for candidate in candidates:
        if candidate.recipient_uei is None:
            continue

        resolution = resolutions.get(
            candidate.recipient_uei
        )

        if resolution is None:
            candidate.recipient_parent_uei = None
            candidate.recipient_parent_name = None
            continue

        candidate.recipient_parent_uei = (
            resolution.canonical_parent_uei
        )

        candidate.recipient_parent_name = (
            resolution.canonical_parent_name
        )
        
def read_existing_recipients(conn) -> list[ExistingRecipient]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                recipient_id,
                recipient_uei,
                recipient_duns,
                recipient_name,
                recipient_name_normalized,
                recipient_parent_uei,
                recipient_parent_name
            FROM procurement.recipient
            ORDER BY recipient_id;
            """
        )
        rows = cur.fetchall()

    return [
        ExistingRecipient(
            recipient_id=int(row[0]),
            recipient_uei=normalize_uei(row[1]),
            recipient_duns=normalize_duns(row[2]),
            recipient_name=str(row[3]),
            recipient_name_normalized=(
                str(row[4]) if row[4] is not None else None
            ),
            recipient_parent_uei=normalize_uei(row[5]),
            recipient_parent_name=(str(row[6]) if row[6] is not None else None),
        )
        for row in rows
    ]


def build_existing_indexes(
    existing: Iterable[ExistingRecipient],
) -> tuple[
    dict[str, ExistingRecipient],
    dict[str, ExistingRecipient],
]:
    """
    Build identifier-based indexes for existing procurement recipients.

    Canonical recipient names are not globally unique. The shared recipient
    identity model permits multiple NAME_FINGERPRINT identities to have the
    same normalized display name, so name-only matching is intentionally
    prohibited here.
    """
    uei_index: dict[str, ExistingRecipient] = {}
    duns_index: dict[str, ExistingRecipient] = {}

    for recipient in existing:
        if recipient.recipient_uei is not None:
            if recipient.recipient_uei in uei_index:
                raise ValueError(
                    f"Duplicate recipient UEI already exists: "
                    f"{recipient.recipient_uei}"
                )
            uei_index[recipient.recipient_uei] = recipient

        if recipient.recipient_duns is not None:
            if recipient.recipient_duns in duns_index:
                raise ValueError(
                    f"Duplicate recipient DUNS already exists: "
                    f"{recipient.recipient_duns}"
                )
            duns_index[recipient.recipient_duns] = recipient

    return uei_index, duns_index


def resolve_existing_recipient(
    candidate: RecipientCandidate,
    uei_index: dict[str, ExistingRecipient],
    duns_index: dict[str, ExistingRecipient],
) -> ExistingRecipient | None:
    """
    Resolve an existing procurement recipient by stable identifiers only.

    Name-only matching is intentionally prohibited because the shared
    recipient dimension permits multiple distinct NAME_FINGERPRINT
    identities with the same normalized display name.
    """
    matches: dict[int, ExistingRecipient] = {}

    if candidate.recipient_uei is not None:
        match = uei_index.get(candidate.recipient_uei)
        if match is not None:
            matches[match.recipient_id] = match

    if candidate.recipient_duns is not None:
        match = duns_index.get(candidate.recipient_duns)
        if match is not None:
            matches[match.recipient_id] = match

    if len(matches) > 1:
        raise ValueError(
            "Candidate identifiers resolve to different existing recipients: "
            f"UEI={candidate.recipient_uei!r}, "
            f"DUNS={candidate.recipient_duns!r}."
        )

    if matches:
        return next(iter(matches.values()))

    return None


def recipient_values_differ(
    existing: ExistingRecipient,
    candidate: RecipientCandidate,
) -> bool:
    return any(
        (
            existing.recipient_uei != candidate.recipient_uei,
            existing.recipient_duns != candidate.recipient_duns,
            existing.recipient_name != candidate.recipient_name,
            existing.recipient_name_normalized
            != candidate.recipient_name_normalized,
            existing.recipient_parent_uei != candidate.recipient_parent_uei,
            existing.recipient_parent_name != candidate.recipient_parent_name,
        )
    )


def apply_candidates(
    conn,
    candidates: list[RecipientCandidate],
) -> tuple[int, int, int]:
    inserted = 0
    updated = 0
    unchanged = 0

    existing = read_existing_recipients(conn)
    uei_index, duns_index = build_existing_indexes(existing)

    with conn.cursor() as cur:
        for candidate in candidates:
            match = resolve_existing_recipient(
                candidate, uei_index, duns_index
            )

            if match is None:
                cur.execute(
                    """
                    INSERT INTO procurement.recipient (
                        recipient_uei,
                        recipient_duns,
                        recipient_name,
                        recipient_name_normalized,
                        recipient_parent_uei,
                        recipient_parent_name,
                        recipient_type_code,
                        business_categories
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL)
                    RETURNING recipient_id;
                    """,
                    (
                        candidate.recipient_uei,
                        candidate.recipient_duns,
                        candidate.recipient_name,
                        candidate.recipient_name_normalized,
                        candidate.recipient_parent_uei,
                        candidate.recipient_parent_name,
                    ),
                )
                recipient_id = int(cur.fetchone()[0])
                inserted += 1
            else:
                recipient_id = match.recipient_id
                merged_candidate = RecipientCandidate(
                    recipient_uei=choose_identifier(
                        match.recipient_uei, candidate.recipient_uei, "UEI"
                    ),
                    recipient_duns=choose_identifier(
                        match.recipient_duns, candidate.recipient_duns, "DUNS"
                    ),
                    recipient_name=candidate.recipient_name,
                    recipient_name_normalized=candidate.recipient_name_normalized,
                    # Parent relationships are temporal and are reconciled separately from
                    # recipient identity using procurement.recipient_parent_relationship.
                    recipient_parent_uei=match.recipient_parent_uei,
                    recipient_parent_name=match.recipient_parent_name,
                )

                if recipient_values_differ(match, merged_candidate):
                    cur.execute(
                        """
                        UPDATE procurement.recipient
                        SET
                            recipient_uei = %s,
                            recipient_duns = %s,
                            recipient_name = %s,
                            recipient_name_normalized = %s,
                            recipient_parent_uei = %s,
                            recipient_parent_name = %s
                        WHERE recipient_id = %s;
                        """,
                        (
                            merged_candidate.recipient_uei,
                            merged_candidate.recipient_duns,
                            merged_candidate.recipient_name,
                            merged_candidate.recipient_name_normalized,
                            merged_candidate.recipient_parent_uei,
                            merged_candidate.recipient_parent_name,
                            recipient_id,
                        ),
                    )
                    updated += 1
                else:
                    unchanged += 1

            if match is None:
                refreshed_candidate = candidate
            else:
                refreshed_candidate = merged_candidate

            refreshed = ExistingRecipient(
                recipient_id=recipient_id,
                recipient_uei=refreshed_candidate.recipient_uei,
                recipient_duns=refreshed_candidate.recipient_duns,
                recipient_name=refreshed_candidate.recipient_name,
                recipient_name_normalized=(
                    refreshed_candidate.recipient_name_normalized
                ),
                recipient_parent_uei=(
                    refreshed_candidate.recipient_parent_uei
                ),
                recipient_parent_name=(
                    refreshed_candidate.recipient_parent_name
                ),
            )

            if candidate.recipient_uei is not None:
                uei_index[candidate.recipient_uei] = refreshed
            if candidate.recipient_duns is not None:
                duns_index[candidate.recipient_duns] = refreshed
            
    return inserted, updated, unchanged


def validate_recipient_dimension(
    conn,
    observations: list[RawRecipientObservation],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT recipient_uei, COUNT(*)
            FROM procurement.recipient
            WHERE recipient_uei IS NOT NULL
            GROUP BY recipient_uei
            HAVING COUNT(*) > 1;
            """
        )
        duplicate_ueis = cur.fetchall()

        cur.execute(
            """
            SELECT recipient_duns, COUNT(*)
            FROM procurement.recipient
            WHERE recipient_duns IS NOT NULL
            GROUP BY recipient_duns
            HAVING COUNT(*) > 1;
            """
        )
        duplicate_duns = cur.fetchall()

        cur.execute(
            """
            SELECT COUNT(*)
            FROM procurement.recipient
            WHERE recipient_name IS NULL OR BTRIM(recipient_name) = '';
            """
        )
        missing_names = int(cur.fetchone()[0])

    if duplicate_ueis:
        raise ValueError(f"Duplicate recipient UEIs found: {duplicate_ueis!r}")
    if duplicate_duns:
        raise ValueError(
            f"Duplicate recipient DUNS values found: {duplicate_duns!r}"
        )
    if missing_names:
        raise ValueError(
            f"Found {missing_names} recipients without a valid name."
        )

    existing = read_existing_recipients(conn)
    uei_index, duns_index = build_existing_indexes(existing)
    unresolved_rows: list[int] = []

    for observation in observations:
        candidate = candidate_from_observation(observation)
        match = resolve_existing_recipient(
            candidate, uei_index, duns_index
        )
        if match is None:
            unresolved_rows.append(observation.source_row_number)

    if unresolved_rows:
        preview = ", ".join(str(row) for row in unresolved_rows[:10])
        raise ValueError(
            f"{len(unresolved_rows)} raw recipient observations could not "
            f"resolve to procurement.recipient. First rows: {preview}"
        )


def print_summary(summary: LoadSummary, elapsed_seconds: float) -> None:
    print()
    print("=" * 68)
    print("ETL-004A.3D SUMMARY")
    print("=" * 68)
    print(
        f"Raw observations examined .............. "
        f"{summary.raw_observations:,}"
    )
    print(
        f"Distinct recipients discovered ......... "
        f"{summary.distinct_candidates:,}"
    )
    print(f"Recipients inserted ..................... {summary.inserted:,}")
    print(f"Recipients updated ...................... {summary.updated:,}")
    print(f"Recipients unchanged .................... {summary.unchanged:,}")
    print("Duplicate UEIs .......................... 0")
    print("Duplicate DUNS values ................... 0")
    print("Unresolved raw observations ............. 0")
    print("Validation .............................. PASS")
    print(f"Elapsed time ............................ {elapsed_seconds:.2f} sec")
    print("=" * 68)


def synchronize_canonical_parent_relationships(
    conn,
    *,
    recipient_ueis: Iterable[str],
) -> int:
    """
    Recompute canonical recipient-parent values from preserved relationship
    history.

    Selection policy is load-order invariant:
    1. latest observed last_action_date wins;
    2. latest first_action_date breaks an equal last-date tie;
    3. parent UEI provides a deterministic final tie-break.

    Relationships with dated observations outrank undated observations.
    """
    normalized_ueis = sorted(
        {
            uei
            for uei in recipient_ueis
            if uei is not None
        }
    )

    if not normalized_ueis:
        return 0

    updated = 0

    with conn.cursor() as cur:
        for recipient_uei in normalized_ueis:
            cur.execute(
                """
                SELECT
                    parent_uei,
                    observed_parent_name
                FROM procurement.recipient_parent_relationship
                WHERE recipient_uei = %s
                ORDER BY
                    last_action_date DESC NULLS LAST,
                    first_action_date DESC NULLS LAST,
                    parent_uei ASC
                LIMIT 1;
                """,
                (recipient_uei,),
            )

            row = cur.fetchone()

            if row is None:
                continue

            canonical_parent_uei = row[0]
            canonical_parent_name = row[1]

            cur.execute(
                """
                UPDATE procurement.recipient
                SET
                    recipient_parent_uei = %s,
                    recipient_parent_name = %s
                WHERE recipient_uei = %s
                  AND (
                        recipient_parent_uei IS DISTINCT FROM %s
                     OR recipient_parent_name IS DISTINCT FROM %s
                  );
                """,
                (
                    canonical_parent_uei,
                    canonical_parent_name,
                    recipient_uei,
                    canonical_parent_uei,
                    canonical_parent_name,
                ),
            )

            updated += cur.rowcount

    return updated

def main() -> None:
    args = parse_arguments()
    started = time.perf_counter()

    print("=" * 68)
    print("ETL-004A.3D — Normalize USAspending Recipients")
    print("=" * 68)

    conn = get_connection()

    try:
        load_batch_id, source_file = get_target_batch(conn, args.load_batch_id)
        print(f"Target raw load batch: {load_batch_id}")
        print(f"Source file: {source_file}")

        observations = read_raw_recipient_observations(conn, load_batch_id)
        print(f"Raw observations read: {len(observations):,}")

        unidentified_rows = [
            observation.source_row_number
            for observation in observations
            if observation.recipient_uei is None
            and observation.recipient_duns is None
        ]

        if unidentified_rows:
            preview = ", ".join(
                str(row) for row in unidentified_rows[:10]
            )
            raise ValueError(
                f"{len(unidentified_rows):,} procurement recipient observations "
                "have neither UEI nor DUNS. Name-only procurement identity "
                "resolution is intentionally disabled pending migration to the "
                "shared recipient identity framework. "
                f"First rows: {preview}"
            )

        candidates = consolidate_candidates(observations)

        parent_observations = (
            build_parent_relationship_observations(
                observations
            )
        )

        parent_resolutions = resolve_parent_relationships(
            parent_observations,
            load_batch_id=load_batch_id,
        )

        apply_parent_resolutions(
            candidates,
            parent_resolutions,
        )

        print(
            "Recipient-parent relationships derived: "
            f"{len(parent_observations):,}"
        )

        print(
            "Recipients with parent history: "
            f"{len(parent_resolutions):,}"
        )

        print(f"Canonical recipient candidates: {len(candidates):,}")

        inserted, updated, unchanged = apply_candidates(conn, candidates)

        relationship_recorder = (
            RecipientParentRelationshipRecorder()
        )

        relationships = []

        for resolution in parent_resolutions.values():
            relationships.extend(
                resolution.relationships
            )

        relationship_count = (
            relationship_recorder.record(
                conn,
                load_batch_id=load_batch_id,
                relationships=relationships,
            )
        )

        print(
            "Recipient-parent relationships recorded: "
            f"{relationship_count:,}"
        )

        canonical_parent_updates = (
            synchronize_canonical_parent_relationships(
                conn,
                recipient_ueis=parent_resolutions.keys(),
            )
        )

        print(
            "Canonical parent relationships synchronized: "
            f"{canonical_parent_updates:,}"
        )

        anomalies = [
            resolution.anomaly
            for resolution in parent_resolutions.values()
            if resolution.anomaly is not None
        ]

        exception_recorder = NormalizationExceptionRecorder()

        for anomaly in anomalies:
            exception_recorder.record(
                conn,
                load_batch_id=anomaly["load_batch_id"],
                entity_type=anomaly["entity_type"],
                entity_key=anomaly["entity_key"],
                anomaly_code=anomaly["anomaly_code"],
                severity=anomaly["severity"],
                source_row_numbers=anomaly["source_row_numbers"],
                raw_values=anomaly["raw_values"],
                normalized_action=anomaly["normalized_action"],
                message=anomaly["message"],
            )

        exception_count = len(anomalies)

        print(
            "Normalization exceptions recorded: "
            f"{exception_count:,}"
        )

        validate_recipient_dimension(conn, observations)
        conn.commit()

        summary = LoadSummary(
            raw_observations=len(observations),
            distinct_candidates=len(candidates),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
        )
        print_summary(summary, time.perf_counter() - started)
        print()
        print("ETL-004A.3D completed successfully.")

    except Exception as exc:
        conn.rollback()
        print()
        print("ETL-004A.3D failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()