#!/usr/bin/env python
"""
CMS Medicare Advantage Part C — Plan Payment Source Profiler v0.2

Read-only forensic profiler for CY2014-CY2024 CMS Plan Payment ZIP packages.

Purpose
-------
* Resolve the 11 annual PLAN_PAYMENT ZIPs from the acquisition manifest.
* Inventory every ZIP member.
* Select exactly two Part C workbooks per year:
    - PartCCountyLevel.xlsx
    - PartCPlanLevel.xlsx
* Record the Plan Payment Data Element(s) PDF as documentation.
* Explicitly classify Part D / reconciliation / RDS artifacts as out of scope.
* Profile Excel sheets, detect likely header rows, and profile columns.
* Fingerprint ZIPs and embedded Part C workbook bytes with SHA-256.
* Produce cross-year schema evidence separately for COUNTY_LEVEL and PLAN_LEVEL.
* Perform NO payment reconstruction and NO enrollment imputation.

This script does not modify CMS source artifacts or write to PostgreSQL.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


REQUIRED_YEARS = list(range(2014, 2025))
EXPECTED_PARTC_PER_YEAR = 2
EXPECTED_PARTC_TOTAL = len(REQUIRED_YEARS) * EXPECTED_PARTC_PER_YEAR

DEFAULT_MANIFEST = Path(
    "data/raw/cms/medicare_advantage/validation/source_acquisition/"
    "cms_ma_partc_source_acquisition_manifest.csv"
)
DEFAULT_OUTPUT_DIR = Path(
    "data/raw/cms/medicare_advantage/validation/payment_profile"
)

SOURCE_COLUMN_CANDIDATES = [
    "source_type", "source", "artifact_type", "dataset_type", "file_type"
]
YEAR_COLUMN_CANDIDATES = [
    "payment_year", "year", "calendar_year", "cy", "source_year"
]
PATH_COLUMN_CANDIDATES = [
    "canonical_local_path", "local_path", "destination_path", "download_path",
    "artifact_path", "file_path", "path"
]
STATUS_COLUMN_CANDIDATES = [
    "status", "acquisition_status", "download_status"
]

CANDIDATE_PATTERNS = {
    "IDENTIFIER": [
        r"\bcontract\b", r"\bplan\b", r"\bid\b", r"\borganization\b",
        r"\borg\b", r"\bh[- ]?number\b"
    ],
    "GEOGRAPHY": [
        r"\bcounty\b", r"\bstate\b", r"\bfips\b", r"\bssa\b",
        r"\bgeograph", r"\bregion\b"
    ],
    "PAYMENT": [
        r"\bpayment\b", r"\bpmt\b", r"\bpaid\b", r"\bamount\b",
        r"\bpmpm\b", r"\bper member\b"
    ],
    "BENCHMARK": [r"\bbenchmark\b", r"\bbid benchmark\b"],
    "REBATE": [r"\brebate\b"],
    "RISK": [r"\brisk\b", r"\bra factor\b", r"\brisk score\b"],
    "ENROLLMENT": [
        r"\benroll", r"\bmember", r"\bbeneficiar", r"\bmonths?\b"
    ],
    "PART_AB": [
        r"\bpart a\b", r"\bpart b\b", r"\ba/b\b", r"\bpart ab\b",
        r"\bpart c\b"
    ],
    "PART_D": [r"\bpart d\b", r"\bdrug\b", r"\brx\b"],
    "QUALITY": [
        r"\bquality\b", r"\bstar\b", r"\bbonus\b", r"\bqbp\b"
    ],
}


def norm_col(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def first_matching_column(columns: Iterable[str], candidates: list[str]) -> str | None:
    mapping = {norm_col(c): c for c in columns}
    for candidate in candidates:
        if norm_col(candidate) in mapping:
            return mapping[norm_col(candidate)]
    return None


def sha256_path(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_cell(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return value


def display_value(value: Any, limit: int = 100) -> str:
    value = clean_cell(value)
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def numeric_series(series: pd.Series) -> pd.Series:
    if series.empty:
        return pd.Series(dtype="float64")
    cleaned = series.map(clean_cell)
    as_text = cleaned.astype("string").str.replace(",", "", regex=False)
    as_text = as_text.str.replace("$", "", regex=False)
    as_text = as_text.str.replace("%", "", regex=False)
    as_text = as_text.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    return pd.to_numeric(as_text, errors="coerce")


def candidate_categories(column_name: str) -> list[str]:
    text = re.sub(r"[_\-]+", " ", str(column_name).lower())
    found = []
    for category, patterns in CANDIDATE_PATTERNS.items():
        if any(re.search(pattern, text, flags=re.I) for pattern in patterns):
            found.append(category)
    return found


def classify_member(name: str) -> tuple[str, str]:
    base = Path(name).name
    low = base.lower()

    if re.search(r"part\s*c\s*county\s*level", low, flags=re.I) and low.endswith((".xlsx", ".xlsm", ".xls")):
        return "PARTC_COUNTY_LEVEL", "PROFILE"
    if re.search(r"part\s*c\s*plan\s*level", low, flags=re.I) and low.endswith((".xlsx", ".xlsm", ".xls")):
        return "PARTC_PLAN_LEVEL", "PROFILE"
    if "plan payment data element" in low and low.endswith(".pdf"):
        return "PLAN_PAYMENT_DOCUMENTATION", "DOCUMENT"
    if "partd" in low.replace(" ", "") or "part d" in low:
        return "PART_D", "OUT_OF_SCOPE"
    if "rds" in low:
        return "RDS", "OUT_OF_SCOPE"
    if low.endswith(".pdf"):
        return "OTHER_DOCUMENTATION", "DOCUMENT"
    return "OTHER", "OUT_OF_SCOPE"


def workbook_role(member_class: str) -> str:
    if member_class == "PARTC_COUNTY_LEVEL":
        return "COUNTY_LEVEL"
    if member_class == "PARTC_PLAN_LEVEL":
        return "PLAN_LEVEL"
    raise ValueError(member_class)


def row_header_score(values: list[Any]) -> float:
    nonblank = [display_value(v, 200) for v in values if clean_cell(v) is not None]
    if not nonblank:
        return -999.0

    unique = len(set(nonblank))
    textish = sum(any(ch.isalpha() for ch in v) for v in nonblank)
    longish = sum(len(v) >= 3 for v in nonblank)
    numeric_only = sum(bool(re.fullmatch(r"[-+]?[\d,.()%$ ]+", v)) for v in nonblank)

    score = 0.0
    score += min(len(nonblank), 25) * 1.0
    score += unique * 0.35
    score += textish * 1.5
    score += longish * 0.25
    score -= numeric_only * 0.75

    joined = " ".join(nonblank).lower()
    header_terms = [
        "contract", "plan", "county", "state", "payment", "benchmark",
        "rebate", "risk", "enrollment", "member", "amount", "rate",
        "organization", "fips", "ssa", "part"
    ]
    score += sum(2.0 for term in header_terms if term in joined)
    return score


def detect_header_row(raw: pd.DataFrame, max_rows: int = 30) -> tuple[int, float]:
    if raw.empty:
        return 0, -999.0
    limit = min(max_rows, len(raw))
    scores = [(i, row_header_score(raw.iloc[i].tolist())) for i in range(limit)]
    return max(scores, key=lambda x: x[1])


def make_unique_headers(values: list[Any]) -> list[str]:
    result = []
    seen = Counter()
    for idx, value in enumerate(values, start=1):
        base = display_value(value, 300)
        if not base:
            base = f"unnamed_{idx}"
        base = re.sub(r"\s+", " ", base).strip()
        seen[base] += 1
        result.append(base if seen[base] == 1 else f"{base}__{seen[base]}")
    return result


def read_excel_workbook_from_bytes(data: bytes, filename: str) -> dict[str, pd.DataFrame]:
    suffix = Path(filename).suffix.lower()
    bio = io.BytesIO(data)

    if suffix in {".xlsx", ".xlsm"}:
        engine = "openpyxl"
    elif suffix == ".xls":
        engine = "xlrd"
    else:
        raise ValueError(f"Unsupported workbook extension: {suffix}")

    xls = pd.ExcelFile(bio, engine=engine)
    result: dict[str, pd.DataFrame] = {}
    for sheet in xls.sheet_names:
        bio.seek(0)
        result[sheet] = pd.read_excel(
            bio,
            sheet_name=sheet,
            header=None,
            dtype=object,
            engine=engine,
        )
    return result


def resolve_repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()

    cwd = Path.cwd().resolve()
    if (cwd / ".git").exists() or (cwd / "data").exists():
        return cwd

    for parent in cwd.parents:
        if (parent / ".git").exists():
            return parent

    return cwd


def resolve_manifest_rows(manifest_path: Path) -> tuple[pd.DataFrame, dict[str, str | None]]:
    manifest = pd.read_csv(manifest_path, dtype=object)

    source_col = first_matching_column(manifest.columns, SOURCE_COLUMN_CANDIDATES)
    year_col = first_matching_column(manifest.columns, YEAR_COLUMN_CANDIDATES)
    path_col = first_matching_column(manifest.columns, PATH_COLUMN_CANDIDATES)
    status_col = first_matching_column(manifest.columns, STATUS_COLUMN_CANDIDATES)

    missing = []
    if source_col is None:
        missing.append("source-type column")
    if year_col is None:
        missing.append("year column")
    if path_col is None:
        missing.append("local-path column")

    if missing:
        raise RuntimeError(
            "Could not resolve " + ", ".join(missing)
            + ". Manifest columns are: " + ", ".join(map(str, manifest.columns))
        )

    source_values = manifest[source_col].astype(str).str.upper().str.strip()
    selected = manifest[source_values.eq("PLAN_PAYMENT")].copy()

    selected["_resolved_year"] = pd.to_numeric(selected[year_col], errors="coerce")
    selected = selected[selected["_resolved_year"].isin(REQUIRED_YEARS)].copy()
    selected["_resolved_year"] = selected["_resolved_year"].astype(int)

    return selected, {
        "source_col": source_col,
        "year_col": year_col,
        "path_col": path_col,
        "status_col": status_col,
    }


def resolve_local_path(repo_root: Path, raw_path: Any) -> Path:
    p = Path(str(raw_path))
    if not p.is_absolute():
        p = repo_root / p
    return p.resolve()


def profile_column(
    series: pd.Series,
    *,
    year: int,
    role: str,
    zip_path: Path,
    member_name: str,
    member_sha256: str,
    sheet_name: str,
    header_row_zero_based: int,
    column_position: int,
    column_name: str,
) -> dict[str, Any]:
    cleaned = series.map(clean_cell)
    nonblank = cleaned.dropna()
    nums = numeric_series(nonblank)
    numeric_nonnull = nums.dropna()

    examples = []
    for value in nonblank:
        text = display_value(value)
        if text and text not in examples:
            examples.append(text)
        if len(examples) >= 5:
            break

    categories = candidate_categories(column_name)

    row = {
        "payment_year": year,
        "workbook_role": role,
        "zip_path": str(zip_path),
        "zip_member": member_name,
        "member_sha256": member_sha256,
        "sheet_name": sheet_name,
        "header_row_excel": header_row_zero_based + 1,
        "column_position": column_position,
        "column_name": column_name,
        "normalized_column_name": norm_col(column_name),
        "row_count": len(series),
        "nonblank_count": len(nonblank),
        "blank_count": int(len(series) - len(nonblank)),
        "distinct_nonblank_count": int(nonblank.astype(str).nunique()) if len(nonblank) else 0,
        "numeric_like_count": int(nums.notna().sum()),
        "text_like_count": int(len(nonblank) - nums.notna().sum()),
        "numeric_min": float(numeric_nonnull.min()) if len(numeric_nonnull) else None,
        "numeric_max": float(numeric_nonnull.max()) if len(numeric_nonnull) else None,
        "numeric_mean": float(numeric_nonnull.mean()) if len(numeric_nonnull) else None,
        "numeric_median": float(numeric_nonnull.median()) if len(numeric_nonnull) else None,
        "negative_count": int((numeric_nonnull < 0).sum()) if len(numeric_nonnull) else 0,
        "zero_count": int((numeric_nonnull == 0).sum()) if len(numeric_nonnull) else 0,
        "example_values": " | ".join(examples),
        "candidate_categories": "|".join(categories),
    }
    return row


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root)
    manifest_path = (
        Path(args.manifest).resolve()
        if args.manifest
        else (repo_root / DEFAULT_MANIFEST).resolve()
    )
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else (repo_root / DEFAULT_OUTPUT_DIR).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 88)
    print("CMS MEDICARE ADVANTAGE PART C — PLAN PAYMENT SOURCE PROFILE v0.2")
    print("=" * 88)
    print()
    print("Read-only forensic profiling; no payment reconstruction.")
    print(f"Repository root: {repo_root}")
    print(f"Manifest:        {manifest_path}")
    print()

    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}")
        return 2

    try:
        selected, cols = resolve_manifest_rows(manifest_path)
    except Exception as exc:
        print(f"ERROR resolving manifest: {exc}")
        return 2

    years = sorted(selected["_resolved_year"].tolist())
    year_counts = Counter(years)
    missing_years = [y for y in REQUIRED_YEARS if y not in year_counts]
    duplicate_years = [y for y, n in year_counts.items() if n > 1]

    print("MANIFEST RESOLUTION")
    print("-" * 88)
    print(f"Source column: {cols['source_col']}")
    print(f"Year column:   {cols['year_col']}")
    print(f"Path column:   {cols['path_col']}")
    print(f"Status column: {cols['status_col'] or 'NONE'}")
    print(f"PLAN_PAYMENT rows resolved: {len(selected)}")
    print(f"Years: {years}")
    print()

    file_rows: list[dict[str, Any]] = []
    member_rows: list[dict[str, Any]] = []
    sheet_rows: list[dict[str, Any]] = []
    column_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []

    profiled_years = set()
    role_year_presence: dict[tuple[int, str], int] = Counter()
    documentation_year_presence: dict[int, int] = Counter()

    for _, manifest_row in selected.sort_values("_resolved_year").iterrows():
        year = int(manifest_row["_resolved_year"])
        zip_path = resolve_local_path(repo_root, manifest_row[cols["path_col"]])
        manifest_status = (
            str(manifest_row[cols["status_col"]])
            if cols["status_col"] is not None
            else ""
        )

        print(f"Profiling CY{year}: {zip_path}")

        file_record = {
            "payment_year": year,
            "manifest_status": manifest_status,
            "zip_path": str(zip_path),
            "exists": zip_path.exists(),
            "file_size_bytes": zip_path.stat().st_size if zip_path.exists() else None,
            "zip_sha256": None,
            "zip_member_count": None,
            "recognized_partc_workbooks": 0,
            "documentation_pdfs": 0,
            "profile_status": "ERROR",
            "error": "",
        }

        if not zip_path.exists():
            msg = "ZIP file does not exist"
            file_record["error"] = msg
            error_rows.append({"payment_year": year, "scope": "ZIP", "item": str(zip_path), "error": msg})
            file_rows.append(file_record)
            continue

        try:
            file_record["zip_sha256"] = sha256_path(zip_path)

            with zipfile.ZipFile(zip_path) as zf:
                infos = [i for i in zf.infolist() if not i.is_dir()]
                file_record["zip_member_count"] = len(infos)

                recognized = []
                docs = []

                for info in infos:
                    member_class, disposition = classify_member(info.filename)
                    member_record = {
                        "payment_year": year,
                        "zip_path": str(zip_path),
                        "zip_sha256": file_record["zip_sha256"],
                        "zip_member": info.filename,
                        "member_basename": Path(info.filename).name,
                        "member_size_bytes": info.file_size,
                        "compressed_size_bytes": info.compress_size,
                        "member_crc32": f"{info.CRC:08x}",
                        "member_class": member_class,
                        "disposition": disposition,
                        "member_sha256": None,
                        "profile_status": "NOT_PROFILED",
                        "error": "",
                    }

                    if disposition in {"PROFILE", "DOCUMENT"}:
                        data = zf.read(info)
                        member_record["member_sha256"] = sha256_bytes(data)
                    else:
                        data = None

                    if disposition == "DOCUMENT" and member_class == "PLAN_PAYMENT_DOCUMENTATION":
                        docs.append(info.filename)
                        documentation_year_presence[year] += 1
                        member_record["profile_status"] = "DOCUMENTED"

                    elif disposition == "PROFILE":
                        recognized.append((info, member_class, data))
                        role = workbook_role(member_class)
                        role_year_presence[(year, role)] += 1
                        member_record["profile_status"] = "SELECTED"

                    else:
                        member_record["profile_status"] = "OUT_OF_SCOPE"

                    member_rows.append(member_record)

                file_record["recognized_partc_workbooks"] = len(recognized)
                file_record["documentation_pdfs"] = len(docs)

                if len(recognized) == 0:
                    msg = "ZIP contains zero recognized Part C workbooks"
                    file_record["error"] = msg
                    error_rows.append({"payment_year": year, "scope": "ZIP", "item": str(zip_path), "error": msg})
                    file_rows.append(file_record)
                    continue

                year_success = True

                for info, member_class, data in recognized:
                    role = workbook_role(member_class)
                    member_sha = sha256_bytes(data)

                    try:
                        sheets = read_excel_workbook_from_bytes(data, info.filename)
                    except Exception as exc:
                        year_success = False
                        msg = f"{type(exc).__name__}: {exc}"
                        error_rows.append({
                            "payment_year": year,
                            "scope": "WORKBOOK",
                            "item": info.filename,
                            "error": msg,
                        })
                        for mr in reversed(member_rows):
                            if mr["payment_year"] == year and mr["zip_member"] == info.filename:
                                mr["profile_status"] = "ERROR"
                                mr["error"] = msg
                                break
                        continue

                    if not sheets:
                        year_success = False
                        msg = "Workbook contains zero readable sheets"
                        error_rows.append({
                            "payment_year": year,
                            "scope": "WORKBOOK",
                            "item": info.filename,
                            "error": msg,
                        })
                        continue

                    for sheet_name, raw in sheets.items():
                        try:
                            header_idx, header_score = detect_header_row(raw)
                            headers = make_unique_headers(raw.iloc[header_idx].tolist()) if len(raw) else []
                            data_df = raw.iloc[header_idx + 1:].copy() if len(raw) else pd.DataFrame()
                            if headers:
                                data_df.columns = headers
                            data_df = data_df.dropna(axis=0, how="all").dropna(axis=1, how="all")

                            sheet_rows.append({
                                "payment_year": year,
                                "workbook_role": role,
                                "zip_path": str(zip_path),
                                "zip_member": info.filename,
                                "member_sha256": member_sha,
                                "sheet_name": sheet_name,
                                "raw_row_count": len(raw),
                                "raw_column_count": len(raw.columns),
                                "detected_header_row_excel": header_idx + 1,
                                "header_score": header_score,
                                "data_row_count": len(data_df),
                                "data_column_count": len(data_df.columns),
                                "detected_columns_json": json.dumps(
                                    [str(c) for c in data_df.columns],
                                    ensure_ascii=False,
                                ),
                                "profile_status": "PASS",
                                "error": "",
                            })

                            for pos, col in enumerate(data_df.columns, start=1):
                                column_rows.append(profile_column(
                                    data_df[col],
                                    year=year,
                                    role=role,
                                    zip_path=zip_path,
                                    member_name=info.filename,
                                    member_sha256=member_sha,
                                    sheet_name=sheet_name,
                                    header_row_zero_based=header_idx,
                                    column_position=pos,
                                    column_name=str(col),
                                ))

                        except Exception as exc:
                            year_success = False
                            msg = f"{type(exc).__name__}: {exc}"
                            error_rows.append({
                                "payment_year": year,
                                "scope": "SHEET",
                                "item": f"{info.filename} :: {sheet_name}",
                                "error": msg,
                            })
                            sheet_rows.append({
                                "payment_year": year,
                                "workbook_role": role,
                                "zip_path": str(zip_path),
                                "zip_member": info.filename,
                                "member_sha256": member_sha,
                                "sheet_name": sheet_name,
                                "raw_row_count": len(raw),
                                "raw_column_count": len(raw.columns),
                                "detected_header_row_excel": None,
                                "header_score": None,
                                "data_row_count": None,
                                "data_column_count": None,
                                "detected_columns_json": None,
                                "profile_status": "ERROR",
                                "error": msg,
                            })

                    for mr in reversed(member_rows):
                        if mr["payment_year"] == year and mr["zip_member"] == info.filename:
                            mr["profile_status"] = "PASS" if year_success else mr["profile_status"]
                            break

                expected_roles_ok = (
                    role_year_presence[(year, "COUNTY_LEVEL")] == 1
                    and role_year_presence[(year, "PLAN_LEVEL")] == 1
                )
                file_record["profile_status"] = "PASS" if year_success and expected_roles_ok else "FAIL"

                if year_success and expected_roles_ok:
                    profiled_years.add(year)
                elif not expected_roles_ok and not file_record["error"]:
                    file_record["error"] = (
                        "Expected exactly one COUNTY_LEVEL and one PLAN_LEVEL workbook; "
                        f"found COUNTY_LEVEL={role_year_presence[(year, 'COUNTY_LEVEL')]}, "
                        f"PLAN_LEVEL={role_year_presence[(year, 'PLAN_LEVEL')]}"
                    )
                    error_rows.append({
                        "payment_year": year,
                        "scope": "ZIP",
                        "item": str(zip_path),
                        "error": file_record["error"],
                    })

        except zipfile.BadZipFile as exc:
            msg = f"BadZipFile: {exc}"
            file_record["error"] = msg
            error_rows.append({"payment_year": year, "scope": "ZIP", "item": str(zip_path), "error": msg})
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            file_record["error"] = msg
            error_rows.append({"payment_year": year, "scope": "ZIP", "item": str(zip_path), "error": msg})

        file_rows.append(file_record)

    # Cross-year schema matrix: normalized field presence by role/year.
    schema_rows: list[dict[str, Any]] = []
    schema_groups: dict[tuple[str, str], dict[str, Any]] = {}

    for row in column_rows:
        key = (row["workbook_role"], row["normalized_column_name"])
        group = schema_groups.setdefault(key, {
            "workbook_role": row["workbook_role"],
            "normalized_column_name": row["normalized_column_name"],
            "observed_column_names": set(),
            "years": set(),
            "sheets": set(),
            "candidate_categories": set(),
        })
        group["observed_column_names"].add(row["column_name"])
        group["years"].add(int(row["payment_year"]))
        group["sheets"].add(row["sheet_name"])
        if row["candidate_categories"]:
            group["candidate_categories"].update(row["candidate_categories"].split("|"))

    for (_, _), group in sorted(schema_groups.items()):
        years_present = sorted(group["years"])
        rec = {
            "workbook_role": group["workbook_role"],
            "normalized_column_name": group["normalized_column_name"],
            "observed_column_names": " | ".join(sorted(group["observed_column_names"])),
            "sheets": " | ".join(sorted(group["sheets"])),
            "candidate_categories": "|".join(sorted(group["candidate_categories"])),
            "first_year": min(years_present) if years_present else None,
            "last_year": max(years_present) if years_present else None,
            "year_count": len(years_present),
        }
        for year in REQUIRED_YEARS:
            rec[f"CY{year}"] = 1 if year in group["years"] else 0
        schema_rows.append(rec)

    candidate_rows = [
        row for row in column_rows if row["candidate_categories"]
    ]

    # Write outputs.
    paths = {
        "file": output_dir / "cms_ma_partc_plan_payment_file_profile.csv",
        "member": output_dir / "cms_ma_partc_plan_payment_member_inventory.csv",
        "sheet": output_dir / "cms_ma_partc_plan_payment_sheet_profile.csv",
        "column": output_dir / "cms_ma_partc_plan_payment_column_profile.csv",
        "candidate": output_dir / "cms_ma_partc_plan_payment_candidate_fields.csv",
        "schema": output_dir / "cms_ma_partc_plan_payment_cross_year_schema.csv",
        "errors": output_dir / "cms_ma_partc_plan_payment_profile_errors.csv",
        "summary": output_dir / "cms_ma_partc_plan_payment_profile_summary.txt",
    }

    write_csv(file_rows, paths["file"])
    write_csv(member_rows, paths["member"])
    write_csv(sheet_rows, paths["sheet"])
    write_csv(column_rows, paths["column"])
    write_csv(candidate_rows, paths["candidate"])
    write_csv(schema_rows, paths["schema"])
    write_csv(error_rows, paths["errors"])

    total_partc = sum(
        1 for r in member_rows if r["member_class"] in {"PARTC_COUNTY_LEVEL", "PARTC_PLAN_LEVEL"}
    )
    years_with_exact_two = sum(
        1 for y in REQUIRED_YEARS
        if role_year_presence[(y, "COUNTY_LEVEL")] == 1
        and role_year_presence[(y, "PLAN_LEVEL")] == 1
    )
    years_with_docs = sum(1 for y in REQUIRED_YEARS if documentation_year_presence[y] >= 1)

    checks = [
        ("Required Plan Payment source rows", len(selected) == 11, f"{len(selected)}/11"),
        ("Missing required years", not missing_years, "NONE" if not missing_years else ",".join(map(str, missing_years))),
        ("Duplicate required years", not duplicate_years, "NONE" if not duplicate_years else ",".join(map(str, duplicate_years))),
        ("Recognized Part C workbooks", total_partc == EXPECTED_PARTC_TOTAL, f"{total_partc}/{EXPECTED_PARTC_TOTAL}"),
        ("Years with exactly two required Part C workbooks", years_with_exact_two == 11, f"{years_with_exact_two}/11"),
        ("Successfully profiled years", len(profiled_years) == 11, f"{len(profiled_years)}/11"),
        ("Years with Plan Payment documentation PDF", years_with_docs == 11, f"{years_with_docs}/11"),
        ("Read/profile errors", len(error_rows) == 0, str(len(error_rows))),
    ]
    overall_pass = all(ok for _, ok, _ in checks)

    lines = []
    add = lines.append
    add("=" * 88)
    add("CMS MEDICARE ADVANTAGE PART C — PLAN PAYMENT SOURCE PROFILE v0.2")
    add("=" * 88)
    add("")
    add("Scope: annual CMS Plan Payment ZIP packages, CY2014-CY2024.")
    add("Purpose: structurally profile the Part C county-level and plan-level workbooks")
    add("before any payment reconstruction.")
    add("No payment amount is reconstructed; no enrollment is imputed; no CMS source")
    add("artifact or database object is modified.")
    add("")
    add(f"Required years                         : {len(REQUIRED_YEARS)}")
    add(f"Manifest Plan Payment rows             : {len(selected)}")
    add(f"Successfully profiled years            : {len(profiled_years)}")
    add(f"Recognized Part C workbooks            : {total_partc}")
    add(f"Expected Part C workbooks              : {EXPECTED_PARTC_TOTAL}")
    add(f"Years with documentation PDF           : {years_with_docs}")
    add(f"ZIP members inventoried                : {len(member_rows)}")
    add(f"Sheets profiled                        : {len(sheet_rows)}")
    add(f"Columns profiled                       : {len(column_rows)}")
    add(f"Candidate semantic fields              : {len(candidate_rows)}")
    add(f"Cross-year schema fields               : {len(schema_rows)}")
    add(f"Profile/read errors                    : {len(error_rows)}")
    add("")
    add("VALIDATION CHECKS")
    add("-" * 88)
    for label, ok, detail in checks:
        add(f"{'PASS' if ok else 'FAIL'}  {label}: {detail}")
    add("")
    add(f"OVERALL STATUS: {'PASS' if overall_pass else 'FAIL'}")
    add("")
    add("PART C WORKBOOK PRESENCE BY YEAR")
    add("-" * 88)
    for year in REQUIRED_YEARS:
        add(
            f"CY{year}: COUNTY_LEVEL={role_year_presence[(year, 'COUNTY_LEVEL')]}; "
            f"PLAN_LEVEL={role_year_presence[(year, 'PLAN_LEVEL')]}; "
            f"DOCUMENTATION_PDF={documentation_year_presence[year]}"
        )
    add("")
    add("INTERPRETATION")
    add("-" * 88)
    add("PASS establishes that the 11 acquired annual Plan Payment ZIP packages contain")
    add("exactly one recognized Part C county-level workbook and one recognized Part C")
    add("plan-level workbook per year, that those workbooks can be read and structurally")
    add("profiled under a deterministic read-only procedure, and that annual Plan Payment")
    add("documentation PDFs are present.")
    add("")
    add("Candidate-field classification is lexical/diagnostic only. It does not establish")
    add("that a field is an actual CMS payment, a PMPM rate, a benchmark, a rebate, a")
    add("risk-adjusted amount, or an additive component.")
    add("")
    add("This profile does not establish payment reconstruction, complete Medicare Advantage")
    add("Part C expenditures, county allocation, Medicare state-ledger readiness, or final")
    add("fiscal-balance inclusion.")
    add("")
    add("NEXT EVIDENTIARY STEP")
    add("-" * 88)
    add("Review the cross-year schema and candidate-field outputs separately for COUNTY_LEVEL")
    add("and PLAN_LEVEL. Then use the preserved CMS Plan Payment Data Element documentation")
    add("to establish the exact meaning, units, grain, and additive/non-additive status of")
    add("every field needed for reconstruction before performing any multiplication.")
    add("")
    add("GOVERNING RULE")
    add("-" * 88)
    add("Never reconstruct a Medicare dollar until we can state exactly what each")
    add("multiplicand means.")
    add("")
    add("OUTPUTS")
    add("-" * 88)
    for path in paths.values():
        add(str(path))

    summary = "\n".join(lines) + "\n"
    paths["summary"].write_text(summary, encoding="utf-8")

    print()
    print(summary)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
