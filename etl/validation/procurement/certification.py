"""
Procurement batch certification engine.
"""

from __future__ import annotations

from etl.validation.procurement.checks.batch import (
    BATCH_CHECKS,
)
from etl.validation.procurement.checks.duplicates import (
    DUPLICATE_CHECKS,
)
from etl.validation.procurement.checks.referential import (
    REFERENTIAL_CHECKS,
)
from etl.validation.procurement.models import (
    CertificationCheck,
    CertificationSummary,
    CheckFunction,
    CheckStatus,
)
from etl.validation.procurement.checks.relationships import (
    RELATIONSHIP_CHECKS,
)
from etl.validation.procurement.checks.financial import (
    FINANCIAL_CHECKS,
)

CERTIFICATION_CHECKS: tuple[CheckFunction, ...] = (
    *BATCH_CHECKS,
    *DUPLICATE_CHECKS,
    *REFERENTIAL_CHECKS,
    *RELATIONSHIP_CHECKS,
    *FINANCIAL_CHECKS,
)

def run_certification(
    cur,
    *,
    load_batch_id: int,
) -> CertificationSummary:
    """
    Run every registered procurement certification check.
    """
    checks: list[CertificationCheck] = []

    for check_function in CERTIFICATION_CHECKS:
        try:
            result = check_function(
                cur,
                load_batch_id,
            )
        except Exception as exc:
            result = CertificationCheck(
                check_code="ENGINE-ERROR",
                section="CERTIFICATION ENGINE",
                label=check_function.__name__,
                status=CheckStatus.FAIL,
                detail=f"{type(exc).__name__}: {exc}",
            )

        checks.append(result)

    return CertificationSummary(
        load_batch_id=load_batch_id,
        checks=checks,
    )