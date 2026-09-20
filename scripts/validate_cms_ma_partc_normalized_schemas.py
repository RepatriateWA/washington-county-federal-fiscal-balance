from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================================
# Paths / constants
# ============================================================================

ROOT = Path(__file__).resolve().parents[1]

ACQUISITION_MANIFEST = (
    ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_advantage"
    / "validation"
    / "source_acquisition"
    / "cms_ma_partc_source_acquisition_manifest.csv"
)

OUTPUT_DIR = (
    ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_advantage"
    / "validation"
    / "normalized_schema"
)

OUTPUT_MANIFEST = (
    OUTPUT_DIR / "cms_ma_partc_normalized_schema_manifest.csv"
)

OUTPUT_SUMMARY = (
    OUTPUT_DIR / "cms_ma_partc_normalized_schema_summary.txt"
)

EXPECTED_MONTHS = 120

EXPECTED_SOURCE_COUNTS = {
    "CPSC": EXPECTED_MONTHS,
    "SCC_SCP": EXPECTED_MONTHS,
    "SNP": EXPECTED_MONTHS,
}

EXPECTED_ARTIFACTS = sum(EXPECTED_SOURCE_COUNTS.values())

EXPECTED_PERIODS = pd.period_range(
    "2014-10",
    "2024-09",
    freq="M",
).astype(str).tolist()


# ============================================================================
# Canonical normalized contracts
# ============================================================================

CPSC_CONTRACT_FIELDS = (
    "contract_id",
    "plan_id",
    "organization_type",
    "plan_type",
    "offers_part_d",
    "snp_plan",
    "eghp",
    "organization_name",
    "organization_marketing_name",
    "plan_name",
    "parent_organization",
    "contract_effective_date",
)

CPSC_ENROLLMENT_FIELDS = (
    "contract_number",
    "plan_id",
    "ssa_state_county_code",
    "fips_state_county_code",
    "state",
    "county",
    "enrollment",
)

SCC_SCP_FIELDS = (
    "county",
    "state",
    "contract_id",
    "organization_name",
    "organization_type",
    "plan_type",
    "ssa_code",
    "fips_code",
    "enrolled",
)

SNP_FIELDS = (
    "contract_number",
    "contract_name",
    "organization_type",
    "plan_id",
    "segment_id",
    "plan_name",
    "plan_type",
    "geographic_name",
    "states",
    "enrollment",
    "snp_type",
    "specialty_diseases",
    "integration_status",
    "applicable_integrated_plan",
)


# ============================================================================
# Explicit source-header aliases
# ============================================================================

CPSC_CONTRACT_ALIASES = {
    "contract id": "contract_id",
    "plan id": "plan_id",
    "organization type": "organization_type",
    "plan type": "plan_type",
    "offers part d": "offers_part_d",
    "snp plan": "snp_plan",
    "eghp": "eghp",
    "organization name": "organization_name",
    "organization marketing name": "organization_marketing_name",
    "plan name": "plan_name",
    "parent organization": "parent_organization",
    "contract effective date": "contract_effective_date",
}

CPSC_ENROLLMENT_ALIASES = {
    "contract number": "contract_number",
    "plan id": "plan_id",
    "ssa state county code": "ssa_state_county_code",
    "fips state county code": "fips_state_county_code",
    "state": "state",
    "county": "county",
    "enrollment": "enrollment",
}

SCC_SCP_ALIASES = {
    "county": "county",
    "state": "state",
    "contract id": "contract_id",
    "organization name": "organization_name",
    "organization type": "organization_type",
    "plan type": "plan_type",
    "ssa code": "ssa_code",
    "fips code": "fips_code",
    "enrolled": "enrolled",
}

SNP_ALIASES = {
    "contract number": "contract_number",
    "contract name": "contract_name",
    "organization type": "organization_type",
    "plan id": "plan_id",
    "segment id": "segment_id",
    "segment_id": "segment_id",
    "plan name": "plan_name",
    "plan type": "plan_type",
    "plan geographic name": "geographic_name",
    "geographic name": "geographic_name",
    "state(s)": "states",
    "plan enrollment": "enrollment",
    "enrollment": "enrollment",
    "special needs plan type": "snp_type",
    "specialty diseases": "specialty_diseases",
    "integration status": "integration_status",
    "applicable integrated plan": "applicable_integrated_plan",
}


