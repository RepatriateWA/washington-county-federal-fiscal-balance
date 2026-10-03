from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "federal_receipts"
    / "validation"
    / "social_insurance_control_inventory_v0_1"
)

CANDIDATE_CSV = OUTPUT_DIR / "candidate_files.csv"
REPORT_TXT = OUTPUT_DIR / "inventory_report.txt"

SEARCH_ROOTS = [
    REPO_ROOT / "data" / "raw",
]

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
}

# Files likely to be useful as actual federal receipt controls.
HIGH_VALUE_PATH_TERMS = [
    "budget",
    "historical",
    "hist2",
    "hist2.4",
    "receipt",
    "receipts",
    "treasury",
    "omb",
    "social_insurance",
    "social insurance",
]

# Terms that may indicate the right content even when the filename
# is generic.
SEMANTIC_TERMS = [
    "old-age",
    "old age",
    "survivors",
    "disability insurance",
    "oasdi",
    "oasi",
    "hospital insurance",
    "social insurance",
    "social security",
    "medicare",
    "employment taxes",
    "contributions",
    "trust fund",
]

# Existing allocator/expenditure families should remain visible if
# encountered, but they should not rank as national receipt controls.
LOW_VALUE_PATH_TERMS = [
    "earnings_employment",
    "historic_table_2",
    "gross_collections",
    "county",
    "beneficiary",
    "medicare_core",
    "usaspending",
    "va_gdx",
]

TEXT_EXTENSIONS = {
    ".txt",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".md",
}

DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".xls",
    ".xlsx",
    ".doc",
    ".docx",
}

MAX_TEXT_BYTES = 20_000_000


def normalize(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        text.lower(),
    ).strip()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def should_skip(path: Path) -> bool:
    return any(
        part.lower() in SKIP_DIR_NAMES
        for part in path.parts
    )


def filename_score(path: Path) -> tuple[int, list[str]]:
    text = normalize(str(path))
    score = 0
    reasons: list[str] = []

    for term in HIGH_VALUE_PATH_TERMS:
        if term in text:
            score += 4
            reasons.append(
                f"HIGH_PATH:{term}"
            )

    for term in SEMANTIC_TERMS:
        if term in text:
            score += 2
            reasons.append(
                f"SEMANTIC_PATH:{term}"
            )

    for term in LOW_VALUE_PATH_TERMS:
        if term in text:
            score -= 2
            reasons.append(
                f"LOW_PATH:{term}"
            )

    return score, reasons


def read_text_if_reasonable(path: Path) -> str:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return ""

    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return ""

        return path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        return ""


def content_score(text: str) -> tuple[int, list[str]]:
    if not text:
        return 0, []

    normalized = normalize(text)

    score = 0
    reasons: list[str] = []

    high_content_terms = [
        "social insurance and retirement receipts",
        "social insurance and retirement",
        "old-age and survivors insurance",
        "old-age, survivors insurance",
        "disability insurance receipts",
        "hospital insurance receipts",
        "employment and general retirement",
        "federal receipts",
        "historical tables",
        "table 2.4",
    ]

    for term in high_content_terms:
        if term in normalized:
            score += 6
            reasons.append(
                f"HIGH_CONTENT:{term}"
            )

    for term in SEMANTIC_TERMS:
        if term in normalized:
            score += 1
            reasons.append(
                f"SEMANTIC_CONTENT:{term}"
            )

    return score, reasons


