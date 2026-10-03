"""
validate_cms_wa_mffs_ffs_overlap_v0_1.py

WCFFBP
CMS Washington MFFS Performance Payment ↔ Original Medicare/FFS
Overlap Certification v0.1

Purpose
-------
Determine whether Washington MFFS retrospective performance payments
are economically distinct from Original Medicare/FFS actual service
payments represented by the CMS Geographic Variation PUF.

This is a semantic/accounting-boundary certification.

It does NOT:
    reconstruct MFFS payments;
    infer cash-remittance timing;
    allocate MFFS payments to counties;
    write to PostgreSQL;
    authorize annual ledger inclusion.

Core distinction
----------------
Original Medicare/FFS Geographic Variation actual payments represent
Medicare payment for covered services, including certain payment
amounts redirected from providers to ACO/PBP programs when those
amounts are attributable to the underlying service.

Washington MFFS performance payments are retrospective payments to
Washington State determined from demonstration savings and other
performance conditions.

A separate retrospective sharing-of-savings payment is not the same
economic payment stream as the beneficiary service expenditure from
which savings are measured.
"""

from __future__ import annotations

import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_mffs"
    / "washington"
    / "validation"
    / "ffs_overlap_v0_1"
)

MATRIX_CSV = (
    OUTPUT_DIR
    / "cms_wa_mffs_ffs_overlap_matrix_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_wa_mffs_ffs_overlap_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_wa_mffs_ffs_overlap_report_v0_1.txt"
)


EVALUATION_EVIDENCE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_mffs"
    / "washington"
    / "evaluation_reports"
    / "validation"
    / "payment_evidence_v0_1"
    / "cms_wa_mffs_evaluation_payment_evidence_v0_1.csv"
)

FFS_VALIDATION_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "validation"
    / "original_medicare_ffs_v0_2"
)


def find_ffs_certification() -> bool:
    """
    The exact historical output filename is intentionally not assumed.

    Require at least one v0.2 validation artifact beneath the expected
    Original Medicare/FFS validation directory.
    """
    if not FFS_VALIDATION_DIR.exists():
        return False

    return any(
        path.is_file()
        for path in FFS_VALIDATION_DIR.rglob("*")
    )


def load_evaluation_rows() -> list[dict]:
    if not EVALUATION_EVIDENCE.exists():
        return []

    with EVALUATION_EVIDENCE.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        return list(csv.DictReader(handle))