# ============================================================================
# Generic helpers
# ============================================================================

def clean(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return " ".join(str(value).strip().split())


def header_key(value: Any) -> str:
    text = clean(value)
    text = text.replace("\ufeff", "")
    return text.casefold()


def resolve_local_path(value: Any) -> Path:
    text = clean(value)

    if not text:
        raise ValueError("Blank local_path")

    path = Path(text)

    if path.is_absolute():
        return path

    return ROOT / path


def read_csv_header(
    zf: zipfile.ZipFile,
    member_name: str,
) -> list[str]:
    with zf.open(member_name) as f:
        sample = f.read(1024 * 1024)

    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            text = sample.decode(encoding)
            reader = csv.reader(io.StringIO(text))
            return [clean(x) for x in next(reader)]
        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"Could not decode CSV header {member_name}: {last_error}"
    )


def normalize_header(
    source_header: list[str],
    aliases: dict[str, str],
) -> tuple[list[str], list[str], list[str]]:
    """
    Returns:
      normalized fields
      unknown nonblank source headers
      duplicate normalized fields
    """
    normalized: list[str] = []
    unknown: list[str] = []

    for raw in source_header:
        key = header_key(raw)

        if not key:
            continue

        if key not in aliases:
            unknown.append(clean(raw))
            continue

        normalized.append(aliases[key])

    counts = Counter(normalized)

    duplicates = sorted(
        field
        for field, count in counts.items()
        if count > 1
    )

    return normalized, unknown, duplicates


