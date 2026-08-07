"""Normalize Assistance recipients into the shared USAspending recipient domain."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from etl.common.db import get_connection
from etl.common.normalization.canonical import select_canonical

from etl.common.identity import (
    RecipientIdentityInput,
    classify_recipient_identity,
)
from etl.common.normalization.canonical import (
    select_canonical,
)
from etl.common.normalization.text import (
    clean_optional_text,
    normalize_comparison_text,
)

EVIDENCE_ROOT = Path("evidence/assistance")

@dataclass(frozen=True)
class RecipientObservation:
    """One Assistance recipient observation from a raw source row."""

    source_row_number: int
    assistance_award_unique_key: str

    recipient_uei: str | None
    recipient_name: str
    recipient_name_raw: str | None

    recipient_parent_uei: str | None
    recipient_parent_name: str | None

    business_types_code: str | None
    business_types_description: str | None

    recipient_country_code: str | None
    recipient_state_code: str | None
    recipient_city_name: str | None
    recipient_zip_code: str | None
    recipient_address_line_1: str | None

    recipient_identity_key: str
    recipient_identity_type: str
    recipient_source_condition: str | None


@dataclass(frozen=True)
class CanonicalRecipient:
    """One deterministic shared recipient identity."""

    recipient_identity_key: str
    recipient_identity_type: str
    recipient_source_condition: str | None

    recipient_uei: str | None
    recipient_name: str
    recipient_name_normalized: str

    recipient_parent_uei: str | None
    recipient_parent_name: str | None

    recipient_type_code: str | None
    business_categories: str | None

    observation_count: int
    award_count: int
    source_row_first: int
    source_row_last: int

    observations: tuple[RecipientObservation, ...]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize Assistance recipients into the shared "
            "USAspending recipient domain."
        )
    )

    parser.add_argument(
        "--load-batch-id",
        type=int,
        required=True,
        help="Raw Assistance load batch ID.",
    )

    return parser.parse_args()

def extract_observations(
    cur,
    *,
    load_batch_id: int,
) -> tuple[int, list[RecipientObservation]]:
    """Extract and classify all raw Assistance recipient observations."""

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

            NULLIF(
                BTRIM(raw_record ->> 'recipient_uei'),
                ''
            ) AS recipient_uei,

            NULLIF(
                BTRIM(raw_record ->> 'recipient_name'),
                ''
            ) AS recipient_name,

            NULLIF(
                BTRIM(raw_record ->> 'recipient_name_raw'),
                ''
            ) AS recipient_name_raw,

            NULLIF(
                BTRIM(raw_record ->> 'recipient_parent_uei'),
                ''
            ) AS recipient_parent_uei,

            NULLIF(
                BTRIM(raw_record ->> 'recipient_parent_name'),
                ''
            ) AS recipient_parent_name,

            NULLIF(
                BTRIM(raw_record ->> 'business_types_code'),
                ''
            ) AS business_types_code,

            NULLIF(
                BTRIM(
                    raw_record
                    ->> 'business_types_description'
                ),
                ''
            ) AS business_types_description,

            NULLIF(
                BTRIM(raw_record ->> 'recipient_country_code'),
                ''
            ) AS recipient_country_code,

            NULLIF(
                BTRIM(raw_record ->> 'recipient_state_code'),
                ''
            ) AS recipient_state_code,

            NULLIF(
                BTRIM(raw_record ->> 'recipient_city_name'),
                ''
            ) AS recipient_city_name,

            NULLIF(
                BTRIM(raw_record ->> 'recipient_zip_code'),
                ''
            ) AS recipient_zip_code,

            NULLIF(
                BTRIM(raw_record ->> 'recipient_address_line_1'),
                ''
            ) AS recipient_address_line_1

        FROM assistance.raw_award_transaction
        WHERE load_batch_id = %s
        ORDER BY source_row_number;
        """,
        (load_batch_id,),
    )

    observations: list[
        RecipientObservation
    ] = []

    for row in cur.fetchall():
        source_row_number = int(row[0])

        recipient_name = clean_optional_text(
            row[3]
        )

        if recipient_name is None:
            raise ValueError(
                f"Source row {source_row_number:,} "
                "has no recipient_name."
            )

        recipient_uei = clean_optional_text(
            row[2]
        )

        if recipient_uei is not None:
            recipient_uei = recipient_uei.upper()

        recipient_country_code = clean_optional_text(
            row[9]
        )
        recipient_state_code = clean_optional_text(
            row[10]
        )
        recipient_city_name = clean_optional_text(
            row[11]
        )
        recipient_zip_code = clean_optional_text(
            row[12]
        )
        recipient_address_line_1 = clean_optional_text(
            row[13]
        )
        business_types_code = clean_optional_text(
            row[7]
        )

        identity = classify_recipient_identity(
            RecipientIdentityInput(
                recipient_name=recipient_name,
                recipient_uei=recipient_uei,
                recipient_country_code=(
                    recipient_country_code
                ),
                recipient_state_code=(
                    recipient_state_code
                ),
                recipient_city_name=(
                    recipient_city_name
                ),
                recipient_zip_code=(
                    recipient_zip_code
                ),
                recipient_address_line_1=(
                    recipient_address_line_1
                ),
                business_types_code=(
                    business_types_code
                ),
            )
        )

        observations.append(
            RecipientObservation(
                source_row_number=source_row_number,
                assistance_award_unique_key=str(
                    row[1]
                ),
                recipient_uei=recipient_uei,
                recipient_name=recipient_name,
                recipient_name_raw=clean_optional_text(
                    row[4]
                ),
                recipient_parent_uei=(
                    clean_optional_text(row[5])
                ),
                recipient_parent_name=(
                    clean_optional_text(row[6])
                ),
                business_types_code=(
                    business_types_code
                ),
                business_types_description=(
                    clean_optional_text(row[8])
                ),
                recipient_country_code=(
                    recipient_country_code
                ),
                recipient_state_code=(
                    recipient_state_code
                ),
                recipient_city_name=(
                    recipient_city_name
                ),
                recipient_zip_code=(
                    recipient_zip_code
                ),
                recipient_address_line_1=(
                    recipient_address_line_1
                ),
                recipient_identity_key=(
                    identity.identity_key
                ),
                recipient_identity_type=(
                    identity.identity_type.value
                ),
                recipient_source_condition=(
                    identity.source_condition.value
                    if identity.source_condition
                    is not None
                    else None
                ),
            )
        )

    if len(observations) != raw_row_count:
        raise ValueError(
            "Recipient observation extraction did not reconcile: "
            f"raw={raw_row_count:,}, "
            f"observations={len(observations):,}."
        )

    return raw_row_count, observations

