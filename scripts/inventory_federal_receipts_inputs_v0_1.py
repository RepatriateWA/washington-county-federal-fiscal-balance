from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = REPO_ROOT / "data" / "raw"

OUTPUT_DIR = (
    RAW_ROOT
    / "rockefeller"
    / "balance_of_payments"
    / "validation"
    / "receipts_input_gap_analysis_v0_1"
)

INVENTORY_CSV = OUTPUT_DIR / "candidate_file_inventory.csv"
SUMMARY_CSV = OUTPUT_DIR / "input_gap_summary.csv"
REPORT_TXT = OUTPUT_DIR / "gap_analysis_report.txt"


@dataclass(frozen=True)
class InputRequirement:
    requirement_id: str
    receipt_category: str
    allocator: str
    expected_source: str
    search_terms: tuple[str, ...]
    preliminary_status: str
    notes: str


REQUIREMENTS = (
    InputRequirement(
        "INDIVIDUAL_INCOME_TAX",
        "Individual income tax",
        "State share of A06500 + A85530 + A85300",
        "IRS SOI Historic Table 2",
        (
            "historic_table_2",
            "in54cm",
            "in55cm",
        ),
        "CANDIDATE_PRESENT",
        "ETL-172B preserved TY2015-TY2023; TY2024 unavailable.",
    ),
    InputRequirement(
        "OASDI_RECEIPTS",
        "OASI / DI employment taxes",
        "State share of covered earnings or contributions",
        "Social Security Administration",
        (
            "eedata",
            "earnings",
            "covered",
            "contribution",
            "oasdi",
        ),
        "REQUIRES_SEMANTIC_CHECK",
        "Do not confuse benefit-payment files with covered-earnings/contribution allocators.",
    ),
    InputRequirement(
        "MEDICARE_HI_RECEIPTS",
        "Medicare Hospital Insurance employment taxes",
        "State share of Medicare-covered earnings or HI contributions",
        "Social Security Administration",
        (
            "eedata",
            "earnings",
            "covered",
            "hospital",
            "medicare",
            "contribution",
        ),
        "REQUIRES_SEMANTIC_CHECK",
        "Medicare expenditure files are not the HI receipts allocator.",
    ),
    InputRequirement(
        "RAILROAD_RETIREMENT",
        "Railroad retirement",
        "Direct state gross collections",
        "IRS Gross Collections Table 5",
        (
            "gross_collections",
            "table5",
            "table_5",
        ),
        "CANDIDATE_PRESENT",
        "ETL-171 certified the IRS Table 5 source family for FFY2015-FFY2024.",
    ),
    InputRequirement(
        "UNEMPLOYMENT_INSURANCE",
        "Unemployment insurance",
        "State UI contributions / gross collections",
        "US DOL ETA-2112 and/or IRS Gross Collections",
        (
            "2112",
            "unemployment",
            "gross_collections",
        ),
        "METHOD_CHANGE_REVIEW",
        "Rockefeller allocator varies by report vintage; preserve vintage-specific treatment.",
    ),
    InputRequirement(
        "OTHER_RETIREMENT",
        "Other retirement receipts",
        "State population share",
        "US Census Bureau population estimates",
        (
            "population",
            "pep",
            "census",
        ),
        "REQUIRES_SEMANTIC_CHECK",
        "Need annual state population denominator, not geography reference files alone.",
    ),
    InputRequirement(
        "CORPORATE_CAPITAL",
        "Corporate income tax - capital component",
        "Dividends + interest + rent + proprietors' income",
        "BEA State Personal Income",
        (
            "sainc",
            "dividend",
            "interest",
            "rent",
            "proprietor",
            "personal_income",
        ),
        "REQUIRES_SEMANTIC_CHECK",
        "Rockefeller weight = 75 percent capital.",
    ),
    InputRequirement(
        "CORPORATE_LABOR",
        "Corporate income tax - labor component",
        "Wages and salaries",
        "BEA State Personal Income",
        (
            "sainc",
            "wage",
            "salary",
            "personal_income",
        ),
        "REQUIRES_SEMANTIC_CHECK",
        "Rockefeller weight = 25 percent labor; federal-wage-only BEA files are insufficient.",
    ),
    InputRequirement(
        "TRANSPORTATION_EXCISE",
        "Transportation / Highway Trust Fund excise",
        "State share of FHTF receipts attributable to highway users",
        "Federal Highway Administration",
        (
            "fhwa",
            "highway",
            "fhtf",
            "fe9",
            "fe221",
        ),
        "REQUIRES_SEMANTIC_CHECK",
        "Need state-level Highway Trust Fund receipt allocator.",
    ),
    InputRequirement(
        "ALCOHOL_EXCISE",
        "Alcohol excise",
        "State alcohol-consumption share",
        "NIAAA",
        (
            "niaaa",
            "alcohol",
            "ethanol",
            "consumption",
        ),
        "REQUIRES_SEMANTIC_CHECK",
        "Rockefeller may substitute nearest available year.",
    ),
    InputRequirement(
        "OTHER_EXCISE",
        "Other excise taxes",
        "State population share",
        "US Census Bureau population estimates",
        (
            "population",
            "pep",
            "census",
        ),
        "REQUIRES_SEMANTIC_CHECK",
        "Includes population-allocated tobacco, airport/airway and miscellaneous excises.",
    ),
    InputRequirement(
        "ESTATE_GIFT",
        "Estate and gift taxes",
        "Direct state gross collections",
        "IRS Gross Collections Table 5",
        (
            "gross_collections",
            "table5",
            "table_5",
        ),
        "CANDIDATE_PRESENT",
        "ETL-171 certified the IRS Table 5 source family for FFY2015-FFY2024.",
    ),
    InputRequirement(
        "FEDERAL_RECEIPT_CONTROLS",
        "National federal receipt controls",
        "Federal fiscal-year national receipt totals by category",
        "Budget of the United States Government / OMB Historical Tables",
        (
            "budget",
            "historical",
            "hist2",
            "table_2",
            "omb",
        ),
        "REQUIRES_SEMANTIC_CHECK",
        "Object Class Analysis files are expenditure controls and do not by themselves satisfy this requirement.",
    ),
)


SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)

    return digest.hexdigest().upper()


def iter_raw_files():
    if not RAW_ROOT.exists():
        return

    for path in RAW_ROOT.rglob("*"):
        if not path.is_file():
            continue

        if any(part.lower() in SKIP_DIR_NAMES for part in path.parts):
            continue

        yield path


def searchable_name(path: Path) -> str:
    try:
        relative = path.relative_to(REPO_ROOT)
    except ValueError:
        relative = path

    return str(relative).lower().replace("\\", "/")


def matching_terms(path: Path, requirement: InputRequirement) -> list[str]:
    name = searchable_name(path)

    return [
        term
        for term in requirement.search_terms
        if term.lower() in name
    ]


def classify_requirement(
    requirement: InputRequirement,
    matches: list[dict],
) -> tuple[str, str]:
    count = len(matches)

    if count == 0:
        return (
            "MISSING",
            "No filename/path candidates found. Acquisition likely required.",
        )

    if requirement.requirement_id in {
        "INDIVIDUAL_INCOME_TAX",
        "RAILROAD_RETIREMENT",
        "ESTATE_GIFT",
    }:
        return (
            "READY_OR_NEAR_READY",
            (
                f"{count} candidate files found and prior ETL work already "
                "supports this source family. Verify required years/fields."
            ),
        )

    if requirement.requirement_id == "UNEMPLOYMENT_INSURANCE":
        return (
            "METHOD_CHANGE_REVIEW",
            (
                f"{count} candidate files found. Vintage-specific Rockefeller "
                "allocator treatment must be resolved before use."
            ),
        )

    return (
        "SEMANTIC_REVIEW_REQUIRED",
        (
            f"{count} candidate files found, but filename/path evidence alone "
            "cannot certify that the required allocator is present."
        ),
    )


