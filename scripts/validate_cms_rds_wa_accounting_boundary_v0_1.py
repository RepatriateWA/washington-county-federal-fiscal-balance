"""
validate_cms_rds_wa_accounting_boundary_v0_1.py

WCFFBP
CMS Retiree Drug Subsidy (RDS)
Washington Accounting Boundary Certification v0.1

Purpose
-------
Certify the accounting boundary for Medicare Retiree Drug Subsidy (RDS)
within the Washington County Federal Fiscal Balance Project.

This validator does NOT:
    * write to PostgreSQL;
    * calculate Washington RDS payment dollars;
    * allocate national or sponsor RDS dollars by beneficiary count;
    * allocate RDS dollars to Washington counties;
    * treat withheld RDS expenditure as zero.

The certification distinguishes:

    1. expenditure existence;
    2. economic additivity;
    3. beneficiary geographic incidence;
    4. payment-dollar geographic incidence;
    5. principal-ledger eligibility.

Expected certified boundary
---------------------------
RDS expenditure existence:
    OBSERVED

RDS payment-dollar grain:
    SPONSOR

RDS economic relationship:
    ADDITIVE_IN_PRINCIPLE

Washington beneficiary incidence:
    DIRECTLY_OBSERVED

Washington dollar incidence:
    UNRESOLVED

Washington county dollar incidence:
    UNRESOLVED

Principal-ledger treatment:
    WITHHOLD_UNRESOLVED

Withholding does NOT imply zero Washington RDS expenditure.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_rds"
    / "validation"
    / "rds_wa_accounting_boundary_v0_1"
)

MATRIX_CSV = OUTPUT_DIR / "cms_rds_wa_accounting_boundary_matrix_v0_1.csv"
CHECKS_CSV = OUTPUT_DIR / "cms_rds_wa_accounting_boundary_checks_v0_1.csv"
REPORT_TXT = OUTPUT_DIR / "cms_rds_wa_accounting_boundary_report_v0_1.txt"


@dataclass(frozen=True)
class EvidenceItem:
    dimension: str
    status: str
    evidence: str
    ledger_implication: str


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


EVIDENCE = [
    EvidenceItem(
        dimension="FEDERAL_EXPENDITURE_EXISTENCE",
        status="OBSERVED",
        evidence=(
            "CMS Plan Payment Data publishes Retiree Drug Subsidy "
            "plan payment data by plan year."
        ),
        ledger_implication=(
            "RDS is a known federal expenditure stream; it must not "
            "be treated as nonexistent or zero."
        ),
    ),
    EvidenceItem(
        dimension="PAYMENT_DOLLAR_GRAIN",
        status="SPONSOR",
        evidence=(
            "The public CMS RDS Plan Payment PUF reports payment "
            "information by plan sponsor/business rather than by "
            "beneficiary residence."
        ),
        ledger_implication=(
            "Sponsor identity cannot be used as beneficiary geography."
        ),
    ),
    EvidenceItem(
        dimension="ECONOMIC_ADDITIVITY",
        status="ADDITIVE_IN_PRINCIPLE",
        evidence=(
            "Prior WCFFBP RDS semantic/additivity certification found "
            "RDS payment dollars economically distinct from Original "
            "Medicare/FFS, Part C, and Part D payment streams."
        ),
        ledger_implication=(
            "RDS is not excluded as a duplicate of FFS, Part C, or Part D."
        ),
    ),
    EvidenceItem(
        dimension="WASHINGTON_BENEFICIARY_INCIDENCE",
        status="DIRECTLY_OBSERVED",
        evidence=(
            "CMS MDCR ENROLL D 3 publishes Retiree Drug Subsidy "
            "(No Part D Plan) enrollment by Area of Residence. "
            "WCFFBP v0.3 certified Washington observations for "
            "CY2015-CY2023."
        ),
        ledger_implication=(
            "Washington RDS beneficiary incidence is established, "
            "but beneficiary counts are not payment dollars."
        ),
    ),
    EvidenceItem(
        dimension="WASHINGTON_DOLLAR_INCIDENCE",
        status="UNRESOLVED",
        evidence=(
            "No validated public CMS source has been identified that "
            "links actual RDS subsidy dollars to beneficiary residence "
            "in Washington."
        ),
        ledger_implication=(
            "Actual RDS dollars cannot currently be assigned to "
            "Washington in the principal ledger."
        ),
    ),
    EvidenceItem(
        dimension="WASHINGTON_COUNTY_DOLLAR_INCIDENCE",
        status="UNRESOLVED",
        evidence=(
            "No validated public CMS source has been identified that "
            "reports or links actual RDS subsidy dollars to Washington "
            "county beneficiary residence."
        ),
        ledger_implication=(
            "No county RDS dollar allocation is permitted."
        ),
    ),
    EvidenceItem(
        dimension="BENEFICIARY_COUNT_ALLOCATION",
        status="REJECTED_FOR_PRINCIPAL_LEDGER",
        evidence=(
            "CMS RDS subsidy payments depend on allowable retiree "
            "prescription-drug costs and are not a fixed payment per "
            "RDS beneficiary."
        ),
        ledger_implication=(
            "Washington's share of RDS beneficiaries must not be used "
            "as though it were observed Washington payment incidence."
        ),
    ),
    EvidenceItem(
        dimension="SPONSOR_NAME_GEOGRAPHY",
        status="REJECTED",
        evidence=(
            "RDS PUF business/sponsor identity describes the payment "
            "recipient/sponsor and does not establish beneficiary "
            "residence."
        ),
        ledger_implication=(
            "Sponsor names, including geographically named sponsors, "
            "must not be converted into Washington expenditure incidence."
        ),
    ),
    EvidenceItem(
        dimension="PRINCIPAL_LEDGER_TREATMENT",
        status="WITHHOLD_UNRESOLVED",
        evidence=(
            "Economic additivity has been established, but Washington "
            "payment-dollar geographic incidence has not."
        ),
        ledger_implication=(
            "Withhold RDS from the principal Washington ledger pending "
            "a validated geographic-dollar source."
        ),
    ),
    EvidenceItem(
        dimension="ZERO_INTERPRETATION",
        status="PROHIBITED",
        evidence=(
            "Withholding results from unresolved geographic attribution, "
            "not evidence of zero Washington RDS expenditure."
        ),
        ledger_implication=(
            "Do not encode withheld RDS as $0."
        ),
    ),
]


def status_for(dimension: str) -> str | None:
    for item in EVIDENCE:
        if item.dimension == dimension:
            return item.status
    return None


def build_checks() -> list[Check]:
    checks: list[Check] = []

    checks.append(
        Check(
            name="RDS federal expenditure existence established",
            passed=(
                status_for("FEDERAL_EXPENDITURE_EXISTENCE")
                == "OBSERVED"
            ),
            detail=(
                "Expected OBSERVED federal RDS expenditure."
            ),
        )
    )

    checks.append(
        Check(
            name="Public RDS payment-dollar grain identified",
            passed=(
                status_for("PAYMENT_DOLLAR_GRAIN")
                == "SPONSOR"
            ),
            detail=(
                "Expected public payment-dollar grain = SPONSOR."
            ),
        )
    )

    checks.append(
        Check(
            name="RDS economic additivity established",
            passed=(
                status_for("ECONOMIC_ADDITIVITY")
                == "ADDITIVE_IN_PRINCIPLE"
            ),
            detail=(
                "Expected ADDITIVE_IN_PRINCIPLE."
            ),
        )
    )

    checks.append(
        Check(
            name="Washington beneficiary incidence established",
            passed=(
                status_for("WASHINGTON_BENEFICIARY_INCIDENCE")
                == "DIRECTLY_OBSERVED"
            ),
            detail=(
                "Expected DIRECTLY_OBSERVED Washington RDS enrollment."
            ),
        )
    )

    checks.append(
        Check(
            name="Washington payment-dollar incidence remains unresolved",
            passed=(
                status_for("WASHINGTON_DOLLAR_INCIDENCE")
                == "UNRESOLVED"
            ),
            detail=(
                "No validated public residence-dollar bridge."
            ),
        )
    )

    checks.append(
        Check(
            name="Washington county payment-dollar incidence remains unresolved",
            passed=(
                status_for("WASHINGTON_COUNTY_DOLLAR_INCIDENCE")
                == "UNRESOLVED"
            ),
            detail=(
                "No validated public county-dollar bridge."
            ),
        )
    )

    checks.append(
        Check(
            name="Beneficiary-count dollar allocation rejected",
            passed=(
                status_for("BENEFICIARY_COUNT_ALLOCATION")
                == "REJECTED_FOR_PRINCIPAL_LEDGER"
            ),
            detail=(
                "Enrollment share is not treated as observed payment incidence."
            ),
        )
    )

    checks.append(
        Check(
            name="Sponsor-name geographic allocation rejected",
            passed=(
                status_for("SPONSOR_NAME_GEOGRAPHY")
                == "REJECTED"
            ),
            detail=(
                "Sponsor identity is not beneficiary residence."
            ),
        )
    )

    checks.append(
        Check(
            name="Unresolved geography not promoted to Washington dollars",
            passed=(
                status_for("WASHINGTON_DOLLAR_INCIDENCE")
                == "UNRESOLVED"
                and status_for("PRINCIPAL_LEDGER_TREATMENT")
                == "WITHHOLD_UNRESOLVED"
            ),
            detail=(
                "Fail-closed geographic accounting boundary preserved."
            ),
        )
    )

    checks.append(
        Check(
            name="Withheld RDS not interpreted as zero",
            passed=(
                status_for("ZERO_INTERPRETATION")
                == "PROHIBITED"
            ),
            detail=(
                "WITHHOLD_UNRESOLVED is distinct from $0."
            ),
        )
    )

    checks.append(
        Check(
            name="Principal-ledger treatment is WITHHOLD_UNRESOLVED",
            passed=(
                status_for("PRINCIPAL_LEDGER_TREATMENT")
                == "WITHHOLD_UNRESOLVED"
            ),
            detail=(
                "RDS remains outside principal WA ledger until a "
                "validated geographic-dollar source exists."
            ),
        )
    )

    return checks


def write_matrix() -> None:
    with MATRIX_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "dimension",
                "status",
                "evidence",
                "ledger_implication",
            ]
        )
        for item in EVIDENCE:
            writer.writerow(
                [
                    item.dimension,
                    item.status,
                    item.evidence,
                    item.ledger_implication,
                ]
            )


def write_checks(checks: list[Check]) -> None:
    with CHECKS_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "result",
                "check",
                "detail",
            ]
        )
        for check in checks:
            writer.writerow(
                [
                    "PASS" if check.passed else "FAIL",
                    check.name,
                    check.detail,
                ]
            )


def build_report(checks: list[Check]) -> str:
    width = 100
    lines: list[str] = []

    lines.append("=" * width)
    lines.append(
        "CMS RETIREE DRUG SUBSIDY (RDS) "
        "WASHINGTON ACCOUNTING BOUNDARY CERTIFICATION v0.1"
    )
    lines.append("=" * width)
    lines.append("")
    lines.append("READ-ONLY")
    lines.append("No database writes.")
    lines.append("No Washington RDS dollar calculation.")
    lines.append("No beneficiary-count dollar allocation.")
    lines.append("No county allocation.")
    lines.append("Withheld RDS is NOT treated as zero.")
    lines.append("")

    lines.append("=" * width)
    lines.append("ACCOUNTING BOUNDARY")
    lines.append("=" * width)
    lines.append("")

    for item in EVIDENCE:
        lines.append(f"{item.dimension}")
        lines.append("-" * width)
        lines.append(f"Status: {item.status}")
        lines.append(f"Evidence: {item.evidence}")
        lines.append(
            f"Ledger implication: {item.ledger_implication}"
        )
        lines.append("")

    lines.append("=" * width)
    lines.append("CHECKS")
    lines.append("=" * width)
    lines.append("")

    for check in checks:
        result = "PASS" if check.passed else "FAIL"
        lines.append(
            f"{result} | {check.name} | {check.detail}"
        )

    lines.append("")

    overall_pass = all(check.passed for check in checks)

    lines.append("=" * width)
    lines.append(
        "OVERALL RDS WASHINGTON ACCOUNTING BOUNDARY: "
        + ("PASS" if overall_pass else "FAIL")
    )
    lines.append("=" * width)
    lines.append("")

    lines.append("Certified boundary:")
    lines.append("  Federal RDS expenditure: OBSERVED")
    lines.append("  Public payment-dollar grain: SPONSOR")
    lines.append("  Economic status: ADDITIVE_IN_PRINCIPLE")
    lines.append(
        "  Washington beneficiary incidence: DIRECTLY_OBSERVED"
    )
    lines.append("  Washington dollar incidence: UNRESOLVED")
    lines.append(
        "  Washington county dollar incidence: UNRESOLVED"
    )
    lines.append(
        "  Principal ledger treatment: WITHHOLD_UNRESOLVED"
    )
    lines.append("")

    lines.append("Methodological interpretation:")
    lines.append(
        "  RDS is a known and economically distinct federal Medicare "
        "expenditure stream."
    )
    lines.append(
        "  Public CMS data establish actual RDS subsidy payments and "
        "independently establish RDS beneficiary residence, but do not "
        "provide a validated public linkage between subsidy dollars "
        "and beneficiary residence."
    )
    lines.append(
        "  WCFFBP therefore does not allocate RDS payments to "
        "Washington using beneficiary counts or sponsor identity."
    )
    lines.append(
        "  RDS is withheld from the principal Washington ledger "
        "pending a validated geographic-dollar source."
    )
    lines.append(
        "  Withholding does not imply zero Washington RDS expenditure."
    )
    lines.append("")

    lines.append("Rejected principal-ledger estimator:")
    lines.append("")
    lines.append(
        "  RDS_WA = RDS_US * "
        "(RDS_Beneficiaries_WA / RDS_Beneficiaries_US)"
    )
    lines.append("")
    lines.append(
        "Reason: RDS subsidy dollars depend on allowable retiree "
        "prescription-drug costs rather than a fixed payment per "
        "beneficiary. Such a calculation would be a model, not an "
        "observed Washington expenditure."
    )
    lines.append("")

    lines.append("Accounting invariant:")
    lines.append("")
    lines.append(
        "  Economic additivity does not imply geographic allocatability."
    )
    lines.append(
        "  No federal expenditure is geographically attributable by "
        "default."
    )
    lines.append(
        "  Geographic attribution must be demonstrated independently "
        "of expenditure existence and economic additivity."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    checks = build_checks()

    write_matrix()
    write_checks(checks)

    report = build_report(checks)
    REPORT_TXT.write_text(report, encoding="utf-8")

    print(report)

    print("Evidence written:")
    print(f"  {MATRIX_CSV.relative_to(REPO_ROOT)}")
    print(f"  {CHECKS_CSV.relative_to(REPO_ROOT)}")
    print(f"  {REPORT_TXT.relative_to(REPO_ROOT)}")
    print("")

    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
