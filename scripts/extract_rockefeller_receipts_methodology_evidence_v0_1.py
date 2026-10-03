"""
ETL-172C-2B
Rockefeller Balance of Payments receipts methodology evidence extraction.

Purpose
-------
Search the frozen UTF-8 text derivatives produced by ETL-172C-2A and
extract page-numbered passages relevant to federal-receipts methodology.

Inputs
------
data/raw/rockefeller/balance_of_payments/validation/text_extraction_v0_1/
    rockefeller_bop_report_2017.txt
    rockefeller_bop_report_2019.txt
    rockefeller_bop_report_2020.txt
    rockefeller_bop_report_2021.txt
    rockefeller_bop_report_2022.txt
    rockefeller_bop_report_2023.txt
    rockefeller_bop_report_2024.txt
    rockefeller_bop_report_2025.txt

Outputs
-------
data/raw/rockefeller/balance_of_payments/validation/
    methodology_evidence_v0_1/
        evidence_index.csv
        evidence_passages.txt
        cluster_summary.csv
        extraction_report.txt

Method
------
The script searches four controlled evidence clusters:

1. Individual income tax
2. Corporate income tax
3. National accounting control
4. Vintage / lag handling

Evidence is preserved by:
- report vintage,
- PDF page number,
- evidence cluster,
- matched search terms,
- complete normalized page text.

A page is emitted only once per evidence cluster even when multiple
search terms match it.

This stage does NOT:
- interpret Rockefeller methodology,
- certify formulas,
- decide whether wording is equivalent across vintages,
- calculate Washington allocation shares,
- extract final ledger dollars,
- perform FY/TY mapping,
- write to PostgreSQL,
- authorize ledger inclusion.
"""

from __future__ import annotations

import csv
import hashlib
import re
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

INPUT_DIR = Path(
    "data/raw/rockefeller/balance_of_payments/"
    "validation/text_extraction_v0_1"
)

OUTPUT_DIR = Path(
    "data/raw/rockefeller/balance_of_payments/"
    "validation/methodology_evidence_v0_1"
)

INDEX_PATH = OUTPUT_DIR / "evidence_index.csv"
PASSAGES_PATH = OUTPUT_DIR / "evidence_passages.txt"
SUMMARY_PATH = OUTPUT_DIR / "cluster_summary.csv"
REPORT_PATH = OUTPUT_DIR / "extraction_report.txt"


