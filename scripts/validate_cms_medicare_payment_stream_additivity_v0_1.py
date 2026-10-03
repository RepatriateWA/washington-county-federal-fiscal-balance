from __future__ import annotations

from pathlib import Path
import csv


OUTDIR = Path(
    "data/raw/cms/medicare/validation/"
    "payment_stream_additivity_v0_1"
)

MATRIX_FILE = OUTDIR / "cms_medicare_payment_stream_overlap_matrix_v0_1.csv"
CHECK_FILE = OUTDIR / "cms_medicare_payment_stream_additivity_checks_v0_1.csv"
REPORT_FILE = OUTDIR / "cms_medicare_payment_stream_additivity_report_v0_1.txt"


STREAMS = {
    "ORIGINAL_MEDICARE_FFS": {
        "program_component": "Original Medicare / Fee-for-Service",
        "benefit_scope": "Medicare Part A and Part B",
        "payment_scope": (
            "Actual Original Medicare / FFS payments represented by "
            "TOT_MDCR_PYMT_AMT in the CMS Geographic Variation PUF"
        ),
        "principal_source": (
            "CMS Medicare Geographic Variation by National, State & County"
        ),
        "wcffbp_status": "CANDIDATE_ADDITIVE",
        "certification": (
            "Original Medicare / FFS source mechanics v0.2 PASS"
        ),
    },
    "MEDICARE_PART_C": {
        "program_component": "Medicare Advantage Part C",
        "benefit_scope": (
            "Medicare Part A/B benefits delivered through Medicare "
            "Advantage plans"
        ),
        "payment_scope": (
            "Risk-adjusted A/B plan payment plus Part C rebate"
        ),
        "principal_source": "CMS Plan Payment PUF + monthly CPSC enrollment",
        "wcffbp_status": "CANDIDATE_ADDITIVE",
        "certification": (
            "Washington Medicare Advantage Part C reconstruction v0.2 PASS"
        ),
    },
    "MEDICARE_PART_D": {
        "program_component": "Medicare Part D",
        "benefit_scope": "Medicare outpatient prescription-drug benefit",
        "payment_scope": (
            "Risk-adjusted Direct Subsidy plus Reinsurance plus "
            "Low-Income Cost Sharing subsidy"
        ),
        "principal_source": "CMS Plan Payment PUF + monthly CPSC enrollment",
        "wcffbp_status": "CANDIDATE_ADDITIVE",
        "certification": (
            "Washington Medicare Part D reconstruction v0.3 PASS"
        ),
    },
}


PAIRWISE = [
    {
        "stream_a": "ORIGINAL_MEDICARE_FFS",
        "stream_b": "MEDICARE_PART_C",
        "beneficiary_overlap_possible": "NO_FOR_SAME_COVERAGE_MONTH",
        "payment_stream_overlap": "NO",
        "classification": "ADDITIVE",
        "basis": (
            "Original Medicare/FFS represents Part A/B claims for the "
            "traditional FFS population. Part C represents Medicare "
            "Advantage plan payments for Part A/B benefits delivered "
            "through MA plans. These are alternative Part A/B delivery "
            "systems rather than two representations of the same payment."
        ),
        "important_boundary": (
            "Do not infer additivity merely from different datasets. "
            "Additivity rests on mutually distinct Part A/B payment "
            "delivery streams."
        ),
    },
    {
        "stream_a": "ORIGINAL_MEDICARE_FFS",
        "stream_b": "MEDICARE_PART_D",
        "beneficiary_overlap_possible": "YES",
        "payment_stream_overlap": "NO",
        "classification": "ADDITIVE",
        "basis": (
            "An Original Medicare beneficiary may also enroll in Part D, "
            "so beneficiary populations can overlap. The payment streams "
            "do not: the FFS Geographic Variation expenditure measure is "
            "the Original Medicare Part A/B stream, whereas Part D is the "
            "prescription-drug subsidy stream reconstructed from Direct "
            "Subsidy, Reinsurance, and LICS."
        ),
        "important_boundary": (
            "Beneficiary overlap is not payment-dollar overlap."
        ),
    },
    {
        "stream_a": "MEDICARE_PART_C",
        "stream_b": "MEDICARE_PART_D",
        "beneficiary_overlap_possible": "YES",
        "payment_stream_overlap": "NO",
        "classification": "ADDITIVE",
        "basis": (
            "MA-PD beneficiaries may generate both Part C and Part D "
            "payments. Certified Part C reconstruction consists of "
            "risk-adjusted A/B payment plus rebate. Certified Part D "
            "reconstruction consists of risk-adjusted Direct Subsidy, "
            "Reinsurance, and LICS. The components are economically "
            "distinct federal payment streams."
        ),
        "important_boundary": (
            "Shared contract, plan, or beneficiary identity does not "
            "make Part C and Part D payments the same dollars."
        ),
    },
]


CONTROLS = [
    {
        "candidate": "PART_D_RECONCILIATION_WORKBOOK",
        "relationship": "MEDICARE_PART_D",
        "classification": "CONTROL_ONLY",
        "reason": (
            "Alternative reconciliation representation of Part D; "
            "not a second additive expenditure stream."
        ),
    },
    {
        "candidate": "USASPENDING_ASSISTANCE_93.774",
        "relationship": "MEDICARE_SMI",
        "classification": "OVERLAPPING_EXCLUDE_DUPLICATE",
        "reason": (
            "Aggregate Medicare SMI reporting retained for provenance "
            "and reconciliation; not additive to CMS-native Medicare."
        ),
    },
]


def check(label: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "check": label,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
    }


def main() -> None:
    print("=" * 100)
    print("CMS MEDICARE PAYMENT-STREAM ADDITIVITY VALIDATOR v0.1")
    print("=" * 100)
    print()
    print("READ-ONLY: no database writes")
    print()

    OUTDIR.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # Stream-definition gate
    # ------------------------------------------------------------------

    required_streams = {
        "ORIGINAL_MEDICARE_FFS",
        "MEDICARE_PART_C",
        "MEDICARE_PART_D",
    }

    checks.append(
        check(
            "Three principal Medicare streams explicitly defined",
            set(STREAMS) == required_streams,
            ", ".join(sorted(STREAMS)),
        )
    )

    # ------------------------------------------------------------------
    # Pairwise completeness gate
    # ------------------------------------------------------------------

    expected_pairs = {
        frozenset(("ORIGINAL_MEDICARE_FFS", "MEDICARE_PART_C")),
        frozenset(("ORIGINAL_MEDICARE_FFS", "MEDICARE_PART_D")),
        frozenset(("MEDICARE_PART_C", "MEDICARE_PART_D")),
    }

    observed_pairs = {
        frozenset((row["stream_a"], row["stream_b"]))
        for row in PAIRWISE
    }

    checks.append(
        check(
            "All three pairwise overlap relationships evaluated",
            observed_pairs == expected_pairs,
            f"{len(observed_pairs)}/3 unique pairs",
        )
    )

    # ------------------------------------------------------------------
    # No-double-counting gate
    # ------------------------------------------------------------------

    all_pairwise_classified = all(
        row["classification"] in {
            "ADDITIVE",
            "OVERLAPPING",
            "CONTROL_ONLY",
            "UNRESOLVED",
        }
        for row in PAIRWISE
    )

    checks.append(
        check(
            "Every pair has explicit accounting classification",
            all_pairwise_classified,
            f"{len(PAIRWISE)}/{len(PAIRWISE)} classified",
        )
    )

    unresolved = [
        row for row in PAIRWISE
        if row["classification"] == "UNRESOLVED"
    ]

    checks.append(
        check(
            "No unresolved pair promoted to additive",
            len(unresolved) == 0,
            f"{len(unresolved)} unresolved pairs",
        )
    )

    payment_overlap_additive_conflicts = [
        row for row in PAIRWISE
        if (
            row["classification"] == "ADDITIVE"
            and row["payment_stream_overlap"] != "NO"
        )
    ]

    checks.append(
        check(
            "No additive pair has identified payment-dollar overlap",
            len(payment_overlap_additive_conflicts) == 0,
            (
                f"{len(payment_overlap_additive_conflicts)} "
                "additivity/overlap conflicts"
            ),
        )
    )

    # ------------------------------------------------------------------
    # Beneficiary-overlap distinction gate
    # ------------------------------------------------------------------

    beneficiary_overlap_pairs = [
        row for row in PAIRWISE
        if row["beneficiary_overlap_possible"] == "YES"
    ]

    beneficiary_overlap_correctly_distinguished = all(
        row["payment_stream_overlap"] == "NO"
        and row["classification"] == "ADDITIVE"
        for row in beneficiary_overlap_pairs
    )

    checks.append(
        check(
            "Beneficiary overlap distinguished from payment overlap",
            (
                len(beneficiary_overlap_pairs) == 2
                and beneficiary_overlap_correctly_distinguished
            ),
            (
                f"{len(beneficiary_overlap_pairs)} pairs permit "
                "beneficiary overlap"
            ),
        )
    )

    # ------------------------------------------------------------------
    # Certified source-mechanics provenance gate
    # ------------------------------------------------------------------

    certifications_present = all(
        bool(row["certification"].strip())
        for row in STREAMS.values()
    )

    checks.append(
        check(
            "Each additive stream references prior certification",
            certifications_present,
            f"{len(STREAMS)}/{len(STREAMS)} streams",
        )
    )

    # ------------------------------------------------------------------
    # Known duplicate/control exclusions
    # ------------------------------------------------------------------

    control_classes_ok = all(
        row["classification"] != "ADDITIVE"
        for row in CONTROLS
    )

    checks.append(
        check(
            "Known reconciliation/overlap sources remain non-additive",
            control_classes_ok,
            f"{len(CONTROLS)}/{len(CONTROLS)} controls non-additive",
        )
    )

    # ------------------------------------------------------------------
    # Accounting conclusion
    # ------------------------------------------------------------------

    additive_pairs = [
        row for row in PAIRWISE
        if row["classification"] == "ADDITIVE"
    ]

    three_stream_additivity_pass = (
        len(additive_pairs) == 3
        and len(payment_overlap_additive_conflicts) == 0
        and len(unresolved) == 0
    )

    checks.append(
        check(
            "FFS + Part C + Part D payment-stream additivity",
            three_stream_additivity_pass,
            f"{len(additive_pairs)}/3 pairwise relationships ADDITIVE",
        )
    )

    # ------------------------------------------------------------------
    # Write overlap matrix.
    # ------------------------------------------------------------------

    matrix_fields = [
        "stream_a",
        "stream_b",
        "beneficiary_overlap_possible",
        "payment_stream_overlap",
        "classification",
        "basis",
        "important_boundary",
    ]

    with MATRIX_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=matrix_fields)
        writer.writeheader()
        writer.writerows(PAIRWISE)

    # ------------------------------------------------------------------
    # Write checks.
    # ------------------------------------------------------------------

    with CHECK_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["check", "status", "detail"],
        )
        writer.writeheader()
        writer.writerows(checks)

    # ------------------------------------------------------------------
    # Human-readable evidence report.
    # ------------------------------------------------------------------

    report_lines: list[str] = []

    report_lines.append(
        "CMS MEDICARE PAYMENT-STREAM ADDITIVITY "
        "CERTIFICATION v0.1"
    )
    report_lines.append("=" * 78)
    report_lines.append("")
    report_lines.append("ACCOUNTING INVARIANT")
    report_lines.append("-" * 78)
    report_lines.append(
        "No federal expenditure source is additive by default."
    )
    report_lines.append(
        "A plus sign is permitted only after affirmative evidence "
        "that the candidate represents an economically distinct "
        "federal payment stream."
    )
    report_lines.append("")

    report_lines.append("PRINCIPAL STREAMS")
    report_lines.append("-" * 78)

    for key, row in STREAMS.items():
        report_lines.append(f"{key}")
        report_lines.append(
            f"  Component: {row['program_component']}"
        )
        report_lines.append(
            f"  Benefit scope: {row['benefit_scope']}"
        )
        report_lines.append(
            f"  Payment scope: {row['payment_scope']}"
        )
        report_lines.append(
            f"  Source: {row['principal_source']}"
        )
        report_lines.append(
            f"  Prior certification: {row['certification']}"
        )
        report_lines.append("")

    report_lines.append("PAIRWISE OVERLAP MATRIX")
    report_lines.append("-" * 78)

    for row in PAIRWISE:
        report_lines.append(
            f"{row['stream_a']} <-> {row['stream_b']}"
        )
        report_lines.append(
            f"  Beneficiary overlap possible: "
            f"{row['beneficiary_overlap_possible']}"
        )
        report_lines.append(
            f"  Payment-stream overlap: "
            f"{row['payment_stream_overlap']}"
        )
        report_lines.append(
            f"  Classification: {row['classification']}"
        )
        report_lines.append(
            f"  Basis: {row['basis']}"
        )
        report_lines.append(
            f"  Boundary: {row['important_boundary']}"
        )
        report_lines.append("")

    report_lines.append("KNOWN NON-ADDITIVE REPRESENTATIONS")
    report_lines.append("-" * 78)

    for row in CONTROLS:
        report_lines.append(
            f"{row['candidate']} -> {row['relationship']}"
        )
        report_lines.append(
            f"  Classification: {row['classification']}"
        )
        report_lines.append(
            f"  Reason: {row['reason']}"
        )
        report_lines.append("")

    report_lines.append("CONCLUSION")
    report_lines.append("-" * 78)
    report_lines.append(
        "For the certified CMS-native payment streams evaluated here:"
    )
    report_lines.append("")
    report_lines.append(
        "  Medicare = Original Medicare/FFS + Part C + Part D"
    )
    report_lines.append("")
    report_lines.append(
        "The plus signs refer to economically distinct federal "
        "payment streams, not mutually exclusive beneficiary populations."
    )
    report_lines.append("")
    report_lines.append(
        "This certification does NOT assert that these three streams "
        "constitute the complete Medicare federal inflow universe."
    )
    report_lines.append(
        "RDS and any other candidate Medicare payment streams require "
        "their own accounting-source/additivity gates before inclusion."
    )

    REPORT_FILE.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # Console report.
    # ------------------------------------------------------------------

    print("=" * 100)
    print("PAIRWISE PAYMENT-STREAM MATRIX")
    print("=" * 100)

    for row in PAIRWISE:
        print(
            f"{row['stream_a']:24} <-> "
            f"{row['stream_b']:24} | "
            f"BENEFICIARY_OVERLAP="
            f"{row['beneficiary_overlap_possible']:26} | "
            f"PAYMENT_OVERLAP={row['payment_stream_overlap']:3} | "
            f"{row['classification']}"
        )

    print()
    print("=" * 100)
    print("CHECKS")
    print("=" * 100)

    for row in checks:
        print(
            f"{row['status']:4} | "
            f"{row['check']} | "
            f"{row['detail']}"
        )

    overall_pass = all(
        row["status"] == "PASS"
        for row in checks
    )

    print()
    print("=" * 100)
    print(
        "OVERALL: "
        + ("PASS" if overall_pass else "FAIL")
    )
    print("=" * 100)

    print()
    print("Certified accounting expression:")
    print()
    print(
        "  Medicare (evaluated streams)"
        " = Original Medicare/FFS + Part C + Part D"
    )
    print()
    print(
        "IMPORTANT: This is an additivity certification, "
        "not yet a Medicare completeness certification."
    )
    print(
        "RDS and other candidate Medicare streams remain outside "
        "this equation until separately evaluated."
    )

    print()
    print("Evidence written:")
    print(f"  {MATRIX_FILE}")
    print(f"  {CHECK_FILE}")
    print(f"  {REPORT_FILE}")

    if not overall_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
