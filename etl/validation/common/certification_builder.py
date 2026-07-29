from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .evidence_package import EvidencePackage


SCHEMA_VERSION = "1.0.0"

VALID_CHECK_STATUSES = {
    "PASS",
    "FAIL",
    "WARNING",
    "ERROR",
}


class CertificationBuilder:
    """
    Builds the machine-readable EPS-001 certification record.

    This builder:
    - does not write files
    - does not perform validation checks
    - converts completed check results into the certification contract
    - derives the overall certification status from the check outcomes
    """

    def __init__(
        self,
        *,
        certification_version: str | None = None,
        etl_version: str | None = None,
    ) -> None:
        self._certification_version = self._clean_optional(
            certification_version
        )
        self._etl_version = self._clean_optional(etl_version)

    def build(
        self,
        package: EvidencePackage,
        *,
        checks: Iterable[Mapping[str, Any]] | None = None,
        statistics: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build a certification document conforming to
        certification.schema.json.
        """
        normalized_checks = [
            self._normalize_check(check)
            for check in (checks or [])
        ]

        summary = self._build_summary(
            package=package,
            checks=normalized_checks,
        )

        document: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "evidence_package_id": package.evidence_package_id,
            "dataset": package.dataset,
            "batch_id": package.batch_id,
            "status": self._derive_status(
                summary=summary,
                checks=normalized_checks,
            ),
            "created_utc": self._format_utc(package.created_utc),
            "summary": summary,
            "checks": normalized_checks,
            "versions": {
                "etl_version": self._etl_version,
                "certification_version": (
                    self._certification_version
                ),
                "evidence_package_version": (
                    package.package_version
                ),
            },
        }

        if statistics is not None:
            document["statistics"] = dict(statistics)

        return document

    def _build_summary(
        self,
        *,
        package: EvidencePackage,
        checks: list[dict[str, Any]],
    ) -> dict[str, int]:
        """
        Use check-level counts when checks are supplied.

        Otherwise, use the certification summary already carried by
        EvidencePackage.
        """
        if checks:
            passed = sum(
                check["status"] == "PASS"
                for check in checks
            )
            failed = sum(
                check["status"] in {"FAIL", "ERROR"}
                for check in checks
            )
            warnings = sum(
                check["status"] == "WARNING"
                for check in checks
            )

            return {
                "passed": passed,
                "failed": failed,
                "warnings": warnings,
                "total": len(checks),
            }

        certification = package.certification

        passed = self._read_nonnegative_integer(
            certification,
            "passed",
        )
        failed = self._read_nonnegative_integer(
            certification,
            "failed",
        )
        warnings = self._read_nonnegative_integer(
            certification,
            "warnings",
        )

        return {
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "total": passed + failed + warnings,
        }

    @staticmethod
    def _derive_status(
        *,
        summary: Mapping[str, int],
        checks: list[dict[str, Any]],
    ) -> str:
        if any(
            check["status"] == "ERROR"
            for check in checks
        ):
            return "ERROR"

        if summary["failed"] > 0:
            return "NOT_CERTIFIED"

        return "CERTIFIED"

    def _normalize_check(
        self,
        check: Mapping[str, Any],
    ) -> dict[str, Any]:
        required_fields = {
            "code",
            "name",
            "category",
            "status",
            "message",
            "evidence",
        }

        missing_fields = required_fields.difference(check)

        if missing_fields:
            missing = ", ".join(sorted(missing_fields))

            raise ValueError(
                f"Certification check is missing required "
                f"field(s): {missing}"
            )

        code = self._require_text(
            check["code"],
            field_name="code",
        )
        name = self._require_text(
            check["name"],
            field_name="name",
        )
        category = self._require_text(
            check["category"],
            field_name="category",
        )
        status = self._require_text(
            check["status"],
            field_name="status",
        ).upper()

        if status not in VALID_CHECK_STATUSES:
            allowed = ", ".join(sorted(VALID_CHECK_STATUSES))

            raise ValueError(
                f"Invalid certification check status "
                f"{status!r}. Expected one of: {allowed}."
            )

        message_value = check["message"]

        if not isinstance(message_value, str):
            raise TypeError(
                "Certification check field 'message' "
                "must be a string."
            )

        evidence_value = check["evidence"]

        if not isinstance(evidence_value, Mapping):
            raise TypeError(
                "Certification check field 'evidence' "
                "must be a mapping."
            )

        return {
            "code": code,
            "name": name,
            "category": category,
            "status": status,
            "message": message_value,
            "evidence": dict(evidence_value),
        }

    @staticmethod
    def _read_nonnegative_integer(
        source: object,
        field_name: str,
    ) -> int:
        if isinstance(source, Mapping):
            value = source.get(field_name)
        else:
            value = getattr(source, field_name, None)

        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"Certification summary field "
                f"{field_name!r} must be an integer."
            )

        if value < 0:
            raise ValueError(
                f"Certification summary field "
                f"{field_name!r} cannot be negative."
            )

        return value

    @staticmethod
    def _require_text(
        value: object,
        *,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError(
                f"Certification check field "
                f"{field_name!r} must be a string."
            )

        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                f"Certification check field "
                f"{field_name!r} cannot be empty."
            )

        return cleaned

    @staticmethod
    def _format_utc(value: object) -> str:
        iso_value = value.isoformat(timespec="seconds")

        if iso_value.endswith("+00:00"):
            return iso_value[:-6] + "Z"

        return iso_value

    @staticmethod
    def _clean_optional(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        cleaned = value.strip()

        return cleaned or None