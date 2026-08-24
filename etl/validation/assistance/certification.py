from __future__ import annotations
from etl.validation.assistance.checks import CHECKS
from etl.validation.assistance.models import CertificationCheck, CertificationSummary, CheckStatus

def run_certification(cur, *, load_batch_id: int) -> CertificationSummary:
    results = []
    for i, fn in enumerate(CHECKS, start=1):
        sp = f"assistance_cert_check_{i}"
        cur.execute(f"SAVEPOINT {sp};")
        try:
            result = fn(cur, load_batch_id)
        except Exception as exc:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp};")
            result = CertificationCheck(
                check_code="ENGINE-ERROR",
                section="CERTIFICATION ENGINE",
                label=fn.__name__,
                status=CheckStatus.FAIL,
                detail=f"{type(exc).__name__}: {exc}",
            )
        finally:
            cur.execute(f"RELEASE SAVEPOINT {sp};")
        results.append(result)
    return CertificationSummary(load_batch_id=load_batch_id, checks=results)
