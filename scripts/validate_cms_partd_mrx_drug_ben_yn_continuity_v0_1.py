#!/usr/bin/env python3
"""
validate_cms_partd_mrx_drug_ben_yn_continuity_v0_1.py

CMS Medicare Part D — mrx_drug_ben_yn Semantic Continuity Certification v0.1
CY2015–CY2025

PURPOSE
-------
Establish, independently of the disputed Contract+PBP population, whether the
CMS PBP Benefits field `mrx_drug_ben_yn` is semantically and structurally
continuous from CY2015 through CY2025.

CY2025 is the documentary semantic anchor. The CMS 2025 PBP Benefits dictionary
must explicitly define:
    mrx_drug_ben_yn
    "Does your plan offer a Medicare Prescription drug (Part D) benefit?"
    1 = Yes
    2 = No

For CY2015–CY2025 this validator independently checks:
  * pbp_mrx source presence
  * exact field presence
  * SAS label continuity where available
  * observed source-value vocabulary and counts
  * absence of undocumented nonblank values

It does NOT:
  * read the disputed 240 Contract+PBP relationships
  * classify any Contract+PBP
  * propagate status from sibling PBPs or other years
  * propagate payments
  * impute values
  * reconstruct payments
  * write to PostgreSQL
  * authorize ledger inclusion

Run from repository root:
    python scripts/validate_cms_partd_mrx_drug_ben_yn_continuity_v0_1.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
PBP_ROOT = REPO_ROOT / "data" / "raw" / "cms" / "medicare_partd" / "pbp_benefits"
OUTPUT_DIR = (
    PBP_ROOT
    / "validation"
    / "mrx_drug_ben_yn_continuity_v0_1"
)

YEARS = tuple(range(2015, 2026))
FIELD = "mrx_drug_ben_yn"
EXPECTED_SAS_LABEL = "MRx Drug Benefit YN"
EXPECTED_CODES = {"1", "2"}
ANCHOR_YEAR = 2025
ANCHOR_QUESTION_FRAGMENT = "does your plan offer a medicare prescription drug"
ANCHOR_PARTD_FRAGMENT = "part d"
EXPECTED_ANCHOR_MAP = {"1": "yes", "2": "no"}

# Known user-supplied CY2025 documentary anchor. If copied into the repository,
# this exact hash is preferred and verified.
EXPECTED_2025_ZIP_SHA256 = (
    "7ca2d3bb30b01ba7e8143c6eea38e1dc5434ff782f5742ab6c640e9b45f6b2d3"
)

MANIFEST_NAME_HINTS = (
    "cms_pbp_benefits_acquisition_manifest.csv",
    "acquisition_manifest.csv",
)

EXCLUDED_PATH_TOKENS = {
    "validation",
    "__pycache__",
}

@dataclass
class YearResult:
    year: int
    zip_path: str = ""
    zip_sha256: str = ""
    pbp_mrx_member: str = ""
    sas_member: str = ""
    field_present: bool = False
    sas_label_found: bool = False
    total_records: int = 0
    code_1_count: int = 0
    code_2_count: int = 0
    blank_count: int = 0
    other_count: int = 0
    other_values: str = ""
    observed_nonblank_values: str = ""
    status: str = "FAIL"
    notes: str = ""

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip())

def norm_lower(s: object) -> str:
    return norm(s).lower()

def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1", errors="replace")

def infer_year_from_text(text: str) -> Optional[int]:
    years = {int(x) for x in re.findall(r"(?<!\d)(20(?:1[5-9]|2[0-5]))(?!\d)", text)}
    return next(iter(years)) if len(years) == 1 else None

def excluded(path: Path) -> bool:
    lower_parts = {p.lower() for p in path.parts}
    return bool(lower_parts & EXCLUDED_PATH_TOKENS)

def load_manifest_candidates() -> dict[int, Path]:
    """Use acquisition manifest paths when they can be resolved safely."""
    found: dict[int, Path] = {}
    manifests = []
    for hint in MANIFEST_NAME_HINTS:
        manifests.extend(PBP_ROOT.rglob(hint))
    for manifest in manifests:
        if excluded(manifest):
            continue
        try:
            with manifest.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
        except Exception:
            continue
        for row in rows:
            year = None
            for key, val in row.items():
                if "year" in norm_lower(key):
                    try:
                        y = int(str(val).strip())
                        if y in YEARS:
                            year = y
                            break
                    except Exception:
                        pass
            if year is None:
                continue
            for key, val in row.items():
                k = norm_lower(key)
                if not any(t in k for t in ("path", "file", "local")):
                    continue
                raw = str(val or "").strip()
                if not raw.lower().endswith(".zip"):
                    continue
                p = Path(raw)
                candidates = [p]
                if not p.is_absolute():
                    candidates += [REPO_ROOT / p, PBP_ROOT / p]
                for candidate in candidates:
                    if candidate.exists() and candidate.is_file():
                        found.setdefault(year, candidate.resolve())
                        break
                if year in found:
                    break
    return found

def discover_year_zip(year: int, manifest_paths: dict[int, Path]) -> Path:
    if year in manifest_paths:
        return manifest_paths[year]

    candidates = []
    for p in PBP_ROOT.rglob("*.zip"):
        if excluded(p):
            continue
        if infer_year_from_text(p.name) == year or infer_year_from_text(str(p.parent)) == year:
            candidates.append(p.resolve())

    # CY2025 may have been copied with the uploaded filename.
    if year == 2025:
        for name in ("pbp_benefits_2025_updated.zip", "pbp-benefits-2025.zip",
                     "pbp_benefits_2025.zip"):
            p = PBP_ROOT / name
            if p.exists():
                candidates.append(p.resolve())

    unique = sorted(set(candidates), key=lambda p: (len(str(p)), str(p).lower()))
    if not unique:
        raise FileNotFoundError(
            f"CY{year}: no PBP Benefits ZIP found under {PBP_ROOT}"
        )

    # Prefer ZIPs whose names explicitly contain PBP/benefit and the year.
    scored = []
    for p in unique:
        s = p.name.lower()
        score = 0
        if str(year) in s:
            score += 4
        if "pbp" in s:
            score += 3
        if "benefit" in s:
            score += 2
        scored.append((score, p))
    max_score = max(x[0] for x in scored)
    best = [p for score, p in scored if score == max_score]

    if len(best) != 1:
        raise RuntimeError(
            f"CY{year}: ambiguous PBP Benefits ZIP discovery: "
            + " | ".join(str(p) for p in best)
        )
    return best[0]

def find_member(zf: zipfile.ZipFile, basename: str) -> Optional[str]:
    matches = [
        n for n in zf.namelist()
        if not n.endswith("/") and Path(n).name.lower() == basename.lower()
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    raise RuntimeError(f"Ambiguous ZIP member {basename}: {matches}")

def detect_delimiter(header_text: str) -> str:
    line = header_text.splitlines()[0] if header_text.splitlines() else header_text
    counts = {"\t": line.count("\t"), ",": line.count(","), "|": line.count("|")}
    delim, count = max(counts.items(), key=lambda x: x[1])
    if count <= 0:
        raise RuntimeError("Unable to detect pbp_mrx delimiter")
    return delim

def profile_pbp_mrx(zf: zipfile.ZipFile, member: str) -> tuple[bool, Counter]:
    text = decode_bytes(zf.read(member))
    delim = detect_delimiter(text[:10000])
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delim)
    if not reader.fieldnames:
        raise RuntimeError("pbp_mrx has no header")
    header_map = {norm_lower(h): h for h in reader.fieldnames if h is not None}
    actual = header_map.get(FIELD.lower())
    if actual is None:
        return False, Counter()

    counts: Counter = Counter()
    for row in reader:
        value = str(row.get(actual, "") or "").strip()
        counts[value] += 1
    return True, counts

def sas_label_present(zf: zipfile.ZipFile, member: Optional[str]) -> bool:
    if not member:
        return False
    text = decode_bytes(zf.read(member))
    # Require field and expected label in the same reasonably short source line.
    for line in text.splitlines():
        low = line.lower()
        if FIELD.lower() in low and EXPECTED_SAS_LABEL.lower() in low:
            return True
    return False

def locate_2025_dictionary(zf: zipfile.ZipFile) -> Optional[str]:
    matches = []
    for n in zf.namelist():
        base = Path(n).name.lower()
        if base.endswith(".xlsx") and "dictionary" in base and "benefit" in base:
            matches.append(n)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        # Narrow fallback: any dictionary XLSX.
        matches = [
            n for n in zf.namelist()
            if Path(n).name.lower().endswith(".xlsx")
            and "dictionary" in Path(n).name.lower()
        ]
    if len(matches) == 1:
        return matches[0]
    return None

def validate_anchor_dictionary(zip_path: Path) -> tuple[bool, list[dict], str]:
    """
    Parse the CY2025 XLSX using openpyxl and require explicit code mapping.
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        return False, [], f"openpyxl unavailable: {exc}"

    with zipfile.ZipFile(zip_path) as zf:
        member = locate_2025_dictionary(zf)
        if not member:
            return False, [], "CY2025 dictionary XLSX not uniquely resolved"
        data = zf.read(member)

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    evidence = []
    mapping: dict[str, str] = {}
    question_evidence = False

    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        try:
            first = next(rows)
        except StopIteration:
            continue
        headers = [norm_lower(v) for v in first]
        # Search all rows generically rather than assuming one exact schema.
        all_rows = [first]
        all_rows.extend(rows)
        for row in all_rows:
            vals = [norm(v) for v in row]
            joined = " | ".join(vals)
            joined_low = joined.lower()
            if FIELD.lower() not in joined_low:
                continue

            rec = {
                "sheet": ws.title,
                "row_text": joined,
            }
            evidence.append(rec)

            if (ANCHOR_QUESTION_FRAGMENT in joined_low
                    and ANCHOR_PARTD_FRAGMENT in joined_low):
                question_evidence = True

            # Prefer named columns when headers expose CODES/CODE_VALUES.
            row_map = {
                headers[i]: vals[i]
                for i in range(min(len(headers), len(vals)))
                if headers[i]
            }
            code = ""
            code_value = ""
            for k, v in row_map.items():
                if k in {"codes", "code", "value"}:
                    code = v
                if k in {"code_values", "code value", "code values",
                         "value_label", "value label"}:
                    code_value = v
            if code in EXPECTED_ANCHOR_MAP and code_value:
                mapping[code] = code_value.lower()

            # Generic fallback for rows where field name and code are on one row.
            for code_candidate, label in EXPECTED_ANCHOR_MAP.items():
                if re.search(rf"(^|\W){re.escape(code_candidate)}(\W|$)", joined):
                    if re.search(rf"(^|\W){label}(\W|$)", joined_low):
                        mapping.setdefault(code_candidate, label)

    wb.close()

    map_ok = all(mapping.get(k) == v for k, v in EXPECTED_ANCHOR_MAP.items())
    ok = map_ok and question_evidence
    note = (
        f"mapping={mapping}; question_evidence={question_evidence}; "
        f"evidence_rows={len(evidence)}"
    )
    return ok, evidence, note

def write_csv(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)

def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_paths = load_manifest_candidates()
    results: list[YearResult] = []
    errors: list[dict] = []

    print("=" * 78)
    print("CMS MEDICARE PART D mrx_drug_ben_yn SEMANTIC CONTINUITY v0.1")
    print("CY2015-CY2025")
    print("=" * 78)
    print()
    print("BOUNDARY:")
    print("  Blind semantic/structural continuity test only.")
    print("  Does NOT read disputed Contract+PBP relationships.")
    print("  No status/payment propagation, imputation, reconstruction, DB writes,")
    print("  or ledger inclusion.")
    print()

    for year in YEARS:
        r = YearResult(year=year)
        try:
            zip_path = discover_year_zip(year, manifest_paths)
            r.zip_path = str(zip_path.relative_to(REPO_ROOT)) if zip_path.is_relative_to(REPO_ROOT) else str(zip_path)
            r.zip_sha256 = sha256_file(zip_path)

            with zipfile.ZipFile(zip_path) as zf:
                bad = zf.testzip()
                if bad:
                    raise RuntimeError(f"ZIP integrity failure at member: {bad}")

                pbp = find_member(zf, "pbp_mrx.txt")
                sas = find_member(zf, "pbp_mrx.sas")
                if not pbp:
                    raise RuntimeError("pbp_mrx.txt not found")

                r.pbp_mrx_member = pbp
                r.sas_member = sas or ""
                r.field_present, counts = profile_pbp_mrx(zf, pbp)
                r.sas_label_found = sas_label_present(zf, sas)

                r.total_records = sum(counts.values())
                r.code_1_count = counts.get("1", 0)
                r.code_2_count = counts.get("2", 0)
                r.blank_count = counts.get("", 0)
                others = {k: v for k, v in counts.items()
                          if k not in {"", "1", "2"}}
                r.other_count = sum(others.values())
                r.other_values = " | ".join(
                    f"{k!r}:{v}" for k, v in sorted(others.items())
                )
                r.observed_nonblank_values = " | ".join(
                    sorted(k for k in counts if k != "")
                )

                structural_ok = (
                    r.field_present
                    and r.sas_label_found
                    and r.other_count == 0
                    and r.code_1_count > 0
                    and r.code_2_count > 0
                )
                r.status = "PASS" if structural_ok else "FAIL"
                if not structural_ok:
                    r.notes = "One or more structural/vocabulary continuity checks failed."

            if year == 2025 and r.zip_sha256 != EXPECTED_2025_ZIP_SHA256:
                r.status = "FAIL"
                r.notes = (
                    r.notes + " " if r.notes else ""
                ) + "CY2025 ZIP SHA-256 differs from preserved documentary anchor."

        except Exception as exc:
            r.status = "FAIL"
            r.notes = str(exc)
            errors.append({"year": year, "error": str(exc)})
        results.append(r)

    # CY2025 direct dictionary semantic anchor
    anchor_ok = False
    anchor_evidence: list[dict] = []
    anchor_note = ""
    try:
        anchor_path = discover_year_zip(2025, manifest_paths)
        anchor_ok, anchor_evidence, anchor_note = validate_anchor_dictionary(anchor_path)
    except Exception as exc:
        anchor_note = str(exc)
        errors.append({"year": 2025, "error": f"Dictionary anchor: {exc}"})

    # Global PASS requires every year structural PASS plus direct CY2025 dictionary PASS.
    all_years_ok = all(r.status == "PASS" for r in results)
    overall_pass = all_years_ok and anchor_ok and len(errors) == 0

    year_rows = [r.__dict__ for r in results]
    write_csv(
        OUTPUT_DIR / "cms_partd_mrx_drug_ben_yn_continuity_by_year.csv",
        year_rows,
        list(YearResult.__dataclass_fields__.keys()),
    )
    write_csv(
        OUTPUT_DIR / "cms_partd_mrx_drug_ben_yn_2025_dictionary_evidence.csv",
        anchor_evidence,
        ["sheet", "row_text"],
    )
    write_csv(
        OUTPUT_DIR / "cms_partd_mrx_drug_ben_yn_continuity_errors.csv",
        errors,
        ["year", "error"],
    )

    checks = [
        {
            "check": "All 11 coverage years resolved and structurally PASS",
            "status": "PASS" if all_years_ok else "FAIL",
            "detail": f"{sum(r.status == 'PASS' for r in results)}/11 years PASS",
        },
        {
            "check": "Exact field mrx_drug_ben_yn present every year",
            "status": "PASS" if all(r.field_present for r in results) else "FAIL",
            "detail": f"{sum(r.field_present for r in results)}/11",
        },
        {
            "check": "SAS label 'MRx Drug Benefit YN' present every year",
            "status": "PASS" if all(r.sas_label_found for r in results) else "FAIL",
            "detail": f"{sum(r.sas_label_found for r in results)}/11",
        },
        {
            "check": "Observed nonblank vocabulary confined to {1,2} every year",
            "status": "PASS" if all(r.other_count == 0 for r in results) else "FAIL",
            "detail": f"other-value records={sum(r.other_count for r in results):,}",
        },
        {
            "check": "Both codes 1 and 2 observed every year",
            "status": "PASS" if all(r.code_1_count > 0 and r.code_2_count > 0 for r in results) else "FAIL",
            "detail": f"{sum(r.code_1_count > 0 and r.code_2_count > 0 for r in results)}/11",
        },
        {
            "check": "CY2025 preserved ZIP SHA-256 matches documentary anchor",
            "status": "PASS" if next((r.zip_sha256 for r in results if r.year == 2025), "") == EXPECTED_2025_ZIP_SHA256 else "FAIL",
            "detail": next((r.zip_sha256 for r in results if r.year == 2025), ""),
        },
        {
            "check": "CY2025 dictionary directly maps 1=Yes and 2=No and defines Part D question",
            "status": "PASS" if anchor_ok else "FAIL",
            "detail": anchor_note,
        },
        {
            "check": "No source/profile errors",
            "status": "PASS" if not errors else "FAIL",
            "detail": f"errors={len(errors)}",
        },
    ]
    write_csv(
        OUTPUT_DIR / "cms_partd_mrx_drug_ben_yn_continuity_checks.csv",
        checks,
        ["check", "status", "detail"],
    )

    summary = []
    summary.append("CMS MEDICARE PART D mrx_drug_ben_yn SEMANTIC CONTINUITY v0.1")
    summary.append(f"Generated UTC: {datetime.now(timezone.utc).isoformat()}")
    summary.append("")
    summary.append("BOUNDARY")
    summary.append("Blind semantic/structural continuity test only.")
    summary.append("No disputed Contract+PBP population is read or classified.")
    summary.append("No status/payment propagation, imputation, reconstruction, DB write, or ledger inclusion.")
    summary.append("")
    summary.append("YEAR RESULTS")
    for r in results:
        summary.append(
            f"CY{r.year}: {r.status} | records={r.total_records:,} | "
            f"1={r.code_1_count:,} | 2={r.code_2_count:,} | "
            f"blank={r.blank_count:,} | other={r.other_count:,} | "
            f"field={r.field_present} | sas_label={r.sas_label_found}"
        )
    summary.append("")
    summary.append("CY2025 DOCUMENTARY ANCHOR")
    summary.append(f"PASS={anchor_ok}")
    summary.append(anchor_note)
    summary.append("")
    summary.append("CHECKS")
    for c in checks:
        summary.append(f"[{c['status']}] {c['check']} — {c['detail']}")
    summary.append("")
    summary.append(f"OVERALL: {'PASS' if overall_pass else 'FAIL'}")
    summary.append("")
    summary.append("INTERPRETATION")
    if overall_pass:
        summary.append(
            "The CMS PBP Benefits field mrx_drug_ben_yn is structurally and "
            "semantically continuous across CY2015-CY2025 under the tested criteria. "
            "CY2025 provides direct CMS dictionary documentation that code 1 means "
            "Yes and code 2 means No for the question asking whether the plan offers "
            "a Medicare Prescription Drug (Part D) benefit. This validator establishes "
            "the semantic rule only; it does not apply that rule to disputed plans."
        )
    else:
        summary.append(
            "Semantic continuity is NOT certified. Do not apply the CY2025 code "
            "mapping backward to disputed CY2015-CY2024 relationships on the basis "
            "of this validator."
        )

    (OUTPUT_DIR / "cms_partd_mrx_drug_ben_yn_continuity_summary.txt").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )

    print("YEAR RESULTS:")
    for r in results:
        print(
            f"  CY{r.year}: {r.status} | records={r.total_records:,} | "
            f"1={r.code_1_count:,} | 2={r.code_2_count:,} | "
            f"blank={r.blank_count:,} | other={r.other_count:,}"
        )
    print()
    print("CHECKS:")
    for c in checks:
        print(f"  [{c['status']}] {c['check']}")
    print()
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"OVERALL: {'PASS' if overall_pass else 'FAIL'}")
    return 0 if overall_pass else 1

if __name__ == "__main__":
    sys.exit(main())
