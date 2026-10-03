"""
WCFFBP
CMS ACO Residual Source Universe Inventory v0.1

Purpose
-------
Define the reproducible source universe required to evaluate Medicare
ACO-related residual payment streams for Washington State before
Medicare v1.0 closeout.

This script performs NO network acquisition.

It does NOT:
    calculate Washington dollars;
    infer geography;
    infer shared-savings payments;
    classify additivity;
    write to PostgreSQL;
    authorize ledger inclusion.

The manifest is intentionally fail-closed:
required source slots remain MISSING until an official CMS artifact
has been preserved locally.
"""

from __future__ import annotations

import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

RAW_ROOT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
)

VALIDATION_DIR = (
    RAW_ROOT
    / "validation"
    / "source_universe_v0_1"
)

MANIFEST_CSV = (
    VALIDATION_DIR
    / "cms_aco_residual_source_universe_manifest_v0_1.csv"
)

CHECKS_CSV = (
    VALIDATION_DIR
    / "cms_aco_residual_source_universe_checks_v0_1.csv"
)

REPORT_TXT = (
    VALIDATION_DIR
    / "cms_aco_residual_source_universe_report_v0_1.txt"
)


def slot(
    *,
    source_family: str,
    slot_id: str,
    year_start: str,
    year_end: str,
    required: bool,
    purpose: str,
    expected_grain: str,
    geography_role: str,
    accounting_question: str,
) -> dict:
    return {
        "source_family": source_family,
        "slot_id": slot_id,
        "year_start": year_start,
        "year_end": year_end,
        "required": "YES" if required else "NO",
        "purpose": purpose,
        "expected_grain": expected_grain,
        "geography_role": geography_role,
        "accounting_question": accounting_question,
        "local_status": "MISSING",
        "local_path": "",
    }


