from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"

@dataclass(frozen=True)
class CertificationCheck:
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
    load_batch_id: int
    checks: list[CertificationCheck]

    @property
    def passed_count(self) -> int:
        return sum(c.status == CheckStatus.PASS for c in self.checks)

    @property
    def failed_count(self) -> int:
        return sum(c.status == CheckStatus.FAIL for c in self.checks)

    @property
    def warning_count(self) -> int:
        return sum(c.status == CheckStatus.WARN for c in self.checks)

    @property
    def is_certified(self) -> bool:
        return self.failed_count == 0

CheckFunction = Callable[[Any, int], CertificationCheck]