SEARCH_CLUSTERS = {
    "INDIVIDUAL_INCOME_TAX": {
        "individual_income_tax": (
            r"\bindividual\s+income\s+tax\b"
        ),
        "A06500": (
            r"\bA06500\b"
        ),
        "A85530": (
            r"\bA85530\b"
        ),
        "A85300": (
            r"\bA85300\b"
        ),
        "liability": (
            r"\bliabilit(?:y|ies)\b"
        ),
        "FICA": (
            r"\bFICA\b"
        ),
        "SECA": (
            r"\bSECA\b"
        ),
    },

    "CORPORATE_INCOME_TAX": {
        "corporate_income_tax": (
            r"\bcorporate\s+income\s+tax\b"
        ),
        "75_percent": (
            r"\b75\s*(?:percent|%)"
        ),
        "25_percent": (
            r"\b25\s*(?:percent|%)"
        ),
        "dividends": (
            r"\bdividends?\b"
        ),
        "interest": (
            r"\binterest\b"
        ),
        "rent": (
            r"\brents?\b"
        ),
        "proprietors": (
            r"\bproprietors?'?\s+income\b"
        ),
        "wages_and_salaries": (
            r"\bwages?\s+and\s+salaries\b"
        ),
    },

    "NATIONAL_ACCOUNTING_CONTROL": {
        "federal_budget": (
            r"\bfederal\s+budget\b"
        ),
        "federal_receipts": (
            r"\bfederal\s+receipts\b"
        ),
        "budget_receipts": (
            r"\bbudget\s+receipts\b"
        ),
        "allocated": (
            r"\ballocat(?:e|ed|es|ing|ion|ions)\b"
        ),
        "unallocable": (
            r"\bunallocable\b"
        ),
        "unallocated": (
            r"\bunallocated\b"
        ),
        "receipts": (
            r"\breceipts\b"
        ),
    },

    "VINTAGE_LAG_HANDLING": {
        "preliminary": (
            r"\bpreliminary\b"
        ),
        "revised": (
            r"\brevis(?:e|ed|es|ing|ion|ions)\b"
        ),
        "latest": (
            r"\blatest\b"
        ),
        "available": (
            r"\bavailable\b"
        ),
        "state_share": (
            r"\bstate\s+shares?\b"
        ),
        "prior_year": (
            r"\bprior\s+year\b"
        ),
        "previous_year": (
            r"\bprevious\s+year\b"
        ),
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest().upper()


def split_pdf_pages(text: str) -> list[str]:
    """
    pdftotext separates source PDF pages with form-feed characters.

    Preserve page order so list index + 1 corresponds to the physical
    PDF page number.
    """

    pages = text.split("\f")

    if pages and not pages[-1].strip():
        pages = pages[:-1]

    return pages


def normalize_page_text(text: str) -> str:
    """
    Normalize only line endings and trailing whitespace.

    Do not collapse substantive line structure because the -layout
    derivative is itself useful evidence.
    """

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    lines = [
        line.rstrip()
        for line in text.splitlines()
    ]

    return "\n".join(lines).strip()


def find_matches(
    text: str,
    patterns: dict[str, str],
) -> list[str]:
    matches: list[str] = []

    for term_name, pattern in patterns.items():
        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            matches.append(term_name)

    return matches


def compact_excerpt(
    text: str,
    matched_terms: list[str],
    patterns: dict[str, str],
    radius: int = 2,
) -> str:
    """
    Produce a compact human-review excerpt around matching lines.

    The complete page is separately preserved in evidence_passages.txt.
    This excerpt exists only to make evidence_index.csv easy to inspect.
    """

    lines = text.splitlines()

    matching_line_numbers: set[int] = set()

    active_patterns = [
        patterns[name]
        for name in matched_terms
    ]

    for line_number, line in enumerate(lines):
        if any(
            re.search(
                pattern,
                line,
                flags=re.IGNORECASE,
            )
            for pattern in active_patterns
        ):
            matching_line_numbers.add(line_number)

    selected: set[int] = set()

    for line_number in matching_line_numbers:
        start = max(
            0,
            line_number - radius,
        )

        end = min(
            len(lines),
            line_number + radius + 1,
        )

        selected.update(
            range(start, end)
        )

    excerpt_lines: list[str] = []
    previous: int | None = None

    for line_number in sorted(selected):
        if (
            previous is not None
            and line_number > previous + 1
        ):
            excerpt_lines.append("[...]")

        line = lines[line_number].strip()

        if line:
            excerpt_lines.append(line)

        previous = line_number

    excerpt = " | ".join(excerpt_lines)

    # Keep CSV manageable. Complete page remains in evidence_passages.txt.
    if len(excerpt) > 4000:
        excerpt = excerpt[:3997] + "..."

    return excerpt


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
        "ROCKEFELLER RECEIPTS METHODOLOGY EVIDENCE "
        "EXTRACTION v0.1 - ETL-172C-2B"
    )
    print("=" * 92)
    print()
    print("Report vintages : 2017, 2019-2025")
    print("Expected reports: 8")
    print("Input           : FROZEN ETL-172C-2A TEXT")
    print("Interpretation  : NONE")
    print("Dollar extract  : NONE")
    print("Database writes : NONE")
    print()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    protected_outputs = (
        INDEX_PATH,
        PASSAGES_PATH,
        SUMMARY_PATH,
        REPORT_PATH,
    )

    for path in protected_outputs:
        if path.exists():
            raise RuntimeError(
                f"Refusing silent overwrite: {path}"
            )

    evidence_rows: list[dict[str, object]] = []
    passage_blocks: list[str] = []
    summary_rows: list[dict[str, object]] = []
    report_lines: list[str] = []

    report_lines.extend(
        [
            "=" * 92,
            (
                "ROCKEFELLER RECEIPTS METHODOLOGY EVIDENCE "
                "EXTRACTION v0.1 - ETL-172C-2B"
            ),
            "=" * 92,
            "",
        ]
    )

    total_pages = 0
    total_evidence_records = 0

    for year in REPORT_YEARS:
        input_path = (
            INPUT_DIR /
            f"rockefeller_bop_report_{year}.txt"
        )

        if not input_path.exists():
            raise RuntimeError(
                f"Missing ETL-172C-2A text derivative: {input_path}"
            )

        text = input_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        pages = split_pdf_pages(text)
        text_hash = sha256_file(input_path)

        total_pages += len(pages)

        print(f"Report {year}")
        print(f"  pages: {len(pages)}")

        report_lines.extend(
            [
                f"REPORT {year}",
                "-" * 92,
                f"Text SHA-256: {text_hash}",
                f"Pages        : {len(pages)}",
            ]
        )

        for cluster_name, patterns in SEARCH_CLUSTERS.items():
            cluster_pages = 0
            cluster_records = 0
            cluster_term_counts = {
                term: 0
                for term in patterns
            }

            for page_number, raw_page in enumerate(
                pages,
                start=1,
            ):
                page_text = normalize_page_text(
                    raw_page
                )

                if not page_text:
                    continue

                matched_terms = find_matches(
                    page_text,
                    patterns,
                )

                if not matched_terms:
                    continue

                cluster_pages += 1
                cluster_records += 1
                total_evidence_records += 1

                for term in matched_terms:
                    cluster_term_counts[term] += 1

                excerpt = compact_excerpt(
                    page_text,
                    matched_terms,
                    patterns,
                )

                evidence_id = (
                    f"R{year}_P{page_number:03d}_"
                    f"{cluster_name}"
                )

                evidence_rows.append(
                    {
                        "evidence_id": evidence_id,
                        "report_year": year,
                        "pdf_page": page_number,
                        "cluster": cluster_name,
                        "matched_terms": ";".join(
                            matched_terms
                        ),
                        "matched_term_count": len(
                            matched_terms
                        ),
                        "text_source_sha256": text_hash,
                        "excerpt": excerpt,
                    }
                )

                passage_blocks.extend(
                    [
                        "=" * 100,
                        f"EVIDENCE ID : {evidence_id}",
                        f"REPORT      : {year}",
                        f"PDF PAGE    : {page_number}",
                        f"CLUSTER     : {cluster_name}",
                        (
                            "MATCHED     : "
                            + ", ".join(matched_terms)
                        ),
                        (
                            "TEXT SHA256 : "
                            + text_hash
                        ),
                        "-" * 100,
                        page_text,
                        "",
                    ]
                )

            summary_row: dict[str, object] = {
                "report_year": year,
                "cluster": cluster_name,
                "matching_pages": cluster_pages,
                "evidence_records": cluster_records,
            }

            for term, count in cluster_term_counts.items():
                summary_row[
                    f"term_{term}_pages"
                ] = count

            summary_rows.append(
                summary_row
            )

            print(
                f"  {cluster_name:<29} "
                f"{cluster_pages:>3} pages"
            )

            report_lines.append(
                f"{cluster_name:<29}: "
                f"{cluster_pages} matching pages"
            )

        print()
        report_lines.append("")

    evidence_fields = [
        "evidence_id",
        "report_year",
        "pdf_page",
        "cluster",
        "matched_terms",
        "matched_term_count",
        "text_source_sha256",
        "excerpt",
    ]

    all_summary_term_fields: list[str] = []

    for patterns in SEARCH_CLUSTERS.values():
        for term in patterns:
            field = f"term_{term}_pages"

            if field not in all_summary_term_fields:
                all_summary_term_fields.append(field)

    summary_fields = [
        "report_year",
        "cluster",
        "matching_pages",
        "evidence_records",
        *all_summary_term_fields,
    ]

    #
    # DictWriter requires all named fields to exist.
    #
    for row in summary_rows:
        for field in all_summary_term_fields:
            row.setdefault(
                field,
                0,
            )

    write_csv(
        INDEX_PATH,
        evidence_rows,
        evidence_fields,
    )

    write_csv(
        SUMMARY_PATH,
        summary_rows,
        summary_fields,
    )

    PASSAGES_PATH.write_text(
        "\n".join(passage_blocks) + "\n",
        encoding="utf-8",
    )

    #
    # Structural completeness check:
    # each report must produce at least one evidence page for
    # each of the four clusters.
    #
    missing_clusters: list[str] = []

    for year in REPORT_YEARS:
        for cluster_name in SEARCH_CLUSTERS:
            found = any(
                row["report_year"] == year
                and row["cluster"] == cluster_name
                and int(row["matching_pages"]) > 0
                for row in summary_rows
            )

            if not found:
                missing_clusters.append(
                    f"{year}:{cluster_name}"
                )

    report_lines.extend(
        [
            "=" * 92,
            "EXTRACTION SUMMARY",
            "=" * 92,
            "",
            (
                "Reports processed       : "
                f"{len(REPORT_YEARS)}"
            ),
            (
                "PDF pages represented   : "
                f"{total_pages}"
            ),
            (
                "Evidence records        : "
                f"{total_evidence_records}"
            ),
            (
                "Missing report/clusters : "
                f"{len(missing_clusters)}"
            ),
        ]
    )

    if missing_clusters:
        report_lines.append("")

        for item in missing_clusters:
            report_lines.append(
                f"  MISSING: {item}"
            )

    report_lines.extend(
        [
            "",
            (
                "Evidence extraction is mechanical only."
            ),
            (
                "Matching text has not been interpreted "
                "or certified."
            ),
            "",
        ]
    )

    if missing_clusters:
        result = "REVIEW REQUIRED"
    else:
        result = "PASS"

    report_lines.append(
        f"EXTRACTION RESULT: {result}"
    )

    REPORT_PATH.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print("=" * 92)
    print("EXTRACTION SUMMARY")
    print("=" * 92)
    print()
    print(
        f"Reports processed       : {len(REPORT_YEARS)}"
    )
    print(
        f"PDF pages represented   : {total_pages}"
    )
    print(
        f"Evidence records        : {total_evidence_records}"
    )
    print(
        "Missing report/clusters : "
        f"{len(missing_clusters)}"
    )

    if missing_clusters:
        print()

        for item in missing_clusters:
            print(f"  MISSING: {item}")

    print()
    print("Outputs:")
    print(f"  {INDEX_PATH}")
    print(f"  {PASSAGES_PATH}")
    print(f"  {SUMMARY_PATH}")
    print(f"  {REPORT_PATH}")
    print()
    print(f"EXTRACTION RESULT: {result}")
    print()
    print(
        "PASS certifies evidence discovery only."
    )
    print(
        "No Rockefeller methodology or numerical "
        "result has been certified."
    )

    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())