def observation_sort_key(
    observation: RecipientObservation,
) -> tuple[int, int, str, str]:
    """
    Deterministically order recipient observations.

    Selection precedence:
        1. latest source row;
        2. populated raw name;
        3. normalized recipient name;
        4. exact recipient name.
    """

    return (
        -observation.source_row_number,
        observation.recipient_name_raw is None,
        normalize_comparison_text(
            observation.recipient_name
        ),
        observation.recipient_name,
    )


def select_latest_non_null(
    observations: list[RecipientObservation],
    attribute: str,
):
    """Select the latest populated value for one attribute."""

    populated = [
        observation
        for observation in observations
        if getattr(observation, attribute) is not None
    ]

    if not populated:
        return None

    selection = select_canonical(
        populated,
        key=observation_sort_key,
    )

    return getattr(
        selection.selected,
        attribute,
    )


def build_canonical_recipients(
    observations: list[RecipientObservation],
) -> list[CanonicalRecipient]:
    """Aggregate source observations into canonical recipient identities."""

    grouped: dict[
        str,
        list[RecipientObservation],
    ] = defaultdict(list)

    for observation in observations:
        grouped[
            observation.recipient_identity_key
        ].append(observation)

    recipients: list[CanonicalRecipient] = []

    for identity_key in sorted(grouped):
        candidates = grouped[identity_key]

        selection = select_canonical(
            candidates,
            key=observation_sort_key,
        )

        selected = selection.selected

        identity_types = {
            item.recipient_identity_type
            for item in candidates
        }

        if len(identity_types) != 1:
            raise ValueError(
                f"Recipient identity key {identity_key!r} "
                "has multiple identity types: "
                f"{sorted(identity_types)!r}."
            )

        source_conditions = {
            item.recipient_source_condition
            for item in candidates
        }

        if len(source_conditions) != 1:
            raise ValueError(
                f"Recipient identity key {identity_key!r} "
                "has multiple source conditions: "
                f"{sorted(source_conditions)!r}."
            )

        observed_ueis = {
            item.recipient_uei
            for item in candidates
            if item.recipient_uei is not None
        }

        if len(observed_ueis) > 1:
            raise ValueError(
                f"Recipient identity key {identity_key!r} "
                "contains multiple UEIs: "
                f"{sorted(observed_ueis)!r}."
            )

        observed_names = {
            normalize_comparison_text(
                item.recipient_name
            )
            for item in candidates
        }

        if (
            selected.recipient_identity_type == "UEI"
            and len(observed_names) > 1
        ):
            raise ValueError(
                f"UEI identity {identity_key!r} contains "
                f"multiple normalized recipient names: "
                f"{sorted(observed_names)!r}."
            )

        parent_ueis = {
            item.recipient_parent_uei
            for item in candidates
            if item.recipient_parent_uei is not None
        }

        parent_names = {
            normalize_comparison_text(
                item.recipient_parent_name
            )
            for item in candidates
            if item.recipient_parent_name is not None
        }

        recipient_parent_uei = (
            select_latest_non_null(
                candidates,
                "recipient_parent_uei",
            )
        )

        recipient_parent_name = (
            select_latest_non_null(
                candidates,
                "recipient_parent_name",
            )
        )

        # Multiple parent observations are preserved in evidence.
        # The latest populated source value is selected canonically.
        _ = parent_ueis
        _ = parent_names

        recipient_type_code = (
            select_latest_non_null(
                candidates,
                "business_types_code",
            )
        )

        business_categories = (
            select_latest_non_null(
                candidates,
                "business_types_description",
            )
        )

        recipient_name = selected.recipient_name

        recipients.append(
            CanonicalRecipient(
                recipient_identity_key=identity_key,
                recipient_identity_type=(
                    selected.recipient_identity_type
                ),
                recipient_source_condition=(
                    selected.recipient_source_condition
                ),
                recipient_uei=selected.recipient_uei,
                recipient_name=recipient_name,
                recipient_name_normalized=(
                    normalize_comparison_text(
                        recipient_name
                    )
                ),
                recipient_parent_uei=(
                    recipient_parent_uei
                ),
                recipient_parent_name=(
                    recipient_parent_name
                ),
                recipient_type_code=(
                    recipient_type_code
                ),
                business_categories=(
                    business_categories
                ),
                observation_count=len(candidates),
                award_count=len(
                    {
                        item.assistance_award_unique_key
                        for item in candidates
                    }
                ),
                source_row_first=min(
                    item.source_row_number
                    for item in candidates
                ),
                source_row_last=max(
                    item.source_row_number
                    for item in candidates
                ),
                observations=tuple(
                    selection.ordered_candidates
                ),
            )
        )

    return recipients

