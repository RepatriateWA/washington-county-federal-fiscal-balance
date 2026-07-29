"""
Procurement batch-completeness certification checks.
"""

from __future__ import annotations

from etl.validation.procurement.models import (
    CertificationCheck,
    CheckStatus,
)
from etl.validation.procurement.query import scalar_query


def check_raw_observations_exist(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.raw_award_transaction
            WHERE load_batch_id = %s;
            """,
            (load_batch_id,),
        )
    )

    status = (
        CheckStatus.PASS
        if count > 0
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="COUNT-001",
        section="BATCH COMPLETENESS",
        label="Raw observations exist",
        status=status,
        observed_value=count,
        expected_value="greater than 0",
        detail=(
            None
            if count > 0
            else "The batch contains no raw procurement observations."
        ),
    )


def check_transactions_exist(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.award_transaction
            WHERE load_batch_id = %s;
            """,
            (load_batch_id,),
        )
    )

    status = (
        CheckStatus.PASS
        if count > 0
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="COUNT-002",
        section="BATCH COMPLETENESS",
        label="Normalized transactions exist",
        status=status,
        observed_value=count,
        expected_value="greater than 0",
        detail=(
            None
            if count > 0
            else "The batch contains no normalized transactions."
        ),
    )


def check_awards_exist(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(DISTINCT award_id)
            FROM procurement.award_transaction
            WHERE load_batch_id = %s;
            """,
            (load_batch_id,),
        )
    )

    status = (
        CheckStatus.PASS
        if count > 0
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="COUNT-003",
        section="BATCH COMPLETENESS",
        label="Normalized awards represented",
        status=status,
        observed_value=count,
        expected_value="greater than 0",
        detail=(
            None
            if count > 0
            else "No normalized awards are represented in the batch."
        ),
    )


def check_raw_transaction_count_reconciliation(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    cur.execute(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM procurement.raw_award_transaction
                WHERE load_batch_id = %s
            ) AS raw_count,
            (
                SELECT COUNT(*)
                FROM procurement.award_transaction
                WHERE load_batch_id = %s
            ) AS transaction_count;
        """,
        (
            load_batch_id,
            load_batch_id,
        ),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Count-reconciliation query returned no result."
        )

    raw_count = int(row[0])
    transaction_count = int(row[1])

    status = (
        CheckStatus.PASS
        if raw_count == transaction_count and raw_count > 0
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="COUNT-004",
        section="BATCH COMPLETENESS",
        label="Raw and normalized counts reconcile",
        status=status,
        observed_value=transaction_count,
        expected_value=raw_count,
        detail=(
            None
            if status == CheckStatus.PASS
            else (
                f"Raw count is {raw_count}; normalized transaction "
                f"count is {transaction_count}."
            )
        ),
    )


BATCH_CHECKS = (
    check_raw_observations_exist,
    check_transactions_exist,
    check_awards_exist,
    check_raw_transaction_count_reconciliation,
)