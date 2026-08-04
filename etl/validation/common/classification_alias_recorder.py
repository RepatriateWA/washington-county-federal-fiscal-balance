"""Persist observed classification descriptions by source batch."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassificationAlias:
    """One observed code-description pair within a load batch."""

    code: str
    observed_description: str
    occurrence_count: int
    first_source_row_number: int | None
    last_source_row_number: int | None


class ClassificationAliasRecorder:
    """Persist NAICS and PSC aliases idempotently."""

    def record_naics(
        self,
        conn,
        *,
        load_batch_id: int,
        aliases: list[ClassificationAlias],
    ) -> int:
        """Upsert NAICS aliases for one source batch."""
        return self._record(
            conn,
            table_name="naics_alias",
            code_column="naics_code",
            load_batch_id=load_batch_id,
            aliases=aliases,
        )

    def record_psc(
        self,
        conn,
        *,
        load_batch_id: int,
        aliases: list[ClassificationAlias],
    ) -> int:
        """Upsert PSC aliases for one source batch."""
        return self._record(
            conn,
            table_name="psc_alias",
            code_column="psc_code",
            load_batch_id=load_batch_id,
            aliases=aliases,
        )

    def _record(
        self,
        conn,
        *,
        table_name: str,
        code_column: str,
        load_batch_id: int,
        aliases: list[ClassificationAlias],
    ) -> int:
        sql = f"""
            INSERT INTO procurement.{table_name} (
                load_batch_id,
                {code_column},
                observed_description,
                occurrence_count,
                first_source_row_number,
                last_source_row_number
            )
            VALUES (
                %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (
                load_batch_id,
                {code_column},
                observed_description
            )
            DO UPDATE SET
                occurrence_count = EXCLUDED.occurrence_count,
                first_source_row_number =
                    EXCLUDED.first_source_row_number,
                last_source_row_number =
                    EXCLUDED.last_source_row_number,
                updated_at = CURRENT_TIMESTAMP;
        """

        with conn.cursor() as cur:
            for alias in sorted(
                aliases,
                key=lambda item: (
                    item.code,
                    item.observed_description,
                ),
            ):
                cur.execute(
                    sql,
                    (
                        load_batch_id,
                        alias.code,
                        alias.observed_description,
                        alias.occurrence_count,
                        alias.first_source_row_number,
                        alias.last_source_row_number,
                    ),
                )

        return len(aliases)