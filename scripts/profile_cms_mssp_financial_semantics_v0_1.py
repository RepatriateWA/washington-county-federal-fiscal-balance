"""
WCFFBP
CMS MSSP Financial Semantics Profiler v0.1

Purpose
-------
Build a reproducible semantic crosswalk between the official CMS
Medicare Shared Savings Program (MSSP) Performance Year Financial and
Quality Results CSV fields and the official CMS data dictionaries.

This is a READ-ONLY semantic evidence profiler.

It DOES:
    - read the preserved CMS financial ZIP directly;
    - read the preserved CMS documentation ZIP directly;
    - map each performance period to the appropriate CMS dictionary;
    - verify that selected financial fields actually occur in the CSV;
    - locate those variable names in the governing CMS dictionary;
    - capture the dictionary text surrounding each variable;
    - classify documentation coverage, not accounting treatment;
    - preserve 2019 and 2019A as separate performance periods;
    - preserve PY2024/document-vintage distinction.

It DOES NOT:
    - calculate Washington dollars;
    - select Washington ACOs;
    - infer payment-dollar geography;
    - infer economic additivity;
    - net advance payments or recoupments;
    - reconstruct cash timing;
    - write to PostgreSQL;
    - authorize ledger inclusion.

Fail-closed rule
----------------
A financial field cannot advance to accounting interpretation unless
the field exists in the applicable source CSV and its governing CMS
documentation contains an identifiable definition/evidence context.

No field is additive merely because its name contains payment,
savings, earned, advance, or recoupment.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]

FINANCIAL_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "Performance Year Financial and Quality Results.zip"
)

DOCUMENTATION_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "documentation"
    / "Performance Year Financial and Quality Results - Documentation.zip"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "validation"
    / "financial_semantics_v0_1"
)

CROSSWALK_CSV = (
    OUTPUT_DIR
    / "cms_mssp_financial_semantic_crosswalk_v0_1.csv"
)

FIELD_INVENTORY_CSV = (
    OUTPUT_DIR
    / "cms_mssp_financial_field_inventory_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_financial_semantics_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_mssp_financial_semantics_report_v0_1.txt"
)


PERIODS = [
    "2015",
    "2016",
    "2017",
    "2018",
    "2019",
    "2019A",
    "2020",
    "2021",
    "2022",
    "2023",
    "2024",
]


# Fields central to the accounting question.
#
# Some may not occur in every year.  Absence is evidence and is
# recorded rather than treated as failure unless a field that we know
# from the certified structural profile should exist is undocumented.
TARGET_FIELDS = [
    "GenSaveLoss",
    "EarnSaveLoss",
    "Adv_Pay",
    "Adv_Pay_Amt",
    "Adv_Pay_Recoup",
    "AIM",
    "AIPRecoup",
]


# Structural expectations established by the certified v0.1 source
# profile.  These are intentionally narrow.
EXPECTED_FIELD_PERIODS = {
    "GenSaveLoss": set(PERIODS),
    "EarnSaveLoss": set(PERIODS),

    "Adv_Pay": {
        "2015", "2016", "2017", "2018",
        "2019", "2019A", "2020", "2021",
    },

    "Adv_Pay_Amt": {
        "2015", "2016", "2017", "2018",
        "2019", "2019A", "2020", "2021",
    },

    "Adv_Pay_Recoup": {
        "2015", "2016", "2017", "2018",
        "2019", "2019A", "2020", "2021",
    },

    "AIM": {
        "2016", "2017", "2018",
        "2019", "2019A", "2020", "2021",
    },

    "AIPRecoup": {
        "2024",
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def financial_period(member_name: str) -> str:
    text = member_name.replace("\\", "/").lower()

    if (
        "2019_off-cycle_1" in text
        or "2019_off_cycle_1" in text
        or "2019a" in text
    ):
        return "2019A"

    for year in range(2015, 2025):
        if re.search(
            rf"(?<!\d){year}(?!\d)",
            text,
        ):
            return str(year)

    return "UNRESOLVED"


def documentation_archive_period(member_name: str) -> str:
    text = member_name.replace("\\", "/").lower()

    if "2019_off-cycle_1" in text:
        return "2019A"

    match = re.search(r"/(20\d{2})/", text)

    if match:
        return match.group(1)

    return "UNRESOLVED"


def decode_csv(data: bytes) -> str:
    for encoding in [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    ]:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise RuntimeError(
        "Unable to decode financial CSV."
    )


def read_csv_header(data: bytes) -> list[str]:
    text = decode_csv(data)

    reader = csv.reader(
        io.StringIO(
            text,
            newline="",
        )
    )

    try:
        return next(reader)
    except StopIteration:
        return []


def extract_pdf_text(data: bytes) -> tuple[str, int]:
    reader = PdfReader(
        io.BytesIO(data)
    )

    pages = []

    for page in reader.pages:
        try:
            pages.append(
                page.extract_text() or ""
            )
        except Exception:
            pages.append("")

    return "\n".join(pages), len(reader.pages)


def governing_dictionary_kind(
    period: str,
) -> str:
    if period in {
        "2015",
        "2016",
        "2017",
        "2018",
        "2019",
        "2019A",
        "2020",
    }:
        return "2013-2020"

    return period


def dictionary_matches(
    member_name: str,
    period: str,
    text: str,
) -> bool:
    """
    Establish governing dictionary using both filename and extracted
    document identity.

    PY2024 is deliberately handled by document content because its
    filename contains 2025_Nov2025 while the first page identifies it
    as the Performance Year 2024 data dictionary.
    """
    filename = Path(
        member_name
    ).name.lower()

    normalized_text = normalize_space(
        text
    ).lower()

    kind = governing_dictionary_kind(
        period
    )

    if kind == "2013-2020":
        return (
            "data_dictionary" in filename
            and "2013-2020" in filename
        )

    if period == "2021":
        return (
            "data_dictionary" in filename
            and "2021" in filename
        )

    if period == "2022":
        return (
            "data_dictionary" in filename
            and "2022" in filename
        )

    if period == "2023":
        return (
            "data_dictionary" in filename
            and "2023" in filename
        )

    if period == "2024":
        return (
            "data_dictionary" in filename
            and "performance year 2024 financial and quality results"
            in normalized_text
        )

    return False


def find_field_context(
    text: str,
    field_name: str,
    radius: int = 700,
) -> tuple[bool, str, int]:
    """
    Locate exact variable-name text and return surrounding context.

    This is documentary evidence extraction, not semantic inference.
    """
    match = re.search(
        re.escape(field_name),
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return False, "", -1

    start = max(
        0,
        match.start() - radius,
    )

    end = min(
        len(text),
        match.end() + radius,
    )

    context = normalize_space(
        text[start:end]
    )

    return True, context, match.start()


def find_keyword_fields(
    headers_by_period: dict[str, list[str]],
) -> list[dict]:
    """
    Discover additional benchmark/expenditure/payment/savings fields
    for later semantic review without assigning them accounting status.
    """
    patterns = [
        r"bench",
        r"bnch",
        r"exp",
        r"pay",
        r"sav",
        r"loss",
        r"recoup",
        r"aim",
        r"aip",
    ]

    rows = []

    for period in PERIODS:
        for position, field_name in enumerate(
            headers_by_period.get(
                period,
                [],
            ),
            start=1,
        ):
            normalized = field_name.lower()

            matched = [
                pattern
                for pattern in patterns
                if re.search(
                    pattern,
                    normalized,
                )
            ]

            if matched:
                rows.append(
                    {
                        "performance_period": period,
                        "column_position": position,
                        "field_name": field_name,
                        "matched_patterns": ";".join(
                            matched
                        ),
                    }
                )

    return rows


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict],
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
        writer.writerows(rows)


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    errors: list[str] = []

    if not FINANCIAL_ZIP.exists():
        raise FileNotFoundError(
            f"Financial ZIP not found: {FINANCIAL_ZIP}"
        )

    if not DOCUMENTATION_ZIP.exists():
        raise FileNotFoundError(
            f"Documentation ZIP not found: {DOCUMENTATION_ZIP}"
        )

    # ------------------------------------------------------------
    # Financial source headers
    # ------------------------------------------------------------
    headers_by_period: dict[
        str,
        list[str],
    ] = {}

    financial_member_by_period: dict[
        str,
        str,
    ] = {}

    with zipfile.ZipFile(
        FINANCIAL_ZIP,
        "r",
    ) as archive:

        csv_members = [
            info
            for info in archive.infolist()
            if (
                not info.is_dir()
                and info.filename.lower().endswith(
                    ".csv"
                )
            )
        ]

        for info in csv_members:
            period = financial_period(
                info.filename
            )

            data = archive.read(info)

            header = read_csv_header(
                data
            )

            if period == "UNRESOLVED":
                errors.append(
                    "Unresolved financial period: "
                    f"{info.filename}"
                )
                continue

            if period in headers_by_period:
                errors.append(
                    "Duplicate financial CSV for "
                    f"{period}"
                )
                continue

            headers_by_period[
                period
            ] = header

            financial_member_by_period[
                period
            ] = info.filename

    # ------------------------------------------------------------
    # Documentation: collapse byte-identical PDFs and retain text.
    # ------------------------------------------------------------
    unique_docs: dict[
        str,
        dict,
    ] = {}

    with zipfile.ZipFile(
        DOCUMENTATION_ZIP,
        "r",
    ) as archive:

        pdf_members = [
            info
            for info in archive.infolist()
            if (
                not info.is_dir()
                and info.filename.lower().endswith(
                    ".pdf"
                )
            )
        ]

        for info in pdf_members:
            data = archive.read(info)

            digest = sha256_bytes(
                data
            )

            if digest not in unique_docs:
                text, pages = extract_pdf_text(
                    data
                )

                unique_docs[
                    digest
                ] = {
                    "sha256": digest,
                    "member_names": [],
                    "archive_periods": set(),
                    "text": text,
                    "pages": pages,
                }

            unique_docs[
                digest
            ]["member_names"].append(
                info.filename
            )

            unique_docs[
                digest
            ]["archive_periods"].add(
                documentation_archive_period(
                    info.filename
                )
            )

    # ------------------------------------------------------------
    # Resolve one governing dictionary per performance period.
    # ------------------------------------------------------------
    governing_docs: dict[
        str,
        dict,
    ] = {}

    for period in PERIODS:
        candidates = []

        for doc in unique_docs.values():
            for member_name in doc[
                "member_names"
            ]:
                if dictionary_matches(
                    member_name,
                    period,
                    doc["text"],
                ):
                    candidates.append(
                        doc
                    )
                    break

        # Collapse same SHA if discovered through multiple member names.
        candidates_by_hash = {
            doc["sha256"]: doc
            for doc in candidates
        }

        candidates = list(
            candidates_by_hash.values()
        )

        if len(candidates) != 1:
            errors.append(
                f"{period}: expected exactly one governing "
                f"dictionary, found {len(candidates)}"
            )
        else:
            governing_docs[
                period
            ] = candidates[0]

    # ------------------------------------------------------------
    # Build semantic evidence crosswalk.
    # ------------------------------------------------------------
    crosswalk_rows = []

    for period in PERIODS:
        header = headers_by_period.get(
            period,
            [],
        )

        governing = governing_docs.get(
            period
        )

        for field_name in TARGET_FIELDS:
            source_present = (
                field_name in header
            )

            expected_present = (
                period
                in EXPECTED_FIELD_PERIODS.get(
                    field_name,
                    set(),
                )
            )

            documented = False
            context = ""
            match_position = -1
            doc_sha = ""
            doc_names = ""

            if governing is not None:
                (
                    documented,
                    context,
                    match_position,
                ) = find_field_context(
                    governing["text"],
                    field_name,
                )

                doc_sha = governing[
                    "sha256"
                ]

                doc_names = ";".join(
                    sorted(
                        {
                            Path(name).name
                            for name in governing[
                                "member_names"
                            ]
                        }
                    )
                )

            if source_present and documented:
                evidence_status = (
                    "SOURCE_AND_DOCUMENTATION_PRESENT"
                )

            elif source_present and not documented:
                evidence_status = (
                    "SOURCE_PRESENT_DOCUMENTATION_NOT_FOUND"
                )

            elif (
                not source_present
                and documented
            ):
                evidence_status = (
                    "DOCUMENTED_NOT_PRESENT_IN_SOURCE_PERIOD"
                )

            else:
                evidence_status = (
                    "NOT_PRESENT_FOR_PERIOD"
                )

            crosswalk_rows.append(
                {
                    "performance_period": period,
                    "field_name": field_name,
                    "expected_from_prior_profile": (
                        "YES"
                        if expected_present
                        else "NO"
                    ),
                    "source_field_present": (
                        "YES"
                        if source_present
                        else "NO"
                    ),
                    "documentation_field_found": (
                        "YES"
                        if documented
                        else "NO"
                    ),
                    "evidence_status": evidence_status,
                    "financial_member": (
                        financial_member_by_period.get(
                            period,
                            ""
                        )
                    ),
                    "governing_dictionary_sha256": (
                        doc_sha
                    ),
                    "governing_dictionary_filenames": (
                        doc_names
                    ),
                    "dictionary_match_position": (
                        match_position
                    ),
                    "dictionary_context": context,
                }
            )

    field_inventory_rows = (
        find_keyword_fields(
            headers_by_period
        )
    )

    # ------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------
    checks = []

    def add_check(
        name: str,
        passed: bool,
        detail: str,
    ) -> None:
        checks.append(
            {
                "check": name,
                "status": (
                    "PASS"
                    if passed
                    else "FAIL"
                ),
                "detail": detail,
            }
        )

    add_check(
        "All 11 financial periods resolved",
        set(
            headers_by_period
        ) == set(PERIODS),
        (
            f"{len(headers_by_period)}/11 "
            "financial periods"
        ),
    )

    add_check(
        "Exactly one governing dictionary resolved per period",
        set(
            governing_docs
        ) == set(PERIODS),
        (
            f"{len(governing_docs)}/11 "
            "periods have governing dictionaries"
        ),
    )

    expected_source_mismatches = []

    for field_name, expected_periods in (
        EXPECTED_FIELD_PERIODS.items()
    ):
        observed_periods = {
            period
            for period in PERIODS
            if field_name
            in headers_by_period.get(
                period,
                []
            )
        }

        if observed_periods != expected_periods:
            expected_source_mismatches.append(
                (
                    field_name,
                    sorted(expected_periods),
                    sorted(observed_periods),
                )
            )

    add_check(
        "Target-field source presence reproduces certified v0.1 structure",
        not expected_source_mismatches,
        (
            "0 mismatches"
            if not expected_source_mismatches
            else str(
                expected_source_mismatches
            )
        ),
    )

    required_documentation_failures = [
        row
        for row in crosswalk_rows
        if (
            row[
                "source_field_present"
            ] == "YES"
            and row[
                "documentation_field_found"
            ] != "YES"
        )
    ]

    add_check(
        "Every observed target source field has governing dictionary evidence",
        not required_documentation_failures,
        (
            f"{len(required_documentation_failures)} "
            "observed source-field/documentation gaps"
        ),
    )

    for field_name in [
        "GenSaveLoss",
        "EarnSaveLoss",
    ]:
        complete_periods = {
            row[
                "performance_period"
            ]
            for row in crosswalk_rows
            if (
                row["field_name"]
                == field_name
                and row[
                    "source_field_present"
                ] == "YES"
                and row[
                    "documentation_field_found"
                ] == "YES"
            )
        }

        add_check(
            f"{field_name} source+documentation coverage all 11 periods",
            complete_periods
            == set(PERIODS),
            (
                f"{len(complete_periods)}/11"
            ),
        )

    advance_observed = [
        row
        for row in crosswalk_rows
        if (
            row["field_name"]
            in {
                "Adv_Pay",
                "Adv_Pay_Amt",
                "Adv_Pay_Recoup",
                "AIM",
                "AIPRecoup",
            }
            and row[
                "source_field_present"
            ] == "YES"
        )
    ]

    advance_documented = [
        row
        for row in advance_observed
        if row[
            "documentation_field_found"
        ] == "YES"
    ]

    add_check(
        "Observed advance/AIM/recoupment target fields have documentation",
        len(advance_observed)
        == len(advance_documented),
        (
            f"{len(advance_documented)}/"
            f"{len(advance_observed)}"
        ),
    )

    # Confirm PY2024 governing dictionary by document content,
    # not merely by its 2025 filename.
    py2024_doc = governing_docs.get(
        "2024"
    )

    py2024_identity_ok = False

    if py2024_doc is not None:
        py2024_identity_ok = (
            "performance year 2024 financial and quality results"
            in normalize_space(
                py2024_doc["text"]
            ).lower()
        )

    add_check(
        "PY2024 dictionary identity established from document text",
        py2024_identity_ok,
        (
            py2024_doc["sha256"]
            if py2024_doc
            else "MISSING"
        ),
    )

    # ------------------------------------------------------------
    # Write evidence
    # ------------------------------------------------------------
    write_csv(
        CROSSWALK_CSV,
        [
            "performance_period",
            "field_name",
            "expected_from_prior_profile",
            "source_field_present",
            "documentation_field_found",
            "evidence_status",
            "financial_member",
            "governing_dictionary_sha256",
            "governing_dictionary_filenames",
            "dictionary_match_position",
            "dictionary_context",
        ],
        crosswalk_rows,
    )

    write_csv(
        FIELD_INVENTORY_CSV,
        [
            "performance_period",
            "column_position",
            "field_name",
            "matched_patterns",
        ],
        field_inventory_rows,
    )

    write_csv(
        CHECKS_CSV,
        [
            "check",
            "status",
            "detail",
        ],
        checks,
    )

    overall_pass = (
        not errors
        and all(
            check["status"]
            == "PASS"
            for check in checks
        )
    )

    # ------------------------------------------------------------
    # Human-readable report
    # ------------------------------------------------------------
    lines = []

    lines.append(
        "=" * 100
    )

    lines.append(
        "CMS MSSP FINANCIAL SEMANTICS PROFILE v0.1"
    )

    lines.append(
        "=" * 100
    )

    lines.append("")

    lines.append(
        "BOUNDARY"
    )

    lines.append(
        "-" * 100
    )

    lines.append(
        "READ-ONLY semantic evidence profiling."
    )

    lines.append(
        "No Washington-dollar calculation."
    )

    lines.append(
        "No geographic allocation."
    )

    lines.append(
        "No economic-additivity conclusion."
    )

    lines.append(
        "No advance-payment netting."
    )

    lines.append(
        "No database writes."
    )

    lines.append(
        "No ledger inclusion."
    )

    lines.append("")

    lines.append(
        "GOVERNING DICTIONARIES"
    )

    lines.append(
        "-" * 100
    )

    for period in PERIODS:
        doc = governing_docs.get(
            period
        )

        if doc is None:
            lines.append(
                f"{period:<6} MISSING"
            )

        else:
            names = sorted(
                {
                    Path(name).name
                    for name in doc[
                        "member_names"
                    ]
                }
            )

            lines.append(
                f"{period:<6} "
                f"{doc['sha256']} | "
                + ";".join(names)
            )

    lines.append("")

    lines.append(
        "TARGET FIELD COVERAGE"
    )

    lines.append(
        "-" * 100
    )

    for field_name in TARGET_FIELDS:
        rows = [
            row
            for row in crosswalk_rows
            if row[
                "field_name"
            ] == field_name
        ]

        source_periods = [
            row[
                "performance_period"
            ]
            for row in rows
            if row[
                "source_field_present"
            ] == "YES"
        ]

        documented_periods = [
            row[
                "performance_period"
            ]
            for row in rows
            if (
                row[
                    "source_field_present"
                ] == "YES"
                and row[
                    "documentation_field_found"
                ] == "YES"
            )
        ]

        lines.append(
            f"{field_name:<20} "
            f"source={','.join(source_periods) or 'NONE'} | "
            f"documented={','.join(documented_periods) or 'NONE'}"
        )

    lines.append("")

    lines.append(
        "DOCUMENTARY CONTEXT"
    )

    lines.append(
        "-" * 100
    )

    # Print one context per unique
    # field/dictionary SHA combination.
    seen_contexts = set()

    for row in crosswalk_rows:
        if (
            row[
                "source_field_present"
            ] != "YES"
            or row[
                "documentation_field_found"
            ] != "YES"
        ):
            continue

        key = (
            row["field_name"],
            row[
                "governing_dictionary_sha256"
            ],
        )

        if key in seen_contexts:
            continue

        seen_contexts.add(
            key
        )

        lines.append(
            f"{row['field_name']} | "
            f"first applicable observed period "
            f"{row['performance_period']}"
        )

        lines.append(
            f"  Dictionary SHA-256: "
            f"{row['governing_dictionary_sha256']}"
        )

        lines.append(
            f"  Context: "
            f"{row['dictionary_context']}"
        )

        lines.append("")

    lines.append(
        "ADDITIONAL FINANCIAL-FIELD INVENTORY"
    )

    lines.append(
        "-" * 100
    )

    distinct_fields = sorted(
        {
            row["field_name"]
            for row in field_inventory_rows
        },
        key=lambda value: value.lower(),
    )

    for field_name in distinct_fields:
        periods = [
            row[
                "performance_period"
            ]
            for row in field_inventory_rows
            if row[
                "field_name"
            ] == field_name
        ]

        lines.append(
            f"{field_name} | "
            + ",".join(periods)
        )

    lines.append("")

    lines.append(
        "CHECKS"
    )

    lines.append(
        "-" * 100
    )

    for check in checks:
        lines.append(
            f"{check['status']} | "
            f"{check['check']} | "
            f"{check['detail']}"
        )

    if errors:
        lines.append("")

        lines.append(
            "ERRORS"
        )

        lines.append(
            "-" * 100
        )

        for error in errors:
            lines.append(
                f"FAIL | {error}"
            )

    lines.append("")

    lines.append(
        "=" * 100
    )

    lines.append(
        "OVERALL CMS MSSP FINANCIAL SEMANTICS PROFILE v0.1: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )

    lines.append(
        "=" * 100
    )

    lines.append("")

    lines.append(
        "Interpretive boundary:"
    )

    lines.append(
        "  PASS means the selected financial fields are structurally "
        "present where expected and have identifiable governing CMS "
        "dictionary evidence."
    )

    lines.append(
        "  PASS does not mean any field is economically additive."
    )

    lines.append(
        "  GenSaveLoss and EarnSaveLoss must not be summed merely "
        "because both are monetary fields."
    )

    lines.append(
        "  Advance/AIM amounts and recoupments must not be added or "
        "subtracted until their accounting relationship is separately "
        "certified."
    )

    lines.append(
        "  ACO identity or location does not establish beneficiary "
        "payment-dollar geography."
    )

    lines.append(
        "  No source is additive by default."
    )

    report = "\n".join(
        lines
    )

    REPORT_TXT.write_text(
        report,
        encoding="utf-8",
    )

    print(
        report
    )

    print("")
    print(
        "Evidence written:"
    )

    for path in [
        CROSSWALK_CSV,
        FIELD_INVENTORY_CSV,
        CHECKS_CSV,
        REPORT_TXT,
    ]:
        print(
            f"  {path.relative_to(REPO_ROOT)}"
        )

    return (
        0
        if overall_pass
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
