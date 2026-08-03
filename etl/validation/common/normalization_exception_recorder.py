"""Record auditable normalization exceptions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from psycopg2.extras import Json


class NormalizationExceptionRecorder:
    """Persist deterministic normalization-exception records."""

    def record(
        self,
        conn,
        *,
        load_batch_id: int,
        entity_type: str,
        entity_key: str,
        anomaly_code: str,
        severity: str,
        source_row_numbers: Sequence[int],
        raw_values: Mapping[str, Any],
        normalized_action: Mapping[str, Any],
        message: str,
    ) -> None:
        """Insert or replace one exception record for an entity anomaly."""

        sql = """
            INSERT INTO procurement.normalization_exception (
                load_batch_id,
                entity_type,
                entity_key,
                anomaly_code,
                severity,
                source_row_numbers,
                raw_values,
                normalized_action,
                message
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (
                load_batch_id,
                entity_type,
                entity_key,
                anomaly_code
            )
            DO UPDATE SET
                severity = EXCLUDED.severity,
                source_row_numbers = EXCLUDED.source_row_numbers,
                raw_values = EXCLUDED.raw_values,
                normalized_action = EXCLUDED.normalized_action,
                message = EXCLUDED.message;
        """

        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    load_batch_id,
                    entity_type,
                    entity_key,
                    anomaly_code,
                    severity,
                    list(source_row_numbers),
                    Json(dict(raw_values)),
                    Json(dict(normalized_action)),
                    message,
                ),
            )