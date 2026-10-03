"""
WCFFBP
CMS Original Medicare Containment Evidence Extractor v0.1

PURPOSE
-------
Establish, from preserved CMS documentation, what the Original Medicare
Geographic Variation PUF and TOT_MDCR_PYMT_AMT represent.

This is an EVIDENCE EXTRACTION step only.

It does NOT determine:
    - whether MSSP EarnSaveLoss overlaps Original Medicare / FFS;
    - whether MSSP EarnSaveLoss is economically additive;
    - whether any MSSP payment has Washington payment-dollar incidence;
    - whether any amount belongs in the principal ledger.

SOURCE PRESERVATION
-------------------
The CMS ZIP is read directly and is not extracted or modified.

The embedded 2014-2024 Original Medicare Geographic Variation
Data Dictionary PDF is hashed independently in memory.

The Methods Paper is read from its preserved standalone PDF.

ABSENCE RULE
------------
Failure to find a term such as MSSP, ACO, or shared savings is NOT
interpreted as evidence that the concept is excluded from the PUF.
"""

from __future__ import annotations

import hashlib
import io
import re
import sys
import warnings
import zipfile

from pathlib import Path

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]


# =====================================================================
# PRESERVED SOURCES
# =====================================================================

DOCUMENTATION_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_geographic_variation"
    / "documentation"
)

METHODS_PDF = (
    DOCUMENTATION_DIR
    / "Geographic Variation Public Use File Methods Paper.pdf"
)

CMS_ZIP = (
    DOCUMENTATION_DIR
    / "Medicare Geographic Variation - by National, State & County.zip"
)

EXPECTED_METHODS_SHA256 = (
    "94666A9FC128F8CB469A55B3D2494368EBFF66F314CD88ED2440C6AE4BE3087F"
)

EXPECTED_ZIP_SHA256 = (
    "17D5BFE2F9388E5BF03552AE8BB97A312B6FFDB9581C434F8FDE5AF0F188BA57"
)

EXPECTED_DICTIONARY_MEMBER = (
    "Medicare Geographic Variation - by National, State & County/"
    "2024/"
    "2014-2024 Original Medicare Geographic Variation Data Dictionary.pdf"
)


# =====================================================================
# SEARCH TARGETS
# =====================================================================

DICTIONARY_TARGETS = [
    "TOT_MDCR_PYMT_AMT",
    "Total Medicare Payment",
    "Medicare Payment",
]

METHODS_TARGETS = [
    "claim",
    "claims",
    "payment",
    "payments",
    "expenditure",
    "expenditures",
    "Original Medicare",
    "fee-for-service",
    "FFS",
    "Chronic Conditions Data Warehouse",
    "CCW",
    "ACO",
    "Accountable Care Organization",
    "MSSP",
    "Shared Savings",
    "shared savings",
]


# =====================================================================
# OUTPUT
# =====================================================================

OUTPUT_DIR = (
    DOCUMENTATION_DIR
    / "validation"
    / "original_medicare_containment_evidence_v0_1"
)

DICTIONARY_TEXT_TXT = (
    OUTPUT_DIR
    / "cms_original_medicare_geographic_variation_dictionary_text_v0_1.txt"
)

METHODS_TEXT_TXT = (
    OUTPUT_DIR
    / "cms_original_medicare_geographic_variation_methods_text_v0_1.txt"
)

DICTIONARY_EVIDENCE_TXT = (
    OUTPUT_DIR
    / "cms_original_medicare_dictionary_evidence_v0_1.txt"
)

METHODS_EVIDENCE_TXT = (
    OUTPUT_DIR
    / "cms_original_medicare_methods_evidence_v0_1.txt"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_original_medicare_containment_evidence_report_v0_1.txt"
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def normalize_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n[ \t]+",
        "\n",
        text,
    )

    return text.strip()


def extract_pdf_pages_from_bytes(
    pdf_bytes: bytes,
) -> list[dict]:
    reader = PdfReader(
        io.BytesIO(pdf_bytes)
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
                "text": normalize_whitespace(text),
            }
        )

    return pages


def extract_pdf_pages_from_path(
    path: Path,
) -> list[dict]:
    reader = PdfReader(
        str(path)
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
                "text": normalize_whitespace(text),
            }
        )

    return pages


def render_full_text(
    title: str,
    pages: list[dict],
) -> str:
    lines = []

    lines.append("=" * 120)
    lines.append(title)
    lines.append("=" * 120)
    lines.append("")

    for page in pages:
        lines.append(
            f"[PAGE {page['page']}]"
        )

        lines.append(
            "-" * 120
        )

        lines.append(
            page["text"]
        )

        lines.append("")

    return "\n".join(lines)


def find_term_windows(
    pages: list[dict],
    term: str,
    *,
    context_chars: int = 900,
) -> list[dict]:
    """
    Return evidence windows around every case-insensitive occurrence
    of a search term.

    Page boundaries are retained.
    """

    matches = []

    pattern = re.compile(
        re.escape(term),
        flags=re.IGNORECASE,
    )

    for page in pages:
        text = page["text"]

        for match_number, match in enumerate(
            pattern.finditer(text),
            start=1,
        ):
            start = max(
                0,
                match.start() - context_chars,
            )

            end = min(
                len(text),
                match.end() + context_chars,
            )

            window = text[
                start:end
            ].strip()

            matches.append(
                {
                    "term": term,
                    "page": page["page"],
                    "match_number_on_page": match_number,
                    "window": window,
                }
            )

    return matches


def render_search_evidence(
    title: str,
    pages: list[dict],
    targets: list[str],
) -> tuple[str, dict[str, int]]:
    lines = []

    counts = {}

    lines.append("=" * 120)
    lines.append(title)
    lines.append("=" * 120)
    lines.append("")

    for target in targets:
        matches = find_term_windows(
            pages,
            target,
        )

        counts[
            target
        ] = len(matches)

        lines.append(
            f"SEARCH TERM: {target}"
        )

        lines.append(
            "-" * 120
        )

        if not matches:
            lines.append(
                "NOT FOUND"
            )

            lines.append(
                "Interpretation: absence is descriptive only and is NOT evidence of exclusion."
            )

            lines.append("")

            continue

        lines.append(
            f"Occurrences: {len(matches)}"
        )

        lines.append("")

        for index, match in enumerate(
            matches,
            start=1,
        ):
            lines.append(
                f"[MATCH {index} | PDF PAGE {match['page']}]"
            )

            lines.append(
                match["window"]
            )

            lines.append("")

    return (
        "\n".join(lines),
        counts,
    )


def exact_archive_inventory(
    archive: zipfile.ZipFile,
) -> list[str]:
    return [
        info.filename
        for info in archive.infolist()
    ]


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
    # SOURCE EXISTENCE
    # -----------------------------------------------------------------

    methods_exists = METHODS_PDF.exists()
    zip_exists = CMS_ZIP.exists()

    check(
        "Preserved Geographic Variation Methods Paper exists",
        methods_exists,
        str(
            METHODS_PDF.relative_to(
                REPO_ROOT
            )
        ),
    )

    check(
        "Preserved CMS Geographic Variation ZIP exists",
        zip_exists,
        str(
            CMS_ZIP.relative_to(
                REPO_ROOT
            )
        ),
    )

    if not (
        methods_exists
        and zip_exists
    ):
        print(
            "FAIL: one or more required preserved CMS artifacts are missing."
        )

        return 1

    # -----------------------------------------------------------------
    # OUTER HASHES
    # -----------------------------------------------------------------

    methods_sha = sha256_file(
        METHODS_PDF
    )

    zip_sha = sha256_file(
        CMS_ZIP
    )

    check(
        "Methods Paper SHA-256 matches preserved acquisition",
        methods_sha
        == EXPECTED_METHODS_SHA256,
        methods_sha,
    )

    check(
        "CMS ZIP SHA-256 matches preserved acquisition",
        zip_sha
        == EXPECTED_ZIP_SHA256,
        zip_sha,
    )

    # -----------------------------------------------------------------
    # ZIP INVENTORY / EMBEDDED DICTIONARY
    # -----------------------------------------------------------------

    with zipfile.ZipFile(
        CMS_ZIP,
        "r",
    ) as archive:
        inventory = exact_archive_inventory(
            archive
        )

        substantive_members = [
            name
            for name in inventory
            if not name.endswith("/")
        ]

        dictionary_exists = (
            EXPECTED_DICTIONARY_MEMBER
            in inventory
        )

        check(
            "Exact 2014-2024 Original Medicare data dictionary member exists",
            dictionary_exists,
            EXPECTED_DICTIONARY_MEMBER,
        )

        check(
            "CMS ZIP contains exactly one substantive member",
            len(
                substantive_members
            )
            == 1,
            (
                f"{len(substantive_members)} substantive member(s)"
            ),
        )

        if not dictionary_exists:
            print(
                "FAIL: expected dictionary member not found."
            )

            return 1

        dictionary_bytes = archive.read(
            EXPECTED_DICTIONARY_MEMBER
        )

    dictionary_sha = sha256_bytes(
        dictionary_bytes
    )

    check(
        "Embedded data dictionary is non-empty",
        len(
            dictionary_bytes
        )
        > 0,
        f"{len(dictionary_bytes):,} bytes",
    )

    # -----------------------------------------------------------------
    # PDF TEXT EXTRACTION
    # -----------------------------------------------------------------

    with warnings.catch_warnings():
        warnings.simplefilter(
            "ignore"
        )

        dictionary_pages = (
            extract_pdf_pages_from_bytes(
                dictionary_bytes
            )
        )

        methods_pages = (
            extract_pdf_pages_from_path(
                METHODS_PDF
            )
        )

    dictionary_nonempty_pages = sum(
        1
        for page in dictionary_pages
        if page["text"].strip()
    )

    methods_nonempty_pages = sum(
        1
        for page in methods_pages
        if page["text"].strip()
    )

    check(
        "Embedded data dictionary PDF yields extractable text",
        dictionary_nonempty_pages > 0,
        (
            f"{dictionary_nonempty_pages}/"
            f"{len(dictionary_pages)} pages non-empty"
        ),
    )

    check(
        "Methods Paper PDF yields extractable text",
        methods_nonempty_pages > 0,
        (
            f"{methods_nonempty_pages}/"
            f"{len(methods_pages)} pages non-empty"
        ),
    )

    # -----------------------------------------------------------------
    # WRITE FULL EXTRACTED TEXT
    # -----------------------------------------------------------------

    dictionary_full_text = render_full_text(
        (
            "CMS 2014-2024 ORIGINAL MEDICARE "
            "GEOGRAPHIC VARIATION DATA DICTIONARY"
        ),
        dictionary_pages,
    )

    methods_full_text = render_full_text(
        (
            "CMS GEOGRAPHIC VARIATION "
            "PUBLIC USE FILE METHODS PAPER"
        ),
        methods_pages,
    )

    DICTIONARY_TEXT_TXT.write_text(
        dictionary_full_text,
        encoding="utf-8",
    )

    METHODS_TEXT_TXT.write_text(
        methods_full_text,
        encoding="utf-8",
    )

    # -----------------------------------------------------------------
    # TARGETED EVIDENCE
    # -----------------------------------------------------------------

    (
        dictionary_evidence,
        dictionary_counts,
    ) = render_search_evidence(
        (
            "CMS ORIGINAL MEDICARE DATA DICTIONARY "
            "TARGETED EVIDENCE v0.1"
        ),
        dictionary_pages,
        DICTIONARY_TARGETS,
    )

    (
        methods_evidence,
        methods_counts,
    ) = render_search_evidence(
        (
            "CMS ORIGINAL MEDICARE METHODS "
            "TARGETED EVIDENCE v0.1"
        ),
        methods_pages,
        METHODS_TARGETS,
    )

    DICTIONARY_EVIDENCE_TXT.write_text(
        dictionary_evidence,
        encoding="utf-8",
    )

    METHODS_EVIDENCE_TXT.write_text(
        methods_evidence,
        encoding="utf-8",
    )

    # -----------------------------------------------------------------
    # CORE EXTRACTION CHECKS
    # -----------------------------------------------------------------

    tot_count = dictionary_counts.get(
        "TOT_MDCR_PYMT_AMT",
        0,
    )

    check(
        "TOT_MDCR_PYMT_AMT is explicitly present in the 2014-2024 data dictionary",
        tot_count > 0,
        f"{tot_count} occurrence(s)",
    )

    claims_occurrences = (
        methods_counts.get(
            "claim",
            0,
        )
        +
        methods_counts.get(
            "claims",
            0,
        )
    )

    check(
        "Methods Paper contains explicit claims terminology",
        claims_occurrences > 0,
        (
            f"{claims_occurrences} combined "
            "'claim'/'claims' occurrence(s)"
        ),
    )

    ffs_occurrences = (
        methods_counts.get(
            "fee-for-service",
            0,
        )
        +
        methods_counts.get(
            "FFS",
            0,
        )
    )

    check(
        "Methods Paper contains explicit FFS terminology",
        ffs_occurrences > 0,
        (
            f"{ffs_occurrences} combined "
            "fee-for-service/FFS occurrence(s)"
        ),
    )

    ccw_occurrences = (
        methods_counts.get(
            "Chronic Conditions Data Warehouse",
            0,
        )
        +
        methods_counts.get(
            "CCW",
            0,
        )
    )

    check(
        "Methods Paper contains explicit CCW terminology",
        ccw_occurrences > 0,
        (
            f"{ccw_occurrences} combined "
            "CCW occurrence(s)"
        ),
    )

    # -----------------------------------------------------------------
    # REPORT
    # -----------------------------------------------------------------

    overall_pass = all(
        item[
            "status"
        ]
        == "PASS"
        for item in checks
    )

    report = []

    report.append(
        "=" * 120
    )

    report.append(
        "CMS ORIGINAL MEDICARE CONTAINMENT EVIDENCE EXTRACTOR v0.1"
    )

    report.append(
        "=" * 120
    )

    report.append("")

    report.append(
        "BOUNDARY"
    )

    report.append(
        "-" * 120
    )

    report.append(
        "Extracts source evidence defining the Original Medicare Geographic Variation PUF and TOT_MDCR_PYMT_AMT."
    )

    report.append(
        "This artifact does NOT determine MSSP/FFS economic additivity or overlap."
    )

    report.append(
        "It does NOT determine Washington payment-dollar incidence."
    )

    report.append(
        "It does NOT write to the database or principal ledger."
    )

    report.append(
        "Search-term absence is NOT interpreted as evidence of exclusion."
    )

    report.append("")

    # -----------------------------------------------------------------
    # PROVENANCE
    # -----------------------------------------------------------------

    report.append(
        "SOURCE PROVENANCE"
    )

    report.append(
        "-" * 120
    )

    report.append(
        str(
            METHODS_PDF.relative_to(
                REPO_ROOT
            )
        )
    )

    report.append(
        "Methods Paper SHA-256: "
        + methods_sha
    )

    report.append("")

    report.append(
        str(
            CMS_ZIP.relative_to(
                REPO_ROOT
            )
        )
    )

    report.append(
        "CMS ZIP SHA-256: "
        + zip_sha
    )

    report.append("")

    report.append(
        "Embedded dictionary member:"
    )

    report.append(
        EXPECTED_DICTIONARY_MEMBER
    )

    report.append(
        "Embedded dictionary SHA-256: "
        + dictionary_sha
    )

    report.append(
        "Embedded dictionary bytes: "
        f"{len(dictionary_bytes):,}"
    )

    report.append("")

    # -----------------------------------------------------------------
    # ARCHIVE INVENTORY
    # -----------------------------------------------------------------

    report.append(
        "CMS ZIP INVENTORY"
    )

    report.append(
        "-" * 120
    )

    for name in inventory:
        report.append(
            name
        )

    report.append("")

    # -----------------------------------------------------------------
    # TARGET SUMMARY
    # -----------------------------------------------------------------

    report.append(
        "DATA DICTIONARY SEARCH SUMMARY"
    )

    report.append(
        "-" * 120
    )

    for target in DICTIONARY_TARGETS:
        report.append(
            f"{target}: "
            f"{dictionary_counts.get(target, 0)} occurrence(s)"
        )

    report.append("")

    report.append(
        "METHODS PAPER SEARCH SUMMARY"
    )

    report.append(
        "-" * 120
    )

    for target in METHODS_TARGETS:
        count = methods_counts.get(
            target,
            0,
        )

        if count:
            result = (
                f"{count} occurrence(s)"
            )

        else:
            result = (
                "NOT FOUND "
                "(absence is not evidence of exclusion)"
            )

        report.append(
            f"{target}: {result}"
        )

    report.append("")

    # -----------------------------------------------------------------
    # CHECKS
    # -----------------------------------------------------------------

    report.append(
        "CHECKS"
    )

    report.append(
        "-" * 120
    )

    for item in checks:
        report.append(
            f"{item['status']} | "
            f"{item['description']} | "
            f"{item['detail']}"
        )

    report.append("")

    report.append(
        "=" * 120
    )

    report.append(
        "OVERALL CMS ORIGINAL MEDICARE CONTAINMENT EVIDENCE EXTRACTOR v0.1: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )

    report.append(
        "=" * 120
    )

    report.append("")

    report.append(
        "INTERPRETIVE BOUNDARY"
    )

    report.append(
        "-" * 120
    )

    report.append(
        "PASS means the preserved CMS documentation was successfully authenticated and the targeted Original Medicare evidence was extracted."
    )

    report.append(
        "PASS does NOT mean MSSP EarnSaveLoss has been proven additive to Original Medicare / FFS."
    )

    report.append(
        "PASS does NOT mean MSSP payments have Washington payment-dollar incidence."
    )

    report.append(
        "The extracted evidence must be reviewed before an economic-overlap conclusion is made."
    )

    report.append(
        "No source is additive by default."
    )

    report.append("")

    report.append(
        "EVIDENCE WRITTEN"
    )

    report.append(
        "-" * 120
    )

    for path in [
        DICTIONARY_TEXT_TXT,
        METHODS_TEXT_TXT,
        DICTIONARY_EVIDENCE_TXT,
        METHODS_EVIDENCE_TXT,
        REPORT_TXT,
    ]:
        report.append(
            str(
                path.relative_to(
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
        if overall_pass
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )