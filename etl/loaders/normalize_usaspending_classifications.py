"""
ETL-004A.3C — Normalize USAspending NAICS and PSC classifications.
"""

import argparse
from collections import defaultdict
from datetime import date
from typing import Any

from etl.common.db import get_connection
from etl.common.usaspending import get_optional, parse_date
from etl.validation.common.classification_alias_recorder import (
    ClassificationAlias,
    ClassificationAliasRecorder,
)
from etl.validation.common.normalization_exception_recorder import (
    NormalizationExceptionRecorder,
)

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize USAspending NAICS and PSC classifications."
    )
    parser.add_argument("--load-batch-id", type=int, default=None)
    return parser.parse_args()


def get_target_load_batch_id(conn, requested_batch_id: int | None) -> int:
    with conn.cursor() as cur:
        if requested_batch_id is not None:
            cur.execute(
                """
                SELECT lb.load_batch_id, lb.load_status,
                       COUNT(raw.raw_award_transaction_id)
                FROM procurement.load_batch lb
                LEFT JOIN procurement.raw_award_transaction raw
                  ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_batch_id = %s
                GROUP BY lb.load_batch_id, lb.load_status;
                """,
                (requested_batch_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Load batch {requested_batch_id} does not exist.")

            load_batch_id, load_status, raw_rows = row
            if load_status not in {"COMPLETED", "COMPLETED_WITH_REJECTIONS"}:
                raise ValueError(
                    f"Load batch {load_batch_id} has status {load_status!r}."
                )
            if raw_rows == 0:
                raise ValueError(f"Load batch {load_batch_id} contains no raw rows.")
            return int(load_batch_id)

        cur.execute(
            """
            SELECT raw.load_batch_id
            FROM procurement.raw_award_transaction raw
            JOIN procurement.load_batch lb
              ON lb.load_batch_id = raw.load_batch_id
            WHERE lb.load_status IN ('COMPLETED', 'COMPLETED_WITH_REJECTIONS')
            GROUP BY raw.load_batch_id
            ORDER BY raw.load_batch_id DESC
            LIMIT 1;
            """
        )
        row = cur.fetchone()

    if row is None:
        raise ValueError("No completed raw procurement load batch was found.")
    return int(row[0])


def read_raw_records(conn, load_batch_id: int) -> list[tuple[int, dict[str, Any]]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_row_number, raw_record
            FROM procurement.raw_award_transaction
            WHERE load_batch_id = %s
            ORDER BY source_row_number, raw_award_transaction_id;
            """,
            (load_batch_id,),
        )
        return [(int(row_number), record) for row_number, record in cur.fetchall()]

def _observation_sort_key(
    observation: tuple[int, date | None],
) -> tuple[date, int]:
    """Return a deterministic recency key."""
    row_number, action_date = observation

    return (
        action_date or date.min,
        row_number,
    )


def _build_aliases(
    observations: dict[
        tuple[str, str],
        list[tuple[int, date | None]],
    ],
) -> list[ClassificationAlias]:
    """Convert source observations into batch-level aliases."""
    aliases: list[ClassificationAlias] = []

    for code, description in sorted(observations):
        source_rows = sorted(
            row_number
            for row_number, _action_date
            in observations[(code, description)]
        )

        aliases.append(
            ClassificationAlias(
                code=code,
                observed_description=description,
                occurrence_count=len(source_rows),
                first_source_row_number=source_rows[0],
                last_source_row_number=source_rows[-1],
            )
        )

    return aliases

def _select_canonical_descriptions(
    *,
    observations: dict[
        tuple[str, str],
        list[tuple[int, date | None]],
    ],
    load_batch_id: int,
    entity_type: str,
) -> tuple[
    dict[str, str],
    list[dict[str, Any]],
]:
    """Select canonical descriptions and report conflicts."""
    descriptions_by_code: dict[
        str,
        dict[str, list[tuple[int, date | None]]],
    ] = defaultdict(dict)

    for (code, description), values in observations.items():
        descriptions_by_code[code][description] = values

    canonical: dict[str, str] = {}
    anomalies: list[dict[str, Any]] = []

    for code in sorted(descriptions_by_code):
        descriptions = descriptions_by_code[code]

        selected_description = max(
            descriptions,
            key=lambda description: max(
                (
                    _observation_sort_key(observation)
                    for observation
                    in descriptions[description]
                ),
                default=(date.min, 0),
            ),
        )

        canonical[code] = selected_description

        if len(descriptions) <= 1:
            continue

        observed_descriptions = []

        all_source_rows: list[int] = []

        for description in sorted(descriptions):
            values = descriptions[description]

            source_rows = sorted(
                row_number
                for row_number, _action_date in values
            )

            action_dates = sorted(
                {
                    action_date.isoformat()
                    for _row_number, action_date in values
                    if action_date is not None
                }
            )

            all_source_rows.extend(source_rows)

            observed_descriptions.append(
                {
                    "description": description,
                    "occurrence_count": len(values),
                    "first_source_row_number": (
                        source_rows[0]
                    ),
                    "last_source_row_number": (
                        source_rows[-1]
                    ),
                    "action_dates": action_dates,
                }
            )

        anomalies.append(
            {
                "load_batch_id": load_batch_id,
                "entity_type": entity_type,
                "entity_key": code,
                "anomaly_code": (
                    "DESCRIPTION_ALIAS"
                ),
                "severity": "WARNING",
                "source_row_numbers": sorted(
                    set(all_source_rows)
                ),
                "raw_values": {
                    "observed_descriptions": (
                        observed_descriptions
                    ),
                },
                "normalized_action": {
                    "canonical_description": (
                        selected_description
                    ),
                    "selection_rule": (
                        "Select the description from the "
                        "latest action date, breaking ties "
                        "with the highest source-row number."
                    ),
                },
                "message": (
                    f"Multiple descriptions were observed "
                    f"for {entity_type.upper()} code "
                    f"{code!r}. Every description was "
                    f"preserved as an alias and the most "
                    f"recent observation was selected as "
                    f"canonical."
                ),
            }
        )

    return canonical, anomalies

def derive_classifications(
    raw_rows: list[tuple[int, dict[str, Any]]],
    *,
    load_batch_id: int,
) -> tuple[
    dict[str, str],
    dict[str, str | None],
    list[ClassificationAlias],
    list[ClassificationAlias],
    list[dict[str, Any]],
]:
    """
    Derive canonical classifications, observed aliases, and anomalies.

    Canonical-description policy:
    - select the description from the latest observed action date;
    - break equal-date ties with the highest source-row number;
    - preserve every exact observed code-description pair as an alias;
    - report codes with multiple descriptions as warnings.
    """
    naics_codes_seen: set[str] = set()
    psc_codes_seen: set[str] = set()

    naics_observations: dict[
        tuple[str, str],
        list[tuple[int, date | None]],
    ] = defaultdict(list)

    psc_observations: dict[
        tuple[str, str],
        list[tuple[int, date | None]],
    ] = defaultdict(list)

    for row_number, record in raw_rows:
        raw_action_date = get_optional(record, "ACTION_DATE")

        try:
            action_date = parse_date(raw_action_date)
        except ValueError as exc:
            raise ValueError(
                f"Invalid action date at source row "
                f"{row_number}: {raw_action_date!r}."
            ) from exc

        naics_code = get_optional(record, "NAICS")
        naics_description = get_optional(
            record,
            "NAICS_DESCRIPTION",
        )

        if naics_code is not None:
            if (
                not naics_code.isdigit()
                or not 2 <= len(naics_code) <= 6
            ):
                raise ValueError(
                    f"Invalid NAICS code {naics_code!r} "
                    f"at source row {row_number}."
                )

            naics_codes_seen.add(naics_code)

            if naics_description is not None:
                naics_observations[
                    (naics_code, naics_description)
                ].append((row_number, action_date))

        psc_code = get_optional(record, "PSC")
        psc_description = get_optional(
            record,
            "PSC_DESCRIPTION",
        )

        if psc_code is not None:
            psc_codes_seen.add(psc_code)

            if psc_description is not None:
                psc_observations[
                    (psc_code, psc_description)
                ].append((row_number, action_date))

    unresolved_naics = sorted(
        naics_codes_seen
        - {
            code
            for code, _description
            in naics_observations
        }
    )

    if unresolved_naics:
        raise ValueError(
            "The following NAICS codes have no description "
            "anywhere in the source batch: "
            + ", ".join(unresolved_naics)
        )

    naics_aliases = _build_aliases(
        naics_observations
    )

    psc_aliases = _build_aliases(
        psc_observations
    )

    naics, naics_anomalies = _select_canonical_descriptions(
        observations=naics_observations,
        load_batch_id=load_batch_id,
        entity_type="naics",
    )

    psc, psc_anomalies = _select_canonical_descriptions(
        observations=psc_observations,
        load_batch_id=load_batch_id,
        entity_type="psc",
    )

    for psc_code in sorted(psc_codes_seen):
        psc.setdefault(psc_code, None)

    anomalies = sorted(
        naics_anomalies + psc_anomalies,
        key=lambda item: (
            item["entity_type"],
            item["entity_key"],
            item["anomaly_code"],
        ),
    )

    return (
        naics,
        psc,
        naics_aliases,
        psc_aliases,
        anomalies,
    )

def upsert_naics(conn, rows: dict[str, str]) -> tuple[int, int]:
    sql = """
        INSERT INTO procurement.naics (
            naics_code, naics_description, naics_year
        )
        VALUES (%s, %s, NULL)
        ON CONFLICT (naics_code)
        DO UPDATE SET naics_description = EXCLUDED.naics_description
        RETURNING (xmax = 0) AS inserted;
    """
    inserted = updated = 0
    with conn.cursor() as cur:
        for code in sorted(rows):
            cur.execute(sql, (code, rows[code]))
            if bool(cur.fetchone()[0]):
                inserted += 1
            else:
                updated += 1
    return inserted, updated


def upsert_psc(conn, rows: dict[str, str | None]) -> tuple[int, int]:
    sql = """
        INSERT INTO procurement.psc (
            psc_code, psc_description, product_or_service
        )
        VALUES (%s, %s, NULL)
        ON CONFLICT (psc_code)
        DO UPDATE SET
            psc_description = COALESCE(
                EXCLUDED.psc_description,
                procurement.psc.psc_description
            )
        RETURNING (xmax = 0) AS inserted;
    """
    inserted = updated = 0
    with conn.cursor() as cur:
        for code in sorted(rows):
            cur.execute(sql, (code, rows[code]))
            if bool(cur.fetchone()[0]):
                inserted += 1
            else:
                updated += 1
    return inserted, updated

def record_aliases(
    conn,
    *,
    load_batch_id: int,
    naics_aliases: list[ClassificationAlias],
    psc_aliases: list[ClassificationAlias],
) -> tuple[int, int]:
    """Persist observed classification descriptions."""
    recorder = ClassificationAliasRecorder()

    naics_count = recorder.record_naics(
        conn,
        load_batch_id=load_batch_id,
        aliases=naics_aliases,
    )

    psc_count = recorder.record_psc(
        conn,
        load_batch_id=load_batch_id,
        aliases=psc_aliases,
    )

    return naics_count, psc_count


def record_classification_exceptions(
    conn,
    *,
    anomalies: list[dict[str, Any]],
) -> int:
    """Persist classification-description conflicts."""
    recorder = NormalizationExceptionRecorder()

    for anomaly in anomalies:
        recorder.record(
            conn,
            load_batch_id=anomaly["load_batch_id"],
            entity_type=anomaly["entity_type"],
            entity_key=anomaly["entity_key"],
            anomaly_code=anomaly["anomaly_code"],
            severity=anomaly["severity"],
            source_row_numbers=(
                anomaly["source_row_numbers"]
            ),
            raw_values=anomaly["raw_values"],
            normalized_action=(
                anomaly["normalized_action"]
            ),
            message=anomaly["message"],
        )

    return len(anomalies)

def validate(conn, naics: dict[str, str], psc: dict[str, str | None]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT naics_code FROM procurement.naics WHERE naics_code = ANY(%s);",
            (list(naics),),
        )
        loaded_naics = {row[0] for row in cur.fetchall()}

        cur.execute(
            "SELECT psc_code FROM procurement.psc WHERE psc_code = ANY(%s);",
            (list(psc),),
        )
        loaded_psc = {row[0] for row in cur.fetchall()}

    missing_naics = set(naics) - loaded_naics
    missing_psc = set(psc) - loaded_psc

    if missing_naics:
        raise ValueError("Missing NAICS codes: " + ", ".join(sorted(missing_naics)))
    if missing_psc:
        raise ValueError("Missing PSC codes: " + ", ".join(sorted(missing_psc)))


def main() -> None:
    args = parse_arguments()
    print("=" * 68)
    print("ETL-004A.3C — Normalize USAspending Classifications")
    print("=" * 68)

    conn = get_connection()
    try:
        batch_id = get_target_load_batch_id(conn, args.load_batch_id)
        print(f"Target raw load batch: {batch_id}")

        raw_rows = read_raw_records(conn, batch_id)
        print(f"Raw observations read: {len(raw_rows):,}")

        (
            naics,
            psc,
            naics_aliases,
            psc_aliases,
            anomalies,
        ) = derive_classifications(
            raw_rows,
            load_batch_id=batch_id,
        )

        print(
            f"Distinct NAICS codes derived: "
            f"{len(naics):,}"
        )
        print(
            f"Distinct PSC codes derived: "
            f"{len(psc):,}"
        )
        print(
            f"NAICS aliases derived: "
            f"{len(naics_aliases):,}"
        )
        print(
            f"PSC aliases derived: "
            f"{len(psc_aliases):,}"
        )
        print(
            f"Description conflicts detected: "
            f"{len(anomalies):,}"
        )

        ni, nu = upsert_naics(conn, naics)
        pi, pu = upsert_psc(conn, psc)

        naics_alias_count, psc_alias_count = record_aliases(
            conn,
            load_batch_id=batch_id,
            naics_aliases=naics_aliases,
            psc_aliases=psc_aliases,
        )

        exception_count = record_classification_exceptions(
            conn,
            anomalies=anomalies,
        )

        validate(conn, naics, psc)
        conn.commit()

        print(f"NAICS inserted: {ni:,}")
        print(f"NAICS updated: {nu:,}")
        print(f"PSC inserted: {pi:,}")
        print(f"PSC updated: {pu:,}")

        print(
            f"NAICS aliases recorded: "
            f"{naics_alias_count:,}"
        )

        print(
            f"PSC aliases recorded: "
            f"{psc_alias_count:,}"
        )
        print(
            f"Normalization exceptions recorded: "
            f"{exception_count:,}"
        )   

        print("Classification validation: PASS")
        print("ETL-004A.3C completed successfully.")

    except Exception as exc:
        conn.rollback()
        print("ETL-004A.3C failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    finally:
        conn.close()


if __name__ == "__main__":
    main()