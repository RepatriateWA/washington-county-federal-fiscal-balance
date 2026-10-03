#!/usr/bin/env python3
r"""
CMS MSSP Assigned Beneficiary County 2019 Semantic/Profile Validator v0.5.1

Purpose
-------
Read-only profiling of the CMS 2019 ACO assigned-beneficiary-by-county archive
against the existing CMS MSSP Performance Year Financial and Quality Results
archive.

NO database writes.
NO raw-source extraction.
NO EarnSaveLoss allocation.
NO ledger-inclusion decision.

The profiler:
  * verifies the pinned 2019 county ZIP;
  * inventories the 2019-01-01 and 2019-07-01/off-cycle county CSVs;
  * profiles schemas, rows, ACO_IDs, duplicate geography keys, and beneficiary
    value states;
  * compares January and July ACO universes;
  * inventories candidate 2019 members in the financial-results ZIP;
  * profiles their ACO_ID sets;
  * reports exact/set-overlap relationships without forcing a period mapping;
  * writes reproducible evidence under the raw source validation tree.

Run from the repository root:
    python .\scripts\profile_cms_mssp_assigned_beneficiary_county_2019_v0_5.py

Optional:
    python .\scripts\profile_cms_mssp_assigned_beneficiary_county_2019_v0_5.py *> .\cms_mssp_2019_county_profile_v0_5_console.txt
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Iterable

VERSION = "v0.5.1"

COUNTY_REL = Path(
    "data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county/"
    "Number of Accountable Care Organization Assigned Beneficiaries by County 2019.zip"
)
FINANCIAL_REL = Path(
    "data/raw/cms/medicare_aco/mssp_performance_results/"
    "Performance Year Financial and Quality Results.zip"
)
EVIDENCE_REL = Path(
    "data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county/"
    "validation/profile_2019_v0_5_1"
)

EXPECTED_COUNTY_SHA256 = (
    "17D8441928A6B725C11BAD6E2C8E536634108E9877409D164EDBBE51B4F9EEAE"
)
EXPECTED_COUNTY_BYTES = 1_685_820

TOTAL_FIELDS = ("Tot_AB_Psn_Yrs", "Tot_AB")
COMPONENT_FIELDS = (
    "AB_Psn_Yrs_ESRD",
    "AB_Psn_Yrs_DIS",
    "AB_Psn_Yrs_AGDU",
    "AB_Psn_Yrs_AGND",
)

ACO_ALIASES = (
    "ACO_ID", "ACO ID", "ACOId", "ACO_ID_Number", "ACO_ID_Num"
)

# Candidate geography fields used only to diagnose duplicate row keys.
GEO_CANDIDATES = (
    "State_ID", "State", "State_Abbr", "State_Code",
    "County_ID", "County", "County_Name", "County_FIPS", "FIPS"
)


def repo_root() -> Path:
    """Find repository root from script location or current working directory."""
    starts = [Path.cwd().resolve(), Path(__file__).resolve().parent]
    for start in starts:
        for p in (start, *start.parents):
            if (p / "data").is_dir() and (p / "scripts").is_dir():
                return p
    raise RuntimeError(
        "Could not locate repository root (expected sibling data/ and scripts/ directories)."
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def decode_csv_bytes(data: bytes) -> str:
    # CMS CSVs are normally UTF-8/UTF-8-SIG; cp1252 is a safe diagnostic fallback.
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1")


def read_zip_csv(zf: zipfile.ZipFile, member: str) -> tuple[list[str], list[dict[str, str]]]:
    text = decode_csv_bytes(zf.read(member))
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    rows = list(reader)
    return fields, rows


def find_col(fields: Iterable[str], aliases: Iterable[str]) -> str | None:
    norm = {re.sub(r"[^a-z0-9]", "", f.lower()): f for f in fields}
    for a in aliases:
        key = re.sub(r"[^a-z0-9]", "", a.lower())
        if key in norm:
            return norm[key]
    return None


def classify_value(value: str | None, *, total: bool) -> str:
    if value is None:
        return "missing-column"
    s = value.strip()
    if s == "":
        return "blank"
    if s == "*":
        return "suppressed"
    if s == ".":
        return "unexpected-dot" if total else "cms-zero-dot"
    try:
        float(s.replace(",", ""))
        return "numeric"
    except ValueError:
        return "other"


def classify_field(rows: list[dict[str, str]], field: str, *, total: bool) -> Counter:
    c = Counter()
    for r in rows:
        c[classify_value(r.get(field), total=total)] += 1
    return c


def fmt_counter(c: Counter) -> str:
    order = [
        "numeric", "suppressed", "cms-zero-dot", "unexpected-dot",
        "blank", "other", "missing-column"
    ]
    return " ".join(f"{k}={c.get(k, 0):,}" for k in order if k in c or c.get(k, 0))


def identify_county_members(names: list[str]) -> dict[str, str]:
    csvs = [n for n in names if n.lower().endswith(".csv")]
    jan = [n for n in csvs if re.search(r"2019[_-]01[_-]01", n, re.I)]
    jul = [n for n in csvs if re.search(r"2019[_-]07[_-]01", n, re.I)]
    if len(jan) != 1 or len(jul) != 1:
        raise RuntimeError(
            f"Expected exactly one 2019_01_01 and one 2019_07_01 county CSV; "
            f"found January={len(jan)}, July={len(jul)}."
        )
    return {"2019_01_01": jan[0], "2019_07_01": jul[0]}


def likely_2019_financial_members(zf: zipfile.ZipFile) -> list[str]:
    names = [i.filename for i in zf.infolist() if i.filename.lower().endswith(".csv")]
    # First pass: filenames carrying 2019/PY2019/2019A/B-style evidence.
    hits = [n for n in names if re.search(r"(?<!\d)2019(?!\d)|py[_ -]?2019", n, re.I)]
    if hits:
        return hits

    # Fallback: inspect CSVs for a year/period column containing 2019.
    candidates = []
    for n in names:
        try:
            fields, rows = read_zip_csv(zf, n)
        except Exception:
            continue
        year_cols = [
            f for f in fields
            if re.search(r"year|period|performance", f, re.I)
        ]
        found = False
        for r in rows[:5000]:
            for f in year_cols:
                if "2019" in (r.get(f) or ""):
                    found = True
                    break
            if found:
                break
        if found:
            candidates.append(n)
    return candidates


def profile_rows(label: str, fields: list[str], rows: list[dict[str, str]]) -> dict:
    aco_col = find_col(fields, ACO_ALIASES)
    if not aco_col:
        raise RuntimeError(f"{label}: could not identify ACO_ID column. Fields={fields}")

    aco_values = [(r.get(aco_col) or "").strip() for r in rows]
    aco_set = {x for x in aco_values if x}
    blank_aco = sum(1 for x in aco_values if not x)

    geo_cols = [f for f in fields if f in GEO_CANDIDATES]
    if not geo_cols:
        # More permissive diagnostic matching.
        geo_cols = [
            f for f in fields
            if re.search(r"state|county|fips", f, re.I) and f != aco_col
        ]

    dup_count = None
    key_cols = [aco_col] + geo_cols
    if len(key_cols) > 1:
        keys = [
            tuple((r.get(c) or "").strip() for c in key_cols)
            for r in rows
        ]
        dup_count = len(keys) - len(set(keys))

    return {
        "label": label,
        "fields": fields,
        "rows": len(rows),
        "aco_col": aco_col,
        "acos": aco_set,
        "blank_aco": blank_aco,
        "geo_cols": geo_cols,
        "duplicate_geo_keys": dup_count,
    }


def write_csv(path: Path, header: list[str], rows: Iterable[Iterable[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main() -> int:
    root = repo_root()
    county_zip = root / COUNTY_REL
    financial_zip = root / FINANCIAL_REL
    evidence = root / EVIDENCE_REL
    evidence.mkdir(parents=True, exist_ok=True)

    report: list[str] = []
    checks: list[tuple[str, str, str]] = []

    def emit(s: str = "") -> None:
        report.append(s)
        print(s)

    def check(name: str, passed: bool, detail: str) -> None:
        status = "PASS" if passed else "FAIL"
        checks.append((name, status, detail))
        emit(f"{name}: {status} - {detail}")

    emit("CMS MSSP ASSIGNED BENEFICIARY COUNTY 2019 SEMANTIC PROFILE v0.5")
    emit("=" * 88)
    emit("Read-only profiling. No DB writes, dollar allocation, or ledger decision.")
    emit()

    if not county_zip.exists():
        raise FileNotFoundError(county_zip)
    if not financial_zip.exists():
        raise FileNotFoundError(financial_zip)

    actual_bytes = county_zip.stat().st_size
    actual_sha = sha256_file(county_zip)
    emit(f"County source: {county_zip}")
    emit(f"County bytes : {actual_bytes:,}")
    emit(f"County SHA256: {actual_sha}")
    emit(f"Financial source: {financial_zip}")
    emit()

    check("SOURCE-01", actual_bytes == EXPECTED_COUNTY_BYTES,
          f"county bytes={actual_bytes:,} expected={EXPECTED_COUNTY_BYTES:,}")
    check("SOURCE-02", actual_sha == EXPECTED_COUNTY_SHA256,
          f"county SHA-256={actual_sha}")
    emit()

    with zipfile.ZipFile(county_zip) as zc:
        county_names = [i.filename for i in zc.infolist()]
        members = identify_county_members(county_names)
        county_profiles = {}

        emit("COUNTY PERIOD PROFILES")
        emit("-" * 88)
        for period, member in members.items():
            fields, rows = read_zip_csv(zc, member)
            p = profile_rows(period, fields, rows)
            county_profiles[period] = p

            emit(f"{period}")
            emit(f"  member: {member}")
            emit(f"  rows={p['rows']:,} distinct_ACO_ID={len(p['acos']):,} blank_ACO_ID={p['blank_aco']:,}")
            emit(f"  ACO column: {p['aco_col']}")
            emit(f"  geography columns used for duplicate diagnostic: {p['geo_cols']}")
            emit(f"  duplicate ACO+geography keys: {p['duplicate_geo_keys']}")
            emit(f"  columns ({len(fields)}): {fields}")

            field_lookup = {f.lower(): f for f in fields}
            for fld in TOTAL_FIELDS:
                actual_fld = field_lookup.get(fld.lower())
                if actual_fld:
                    emit(f"  {actual_fld}: {fmt_counter(classify_field(rows, actual_fld, total=True))}")
                else:
                    emit(f"  {fld}: MISSING")
            for fld in COMPONENT_FIELDS:
                actual_fld = field_lookup.get(fld.lower())
                if actual_fld:
                    emit(f"  {actual_fld}: {fmt_counter(classify_field(rows, actual_fld, total=False))}")
                else:
                    emit(f"  {fld}: MISSING")
            emit()

            write_csv(
                evidence / f"cms_mssp_county_{period}_schema_v0_5_1.csv",
                ["ordinal", "column_name"],
                ((i + 1, f) for i, f in enumerate(fields)),
            )
            write_csv(
                evidence / f"cms_mssp_county_{period}_aco_ids_v0_5_1.csv",
                ["ACO_ID"],
                ((x,) for x in sorted(p["acos"])),
            )

        jan = county_profiles["2019_01_01"]["acos"]
        jul = county_profiles["2019_07_01"]["acos"]
        overlap = jan & jul
        jan_only = jan - jul
        jul_only = jul - jan

        emit("COUNTY COHORT SET RELATIONSHIP")
        emit("-" * 88)
        emit(f"January ACOs : {len(jan):,}")
        emit(f"July ACOs    : {len(jul):,}")
        emit(f"Intersection : {len(overlap):,}")
        emit(f"January only : {len(jan_only):,}")
        emit(f"July only    : {len(jul_only):,}")
        emit(f"Union        : {len(jan | jul):,}")
        emit()

        write_csv(
            evidence / "cms_mssp_2019_county_cohort_set_relationship_v0_5_1.csv",
            ["relationship", "ACO_ID"],
            [(kind, aco) for kind, vals in (
                ("intersection", overlap),
                ("january_only", jan_only),
                ("july_only", jul_only),
            ) for aco in sorted(vals)],
        )

    emit("FINANCIAL 2019 CANDIDATE MEMBERS")
    emit("-" * 88)
    financial_profiles = []
    with zipfile.ZipFile(financial_zip) as zf:
        candidates = likely_2019_financial_members(zf)
        emit(f"Candidate 2019 CSV members found: {len(candidates)}")
        if not candidates:
            emit("No candidate 2019 financial CSV was identified automatically.")
        for member in candidates:
            try:
                fields, rows = read_zip_csv(zf, member)
                p = profile_rows(member, fields, rows)
            except Exception as exc:
                emit(f"  {member}")
                emit(f"    PROFILE ERROR: {exc}")
                continue

            financial_profiles.append(p)
            emit(f"  {member}")
            emit(f"    rows={p['rows']:,} distinct_ACO_ID={len(p['acos']):,} blank_ACO_ID={p['blank_aco']:,}")
            emit(f"    ACO column: {p['aco_col']}")
            emit(f"    columns ({len(fields)}): {fields}")

            for cohort_name, cp in county_profiles.items():
                ca = cp["acos"]
                fa = p["acos"]
                emit(
                    f"    vs {cohort_name}: "
                    f"county={len(ca):,} financial={len(fa):,} "
                    f"intersection={len(ca & fa):,} "
                    f"county_only={len(ca - fa):,} "
                    f"financial_only={len(fa - ca):,} "
                    f"exact_equal={'YES' if ca == fa else 'NO'}"
                )
            emit()

    comparison_rows = []
    for fp in financial_profiles:
        for cohort_name, cp in county_profiles.items():
            ca, fa = cp["acos"], fp["acos"]
            comparison_rows.append([
                cohort_name,
                fp["label"],
                len(ca),
                len(fa),
                len(ca & fa),
                len(ca - fa),
                len(fa - ca),
                "YES" if ca == fa else "NO",
            ])
    write_csv(
        evidence / "cms_mssp_2019_county_financial_set_comparison_v0_5_1.csv",
        [
            "county_cohort", "financial_member", "county_acos", "financial_acos",
            "intersection", "county_only", "financial_only", "exact_equal"
        ],
        comparison_rows,
    )

    emit("INTERPRETATION GUARDRAILS")
    emit("-" * 88)
    emit("PROFILE-ONLY: This script does not choose a governing 2019 financial period.")
    emit("PROFILE-ONLY: It does not treat suppressed beneficiary observations as zero.")
    emit("PROFILE-ONLY: It does not allocate EarnSaveLoss or any other financial measure.")
    emit("PROFILE-ONLY: It does not establish Washington dollar incidence or ledger inclusion.")
    emit()

    check("COUNTY-01", set(county_profiles) == {"2019_01_01", "2019_07_01"},
          "exactly the January and July/off-cycle county CSVs were identified")
    check("COUNTY-02", all(p["blank_aco"] == 0 for p in county_profiles.values()),
          "ACO_ID is populated on every county row")
    check("FIN-01", len(financial_profiles) > 0,
          f"profiled financial 2019 candidate members={len(financial_profiles)}")

    overall = all(status == "PASS" for _, status, _ in checks)
    emit()
    emit(f"OVERALL PROFILE EXECUTION {VERSION}: {'PASS' if overall else 'REVIEW REQUIRED'}")
    emit(f"Evidence: {evidence}")

    (evidence / "cms_mssp_assigned_beneficiary_county_2019_profile_v0_5_1.txt").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    write_csv(
        evidence / "cms_mssp_assigned_beneficiary_county_2019_checks_v0_5_1.csv",
        ["check_id", "status", "detail"],
        checks,
    )

    return 0 if overall else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nFATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