def build_manifest() -> list[dict]:
    rows: list[dict] = []

    # ------------------------------------------------------------
    # MSSP Performance Year Financial and Quality Results
    # One required source slot for every principal study year.
    # ------------------------------------------------------------
    for year in range(2015, 2025):
        rows.append(
            slot(
                source_family="MSSP_PERFORMANCE_RESULTS",
                slot_id=f"MSSP_PY{year}",
                year_start=str(year),
                year_end=str(year),
                required=True,
                purpose=(
                    "Observe ACO-level financial performance, "
                    "benchmark, savings/loss, and earned "
                    "shared-savings fields."
                ),
                expected_grain="ACO_PERFORMANCE_YEAR",
                geography_role=(
                    "NOT_BY_ITSELF_WA_DOLLAR_INCIDENCE"
                ),
                accounting_question=(
                    "Does a Washington-relevant ACO receive "
                    "a separately identifiable federal "
                    "shared-savings/performance payment?"
                ),
            )
        )

    # ------------------------------------------------------------
    # ACO identifier crosswalk.
    # Needed because CMS changed public ACO identifiers.
    # ------------------------------------------------------------
    rows.append(
        slot(
            source_family="MSSP_ACO_ID_CROSSWALK",
            slot_id="MSSP_ACO_ID_CROSSWALK",
            year_start="PRE_2019",
            year_end="POST_2019",
            required=True,
            purpose=(
                "Link encrypted historical ACO identifiers "
                "to later unencrypted ACO identifiers."
            ),
            expected_grain="ACO_IDENTIFIER",
            geography_role="IDENTITY_ONLY",
            accounting_question=(
                "Can ACO identity be followed consistently "
                "across historical PUF vintages?"
            ),
        )
    )

    # ------------------------------------------------------------
    # ACO organization / participant information.
    # Required for Washington applicability testing.
    # Presence in WA does NOT itself allocate dollars to WA.
    # ------------------------------------------------------------
    rows.append(
        slot(
            source_family="MSSP_ACO_ORGANIZATION",
            slot_id="MSSP_ACO_ORGANIZATION_REFERENCE",
            year_start="2015",
            year_end="2024",
            required=True,
            purpose=(
                "Identify ACO organization attributes and "
                "support Washington applicability analysis."
            ),
            expected_grain="ACO",
            geography_role="APPLICABILITY_EVIDENCE_ONLY",
            accounting_question=(
                "Does an ACO have a defensible Washington "
                "organizational nexus?"
            ),
        )
    )

    rows.append(
        slot(
            source_family="MSSP_ACO_PARTICIPANTS",
            slot_id="MSSP_ACO_PARTICIPANTS_REFERENCE",
            year_start="2015",
            year_end="2024",
            required=True,
            purpose=(
                "Identify participating providers/suppliers "
                "and support Washington applicability analysis."
            ),
            expected_grain="ACO_PARTICIPANT",
            geography_role="APPLICABILITY_EVIDENCE_ONLY",
            accounting_question=(
                "Does an ACO include Washington participants, "
                "without assuming participant location equals "
                "payment-dollar incidence?"
            ),
        )
    )

    # ------------------------------------------------------------
    # Beneficiary geography.
    # Useful as incidence evidence but explicitly NOT an automatic
    # shared-savings allocation key.
    # ------------------------------------------------------------
    rows.append(
        slot(
            source_family="MSSP_BENEFICIARY_GEOGRAPHY",
            slot_id="MSSP_BENEFICIARY_COUNTY_REFERENCE",
            year_start="2015",
            year_end="2024",
            required=True,
            purpose=(
                "Establish whether assigned beneficiaries "
                "are observed in Washington geography."
            ),
            expected_grain="ACO_OR_PROGRAM_COUNTY_YEAR",
            geography_role=(
                "BENEFICIARY_INCIDENCE_NOT_PAYMENT_ALLOCATION"
            ),
            accounting_question=(
                "Is Washington beneficiary incidence "
                "observable independently of payment dollars?"
            ),
        )
    )

    # ------------------------------------------------------------
    # ACO Investment Model.
    # Separate candidate payment stream.
    # ------------------------------------------------------------
    rows.append(
        slot(
            source_family="ACO_INVESTMENT_MODEL",
            slot_id="AIM_PAYMENT_EVIDENCE",
            year_start="2015",
            year_end="2018",
            required=True,
            purpose=(
                "Determine Washington applicability and "
                "whether upfront/monthly AIM payments form "
                "a distinct federal expenditure stream."
            ),
            expected_grain="ACO_MODEL_PARTICIPANT",
            geography_role="TO_BE_CERTIFIED",
            accounting_question=(
                "Are AIM advance payments relevant to "
                "Washington and distinct from MSSP shared "
                "savings and FFS service payments?"
            ),
        )
    )

    # ------------------------------------------------------------
    # Next Generation ACO.
    # Separate CMMI model with financial results.
    # ------------------------------------------------------------
    rows.append(
        slot(
            source_family="NEXT_GENERATION_ACO",
            slot_id="NGACO_FINANCIAL_RESULTS",
            year_start="2016",
            year_end="2021",
            required=True,
            purpose=(
                "Test Washington applicability and identify "
                "any distinct financial settlement/payment "
                "stream."
            ),
            expected_grain="ACO_MODEL_PERFORMANCE_YEAR",
            geography_role="TO_BE_CERTIFIED",
            accounting_question=(
                "Did Washington have material Next Generation "
                "ACO payment exposure not already represented "
                "in FFS?"
            ),
        )
    )

    # ------------------------------------------------------------
    # Pioneer ACO.
    # Included deliberately even though initial official review
    # suggests no Washington participant.  We certify rather than
    # silently omit it.
    # ------------------------------------------------------------
    rows.append(
        slot(
            source_family="PIONEER_ACO",
            slot_id="PIONEER_WA_APPLICABILITY",
            year_start="2015",
            year_end="2016",
            required=True,
            purpose=(
                "Formally test Washington applicability "
                "during the portion of Pioneer overlapping "
                "the WCFFBP study period."
            ),
            expected_grain="ACO_MODEL_PARTICIPANT",
            geography_role="APPLICABILITY_TEST",
            accounting_question=(
                "Was any Pioneer ACO participant materially "
                "applicable to Washington?"
            ),
        )
    )

    return rows


def discover_local_files(rows: list[dict]) -> None:
    """
    Conservative local discovery.

    A source slot is marked PRESENT only when a file exists beneath a
    source-family directory named exactly for that family.

    This avoids treating unrelated CMS files as evidence.
    """
    for row in rows:
        family_dir = RAW_ROOT / row["source_family"].lower()

        if not family_dir.exists():
            continue

        files = sorted(
            p
            for p in family_dir.rglob("*")
            if p.is_file()
        )

        if files:
            row["local_status"] = "PRESENT_UNVALIDATED"
            row["local_path"] = ";".join(
                str(p.relative_to(REPO_ROOT))
                for p in files
            )


