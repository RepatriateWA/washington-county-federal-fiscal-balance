"""
CMS Original Medicare Geographic Variation Timing Certification v0.1
====================================================================

Purpose
-------
Certify the annual time basis of the CMS Original Medicare Geographic
Variation Public Use File (FFS GV PUF) used by WCFFBP.

Question
--------
What annual period does the source variable YEAR represent?

Certified interpretation
------------------------
CALENDAR_YEAR

Evidence
--------
1. The CMS data dictionary defines YEAR as "Year".
2. The CMS Methods Paper explicitly states that the FFS GV PUF covers
   calendar years.
3. The Methods Paper also describes beneficiary inclusion/exclusion
   criteria using the calendar-year period.

Important boundary
------------------
The preserved Methods Paper directly describes the May 2024 PUF vintage,
which covered calendar years through 2022. The current WCFFBP source file
extends through 2024.

This certification therefore establishes the documented annual-period
convention of the FFS GV PUF as CALENDAR_YEAR. It does not claim that the
preserved May 2024 Methods Paper directly documents the later 2023-2024
observations individually.

READ ONLY.

No:
    * payment reconstruction,
    * dollar modification,
    * CY-to-FFY conversion,
    * database write,
    * ledger inclusion,
    * extrapolation.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

DOC_ROOT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "documentation"
    / "validation"
    / "original_medicare_containment_evidence_v0_1"
)

DICTIONARY_TEXT = (
    DOC_ROOT
    / "cms_original_medicare_geographic_variation_dictionary_text_v0_1.txt"
)

METHODS_TEXT = (
    DOC_ROOT
    / "cms_original_medicare_geographic_variation_methods_text_v0_1.txt"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "validation"
    / "timing_certification_v0_1"
)

METHODOLOGY_VERSION = "CMS-OM-GV-TIMING-CERT-v0.1"


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required evidence artifact not found: {path}")

    return path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def write_csv(
    path: Path,
    rows: list[dict[str, str]],
    fieldnames: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_for_search(text: str) -> str:
    return " ".join(text.lower().split())


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dictionary_raw = read_text(DICTIONARY_TEXT)
    methods_raw = read_text(METHODS_TEXT)

    dictionary = normalize_for_search(dictionary_raw)
    methods = normalize_for_search(methods_raw)

    checks: list[dict[str, str]] = []

    def add_check(
        check_id: str,
        description: str,
        condition: bool,
        detail: str,
    ) -> None:
        checks.append(
            {
                "check_id": check_id,
                "description": description,
                "status": "PASS" if condition else "FAIL",
                "detail": detail,
            }
        )

    #
    # Evidence test 1:
    # The dictionary identifies YEAR as the annual variable.
    #
    # Text extraction can collapse table spacing, so test a few
    # conservative normalized variants rather than one formatting layout.
    #

    dictionary_year_evidence = any(
        phrase in dictionary
        for phrase in (
            "year year year",
            "year year geographic level",
            "variable name definition year year",
        )
    )

    add_check(
        "DICTIONARY_YEAR_FIELD",
        "CMS data dictionary identifies YEAR as the source year field",
        dictionary_year_evidence,
        (
            "Expected extracted dictionary evidence equivalent to "
            "Term Name=Year; Variable Name=YEAR; Definition=Year"
        ),
    )

    #
    # Evidence test 2:
    # The Methods Paper explicitly states the annual convention.
    #

    methods_calendar_year_statement = (
        "covers calendar years" in methods
    )

    add_check(
        "METHODS_CALENDAR_YEAR_STATEMENT",
        (
            "CMS Methods Paper explicitly states that the FFS GV PUF "
            "covers calendar years"
        ),
        methods_calendar_year_statement,
        'Expected phrase containing "covers calendar years"',
    )

    #
    # Evidence test 3:
    # The Methods Paper uses calendar-year language for the study
    # population, independently corroborating the annual convention.
    #

    calendar_year_population_evidence = (
        "during the calendar year" in methods
    )

    add_check(
        "METHODS_CALENDAR_YEAR_POPULATION",
        (
            "CMS Methods Paper applies calendar-year terminology to "
            "the FFS GV PUF study population"
        ),
        calendar_year_population_evidence,
        'Expected phrase containing "during the calendar year"',
    )

    #
    # Evidence test 4:
    # Guard against accidentally certifying an FFY convention.
    #
    # The document may contain incidental "FY" references concerning
    # unrelated quality-measure endorsement periods. Therefore we do not
    # require the entire document to contain no fiscal-year terminology.
    #
    # Instead, certification depends positively on the explicit statement
    # that the FFS GV PUF itself covers calendar years.
    #

    timing_basis = (
        "CALENDAR_YEAR"
        if methods_calendar_year_statement
        else "UNRESOLVED"
    )

    add_check(
        "TIMING_BASIS_RESOLUTION",
        "Source annual-period convention resolves to CALENDAR_YEAR",
        timing_basis == "CALENDAR_YEAR",
        f"resolved_timing_basis={timing_basis}",
    )

    #
    # Preserve the vintage limitation explicitly.
    #

    preserved_methods_through_2022 = (
        "calendar years 2007-2022" in methods
        or "data for 2007-2022" in methods
    )

    add_check(
        "METHODS_VINTAGE_BOUNDARY",
        (
            "Preserved Methods Paper is recognized as directly "
            "documenting the PUF through 2022"
        ),
        preserved_methods_through_2022,
        (
            "Later 2023-2024 observations inherit the documented "
            "PUF annual-period convention; they are not individually "
            "documented by the preserved May 2024 Methods Paper"
        ),
    )

    overall_pass = all(
        row["status"] == "PASS"
        for row in checks
    )

    certification_status = (
        "CERTIFIED_CALENDAR_YEAR"
        if overall_pass
        else "NOT_CERTIFIED"
    )

    #
    # Machine-readable certification artifact.
    #

    certification_rows = [
        {
            "source_family": "CMS_ORIGINAL_MEDICARE",
            "source_dataset": (
                "ORIGINAL_MEDICARE_GEOGRAPHIC_VARIATION_PUF"
            ),
            "source_year_variable": "YEAR",
            "timing_basis": timing_basis,
            "timing_certification_status": certification_status,
            "dictionary_definition": "Year",
            "methods_document_period_language": "calendar years",
            "preserved_methods_document_direct_through_year": "2022",
            "current_wcffbp_source_through_year": "2024",
            "later_year_timing_treatment": (
                "SAME_DOCUMENTED_DATASET_ANNUAL_PERIOD_CONVENTION"
            ),
            "cy_to_ffy_conversion": "NOT_PERFORMED",
            "ledger_authorization": "NOT_AUTHORIZED_BY_THIS_CERTIFICATION",
            "methodology_version": METHODOLOGY_VERSION,
        }
    ]

    certification_path = (
        OUTPUT_DIR
        / "cms_original_medicare_timing_certification_v0_1.csv"
    )

    checks_path = (
        OUTPUT_DIR
        / "cms_original_medicare_timing_checks_v0_1.csv"
    )

    report_path = (
        OUTPUT_DIR
        / "cms_original_medicare_timing_report_v0_1.txt"
    )

    evidence_path = (
        OUTPUT_DIR
        / "cms_original_medicare_timing_evidence_v0_1.csv"
    )

    write_csv(
        certification_path,
        certification_rows,
        list(certification_rows[0].keys()),
    )

    write_csv(
        checks_path,
        checks,
        [
            "check_id",
            "description",
            "status",
            "detail",
        ],
    )

    evidence_rows = [
        {
            "evidence_id": "DICTIONARY_YEAR",
            "source_artifact": str(
                DICTIONARY_TEXT.relative_to(REPO_ROOT)
            ),
            "source_sha256": sha256_file(DICTIONARY_TEXT),
            "evidence_role": "SOURCE_VARIABLE_DEFINITION",
            "evidence_summary": (
                "CMS dictionary defines Term Name Year, "
                "Variable Name YEAR, Definition Year."
            ),
        },
        {
            "evidence_id": "METHODS_CALENDAR_YEAR",
            "source_artifact": str(
                METHODS_TEXT.relative_to(REPO_ROOT)
            ),
            "source_sha256": sha256_file(METHODS_TEXT),
            "evidence_role": "ANNUAL_PERIOD_DEFINITION",
            "evidence_summary": (
                "CMS Methods Paper explicitly states that the "
                "FFS GV PUF covers calendar years."
            ),
        },
        {
            "evidence_id": "METHODS_STUDY_POPULATION",
            "source_artifact": str(
                METHODS_TEXT.relative_to(REPO_ROOT)
            ),
            "source_sha256": sha256_file(METHODS_TEXT),
            "evidence_role": "CORROBORATING_TIMING_EVIDENCE",
            "evidence_summary": (
                "CMS Methods Paper describes beneficiary inclusion "
                "using the calendar-year period."
            ),
        },
    ]

    write_csv(
        evidence_path,
        evidence_rows,
        [
            "evidence_id",
            "source_artifact",
            "source_sha256",
            "evidence_role",
            "evidence_summary",
        ],
    )

    #
    # Human-readable report.
    #

    lines: list[str] = []

    lines.append(
        "CMS ORIGINAL MEDICARE GEOGRAPHIC VARIATION "
        "TIMING CERTIFICATION v0.1"
    )
    lines.append("=" * 100)
    lines.append("")
    lines.append("READ-ONLY DOCUMENTARY CERTIFICATION")
    lines.append("")
    lines.append(
        "No payment reconstruction, dollar modification, CY-to-FFY "
        "conversion, database write, extrapolation, or ledger inclusion."
    )
    lines.append("")
    lines.append("QUESTION")
    lines.append("-" * 100)
    lines.append(
        "What annual period does the CMS Original Medicare "
        "Geographic Variation PUF YEAR variable represent?"
    )
    lines.append("")
    lines.append("DOCUMENTARY EVIDENCE")
    lines.append("-" * 100)
    lines.append(
        "Dictionary: YEAR is defined as Year."
    )
    lines.append(
        "Methods Paper: the FFS GV PUF explicitly covers calendar years."
    )
    lines.append(
        "Methods Paper: study-population descriptions independently "
        "use calendar-year terminology."
    )
    lines.append("")
    lines.append("VINTAGE BOUNDARY")
    lines.append("-" * 100)
    lines.append(
        "The preserved May 2024 Methods Paper directly documents the "
        "PUF through calendar year 2022."
    )
    lines.append(
        "The current WCFFBP source extends through 2024. This "
        "certification applies the documented dataset annual-period "
        "convention to those later observations; it does not claim that "
        "the preserved Methods Paper individually documents CY2023 or "
        "CY2024."
    )
    lines.append("")
    lines.append("VALIDATION CHECKS")
    lines.append("-" * 100)

    for check in checks:
        lines.append(
            f"{check['status']:4s}  "
            f"{check['check_id']}: "
            f"{check['description']} "
            f"[{check['detail']}]"
        )

    lines.append("")
    lines.append("TIMING INTERPRETATION")
    lines.append("-" * 100)

    if overall_pass:
        lines.append(
            "CMS Original Medicare Geographic Variation YEAR "
            "is certified as CALENDAR_YEAR."
        )
        lines.append("")
        lines.append(
            "Accordingly, the WCFFBP Original Medicare annual "
            "observations may be aligned by calendar year with the "
            "certified Part C and Part D calendar-month reconstructions."
        )
        lines.append("")
        lines.append(
            "No conversion from calendar year to federal fiscal year "
            "is performed or authorized by this certification."
        )
    else:
        lines.append(
            "The annual-period convention was not sufficiently "
            "established by the preserved documentary evidence."
        )

    lines.append("")
    lines.append("CERTIFICATION RESULT")
    lines.append("-" * 100)

    if overall_pass:
        lines.append(
            f"{METHODOLOGY_VERSION} — PASS"
        )
        lines.append("")
        lines.append(
            "ORIGINAL MEDICARE YEAR BASIS: CERTIFIED_CALENDAR_YEAR"
        )
        lines.append(
            "MEDICARE CORE TEMPORAL ALIGNMENT: "
            "SUPPORTED FOR COMMON CALENDAR-YEAR ACCOUNTING"
        )
        lines.append(
            "FINAL FEDERAL-INFLOW LEDGER INCLUSION: "
            "NOT AUTHORIZED BY THIS CERTIFICATION"
        )
    else:
        lines.append(
            f"{METHODOLOGY_VERSION} — FAIL"
        )
        lines.append("")
        lines.append(
            "ORIGINAL MEDICARE YEAR BASIS: NOT CERTIFIED"
        )

    lines.append("")

    report_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\n".join(lines))

    if not overall_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()