"""
Procurement referential-integrity certification checks.
"""

from __future__ import annotations

from etl.validation.procurement.models import (
    CertificationCheck,
    CheckStatus,
)
from etl.validation.procurement.query import scalar_query


def make_orphan_check(
    *,
    check_code: str,
    label: str,
    orphan_count: int,
    detail_label: str,
) -> CertificationCheck:
    status = (
        CheckStatus.PASS
        if orphan_count == 0
        else CheckStatus.FAIL
    )

    return CertificationCheck(
        check_code=check_code,
        section="REFERENTIAL INTEGRITY",
        label=label,
        status=status,
        observed_value=orphan_count,
        expected_value=0,
        detail=(
            None
            if orphan_count == 0
            else f"{orphan_count} {detail_label} were found."
        ),
    )


def check_transaction_award_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.award_transaction AS txn
            LEFT JOIN procurement.award AS aw
              ON aw.award_id = txn.award_id
            WHERE txn.load_batch_id = %s
              AND aw.award_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-001",
        label="Transaction award references resolve",
        orphan_count=orphan_count,
        detail_label="orphan transaction-to-award references",
    )


def check_award_recipient_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT txn.award_id
                FROM procurement.award_transaction AS txn
                WHERE txn.load_batch_id = %s
            ) AS batch_awards
            JOIN procurement.award AS aw
              ON aw.award_id = batch_awards.award_id
            LEFT JOIN procurement.recipient AS recipient
              ON recipient.recipient_id = aw.recipient_id
            WHERE aw.recipient_id IS NOT NULL
              AND recipient.recipient_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-002",
        label="Award recipient references resolve",
        orphan_count=orphan_count,
        detail_label="orphan award-to-recipient references",
    )


def check_awarding_agency_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT txn.award_id
                FROM procurement.award_transaction AS txn
                WHERE txn.load_batch_id = %s
            ) AS batch_awards
            JOIN procurement.award AS aw
              ON aw.award_id = batch_awards.award_id
            LEFT JOIN procurement.agency AS agency
              ON agency.agency_id = aw.awarding_agency_id
            WHERE aw.awarding_agency_id IS NOT NULL
              AND agency.agency_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-003",
        label="Awarding-agency references resolve",
        orphan_count=orphan_count,
        detail_label="orphan awarding-agency references",
    )


def check_awarding_subagency_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT txn.award_id
                FROM procurement.award_transaction AS txn
                WHERE txn.load_batch_id = %s
            ) AS batch_awards
            JOIN procurement.award AS aw
              ON aw.award_id = batch_awards.award_id
            LEFT JOIN procurement.agency AS agency
              ON agency.agency_id = aw.awarding_subagency_id
            WHERE aw.awarding_subagency_id IS NOT NULL
              AND agency.agency_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-004",
        label="Awarding-subagency references resolve",
        orphan_count=orphan_count,
        detail_label="orphan awarding-subagency references",
    )


def check_funding_agency_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT txn.award_id
                FROM procurement.award_transaction AS txn
                WHERE txn.load_batch_id = %s
            ) AS batch_awards
            JOIN procurement.award AS aw
              ON aw.award_id = batch_awards.award_id
            LEFT JOIN procurement.agency AS agency
              ON agency.agency_id = aw.funding_agency_id
            WHERE aw.funding_agency_id IS NOT NULL
              AND agency.agency_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-005",
        label="Funding-agency references resolve",
        orphan_count=orphan_count,
        detail_label="orphan funding-agency references",
    )


def check_funding_subagency_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT txn.award_id
                FROM procurement.award_transaction AS txn
                WHERE txn.load_batch_id = %s
            ) AS batch_awards
            JOIN procurement.award AS aw
              ON aw.award_id = batch_awards.award_id
            LEFT JOIN procurement.agency AS agency
              ON agency.agency_id = aw.funding_subagency_id
            WHERE aw.funding_subagency_id IS NOT NULL
              AND agency.agency_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-006",
        label="Funding-subagency references resolve",
        orphan_count=orphan_count,
        detail_label="orphan funding-subagency references",
    )


def check_place_transaction_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.place_of_performance AS pop
            JOIN procurement.award_transaction AS batch_txn
              ON batch_txn.award_transaction_id =
                 pop.award_transaction_id
            LEFT JOIN procurement.award_transaction AS resolved_txn
              ON resolved_txn.award_transaction_id =
                 pop.award_transaction_id
            WHERE batch_txn.load_batch_id = %s
              AND resolved_txn.award_transaction_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-007",
        label="Place transaction references resolve",
        orphan_count=orphan_count,
        detail_label="orphan place-to-transaction references",
    )


def check_canonical_place_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.place_of_performance AS pop
            JOIN procurement.award_transaction AS txn
              ON txn.award_transaction_id =
                 pop.award_transaction_id
            LEFT JOIN procurement.place AS place
              ON place.place_id = pop.place_id
            WHERE txn.load_batch_id = %s
              AND pop.place_id IS NOT NULL
              AND place.place_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-008",
        label="Canonical-place references resolve",
        orphan_count=orphan_count,
        detail_label="orphan canonical-place references",
    )


def check_state_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.place_of_performance AS pop
            JOIN procurement.award_transaction AS txn
              ON txn.award_transaction_id =
                 pop.award_transaction_id
            LEFT JOIN reference.state_registry AS state
              ON state.state_id = pop.state_id
            WHERE txn.load_batch_id = %s
              AND pop.state_id IS NOT NULL
              AND state.state_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-009",
        label="State references resolve",
        orphan_count=orphan_count,
        detail_label="orphan state references",
    )


def check_county_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.place_of_performance AS pop
            JOIN procurement.award_transaction AS txn
              ON txn.award_transaction_id =
                 pop.award_transaction_id
            LEFT JOIN reference.county_registry AS county
              ON county.county_id = pop.county_id
            WHERE txn.load_batch_id = %s
              AND pop.county_id IS NOT NULL
              AND county.county_id IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-010",
        label="County references resolve",
        orphan_count=orphan_count,
        detail_label="orphan county references",
    )


def check_naics_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.award_transaction AS txn
            LEFT JOIN procurement.naics AS naics
              ON naics.naics_code = txn.naics_code
            WHERE txn.load_batch_id = %s
              AND txn.naics_code IS NOT NULL
              AND naics.naics_code IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-011",
        label="NAICS references resolve",
        orphan_count=orphan_count,
        detail_label="orphan transaction-to-NAICS references",
    )


def check_psc_references(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    orphan_count = int(
        scalar_query(
            cur,
            """
            SELECT COUNT(*)
            FROM procurement.award_transaction AS txn
            LEFT JOIN procurement.psc AS psc
              ON psc.psc_code = txn.psc_code
            WHERE txn.load_batch_id = %s
              AND txn.psc_code IS NOT NULL
              AND psc.psc_code IS NULL;
            """,
            (load_batch_id,),
        )
    )

    return make_orphan_check(
        check_code="FK-012",
        label="PSC references resolve",
        orphan_count=orphan_count,
        detail_label="orphan transaction-to-PSC references",
    )

REFERENTIAL_CHECKS = (
    check_transaction_award_references,
    check_award_recipient_references,
    check_awarding_agency_references,
    check_awarding_subagency_references,
    check_funding_agency_references,
    check_funding_subagency_references,
    check_place_transaction_references,
    check_canonical_place_references,
    check_state_references,
    check_county_references,
    check_naics_references,
    check_psc_references,
)