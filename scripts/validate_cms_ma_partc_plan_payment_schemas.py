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
    / "plan_payment_schema"
)

OUTPUT_MANIFEST = (
    OUTPUT_DIR
    / "cms_ma_partc_plan_payment_schema_manifest.csv"
)

OUTPUT_SUMMARY = (
    OUTPUT_DIR
    / "cms_ma_partc_plan_payment_schema_summary.txt"
)

EXPECTED_YEARS = [str(year) for year in range(2014, 2025)]
EXPECTED_YEAR_COUNT = len(EXPECTED_YEARS)


# ============================================================================
# Normalized semantic contract
# ============================================================================

NORMALIZED_FIELDS = (
    "county_code",
    "state_abbreviation",
    "county_name",
    "plan_type",
    "snp_plan_type",
    "average_part_c_risk_score",
    "average_ab_pmpm_payment",
    "average_rebate_pmpm_payment",
)

HEADER_ALIASES = {
    "county code": "county_code",
    "state abbreviation": "state_abbreviation",
    "county name": "county_name",
    "plan type": "plan_type",
    "snp plan type": "snp_plan_type",

    # Standard CMS wording.
    "average part c risk score": "average_part_c_risk_score",

    # CY2014 historical CMS wording.
    "average part risk score": "average_part_c_risk_score",

    # Standard wording plus CY2017 punctuation variant.
    "average ab pm/pm payment": "average_ab_pmpm_payment",
    "average a/b pm/pm payment": "average_ab_pmpm_payment",

    "average rebate pm/pm payment": "average_rebate_pmpm_payment",
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


def normalize_payment_year(value: Any) -> str:
    text = clean(value)

    if text.endswith(".0"):
        text = text[:-2]

    return text


def resolve_local_path(value: Any) -> Path:
    text = clean(value)

    if not text:
        raise ValueError("Blank local_path")

    path = Path(text)

    if path.is_absolute():
        return path

    return ROOT / path


def find_partc_county_workbooks(
    zf: zipfile.ZipFile,
) -> list[str]:
    candidates: list[str] = []

    for info in zf.infolist():
        if info.is_dir():
            continue

        name = Path(info.filename).name
        extension = Path(name).suffix.lower()

        if extension not in {".xls", ".xlsx"}:
            continue

        compact = re.sub(
            r"[^a-z0-9]+",
            "",
            name.casefold(),
        )

        if "partc" in compact and "county" in compact:
            candidates.append(info.filename)

    return candidates


def excel_engine(extension: str) -> str:
    if extension == ".xls":
        return "xlrd"

    if extension == ".xlsx":
        return "openpyxl"

    raise ValueError(
        f"Unsupported Excel extension: {extension}"
    )


# ============================================================================
# Header discovery / normalization
# ============================================================================

def locate_payment_header(
    payload: bytes,
    extension: str,
) -> tuple[str, int, pd.DataFrame]:
    """
    Locate the Part C county payment table semantically.

    Returns:
        sheet name
        zero-based physical header row
        complete sheet with header=None
    """
    engine = excel_engine(extension)

    book = pd.ExcelFile(
        io.BytesIO(payload),
        engine=engine,
    )

    candidates: list[
        tuple[int, str, int]
    ] = []

    core_signals = {
        "county code",
        "state abbreviation",
        "county name",
        "plan type",
        "snp plan type",
    }

    risk_signals = {
        "average part c risk score",
        "average part risk score",
    }

    ab_signals = {
        "average ab pm/pm payment",
        "average a/b pm/pm payment",
    }

    rebate_signals = {
        "average rebate pm/pm payment",
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
                header_key(value)
                for value in row.tolist()
                if header_key(value)
            }

            core_score = len(keys & core_signals)
            risk_score = int(
                bool(keys & risk_signals)
            )
            ab_score = int(
                bool(keys & ab_signals)
            )
            rebate_score = int(
                bool(keys & rebate_signals)
            )

            if (
                core_score >= 4
                and risk_score == 1
                and ab_score == 1
                and rebate_score == 1
            ):
                score = (
                    core_score
                    + risk_score
                    + ab_score
                    + rebate_score
                )

                candidates.append(
                    (score, sheet, int(idx))
                )

    if not candidates:
        raise RuntimeError(
            "Could not locate Part C county payment header"
        )

    candidates.sort(
        key=lambda x: (-x[0], x[1], x[2])
    )

    best_score = candidates[0][0]

    best = [
        x for x in candidates
        if x[0] == best_score
    ]

    if len(best) != 1:
        rendered = [
            f"{sheet!r}:row{idx + 1}"
            for _, sheet, idx in best
        ]

        raise RuntimeError(
            "Ambiguous Part C county payment header candidates: "
            + ", ".join(rendered)
        )

    _, sheet, header_index = best[0]

    full = pd.read_excel(
        io.BytesIO(payload),
        sheet_name=sheet,
        header=None,
        engine=engine,
    )

    return sheet, header_index, full


def normalize_header(
    raw_header: list[Any],
) -> tuple[
    dict[str, int],
    list[str],
    list[str],
]:
    """
    Return:
      normalized logical field -> physical zero-based column index
      unknown nonblank source headers
      duplicate normalized logical fields
    """
    mapping: dict[str, int] = {}
    unknown: list[str] = []
    duplicate_fields: list[str] = []

    for col_index, raw_value in enumerate(raw_header):
        key = header_key(raw_value)

        if not key:
            continue

        if key not in HEADER_ALIASES:
            unknown.append(clean(raw_value))
            continue

        logical = HEADER_ALIASES[key]

        if logical in mapping:
            duplicate_fields.append(logical)
            continue

        mapping[logical] = col_index

    return (
        mapping,
        unknown,
        sorted(set(duplicate_fields)),
    )


# ============================================================================
# Washington-content checks
# ============================================================================

def data_rows(
    frame: pd.DataFrame,
    header_index: int,
) -> pd.DataFrame:
    return frame.iloc[header_index + 1 :].copy()


def logical_series(
    frame: pd.DataFrame,
    mapping: dict[str, int],
    field: str,
) -> pd.Series:
    return frame.iloc[:, mapping[field]]


def numeric_profile(
    series: pd.Series,
) -> dict[str, Any]:
    source_nonblank = series.map(clean).ne("")
    numeric = pd.to_numeric(
        series,
        errors="coerce",
    )

    nonblank_count = int(source_nonblank.sum())
    numeric_count = int(
        numeric[source_nonblank].notna().sum()
    )

    nonnumeric_count = (
        nonblank_count - numeric_count
    )

    numeric_values = numeric[
        source_nonblank &
        numeric.notna()
    ]

    return {
        "nonblank": nonblank_count,
        "numeric": numeric_count,
        "nonnumeric": nonnumeric_count,
        "minimum": (
            float(numeric_values.min())
            if len(numeric_values)
            else None
        ),
        "maximum": (
            float(numeric_values.max())
            if len(numeric_values)
            else None
        ),
    }


def validate_wa_content(
    frame: pd.DataFrame,
    header_index: int,
    mapping: dict[str, int],
) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []

    data = data_rows(
        frame,
        header_index,
    )

    state = logical_series(
        data,
        mapping,
        "state_abbreviation",
    ).map(clean).str.upper()

    wa = data[state.eq("WA")].copy()

    if len(wa) == 0:
        notes.append(
            "No Washington rows found"
        )

        return {
            "wa_rows": 0,
            "wa_counties": 0,
            "wa_plan_types": 0,
            "wa_snp_types": 0,
            "risk_nonblank": 0,
            "risk_numeric": 0,
            "risk_nonnumeric": 0,
            "risk_min": "",
            "risk_max": "",
            "ab_nonblank": 0,
            "ab_numeric": 0,
            "ab_nonnumeric": 0,
            "rebate_nonblank": 0,
            "rebate_numeric": 0,
            "rebate_nonnumeric": 0,
        }, notes

    county_names = logical_series(
        wa,
        mapping,
        "county_name",
    ).map(clean)

    plan_types = logical_series(
        wa,
        mapping,
        "plan_type",
    ).map(clean)

    snp_types = logical_series(
        wa,
        mapping,
        "snp_plan_type",
    ).map(clean)

    if county_names.eq("").any():
        notes.append(
            "One or more WA rows have blank county_name"
        )

    if plan_types.eq("").any():
        notes.append(
            "One or more WA rows have blank plan_type"
        )

    risk = numeric_profile(
        logical_series(
            wa,
            mapping,
            "average_part_c_risk_score",
        )
    )

    ab = numeric_profile(
        logical_series(
            wa,
            mapping,
            "average_ab_pmpm_payment",
        )
    )

    rebate = numeric_profile(
        logical_series(
            wa,
            mapping,
            "average_rebate_pmpm_payment",
        )
    )

    # These are source-content checks, not economic-range assertions.
    # Every populated WA payment/risk cell must be numeric.
    if risk["nonblank"] == 0:
        notes.append(
            "WA risk-score field has no populated values"
        )

    if risk["nonnumeric"] != 0:
        notes.append(
            "WA risk-score field contains "
            f"{risk['nonnumeric']} nonnumeric populated values"
        )

    if ab["nonblank"] == 0:
        notes.append(
            "WA A/B PMPM field has no populated values"
        )

    if ab["nonnumeric"] != 0:
        notes.append(
            "WA A/B PMPM field contains "
            f"{ab['nonnumeric']} nonnumeric populated values"
        )

    if rebate["nonblank"] == 0:
        notes.append(
            "WA rebate PMPM field has no populated values"
        )

    if rebate["nonnumeric"] != 0:
        notes.append(
            "WA rebate PMPM field contains "
            f"{rebate['nonnumeric']} nonnumeric populated values"
        )

    # Risk score should be populated for every WA payment row based on
    # the observed source structure. Fail closed if that ceases to hold.
    if risk["nonblank"] != len(wa):
        notes.append(
            "WA risk-score population is incomplete: "
            f"{risk['nonblank']}/{len(wa)} rows populated"
        )

    if ab["nonblank"] != len(wa):
        notes.append(
            "WA A/B PMPM population is incomplete: "
            f"{ab['nonblank']}/{len(wa)} rows populated"
        )

    if rebate["nonblank"] != len(wa):
        notes.append(
            "WA rebate PMPM population is incomplete: "
            f"{rebate['nonblank']}/{len(wa)} rows populated"
        )

    profile = {
        "wa_rows": len(wa),
        "wa_counties": int(
            county_names[county_names.ne("")].nunique()
        ),
        "wa_plan_types": int(
            plan_types[plan_types.ne("")].nunique()
        ),
        "wa_snp_types": int(
            snp_types[snp_types.ne("")].nunique()
        ),
        "risk_nonblank": risk["nonblank"],
        "risk_numeric": risk["numeric"],
        "risk_nonnumeric": risk["nonnumeric"],
        "risk_min": risk["minimum"],
        "risk_max": risk["maximum"],
        "ab_nonblank": ab["nonblank"],
        "ab_numeric": ab["numeric"],
        "ab_nonnumeric": ab["nonnumeric"],
        "rebate_nonblank": rebate["nonblank"],
        "rebate_numeric": rebate["numeric"],
        "rebate_nonnumeric": rebate["nonnumeric"],
    }

    return profile, notes


# ============================================================================
# Per-year validation
# ============================================================================

def failure_row(
    year: str,
    path: Path,
    note: str,
) -> dict[str, Any]:
    return {
        "payment_year": year,
        "local_path": str(path),
        "status": "FAIL",
        "workbook_member": "",
        "sheet": "",
        "header_row": "",
        "physical_columns": "",
        "normalized_fields": "",
        "source_variation": "",
        "wa_rows": "",
        "wa_counties": "",
        "wa_plan_types": "",
        "wa_snp_types": "",
        "risk_nonblank": "",
        "risk_numeric": "",
        "risk_nonnumeric": "",
        "risk_min": "",
        "risk_max": "",
        "ab_nonblank": "",
        "ab_numeric": "",
        "ab_nonnumeric": "",
        "rebate_nonblank": "",
        "rebate_numeric": "",
        "rebate_nonnumeric": "",
        "notes": note,
    }


def validate_year(
    year: str,
    path: Path,
) -> dict[str, Any]:
    notes: list[str] = []
    source_variations: list[str] = []

    if not path.exists():
        return failure_row(
            year,
            path,
            "Canonical Plan Payment archive missing",
        )

    try:
        with zipfile.ZipFile(path) as zf:
            candidates = find_partc_county_workbooks(zf)

            if len(candidates) != 1:
                return failure_row(
                    year,
                    path,
                    "Expected exactly one Part C county workbook; "
                    f"found {len(candidates)}",
                )

            member = candidates[0]
            payload = zf.read(member)

    except Exception as exc:
        return failure_row(
            year,
            path,
            f"Archive/workbook read failure: {exc}",
        )

    extension = Path(member).suffix.lower()

    try:
        sheet, header_index, frame = locate_payment_header(
            payload,
            extension,
        )
    except Exception as exc:
        return failure_row(
            year,
            path,
            f"Header discovery failure: {exc}",
        )

    raw_header = frame.iloc[header_index].tolist()

    # Remove only trailing physically blank cells.
    while raw_header and not clean(raw_header[-1]):
        raw_header.pop()

    mapping, unknown, duplicates = normalize_header(
        raw_header
    )

    missing = sorted(
        set(NORMALIZED_FIELDS) - set(mapping)
    )

    unexpected = sorted(
        set(mapping) - set(NORMALIZED_FIELDS)
    )

    if unknown:
        notes.append(
            "Unknown nonblank headers: "
            + "|".join(unknown)
        )

    if duplicates:
        notes.append(
            "Duplicate normalized logical fields: "
            + "|".join(duplicates)
        )

    if missing:
        notes.append(
            "Missing normalized fields: "
            + "|".join(missing)
        )

    if unexpected:
        notes.append(
            "Unexpected normalized fields: "
            + "|".join(unexpected)
        )

    # Explicitly preserve known historical source variations.
    raw_keys = [
        header_key(x)
        for x in raw_header
        if header_key(x)
    ]

    if "average part risk score" in raw_keys:
        source_variations.append(
            "Average Part Risk Score -> "
            "average_part_c_risk_score"
        )

    if "average a/b pm/pm payment" in raw_keys:
        source_variations.append(
            "Average A/B PM/PM Payment -> "
            "average_ab_pmpm_payment"
        )

    # Confirm the CY2024 physical-order variation rather than depending on it.
    if year == "2024":
        risk_index = mapping.get(
            "average_part_c_risk_score"
        )

        ab_index = mapping.get(
            "average_ab_pmpm_payment"
        )

        if risk_index is not None and ab_index is not None:
            if ab_index < risk_index:
                source_variations.append(
                    "A/B PMPM precedes risk score physically; "
                    "header-based normalization used"
                )
            else:
                notes.append(
                    "CY2024 expected A/B-before-risk physical "
                    "ordering was not observed"
                )

    profile = {
        "wa_rows": "",
        "wa_counties": "",
        "wa_plan_types": "",
        "wa_snp_types": "",
        "risk_nonblank": "",
        "risk_numeric": "",
        "risk_nonnumeric": "",
        "risk_min": "",
        "risk_max": "",
        "ab_nonblank": "",
        "ab_numeric": "",
        "ab_nonnumeric": "",
        "rebate_nonblank": "",
        "rebate_numeric": "",
        "rebate_nonnumeric": "",
    }

    if not missing and not duplicates:
        try:
            profile, content_notes = validate_wa_content(
                frame,
                header_index,
                mapping,
            )

            notes.extend(content_notes)

        except Exception as exc:
            notes.append(
                f"Washington content validation failed: {exc}"
            )

    status = "PASS" if not notes else "FAIL"

    return {
        "payment_year": year,
        "local_path": str(path),
        "status": status,
        "workbook_member": member,
        "sheet": sheet,
        "header_row": header_index + 1,
        "physical_columns": len(raw_header),
        "normalized_fields": len(mapping),
        "source_variation": "; ".join(source_variations),
        **profile,
        "notes": "; ".join(notes),
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
        "CMS MEDICARE ADVANTAGE PART C PLAN PAYMENT SCHEMA VALIDATION"
    )
    lines.append("=" * 80)
    lines.append("")

    lines.append("SCOPE")
    lines.append("-" * 80)
    lines.append(
        "Payment years: CY2014 through CY2024 inclusive."
    )
    lines.append(
        "Source: canonical CMS Plan Payment Part C county-level workbooks."
    )
    lines.append(
        "Validation is read-only with respect to CMS source artifacts "
        "and performs no database writes."
    )
    lines.append("")

    lines.append("SOURCE UNIVERSE")
    lines.append("-" * 80)
    lines.append(
        f"Expected payment years : {EXPECTED_YEAR_COUNT}"
    )
    lines.append(
        f"Validation result rows : {len(results)}"
    )
    lines.append("")

    lines.append("VALIDATION STATUS")
    lines.append("-" * 80)

    counts = Counter(results["status"])

    lines.append(
        f"PASS    : {counts.get('PASS', 0):>2}"
    )
    lines.append(
        f"FAIL    : {counts.get('FAIL', 0):>2}"
    )
    lines.append("")

    lines.append("NORMALIZED CONTRACT")
    lines.append("-" * 80)

    for field in NORMALIZED_FIELDS:
        lines.append(f"  {field}")

    lines.append("")
    lines.append("YEAR-BY-YEAR WASHINGTON CONTENT")
    lines.append("-" * 80)

    for _, row in results.iterrows():
        lines.append(
            f"CY{row['payment_year']}: "
            f"{row['status']} | "
            f"WA rows={row['wa_rows']} | "
            f"counties={row['wa_counties']} | "
            f"plan types={row['wa_plan_types']} | "
            f"SNP types={row['wa_snp_types']} | "
            f"risk numeric={row['risk_numeric']}"
        )

    variations = results[
        results["source_variation"].map(clean).ne("")
    ]

    if not variations.empty:
        lines.append("")
        lines.append("EXPLICIT SOURCE-FORMAT VARIATIONS")
        lines.append("-" * 80)

        for _, row in variations.iterrows():
            lines.append(
                f"CY{row['payment_year']}: "
                f"{row['source_variation']}"
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
                f"CY{row['payment_year']}: "
                f"{row['notes']}"
            )

    lines.append("")
    lines.append("INTERPRETATION")
    lines.append("-" * 80)

    if (
        len(results) == EXPECTED_YEAR_COUNT
        and counts.get("FAIL", 0) == 0
    ):
        lines.append(
            "RESULT: PASS — all 11 canonical CMS Medicare Advantage "
            "Part C county Plan Payment sources map deterministically "
            "to one eight-field WCFFBP normalized semantic contract."
        )
    else:
        lines.append(
            "RESULT: FAIL — one or more Plan Payment sources do not "
            "map deterministically to the normalized semantic contract."
        )

    lines.append("")
    lines.append(
        "A Plan Payment schema PASS establishes deterministic structural "
        "interpretability of the annual payment source and Washington "
        "content. It does not establish monthly enrollment linkage, "
        "payment completeness, reconstructed expenditures, Medicare "
        "state-ledger readiness, or final fiscal-balance inclusion."
    )

    return "\n".join(lines) + "\n"


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    print("=" * 80)
    print(
        "CMS MEDICARE ADVANTAGE PART C PLAN PAYMENT SCHEMA VALIDATOR"
    )
    print("=" * 80)
    print()

    if not ACQUISITION_MANIFEST.exists():
        print(
            "ERROR: acquisition manifest not found:\n"
            f"  {ACQUISITION_MANIFEST}"
        )
        return 1

    manifest = pd.read_csv(
        ACQUISITION_MANIFEST,
        dtype=str,
    ).fillna("")

    required_columns = {
        "source_type",
        "payment_year",
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

    plan_payment = manifest[
        manifest["source_type"] == "PLAN_PAYMENT"
    ].copy()

    plan_payment["normalized_payment_year"] = (
        plan_payment["payment_year"]
        .map(normalize_payment_year)
    )

    print(
        f"Canonical Plan Payment rows: {len(plan_payment)}"
    )

    if len(plan_payment) != EXPECTED_YEAR_COUNT:
        print(
            f"ERROR: expected {EXPECTED_YEAR_COUNT} Plan Payment "
            f"rows; found {len(plan_payment)}"
        )
        return 1

    observed_years = sorted(
        plan_payment["normalized_payment_year"].tolist()
    )

    if observed_years != EXPECTED_YEARS:
        missing = sorted(
            set(EXPECTED_YEARS) - set(observed_years)
        )

        extra = sorted(
            set(observed_years) - set(EXPECTED_YEARS)
        )

        print(
            "ERROR: Plan Payment year universe does not match "
            "CY2014-CY2024."
        )
        print("Missing:", missing)
        print("Extra:", extra)
        return 1

    duplicate_years = (
        plan_payment[
            "normalized_payment_year"
        ]
        .value_counts()
    )

    duplicate_years = duplicate_years[
        duplicate_years != 1
    ]

    if not duplicate_years.empty:
        print(
            "ERROR: one or more payment years do not have "
            "exactly one canonical manifest row:"
        )
        print(duplicate_years.to_string())
        return 1

    nonpass = plan_payment[
        plan_payment["status"].str.upper() != "PASS"
    ]

    if not nonpass.empty:
        print(
            "ERROR: one or more Plan Payment acquisition rows "
            "are not PASS."
        )
        print(
            nonpass[
                [
                    "normalized_payment_year",
                    "status",
                ]
            ].to_string(index=False)
        )
        return 1

    print("Canonical Plan Payment source universe: PASS")
    print()

    results: list[dict[str, Any]] = []

    ordered = plan_payment.sort_values(
        "normalized_payment_year"
    )

    for i, (_, row) in enumerate(
        ordered.iterrows(),
        start=1,
    ):
        year = clean(
            row["normalized_payment_year"]
        )

        path = resolve_local_path(
            row["local_path"]
        )

        print(
            f"[{i:02d}/{EXPECTED_YEAR_COUNT}] "
            f"CY{year}",
            end=" ",
            flush=True,
        )

        result = validate_year(
            year,
            path,
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
        quoting=csv.QUOTE_MINIMAL,
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