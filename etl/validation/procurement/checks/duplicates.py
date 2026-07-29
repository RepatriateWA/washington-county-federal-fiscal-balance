"""
Procurement duplicate-detection certification checks.
"""

from __future__ import annotations

from etl.validation.procurement.models import (
    CertificationCheck,
    CheckStatus,
)
from etl.validation.procurement.query import scalar_query


def check_raw_source_rows_unique(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    duplicate_groups = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT source_row_number
                FROM procurement.raw_award_transaction
                WHERE load_batch_id = %s
                GROUP BY source_row_number
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
        check_code="DUP-001",
        section="DUPLICATE DETECTION",
        label="Raw source-row identifiers are unique",
        status=status,
        observed_value=duplicate_groups,
        expected_value=0,
        detail=(
            None
            if duplicate_groups == 0
            else (
                f"{duplicate_groups} duplicated raw source-row "
                "identifier groups were found."
            )
        ),
    )


def check_transaction_source_rows_unique(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    duplicate_groups = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT source_row_number
                FROM procurement.award_transaction
                WHERE load_batch_id = %s
                GROUP BY source_row_number
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
        check_code="DUP-002",
        section="DUPLICATE DETECTION",
        label="Transaction source-row identifiers are unique",
        status=status,
        observed_value=duplicate_groups,
        expected_value=0,
        detail=(
            None
            if duplicate_groups == 0
            else (
                f"{duplicate_groups} duplicated normalized "
                "source-row identifier groups were found."
            )
        ),
    )


DUPLICATE_CHECKS = (
    check_raw_source_rows_unique,
    check_transaction_source_rows_unique,
)