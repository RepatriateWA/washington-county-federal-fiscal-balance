#!/usr/bin/env python3
"""
Extract CMS MSSP beneficiary-geography incidence methodology evidence v0.1.

Purpose
-------
Read-only evidence gate. This script examines the already-preserved CMS
"Number of Accountable Care Organization Assigned Beneficiaries by County"
documentation and extracts evidence relevant to ONE question:

    Does CMS methodology support assigned-beneficiary county/person-year
    geography as an economic geographic-incidence basis for MSSP settlement
    dollars (e.g., positive EarnSaveLoss)?

This is an evidence extractor, NOT an incidence decision and NOT an allocation
engine.

It does NOT:
  * allocate EarnSaveLoss or any dollars;
  * treat ACO headquarters or participant addresses as beneficiary incidence;
  * reconstruct or impute CMS-suppressed cells;
  * infer that a CMS benchmark weighting method is automatically a payment-
    dollar allocation method;
  * write to a database or principal ledger.

PASS means the authenticated documentation was parsed and the targeted evidence
search completed. PASS does not mean an incidence methodology was established.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    print("ERROR: pypdf is required. Install with: pip install pypdf")
    raise

ROOT = Path(__file__).resolve().parents[1]

SOURCE_ZIP = ROOT / (
    "data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county/"
    "Number of Accountable Care Organization Assigned Beneficiaries by County.zip"
)
OUTDIR = ROOT / (
    "data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county/"
    "validation/incidence_methodology_v0_1"
)

EXPECTED_SHA256 = (
    "2BDD88C3B00B3035914426286BE38E518FA6E552D54285B19289EB964878F942"
)
EXPECTED_BYTES = 8_450_964
EXPECTED_PDF_MEMBERS = 10
PERIODS = ("2020", "2021", "2022", "2023", "2024")

# Search terms are intentionally broader than the eventual decision rule.
# Absence is descriptive only.
SEARCH_GROUPS = {
    "county_residence_geography": [
        "county of residence",
        "county",
        "counties",
        "residence",
        "resident",
        "service area",
        "regional service area",
    ],
    "assigned_beneficiary_measure": [
        "assigned beneficiary",
        "assigned beneficiaries",
        "person-year",
        "person year",
        "person-years",
        "person years",
        "Tot_AB_Psn_Yrs",
        "Tot_AB",
    ],
    "benchmark_weighting": [
        "benchmark",
        "regional benchmark",
        "regional adjustment",
        "regional expenditures",
        "weighted",
        "weighting",
        "weighted average",
        "person-year weighted",
        "person year weighted",
    ],
    "ffs_expenditure_basis": [
        "fee-for-service",
        "FFS",
        "expenditure",
        "expenditures",
        "Parts A and B",
        "Parts A/B",
        "Medicare Parts A and B",
        "per capita",
    ],
    "settlement_payment_link": [
        "shared savings",
        "shared losses",
        "performance payment",
        "EarnSaveLoss",
        "settlement",
        "financial reconciliation",
        "payment",
        "payments",
    ],
    "allocation_incidence_language": [
        "allocate",
        "allocated",
        "allocation",
        "apportion",
        "apportioned",
        "attributable",
        "attributed",
        "incidence",
        "distributed",
        "distribution",
    ],
    "suppression_boundary": [
        "suppressed",
        "suppression",
        "privacy",
        "HIPAA",
    ],
}

CONTEXT_LINES = 5
MAX_WINDOWS_PER_TERM_PER_DOC = 30


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def period_from_member(name: str) -> str | None:
    m = re.search(r"/(20(?:20|21|22|23|24))/", name)
    return m.group(1) if m else None


def doc_type(name: str) -> str:
    low = name.lower()
    if "methodology" in low:
        return "METHODOLOGY"
    if "dictionary" in low:
        return "DATA_DICTIONARY"
    return "OTHER_PDF"


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract_pdf_text(data: bytes) -> tuple[str, int, list[str]]:
    reader = PdfReader(io.BytesIO(data))
    pages = []
    errors = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            pages.append(normalize_text(page.extract_text() or ""))
        except Exception as exc:
            pages.append("")
            errors.append(f"page {i}: {type(exc).__name__}: {exc}")
    return "\n".join(pages), len(reader.pages), errors


def flexible_pattern(term: str) -> re.Pattern:
    escaped = re.escape(term)
    escaped = escaped.replace(r"\ ", r"[\s\-/]+")
    return re.compile(escaped, re.IGNORECASE)


def windows_for_term(
    text: str,
    *,
    group: str,
    term: str,
    sha: str,
    representative_member: str,
    dtype: str,
) -> list[dict]:
    lines = text.splitlines()
    pat = flexible_pattern(term)
    rows = []
    for idx, line in enumerate(lines):
        if not pat.search(line):
            continue
        start = max(0, idx - CONTEXT_LINES)
        end = min(len(lines), idx + CONTEXT_LINES + 1)
        rows.append({
            "document_sha256": sha,
            "document_type": dtype,
            "representative_member": representative_member,
            "search_group": group,
            "search_term": term,
            "matched_line_number": idx + 1,
            "window_start_line": start + 1,
            "window_end_line": end,
            "evidence_window": "\n".join(lines[start:end]),
        })
        if len(rows) >= MAX_WINDOWS_PER_TERM_PER_DOC:
            break
    return rows


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []

    def check(cid: str, passed: bool, detail: str) -> None:
        checks.append({
            "check_id": cid,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
        })

    print("CMS MSSP BENEFICIARY-GEOGRAPHY INCIDENCE METHODOLOGY EVIDENCE v0.1")
    print("=" * 80)

    if not SOURCE_ZIP.exists():
        print(f"ERROR: source archive not found: {SOURCE_ZIP}")
        return 2

    source_sha = sha256_file(SOURCE_ZIP)
    source_bytes = SOURCE_ZIP.stat().st_size

    print(f"Source: {SOURCE_ZIP}")
    print(f"SHA-256: {source_sha}")
    print(f"Bytes: {source_bytes:,}")

    check("SOURCE-01", source_sha == EXPECTED_SHA256,
          f"archive SHA-256={source_sha}")
    check("SOURCE-02", source_bytes == EXPECTED_BYTES,
          f"archive bytes={source_bytes:,} expected={EXPECTED_BYTES:,}")

    member_rows = []
    unique_docs: dict[str, dict] = {}

    with zipfile.ZipFile(SOURCE_ZIP) as z:
        pdf_names = [n for n in z.namelist() if n.lower().endswith(".pdf")]
        check("DOC-01", len(pdf_names) == EXPECTED_PDF_MEMBERS,
              f"PDF members={len(pdf_names)} expected={EXPECTED_PDF_MEMBERS}")

        period_type_counts = defaultdict(int)

        for name in pdf_names:
            raw = z.read(name)
            digest = sha256_bytes(raw)
            period = period_from_member(name) or "UNKNOWN"
            dtype = doc_type(name)
            period_type_counts[(period, dtype)] += 1

            member_rows.append({
                "period": period,
                "document_type": dtype,
                "member_name": name,
                "bytes": len(raw),
                "sha256": digest,
            })

            if digest not in unique_docs:
                unique_docs[digest] = {
                    "sha256": digest,
                    "bytes": len(raw),
                    "members": [],
                    "periods": set(),
                    "types": set(),
                    "data": raw,
                }
            unique_docs[digest]["members"].append(name)
            unique_docs[digest]["periods"].add(period)
            unique_docs[digest]["types"].add(dtype)

    check(
        "DOC-02",
        all(
            period_type_counts[(p, "METHODOLOGY")] == 1
            and period_type_counts[(p, "DATA_DICTIONARY")] == 1
            for p in PERIODS
        ),
        "one methodology and one data dictionary present for every 2020-2024 period",
    )

    print(f"PDF members: {len(member_rows)}")
    print(f"Unique PDF byte streams: {len(unique_docs)}")

    unique_rows = []
    evidence_rows = []
    parse_errors = 0

    for digest, doc in sorted(unique_docs.items()):
        representative = sorted(doc["members"])[0]
        dtype = "|".join(sorted(doc["types"]))
        text, pages, errors = extract_pdf_text(doc["data"])
        parse_errors += len(errors)

        unique_rows.append({
            "sha256": digest,
            "bytes": doc["bytes"],
            "pages": pages,
            "member_count": len(doc["members"]),
            "periods": "|".join(sorted(doc["periods"])),
            "document_types": dtype,
            "representative_member": representative,
            "all_members": "|".join(sorted(doc["members"])),
            "text_characters": len(text),
            "parse_error_count": len(errors),
            "parse_errors": "|".join(errors),
        })

        print(
            f"{digest[:12]}... type={dtype} pages={pages} "
            f"members={len(doc['members'])} "
            f"periods={','.join(sorted(doc['periods']))} "
            f"chars={len(text):,} errors={len(errors)}"
        )

        for group, terms in SEARCH_GROUPS.items():
            for term in terms:
                evidence_rows.extend(
                    windows_for_term(
                        text,
                        group=group,
                        term=term,
                        sha=digest,
                        representative_member=representative,
                        dtype=dtype,
                    )
                )

    check("PARSE-01", parse_errors == 0,
          f"PDF page parse errors={parse_errors}")
    check(
        "PARSE-02",
        all(r["text_characters"] > 0 for r in unique_rows),
        "all unique PDFs yielded nonempty extracted text",
    )

    hit_counts = defaultdict(int)
    doc_hit_counts = defaultdict(set)

    for row in evidence_rows:
        key = (row["search_group"], row["search_term"])
        hit_counts[key] += 1
        doc_hit_counts[key].add(row["document_sha256"])

    search_rows = []
    for group, terms in SEARCH_GROUPS.items():
        for term in terms:
            count = hit_counts[(group, term)]
            search_rows.append({
                "search_group": group,
                "search_term": term,
                "status": "FOUND" if count else "NOT_FOUND_IN_EXTRACTED_TEXT",
                "evidence_windows": count,
                "documents_with_hits": len(doc_hit_counts[(group, term)]),
            })

    expected_searches = sum(len(v) for v in SEARCH_GROUPS.values())
    check("SEARCH-01", len(search_rows) == expected_searches,
          f"targeted search terms accounted={len(search_rows)}")

    # These are extraction-accounting tests only. They do not certify incidence.
    methodology_shas = {
        r["sha256"]
        for r in unique_rows
        if "METHODOLOGY" in r["document_types"]
    }
    methodology_evidence = [
        r for r in evidence_rows
        if r["document_sha256"] in methodology_shas
    ]
    methodology_groups = {r["search_group"] for r in methodology_evidence}

    check(
        "EVIDENCE-01",
        "county_residence_geography" in methodology_groups,
        "methodology produced county/geography evidence",
    )
    check(
        "EVIDENCE-02",
        "assigned_beneficiary_measure" in methodology_groups,
        "methodology produced assigned-beneficiary/person-year evidence",
    )
    check(
        "EVIDENCE-03",
        "benchmark_weighting" in methodology_groups,
        "methodology produced benchmark/weighting evidence",
    )
    check(
        "EVIDENCE-04",
        "ffs_expenditure_basis" in methodology_groups,
        "methodology produced FFS/expenditure evidence",
    )

    # Deliberately do NOT require settlement/payment linkage to be found.
    # Its absence may itself be the central result, but absence is not proof.
    settlement_hits = sum(
        r["evidence_windows"]
        for r in search_rows
        if r["search_group"] == "settlement_payment_link"
    )
    allocation_hits = sum(
        r["evidence_windows"]
        for r in search_rows
        if r["search_group"] == "allocation_incidence_language"
    )

    write_csv(
        OUTDIR / "cms_mssp_incidence_methodology_document_members_v0_1.csv",
        member_rows,
        ["period", "document_type", "member_name", "bytes", "sha256"],
    )
    write_csv(
        OUTDIR / "cms_mssp_incidence_methodology_unique_documents_v0_1.csv",
        unique_rows,
        [
            "sha256", "bytes", "pages", "member_count", "periods",
            "document_types", "representative_member", "all_members",
            "text_characters", "parse_error_count", "parse_errors",
        ],
    )
    write_csv(
        OUTDIR / "cms_mssp_incidence_methodology_search_accounting_v0_1.csv",
        search_rows,
        [
            "search_group", "search_term", "status",
            "evidence_windows", "documents_with_hits",
        ],
    )
    write_csv(
        OUTDIR / "cms_mssp_incidence_methodology_evidence_v0_1.csv",
        evidence_rows,
        [
            "document_sha256", "document_type", "representative_member",
            "search_group", "search_term", "matched_line_number",
            "window_start_line", "window_end_line", "evidence_window",
        ],
    )
    write_csv(
        OUTDIR / "cms_mssp_incidence_methodology_checks_v0_1.csv",
        checks,
        ["check_id", "status", "detail"],
    )

    disposition = [{
        "dimension": "beneficiary_geography_as_payment_incidence",
        "status": "NOT_DECIDED_BY_EXTRACTOR",
        "note": (
            "Requires substantive review of extracted CMS evidence. "
            "Benchmark weighting is not presumed to equal settlement-dollar incidence."
        ),
    }, {
        "dimension": "suppressed_geography",
        "status": "CMS_SUPPRESSED_UNRESOLVED",
        "note": "No suppressed values reconstructed or imputed.",
    }, {
        "dimension": "washington_payment_dollar_incidence",
        "status": "UNRESOLVED",
        "note": "No dollars allocated.",
    }, {
        "dimension": "county_payment_dollar_incidence",
        "status": "UNRESOLVED",
        "note": "No dollars allocated.",
    }, {
        "dimension": "principal_ledger",
        "status": "WITHHOLD_UNRESOLVED",
        "note": "No ledger inclusion authorized.",
    }]

    write_csv(
        OUTDIR / "cms_mssp_incidence_methodology_disposition_v0_1.csv",
        disposition,
        ["dimension", "status", "note"],
    )

    overall = all(c["status"] == "PASS" for c in checks)

    report = [
        "CMS MSSP BENEFICIARY-GEOGRAPHY INCIDENCE METHODOLOGY EVIDENCE v0.1",
        "=" * 80,
        "",
        "QUESTION",
        "Does CMS methodology support assigned-beneficiary county/person-year",
        "geography as an economic geographic-incidence basis for MSSP settlement",
        "dollars such as positive EarnSaveLoss?",
        "",
        "BOUNDARY",
        "Evidence extraction only. PASS means the preserved documentation was",
        "authenticated, parsed, and searched successfully. PASS does NOT answer",
        "the incidence question.",
        "",
        "NO-ASSUMPTION RULE",
        "A CMS method that uses county/person-year weighting for regional benchmark",
        "or expenditure calculations is not automatically treated as a rule for",
        "allocating an ACO's settlement payment geographically.",
        "",
        "NO-SUPPRESSION-RECONSTRUCTION RULE",
        "CMS '*' values remain unresolved. No protected cell is zeroed, bounded,",
        "reconstructed, or imputed.",
        "",
        f"Source archive: {SOURCE_ZIP}",
        f"SHA-256: {source_sha}",
        f"Bytes: {source_bytes:,}",
        f"PDF members: {len(member_rows)}",
        f"Unique PDF byte streams: {len(unique_docs)}",
        f"Evidence windows: {len(evidence_rows)}",
        f"Settlement/payment search windows: {settlement_hits}",
        f"Allocation/incidence search windows: {allocation_hits}",
        "",
        "SEARCH ACCOUNTING",
    ]

    for row in search_rows:
        report.append(
            f"{row['search_group']} | {row['search_term']} | "
            f"{row['status']} | windows={row['evidence_windows']} | "
            f"documents={row['documents_with_hits']}"
        )

    report.extend(["", "CHECKS"])
    report.extend(
        f"{c['check_id']}: {c['status']} - {c['detail']}" for c in checks
    )
    report.extend([
        "",
        "INTERPRETIVE RULE",
        "NOT_FOUND_IN_EXTRACTED_TEXT is descriptive only and is not evidence that",
        "a rule, mechanism, or relationship does not exist.",
        "",
        "DISPOSITION",
        "beneficiary_geography_as_payment_incidence = NOT_DECIDED_BY_EXTRACTOR",
        "washington_payment_dollar_incidence = UNRESOLVED",
        "county_payment_dollar_incidence = UNRESOLVED",
        "principal_ledger = WITHHOLD_UNRESOLVED",
        "",
        "OVERALL INCIDENCE METHODOLOGY EVIDENCE v0.1: "
        + ("PASS" if overall else "FAIL"),
    ])

    (
        OUTDIR / "cms_mssp_incidence_methodology_report_v0_1.txt"
    ).write_text("\n".join(report) + "\n", encoding="utf-8")

    print()
    for row in search_rows:
        print(
            f"{row['search_group']}/{row['search_term']}: "
            f"{row['status']} windows={row['evidence_windows']} "
            f"documents={row['documents_with_hits']}"
        )

    print()
    for c in checks:
        print(f"{c['check_id']}: {c['status']} - {c['detail']}")

    print()
    print(
        "OVERALL INCIDENCE METHODOLOGY EVIDENCE v0.1: "
        + ("PASS" if overall else "FAIL")
    )
    print(f"Evidence windows: {len(evidence_rows):,}")
    print(f"Evidence: {OUTDIR}")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