def write_csv(
    path: Path,
    fields: list[str],
    rows: list[dict],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = build_manifest()
    discover_local_files(rows)

    required_rows = [
        row
        for row in rows
        if row["required"] == "YES"
    ]

    present_rows = [
        row
        for row in required_rows
        if row["local_status"] != "MISSING"
    ]

    missing_rows = [
        row
        for row in required_rows
        if row["local_status"] == "MISSING"
    ]

    fields = [
        "source_family",
        "slot_id",
        "year_start",
        "year_end",
        "required",
        "purpose",
        "expected_grain",
        "geography_role",
        "accounting_question",
        "local_status",
        "local_path",
    ]

    write_csv(
        MANIFEST_CSV,
        fields,
        rows,
    )

    checks = [
        {
            "check": "MSSP PY2015-PY2024 source slots defined",
            "status": (
                "PASS"
                if sum(
                    row["source_family"]
                    == "MSSP_PERFORMANCE_RESULTS"
                    for row in rows
                ) == 10
                else "FAIL"
            ),
            "detail": (
                f"{sum(row['source_family'] == 'MSSP_PERFORMANCE_RESULTS' for row in rows)}/10"
            ),
        },
        {
            "check": "ACO ID crosswalk source slot defined",
            "status": (
                "PASS"
                if any(
                    row["source_family"]
                    == "MSSP_ACO_ID_CROSSWALK"
                    for row in rows
                )
                else "FAIL"
            ),
            "detail": "Historical identifier continuity required",
        },
        {
            "check": "Washington applicability sources defined",
            "status": (
                "PASS"
                if all(
                    any(
                        row["source_family"] == family
                        for row in rows
                    )
                    for family in [
                        "MSSP_ACO_ORGANIZATION",
                        "MSSP_ACO_PARTICIPANTS",
                        "MSSP_BENEFICIARY_GEOGRAPHY",
                    ]
                )
                else "FAIL"
            ),
            "detail": (
                "Organization, participant, and beneficiary "
                "geography kept distinct"
            ),
        },
        {
            "check": "Residual ACO model candidates defined",
            "status": (
                "PASS"
                if all(
                    any(
                        row["source_family"] == family
                        for row in rows
                    )
                    for family in [
                        "ACO_INVESTMENT_MODEL",
                        "NEXT_GENERATION_ACO",
                        "PIONEER_ACO",
                    ]
                )
                else "FAIL"
            ),
            "detail": "AIM, Next Generation, Pioneer",
        },
        {
            "check": "All required source slots locally present",
            "status": (
                "PASS"
                if not missing_rows
                else "FAIL"
            ),
            "detail": (
                f"{len(present_rows)}/{len(required_rows)} "
                "required slots presently have local files"
            ),
        },
    ]

    write_csv(
        CHECKS_CSV,
        ["check", "status", "detail"],
        checks,
    )

    lines: list[str] = []

    lines.append("=" * 100)
    lines.append(
        "CMS ACO RESIDUAL SOURCE UNIVERSE INVENTORY v0.1"
    )
    lines.append("=" * 100)
    lines.append("")
    lines.append(
        "Purpose: define the reproducible source universe "
        "before Medicare v1.0 closeout."
    )
    lines.append("")
    lines.append(
        "No network acquisition."
    )
    lines.append(
        "No payment reconstruction."
    )
    lines.append(
        "No geographic allocation."
    )
    lines.append(
        "No database writes."
    )
    lines.append(
        "No ledger inclusion."
    )
    lines.append("")

    lines.append("SOURCE UNIVERSE")
    lines.append("-" * 100)

    for row in rows:
        lines.append(
            f"{row['slot_id']:<38} "
            f"{row['local_status']}"
        )

    lines.append("")
    lines.append("SUMMARY")
    lines.append("-" * 100)
    lines.append(
        f"Source slots:       {len(rows)}"
    )
    lines.append(
        f"Required slots:     {len(required_rows)}"
    )
    lines.append(
        f"Present locally:    {len(present_rows)}"
    )
    lines.append(
        f"Missing locally:    {len(missing_rows)}"
    )
    lines.append("")

    if missing_rows:
        lines.append("MISSING REQUIRED SLOTS")
        lines.append("-" * 100)

        for row in missing_rows:
            lines.append(
                f"{row['slot_id']} | "
                f"{row['source_family']} | "
                f"{row['year_start']}-{row['year_end']}"
            )

        lines.append("")

    lines.append("CHECKS")
    lines.append("-" * 100)

    for check in checks:
        lines.append(
            f"{check['status']} | "
            f"{check['check']} | "
            f"{check['detail']}"
        )

    lines.append("")
    lines.append("=" * 100)
    lines.append(
        "SOURCE-UNIVERSE STATUS: "
        + (
            "COMPLETE_FOR_VALIDATION"
            if not missing_rows
            else "ACQUISITION_REQUIRED"
        )
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("Interpretive boundary:")
    lines.append(
        "  A missing source is not evidence of zero expenditure."
    )
    lines.append(
        "  A Washington participant is not automatically "
        "evidence that payment dollars belong to Washington."
    )
    lines.append(
        "  Washington beneficiary incidence is not automatically "
        "a payment-dollar allocation key."
    )
    lines.append(
        "  Different CMS datasets are not additive by default."
    )
    lines.append(
        "  Every candidate requires an explicit economic-overlap "
        "classification before ledger inclusion."
    )
    lines.append(
        "  This inventory supports a systematic and reproducible "
        "review; it makes no claim of definitive completeness."
    )

    report = "\n".join(lines)

    REPORT_TXT.write_text(
        report,
        encoding="utf-8",
    )

    print(report)
    print()
    print("Evidence written:")
    print(
        f"  {MANIFEST_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"  {CHECKS_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"  {REPORT_TXT.relative_to(REPO_ROOT)}"
    )

    # Missing local source files are an expected acquisition state,
    # not a Python execution failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
