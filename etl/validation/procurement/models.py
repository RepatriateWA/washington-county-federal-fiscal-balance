"""
Shared models for procurement batch certification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class CheckStatus(str, Enum):
    """
    Permitted certification outcomes.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


@dataclass(frozen=True)
class CertificationCheck:
    """
    Result of one independent certification check.
    """

    check_code: str
    section: str
    label: str
    status: CheckStatus
    observed_value: Any = None
    expected_value: Any = None
    detail: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CertificationSummary:
    """
    Aggregate result of one procurement certification run.
    """

    load_batch_id: int
    checks: list[CertificationCheck]

    @property
    def passed_count(self) -> int:
        return sum(
            check.status == CheckStatus.PASS
            for check in self.checks
        )

    @property
    def failed_count(self) -> int:
        return sum(
            check.status == CheckStatus.FAIL
            for check in self.checks
        )

    @property
    def warning_count(self) -> int:
        return sum(
            check.status == CheckStatus.WARN
            for check in self.checks
        )

    @property
    def is_certified(self) -> bool:
        return self.failed_count == 0


CheckFunction = Callable[
    [Any, int],
    CertificationCheck,
]