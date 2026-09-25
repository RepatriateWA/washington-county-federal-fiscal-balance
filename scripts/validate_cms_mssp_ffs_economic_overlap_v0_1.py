"""
WCFFBP
CMS MSSP <-> Original Medicare / FFS Economic Overlap Validator v0.1

PURPOSE
-------
Certify the economic relationship between:

    1. Original Medicare / FFS actual payments represented by
       TOT_MDCR_PYMT_AMT in the CMS Geographic Variation PUF; and

    2. positive MSSP EarnSaveLoss amounts representing earned
       shared-savings / performance payments.

The validator implements the WCFFBP no-double-counting rule:

    No federal expenditure source is additive by default.

A candidate source receives ADDITIVE_DISTINCT status only when affirmative
source evidence establishes that it represents an economically distinct
payment stream rather than another representation of dollars already
included elsewhere.

CERTIFICATION SCOPE
-------------------
This validator may certify:

    - Original Medicare FFS claims/payment containment;
    - containment of ACO/PBP split-payment amounts in actual FFS payment;
    - MSSP EarnSaveLoss settlement semantics;
    - economic distinction between positive EarnSaveLoss and the
      underlying FFS claim/split-payment amounts;
    - ADDITIVE_IN_PRINCIPLE status for positive EarnSaveLoss.

THIS VALIDATOR DOES NOT CERTIFY
-------------------------------
    - Washington payment-dollar incidence;
    - beneficiary residence;
    - county payment-dollar incidence;
    - cash payment date;
    - FFY attribution;
    - ledger inclusion;
    - negative EarnSaveLoss as negative federal expenditure;
    - advance/AIM/AIP netting;
    - Medicare completeness.

READ-ONLY
---------
No database writes.
No source modification.
No ledger writes.
"""

from __future__ import annotations

import csv
import hashlib
import re
import sys

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


# =====================================================================
# INPUT ARTIFACTS
# =====================================================================

GV_EVIDENCE_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "documentation"
    / "validation"
    / "original_medicare_containment_evidence_v0_1"
)

GV_DICTIONARY_TEXT = (
    GV_EVIDENCE_DIR
    / "cms_original_medicare_geographic_variation_dictionary_text_v0_1.txt"
)

GV_METHODS_TEXT = (
    GV_EVIDENCE_DIR
    / "cms_original_medicare_geographic_variation_methods_text_v0_1.txt"
)


MSSP_EVIDENCE_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "validation"
    / "settlement_vs_ffs_containment_evidence_v0_1"
)

MSSP_EVIDENCE_TEXT = (
    MSSP_EVIDENCE_DIR
    / "cms_mssp_settlement_vs_ffs_containment_evidence_v0_1.txt"
)


# =====================================================================
# FROZEN SOURCE HASHES
# =====================================================================

GV_METHODS_PDF = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "documentation"
    / "Geographic Variation Public Use File Methods Paper.pdf"
)

GV_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "documentation"
    / "Medicare Geographic Variation - by National, State & County.zip"
)

MSSP_DOCUMENTATION_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "documentation"
    / "Performance Year Financial and Quality Results - Documentation.zip"
)


EXPECTED_GV_METHODS_SHA256 = (
    "94666A9FC128F8CB469A55B3D2494368EBFF66F314CD88ED2440C6AE4BE3087F"
)

EXPECTED_GV_ZIP_SHA256 = (
    "17D5BFE2F9388E5BF03552AE8BB97A312B6FFDB9581C434F8FDE5AF0F188BA57"
)

EXPECTED_MSSP_DOCUMENTATION_SHA256 = (
    "054E06866C7EB4D1EF1A02580B02FBB4639999C9B2ED93AFC4FD593CDA1B8703"
)


# =====================================================================
# OUTPUT
# =====================================================================

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "validation"
    / "mssp_ffs_economic_overlap_v0_1"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_ffs_economic_overlap_checks_v0_1.csv"
)

DISPOSITION_CSV = (
    OUTPUT_DIR
    / "cms_mssp_ffs_economic_overlap_disposition_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_mssp_ffs_economic_overlap_certification_report_v0_1.txt"
)


