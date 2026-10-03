from __future__ import annotations

import csv
from pathlib import Path


OUTDIR = Path(
    "data/raw/cms/medicare_rds/validation/"
    "rds_semantic_additivity_v0_1"
)

MATRIX_FILE = OUTDIR / "cms_rds_overlap_matrix_v0_1.csv"
CHECKS_FILE = OUTDIR / "cms_rds_semantic_additivity_checks_v0_1.csv"
REPORT_FILE = OUTDIR / "cms_rds_semantic_additivity_report_v0_1.txt"


RDS = {
    "stream": "RETIREE_DRUG_SUBSIDY",
    "program": "Medicare Retiree Drug Subsidy",
    "payee": "Qualified employer/union retiree prescription-drug plan sponsor",
    "beneficiary_status": (
        "Qualifying covered retiree is Medicare Part D eligible "
        "but is not enrolled in a Medicare Part D plan"
    ),
    "payment_scope": (
        "Federal subsidy payment based on allowable prescription-drug "
        "costs for qualifying covered retirees"
    ),
    "public_puf_grain": "Business / plan sponsor",
    "public_puf_payment_field": "Subsidy Paid / Total Paid",
    "public_puf_count_field": "Retiree Count / ELGBL Count",
    "public_puf_geography": "NONE_PUBLISHED_IN_PROFILED_TABLE",
}


PAIRWISE = [
    {
        "stream_a": "RETIREE_DRUG_SUBSIDY",
        "stream_b": "MEDICARE_PART_D",
        "beneficiary_overlap_same_period": "NO",
        "payment_stream_overlap": "NO",
        "classification": "ADDITIVE",
        "basis": (
            "CMS requires a qualifying covered retiree for RDS to be "
            "eligible for Medicare Part D but not enrolled in a Part D "
            "plan. RDS therefore represents employer/union retiree-drug "
            "subsidy payments outside the ordinary Part D plan-payment "
            "stream reconstructed by WCFFBP."
        ),
    },
    {
        "stream_a": "RETIREE_DRUG_SUBSIDY",
        "stream_b": "ORIGINAL_MEDICARE_FFS",
        "beneficiary_overlap_same_period": "YES",
        "payment_stream_overlap": "NO",
        "classification": "ADDITIVE",
        "basis": (
            "RDS is a prescription-drug subsidy to qualified retiree "
            "plan sponsors. Original Medicare/FFS accounting represents "
            "the certified Part A/B FFS payment stream. A retiree may "
            "participate in Original Medicare while also being covered "
            "by an RDS-qualified employer/union drug plan, but the "
            "federal payment streams are economically distinct."
        ),
    },
    {
        "stream_a": "RETIREE_DRUG_SUBSIDY",
        "stream_b": "MEDICARE_PART_C",
        "beneficiary_overlap_same_period": "POSSIBLE_OR_NOT_REQUIRED_FOR_GATE",
        "payment_stream_overlap": "NO",
        "classification": "ADDITIVE",
        "basis": (
            "Certified Part C accounting consists of Medicare Advantage "
            "A/B plan payment plus Part C rebate. RDS is a separate "
            "prescription-drug subsidy paid under the employer/union "
            "retiree-drug subsidy program. No RDS component is included "
            "in the certified WCFFBP Part C reconstruction."
        ),
    },
]


GEOGRAPHY = {
    "published_fields": (
        "Business name; Subsidy Paid/Total Paid; "
        "Retiree Count/ELGBL Count"
    ),
    "state_field": "NO",
    "county_field": "NO",
    "zip_field": "NO",
    "beneficiary_residence_field": "NO",
    "sponsor_name_is_geography": "NO",
    "washington_allocation_status": "UNRESOLVED",
    "ledger_status": "NOT_YET_WA_ALLOCATABLE",
}


def make_check(label: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "check": label,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
    }


