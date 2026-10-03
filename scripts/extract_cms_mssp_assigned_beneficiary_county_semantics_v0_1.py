#!/usr/bin/env python3
"""
Extract CMS MSSP Assigned Beneficiaries by County documentation semantics v0.1.

Boundary
--------
Read-only with respect to source data and databases. This script:
  * authenticates the already-preserved county-PUF archive;
  * inventories and SHA-256 deduplicates its 10 PDF documentation members;
  * extracts text from unique PDFs with pypdf;
  * captures compact evidence windows for:
      - six beneficiary/person-year fields,
      - suppression / blank / missing semantics,
      - rounding,
      - county / residence geography,
      - beneficiary / person-year terminology;
  * writes evidence and a compact report.

PASS means the source was authenticated, documentation was parsed, and the
targeted evidence search completed. PASS does NOT mean any particular
suppression rule, geographic-incidence rule, reconstruction method, or
allocation rule was established.

No allocations, settlement-dollar calculations, database writes, or ledger
writes are performed.
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
    "validation/semantics_v0_1"
)

EXPECTED_SHA256 = (
    "2BDD88C3B00B3035914426286BE38E518FA6E552D54285B19289EB964878F942"
)
EXPECTED_BYTES = 8_450_964
EXPECTED_PDF_MEMBERS = 10
ACQUIRED_PERIODS = ("2020", "2021", "2022", "2023", "2024")

FIELD_TERMS = (
    "AB_Psn_Yrs_ESRD",
    "AB_Psn_Yrs_DIS",
    "AB_Psn_Yrs_AGDU",
    "AB_Psn_Yrs_AGND",
    "Tot_AB_Psn_Yrs",
    "Tot_AB",
)

SEARCH_GROUPS = {
    "field_definition": list(FIELD_TERMS),
    "suppression": [
        "suppress", "suppression", "suppressed",
        "cell size", "minimum cell", "privacy",
    ],
    "blank_missing": [
        "blank", "missing", "null", "not available",
        "not applicable", "n/a",
    ],
    "rounding": [
        "round", "rounded", "rounding",
    ],
    "geography": [
        "county", "counties", "residence", "resident",
        "geographic", "geography", "state",
    ],
    "beneficiary_person_year": [
        "beneficiary", "beneficiaries", "person-year", "person year",
        "person-years", "person years", "assigned beneficiary",
    ],
}

# Evidence windows are deliberately compact and line-oriented.
CONTEXT_LINES = 3
MAX_WINDOWS_PER_TERM_PER_DOCUMENT = 20


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


def normalize_text(text: str) -> str:
    # Preserve line structure while making extracted PDF text easier to search.
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
    page_texts = []
    errors = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            page_texts.append(normalize_text(page.extract_text() or ""))
        except Exception as exc:  # evidence-preserving: report parse failures
            page_texts.append("")
            errors.append(f"page {i}: {type(exc).__name__}: {exc}")
    return "\n".join(page_texts), len(reader.pages), errors


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def term_pattern(term: str) -> re.Pattern:
    # Field names require literal matching; prose terms use flexible whitespace
    # around hyphens/spaces but otherwise remain literal.
    if term in FIELD_TERMS:
        return re.compile(re.escape(term), re.IGNORECASE)
    escaped = re.escape(term)
    escaped = escaped.replace(r"\ ", r"[\s\-]+")
    return re.compile(escaped, re.IGNORECASE)


def evidence_windows(
    text: str,
    *,
    group: str,
    term: str,
    doc_sha: str,
    representative_member: str,
) -> list[dict]:
    lines = text.splitlines()
    pat = term_pattern(term)
    hits = []
    for idx, line in enumerate(lines):
        if not pat.search(line):
            continue
        start = max(0, idx - CONTEXT_LINES)
        end = min(len(lines), idx + CONTEXT_LINES + 1)
        window = "\n".join(lines[start:end])
        hits.append({
            "document_sha256": doc_sha,
            "representative_member": representative_member,
            "search_group": group,
            "search_term": term,
            "matched_line_number": idx + 1,
            "window_start_line": start + 1,
            "window_end_line": end,
            "evidence_window": window,
        })
        if len(hits) >= MAX_WINDOWS_PER_TERM_PER_DOCUMENT:
            break
    return hits


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []

    def check(cid: str, passed: bool, detail: str) -> None:
        checks.append({
            "check_id": cid,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
        })

    print("CMS MSSP ASSIGNED BENEFICIARY COUNTY SEMANTICS EXTRACTOR v0.1")
    print("=" * 72)

    if not SOURCE_ZIP.exists():
        print(f"ERROR: source archive not found: {SOURCE_ZIP}")
        return 2

    source_hash = sha256_file(SOURCE_ZIP)
    source_bytes = SOURCE_ZIP.stat().st_size

    print(f"Source: {SOURCE_ZIP}")
    print(f"SHA-256: {source_hash}")
    print(f"Bytes: {source_bytes:,}")

    check("SOURCE-01", source_hash == EXPECTED_SHA256,
          f"archive SHA-256={source_hash}")
    check("SOURCE-02", source_bytes == EXPECTED_BYTES,
          f"archive bytes={source_bytes:,} expected={EXPECTED_BYTES:,}")

    member_rows: list[dict] = []
    unique_docs: dict[str, dict] = {}

    with zipfile.ZipFile(SOURCE_ZIP) as z:
        pdf_names = [n for n in z.namelist() if n.lower().endswith(".pdf")]
        check("DOC-01", len(pdf_names) == EXPECTED_PDF_MEMBERS,
              f"PDF members={len(pdf_names)} expected={EXPECTED_PDF_MEMBERS}")

        periods_with_two = defaultdict(int)
        for name in pdf_names:
            data = z.read(name)
            digest = sha256_bytes(data)
            period = period_from_member(name) or "UNKNOWN"
            periods_with_two[period] += 1

            member_rows.append({
                "period": period,
                "member_name": name,
                "bytes": len(data),
                "sha256": digest,
            })

            if digest not in unique_docs:
                unique_docs[digest] = {
                    "sha256": digest,
                    "bytes": len(data),
                    "members": [],
                    "periods": set(),
                    "data": data,
                }
            unique_docs[digest]["members"].append(name)
            unique_docs[digest]["periods"].add(period)

    check(
        "DOC-02",
        all(periods_with_two[p] == 2 for p in ACQUIRED_PERIODS),
        "PDF members by period=" +
        ",".join(f"{p}:{periods_with_two[p]}" for p in ACQUIRED_PERIODS),
    )
    check("DOC-03", len(unique_docs) >= 2,
          f"unique PDF byte streams={len(unique_docs)}")

    print(f"PDF members: {len(member_rows)}")
    print(f"Unique PDF byte streams: {len(unique_docs)}")

    unique_rows: list[dict] = []
    evidence_rows: list[dict] = []
    parse_error_count = 0

    for digest, doc in sorted(unique_docs.items()):
        representative = sorted(doc["members"])[0]
        text, pages, errors = extract_pdf_text(doc["data"])
        parse_error_count += len(errors)

        unique_rows.append({
            "sha256": digest,
            "bytes": doc["bytes"],
            "pages": pages,
            "member_count": len(doc["members"]),
            "periods": "|".join(sorted(doc["periods"])),
            "representative_member": representative,
            "all_members": "|".join(sorted(doc["members"])),
            "text_characters": len(text),
            "parse_error_count": len(errors),
            "parse_errors": "|".join(errors),
        })

        print(
            f"{digest[:12]}... pages={pages} members={len(doc['members'])} "
            f"periods={','.join(sorted(doc['periods']))} chars={len(text):,} "
            f"errors={len(errors)}"
        )

        for group, terms in SEARCH_GROUPS.items():
            for term in terms:
                evidence_rows.extend(
                    evidence_windows(
                        text,
                        group=group,
                        term=term,
                        doc_sha=digest,
                        representative_member=representative,
                    )
                )

    check("PARSE-01", parse_error_count == 0,
          f"PDF page parse errors={parse_error_count}")
    check("PARSE-02",
          all(r["text_characters"] > 0 for r in unique_rows),
          "all unique PDFs yielded nonempty text")

    # Search accounting: absence is explicitly descriptive, not a semantic
    # conclusion. PASS means the targeted search ran against all parsed docs.
    hit_counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in evidence_rows:
        hit_counts[(row["search_group"], row["search_term"])] += 1

    search_rows = []
    for group, terms in SEARCH_GROUPS.items():
        for term in terms:
            search_rows.append({
                "search_group": group,
                "search_term": term,
                "evidence_windows": hit_counts[(group, term)],
                "status": (
                    "FOUND"
                    if hit_counts[(group, term)] > 0
                    else "NOT_FOUND_IN_EXTRACTED_TEXT"
                ),
            })

    check("SEARCH-01",
          len(search_rows) == sum(len(v) for v in SEARCH_GROUPS.values()),
          f"targeted search terms accounted={len(search_rows)}")
    check("SEARCH-02",
          all(
              any(
                  r["search_group"] == "field_definition"
                  and r["search_term"] == field
                  for r in search_rows
              )
              for field in FIELD_TERMS
          ),
          "all six target fields included in search universe")

    # We do NOT require every term to be found. That would convert absence into
    # a false failure. We do report the field-definition coverage separately.
    fields_found = {
        r["search_term"]
        for r in search_rows
        if r["search_group"] == "field_definition"
        and r["status"] == "FOUND"
    }
    check("FIELD-01",
          len(fields_found) > 0,
          "target field names found in extracted documentation="
          + ",".join(sorted(fields_found)) if fields_found else
          "no target field names found in extracted documentation")

    # Write evidence.
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_document_members_v0_1.csv",
        member_rows,
        ["period", "member_name", "bytes", "sha256"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_unique_documents_v0_1.csv",
        unique_rows,
        [
            "sha256", "bytes", "pages", "member_count", "periods",
            "representative_member", "all_members", "text_characters",
            "parse_error_count", "parse_errors",
        ],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_search_accounting_v0_1.csv",
        search_rows,
        ["search_group", "search_term", "evidence_windows", "status"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_semantic_evidence_v0_1.csv",
        evidence_rows,
        [
            "document_sha256", "representative_member", "search_group",
            "search_term", "matched_line_number", "window_start_line",
            "window_end_line", "evidence_window",
        ],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_semantics_checks_v0_1.csv",
        checks,
        ["check_id", "status", "detail"],
    )

    overall = all(c["status"] == "PASS" for c in checks)

    report = [
        "CMS MSSP ASSIGNED BENEFICIARY COUNTY SEMANTICS EXTRACTOR v0.1",
        "=" * 72,
        "",
        "BOUNDARY",
        "Evidence extraction only. PASS means the preserved source was authenticated,",
        "the documentation corpus was inventoried/deduplicated/parsed, and the targeted",
        "semantic search completed.",
        "",
        "PASS DOES NOT ESTABLISH:",
        "- the meaning of an undocumented blank or nonnumeric value",
        "- a suppression threshold",
        "- that suppressed values are zero",
        "- that suppressed geography may be reconstructed or imputed",
        "- beneficiary-residence weighting as payment-dollar incidence",
        "- Washington or county payment-dollar incidence",
        "- cash / federal fiscal-year timing",
        "- principal-ledger inclusion",
        "",
        f"Source archive: {SOURCE_ZIP}",
        f"Source SHA-256: {source_hash}",
        f"Source bytes: {source_bytes:,}",
        f"PDF members: {len(member_rows)}",
        f"Unique PDF byte streams: {len(unique_docs)}",
        f"Evidence windows: {len(evidence_rows)}",
        "",
        "SEARCH ACCOUNTING",
    ]
    for row in search_rows:
        report.append(
            f"{row['search_group']} | {row['search_term']} | "
            f"{row['status']} | windows={row['evidence_windows']}"
        )

    report.extend(["", "CHECKS"])
    report.extend(
        f"{c['check_id']}: {c['status']} - {c['detail']}" for c in checks
    )
    report.extend([
        "",
        "INTERPRETIVE RULE",
        "NOT_FOUND_IN_EXTRACTED_TEXT is descriptive only. It is not evidence that a",
        "concept, rule, threshold, or mechanism does not exist.",
        "",
        "OVERALL SEMANTICS EXTRACTOR v0.1: " + ("PASS" if overall else "FAIL"),
    ])

    (OUTDIR / "cms_mssp_assigned_beneficiary_county_semantics_report_v0_1.txt").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )

    print()
    for row in search_rows:
        print(
            f"{row['search_group']}/{row['search_term']}: "
            f"{row['status']} windows={row['evidence_windows']}"
        )

    print()
    for c in checks:
        print(f"{c['check_id']}: {c['status']} - {c['detail']}")

    print()
    print(
        "OVERALL SEMANTICS EXTRACTOR v0.1: "
        + ("PASS" if overall else "FAIL")
    )
    print(f"Evidence windows: {len(evidence_rows):,}")
    print(f"Evidence: {OUTDIR}")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