def classify(
    path: Path,
    score: int,
    reasons: list[str],
) -> str:
    normalized = normalize(str(path))

    if (
        "rockefeller" in normalized
        and "balance_of_payments" in normalized
    ):
        return "METHODOLOGY_REFERENCE"

    if "earnings_employment" in normalized:
        return "STATE_ALLOCATOR_SOURCE"

    if "gross_collections" in normalized:
        return "ADMINISTRATIVE_STATE_RECEIPTS"

    if (
        "object_class" in normalized
        or "object class" in normalized
    ):
        return "EXPENDITURE_SIDE_OMB"

    if any(
        term in normalized
        for term in (
            "historical",
            "hist2",
            "budget",
            "treasury",
        )
    ):
        if score >= 4:
            return "POTENTIAL_NATIONAL_CONTROL"

    if score >= 10:
        return "POTENTIAL_NATIONAL_CONTROL"

    if score >= 4:
        return "SEMANTIC_REVIEW"

    return "LOW_PRIORITY"


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows: list[dict[str, str | int]] = []
    scanned = 0

    print("=" * 100)
    print(
        "ETL-172F-1 NATIONAL SOCIAL-INSURANCE "
        "RECEIPT CONTROL INVENTORY"
    )
    print("=" * 100)
    print()
    print(
        "Inventory only. No acquisition, receipt extraction, "
        "allocation, reconciliation, or DB writes."
    )
    print()

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if should_skip(path):
                continue

            scanned += 1

            suffix = path.suffix.lower()

            if (
                suffix not in TEXT_EXTENSIONS
                and suffix not in DOCUMENT_EXTENSIONS
            ):
                continue

            path_score, path_reasons = filename_score(path)

            text = read_text_if_reasonable(path)

            text_score, text_reasons = content_score(text)

            score = path_score + text_score
            reasons = path_reasons + text_reasons

            if score <= 0:
                continue

            classification = classify(
                path,
                score,
                reasons,
            )

            rows.append(
                {
                    "path": relative(path),
                    "extension": suffix,
                    "bytes": path.stat().st_size,
                    "score": score,
                    "classification": classification,
                    "reasons": "; ".join(reasons),
                }
            )

    rows.sort(
        key=lambda row: (
            -int(row["score"]),
            str(row["path"]).lower(),
        )
    )

    fieldnames = [
        "path",
        "extension",
        "bytes",
        "score",
        "classification",
        "reasons",
    ]

    with CANDIDATE_CSV.open(
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

    classifications = Counter(
        str(row["classification"])
        for row in rows
    )

    potential_controls = [
        row
        for row in rows
        if row["classification"]
        == "POTENTIAL_NATIONAL_CONTROL"
    ]

    report_lines = [
        "=" * 100,
        (
            "ETL-172F-1 NATIONAL SOCIAL-INSURANCE "
            "RECEIPT CONTROL INVENTORY"
        ),
        "=" * 100,
        "",
        (
            "Inventory only. No acquisition, receipt extraction, "
            "allocation, reconciliation, or DB writes."
        ),
        "",
        f"Files scanned                 : {scanned:,}",
        f"Candidate files retained      : {len(rows):,}",
        (
            "Potential national controls   : "
            f"{len(potential_controls):,}"
        ),
        "",
        "CLASSIFICATIONS",
        "-" * 100,
    ]

    for name, count in sorted(
        classifications.items()
    ):
        report_lines.append(
            f"{name:<35} {count:>8,}"
        )

    report_lines.extend(
        [
            "",
            "TOP POTENTIAL NATIONAL CONTROLS",
            "-" * 100,
        ]
    )

    if potential_controls:
        for row in potential_controls[:50]:
            report_lines.append(
                f"{int(row['score']):>4} | "
                f"{row['path']}"
            )
    else:
        report_lines.append(
            "NONE IDENTIFIED"
        )

    report_lines.extend(
        [
            "",
            "INTERPRETATION",
            "-" * 100,
            (
                "POTENTIAL_NATIONAL_CONTROL means only that an "
                "existing repository artifact merits semantic "
                "inspection as a possible federal receipt control."
            ),
            (
                "It does not certify that the artifact contains "
                "OASI, DI, or Hospital Insurance national receipts."
            ),
            (
                "METHODOLOGY_REFERENCE artifacts may describe the "
                "Rockefeller method but are not themselves federal "
                "national controls."
            ),
            (
                "STATE_ALLOCATOR_SOURCE artifacts contain allocation "
                "inputs, not federal national receipt totals."
            ),
            "",
        ]
    )

    REPORT_TXT.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    print(f"Files scanned               : {scanned:,}")
    print(f"Candidate files retained    : {len(rows):,}")
    print(
        "Potential national controls : "
        f"{len(potential_controls):,}"
    )
    print()

    print("CLASSIFICATIONS")
    print("-" * 100)

    for name, count in sorted(
        classifications.items()
    ):
        print(
            f"{name:<35} {count:>8,}"
        )

    print()
    print("TOP POTENTIAL NATIONAL CONTROLS")
    print("-" * 100)

    if potential_controls:
        for row in potential_controls[:25]:
            print(
                f"{int(row['score']):>4} | "
                f"{row['path']}"
            )
    else:
        print("NONE IDENTIFIED")

    print()
    print(
        f"Candidate CSV : {relative(CANDIDATE_CSV)}"
    )
    print(
        f"Report        : {relative(REPORT_TXT)}"
    )
    print()
    print("ETL-172F-1 RESULT: INVENTORY COMPLETE")

    return 0


if __name__ == "__main__":
    sys.exit(main())