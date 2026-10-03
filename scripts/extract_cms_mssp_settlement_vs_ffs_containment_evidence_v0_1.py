"""
WCFFBP
CMS MSSP Settlement vs FFS Containment Evidence Extractor v0.1

PURPOSE
-------
Search the already-preserved CMS MSSP documentation for evidence needed
to distinguish MSSP EarnSaveLoss from FFS claim-linked ACO/PBP payment
amounts already represented in the Original Medicare Geographic
Variation PUF.

THIS SCRIPT DOES NOT MAKE THE ACCOUNTING DECISION.

It asks whether CMS documentation provides evidence concerning:

    1. EarnSaveLoss / earned shared savings;
    2. performance payments;
    3. underlying claims / expenditures;
    4. population-based or split payments;
    5. claim value-code / other-applied-indicator mechanisms;
    6. advance/AIM/AIP settlement amounts.

No source is additive by default.

ABSENCE RULE
------------
A term that is not found is reported as NOT FOUND.

Absence is NOT evidence that the corresponding payment mechanism is
excluded from MSSP EarnSaveLoss or from Original Medicare spending.

READ-ONLY
---------
No source files are modified.
No database writes.
No ledger inclusion.
"""

from __future__ import annotations

import hashlib
import io
import re
import sys
import zipfile

from pathlib import Path

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]


# =====================================================================
# PRESERVED MSSP DOCUMENTATION
# =====================================================================

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

EXPECTED_DOCUMENTATION_SHA256 = (
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
    / "mssp_performance_results"
    / "validation"
    / "settlement_vs_ffs_containment_evidence_v0_1"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_mssp_settlement_vs_ffs_containment_evidence_report_v0_1.txt"
)

EVIDENCE_TXT = (
    OUTPUT_DIR
    / "cms_mssp_settlement_vs_ffs_containment_evidence_v0_1.txt"
)


# =====================================================================
# SEARCH CONCEPTS
# =====================================================================

CONCEPTS = [
    {
        "name": "EARNSAVELOSS",
        "patterns": [
            r"\bEarnSaveLoss\b",
            r"earned shared savings",
            r"shared savings payment",
        ],
    },
    {
        "name": "PERFORMANCE PAYMENT",
        "patterns": [
            r"performance payment",
            r"performance payments",
            r"earned performance",
        ],
    },
    {
        "name": "UNDERLYING CLAIMS / EXPENDITURES",
        "patterns": [
            r"\bclaim\b",
            r"\bclaims\b",
            r"assigned beneficiary expenditures",
            r"beneficiary expenditures",
            r"total expenditures",
            r"\bexpenditures\b",
        ],
    },
    {
        "name": "POPULATION-BASED / SPLIT PAYMENT",
        "patterns": [
            r"population[- ]based payment",
            r"population[- ]based payments",
            r"\bPBP\b",
            r"split payment",
            r"split payments",
        ],
    },
    {
        "name": "CLAIM PAYMENT REDIRECTION MECHANISM",
        "patterns": [
            r"value code",
            r"value codes",
            r"\bQ1\b",
            r"other applied indicator",
            r"other applied indicator code",
        ],
    },
    {
        "name": "ADVANCE / AIM / AIP SETTLEMENT",
        "patterns": [
            r"\bAdv_Pay_Amt\b",
            r"\bAdv_Pay_Recoup\b",
            r"\bAIM\b",
            r"\bAIPBalance\b",
            r"\bAIPRecoup\b",
            r"\bAIPOwe\b",
            r"advance payment",
            r"advance payments",
            r"recoup",
            r"recoupment",
        ],
    },
]


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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(
        data
    ).hexdigest().upper()