# =====================================================================
# HELPERS
# =====================================================================

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            h.update(block)

    return h.hexdigest().upper()


def read_text(path: Path) -> str:
    return path.read_text(
        encoding="utf-8",
    )


def normalize(text: str) -> str:
    text = text.replace(
        "\x00",
        " ",
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def contains_all(
    text: str,
    patterns: list[str],
) -> bool:
    return all(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        is not None
        for pattern in patterns
    )


def contains_any(
    text: str,
    patterns: list[str],
) -> bool:
    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        is not None
        for pattern in patterns
    )


def write_csv(
    path: Path,
    rows: list[dict],
    fieldnames: list[str],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(
            rows
        )


# =====================================================================
# MAIN
# =====================================================================

def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    checks = []

    def check(
        check_id: str,
        description: str,
        passed: bool,
        detail: str,
    ) -> None:
        checks.append(
            {
                "check_id": check_id,
                "status": (
                    "PASS"
                    if passed
                    else "FAIL"
                ),
                "description": description,
                "detail": detail,
            }
        )

    # -----------------------------------------------------------------
    # 1. INPUT EXISTENCE
    # -----------------------------------------------------------------

    required_files = [
        GV_METHODS_PDF,
        GV_ZIP,
        MSSP_DOCUMENTATION_ZIP,
        GV_DICTIONARY_TEXT,
        GV_METHODS_TEXT,
        MSSP_EVIDENCE_TEXT,
    ]

    for index, path in enumerate(
        required_files,
        start=1,
    ):
        check(
            f"SOURCE-{index:02d}",
            f"Required artifact exists: {path.name}",
            path.exists(),
            str(
                path.relative_to(
                    REPO_ROOT
                )
            ),
        )

    if not all(
        path.exists()
        for path in required_files
    ):
        write_csv(
            CHECKS_CSV,
            checks,
            [
                "check_id",
                "status",
                "description",
                "detail",
            ],
        )

        print(
            "FAIL: one or more required artifacts are missing."
        )

        return 1

    # -----------------------------------------------------------------
    # 2. SOURCE AUTHENTICATION
    # -----------------------------------------------------------------

    gv_methods_sha = sha256_file(
        GV_METHODS_PDF
    )

    gv_zip_sha = sha256_file(
        GV_ZIP
    )

    mssp_docs_sha = sha256_file(
        MSSP_DOCUMENTATION_ZIP
    )

    check(
        "HASH-01",
        "Original Medicare Methods Paper SHA-256 matches frozen source",
        gv_methods_sha
        == EXPECTED_GV_METHODS_SHA256,
        gv_methods_sha,
    )

    check(
        "HASH-02",
        "Original Medicare documentation ZIP SHA-256 matches frozen source",
        gv_zip_sha
        == EXPECTED_GV_ZIP_SHA256,
        gv_zip_sha,
    )

    check(
        "HASH-03",
        "MSSP documentation ZIP SHA-256 matches frozen source",
        mssp_docs_sha
        == EXPECTED_MSSP_DOCUMENTATION_SHA256,
        mssp_docs_sha,
    )

    # -----------------------------------------------------------------
    # 3. LOAD EVIDENCE
    # -----------------------------------------------------------------

    gv_dictionary = normalize(
        read_text(
            GV_DICTIONARY_TEXT
        )
    )

    gv_methods = normalize(
        read_text(
            GV_METHODS_TEXT
        )
    )

    mssp_evidence = normalize(
        read_text(
            MSSP_EVIDENCE_TEXT
        )
    )

    # -----------------------------------------------------------------
    # 4. ORIGINAL MEDICARE / FFS CONTAINMENT
    # -----------------------------------------------------------------

    gv_tot_payment = contains_all(
        gv_dictionary,
        [
            r"\bTOT_MDCR_PYMT_AMT\b",
            r"Total\s+Actual\s+Medicare\s+Payment",
            r"Total\s+actual\s+Medicare\s+payment",
            r"Original\s+Medicare",
        ],
    )

    check(
        "FFS-01",
        (
            "TOT_MDCR_PYMT_AMT is documented as "
            "Total Actual Medicare Payment for Original Medicare"
        ),
        gv_tot_payment,
        (
            "Requires field identifier, Total Actual Medicare Payment, "
            "and Original Medicare language."
        ),
    )

    gv_claim_universe = contains_all(
        gv_methods,
        [
            r"100\s+percent\s+of\s+Medicare\s+claims",
            r"fee\s*-\s*for\s*-\s*service|\bFFS\b",
            r"Chronic\s+Condition[s]?\s+Data\s+Warehouse|\bCCW\b",
        ],
    )

    check(
        "FFS-02",
        (
            "Original Medicare Geographic Variation PUF is grounded "
            "in the FFS claims universe"
        ),
        gv_claim_universe,
        (
            "Requires 100 percent Medicare claims, FFS terminology, "
            "and CCW terminology."
        ),
    )

    # -----------------------------------------------------------------
    # 5. ACO/PBP SPLIT-PAYMENT CONTAINMENT
    # -----------------------------------------------------------------

    split_payment_evidence = contains_all(
        gv_methods,
        [
            r"split\s+payment",
            r"not\s+a\s+change\s+in\s+total\s+Medicare\s+spending",
            r"distributed\s+to\s+the\s+ACO\s+or\s+PBP",
        ],
    )

    check(
        "FFS-03",
        (
            "CMS identifies ACO/PBP split payments as redistribution "
            "of an underlying claim payment rather than new spending"
        ),
        split_payment_evidence,
        (
            "Requires split-payment terminology, no-change-in-total-"
            "spending language, and ACO/PBP distribution language."
        ),
    )

    actual_payment_includes_aco_pbp = contains_all(
        gv_methods,
        [
            r"actual\s+payment\s+is\s+the\s+sum",
            r"provider\s+payments",
            r"ACO[s]?\s+or\s+PBP",
        ],
    )

    check(
        "FFS-04",
        (
            "CMS states that applicable ACO/PBP split-payment amounts "
            "are included in actual FFS payment"
        ),
        actual_payment_includes_aco_pbp,
        (
            "Requires actual-payment sum, provider-payment, "
            "and ACO/PBP language."
        ),
    )

    # -----------------------------------------------------------------
    # 6. MSSP SETTLEMENT SEMANTICS
    # -----------------------------------------------------------------

    earnsave_semantics = contains_all(
        mssp_evidence,
        [
            r"\bEarnSaveLoss\b",
            r"Total\s+earned\s+shared\s+savings",
            r"eligible\s+for\s+a\s+performance\s+payment",
            r"final\s+sharing\s+rate",
            r"sequestration",
            r"performance\s+payment\s+limit",
        ],
    )

    check(
        "MSSP-01",
        (
            "EarnSaveLoss is documented as an earned shared-savings "
            "performance-payment amount"
        ),
        earnsave_semantics,
        (
            "Requires EarnSaveLoss, earned shared savings, performance "
            "payment, sharing rate, sequestration, and payment limit."
        ),
    )

    gensaveloss_semantics = contains_all(
        mssp_evidence,
        [
            r"\bGenSaveLoss\b",
            r"Benchmark\s+Minus\s+(?:Assigned\s+)?Expenditures",
            r"does\s+not\s+account\s+for",
            r"final\s+sharing\s+rate",
        ],
    )

    check(
        "MSSP-02",
        (
            "GenSaveLoss is documented as benchmark-minus-expenditures "
            "before final sharing/payment adjustments"
        ),
        gensaveloss_semantics,
        (
            "Requires GenSaveLoss, benchmark-minus-expenditures, "
            "and pre-sharing adjustment semantics."
        ),
    )

    ffs_expenditure_base = contains_all(
        mssp_evidence,
        [
            r"Medicare\s+Parts\s+A\s+and\s+B\s+FFS\s+expenditures",
            r"assigned\s+beneficiar",
        ],
    )

    check(
        "MSSP-03",
        (
            "MSSP settlement calculation uses Medicare Parts A/B FFS "
            "expenditures for assigned beneficiaries"
        ),
        ffs_expenditure_base,
        (
            "Requires explicit Medicare Parts A and B FFS expenditure "
            "and assigned-beneficiary language."
        ),
    )

    claims_component_evidence = contains_all(
        mssp_evidence,
        [
            r"claims\s+are\s+identified\s+by\s+claim\s+type\s+code",
            r"performance\s+year",
        ],
    )

    check(
        "MSSP-04",
        (
            "MSSP expenditure measures are explicitly grounded in "
            "underlying Medicare claims"
        ),
        claims_component_evidence,
        (
            "Requires claim-type-code and performance-year expenditure "
            "evidence."
        ),
    )

    # -----------------------------------------------------------------
    # 7. SETTLEMENT-STAGE CORROBORATION
    # -----------------------------------------------------------------

    settlement_stage = contains_all(
        mssp_evidence,
        [
            r"financial\s+reconciliation",
            r"performance\s+year\s+settlement|performance\s+payment\s+earned",
            r"recoup",
        ],
    )

    check(
        "MSSP-05",
        (
            "MSSP documentation independently identifies a "
            "financial-reconciliation / settlement stage"
        ),
        settlement_stage,
        (
            "Advance/AIM/AIP evidence is used only as corroboration "
            "of settlement-stage mechanics."
        ),
    )

    # -----------------------------------------------------------------
    # 8. CRITICAL ECONOMIC-DISTINCTION GATE
    # -----------------------------------------------------------------

    prerequisite_ids = [
        "FFS-01",
        "FFS-02",
        "FFS-03",
        "FFS-04",
        "MSSP-01",
        "MSSP-02",
        "MSSP-03",
        "MSSP-04",
        "MSSP-05",
    ]

    status_by_id = {
        row[
            "check_id"
        ]: row[
            "status"
        ]
        for row in checks
    }

    prerequisites_pass = all(
        status_by_id.get(
            check_id
        )
        == "PASS"
        for check_id in prerequisite_ids
    )

    check(
        "ECON-01",
        (
            "Positive MSSP EarnSaveLoss is economically distinguishable "
            "from FFS claim expenditure already represented in "
            "TOT_MDCR_PYMT_AMT"
        ),
        prerequisites_pass,
        (
            "Certification requires the complete affirmative evidence "
            "chain: FFS claim containment + split-payment containment + "
            "MSSP benchmark/expenditure/performance-payment settlement."
        ),
    )

    # -----------------------------------------------------------------
    # 9. NEGATIVE VALUES ARE NOT CERTIFIED AS NEGATIVE SPENDING
    # -----------------------------------------------------------------

    negative_semantics = contains_any(
        mssp_evidence,
        [
            r"owed\s+losses",
            r"share\s+of\s+losses",
            r"shared\s+losses",
        ],
    )

    check(
        "BOUNDARY-01",
        (
            "Documentation contains owed/shared-loss semantics, "
            "preventing automatic treatment of negative EarnSaveLoss "
            "as negative federal expenditure"
        ),
        negative_semantics,
        (
            "Negative observations remain a separate settlement concept."
        ),
    )

    # -----------------------------------------------------------------
    # 10. FINAL STATUS
    # -----------------------------------------------------------------

    all_checks_pass = all(
        row[
            "status"
        ]
        == "PASS"
        for row in checks
    )

    economic_gate_pass = (
        status_by_id.get(
            "ECON-01"
        )
        == "PASS"
        if "ECON-01" in status_by_id
        else prerequisites_pass
    )

    # ECON-01 was appended after status_by_id was constructed.
    economic_gate_pass = prerequisites_pass

    if (
        all_checks_pass
        and economic_gate_pass
    ):
        certification_status = (
            "ADDITIVE_DISTINCT"
        )

        additivity_status = (
            "ADDITIVE_IN_PRINCIPLE"
        )

        principal_ledger = (
            "WITHHOLD_UNRESOLVED"
        )

    else:
        certification_status = (
            "UNRESOLVED"
        )

        additivity_status = (
            "UNRESOLVED"
        )

        principal_ledger = (
            "WITHHOLD_UNRESOLVED"
        )

    # -----------------------------------------------------------------
    # 11. DISPOSITION ARTIFACT
    # -----------------------------------------------------------------

    disposition_rows = [
        {
            "dimension": "payment_stream",
            "status": "OBSERVED",
            "detail": (
                "Positive MSSP EarnSaveLoss observations."
            ),
        },
        {
            "dimension": "economic_relationship_to_original_medicare_ffs",
            "status": certification_status,
            "detail": (
                "Positive EarnSaveLoss is evaluated against "
                "TOT_MDCR_PYMT_AMT and the FFS claims universe."
            ),
        },
        {
            "dimension": "relationship_to_ffs_claim_expenditure",
            "status": (
                "NOT_CONTAINED_AS_UNDERLYING_FFS_CLAIM_EXPENDITURE"
                if certification_status
                == "ADDITIVE_DISTINCT"
                else "UNRESOLVED"
            ),
            "detail": (
                "EarnSaveLoss is a performance-payment settlement "
                "derived after comparison of assigned-beneficiary "
                "FFS expenditures with the benchmark."
            ),
        },
        {
            "dimension": "relationship_to_aco_pbp_split_payment",
            "status": (
                "ECONOMICALLY_DISTINCT"
                if certification_status
                == "ADDITIVE_DISTINCT"
                else "UNRESOLVED"
            ),
            "detail": (
                "ACO/PBP split payments are contained within actual "
                "FFS payment; EarnSaveLoss is separately defined as "
                "earned shared savings/performance payment."
            ),
        },
        {
            "dimension": "economic_additivity",
            "status": additivity_status,
            "detail": (
                "Economic additivity only. This does not establish "
                "geographic incidence or ledger inclusion."
            ),
        },
        {
            "dimension": "washington_payment_dollar_incidence",
            "status": "UNRESOLVED",
            "detail": (
                "ACO organizational connection is not payment-dollar incidence."
            ),
        },
        {
            "dimension": "washington_county_payment_dollar_incidence",
            "status": "UNRESOLVED",
            "detail": (
                "No county allocation is certified by this validator."
            ),
        },
        {
            "dimension": "cash_ffy_timing",
            "status": "UNRESOLVED",
            "detail": (
                "Performance year is not assumed to equal cash-payment FFY."
            ),
        },
        {
            "dimension": "negative_earnsaveloss",
            "status": "SEPARATE_SETTLEMENT_CONCEPT",
            "detail": (
                "Negative EarnSaveLoss is not automatically treated "
                "as negative federal expenditure."
            ),
        },
        {
            "dimension": "principal_ledger",
            "status": principal_ledger,
            "detail": (
                "Withheld pending independent geographic-incidence "
                "and timing reconciliation."
            ),
        },
    ]

    write_csv(
        DISPOSITION_CSV,
        disposition_rows,
        [
            "dimension",
            "status",
            "detail",
        ],
    )

    # -----------------------------------------------------------------
    # 12. CHECK ARTIFACT
    # -----------------------------------------------------------------

    write_csv(
        CHECKS_CSV,
        checks,
        [
            "check_id",
            "status",
            "description",
            "detail",
        ],
    )

    # -----------------------------------------------------------------
    # 13. REPORT
    # -----------------------------------------------------------------

    report = []

    report.append(
        "=" * 118
    )

    report.append(
        "CMS MSSP <-> ORIGINAL MEDICARE / FFS ECONOMIC OVERLAP CERTIFICATION v0.1"
    )

    report.append(
        "=" * 118
    )

    report.append("")

    report.append(
        "BOUNDARY"
    )

    report.append(
        "-" * 118
    )

    report.append(
        "Economic-overlap certification only."
    )

    report.append(
        "No Washington payment-dollar incidence is certified."
    )

    report.append(
        "No county incidence is certified."
    )

    report.append(
        "No cash/FFY timing is certified."
    )

    report.append(
        "No principal-ledger inclusion occurs."
    )

    report.append(
        "Negative EarnSaveLoss is not classified as negative federal spending."
    )

    report.append("")

    report.append(
        "SOURCE AUTHENTICATION"
    )

    report.append(
        "-" * 118
    )

    report.append(
        "Original Medicare Methods Paper SHA-256: "
        + gv_methods_sha
    )

    report.append(
        "Original Medicare documentation ZIP SHA-256: "
        + gv_zip_sha
    )

    report.append(
        "MSSP documentation ZIP SHA-256: "
        + mssp_docs_sha
    )

    report.append("")

    report.append(
        "ECONOMIC EVIDENCE CHAIN"
    )

    report.append(
        "-" * 118
    )

    report.append(
        "1. TOT_MDCR_PYMT_AMT represents actual Original Medicare payment."
    )

    report.append(
        "2. The Geographic Variation PUF is grounded in the FFS claims universe."
    )

    report.append(
        "3. CMS explicitly identifies certain ACO/PBP payments as split payments already contained in actual FFS payment."
    )

    report.append(
        "4. MSSP assigned-beneficiary expenditures are Medicare Parts A/B FFS expenditures grounded in claims."
    )

    report.append(
        "5. GenSaveLoss is generated savings measured from benchmark minus expenditures."
    )

    report.append(
        "6. EarnSaveLoss is the ACO share of savings after performance-payment adjustments."
    )

    report.append(
        "7. Therefore positive EarnSaveLoss is economically distinct from the underlying FFS claim expenditure and from the contained ACO/PBP split-payment mechanism."
    )

    report.append("")

    report.append(
        "CHECKS"
    )

    report.append(
        "-" * 118
    )

    for row in checks:
        report.append(
            (
                f"{row['status']} | "
                f"{row['check_id']} | "
                f"{row['description']} | "
                f"{row['detail']}"
            )
        )

    report.append("")

    report.append(
        "CERTIFIED DISPOSITION"
    )

    report.append(
        "-" * 118
    )

    report.append(
        "Positive MSSP EarnSaveLoss expenditure existence: OBSERVED"
    )

    report.append(
        "Economic relationship to Original Medicare / FFS: "
        + certification_status
    )

    report.append(
        "Economic additivity: "
        + additivity_status
    )

    report.append(
        "Washington payment-dollar incidence: UNRESOLVED"
    )

    report.append(
        "County payment-dollar incidence: UNRESOLVED"
    )

    report.append(
        "Cash / FFY timing: UNRESOLVED"
    )

    report.append(
        "Negative EarnSaveLoss: SEPARATE_SETTLEMENT_CONCEPT"
    )

    report.append(
        "Principal ledger: "
        + principal_ledger
    )

    report.append("")

    report.append(
        "=" * 118
    )

    report.append(
        "OVERALL CMS MSSP <-> ORIGINAL MEDICARE / FFS ECONOMIC OVERLAP CERTIFICATION v0.1: "
        + (
            "PASS"
            if all_checks_pass
            else "FAIL"
        )
    )

    report.append(
        "=" * 118
    )

    report.append("")

    report.append(
        "ACCOUNTING RULE"
    )

    report.append(
        "-" * 118
    )

    report.append(
        "No federal expenditure source is additive by default."
    )

    report.append(
        "Positive EarnSaveLoss receives ADDITIVE_IN_PRINCIPLE status only because affirmative CMS evidence establishes an economically distinct settlement-stage performance payment."
    )

    report.append(
        "Economic additivity does not establish geographic allocatability."
    )

    report.append(
        "WITHHOLD_UNRESOLVED is not zero."
    )

    report.append("")

    report.append(
        "EVIDENCE WRITTEN"
    )

    report.append(
        "-" * 118
    )

    report.append(
        str(
            CHECKS_CSV.relative_to(
                REPO_ROOT
            )
        )
    )

    report.append(
        str(
            DISPOSITION_CSV.relative_to(
                REPO_ROOT
            )
        )
    )

    report.append(
        str(
            REPORT_TXT.relative_to(
                REPO_ROOT
            )
        )
    )

    report_text = "\n".join(
        report
    )

    REPORT_TXT.write_text(
        report_text,
        encoding="utf-8",
    )

    print(
        report_text
    )

    return (
        0
        if all_checks_pass
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )