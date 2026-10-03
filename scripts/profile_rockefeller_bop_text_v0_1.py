"""
ETL-172C-2A
Rockefeller Balance of Payments PDF text extraction and structural profile.

Purpose
-------
Create reproducible UTF-8 text derivatives from the eight preserved
Rockefeller Institute Balance of Payments PDF reports and record a
structural profile of those reports.

Inputs
------
data/raw/rockefeller/balance_of_payments/source/
    rockefeller_bop_report_2017.pdf
    rockefeller_bop_report_2019.pdf
    rockefeller_bop_report_2020.pdf
    rockefeller_bop_report_2021.pdf
    rockefeller_bop_report_2022.pdf
    rockefeller_bop_report_2023.pdf
    rockefeller_bop_report_2024.pdf
    rockefeller_bop_report_2025.pdf

Outputs
-------
data/raw/rockefeller/balance_of_payments/validation/text_extraction_v0_1/
    rockefeller_bop_report_2017.txt
    ...
    rockefeller_bop_report_2025.txt
    extraction_manifest.csv
    structural_profile.csv
    profile_report.txt

Method
------
- pdfinfo supplies PDF metadata and page counts.
- pdftotext -layout -enc UTF-8 creates text derivatives.
- Source PDFs remain untouched.
- Source and derivative SHA-256 hashes are recorded.
- Exact Poppler utility versions are recorded.
- Diagnostic methodology-term presence is recorded.

This stage does NOT:
- interpret Rockefeller methodology,
- certify any allocation formula,
- extract Washington dollar values,
- classify preliminary versus final estimates,
- perform FY/TY mapping,
- calculate federal receipts,
- write to PostgreSQL,
- authorize ledger inclusion.
"""

from __future__ import annotations

import csv
import hashlib
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPORT_YEARS = (
    2017,
    2019,
    2020,
    2021,
    2022,
    2023,
    2024,
    2025,
)

SOURCE_DIR = Path(
    "data/raw/rockefeller/balance_of_payments/source"
)

OUTPUT_DIR = Path(
    "data/raw/rockefeller/balance_of_payments/"
    "validation/text_extraction_v0_1"
)

MANIFEST_PATH = OUTPUT_DIR / "extraction_manifest.csv"
PROFILE_PATH = OUTPUT_DIR / "structural_profile.csv"
REPORT_PATH = OUTPUT_DIR / "profile_report.txt"


DIAGNOSTIC_TERMS = {
    "individual_income_tax": (
        r"\bindividual\s+income\s+tax\b"
    ),
    "corporate_income_tax": (
        r"\bcorporate\s+income\s+tax\b"
    ),
    "social_insurance": (
        r"\bsocial\s+insurance\b"
    ),
    "oasdi": (
        r"\bOASDI\b"
    ),
    "medicare": (
        r"\bMedicare\b"
    ),
    "railroad_retirement": (
        r"\brailroad\s+retirement\b"
    ),
    "unemployment_insurance": (
        r"\bunemployment\s+insurance\b"
    ),
    "estate_tax": (
        r"\bestate\s+tax\b"
    ),
    "gift_tax": (
        r"\bgift\s+tax\b"
    ),
    "excise_tax": (
        r"\bexcise\s+tax(?:es)?\b"
    ),
    "federal_budget": (
        r"\bfederal\s+budget\b"
    ),
    "irs": (
        r"\bIRS\b"
    ),
    "bea": (
        r"\bBEA\b"
    ),
    "seventy_five_percent": (
        r"\b75\s*(?:percent|%)"
    ),
    "twenty_five_percent": (
        r"\b25\s*(?:percent|%)"
    ),
}


@dataclass(frozen=True)
class PdfMetadata:
    pages: int
    title: str
    author: str
    creator: str
    producer: str
    creation_date: str
    mod_date: str
    tagged: str
    encrypted: str
    page_size: str
    file_size: str
    pdf_version: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest().upper()


def run_command(
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def get_tool_path(name: str) -> str:
    path = shutil.which(name)

    if path is None:
        raise RuntimeError(
            f"Required utility not found on PATH: {name}"
        )

    return path


def get_poppler_version(
    executable: str,
) -> str:
    result = run_command(
        [
            executable,
            "-v",
        ]
    )

    combined = "\n".join(
        part
        for part in (
            result.stdout.strip(),
            result.stderr.strip(),
        )
        if part
    )

    match = re.search(
        r"version\s+([0-9][^\s]*)",
        combined,
        flags=re.IGNORECASE,
    )

    if match is None:
        return combined.splitlines()[0] if combined else "UNKNOWN"

    return match.group(1)


def parse_pdfinfo(
    text: str,
) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw_line in text.splitlines():
        if ":" not in raw_line:
            continue

        key, value = raw_line.split(":", 1)

        values[key.strip()] = value.strip()

    return values


def get_pdf_metadata(
    pdfinfo_executable: str,
    pdf_path: Path,
) -> PdfMetadata:
    result = run_command(
        [
            pdfinfo_executable,
            str(pdf_path),
        ]
    )

    values = parse_pdfinfo(result.stdout)

    pages_text = values.get("Pages")

    if pages_text is None:
        raise RuntimeError(
            f"pdfinfo did not report page count: {pdf_path}"
        )

    try:
        pages = int(pages_text)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid page count from pdfinfo: {pages_text}"
        ) from exc

    return PdfMetadata(
        pages=pages,
        title=values.get("Title", ""),
        author=values.get("Author", ""),
        creator=values.get("Creator", ""),
        producer=values.get("Producer", ""),
        creation_date=values.get("CreationDate", ""),
        mod_date=values.get("ModDate", ""),
        tagged=values.get("Tagged", ""),
        encrypted=values.get("Encrypted", ""),
        page_size=values.get("Page size", ""),
        file_size=values.get("File size", ""),
        pdf_version=values.get("PDF version", ""),
    )


def extract_text(
    pdftotext_executable: str,
    pdf_path: Path,
    output_path: Path,
) -> None:
    run_command(
        [
            pdftotext_executable,
            "-layout",
            "-enc",
            "UTF-8",
            str(pdf_path),
            str(output_path),
        ]
    )

    if not output_path.exists():
        raise RuntimeError(
            f"pdftotext did not create output: {output_path}"
        )

    if output_path.stat().st_size == 0:
        raise RuntimeError(
            f"pdftotext created empty output: {output_path}"
        )


def count_pages_with_text(
    text: str,
) -> tuple[int, int]:
    """
    pdftotext separates PDF pages with form-feed characters.
    Return:
        pages represented in text derivative,
        pages containing non-whitespace text.
    """

    pages = text.split("\f")

    if pages and not pages[-1].strip():
        pages = pages[:-1]

    represented = len(pages)

    with_text = sum(
        1
        for page in pages
        if page.strip()
    )

    return represented, with_text