def normalize_whitespace(text: str) -> str:
    text = text.replace(
        "\x00",
        " ",
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def pdf_pages_from_bytes(
    data: bytes,
) -> list[dict]:
    reader = PdfReader(
        io.BytesIO(data)
    )

    pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        try:
            text = page.extract_text() or ""

        except Exception as exc:
            text = (
                "[TEXT EXTRACTION ERROR: "
                f"{type(exc).__name__}: {exc}]"
            )

        pages.append(
            {
                "page": page_number,
                "text": normalize_whitespace(
                    text
                ),
            }
        )

    return pages


def sentence_split(
    text: str,
) -> list[str]:
    text = normalize_whitespace(
        text
    )

    return [
        item.strip()
        for item in re.split(
            r"(?<=[.!?])\s+(?=[A-Z0-9(])",
            text,
        )
        if item.strip()
    ]


def evidence_window(
    text: str,
    patterns: list[str],
    radius: int = 1,
) -> str:
    sentences = sentence_split(
        text
    )

    matched = []

    for index, sentence in enumerate(
        sentences
    ):
        if any(
            re.search(
                pattern,
                sentence,
                flags=re.IGNORECASE,
            )
            for pattern in patterns
        ):
            matched.append(
                index
            )

    if not matched:
        return ""

    keep = set()

    for index in matched:
        for offset in range(
            -radius,
            radius + 1,
        ):
            candidate = (
                index
                + offset
            )

            if (
                0
                <= candidate
                < len(sentences)
            ):
                keep.add(
                    candidate
                )

    return normalize_whitespace(
        " ".join(
            sentences[index]
            for index in sorted(
                keep
            )
        )
    )


def score_text(
    text: str,
    patterns: list[str],
) -> int:
    score = 0

    for pattern in patterns:
        score += len(
            re.findall(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
        )

    return score


def dictionary_like_member(
    member_name: str,
) -> bool:
    name = member_name.casefold()

    return (
        name.endswith(".pdf")
        and (
            "dictionary" in name
            or "data_dict" in name
            or "data dict" in name
        )
    )


def methodology_like_member(
    member_name: str,
) -> bool:
    name = member_name.casefold()

    return (
        name.endswith(".pdf")
        and (
            "method" in name
            or "specification" in name
        )
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
        description: str,
        passed: bool,
        detail: str,
    ) -> None:
        checks.append(
            {
                "description": description,
                "status": (
                    "PASS"
                    if passed
                    else "FAIL"
                ),
                "detail": detail,
            }
        )

    # -----------------------------------------------------------------
    # SOURCE AUTHENTICATION
    # -----------------------------------------------------------------

    source_exists = (
        DOCUMENTATION_ZIP.exists()
    )

    check(
        "Preserved MSSP documentation ZIP exists",
        source_exists,
        str(
            DOCUMENTATION_ZIP.relative_to(
                REPO_ROOT
            )
        ),
    )

    if not source_exists:
        print(
            "FAIL: preserved MSSP documentation ZIP is missing."
        )

        return 1

    source_sha = sha256_file(
        DOCUMENTATION_ZIP
    )

    check(
        "MSSP documentation ZIP SHA-256 matches preserved acquisition",
        source_sha
        == EXPECTED_DOCUMENTATION_SHA256,
        source_sha,
    )

    # -----------------------------------------------------------------
    # READ UNIQUE PDF BYTE STREAMS
    # -----------------------------------------------------------------

    pdf_members = []

    with zipfile.ZipFile(
        DOCUMENTATION_ZIP,
        "r",
    ) as archive:

        for info in archive.infolist():

            if (
                info.is_dir()
                or not info.filename.lower().endswith(
                    ".pdf"
                )
            ):
                continue

            data = archive.read(
                info
            )

            pdf_members.append(
                {
                    "member": info.filename,
                    "sha256": sha256_bytes(
                        data
                    ),
                    "bytes": data,
                }
            )

    check(
        "Documentation ZIP contains 22 PDF members",
        len(
            pdf_members
        )
        == 22,
        (
            f"{len(pdf_members)}/22"
        ),
    )

    unique_by_sha = {}

    for member in pdf_members:
        unique_by_sha.setdefault(
            member[
                "sha256"
            ],
            member,
        )

    unique_pdfs = list(
        unique_by_sha.values()
    )

    check(
        "Documentation ZIP reproduces 7 unique PDF byte streams",
        len(
            unique_pdfs
        )
        == 7,
        (
            f"{len(unique_pdfs)}/7"
        ),
    )

    # -----------------------------------------------------------------
    # PARSE UNIQUE PDFs
    # -----------------------------------------------------------------

    parsed_documents = []

    parse_errors = []

    for document in unique_pdfs:

        try:
            pages = pdf_pages_from_bytes(
                document[
                    "bytes"
                ]
            )

        except Exception as exc:
            parse_errors.append(
                (
                    document[
                        "member"
                    ],
                    type(exc).__name__,
                    str(exc),
                )
            )

            continue

        parsed_documents.append(
            {
                "member": document[
                    "member"
                ],
                "sha256": document[
                    "sha256"
                ],
                "pages": pages,
                "dictionary_like": (
                    dictionary_like_member(
                        document[
                            "member"
                        ]
                    )
                ),
                "methodology_like": (
                    methodology_like_member(
                        document[
                            "member"
                        ]
                    )
                ),
            }
        )

    check(
        "All 7 unique PDF byte streams parse",
        (
            len(
                parsed_documents
            )
            == 7
            and not parse_errors
        ),
        (
            f"{len(parsed_documents)}/7 parsed; "
            f"errors={len(parse_errors)}"
        ),
    )

    # -----------------------------------------------------------------
    # SEARCH ALL UNIQUE DOCUMENTS
    # -----------------------------------------------------------------

    concept_evidence = {}

    for concept in CONCEPTS:

        observations = []

        for document in parsed_documents:

            for page in document[
                "pages"
            ]:

                score = score_text(
                    page[
                        "text"
                    ],
                    concept[
                        "patterns"
                    ],
                )

                if score <= 0:
                    continue

                window = evidence_window(
                    page[
                        "text"
                    ],
                    concept[
                        "patterns"
                    ],
                    radius=1,
                )

                if not window:
                    continue

                observations.append(
                    {
                        "member": document[
                            "member"
                        ],
                        "sha256": document[
                            "sha256"
                        ],
                        "page": page[
                            "page"
                        ],
                        "score": score,
                        "dictionary_like": document[
                            "dictionary_like"
                        ],
                        "methodology_like": document[
                            "methodology_like"
                        ],
                        "text": window,
                    }
                )

        # -------------------------------------------------------------
        # DEDUPLICATE IDENTICAL EVIDENCE WINDOWS
        # -------------------------------------------------------------

        observations.sort(
            key=lambda row: (
                -row[
                    "score"
                ],
                row[
                    "member"
                ],
                row[
                    "page"
                ],
            )
        )

        seen = set()
        unique_observations = []

        for observation in observations:

            key = normalize_whitespace(
                observation[
                    "text"
                ]
            ).casefold()

            if key in seen:
                continue

            seen.add(
                key
            )

            unique_observations.append(
                observation
            )

        concept_evidence[
            concept[
                "name"
            ]
        ] = unique_observations

    # -----------------------------------------------------------------
    # REQUIRED SEMANTIC EVIDENCE
    # -----------------------------------------------------------------

    earn_evidence = concept_evidence[
        "EARNSAVELOSS"
    ]

    claims_evidence = concept_evidence[
        "UNDERLYING CLAIMS / EXPENDITURES"
    ]

    check(
        "EarnSaveLoss / earned shared-savings evidence is present",
        len(
            earn_evidence
        )
        > 0,
        (
            f"{len(earn_evidence)} unique evidence window(s)"
        ),
    )

    check(
        "Underlying claims / expenditure evidence is present",
        len(
            claims_evidence
        )
        > 0,
        (
            f"{len(claims_evidence)} unique evidence window(s)"
        ),
    )

    # -----------------------------------------------------------------
    # RENDER COMPACT EVIDENCE FILE
    # -----------------------------------------------------------------

    evidence_lines = []

    evidence_lines.append(
        "=" * 110
    )

    evidence_lines.append(
        "CMS MSSP SETTLEMENT vs FFS CONTAINMENT EVIDENCE v0.1"
    )

    evidence_lines.append(
        "=" * 110
    )

    evidence_lines.append("")

    evidence_lines.append(
        "BOUNDARY"
    )

    evidence_lines.append(
        "-" * 110
    )

    evidence_lines.append(
        "Evidence extraction only. No MSSP/FFS economic-additivity decision is made."
    )

    evidence_lines.append(
        "Absence of a term is not evidence of exclusion."
    )

    evidence_lines.append(
        "No Washington payment-dollar incidence is inferred."
    )

    evidence_lines.append(
        "No database write or ledger inclusion occurs."
    )

    evidence_lines.append("")

    for number, concept in enumerate(
        CONCEPTS,
        start=1,
    ):

        name = concept[
            "name"
        ]

        observations = concept_evidence[
            name
        ]

        evidence_lines.append(
            f"{number}. {name}"
        )

        evidence_lines.append(
            "-" * 110
        )

        if not observations:

            evidence_lines.append(
                "NOT FOUND"
            )

            evidence_lines.append(
                "Absence is descriptive only and is NOT evidence of exclusion."
            )

            evidence_lines.append("")

            continue

        # Keep evidence compact while preserving the strongest unique
        # passages. Eight per concept is intentionally conservative.
        selected = observations[
            :8
        ]

        evidence_lines.append(
            (
                f"Unique evidence windows found: "
                f"{len(observations)}"
            )
        )

        evidence_lines.append(
            (
                f"Strongest windows shown: "
                f"{len(selected)}"
            )
        )

        evidence_lines.append("")

        for index, observation in enumerate(
            selected,
            start=1,
        ):

            evidence_lines.append(
                (
                    f"[PASSAGE {index} | "
                    f"PDF PAGE {observation['page']} | "
                    f"SCORE {observation['score']}]"
                )
            )

            evidence_lines.append(
                "Member: "
                + observation[
                    "member"
                ]
            )

            evidence_lines.append(
                "PDF SHA-256: "
                + observation[
                    "sha256"
                ]
            )

            evidence_lines.append(
                observation[
                    "text"
                ]
            )

            evidence_lines.append("")

        evidence_lines.append("")

    EVIDENCE_TXT.write_text(
        "\n".join(
            evidence_lines
        ),
        encoding="utf-8",
    )

    # -----------------------------------------------------------------
    # REPORT
    # -----------------------------------------------------------------

    overall_pass = all(
        row[
            "status"
        ]
        == "PASS"
        for row in checks
    )

    report = []

    report.append(
        "=" * 110
    )

    report.append(
        "CMS MSSP SETTLEMENT vs FFS CONTAINMENT EVIDENCE EXTRACTOR v0.1"
    )

    report.append(
        "=" * 110
    )

    report.append("")

    report.append(
        "BOUNDARY"
    )

    report.append(
        "-" * 110
    )

    report.append(
        "Searches preserved CMS MSSP documentation for evidence needed to distinguish EarnSaveLoss from FFS-contained payments."
    )

    report.append(
        "This extractor does NOT make the economic-overlap or additivity decision."
    )

    report.append(
        "Absence of terminology is NOT interpreted as proof of exclusion."
    )

    report.append(
        "No Washington incidence, cash timing, database write, or ledger inclusion."
    )

    report.append("")

    report.append(
        "SOURCE"
    )

    report.append(
        "-" * 110
    )

    report.append(
        str(
            DOCUMENTATION_ZIP.relative_to(
                REPO_ROOT
            )
        )
    )

    report.append(
        "SHA-256: "
        + source_sha
    )

    report.append("")

    report.append(
        "DOCUMENT UNIVERSE"
    )

    report.append(
        "-" * 110
    )

    report.append(
        f"PDF archive members: {len(pdf_members)}"
    )

    report.append(
        f"Unique PDF byte streams: {len(unique_pdfs)}"
    )

    report.append(
        f"Unique PDFs parsed: {len(parsed_documents)}"
    )

    report.append(
        f"Parse errors: {len(parse_errors)}"
    )

    report.append("")

    report.append(
        "EVIDENCE SUMMARY"
    )

    report.append(
        "-" * 110
    )

    for concept in CONCEPTS:

        name = concept[
            "name"
        ]

        count = len(
            concept_evidence[
                name
            ]
        )

        report.append(
            (
                f"{name}: "
                + (
                    f"{count} unique evidence window(s)"
                    if count
                    else (
                        "NOT FOUND "
                        "(absence is not evidence of exclusion)"
                    )
                )
            )
        )

    report.append("")

    report.append(
        "CHECKS"
    )

    report.append(
        "-" * 110
    )

    for row in checks:

        report.append(
            (
                f"{row['status']} | "
                f"{row['description']} | "
                f"{row['detail']}"
            )
        )

    report.append("")

    report.append(
        "=" * 110
    )

    report.append(
        "OVERALL CMS MSSP SETTLEMENT vs FFS CONTAINMENT EVIDENCE EXTRACTOR v0.1: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )

    report.append(
        "=" * 110
    )

    report.append("")

    report.append(
        "INTERPRETIVE BOUNDARY"
    )

    report.append(
        "-" * 110
    )

    report.append(
        "PASS means the preserved MSSP documentation was authenticated and the targeted settlement/containment evidence was extracted."
    )

    report.append(
        "PASS does NOT establish that EarnSaveLoss is economically distinct from Original Medicare / FFS."
    )

    report.append(
        "PASS does NOT establish Washington payment-dollar incidence."
    )

    report.append(
        "No source is additive by default."
    )

    report.append("")

    report.append(
        "Evidence file:"
    )

    report.append(
        str(
            EVIDENCE_TXT.relative_to(
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

    # -----------------------------------------------------------------
    # SHORT CONSOLE OUTPUT
    # -----------------------------------------------------------------

    print(
        report_text
    )

    return (
        0
        if overall_pass
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )