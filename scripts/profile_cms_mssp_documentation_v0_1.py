"""
WCFFBP
CMS MSSP Documentation Source Profiler v0.1

READ-ONLY.

Purpose:
    Certify the physical and logical structure of the CMS documentation
    package downloaded with the MSSP Performance Year Financial and
    Quality Results datasets.

This profiler:
    - preserves the outer ZIP as authoritative source bytes;
    - inventories all embedded PDF members;
    - computes SHA-256 for each embedded PDF;
    - identifies byte-identical duplicates;
    - groups unique documents;
    - records CMS archive-folder context;
    - extracts PDF text in memory;
    - profiles document titles / first-page text;
    - searches for key MSSP financial-field vocabulary;
    - does NOT infer financial semantics from filenames alone;
    - does NOT calculate payments;
    - does NOT perform geographic allocation;
    - does NOT write to PostgreSQL;
    - does NOT authorize ledger inclusion.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_ZIP = (
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
    / "documentation"
    / "validation"
    / "documentation_profile_v0_1"
)

MEMBER_CSV = OUTPUT_DIR / "cms_mssp_documentation_member_inventory_v0_1.csv"
UNIQUE_CSV = OUTPUT_DIR / "cms_mssp_documentation_unique_documents_v0_1.csv"
TERM_CSV = OUTPUT_DIR / "cms_mssp_documentation_term_profile_v0_1.csv"
CHECKS_CSV = OUTPUT_DIR / "cms_mssp_documentation_checks_v0_1.csv"
REPORT_TXT = OUTPUT_DIR / "cms_mssp_documentation_report_v0_1.txt"


SEARCH_TERMS = [
    "EarnSaveLoss",
    "GenSaveLoss",
    "Adv_Pay",
    "Adv_Pay_Amt",
    "Adv_Pay_Recoup",
    "AIPRecoup",
    "AIM",
    "ACO_ID",
    "ACO_Num",
    "ACO_State",
    "benchmark",
    "generated savings",
    "earned shared savings",
    "shared savings payment",
    "advance payment",
    "recoup",
    "sequestration",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            h.update(block)

    return h.hexdigest().upper()


def archive_period(member_name: str) -> str:
    text = member_name.replace("\\", "/").lower()

    if "2019_off-cycle_1" in text:
        return "2019A"

    match = re.search(r"/(20\d{2})/", text)

    if match:
        return match.group(1)

    return "UNRESOLVED"


def extract_pdf_text(data: bytes) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(data))

    pages = []

    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")

    return "\n".join(pages), len(reader.pages)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def first_text_excerpt(text: str, length: int = 500) -> str:
    clean = normalize_space(text)
    return clean[:length]


def term_present(text: str, term: str) -> bool:
    return term.lower() in text.lower()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_ZIP.exists():
        raise FileNotFoundError(
            f"Required documentation ZIP not found: {SOURCE_ZIP}"
        )

    outer_bytes = SOURCE_ZIP.stat().st_size
    outer_sha256 = sha256_file(SOURCE_ZIP)

    member_rows = []
    term_rows = []
    errors = []

    # Hash -> member observations
    hash_members: dict[str, list[dict]] = defaultdict(list)

    with zipfile.ZipFile(SOURCE_ZIP, "r") as archive:
        pdf_members = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and info.filename.lower().endswith(".pdf")
        ]

        for info in pdf_members:
            data = archive.read(info)
            digest = sha256_bytes(data)
            period = archive_period(info.filename)

            try:
                text, pages = extract_pdf_text(data)
                text_status = "PASS"
            except Exception as exc:
                text = ""
                pages = 0
                text_status = "FAIL"
                errors.append(
                    f"{info.filename}: PDF text extraction failed: {exc}"
                )

            excerpt = first_text_excerpt(text)

            observation = {
                "archive_period": period,
                "member_name": info.filename,
                "member_bytes": len(data),
                "compressed_bytes": info.compress_size,
                "sha256": digest,
                "pages": pages,
                "text_characters": len(text),
                "text_extraction_status": text_status,
                "first_text_excerpt": excerpt,
            }

            member_rows.append(observation)
            hash_members[digest].append(observation)

            for term in SEARCH_TERMS:
                count = text.lower().count(term.lower())

                term_rows.append(
                    {
                        "archive_period": period,
                        "member_name": info.filename,
                        "sha256": digest,
                        "search_term": term,
                        "occurrence_count": count,
                        "present": "YES" if count > 0 else "NO",
                    }
                )

    unique_rows = []

    for digest, observations in sorted(hash_members.items()):
        periods = sorted(
            {row["archive_period"] for row in observations},
            key=lambda value: (
                2019.5
                if value == "2019A"
                else int(value)
                if value.isdigit()
                else 9999
            ),
        )

        names = sorted(
            {Path(row["member_name"]).name for row in observations}
        )

        representative = observations[0]

        unique_rows.append(
            {
                "sha256": digest,
                "physical_member_count": len(observations),
                "archive_periods": ";".join(periods),
                "filenames": ";".join(names),
                "member_bytes": representative["member_bytes"],
                "pages": representative["pages"],
                "text_characters": representative["text_characters"],
                "text_extraction_status": representative[
                    "text_extraction_status"
                ],
                "first_text_excerpt": representative[
                    "first_text_excerpt"
                ],
            }
        )

    checks = []

    def add_check(name: str, passed: bool, detail: str) -> None:
        checks.append(
            {
                "check": name,
                "status": "PASS" if passed else "FAIL",
                "detail": detail,
            }
        )

    add_check(
        "Source documentation ZIP exists and is nonzero",
        outer_bytes > 0,
        f"{outer_bytes:,} bytes",
    )

    add_check(
        "Exactly 22 PDF members observed",
        len(member_rows) == 22,
        f"{len(member_rows)}/22",
    )

    add_check(
        "All PDF members are nonzero",
        all(row["member_bytes"] > 0 for row in member_rows),
        (
            f"{sum(row['member_bytes'] <= 0 for row in member_rows)} "
            "zero-byte PDFs"
        ),
    )

    add_check(
        "All PDF members yield readable page structure",
        all(row["pages"] > 0 for row in member_rows),
        (
            f"{sum(row['pages'] <= 0 for row in member_rows)} "
            "PDFs with zero readable pages"
        ),
    )

    add_check(
        "All PDF members yield extractable text",
        all(
            row["text_extraction_status"] == "PASS"
            and row["text_characters"] > 0
            for row in member_rows
        ),
        (
            f"{sum(row['text_extraction_status'] != 'PASS' or row['text_characters'] <= 0 for row in member_rows)} "
            "PDF text failures"
        ),
    )

    add_check(
        "All documentation archive periods resolved",
        all(row["archive_period"] != "UNRESOLVED" for row in member_rows),
        (
            f"{sum(row['archive_period'] == 'UNRESOLVED' for row in member_rows)} "
            "unresolved members"
        ),
    )

    duplicate_members = len(member_rows) - len(unique_rows)

    add_check(
        "Duplicate physical documentation explicitly identified",
        duplicate_members > 0,
        (
            f"{len(member_rows)} physical PDFs -> "
            f"{len(unique_rows)} unique byte-level documents; "
            f"{duplicate_members} duplicate copies"
        ),
    )

    # We expect documentation to contain at least the central
    # savings/loss vocabulary somewhere, but we do not require every
    # document to contain every term.
    terms_anywhere = {
        row["search_term"]
        for row in term_rows
        if row["present"] == "YES"
    }

    add_check(
        "EarnSaveLoss documented somewhere in package",
        "EarnSaveLoss" in terms_anywhere,
        "Lexical documentation check only",
    )

    add_check(
        "GenSaveLoss documented somewhere in package",
        "GenSaveLoss" in terms_anywhere,
        "Lexical documentation check only",
    )

    add_check(
        "Advance-payment vocabulary documented somewhere",
        any(
            term in terms_anywhere
            for term in [
                "Adv_Pay",
                "Adv_Pay_Amt",
                "Adv_Pay_Recoup",
                "advance payment",
            ]
        ),
        "Lexical documentation check only",
    )

    write_csv(
        MEMBER_CSV,
        [
            "archive_period",
            "member_name",
            "member_bytes",
            "compressed_bytes",
            "sha256",
            "pages",
            "text_characters",
            "text_extraction_status",
            "first_text_excerpt",
        ],
        member_rows,
    )

    write_csv(
        UNIQUE_CSV,
        [
            "sha256",
            "physical_member_count",
            "archive_periods",
            "filenames",
            "member_bytes",
            "pages",
            "text_characters",
            "text_extraction_status",
            "first_text_excerpt",
        ],
        unique_rows,
    )

    write_csv(
        TERM_CSV,
        [
            "archive_period",
            "member_name",
            "sha256",
            "search_term",
            "occurrence_count",
            "present",
        ],
        term_rows,
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
        and all(check["status"] == "PASS" for check in checks)
    )

    lines = []

    lines.append("=" * 100)
    lines.append("CMS MSSP DOCUMENTATION SOURCE PROFILE v0.1")
    lines.append("=" * 100)
    lines.append("")

    lines.append("SOURCE ARTIFACT")
    lines.append("-" * 100)
    lines.append(f"Path:    {SOURCE_ZIP.relative_to(REPO_ROOT)}")
    lines.append(f"Bytes:   {outer_bytes:,}")
    lines.append(f"SHA-256: {outer_sha256}")
    lines.append("")

    lines.append("BOUNDARY")
    lines.append("-" * 100)
    lines.append("READ-ONLY documentation profiling.")
    lines.append("No payment reconstruction.")
    lines.append("No Washington-dollar calculation.")
    lines.append("No geographic allocation.")
    lines.append("No database writes.")
    lines.append("No ledger inclusion.")
    lines.append("")

    lines.append("PHYSICAL / LOGICAL DOCUMENT INVENTORY")
    lines.append("-" * 100)
    lines.append(f"Physical PDF members: {len(member_rows)}")
    lines.append(f"Unique byte-level documents: {len(unique_rows)}")
    lines.append(
        f"Duplicate physical copies: {len(member_rows) - len(unique_rows)}"
    )
    lines.append("")

    for index, row in enumerate(unique_rows, start=1):
        lines.append(f"UNIQUE DOCUMENT {index}")
        lines.append(f"  SHA-256: {row['sha256']}")
        lines.append(
            f"  Physical copies: {row['physical_member_count']}"
        )
        lines.append(
            f"  Archive periods: {row['archive_periods']}"
        )
        lines.append(f"  Filenames: {row['filenames']}")
        lines.append(f"  Bytes: {row['member_bytes']:,}")
        lines.append(f"  Pages: {row['pages']}")
        lines.append(
            f"  Text characters: {row['text_characters']:,}"
        )
        lines.append(
            f"  First text: {row['first_text_excerpt']}"
        )
        lines.append("")

    lines.append("TERM COVERAGE")
    lines.append("-" * 100)

    for term in SEARCH_TERMS:
        matching = [
            row
            for row in term_rows
            if row["search_term"] == term
            and row["present"] == "YES"
        ]

        unique_hashes = {
            row["sha256"]
            for row in matching
        }

        lines.append(
            f"{term:<30} "
            f"physical_docs={len(matching):>2} "
            f"unique_docs={len(unique_hashes):>2}"
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

    if errors:
        lines.append("")
        lines.append("ERRORS")
        lines.append("-" * 100)

        for error in errors:
            lines.append(f"FAIL | {error}")

    lines.append("")
    lines.append("=" * 100)
    lines.append(
        "OVERALL CMS MSSP DOCUMENTATION SOURCE PROFILE v0.1: "
        + ("PASS" if overall_pass else "FAIL")
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("Interpretive boundary:")
    lines.append(
        "  Archive-folder placement is provenance, not proof that a "
        "document semantically governs that performance year."
    )
    lines.append(
        "  Byte-identical copies are retained in the physical manifest "
        "but collapsed for logical-document analysis."
    )
    lines.append(
        "  Search-term occurrence establishes lexical coverage only, "
        "not accounting meaning."
    )
    lines.append(
        "  The apparent 2025-named dictionary stored under the 2024 "
        "archive folder requires semantic inspection before it can be "
        "used as evidence for PY2024."
    )
    lines.append(
        "  No MSSP payment field is additive by default."
    )

    report = "\n".join(lines)

    REPORT_TXT.write_text(report, encoding="utf-8")

    print(report)
    print("")
    print("Evidence written:")

    for path in [
        MEMBER_CSV,
        UNIQUE_CSV,
        TERM_CSV,
        CHECKS_CSV,
        REPORT_TXT,
    ]:
        print(f"  {path.relative_to(REPO_ROOT)}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