def recipient_values(
    recipient: CanonicalRecipient,
) -> tuple[object, ...]:
    """Return the database values representing one canonical recipient."""

    return (
        recipient.recipient_uei,
        None,  # recipient_duns is absent in this Assistance extract.
        recipient.recipient_name,
        recipient.recipient_name_normalized,
        recipient.recipient_parent_uei,
        recipient.recipient_parent_name,
        recipient.recipient_type_code,
        recipient.business_categories,
        recipient.recipient_identity_key,
        recipient.recipient_identity_type,
        recipient.recipient_source_condition,
    )


def find_existing_recipient(
    cur,
    recipient: CanonicalRecipient,
):
    """
    Find an existing shared recipient safely.

    Matching precedence:
        1. exact recipient_identity_key;
        2. exact UEI for UEI-based identities;
        3. otherwise no existing match.

    Name-only matching is intentionally prohibited.
    """

    cur.execute(
        """
        SELECT
            recipient_id,
            recipient_uei,
            recipient_duns,
            recipient_name,
            recipient_name_normalized,
            recipient_parent_uei,
            recipient_parent_name,
            recipient_type_code,
            business_categories,
            recipient_identity_key,
            recipient_identity_type,
            recipient_source_condition
        FROM procurement.recipient
        WHERE recipient_identity_key = %s;
        """,
        (recipient.recipient_identity_key,),
    )

    existing = cur.fetchone()

    if existing is not None:
        return existing

    if (
        recipient.recipient_identity_type == "UEI"
        and recipient.recipient_uei is not None
    ):
        cur.execute(
            """
            SELECT
                recipient_id,
                recipient_uei,
                recipient_duns,
                recipient_name,
                recipient_name_normalized,
                recipient_parent_uei,
                recipient_parent_name,
                recipient_type_code,
                business_categories,
                recipient_identity_key,
                recipient_identity_type,
                recipient_source_condition
            FROM procurement.recipient
            WHERE UPPER(BTRIM(recipient_uei)) = %s
            ORDER BY recipient_id;
            """,
            (recipient.recipient_uei.upper(),),
        )

        matches = cur.fetchall()

        if len(matches) > 1:
            raise ValueError(
                f"UEI {recipient.recipient_uei!r} matches "
                f"{len(matches):,} existing shared recipients."
            )

        if matches:
            return matches[0]

    return None


def merge_optional_value(
    existing: object,
    proposed: object,
) -> object:
    """
    Preserve an existing populated value.

    A proposed value fills a null but does not silently overwrite
    an existing conflicting observation.
    """

    if existing is None:
        return proposed

    return existing


def upsert_recipients(
    cur,
    recipients: list[CanonicalRecipient],
) -> tuple[int, int, int, int, dict[str, int]]:
    """
    Insert or enrich shared recipients.

    Existing recipient names are preserved when populated.
    New identity metadata may be added to legacy Procurement rows.
    """

    inserted = 0
    updated = 0
    unchanged = 0
    conflicts = 0

    identity_to_recipient_id: dict[str, int] = {}

    for recipient in recipients:
        existing = find_existing_recipient(
            cur,
            recipient,
        )

        proposed = recipient_values(
            recipient
        )

        if existing is None:
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
                    business_categories,
                    recipient_identity_key,
                    recipient_identity_type,
                    recipient_source_condition
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                RETURNING recipient_id;
                """,
                proposed,
            )

            recipient_id = int(
                cur.fetchone()[0]
            )

            inserted += 1
            identity_to_recipient_id[
                recipient.recipient_identity_key
            ] = recipient_id
            continue

        recipient_id = int(existing[0])

        existing_values = existing[1:]

        # Identity metadata may safely enrich an existing legacy row.
        merged = (
            merge_optional_value(
                existing_values[0],
                recipient.recipient_uei,
            ),
            existing_values[1],  # Preserve existing DUNS.
            merge_optional_value(
                existing_values[2],
                recipient.recipient_name,
            ),
            merge_optional_value(
                existing_values[3],
                recipient.recipient_name_normalized,
            ),
            merge_optional_value(
                existing_values[4],
                recipient.recipient_parent_uei,
            ),
            merge_optional_value(
                existing_values[5],
                recipient.recipient_parent_name,
            ),
            merge_optional_value(
                existing_values[6],
                recipient.recipient_type_code,
            ),
            merge_optional_value(
                existing_values[7],
                recipient.business_categories,
            ),
            merge_optional_value(
                existing_values[8],
                recipient.recipient_identity_key,
            ),
            merge_optional_value(
                existing_values[9],
                recipient.recipient_identity_type,
            ),
            merge_optional_value(
                existing_values[10],
                recipient.recipient_source_condition,
            ),
        )

        existing_identity_key = existing_values[8]

        if (
            existing_identity_key is not None
            and existing_identity_key
            != recipient.recipient_identity_key
        ):
            conflicts += 1

            raise ValueError(
                f"Shared recipient {recipient_id} already has "
                f"identity key {existing_identity_key!r}, but "
                f"Assistance proposed "
                f"{recipient.recipient_identity_key!r}."
            )

        if merged == existing_values:
            unchanged += 1
        else:
            cur.execute(
                """
                UPDATE procurement.recipient
                SET
                    recipient_uei = %s,
                    recipient_duns = %s,
                    recipient_name = %s,
                    recipient_name_normalized = %s,
                    recipient_parent_uei = %s,
                    recipient_parent_name = %s,
                    recipient_type_code = %s,
                    business_categories = %s,
                    recipient_identity_key = %s,
                    recipient_identity_type = %s,
                    recipient_source_condition = %s
                WHERE recipient_id = %s;
                """,
                (
                    *merged,
                    recipient_id,
                ),
            )

            updated += 1

        identity_to_recipient_id[
            recipient.recipient_identity_key
        ] = recipient_id

    return (
        inserted,
        updated,
        unchanged,
        conflicts,
        identity_to_recipient_id,
    )

def validate_results(
    cur,
    *,
    recipients: list[CanonicalRecipient],
    identity_to_recipient_id: dict[str, int],
) -> dict[str, int]:
    """Validate canonical recipient representation."""

    expected_count = len(recipients)

    if len(identity_to_recipient_id) != expected_count:
        raise ValueError(
            "Recipient identity map did not reconcile: "
            f"expected={expected_count:,}, "
            f"mapped={len(identity_to_recipient_id):,}."
        )

    identity_keys = [
        recipient.recipient_identity_key
        for recipient in recipients
    ]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM procurement.recipient
        WHERE recipient_identity_key = ANY(%s);
        """,
        (identity_keys,),
    )

    represented_count = int(
        cur.fetchone()[0]
    )

    if represented_count != expected_count:
        raise ValueError(
            "Recipient representation validation failed: "
            f"expected={expected_count:,}, "
            f"represented={represented_count:,}."
        )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT recipient_identity_key
            FROM procurement.recipient
            WHERE recipient_identity_key = ANY(%s)
            GROUP BY recipient_identity_key
            HAVING COUNT(*) > 1
        ) AS duplicates;
        """,
        (identity_keys,),
    )

    duplicate_identity_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM procurement.recipient
        WHERE recipient_identity_key = ANY(%s)
          AND (
                recipient_name IS NULL
             OR BTRIM(recipient_name) = ''
             OR recipient_identity_type IS NULL
             OR BTRIM(recipient_identity_type) = ''
          );
        """,
        (identity_keys,),
    )

    invalid_required_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM procurement.recipient
        WHERE recipient_identity_key = ANY(%s)
          AND recipient_identity_type = 'UEI'
          AND (
                recipient_uei IS NULL
             OR BTRIM(recipient_uei) = ''
          );
        """,
        (identity_keys,),
    )

    uei_identity_without_uei_count = int(
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM procurement.recipient
        WHERE recipient_identity_key = ANY(%s)
          AND recipient_identity_type = 'SOURCE_CONDITION'
          AND recipient_source_condition IS NULL;
        """,
        (identity_keys,),
    )

    source_condition_without_code_count = int(
        cur.fetchone()[0]
    )

    if duplicate_identity_count:
        raise ValueError(
            f"Recipient validation found "
            f"{duplicate_identity_count:,} duplicate identity keys."
        )

    if invalid_required_count:
        raise ValueError(
            f"Recipient validation found "
            f"{invalid_required_count:,} invalid required values."
        )

    if uei_identity_without_uei_count:
        raise ValueError(
            f"Recipient validation found "
            f"{uei_identity_without_uei_count:,} UEI identities "
            "without populated UEIs."
        )

    if source_condition_without_code_count:
        raise ValueError(
            f"Recipient validation found "
            f"{source_condition_without_code_count:,} "
            "source-condition identities without condition codes."
        )

    identity_type_counts: dict[str, int] = {}

    cur.execute(
        """
        SELECT
            recipient_identity_type,
            COUNT(*)
        FROM procurement.recipient
        WHERE recipient_identity_key = ANY(%s)
        GROUP BY recipient_identity_type
        ORDER BY recipient_identity_type;
        """,
        (identity_keys,),
    )

    for identity_type, count in cur.fetchall():
        identity_type_counts[str(identity_type)] = int(count)

    return {
        "represented_count": represented_count,
        "duplicate_identity_count": duplicate_identity_count,
        "invalid_required_count": invalid_required_count,
        "uei_identity_without_uei_count": (
            uei_identity_without_uei_count
        ),
        "source_condition_without_code_count": (
            source_condition_without_code_count
        ),
        "uei_count": identity_type_counts.get("UEI", 0),
        "name_fingerprint_count": identity_type_counts.get(
            "NAME_FINGERPRINT",
            0,
        ),
        "source_condition_count": identity_type_counts.get(
            "SOURCE_CONDITION",
            0,
        ),
    }

def write_evidence(
    *,
    load_batch_id: int,
    raw_row_count: int,
    recipients: list[CanonicalRecipient],
    inserted: int,
    updated: int,
    unchanged: int,
    conflicts: int,
    validation: dict[str, int],
) -> Path:
    """Write deterministic Assistance recipient normalization evidence."""

    output_directory = (
        EVIDENCE_ROOT
        / f"batch_{load_batch_id:04d}"
        / "normalization"
        / "recipients"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory_file = (
        output_directory
        / "recipient_inventory.csv"
    )

    parent_conflict_file = (
        output_directory
        / "recipient_parent_conflicts.csv"
    )

    summary_file = (
        output_directory
        / "normalization_summary.txt"
    )

    with inventory_file.open(
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
                "recipient_identity_key",
                "recipient_identity_type",
                "recipient_source_condition",
                "recipient_uei",
                "recipient_name",
                "recipient_name_normalized",
                "recipient_parent_uei",
                "recipient_parent_name",
                "recipient_type_code",
                "business_categories",
                "observation_count",
                "award_count",
                "source_row_first",
                "source_row_last",
            ]
        )

        for recipient in recipients:
            writer.writerow(
                [
                    recipient.recipient_identity_key,
                    recipient.recipient_identity_type,
                    recipient.recipient_source_condition,
                    recipient.recipient_uei,
                    recipient.recipient_name,
                    recipient.recipient_name_normalized,
                    recipient.recipient_parent_uei,
                    recipient.recipient_parent_name,
                    recipient.recipient_type_code,
                    recipient.business_categories,
                    recipient.observation_count,
                    recipient.award_count,
                    recipient.source_row_first,
                    recipient.source_row_last,
                ]
            )

    parent_conflict_count = 0

    with parent_conflict_file.open(
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
                "recipient_identity_key",
                "recipient_uei",
                "recipient_name",
                "canonical_parent_uei",
                "canonical_parent_name",
                "observed_parent_uei",
                "observed_parent_name",
                "source_row_number",
                "selected_as_canonical",
            ]
        )

        for recipient in recipients:
            parent_pairs = {
                (
                    observation.recipient_parent_uei,
                    observation.recipient_parent_name,
                )
                for observation in recipient.observations
                if (
                    observation.recipient_parent_uei
                    is not None
                    or observation.recipient_parent_name
                    is not None
                )
            }

            if len(parent_pairs) <= 1:
                continue

            parent_conflict_count += 1

            for observation in recipient.observations:
                if (
                    observation.recipient_parent_uei
                    is None
                    and observation.recipient_parent_name
                    is None
                ):
                    continue

                selected_as_canonical = (
                    observation.recipient_parent_uei
                    == recipient.recipient_parent_uei
                    and observation.recipient_parent_name
                    == recipient.recipient_parent_name
                )

                writer.writerow(
                    [
                        recipient.recipient_identity_key,
                        recipient.recipient_uei,
                        recipient.recipient_name,
                        recipient.recipient_parent_uei,
                        recipient.recipient_parent_name,
                        observation.recipient_parent_uei,
                        observation.recipient_parent_name,
                        observation.source_row_number,
                        str(
                            selected_as_canonical
                        ).upper(),
                    ]
                )

    summary_lines = [
        "=" * 72,
        "ETL-005D.1 — ASSISTANCE RECIPIENT NORMALIZATION",
        "=" * 72,
        f"Load batch ID .................. {load_batch_id}",
        f"Raw observations examined ...... {raw_row_count:,}",
        f"Canonical recipient identities . {len(recipients):,}",
        f"UEI identities ................. {validation['uei_count']:,}",
        (
            "Name-fingerprint identities .... "
            f"{validation['name_fingerprint_count']:,}"
        ),
        (
            "Source-condition identities .... "
            f"{validation['source_condition_count']:,}"
        ),
        f"Recipients inserted ............ {inserted:,}",
        f"Recipients updated ............. {updated:,}",
        f"Recipients unchanged ........... {unchanged:,}",
        f"Identity conflicts ............. {conflicts:,}",
        f"Parent-conflict identities ..... {parent_conflict_count:,}",
        (
            "Duplicate identity keys ........ "
            f"{validation['duplicate_identity_count']:,}"
        ),
        (
            "Invalid required values ........ "
            f"{validation['invalid_required_count']:,}"
        ),
        "Validation ..................... PASS",
        "=" * 72,
        "",
        (
            "UEI identities use the authoritative source UEI."
        ),
        (
            "Named recipients without UEIs use deterministic "
            "source-derived fingerprints."
        ),
        (
            "PII-redacted and multiple-recipient values are modeled "
            "as source conditions, not asserted legal entities."
        ),
        (
            "Name-only matching to existing shared recipients is "
            "prohibited."
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
    print("ETL-005D.1 — Normalize Assistance Recipients")
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

            recipients = build_canonical_recipients(
                observations
            )

            (
                inserted,
                updated,
                unchanged,
                conflicts,
                identity_to_recipient_id,
            ) = upsert_recipients(
                cur,
                recipients,
            )

            validation = validate_results(
                cur,
                recipients=recipients,
                identity_to_recipient_id=(
                    identity_to_recipient_id
                ),
            )

        conn.commit()

        evidence_directory = write_evidence(
            load_batch_id=args.load_batch_id,
            raw_row_count=raw_row_count,
            recipients=recipients,
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            conflicts=conflicts,
            validation=validation,
        )

        print()
        print("=" * 72)
        print("ETL-005D.1 SUMMARY")
        print("=" * 72)
        print(
            "Raw observations examined ...... "
            f"{raw_row_count:,}"
        )
        print(
            "Canonical recipient identities . "
            f"{len(recipients):,}"
        )
        print(
            "UEI identities ................. "
            f"{validation['uei_count']:,}"
        )
        print(
            "Name-fingerprint identities .... "
            f"{validation['name_fingerprint_count']:,}"
        )
        print(
            "Source-condition identities .... "
            f"{validation['source_condition_count']:,}"
        )
        print(
            "Recipients inserted ............ "
            f"{inserted:,}"
        )
        print(
            "Recipients updated ............. "
            f"{updated:,}"
        )
        print(
            "Recipients unchanged ........... "
            f"{unchanged:,}"
        )
        print(
            "Identity conflicts ............. "
            f"{conflicts:,}"
        )
        print(
            "Duplicate identity keys ........ "
            f"{validation['duplicate_identity_count']:,}"
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
            "Assistance recipient normalization "
            "completed successfully."
        )

    except Exception as exc:
        conn.rollback()

        print()
        print(
            "Assistance recipient normalization failed."
        )
        print(f"{type(exc).__name__}: {exc}")

        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()

    