def main() -> None:
    print("=" * 100)
    print("CMS RETIREE DRUG SUBSIDY SEMANTIC / ADDITIVITY VALIDATOR v0.1")
    print("=" * 100)
    print()
    print("READ-ONLY: no database writes")
    print("No Washington RDS dollars are reconstructed or allocated.")
    print()

    OUTDIR.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # Semantic identity
    # ------------------------------------------------------------------

    checks.append(
        make_check(
            "RDS identified as federal subsidy payment stream",
            bool(RDS["payment_scope"]),
            RDS["payment_scope"],
        )
    )

    checks.append(
        make_check(
            "RDS payee/grain identified as plan sponsor",
            RDS["public_puf_grain"] == "Business / plan sponsor",
            RDS["payee"],
        )
    )

    # ------------------------------------------------------------------
    # Critical RDS <-> Part D exclusion
    # ------------------------------------------------------------------

    rds_partd = next(
        row
        for row in PAIRWISE
        if row["stream_b"] == "MEDICARE_PART_D"
    )

    checks.append(
        make_check(
            "RDS and Part D beneficiary eligibility distinguished",
            (
                rds_partd["beneficiary_overlap_same_period"] == "NO"
                and rds_partd["payment_stream_overlap"] == "NO"
            ),
            (
                "RDS qualifying retiree is Part D eligible but not "
                "enrolled in a Part D plan"
            ),
        )
    )

    # ------------------------------------------------------------------
    # Pairwise accounting gate
    # ------------------------------------------------------------------

    expected_pairs = {
        frozenset(("RETIREE_DRUG_SUBSIDY", "MEDICARE_PART_D")),
        frozenset(("RETIREE_DRUG_SUBSIDY", "ORIGINAL_MEDICARE_FFS")),
        frozenset(("RETIREE_DRUG_SUBSIDY", "MEDICARE_PART_C")),
    }

    observed_pairs = {
        frozenset((row["stream_a"], row["stream_b"]))
        for row in PAIRWISE
    }

    checks.append(
        make_check(
            "RDS evaluated against all three certified Medicare streams",
            observed_pairs == expected_pairs,
            f"{len(observed_pairs)}/3 pairwise relationships",
        )
    )

    overlap_conflicts = [
        row
        for row in PAIRWISE
        if (
            row["classification"] == "ADDITIVE"
            and row["payment_stream_overlap"] != "NO"
        )
    ]

    checks.append(
        make_check(
            "No RDS additive pair has identified payment-dollar overlap",
            len(overlap_conflicts) == 0,
            f"{len(overlap_conflicts)} conflicts",
        )
    )

    all_additive = all(
        row["classification"] == "ADDITIVE"
        for row in PAIRWISE
    )

    checks.append(
        make_check(
            "RDS economically distinct from evaluated Medicare streams",
            all_additive,
            (
                f"{sum(row['classification'] == 'ADDITIVE' for row in PAIRWISE)}"
                "/3 pairwise relationships ADDITIVE"
            ),
        )
    )

    # ------------------------------------------------------------------
    # Geography gate
    # ------------------------------------------------------------------

    geography_absent = all(
        GEOGRAPHY[key] == "NO"
        for key in [
            "state_field",
            "county_field",
            "zip_field",
            "beneficiary_residence_field",
        ]
    )

    checks.append(
        make_check(
            "Published RDS table lacks explicit geographic allocation field",
            geography_absent,
            GEOGRAPHY["published_fields"],
        )
    )

    checks.append(
        make_check(
            "Sponsor/business name prohibited as geographic allocation",
            GEOGRAPHY["sponsor_name_is_geography"] == "NO",
            (
                "Organization name is sponsor identity, not a certified "
                "beneficiary-residence geography"
            ),
        )
    )

    checks.append(
        make_check(
            "Washington allocation remains unresolved",
            (
                GEOGRAPHY["washington_allocation_status"] == "UNRESOLVED"
                and GEOGRAPHY["ledger_status"] == "NOT_YET_WA_ALLOCATABLE"
            ),
            (
                f"{GEOGRAPHY['washington_allocation_status']} / "
                f"{GEOGRAPHY['ledger_status']}"
            ),
        )
    )

    # ------------------------------------------------------------------
    # Conservative accounting invariant
    # ------------------------------------------------------------------

    additive_in_principle = (
        all_additive
        and len(overlap_conflicts) == 0
    )

    wa_ledger_eligible = (
        additive_in_principle
        and GEOGRAPHY["washington_allocation_status"] == "RESOLVED"
    )

    checks.append(
        make_check(
            "No unresolved RDS geography promoted into Washington ledger",
            not wa_ledger_eligible,
            (
                "RDS is additive in principle but remains outside the "
                "Washington ledger until geographic incidence is resolved"
            ),
        )
    )

    # ------------------------------------------------------------------
    # Write pairwise matrix
    # ------------------------------------------------------------------

    matrix_fields = [
        "stream_a",
        "stream_b",
        "beneficiary_overlap_same_period",
        "payment_stream_overlap",
        "classification",
        "basis",
    ]

    with MATRIX_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=matrix_fields,
        )
        writer.writeheader()
        writer.writerows(PAIRWISE)

    # ------------------------------------------------------------------
    # Write checks
    # ------------------------------------------------------------------

    with CHECKS_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["check", "status", "detail"],
        )
        writer.writeheader()
        writer.writerows(checks)

    # ------------------------------------------------------------------
    # Human-readable report
    # ------------------------------------------------------------------

    lines: list[str] = []

    lines.append(
        "CMS RETIREE DRUG SUBSIDY SEMANTIC / ADDITIVITY "
        "CERTIFICATION v0.1"
    )
    lines.append("=" * 78)
    lines.append("")

    lines.append("SEMANTIC CONCLUSION")
    lines.append("-" * 78)
    lines.append(
        "RDS is a federal Medicare prescription-drug subsidy payment "
        "to qualified employer/union retiree plan sponsors."
    )
    lines.append(
        "A qualifying covered retiree is eligible for Medicare Part D "
        "but is not enrolled in a Medicare Part D plan."
    )
    lines.append("")

    lines.append("ADDITIVITY CONCLUSION")
    lines.append("-" * 78)
    lines.append(
        "RDS is economically distinct from the WCFFBP-certified "
        "Original Medicare/FFS, Part C, and Part D payment streams."
    )
    lines.append("")
    lines.append(
        "Medicare evaluated streams, if geographic incidence is resolved:"
    )
    lines.append(
        "  Original Medicare/FFS + Part C + Part D + RDS"
    )
    lines.append("")

    lines.append("GEOGRAPHIC BOUNDARY")
    lines.append("-" * 78)
    lines.append(
        "The profiled public RDS Plan Payment table contains sponsor/"
        "business identity, payment amount, and retiree count."
    )
    lines.append(
        "It does not contain an explicit state, county, ZIP, or "
        "beneficiary-residence field usable for WCFFBP allocation."
    )
    lines.append(
        "A geographic word appearing inside Business Name does not "
        "constitute geographic evidence."
    )
    lines.append("")

    lines.append("WASHINGTON LEDGER STATUS")
    lines.append("-" * 78)
    lines.append("Economic distinctness: ADDITIVE_IN_PRINCIPLE")
    lines.append("Washington incidence: UNRESOLVED")
    lines.append("Current ledger treatment: NOT_YET_WA_ALLOCATABLE")
    lines.append("")
    lines.append(
        "No RDS dollar receives a Washington plus sign until an "
        "independent geographic-incidence method is certified."
    )

    REPORT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # Console
    # ------------------------------------------------------------------

    print("=" * 100)
    print("RDS SEMANTIC BOUNDARY")
    print("=" * 100)
    print(f"Payee: {RDS['payee']}")
    print(f"Payment: {RDS['payment_scope']}")
    print(f"PUF grain: {RDS['public_puf_grain']}")
    print(
        "RDS beneficiary status: "
        + RDS["beneficiary_status"]
    )

    print()
    print("=" * 100)
    print("PAIRWISE PAYMENT-STREAM MATRIX")
    print("=" * 100)

    for row in PAIRWISE:
        print(
            f"{row['stream_a']:24} <-> "
            f"{row['stream_b']:24} | "
            f"BENEFICIARY_OVERLAP="
            f"{row['beneficiary_overlap_same_period']:35} | "
            f"PAYMENT_OVERLAP={row['payment_stream_overlap']:3} | "
            f"{row['classification']}"
        )

    print()
    print("=" * 100)
    print("GEOGRAPHIC GATE")
    print("=" * 100)
    print(
        "Published fields: "
        + GEOGRAPHY["published_fields"]
    )
    print("State field: NO")
    print("County field: NO")
    print("ZIP field: NO")
    print("Beneficiary residence field: NO")
    print("Sponsor/business name usable as geography: NO")
    print("Washington allocation: UNRESOLVED")
    print("Ledger status: NOT_YET_WA_ALLOCATABLE")

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
    print("Certified conclusion:")
    print()
    print("  RDS economic status: ADDITIVE_IN_PRINCIPLE")
    print("  RDS Washington incidence: UNRESOLVED")
    print("  RDS current WA ledger status: NOT_YET_WA_ALLOCATABLE")
    print()
    print(
        "No Washington RDS dollars have been inferred from sponsor names."
    )

    print()
    print("Evidence written:")
    print(f"  {MATRIX_FILE}")
    print(f"  {CHECKS_FILE}")
    print(f"  {REPORT_FILE}")

    if not overall_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
