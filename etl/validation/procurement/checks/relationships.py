"""
Procurement award-relationship completeness checks.
"""

from __future__ import annotations

from etl.validation.procurement.models import (
    CertificationCheck,
    CheckStatus,
)


def check_relationship_completeness(
    cur,
    load_batch_id: int,
    *,
    check_code: str,
    label: str,
    relationship_column: str,
) -> CertificationCheck:
    allowed_columns = {
        "recipient_id",
        "awarding_agency_id",
        "awarding_subagency_id",
        "funding_agency_id",
        "funding_subagency_id",
    }

    if relationship_column not in allowed_columns:
        raise ValueError(
            f"Unsupported relationship column: "
            f"{relationship_column!r}"
        )

    cur.execute(
        f"""
        SELECT
            COUNT(*) AS award_count,
            COUNT(aw.{relationship_column}) AS resolved_count
        FROM (
            SELECT DISTINCT award_id
            FROM procurement.award_transaction
            WHERE load_batch_id = %s
        ) AS batch_awards
        JOIN procurement.award AS aw
          ON aw.award_id = batch_awards.award_id;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            f"Completeness query for {relationship_column} "
            "returned no result."
        )

    award_count = int(row[0])
    resolved_count = int(row[1])

    completeness = (
        resolved_count / award_count * 100
        if award_count > 0
        else 0.0
    )

    status = (
        CheckStatus.PASS
        if award_count > 0 and resolved_count == award_count
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code=check_code,
        section="RELATIONSHIP COMPLETENESS",
        label=label,
        status=status,
        observed_value=(
            f"{resolved_count}/{award_count} "
            f"({completeness:.2f}%)"
        ),
        expected_value="100.00%",
        detail=(
            None
            if status == CheckStatus.PASS
            else (
                f"{award_count - resolved_count} of "
                f"{award_count} awards lack this relationship."
            )
        ),
    )


def check_recipient_completeness(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    return check_relationship_completeness(
        cur,
        load_batch_id,
        check_code="REL-001",
        label="Recipient relationships complete",
        relationship_column="recipient_id",
    )


def check_awarding_agency_completeness(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    return check_relationship_completeness(
        cur,
        load_batch_id,
        check_code="REL-002",
        label="Awarding-agency relationships complete",
        relationship_column="awarding_agency_id",
    )


def check_awarding_subagency_completeness(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    return check_relationship_completeness(
        cur,
        load_batch_id,
        check_code="REL-003",
        label="Awarding-subagency relationships complete",
        relationship_column="awarding_subagency_id",
    )


def check_funding_agency_completeness(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    return check_relationship_completeness(
        cur,
        load_batch_id,
        check_code="REL-004",
        label="Funding-agency relationships complete",
        relationship_column="funding_agency_id",
    )


def check_funding_subagency_completeness(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    return check_relationship_completeness(
        cur,
        load_batch_id,
        check_code="REL-005",
        label="Funding-subagency relationships complete",
        relationship_column="funding_subagency_id",
    )


RELATIONSHIP_CHECKS = (
    check_recipient_completeness,
    check_awarding_agency_completeness,
    check_awarding_subagency_completeness,
    check_funding_agency_completeness,
    check_funding_subagency_completeness,
)