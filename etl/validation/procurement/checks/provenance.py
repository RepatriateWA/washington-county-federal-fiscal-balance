"""Procurement normalization-provenance certification checks."""

from __future__ import annotations

from etl.validation.procurement.models import (
    CertificationCheck,
    CheckStatus,
)
from etl.validation.procurement.query import scalar_query


def check_normalization_exception_keys_unique(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    duplicate_groups = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    entity_type,
                    entity_key,
                    anomaly_code
                FROM procurement.normalization_exception
                WHERE load_batch_id = %s
                GROUP BY
                    entity_type,
                    entity_key,
                    anomaly_code
                HAVING COUNT(*) > 1
            ) AS duplicates;
            """,
            (load_batch_id,),
        )
    )

    status = (
        CheckStatus.PASS
        if duplicate_groups == 0
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="PROV-001",
        section="NORMALIZATION PROVENANCE",
        label="Normalization exception keys are unique",
        status=status,
        observed_value=duplicate_groups,
        expected_value=0,
        detail=(
            None
            if duplicate_groups == 0
            else (
                f"{duplicate_groups} duplicate normalization-"
                "exception key groups were found."
            )
        ),
    )


def check_exception_source_rows_resolve(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    unresolved_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.normalization_exception AS exception
            CROSS JOIN LATERAL
                UNNEST(exception.source_row_numbers)
                AS rows(source_row_number)
            LEFT JOIN procurement.raw_award_transaction AS raw
                ON raw.load_batch_id = exception.load_batch_id
                AND raw.source_row_number = rows.source_row_number
            WHERE exception.load_batch_id = %s
              AND raw.raw_award_transaction_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    status = (
        CheckStatus.PASS
        if unresolved_count == 0
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="PROV-002",
        section="NORMALIZATION PROVENANCE",
        label="Exception source rows resolve",
        status=status,
        observed_value=unresolved_count,
        expected_value=0,
        detail=(
            None
            if unresolved_count == 0
            else (
                f"{unresolved_count} exception source-row "
                "references do not resolve."
            )
        ),
    )


def check_naics_aliases_reconcile(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    cur.execute(
        """
        SELECT
            COUNT(*) AS alias_rows,
            COALESCE(SUM(alias.occurrence_count), 0)
                AS alias_occurrences,
            (
                SELECT COUNT(*)
                FROM procurement.raw_award_transaction AS raw
                WHERE raw.load_batch_id = %s
                  AND NULLIF(
                      BTRIM(raw.raw_record ->> 'naics_code'),
                      ''
                  ) IS NOT NULL
                  AND NULLIF(
                      BTRIM(raw.raw_record ->> 'naics_description'),
                      ''
                  ) IS NOT NULL
            ) AS source_occurrences
        FROM procurement.naics_alias AS alias
        WHERE alias.load_batch_id = %s;
        """,
        (
            load_batch_id,
            load_batch_id,
        ),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "NAICS alias reconciliation returned no result."
        )

    alias_rows = int(row[0])
    alias_occurrences = int(row[1])
    source_occurrences = int(row[2])

    status = (
        CheckStatus.PASS
        if alias_rows > 0
        and alias_occurrences == source_occurrences
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="PROV-003",
        section="NORMALIZATION PROVENANCE",
        label="NAICS aliases reconcile",
        status=status,
        observed_value=(
            f"{alias_occurrences}/{source_occurrences}"
        ),
        expected_value="all described source occurrences",
        detail=(
            None
            if status == CheckStatus.PASS
            else (
                f"{alias_rows} alias rows represent "
                f"{alias_occurrences} occurrences, while the "
                f"source contains {source_occurrences}."
            )
        ),
        evidence={
            "alias_rows": alias_rows,
            "alias_occurrences": alias_occurrences,
            "source_occurrences": source_occurrences,
        },
    )


def check_psc_aliases_reconcile(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    cur.execute(
        """
        SELECT
            COUNT(*) AS alias_rows,
            COALESCE(SUM(alias.occurrence_count), 0)
                AS alias_occurrences,
            (
                SELECT COUNT(*)
                FROM procurement.raw_award_transaction AS raw
                WHERE raw.load_batch_id = %s
                  AND NULLIF(
                      BTRIM(raw.raw_record ->> 'product_or_service_code'),
                      ''
                  ) IS NOT NULL
                  AND NULLIF(
                      BTRIM(
                          raw.raw_record
                          ->> 'product_or_service_code_description'
                      ),
                      ''
                  ) IS NOT NULL
            ) AS source_occurrences
        FROM procurement.psc_alias AS alias
        WHERE alias.load_batch_id = %s;
        """,
        (
            load_batch_id,
            load_batch_id,
        ),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "PSC alias reconciliation returned no result."
        )

    alias_rows = int(row[0])
    alias_occurrences = int(row[1])
    source_occurrences = int(row[2])

    status = (
        CheckStatus.PASS
        if alias_rows > 0
        and alias_occurrences == source_occurrences
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="PROV-004",
        section="NORMALIZATION PROVENANCE",
        label="PSC aliases reconcile",
        status=status,
        observed_value=(
            f"{alias_occurrences}/{source_occurrences}"
        ),
        expected_value="all described source occurrences",
        detail=(
            None
            if status == CheckStatus.PASS
            else (
                f"{alias_rows} alias rows represent "
                f"{alias_occurrences} occurrences, while the "
                f"source contains {source_occurrences}."
            )
        ),
        evidence={
            "alias_rows": alias_rows,
            "alias_occurrences": alias_occurrences,
            "source_occurrences": source_occurrences,
        },
    )


def check_recipient_history_warnings(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    warning_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.normalization_exception
            WHERE load_batch_id = %s
              AND anomaly_code = 'RECIPIENT_UEI_ALIAS'
              AND severity = 'WARNING';
            """,
            (load_batch_id,),
        )
    )

    status = (
        CheckStatus.WARN
        if warning_count > 0
        else CheckStatus.PASS
    )

    return CertificationCheck(
        check_code="PROV-005",
        section="NORMALIZATION PROVENANCE",
        label="Award recipient-history warnings",
        status=status,
        observed_value=warning_count,
        expected_value=0,
        detail=(
            None
            if warning_count == 0
            else (
                f"{warning_count} awards contain multiple observed "
                "recipient UEIs. The relationships are preserved and "
                "canonical recipients were selected deterministically."
            )
        ),
        evidence={
            "warning_count": warning_count,
        },
    )


PROVENANCE_CHECKS = (
    check_normalization_exception_keys_unique,
    check_exception_source_rows_resolve,
    check_naics_aliases_reconcile,
    check_psc_aliases_reconcile,
    check_recipient_history_warnings,
)