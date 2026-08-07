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


def check_award_recipient_history_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    cur.execute(
        """
        SELECT
            COUNT(*) AS relationship_count,
            COUNT(*) FILTER (
                WHERE aw.award_id IS NULL
                   OR recipient.recipient_id IS NULL
            ) AS orphan_count
        FROM procurement.award_recipient_relationship AS rel
        LEFT JOIN procurement.award AS aw
          ON aw.award_id = rel.award_id
        LEFT JOIN procurement.recipient AS recipient
          ON recipient.recipient_id = rel.recipient_id
        WHERE rel.load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Award-recipient history query returned no result."
        )

    relationship_count = int(row[0])
    orphan_count = int(row[1])

    status = (
        CheckStatus.PASS
        if relationship_count > 0 and orphan_count == 0
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="REL-006",
        section="RELATIONSHIP COMPLETENESS",
        label="Award-recipient history resolves",
        status=status,
        observed_value=(
            f"{relationship_count - orphan_count}/"
            f"{relationship_count}"
        ),
        expected_value="all relationships",
        detail=(
            None
            if status == CheckStatus.PASS
            else (
                f"{orphan_count} award-recipient history rows "
                "contain unresolved references."
            )
        ),
        evidence={
            "relationship_count": relationship_count,
            "orphan_count": orphan_count,
        },
    )


def check_recipient_parent_history_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    cur.execute(
        """
        SELECT
            COUNT(*) AS relationship_count,
            COUNT(*) FILTER (
                WHERE recipient.recipient_id IS NULL
            ) AS unresolved_recipient_count
        FROM procurement.recipient_parent_relationship AS rel
        LEFT JOIN procurement.recipient AS recipient
          ON recipient.recipient_uei = rel.recipient_uei
        WHERE rel.load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Recipient-parent history query returned no result."
        )

    relationship_count = int(row[0])
    unresolved_count = int(row[1])

    status = (
        CheckStatus.PASS
        if relationship_count > 0 and unresolved_count == 0
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="REL-007",
        section="RELATIONSHIP COMPLETENESS",
        label="Recipient-parent history resolves",
        status=status,
        observed_value=(
            f"{relationship_count - unresolved_count}/"
            f"{relationship_count}"
        ),
        expected_value="all relationships",
        detail=(
            None
            if status == CheckStatus.PASS
            else (
                f"{unresolved_count} recipient-parent history rows "
                "do not resolve to a canonical recipient."
            )
        ),
        evidence={
            "relationship_count": relationship_count,
            "unresolved_recipient_count": unresolved_count,
        },
    )


def check_award_recipient_history_coverage(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    cur.execute(
        """
        SELECT
            (
                SELECT COUNT(DISTINCT txn.award_id)
                FROM procurement.award_transaction AS txn
                WHERE txn.load_batch_id = %s
            ) AS batch_awards,
            (
                SELECT COUNT(DISTINCT rel.award_id)
                FROM procurement.award_recipient_relationship AS rel
                WHERE rel.load_batch_id = %s
            ) AS history_awards;
        """,
        (
            load_batch_id,
            load_batch_id,
        ),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Award-recipient history coverage query returned no result."
        )

    batch_awards = int(row[0])
    history_awards = int(row[1])

    status = (
        CheckStatus.PASS
        if batch_awards > 0 and history_awards == batch_awards
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code="REL-008",
        section="RELATIONSHIP COMPLETENESS",
        label="Award-recipient history coverage complete",
        status=status,
        observed_value=f"{history_awards}/{batch_awards}",
        expected_value="all batch awards",
        detail=(
            None
            if status == CheckStatus.PASS
            else (
                f"{batch_awards - history_awards} awards lack "
                "award-recipient history rows."
            )
        ),
        evidence={
            "batch_awards": batch_awards,
            "history_awards": history_awards,
        },
    )

RELATIONSHIP_CHECKS = (
    check_recipient_completeness,
    check_awarding_agency_completeness,
    check_awarding_subagency_completeness,
    check_funding_agency_completeness,
    check_funding_subagency_completeness,
    check_award_recipient_history_references,
    check_recipient_parent_history_references,
    check_award_recipient_history_coverage,
)