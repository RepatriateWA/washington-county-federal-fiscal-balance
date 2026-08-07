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

from etl.validation.procurement.checks.provenance import (
    PROVENANCE_CHECKS,
)

CERTIFICATION_CHECKS: tuple[CheckFunction, ...] = (
    *BATCH_CHECKS,
    *DUPLICATE_CHECKS,
    *REFERENTIAL_CHECKS,
    *RELATIONSHIP_CHECKS,
    *PROVENANCE_CHECKS,
    *FINANCIAL_CHECKS,
)

def run_certification(
    cur,
    *,
    load_batch_id: int,
) -> CertificationSummary:
    """
    Run every registered procurement certification check.

    Each check executes inside its own savepoint so one SQL failure
    does not leave the transaction aborted or prevent later checks
    from running.
    """
    checks: list[CertificationCheck] = []

    for check_number, check_function in enumerate(
        CERTIFICATION_CHECKS,
        start=1,
    ):
        savepoint_name = f"procurement_cert_check_{check_number}"

        cur.execute(
            f"SAVEPOINT {savepoint_name};"
        )

        try:
            result = check_function(
                cur,
                load_batch_id,
            )

        except Exception as exc:
            cur.execute(
                f"ROLLBACK TO SAVEPOINT {savepoint_name};"
            )

            result = CertificationCheck(
                check_code="ENGINE-ERROR",
                section="CERTIFICATION ENGINE",
                label=check_function.__name__,
                status=CheckStatus.FAIL,
                detail=f"{type(exc).__name__}: {exc}",
            )

        finally:
            cur.execute(
                f"RELEASE SAVEPOINT {savepoint_name};"
            )

        checks.append(result)

    return CertificationSummary(
        load_batch_id=load_batch_id,
        checks=checks,
    )