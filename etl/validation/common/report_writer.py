from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class ReportWriter:
    """
    Renders and writes a human-readable EPS-001 certification report.

    The report is derived from the certification document. It does not
    independently calculate certification status or validation totals.
    """

    def render(
        self,
        certification: Mapping[str, Any],
    ) -> str:
        evidence_package_id = self._require_text(
            certification,
            "evidence_package_id",
        )
        dataset = self._require_text(
            certification,
            "dataset",
        )
        status = self._require_text(
            certification,
            "status",
        )
        created_utc = self._require_text(
            certification,
            "created_utc",
        )

        batch_id = certification.get("batch_id")

        summary = certification.get("summary")

        if not isinstance(summary, Mapping):
            raise TypeError(
                "Certification field 'summary' must be a mapping."
            )

        passed = self._require_integer(summary, "passed")
        failed = self._require_integer(summary, "failed")
        warnings = self._require_integer(summary, "warnings")
        total = self._require_integer(summary, "total")

        checks_value = certification.get("checks")

        if not isinstance(checks_value, Sequence) or isinstance(
            checks_value,
            (str, bytes),
        ):
            raise TypeError(
                "Certification field 'checks' must be a sequence."
            )

        lines = [
            "EPS-001 CERTIFICATION REPORT",
            "=" * 72,
            "",
            f"Evidence Package ID: {evidence_package_id}",
            f"Dataset:             {dataset}",
            f"Batch ID:            {batch_id}",
            f"Created UTC:         {created_utc}",
            "",
            "CERTIFICATION DECISION",
            "-" * 72,
            f"Status:              {status}",
            "",
            "VALIDATION SUMMARY",
            "-" * 72,
            f"Passed:              {passed}",
            f"Failed:              {failed}",
            f"Warnings:            {warnings}",
            f"Total checks:        {total}",
            "",
            "CHECK RESULTS",
            "-" * 72,
        ]

        if not checks_value:
            lines.append("No detailed check records were supplied.")
        else:
            for index, check in enumerate(checks_value, start=1):
                if not isinstance(check, Mapping):
                    raise TypeError(
                        "Every certification check must be a mapping."
                    )

                lines.extend(
                    self._render_check(
                        check=check,
                        index=index,
                    )
                )

        statistics = certification.get("statistics")

        if statistics is not None:
            if not isinstance(statistics, Mapping):
                raise TypeError(
                    "Certification field 'statistics' "
                    "must be a mapping."
                )

            lines.extend(
                [
                    "",
                    "STATISTICS",
                    "-" * 72,
                ]
            )

            if statistics:
                for key, value in statistics.items():
                    label = str(key).replace("_", " ").title()
                    lines.append(f"{label}: {value}")
            else:
                lines.append("No statistics were supplied.")

        versions = certification.get("versions")

        if versions is not None:
            if not isinstance(versions, Mapping):
                raise TypeError(
                    "Certification field 'versions' "
                    "must be a mapping."
                )

            lines.extend(
                [
                    "",
                    "VERSIONS",
                    "-" * 72,
                    (
                        "Evidence Package:    "
                        f"{versions.get('evidence_package_version')}"
                    ),
                    (
                        "Certification:       "
                        f"{versions.get('certification_version')}"
                    ),
                    (
                        "ETL:                 "
                        f"{versions.get('etl_version')}"
                    ),
                ]
            )

        lines.extend(
            [
                "",
                "=" * 72,
                "End of certification report.",
                "",
            ]
        )

        return "\n".join(lines)

    def write(
        self,
        path: Path,
        certification: Mapping[str, Any],
    ) -> None:
        report = self.render(certification)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            report,
            encoding="utf-8",
            newline="\n",
        )

    def _render_check(
        self,
        *,
        check: Mapping[str, Any],
        index: int,
    ) -> list[str]:
        code = self._require_text(check, "code")
        name = self._require_text(check, "name")
        category = self._require_text(check, "category")
        status = self._require_text(check, "status")

        message = check.get("message")

        if not isinstance(message, str):
            raise TypeError(
                "Certification check field 'message' "
                "must be a string."
            )

        evidence = check.get("evidence")

        if not isinstance(evidence, Mapping):
            raise TypeError(
                "Certification check field 'evidence' "
                "must be a mapping."
            )

        lines = [
            "",
            f"{index}. [{status}] {code} — {name}",
            f"   Category: {category}",
        ]

        if message:
            lines.append(f"   Message:  {message}")

        if evidence:
            lines.append("   Evidence:")

            for key, value in evidence.items():
                label = str(key).replace("_", " ")
                lines.append(f"      {label}: {value}")
        else:
            lines.append("   Evidence: None supplied")

        return lines

    @staticmethod
    def _require_text(
        source: Mapping[str, Any],
        field_name: str,
    ) -> str:
        value = source.get(field_name)

        if not isinstance(value, str):
            raise TypeError(
                f"Field {field_name!r} must be a string."
            )

        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                f"Field {field_name!r} cannot be empty."
            )

        return cleaned

    @staticmethod
    def _require_integer(
        source: Mapping[str, Any],
        field_name: str,
    ) -> int:
        value = source.get(field_name)

        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"Field {field_name!r} must be an integer."
            )

        if value < 0:
            raise ValueError(
                f"Field {field_name!r} cannot be negative."
            )

        return value