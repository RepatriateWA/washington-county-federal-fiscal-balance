#!/usr/bin/env python3
r"""
CMS MSSP Assigned-Beneficiary County Value Semantics Certification v0.7

Purpose
-------
Read-only certification/profile of raw beneficiary-value encodings for the
CMS MSSP ACO assigned-beneficiary-by-county source across the available
2016-2024 source chain.

Guardrails
----------
* No DB writes.
* No source mutation.
* No beneficiary-value imputation.
* No suppressed value is treated as zero.
* 2016 blank cells remain UNRESOLVED_HISTORICAL_ENCODING.
* No EarnSaveLoss or other financial value is allocated.
* No Washington incidence or ledger-inclusion decision is made.
* 2015 is recorded as SOURCE_NOT_RECOVERED and is not fabricated.

Run from repository root:
    python .\scripts\certify_cms_mssp_county_value_semantics_2016_2024_v0_7.py

Optional console capture:
    python .\scripts\certify_cms_mssp_county_value_semantics_2016_2024_v0_7.py `
      *> .\cms_mssp_county_value_semantics_v0_7_console.txt
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

VERSION = "v0.7"

SRC_REL = Path("data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county")
EVID_REL = SRC_REL / "validation" / "value_semantics_v0_7"

PINNED = {
    2016: {
        "filename": "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2016_01_01.csv",
        "bytes": 4421455,
        "sha256": "6D745C0F28949F53B4EDA8793CF050A15AFC8A947402901F9E94A9C3EE2FEB19",
    },
    2017: {
        "filename": "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2017_01_01.csv",
        "bytes": 5563732,
        "sha256": "D3C6EDF2B8B80E4244FAD4BC36E8E9E518055D97A0147ABA79DE7D3A61E6ABB3",
    },
    2018: {
        "filename": "Number_Of_ACO_Assigned_Beneficiaries_by_County_PUF_2018_01_01.csv",
        "bytes": 6503795,
        "sha256": "ABA3135EF3CD8F7AEC46F0354D246AD30821BF53EFB9B0D738C957612CE7597F",
    },
}

EXPECTED_MEASURES = [
    ("AB_Psn_Yrs_ESRD", "esrd assigned beneficiary person-years", "COMPONENT"),
    ("AB_Psn_Yrs_DIS", "disabled assigned beneficiary person-years", "COMPONENT"),
    ("AB_Psn_Yrs_AGDU", "aged/dual assigned beneficiary person-years", "COMPONENT"),
    ("AB_Psn_Yrs_AGND", "aged/non-dual assigned beneficiary person-years", "COMPONENT"),
    ("Tot_AB_Psn_Yrs", "total assigned beneficiary person-years", "TOTAL"),
    ("Tot_AB", "total assigned beneficiaries", "TOTAL"),
]

# CMS-documented semantics for explicit symbols in the published data dictionary.
# "." applies to enrollment-type component cells: county has no assigned
# beneficiaries with that enrollment type.
# "*" denotes suppression, including complementary suppression.
DOC_SEMANTICS = {
    "DOT": "DOCUMENTED_MISSING_NO_ASSIGNED_BENEFICIARIES_FOR_ENROLLMENT_TYPE",
    "STAR": "DOCUMENTED_SUPPRESSED_PRIMARY_OR_COMPLEMENTARY",
    "NUMERIC": "OBSERVED_NUMERIC",
    "BLANK_2016": "UNRESOLVED_HISTORICAL_ENCODING",
    "OTHER": "UNEXPECTED_RAW_STATE",
}

def repo_root() -> Path:
    starts = [Path.cwd().resolve(), Path(__file__).resolve().parent]
    for start in starts:
        for p in (start, *start.parents):
            if (p / "data").is_dir() and (p / "scripts").is_dir():
                return p
    raise RuntimeError("Could not locate repository root.")

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()

def norm_header(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def classify_raw(v: str | None) -> str:
    if v is None or v == "" or (isinstance(v, str) and not v.strip()):
        return "BLANK"
    x = v.strip()
    if x == ".":
        return "DOT"
    if x == "*":
        return "STAR"
    try:
        float(x.replace(",", ""))
        return "NUMERIC"
    except ValueError:
        return "OTHER"

def read_csv_bytes(raw: bytes):
    text = raw.decode("utf-8-sig", errors="strict")
    reader = csv.DictReader(io.StringIO(text))
    return reader.fieldnames or [], list(reader)

def read_csv_path(path: Path):
    return read_csv_bytes(path.read_bytes())

def find_measure_columns(fields):
    """
    Resolve beneficiary-measure columns across CMS schema vintages.

    Historical files may use descriptive column labels, while later
    files use canonical abbreviated CMS variable names such as
    AB_Psn_Yrs_ESRD and Tot_AB.

    This is schema aliasing only. It does not alter source values or
    assign semantics to any raw cell.
    """
    out = []
    normalized = {norm_header(f): f for f in fields}

    for var, label, kind in EXPECTED_MEASURES:
        aliases = {
            norm_header(var),
            norm_header(label),
        }

        exact = next(
            (
                normalized[alias]
                for alias in aliases
                if alias in normalized
            ),
            None,
        )

        if exact:
            out.append((var, label, kind, exact))

    return out

def find_year_col(fields):
    return next((f for f in fields if norm_header(f) == "year"), None)

def find_aco_col(fields):
    aliases = {"aco id", "aco_id", "aco_num", "aco num"}
    return next((f for f in fields if norm_header(f) in aliases), None)

def discover_2020_2024_zip(src: Path) -> Path:
    candidates = []
    for p in src.glob("*.zip"):
        try:
            with zipfile.ZipFile(p) as z:
                names = [n.lower() for n in z.namelist()]
                score = sum(
                    any(str(y) in n and n.endswith(".csv") for n in names)
                    for y in range(2020, 2025)
                )
                if score >= 5:
                    candidates.append((score, p))
        except zipfile.BadZipFile:
            pass
    if not candidates:
        raise FileNotFoundError("Could not discover the preserved 2020-2024 assigned-beneficiary county ZIP.")
    candidates.sort(key=lambda x: (-x[0], str(x[1]).lower()))
    return candidates[0][1]

def choose_year_csv(z: zipfile.ZipFile, year: int):
    candidates = []
    for n in z.namelist():
        low = n.lower()
        if not low.endswith(".csv") or str(year) not in low:
            continue
        # Prefer the assigned-beneficiary county PUF, not dictionaries/readmes.
        score = 0
        if "beneficiar" in low: score += 3
        if "county" in low: score += 3
        if "puf" in low: score += 2
        if "off-cycle" in low or "off_cycle" in low: score -= 10
        candidates.append((score, n))
    if not candidates:
        raise FileNotFoundError(f"No CSV candidate found for {year} in {z.filename}")
    candidates.sort(key=lambda x: (-x[0], x[1].lower()))
    return candidates[0][1]

def allocation_status(year: int, kind: str, counts: Counter) -> str:
    """
    Certification-level usability only; not an allocation algorithm.
    """
    if counts["OTHER"]:
        return "NOT_SAFE_UNEXPECTED_RAW_STATE"
    if year == 2016 and counts["BLANK"]:
        return "BOUNDED_OR_SENSITIVITY_ONLY_2016_ENCODING_UNRESOLVED"
    if kind == "TOTAL":
        if counts["DOT"]:
            return "NOT_SAFE_UNEXPECTED_DOT_IN_TOTAL"
        if counts["STAR"]:
            return "BOUNDED_OR_SUPPRESSION_POLICY_REQUIRED"
        return "DIRECT_NUMERIC_AVAILABLE"
    # COMPONENT
    if counts["BLANK"]:
        return "NOT_SAFE_UNEXPECTED_BLANK"
    if counts["STAR"]:
        return "BOUNDED_OR_SUPPRESSION_POLICY_REQUIRED"
    # DOT has documented zero-beneficiary enrollment-type meaning, but this
    # script does not coerce the raw cell to numeric zero.
    return "DIRECT_NUMERIC_PLUS_DOCUMENTED_DOT_SEMANTICS"

def main() -> int:
    root = repo_root()
    src = root / SRC_REL
    evid = root / EVID_REL
    evid.mkdir(parents=True, exist_ok=True)

    report = []
    detail_rows = []
    checks = []

    def emit(s=""):
        print(s)
        report.append(s)

    def check(code, ok, detail):
        status = "PASS" if ok else "FAIL"
        checks.append((code, status, detail))
        emit(f"{code}: {status} - {detail}")

    emit(f"CMS MSSP COUNTY VALUE SEMANTICS CERTIFICATION {VERSION}")
    emit("=" * 100)
    emit("Scope: available assigned-beneficiary-by-county sources, 2016-2024.")
    emit("2015: SOURCE_NOT_RECOVERED; no fabricated observations.")
    emit("CMS documentary rule encoded for explicit symbols: '.' = no assigned beneficiaries")
    emit("for that enrollment type; '*' = primary/complementary suppression.")
    emit("2016 blanks remain unresolved and are NOT equated to '.', '*', or zero.")
    emit()

    sources = {}

    # Pinned standalone 2016-2018 sources.
    for year, spec in PINNED.items():
        path = src / spec["filename"]
        if not path.exists():
            check(f"{year}-SOURCE", False, f"missing {path}")
            continue
        check(f"{year}-BYTES", path.stat().st_size == spec["bytes"],
              f"{path.stat().st_size:,} expected {spec['bytes']:,}")
        actual_hash = sha256(path)
        check(f"{year}-SHA256", actual_hash == spec["sha256"], actual_hash)
        fields, rows = read_csv_path(path)
        sources[year] = (spec["filename"], fields, rows)

    # Discover preserved 2020-2024 ZIP and profile its governing annual CSVs.
    try:
        modern_zip = discover_2020_2024_zip(src)
        emit(f"2020-2024 ZIP: {modern_zip}")
        emit(f"ZIP bytes: {modern_zip.stat().st_size:,}")
        emit(f"ZIP SHA256: {sha256(modern_zip)}")
        with zipfile.ZipFile(modern_zip) as z:
            for year in range(2020, 2025):
                member = choose_year_csv(z, year)
                fields, rows = read_csv_bytes(z.read(member))
                sources[year] = (f"{modern_zip.name}::{member}", fields, rows)
                emit(f"{year} member: {member}")
        emit()
    except Exception as exc:
        check("2020-2024-SOURCE", False, f"{type(exc).__name__}: {exc}")

    # 2019 is intentionally not folded into a single annual observation:
    # regular and off-cycle are separate certified participation periods.
    emit("2019 STATUS")
    emit("-" * 100)
    emit("2019 is DEFERRED_TO_CERTIFIED_PERIOD_MODEL: regular and off-cycle county PUFs")
    emit("must remain separate participation-period observations; no annual collapsing is performed here.")
    emit()

    for year in [2016, 2017, 2018, 2020, 2021, 2022, 2023, 2024]:
        emit(f"{year} VALUE-STATE PROFILE")
        emit("-" * 100)
        if year not in sources:
            emit("SOURCE UNAVAILABLE TO THIS RUN")
            emit()
            continue

        source_name, fields, rows = sources[year]
        emit(f"source={source_name}")
        emit(f"rows={len(rows):,}")
        ycol = find_year_col(fields)
        acol = find_aco_col(fields)
        measures = find_measure_columns(fields)

        check(f"{year}-SCHEMA", len(measures) == 6,
              f"beneficiary measure columns={len(measures)}/6")
        if ycol:
            mismatches = sum(1 for r in rows if (r.get(ycol) or "").strip() != str(year))
            check(f"{year}-YEAR", mismatches == 0, f"mismatched rows={mismatches:,}")
        else:
            check(f"{year}-YEAR", False, "Year column not found")

        distinct_acos = len({(r.get(acol) or "").strip() for r in rows if acol and (r.get(acol) or "").strip()})
        emit(f"distinct_ACO_ID={distinct_acos:,}")

        for var, label, kind, raw_col in measures:
            counts = Counter(classify_raw(r.get(raw_col)) for r in rows)
            status = allocation_status(year, kind, counts)
            semantics = []
            if counts["NUMERIC"]: semantics.append(DOC_SEMANTICS["NUMERIC"])
            if counts["DOT"]: semantics.append(DOC_SEMANTICS["DOT"])
            if counts["STAR"]: semantics.append(DOC_SEMANTICS["STAR"])
            if counts["BLANK"]:
                semantics.append(DOC_SEMANTICS["BLANK_2016"] if year == 2016 else "UNEXPECTED_BLANK")
            if counts["OTHER"]: semantics.append(DOC_SEMANTICS["OTHER"])

            emit(
                f"{var:<18} kind={kind:<9} "
                f"numeric={counts['NUMERIC']:,} dot={counts['DOT']:,} "
                f"star={counts['STAR']:,} blank={counts['BLANK']:,} "
                f"other={counts['OTHER']:,}"
            )
            emit(f"  certification={status}")
            detail_rows.append({
                "year": year,
                "source": source_name,
                "variable": var,
                "source_column": raw_col,
                "measure_kind": kind,
                "numeric_count": counts["NUMERIC"],
                "dot_count": counts["DOT"],
                "star_count": counts["STAR"],
                "blank_count": counts["BLANK"],
                "other_count": counts["OTHER"],
                "documented_or_observed_semantics": ";".join(semantics),
                "allocation_readiness": status,
            })

            # Mechanical validity: known lexical states only.
            check(f"{year}-{var}-LEXICAL", counts["OTHER"] == 0,
                  f"unexpected raw states={counts['OTHER']:,}")
            # Total fields should not use documented component-only dot semantics.
            if kind == "TOTAL":
                check(f"{year}-{var}-TOTAL-DOT", counts["DOT"] == 0,
                      f"dot states in total field={counts['DOT']:,}")
        emit()

    emit("CERTIFICATION CONCLUSIONS")
    emit("-" * 100)
    emit("2015: SOURCE_NOT_RECOVERED. Do not impute from adjacent years.")
    emit("2016: Numeric observations are usable as observed; blank cells remain")
    emit("      UNRESOLVED_HISTORICAL_ENCODING and require bounded/sensitivity treatment")
    emit("      unless contemporaneous CMS documentation resolves the encoding.")
    emit("2017-2018 and 2020-2024: explicit '.'/'*' semantics may be carried forward")
    emit("      according to CMS documentation, while preserving the raw symbols.")
    emit("2019: preserve regular and off-cycle participation periods separately.")
    emit("No dollar allocation is authorized by this certification alone.")
    emit()

    emit("GUARDRAILS")
    emit("-" * 100)
    emit("No source file was modified.")
    emit("No blank, '.', or '*' cell was converted to a numeric value.")
    emit("No EarnSaveLoss or other financial measure was allocated.")
    emit("No Washington or county dollar incidence was inferred.")
    emit("No ledger inclusion decision was made.")
    emit()

    failures = [x for x in checks if x[1] == "FAIL"]
    emit(f"OVERALL EXECUTION {VERSION}: {'PASS' if not failures else 'FAIL'}")
    emit(f"Checks: {len(checks)} total; {len(failures)} failed")
    emit(f"Evidence: {evid}")

    report_path = evid / "cms_mssp_county_value_semantics_certification_v0_7.txt"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")

    detail_path = evid / "cms_mssp_county_value_semantics_detail_v0_7.csv"
    with detail_path.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "year", "source", "variable", "source_column", "measure_kind",
            "numeric_count", "dot_count", "star_count", "blank_count",
            "other_count", "documented_or_observed_semantics",
            "allocation_readiness",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(detail_rows)

    checks_path = evid / "cms_mssp_county_value_semantics_checks_v0_7.csv"
    with checks_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["check_code", "status", "detail"])
        w.writerows(checks)

    return 0 if not failures else 1

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nFATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