def diagnostic_counts(
    text: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}

    for name, pattern in DIAGNOSTIC_TERMS.items():
        counts[name] = len(
            re.findall(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
        )

    return counts


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
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
        writer.writerows(rows)


def main() -> int:
    print("=" * 92)
    print(
        "ROCKEFELLER BOP PDF TEXT EXTRACTION AND "
        "STRUCTURAL PROFILE v0.1 - ETL-172C-2A"
    )
    print("=" * 92)
    print()
    print("Report vintages : 2017, 2019-2025")
    print("Expected reports: 8")
    print("Source mutation : NONE")
    print("Methodology     : NOT INTERPRETED")
    print("Dollar extract  : NONE")
    print("Database writes : NONE")
    print()

    pdftotext = get_tool_path("pdftotext")
    pdfinfo = get_tool_path("pdfinfo")

    pdftotext_version = get_poppler_version(pdftotext)
    pdfinfo_version = get_poppler_version(pdfinfo)

    print(f"pdftotext       : {pdftotext}")
    print(f"pdftotext ver.  : {pdftotext_version}")
    print(f"pdfinfo         : {pdfinfo}")
    print(f"pdfinfo ver.    : {pdfinfo_version}")
    print()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    protected_outputs = (
        MANIFEST_PATH,
        PROFILE_PATH,
        REPORT_PATH,
    )

    for path in protected_outputs:
        if path.exists():
            raise RuntimeError(
                f"Refusing silent overwrite: {path}"
            )

    existing_text = list(
        OUTPUT_DIR.glob("rockefeller_bop_report_*.txt")
    )

    if existing_text:
        raise RuntimeError(
            "Refusing silent overwrite: derived report text "
            f"already exists in {OUTPUT_DIR}"
        )

    manifest_rows: list[dict[str, object]] = []
    profile_rows: list[dict[str, object]] = []
    report_lines: list[str] = []

    report_lines.extend(
        [
            "=" * 92,
            (
                "ROCKEFELLER BOP PDF TEXT EXTRACTION AND "
                "STRUCTURAL PROFILE v0.1 - ETL-172C-2A"
            ),
            "=" * 92,
            "",
            f"pdftotext version : {pdftotext_version}",
            f"pdfinfo version   : {pdfinfo_version}",
            "",
        ]
    )

    for year in REPORT_YEARS:
        pdf_path = (
            SOURCE_DIR /
            f"rockefeller_bop_report_{year}.pdf"
        )

        text_path = (
            OUTPUT_DIR /
            f"rockefeller_bop_report_{year}.txt"
        )

        if not pdf_path.exists():
            raise RuntimeError(
                f"Missing preserved source PDF: {pdf_path}"
            )

        print(f"Report {year}")

        metadata = get_pdf_metadata(
            pdfinfo,
            pdf_path,
        )

        extract_text(
            pdftotext,
            pdf_path,
            text_path,
        )

        text = text_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        source_hash = sha256_file(pdf_path)
        text_hash = sha256_file(text_path)

        source_bytes = pdf_path.stat().st_size
        text_bytes = text_path.stat().st_size

        character_count = len(text)
        line_count = len(text.splitlines())

        (
            text_pages_represented,
            pages_with_text,
        ) = count_pages_with_text(text)

        pages_without_text = max(
            metadata.pages - pages_with_text,
            0,
        )

        counts = diagnostic_counts(text)

        print(f"  PDF pages       : {metadata.pages}")
        print(f"  source bytes    : {source_bytes}")
        print(f"  text bytes      : {text_bytes}")
        print(f"  characters      : {character_count}")
        print(f"  lines           : {line_count}")
        print(f"  pages with text : {pages_with_text}")
        print(
            "  pages no text   : "
            f"{pages_without_text}"
        )
        print(
            "  individual tax  : "
            f"{counts['individual_income_tax']}"
        )
        print(
            "  corporate tax   : "
            f"{counts['corporate_income_tax']}"
        )
        print(
            "  75 percent      : "
            f"{counts['seventy_five_percent']}"
        )
        print(
            "  25 percent      : "
            f"{counts['twenty_five_percent']}"
        )
        print()

        manifest_rows.append(
            {
                "report_year": year,
                "source_path": str(pdf_path),
                "source_bytes": source_bytes,
                "source_sha256": source_hash,
                "text_path": str(text_path),
                "text_bytes": text_bytes,
                "text_sha256": text_hash,
                "pdftotext_version": pdftotext_version,
                "pdfinfo_version": pdfinfo_version,
                "extraction_options": "-layout -enc UTF-8",
                "extraction_status": "PASS",
            }
        )

        profile_row: dict[str, object] = {
            "report_year": year,
            "pdf_pages": metadata.pages,
            "text_pages_represented": (
                text_pages_represented
            ),
            "pages_with_text": pages_with_text,
            "pages_without_text": pages_without_text,
            "text_characters": character_count,
            "text_lines": line_count,
            "pdf_title": metadata.title,
            "pdf_author": metadata.author,
            "pdf_creator": metadata.creator,
            "pdf_producer": metadata.producer,
            "pdf_creation_date": metadata.creation_date,
            "pdf_mod_date": metadata.mod_date,
            "pdf_tagged": metadata.tagged,
            "pdf_encrypted": metadata.encrypted,
            "pdf_page_size": metadata.page_size,
            "pdf_file_size": metadata.file_size,
            "pdf_version": metadata.pdf_version,
        }

        profile_row.update(counts)

        profile_rows.append(profile_row)

        report_lines.extend(
            [
                f"REPORT {year}",
                "-" * 92,
                f"PDF pages              : {metadata.pages}",
                (
                    "Text pages represented : "
                    f"{text_pages_represented}"
                ),
                (
                    "Pages with text        : "
                    f"{pages_with_text}"
                ),
                (
                    "Pages without text     : "
                    f"{pages_without_text}"
                ),
                (
                    "Extracted characters   : "
                    f"{character_count}"
                ),
                f"Extracted lines        : {line_count}",
                (
                    "Individual income tax  : "
                    f"{counts['individual_income_tax']}"
                ),
                (
                    "Corporate income tax   : "
                    f"{counts['corporate_income_tax']}"
                ),
                (
                    "Social insurance       : "
                    f"{counts['social_insurance']}"
                ),
                f"OASDI                   : {counts['oasdi']}",
                (
                    "Medicare                : "
                    f"{counts['medicare']}"
                ),
                (
                    "Railroad retirement     : "
                    f"{counts['railroad_retirement']}"
                ),
                (
                    "Unemployment insurance : "
                    f"{counts['unemployment_insurance']}"
                ),
                (
                    "Estate tax              : "
                    f"{counts['estate_tax']}"
                ),
                (
                    "Gift tax                : "
                    f"{counts['gift_tax']}"
                ),
                (
                    "Excise tax              : "
                    f"{counts['excise_tax']}"
                ),
                (
                    "Federal budget          : "
                    f"{counts['federal_budget']}"
                ),
                f"IRS                     : {counts['irs']}",
                f"BEA                     : {counts['bea']}",
                (
                    "75 percent / 75%        : "
                    f"{counts['seventy_five_percent']}"
                ),
                (
                    "25 percent / 25%        : "
                    f"{counts['twenty_five_percent']}"
                ),
                "",
            ]
        )

    manifest_fields = [
        "report_year",
        "source_path",
        "source_bytes",
        "source_sha256",
        "text_path",
        "text_bytes",
        "text_sha256",
        "pdftotext_version",
        "pdfinfo_version",
        "extraction_options",
        "extraction_status",
    ]

    profile_fields = [
        "report_year",
        "pdf_pages",
        "text_pages_represented",
        "pages_with_text",
        "pages_without_text",
        "text_characters",
        "text_lines",
        "pdf_title",
        "pdf_author",
        "pdf_creator",
        "pdf_producer",
        "pdf_creation_date",
        "pdf_mod_date",
        "pdf_tagged",
        "pdf_encrypted",
        "pdf_page_size",
        "pdf_file_size",
        "pdf_version",
        *DIAGNOSTIC_TERMS.keys(),
    ]

    write_csv(
        MANIFEST_PATH,
        manifest_rows,
        manifest_fields,
    )

    write_csv(
        PROFILE_PATH,
        profile_rows,
        profile_fields,
    )

    all_reports = (
        len(manifest_rows) == len(REPORT_YEARS)
    )

    all_have_text = all(
        int(row["text_characters"]) > 0
        for row in profile_rows
    )

    all_pages_have_text = all(
        int(row["pages_without_text"]) == 0
        for row in profile_rows
    )

    report_lines.extend(
        [
            "=" * 92,
            "PROFILE SUMMARY",
            "=" * 92,
            "",
            (
                "Expected reports       : "
                f"{len(REPORT_YEARS)}"
            ),
            (
                "Extracted reports      : "
                f"{len(manifest_rows)}"
            ),
            (
                "All reports have text  : "
                f"{'YES' if all_have_text else 'NO'}"
            ),
            (
                "All PDF pages have text: "
                f"{'YES' if all_pages_have_text else 'NO'}"
            ),
            "",
            (
                "Methodology term counts are diagnostic "
                "only."
            ),
            (
                "No methodological meaning has been "
                "certified."
            ),
            "",
        ]
    )

    if all_reports and all_have_text:
        result = "PASS"
    else:
        result = "REVIEW REQUIRED"

    report_lines.append(
        f"PROFILE RESULT: {result}"
    )

    REPORT_PATH.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print("=" * 92)
    print("PROFILE SUMMARY")
    print("=" * 92)
    print()
    print(
        f"Expected reports       : {len(REPORT_YEARS)}"
    )
    print(
        f"Extracted reports      : {len(manifest_rows)}"
    )
    print(
        "All reports have text  : "
        f"{'YES' if all_have_text else 'NO'}"
    )
    print(
        "All PDF pages have text: "
        f"{'YES' if all_pages_have_text else 'NO'}"
    )
    print()
    print("Outputs:")
    print(f"  {MANIFEST_PATH}")
    print(f"  {PROFILE_PATH}")
    print(f"  {REPORT_PATH}")
    print()
    print(f"PROFILE RESULT: {result}")
    print()
    print(
        "PASS certifies successful mechanical text "
        "extraction only."
    )
    print(
        "No Rockefeller methodology or numerical "
        "result has been certified."
    )

    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(
            "ERROR: external Poppler command failed.",
            file=sys.stderr,
        )

        if exc.stdout:
            print(exc.stdout, file=sys.stderr)

        if exc.stderr:
            print(exc.stderr, file=sys.stderr)

        raise