def contract_check(
    normalized: list[str],
    expected: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    observed = set(normalized)
    required = set(expected)

    missing = sorted(required - observed)
    unexpected = sorted(observed - required)

    return missing, unexpected


def first_nonblank_header_candidate(
    frame: pd.DataFrame,
) -> tuple[int, list[str]] | None:
    for idx, row in frame.iterrows():
        values = [clean(x) for x in row.tolist()]

        if any(values):
            return int(idx), values

    return None


# ============================================================================
# CPSC validation
# ============================================================================

def validate_cpsc(
    period: str,
    path: Path,
) -> dict[str, Any]:
    notes: list[str] = []

    with zipfile.ZipFile(path) as zf:
        csv_members = [
            x.filename
            for x in zf.infolist()
            if not x.is_dir()
            and Path(x.filename).suffix.lower() == ".csv"
        ]

        contract_candidates = [
            x for x in csv_members
            if "contract" in Path(x).name.casefold()
        ]

        enrollment_candidates = [
            x for x in csv_members
            if "enrollment" in Path(x).name.casefold()
        ]

        if len(contract_candidates) != 1:
            return failure_row(
                "CPSC",
                period,
                path,
                "Expected exactly one contract-info CSV; "
                f"found {len(contract_candidates)}",
            )

        if len(enrollment_candidates) != 1:
            return failure_row(
                "CPSC",
                period,
                path,
                "Expected exactly one enrollment-info CSV; "
                f"found {len(enrollment_candidates)}",
            )

        contract_header = read_csv_header(
            zf,
            contract_candidates[0],
        )

        enrollment_header = read_csv_header(
            zf,
            enrollment_candidates[0],
        )

    contract_norm, contract_unknown, contract_dupes = normalize_header(
        contract_header,
        CPSC_CONTRACT_ALIASES,
    )

    enrollment_norm, enrollment_unknown, enrollment_dupes = normalize_header(
        enrollment_header,
        CPSC_ENROLLMENT_ALIASES,
    )

    contract_missing, contract_unexpected = contract_check(
        contract_norm,
        CPSC_CONTRACT_FIELDS,
    )

    enrollment_missing, enrollment_unexpected = contract_check(
        enrollment_norm,
        CPSC_ENROLLMENT_FIELDS,
    )

    if contract_unknown:
        notes.append(
            "Unknown contract headers: "
            + "|".join(contract_unknown)
        )

    if enrollment_unknown:
        notes.append(
            "Unknown enrollment headers: "
            + "|".join(enrollment_unknown)
        )

    if contract_dupes:
        notes.append(
            "Duplicate normalized contract fields: "
            + "|".join(contract_dupes)
        )

    if enrollment_dupes:
        notes.append(
            "Duplicate normalized enrollment fields: "
            + "|".join(enrollment_dupes)
        )

    if contract_missing:
        notes.append(
            "Missing contract fields: "
            + "|".join(contract_missing)
        )

    if enrollment_missing:
        notes.append(
            "Missing enrollment fields: "
            + "|".join(enrollment_missing)
        )

    if contract_unexpected:
        notes.append(
            "Unexpected normalized contract fields: "
            + "|".join(contract_unexpected)
        )

    if enrollment_unexpected:
        notes.append(
            "Unexpected normalized enrollment fields: "
            + "|".join(enrollment_unexpected)
        )

    status = "PASS" if not notes else "FAIL"

    return {
        "source_type": "CPSC",
        "period": period,
        "local_path": str(path),
        "status": status,
        "logical_tables": 2,
        "supplied_logical_fields": (
            len(contract_norm) + len(enrollment_norm)
        ),
        "normalized_contract_fields": len(CPSC_CONTRACT_FIELDS),
        "structural_null_fields": "",
        "header_row": "1|1",
        "special_rule": "",
        "notes": "; ".join(notes),
    }


# ============================================================================
# SCC/SCP validation
# ============================================================================

def validate_scc_scp(
    period: str,
    path: Path,
) -> dict[str, Any]:
    notes: list[str] = []

    with zipfile.ZipFile(path) as zf:
        primary_csvs: list[str] = []

        for info in zf.infolist():
            if info.is_dir():
                continue

            if Path(info.filename).suffix.lower() != ".csv":
                continue

            name = Path(info.filename).name.casefold()

            if "alt" in name or "alternative" in name:
                continue

            primary_csvs.append(info.filename)

        if len(primary_csvs) != 1:
            return failure_row(
                "SCC_SCP",
                period,
                path,
                "Expected exactly one primary SCC/SCP CSV; "
                f"found {len(primary_csvs)}",
            )

        header = read_csv_header(
            zf,
            primary_csvs[0],
        )

    normalized, unknown, duplicates = normalize_header(
        header,
        SCC_SCP_ALIASES,
    )

    missing, unexpected = contract_check(
        normalized,
        SCC_SCP_FIELDS,
    )

    if unknown:
        notes.append(
            "Unknown headers: " + "|".join(unknown)
        )

    if duplicates:
        notes.append(
            "Duplicate normalized fields: "
            + "|".join(duplicates)
        )

    if missing:
        notes.append(
            "Missing fields: " + "|".join(missing)
        )

    if unexpected:
        notes.append(
            "Unexpected normalized fields: "
            + "|".join(unexpected)
        )

    status = "PASS" if not notes else "FAIL"

    return {
        "source_type": "SCC_SCP",
        "period": period,
        "local_path": str(path),
        "status": status,
        "logical_tables": 1,
        "supplied_logical_fields": len(normalized),
        "normalized_contract_fields": len(SCC_SCP_FIELDS),
        "structural_null_fields": "",
        "header_row": "1",
        "special_rule": (
            "Primary CSV only; explicitly named alternative "
            "artifact is noncanonical ancillary packaging."
            if period == "2018-10"
            else ""
        ),
        "notes": "; ".join(notes),
    }


# ============================================================================
# SNP helpers
# ============================================================================

def locate_snp_header(
    payload: bytes,
    extension: str,
) -> tuple[str, int, pd.DataFrame]:
    engine = "xlrd" if extension == ".xls" else "openpyxl"

    book = pd.ExcelFile(
        io.BytesIO(payload),
        engine=engine,
    )

    candidates: list[
        tuple[int, str, int, pd.DataFrame]
    ] = []

    targets = {
        "contract number",
        "plan id",
        "plan name",
        "plan type",
        "special needs plan type",
    }

    for sheet in book.sheet_names:
        preview = pd.read_excel(
            io.BytesIO(payload),
            sheet_name=sheet,
            header=None,
            nrows=40,
            engine=engine,
        )

        for idx, row in preview.iterrows():
            keys = {
                header_key(x)
                for x in row.tolist()
                if header_key(x)
            }

            score = len(keys & targets)

            if score >= 3:
                candidates.append(
                    (score, sheet, int(idx), preview)
                )

    if not candidates:
        raise RuntimeError(
            "Could not locate SNP logical header row"
        )

    candidates.sort(
        key=lambda x: (-x[0], x[1], x[2])
    )

    _, sheet, header_index, _ = candidates[0]

    full = pd.read_excel(
        io.BytesIO(payload),
        sheet_name=sheet,
        header=None,
        engine=engine,
    )

    return sheet, header_index, full


def choose_snp_report_workbook(
    zf: zipfile.ZipFile,
) -> str:
    workbooks = [
        x.filename
        for x in zf.infolist()
        if not x.is_dir()
        and Path(x.filename).suffix.lower() in {".xls", ".xlsx"}
    ]

    report = [
        x
        for x in workbooks
        if "raw data" not in Path(x).name.casefold()
    ]

    if len(report) != 1:
        raise RuntimeError(
            "Expected exactly one canonical SNP report workbook; "
            f"found {len(report)}: {report}"
        )

    return report[0]


def snp_data_rows(
    frame: pd.DataFrame,
    header_index: int,
) -> pd.DataFrame:
    """
    Restrict to apparent plan records.

    Contract Number and Plan ID are the first and fourth logical columns
    throughout the observed 2014-10 through 2024-09 source universe.
    """
    data = frame.iloc[header_index + 1 :].copy()

    if data.shape[1] < 4:
        return data.iloc[0:0].copy()

    contract = data.iloc[:, 0].map(clean)
    plan_id = data.iloc[:, 3].map(clean)

    return data[
        contract.ne("") &
        plan_id.ne("")
    ].copy()


def validate_snp_duplicate_2023_04(
    frame: pd.DataFrame,
    header_index: int,
) -> tuple[bool, str]:
    """
    Empirically established source anomaly:

    Physical column 14 = Applicable Integrated Plan
    Physical column 15 = blank
    Physical column 16 = duplicate Applicable Integrated Plan

    The duplicate must be identical row-for-row. Any deviation FAILS.
    """
    if frame.shape[1] < 16:
        return False, (
            "2023-04 duplicate-field rule expected at least "
            "16 physical columns"
        )

    data = snp_data_rows(
        frame,
        header_index,
    )

    if len(data) == 0:
        return False, "2023-04 contains zero detected SNP data rows"

    c14 = data.iloc[:, 13].map(clean)
    c15 = data.iloc[:, 14].map(clean)
    c16 = data.iloc[:, 15].map(clean)

    blank_separator = int(c15.ne("").sum())
    mismatches = int(c14.ne(c16).sum())

    if blank_separator != 0:
        return False, (
            "2023-04 physical column 15 is not entirely blank; "
            f"nonblank cells={blank_separator}"
        )

    if mismatches != 0:
        return False, (
            "2023-04 duplicate Applicable Integrated Plan "
            f"columns disagree in {mismatches} rows"
        )

    return True, (
        "Verified 2023-04 duplicate Applicable Integrated Plan "
        f"in {len(data):,}/{len(data):,} data rows; "
        "physical column 15 blank; duplicate collapsed to one "
        "logical field."
    )


# ============================================================================
# SNP validation
# ============================================================================

def validate_snp(
    period: str,
    path: Path,
) -> dict[str, Any]:
    notes: list[str] = []
    special_rule = ""

    try:
        with zipfile.ZipFile(path) as zf:
            member = choose_snp_report_workbook(zf)
            payload = zf.read(member)
    except Exception as exc:
        return failure_row(
            "SNP",
            period,
            path,
            f"SNP workbook selection failed: {exc}",
        )

    ext = Path(member).suffix.lower()

    try:
        sheet, header_index, frame = locate_snp_header(
            payload,
            ext,
        )
    except Exception as exc:
        return failure_row(
            "SNP",
            period,
            path,
            f"SNP header detection failed: {exc}",
        )

    raw_header = [
        clean(x)
        for x in frame.iloc[header_index].tolist()
    ]

    # Remove trailing physically blank cells only.
    while raw_header and not raw_header[-1]:
        raw_header.pop()

    # ---------------------------------------------------------------------
    # 2023-04 has a verified physical duplicate:
    #
    #   col 14 Applicable Integrated Plan
    #   col 15 blank
    #   col 16 Applicable Integrated Plan (identical data)
    #
    # Validate the invariant before collapsing the duplicate.
    # ---------------------------------------------------------------------

    if period == "2023-04":
        duplicate_ok, duplicate_note = (
            validate_snp_duplicate_2023_04(
                frame,
                header_index,
            )
        )

        if not duplicate_ok:
            notes.append(duplicate_note)
        else:
            special_rule = duplicate_note

        # Normalize only the first 14 physical fields after the
        # duplicate invariant has been explicitly tested.
        raw_header_for_normalization = raw_header[:14]

    else:
        raw_header_for_normalization = raw_header

    normalized, unknown, duplicates = normalize_header(
        raw_header_for_normalization,
        SNP_ALIASES,
    )

    observed = set(normalized)

    # Before July 2022 the two integration fields were not supplied.
    legacy_period = period < "2022-07"

    if legacy_period:
        expected_supplied = set(SNP_FIELDS[:-2])

        missing_supplied = sorted(
            expected_supplied - observed
        )

        unexpected_supplied = sorted(
            observed - expected_supplied
        )

        structural_nulls = (
            "integration_status|applicable_integrated_plan"
        )

        if "integration_status" in observed:
            notes.append(
                "Legacy SNP period unexpectedly supplies "
                "integration_status"
            )

        if "applicable_integrated_plan" in observed:
            notes.append(
                "Legacy SNP period unexpectedly supplies "
                "applicable_integrated_plan"
            )

    else:
        expected_supplied = set(SNP_FIELDS)

        missing_supplied = sorted(
            expected_supplied - observed
        )

        unexpected_supplied = sorted(
            observed - expected_supplied
        )

        structural_nulls = ""

    if unknown:
        notes.append(
            "Unknown headers: " + "|".join(unknown)
        )

    if duplicates:
        notes.append(
            "Duplicate normalized fields after source-specific "
            "normalization: "
            + "|".join(duplicates)
        )

    if missing_supplied:
        notes.append(
            "Missing supplied logical fields: "
            + "|".join(missing_supplied)
        )

    if unexpected_supplied:
        notes.append(
            "Unexpected supplied logical fields: "
            + "|".join(unexpected_supplied)
        )

    status = "PASS" if not notes else "FAIL"

    return {
        "source_type": "SNP",
        "period": period,
        "local_path": str(path),
        "status": status,
        "logical_tables": 1,
        "supplied_logical_fields": len(normalized),
        "normalized_contract_fields": len(SNP_FIELDS),
        "structural_null_fields": structural_nulls,
        "header_row": str(header_index + 1),
        "special_rule": special_rule,
        "notes": "; ".join(notes),
    }


# ============================================================================
# Result helpers
# ============================================================================

def failure_row(
    source_type: str,
    period: str,
    path: Path,
    note: str,
) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "period": period,
        "local_path": str(path),
        "status": "FAIL",
        "logical_tables": "",
        "supplied_logical_fields": "",
        "normalized_contract_fields": "",
        "structural_null_fields": "",
        "header_row": "",
        "special_rule": "",
        "notes": note,
    }


# ============================================================================
# Summary
# ============================================================================

def build_summary(
    results: pd.DataFrame,
) -> str:
    lines: list[str] = []

    lines.append("=" * 80)
    lines.append(
        "CMS MEDICARE ADVANTAGE PART C NORMALIZED MONTHLY SCHEMA VALIDATION"
    )
    lines.append("=" * 80)
    lines.append("")

    lines.append("SCOPE")
    lines.append("-" * 80)
    lines.append(
        "Period: October 2014 through September 2024 inclusive."
    )
    lines.append(
        "Sources: canonical CPSC, SCC/SCP, and SNP monthly artifacts."
    )
    lines.append(
        "Plan Payment annual artifacts are outside this validation layer."
    )
    lines.append(
        "Validation is read-only with respect to CMS source artifacts "
        "and performs no database writes."
    )
    lines.append("")

    lines.append("SOURCE UNIVERSE")
    lines.append("-" * 80)
    lines.append(
        f"Expected monthly artifacts : {EXPECTED_ARTIFACTS}"
    )
    lines.append(
        f"Validation result rows     : {len(results)}"
    )

    for source_type, expected in EXPECTED_SOURCE_COUNTS.items():
        observed = int(
            (results["source_type"] == source_type).sum()
        )

        lines.append(
            f"{source_type:<10} expected {expected:>3} | "
            f"observed {observed:>3}"
        )

    lines.append("")
    lines.append("VALIDATION STATUS")
    lines.append("-" * 80)

    counts = Counter(results["status"])

    for status in ("PASS", "FAIL"):
        lines.append(
            f"{status:<8}: {counts.get(status, 0):>3}"
        )

    lines.append("")
    lines.append("NORMALIZED CONTRACTS")
    lines.append("-" * 80)
    lines.append(
        "CPSC CONTRACT_INFO  : 12 logical fields"
    )
    lines.append(
        "CPSC ENROLLMENT_INFO:  7 logical fields"
    )
    lines.append(
        "SCC/SCP PRIMARY     :  9 logical fields"
    )
    lines.append(
        "SNP                 : 14-field normalized semantic contract"
    )
    lines.append(
        "  2014-10 through 2022-06: 12 source-supplied fields + "
        "2 structural NULL fields"
    )
    lines.append(
        "  2022-07 through 2024-09: 14 source-supplied logical fields"
    )

    # Header row distribution is useful evidence of source-format evolution.
    snp = results[
        results["source_type"] == "SNP"
    ]

    if not snp.empty:
        lines.append("")
        lines.append("SNP HEADER ROW DISTRIBUTION")
        lines.append("-" * 80)

        header_counts = Counter(
            clean(x)
            for x in snp["header_row"]
            if clean(x)
        )

        for header_row, count in sorted(
            header_counts.items(),
            key=lambda x: int(x[0]),
        ):
            lines.append(
                f"Physical header row {header_row:>2}: "
                f"{count:>3} months"
            )

    special = results[
        results["special_rule"].map(clean).ne("")
    ]

    if not special.empty:
        lines.append("")
        lines.append("EXPLICIT SOURCE-FORMAT EXCEPTIONS")
        lines.append("-" * 80)

        for _, row in special.iterrows():
            lines.append(
                f"{row['source_type']} {row['period']}: "
                f"{row['special_rule']}"
            )

    failures = results[
        results["status"] == "FAIL"
    ]

    if not failures.empty:
        lines.append("")
        lines.append("FAILURES")
        lines.append("-" * 80)

        for _, row in failures.iterrows():
            lines.append(
                f"{row['source_type']} {row['period']}: "
                f"{row['notes']}"
            )

    lines.append("")
    lines.append("INTERPRETATION")
    lines.append("-" * 80)

    if (
        len(results) == EXPECTED_ARTIFACTS
        and counts.get("FAIL", 0) == 0
    ):
        lines.append(
            "RESULT: PASS — all 360 canonical monthly CMS Medicare "
            "Advantage Part C source artifacts map deterministically "
            "to the defined WCFFBP normalized logical contracts."
        )
    else:
        lines.append(
            "RESULT: FAIL — one or more monthly source artifacts do "
            "not map deterministically to the defined normalized "
            "logical contracts."
        )

    lines.append("")
    lines.append(
        "A normalized-schema PASS establishes deterministic structural "
        "interpretability. It does not establish economic linkage, "
        "payment completeness, Medicare state-ledger readiness, or "
        "final fiscal-balance inclusion."
    )

    return "\n".join(lines) + "\n"


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    print("=" * 80)
    print(
        "CMS MEDICARE ADVANTAGE PART C NORMALIZED SCHEMA VALIDATOR"
    )
    print("=" * 80)
    print()

    if not ACQUISITION_MANIFEST.exists():
        print(
            f"ERROR: acquisition manifest not found:\n"
            f"  {ACQUISITION_MANIFEST}"
        )
        return 1

    manifest = pd.read_csv(
        ACQUISITION_MANIFEST,
        dtype=str,
    ).fillna("")

    required_columns = {
        "source_type",
        "period",
        "local_path",
        "status",
    }

    missing_columns = sorted(
        required_columns - set(manifest.columns)
    )

    if missing_columns:
        print(
            "ERROR: acquisition manifest missing columns: "
            + ", ".join(missing_columns)
        )
        return 1

    monthly = manifest[
        manifest["source_type"].isin(
            EXPECTED_SOURCE_COUNTS
        )
    ].copy()

    print(f"Monthly canonical manifest rows: {len(monthly)}")

    if len(monthly) != EXPECTED_ARTIFACTS:
        print(
            f"ERROR: expected {EXPECTED_ARTIFACTS} monthly "
            f"canonical artifacts; found {len(monthly)}"
        )
        return 1

    for source_type, expected in EXPECTED_SOURCE_COUNTS.items():
        subset = monthly[
            monthly["source_type"] == source_type
        ]

        if len(subset) != expected:
            print(
                f"ERROR: {source_type} expected {expected}; "
                f"found {len(subset)}"
            )
            return 1

        periods = sorted(
            clean(x)
            for x in subset["period"]
        )

        if periods != EXPECTED_PERIODS:
            missing = sorted(
                set(EXPECTED_PERIODS) - set(periods)
            )
            extra = sorted(
                set(periods) - set(EXPECTED_PERIODS)
            )

            print(
                f"ERROR: {source_type} monthly period universe "
                "does not match 2014-10 through 2024-09."
            )
            print("Missing:", missing)
            print("Extra:", extra)
            return 1

    nonpass = monthly[
        monthly["status"].str.upper() != "PASS"
    ]

    if not nonpass.empty:
        print(
            "ERROR: one or more monthly acquisition-manifest "
            "rows are not PASS."
        )
        print(
            nonpass[
                ["source_type", "period", "status"]
            ].to_string(index=False)
        )
        return 1

    print("Monthly canonical source universe: PASS")
    print()

    results: list[dict[str, Any]] = []

    ordered = monthly.sort_values(
        ["source_type", "period"]
    )

    for i, (_, row) in enumerate(
        ordered.iterrows(),
        start=1,
    ):
        source_type = clean(row["source_type"])
        period = clean(row["period"])
        path = resolve_local_path(row["local_path"])

        print(
            f"[{i:03d}/{EXPECTED_ARTIFACTS}] "
            f"{source_type:<10} {period}",
            end=" ",
            flush=True,
        )

        if not path.exists():
            result = failure_row(
                source_type,
                period,
                path,
                "Canonical artifact missing from filesystem",
            )

        elif source_type == "CPSC":
            result = validate_cpsc(
                period,
                path,
            )

        elif source_type == "SCC_SCP":
            result = validate_scc_scp(
                period,
                path,
            )

        elif source_type == "SNP":
            result = validate_snp(
                period,
                path,
            )

        else:
            result = failure_row(
                source_type,
                period,
                path,
                f"Unsupported source type {source_type!r}",
            )

        results.append(result)

        print(result["status"])

    result_df = pd.DataFrame(results)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_df.to_csv(
        OUTPUT_MANIFEST,
        index=False,
        encoding="utf-8",
    )

    summary = build_summary(
        result_df,
    )

    OUTPUT_SUMMARY.write_text(
        summary,
        encoding="utf-8",
    )

    print()
    print(summary)

    print("OUTPUTS")
    print("-" * 80)
    print(OUTPUT_MANIFEST)
    print(OUTPUT_SUMMARY)

    failures = int(
        (result_df["status"] == "FAIL").sum()
    )

    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())