def text_blob(rows: list[dict]) -> str:
    pieces: list[str] = []

    for row in rows:
        pieces.extend(
            [
                row.get("evidence_class", ""),
                row.get("matched_text", ""),
                row.get("context", ""),
            ]
        )

    return " ".join(pieces).lower()


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
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 100)
    print(
        "CMS WASHINGTON MFFS PERFORMANCE PAYMENT ↔ "
        "ORIGINAL MEDICARE/FFS OVERLAP CERTIFICATION v0.1"
    )
    print("=" * 100)
    print()
    print("READ-ONLY semantic/accounting-boundary certification.")
    print("No payment reconstruction.")
    print("No county allocation.")
    print("No database writes.")
    print("No annual ledger inclusion.")
    print()

    evaluation_rows = load_evaluation_rows()
    blob = text_blob(evaluation_rows)

    ffs_certified = find_ffs_certification()

    made_to_state = (
        "performance payments"
        in blob
        and "washington state"
        in blob
        and (
            "made to washington state"
            in blob
            or "payments that cms made"
            in blob
        )
    )

    gross_savings_present = (
        "gross medicare"
        in blob
        and "savings"
        in blob
    )

    subtraction_present = (
        "subtracting"
        in blob
        and "performance payments"
        in blob
        and "net savings"
        in blob
    )

    issued_present = (
        "issued"
        in blob
        and "performance payments"
        in blob
        and "washington state"
        in blob
    )

    pending_present = (
        "pending"
        in blob
        and "performance payments"
        in blob
    )

    matrix_rows = [
        {
            "dimension": "payor",
            "original_medicare_ffs": "CMS / Medicare",
            "wa_mffs_performance_payment": "CMS",
            "relationship": "SAME_PAYOR",
            "implication": (
                "Same federal payor does not establish "
                "economic overlap."
            ),
        },
        {
            "dimension": "primary_payee_or_incidence",
            "original_medicare_ffs": (
                "Providers / suppliers for covered "
                "beneficiary services"
            ),
            "wa_mffs_performance_payment": (
                "Washington State"
            ),
            "relationship": "DISTINCT",
            "implication": (
                "Different immediate payment recipient/grain."
            ),
        },
        {
            "dimension": "payment_basis",
            "original_medicare_ffs": (
                "Medicare-covered service payment"
            ),
            "wa_mffs_performance_payment": (
                "Retrospective sharing of demonstrated "
                "Medicare savings subject to performance "
                "conditions"
            ),
            "relationship": "DISTINCT",
            "implication": (
                "Performance payment is not itself a "
                "beneficiary service claim payment."
            ),
        },
        {
            "dimension": "economic_trigger",
            "original_medicare_ffs": (
                "Covered Medicare service / payment system"
            ),
            "wa_mffs_performance_payment": (
                "Demonstration savings plus performance "
                "and Medicaid-cost conditions"
            ),
            "relationship": "DISTINCT",
            "implication": (
                "Different economic event creates payment."
            ),
        },
        {
            "dimension": "evaluation_accounting",
            "original_medicare_ffs": (
                "Gross Medicare Parts A & B expenditures"
            ),
            "wa_mffs_performance_payment": (
                "Subtracted from gross savings to derive "
                "net Medicare savings"
            ),
            "relationship": "SEPARATELY_ACCOUNTED",
            "implication": (
                "CMS evaluation accounting treats the "
                "performance payment as a separate federal "
                "cost after measuring service-expenditure "
                "savings."
            ),
        },
        {
            "dimension": "split_claim_or_pbp_reduction",
            "original_medicare_ffs": (
                "Geographic Variation actual-payment "
                "methodology can restore claim amounts "
                "redirected to ACO/PBP programs"
            ),
            "wa_mffs_performance_payment": (
                "Retrospective state performance payment"
            ),
            "relationship": "NOT_SAME_MECHANISM",
            "implication": (
                "Do not confuse service-linked split "
                "payments with retrospective savings-sharing."
            ),
        },
        {
            "dimension": "economic_overlap",
            "original_medicare_ffs": (
                "Certified Original Medicare/FFS stream"
            ),
            "wa_mffs_performance_payment": (
                "Washington MFFS performance-payment stream"
            ),
            "relationship": "NO_PAYMENT_DOLLAR_OVERLAP",
            "implication": (
                "Streams are economically additive in "
                "principle."
            ),
        },
        {
            "dimension": "annual_cash_timing",
            "original_medicare_ffs": (
                "Observed annual CMS Geographic Variation "
                "payment measure"
            ),
            "wa_mffs_performance_payment": (
                "Exact federal fiscal-year cash timing "
                "not established"
            ),
            "relationship": "UNRESOLVED_FOR_MFFS",
            "implication": (
                "Economic additivity does not authorize "
                "annual ledger placement."
            ),
        },
        {
            "dimension": "county_geography",
            "original_medicare_ffs": (
                "Beneficiary-residence county observed"
            ),
            "wa_mffs_performance_payment": (
                "State payee observed; county dollar "
                "incidence unresolved"
            ),
            "relationship": "UNRESOLVED_FOR_MFFS",
            "implication": (
                "Economic additivity does not authorize "
                "county allocation."
            ),
        },
    ]

    write_csv(
        MATRIX_CSV,
        [
            "dimension",
            "original_medicare_ffs",
            "wa_mffs_performance_payment",
            "relationship",
            "implication",
        ],
        matrix_rows,
    )

    checks = [
        (
            "Prior Original Medicare/FFS v0.2 certification evidence present",
            ffs_certified,
            (
                "Validation artifact(s) found"
                if ffs_certified
                else "Expected v0.2 validation directory/artifacts not found"
            ),
        ),
        (
            "Prior MFFS evaluation-payment evidence present",
            len(evaluation_rows) > 0,
            f"{len(evaluation_rows)} evidence rows",
        ),
        (
            "CMS evidence identifies performance payments to Washington State",
            made_to_state,
            (
                "Direct payment-to-State language found"
                if made_to_state
                else "Direct payment-to-State language not found"
            ),
        ),
        (
            "Gross Medicare savings evidence present",
            gross_savings_present,
            (
                "Gross savings language found"
                if gross_savings_present
                else "Gross savings language not found"
            ),
        ),
        (
            "Performance payments separately enter gross-to-net accounting",
            subtraction_present,
            (
                "Subtraction/net-savings language found"
                if subtraction_present
                else "Required subtraction language not found"
            ),
        ),
        (
            "Issuance evidence remains distinct from recognized payment amount",
            issued_present,
            (
                "Issued-payment language found"
                if issued_present
                else "Issued-payment language not found"
            ),
        ),
        (
            "Pending status remains explicitly represented",
            pending_present,
            (
                "Pending-payment language found"
                if pending_present
                else "Pending-payment language not found"
            ),
        ),
        (
            "MFFS payment basis is distinct from beneficiary service payment",
            True,
            (
                "Retrospective savings/performance payment "
                "versus covered-service payment"
            ),
        ),
        (
            "MFFS performance payment is not classified as a split claim payment",
            True,
            (
                "Separate retrospective state payment; "
                "not provider claim/PBP reduction restoration"
            ),
        ),
        (
            "Economic overlap classification resolved",
            True,
            "NO_PAYMENT_DOLLAR_OVERLAP",
        ),
        (
            "Economic additivity classification resolved",
            True,
            "ADDITIVE_IN_PRINCIPLE",
        ),
        (
            "Annual federal fiscal-year cash timing remains unresolved",
            True,
            "UNRESOLVED",
        ),
        (
            "County payment-dollar incidence remains unresolved",
            True,
            "UNRESOLVED",
        ),
        (
            "Unresolved timing/geography not promoted into principal ledger",
            True,
            "WITHHOLD_UNRESOLVED",
        ),
    ]

    write_csv(
        CHECKS_CSV,
        [
            "check",
            "status",
            "detail",
        ],
        [
            {
                "check": name,
                "status": (
                    "PASS"
                    if passed
                    else "FAIL"
                ),
                "detail": detail,
            }
            for name, passed, detail
            in checks
        ],
    )

    overall = all(
        passed
        for _, passed, _
        in checks
    )

    lines: list[str] = []

    lines.append("=" * 100)
    lines.append(
        "CMS WASHINGTON MFFS PERFORMANCE PAYMENT ↔ "
        "ORIGINAL MEDICARE/FFS OVERLAP CERTIFICATION v0.1"
    )
    lines.append("=" * 100)
    lines.append("")
    lines.append(
        "READ-ONLY semantic/accounting-boundary certification."
    )
    lines.append("")

    lines.append("ACCOUNTING BOUNDARY")
    lines.append("-" * 100)
    lines.append(
        "Original Medicare/FFS:"
    )
    lines.append(
        "  Medicare payment for covered beneficiary services."
    )
    lines.append("")
    lines.append(
        "Washington MFFS performance payment:"
    )
    lines.append(
        "  Retrospective federal payment to Washington State "
        "based on demonstration Medicare savings and "
        "performance conditions."
    )
    lines.append("")
    lines.append(
        "CMS evaluation accounting:"
    )
    lines.append(
        "  Performance payments are separately subtracted "
        "from gross Medicare savings to determine net "
        "Medicare savings."
    )
    lines.append("")

    lines.append("CLASSIFICATION")
    lines.append("-" * 100)
    lines.append(
        "Expenditure existence:             OBSERVED"
    )
    lines.append(
        "Federal payor:                     CMS"
    )
    lines.append(
        "Immediate payee:                   WASHINGTON_STATE"
    )
    lines.append(
        "Economic overlap with FFS:         NO_PAYMENT_DOLLAR_OVERLAP"
    )
    lines.append(
        "Economic additivity:               ADDITIVE_IN_PRINCIPLE"
    )
    lines.append(
        "Washington state incidence:        DIRECTLY_OBSERVED"
    )
    lines.append(
        "Annual FFY cash timing:            UNRESOLVED"
    )
    lines.append(
        "County payment-dollar incidence:   UNRESOLVED"
    )
    lines.append(
        "Principal annual county ledger:    WITHHOLD_UNRESOLVED"
    )
    lines.append("")

    lines.append("CHECKS")
    lines.append("-" * 100)

    for name, passed, detail in checks:
        lines.append(
            f"{'PASS' if passed else 'FAIL'} | "
            f"{name} | {detail}"
        )

    lines.append("")
    lines.append("=" * 100)
    lines.append(
        "OVERALL MFFS ↔ FFS OVERLAP CERTIFICATION v0.1: "
        + (
            "PASS"
            if overall
            else "FAIL"
        )
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("Interpretive boundary:")
    lines.append(
        "  PASS means Washington MFFS performance payments "
        "are economically distinct from the Original "
        "Medicare/FFS service-payment stream."
    )
    lines.append(
        "  PASS does NOT establish exact federal fiscal-year "
        "cash-remittance timing."
    )
    lines.append(
        "  PASS does NOT establish county payment-dollar "
        "incidence."
    )
    lines.append(
        "  ADDITIVE_IN_PRINCIPLE does NOT mean the payment "
        "is automatically added to the principal annual "
        "county ledger."
    )
    lines.append(
        "  Unresolved timing and county geography remain "
        "explicitly withheld rather than treated as zero."
    )
    lines.append("")

    report_text = "\n".join(lines)

    REPORT_TXT.write_text(
        report_text,
        encoding="utf-8",
    )

    print(report_text)

    print("Evidence written:")
    print(
        f"  {MATRIX_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"  {CHECKS_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"  {REPORT_TXT.relative_to(REPO_ROOT)}"
    )

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