def main() -> None:
    print("=" * 92)
    print("FEDERAL RECEIPTS INPUT GAP ANALYSIS v0.1 - ETL-172D-1")
    print("=" * 92)
    print()
    print(f"Repository : {REPO_ROOT}")
    print(f"Raw root   : {RAW_ROOT}")
    print("Dollar calc: NONE")
    print("Acquisition: NONE")
    print("DB writes  : NONE")
    print()

    if not RAW_ROOT.exists():
        raise SystemExit(f"Raw-data root not found: {RAW_ROOT}")

    if OUTPUT_DIR.exists():
        existing = [
            path
            for path in OUTPUT_DIR.iterdir()
            if path.is_file()
        ]
        if existing:
            raise SystemExit(
                "Refusing silent overwrite. Output directory already contains files:\n"
                + "\n".join(f"  {path}" for path in existing)
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_files = list(iter_raw_files())

    inventory_rows: list[dict] = []
    summary_rows: list[dict] = []

    for requirement in REQUIREMENTS:
        matches: list[dict] = []

        for path in all_files:
            terms = matching_terms(path, requirement)

            if not terms:
                continue

            stat = path.stat()

            try:
                relative = path.relative_to(REPO_ROOT)
            except ValueError:
                relative = path

            row = {
                "requirement_id": requirement.requirement_id,
                "receipt_category": requirement.receipt_category,
                "expected_source": requirement.expected_source,
                "allocator": requirement.allocator,
                "matched_terms": ";".join(terms),
                "relative_path": str(relative),
                "suffix": path.suffix.lower(),
                "bytes": stat.st_size,
                "modified_utc": datetime.fromtimestamp(
                    stat.st_mtime,
                    tz=timezone.utc,
                ).isoformat(),
                "sha256": sha256_file(path),
            }

            matches.append(row)
            inventory_rows.append(row)

        status, assessment = classify_requirement(
            requirement,
            matches,
        )

        summary_rows.append(
            {
                "requirement_id": requirement.requirement_id,
                "receipt_category": requirement.receipt_category,
                "expected_source": requirement.expected_source,
                "allocator": requirement.allocator,
                "candidate_file_count": len(matches),
                "inventory_status": status,
                "prior_expectation": requirement.preliminary_status,
                "assessment": assessment,
                "notes": requirement.notes,
            }
        )

    inventory_fields = [
        "requirement_id",
        "receipt_category",
        "expected_source",
        "allocator",
        "matched_terms",
        "relative_path",
        "suffix",
        "bytes",
        "modified_utc",
        "sha256",
    ]

    with INVENTORY_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=inventory_fields,
        )
        writer.writeheader()
        writer.writerows(inventory_rows)

    summary_fields = [
        "requirement_id",
        "receipt_category",
        "expected_source",
        "allocator",
        "candidate_file_count",
        "inventory_status",
        "prior_expectation",
        "assessment",
        "notes",
    ]

    with SUMMARY_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=summary_fields,
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    report_lines = [
        "=" * 92,
        "FEDERAL RECEIPTS INPUT GAP ANALYSIS v0.1 - ETL-172D-1",
        "=" * 92,
        "",
        f"Generated UTC : {utc_now()}",
        f"Repository    : {REPO_ROOT}",
        f"Files scanned : {len(all_files):,}",
        f"Requirements  : {len(REQUIREMENTS)}",
        "",
        "IMPORTANT",
        "-" * 92,
        "This is a repository inventory and gap-screening step only.",
        "Filename/path matches do NOT certify source semantics.",
        "No files were acquired.",
        "No receipt values were calculated.",
        "No database writes were performed.",
        "",
        "REQUIREMENT SUMMARY",
        "-" * 92,
    ]

    for row in summary_rows:
        report_lines.extend(
            [
                f"{row['requirement_id']}",
                f"  category   : {row['receipt_category']}",
                f"  source     : {row['expected_source']}",
                f"  allocator  : {row['allocator']}",
                f"  candidates : {row['candidate_file_count']}",
                f"  status     : {row['inventory_status']}",
                f"  assessment : {row['assessment']}",
                "",
            ]
        )

    missing = [
        row
        for row in summary_rows
        if row["inventory_status"] == "MISSING"
    ]

    semantic = [
        row
        for row in summary_rows
        if row["inventory_status"] == "SEMANTIC_REVIEW_REQUIRED"
    ]

    ready = [
        row
        for row in summary_rows
        if row["inventory_status"] == "READY_OR_NEAR_READY"
    ]

    method_change = [
        row
        for row in summary_rows
        if row["inventory_status"] == "METHOD_CHANGE_REVIEW"
    ]

    report_lines.extend(
        [
            "=" * 92,
            "SCREENING COUNTS",
            "=" * 92,
            "",
            f"READY_OR_NEAR_READY      : {len(ready)}",
            f"SEMANTIC_REVIEW_REQUIRED : {len(semantic)}",
            f"METHOD_CHANGE_REVIEW     : {len(method_change)}",
            f"MISSING                  : {len(missing)}",
            "",
        ]
    )

    if missing:
        report_lines.extend(
            [
                "APPARENT ACQUISITION GAPS",
                "-" * 92,
            ]
        )

        for row in missing:
            report_lines.append(
                f"{row['requirement_id']}: "
                f"{row['expected_source']}"
            )

        report_lines.append("")

    report_lines.extend(
        [
            "OUTPUTS",
            "-" * 92,
            str(INVENTORY_CSV.relative_to(REPO_ROOT)),
            str(SUMMARY_CSV.relative_to(REPO_ROOT)),
            str(REPORT_TXT.relative_to(REPO_ROOT)),
            "",
            "SCREENING RESULT: COMPLETE",
            "",
            "COMPLETE means the repository was screened against the",
            "ETL-172C Rockefeller receipts allocator requirements.",
            "It does not certify that candidate files contain the required",
            "variables, years, geographies, units, or accounting periods.",
        ]
    )

    REPORT_TXT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print("\n".join(report_lines))


if __name__ == "__main__":
    main()