from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


# ============================================================================
# Configuration
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
    / "source_validation"
)

VALIDATION_MANIFEST = OUTPUT_DIR / "cms_ma_partc_source_validation_manifest.csv"
SCHEMA_MANIFEST = OUTPUT_DIR / "cms_ma_partc_schema_family_manifest.csv"
SUMMARY_FILE = OUTPUT_DIR / "cms_ma_partc_source_validation_summary.txt"

EXPECTED_SOURCE_COUNTS = {
    "CPSC": 120,
    "SCC_SCP": 120,
    "SNP": 120,
    "PLAN_PAYMENT": 11,
}

EXPECTED_TOTAL = sum(EXPECTED_SOURCE_COUNTS.values())

DATA_EXTENSIONS = {".csv", ".xls", ".xlsx"}
DOCUMENTATION_EXTENSIONS = {".txt", ".pdf"}
ARCHIVE_EXTENSIONS = {".zip"}


# ============================================================================
# Helpers
# ============================================================================

def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def normalize_payment_year(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""

    match = re.fullmatch(r"(\d{4})(?:\.0+)?", text)
    if not match:
        return text

    return match.group(1)


def source_identity(row: pd.Series) -> str:
    period = normalize_text(row.get("period", ""))
    if period:
        return period

    return normalize_payment_year(row.get("payment_year", ""))


def resolve_local_path(value: object) -> Path:
    text = normalize_text(value)
    if not text:
        raise ValueError("Blank local_path")

    path = Path(text)

    if path.is_absolute():
        return path

    return ROOT / path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()


def clean_member_name(name: str) -> str:
    return name.replace("\\", "/")


def basename_lower(name: str) -> str:
    return Path(clean_member_name(name)).name.lower()


def extension(name: str) -> str:
    return Path(clean_member_name(name)).suffix.lower()


def normalize_schema_column(value: object) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"\s+", " ", text)
    return text


def schema_fingerprint(columns: Iterable[object]) -> str:
    normalized = [normalize_schema_column(x) for x in columns]
    payload = "\x1f".join(normalized).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def classify_member(name: str) -> str:
    lower = basename_lower(name)
    ext = extension(name)

    if ext in DOCUMENTATION_EXTENSIONS:
        return "DOCUMENTATION"

    if ext in ARCHIVE_EXTENSIONS:
        if "alt" in lower or "alternative" in lower:
            return "ALTERNATE_ARCHIVE"
        return "NESTED_ARCHIVE"

    if ext in DATA_EXTENSIONS:
        if "raw data" in lower or "raw_data" in lower:
            return "RAW_DATA"

        if "alt" in lower or "alternative" in lower:
            return "ALTERNATE_DATA"

        return "DATA"

    return "OTHER"


def open_csv_columns(zf: zipfile.ZipFile, member_name: str) -> list[str]:
    """
    Read only enough of a CSV member to identify its header.

    CMS historical files are commonly cp1252/latin1-compatible. Try a small
    deterministic encoding sequence rather than assuming UTF-8.
    """
    raw = zf.open(member_name)

    try:
        sample = raw.read(1024 * 1024)
    finally:
        raw.close()

    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            text = sample.decode(encoding)
            reader = csv.reader(io.StringIO(text))
            header = next(reader)
            return [normalize_text(x) for x in header]
        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"Could not decode CSV header for {member_name}: {last_error}"
    )


def open_excel_structure(
    zf: zipfile.ZipFile,
    member_name: str,
) -> tuple[list[str], list[str]]:
    """
    Return workbook sheet names plus a conservative first-row fingerprint.

    This intentionally avoids interpreting historical CMS workbook semantics.
    It inventories structure so later schema adapters can be evidence-driven.
    """
    payload = zf.read(member_name)
    ext = extension(member_name)

    if ext == ".xlsx":
        engine = "openpyxl"
    elif ext == ".xls":
        engine = "xlrd"
    else:
        raise ValueError(f"Unsupported workbook extension: {ext}")

    book = pd.ExcelFile(io.BytesIO(payload), engine=engine)
    sheets = [normalize_text(x) for x in book.sheet_names]

    first_sheet_columns: list[str] = []

    if sheets:
        try:
            preview = pd.read_excel(
                io.BytesIO(payload),
                sheet_name=sheets[0],
                header=None,
                nrows=25,
                engine=engine,
            )

            # Preserve a compact structural representation rather than
            # pretending the first physical row is always the true header.
            for _, row in preview.iterrows():
                values = [
                    normalize_text(x)
                    for x in row.tolist()
                    if normalize_text(x)
                ]
                if values:
                    first_sheet_columns = values
                    break
        except Exception:
            first_sheet_columns = []

    return sheets, first_sheet_columns


def expected_semantics(
    source_type: str,
    member_names: list[str],
) -> tuple[bool, list[str]]:
    """
    Source-family semantic checks.

    These checks intentionally use broad family characteristics. They should
    detect wrong-product artifacts without requiring one exact historical
    filename convention.
    """
    problems: list[str] = []
    lower_names = [basename_lower(x) for x in member_names]

    if source_type == "CPSC":
        csv_names = [x for x in lower_names if x.endswith(".csv")]

        has_contract = any("contract" in x for x in csv_names)
        has_enrollment = any("enrollment" in x for x in csv_names)

        if len(csv_names) < 2:
            problems.append("CPSC archive has fewer than two CSV members")

        if not has_contract:
            problems.append("CPSC archive lacks contract-info-like CSV")

        if not has_enrollment:
            problems.append("CPSC archive lacks enrollment-info-like CSV")

    elif source_type == "SCC_SCP":
        csv_names = [x for x in lower_names if x.endswith(".csv")]

        primary = [
            x
            for x in csv_names
            if "alt" not in x and "alternative" not in x
        ]

        if len(primary) != 1:
            problems.append(
                f"SCC/SCP expected one primary CSV; found {len(primary)}"
            )

        if primary:
            candidate = primary[0]
            if not any(
                token in candidate
                for token in ("scc", "scp", "statecounty", "state-county")
            ):
                problems.append(
                    "SCC/SCP primary CSV filename lacks expected family identity"
                )

    elif source_type == "SNP":
        workbook_names = [
            x
            for x in lower_names
            if x.endswith(".xls") or x.endswith(".xlsx")
        ]

        if not workbook_names:
            problems.append("SNP archive contains no Excel workbook")

        if not any("snp" in x for x in workbook_names):
            problems.append("SNP workbook filename lacks SNP family identity")

    elif source_type == "PLAN_PAYMENT":
        workbook_names = [
            x
            for x in lower_names
            if x.endswith(".xlsx") or x.endswith(".xls")
        ]

        if len(workbook_names) < 1:
            problems.append("Plan Payment archive contains no workbook")

        combined = " ".join(workbook_names)

        if not any(
            token in combined
            for token in ("partc", "part c", "payment", "pland")
        ):
            problems.append(
                "Plan Payment workbook names lack recognizable payment identity"
            )

    else:
        problems.append(f"Unknown source_type {source_type!r}")

    return not problems, problems


@dataclass
class ArtifactResult:
    source_type: str
    identity: str
    local_path: str
    status: str
    file_exists: str
    byte_match: str
    sha256_match: str
    zip_valid: str
    semantic_match: str
    member_count: int
    data_member_count: int
    documentation_member_count: int
    alternate_member_count: int
    member_extensions: str
    member_names: str
    schema_fingerprints: str
    notes: str


# ============================================================================
# Validation
# ============================================================================

def validate_artifact(row: pd.Series) -> ArtifactResult:
    source_type = normalize_text(row.get("source_type", ""))
    identity = source_identity(row)
    path = resolve_local_path(row.get("local_path", ""))

    notes: list[str] = []

    if not path.exists():
        return ArtifactResult(
            source_type=source_type,
            identity=identity,
            local_path=str(path),
            status="FAIL",
            file_exists="NO",
            byte_match="NO",
            sha256_match="NO",
            zip_valid="NO",
            semantic_match="NO",
            member_count=0,
            data_member_count=0,
            documentation_member_count=0,
            alternate_member_count=0,
            member_extensions="",
            member_names="",
            schema_fingerprints="",
            notes="Canonical acquisition-manifest artifact is missing",
        )

    expected_bytes = normalize_text(row.get("bytes", ""))
    actual_bytes = path.stat().st_size

    byte_match = "YES"
    if expected_bytes:
        try:
            byte_match = (
                "YES"
                if actual_bytes == int(float(expected_bytes))
                else "NO"
            )
        except ValueError:
            byte_match = "NO"
            notes.append(f"Invalid manifest byte count {expected_bytes!r}")

    expected_hash = normalize_text(row.get("sha256", "")).lower()
    actual_hash = sha256_file(path).lower()

    sha_match = "YES" if expected_hash == actual_hash else "NO"

    if not expected_hash:
        sha_match = "NO"
        notes.append("Acquisition manifest SHA-256 is blank")

    if not zipfile.is_zipfile(path):
        return ArtifactResult(
            source_type=source_type,
            identity=identity,
            local_path=str(path),
            status="FAIL",
            file_exists="YES",
            byte_match=byte_match,
            sha256_match=sha_match,
            zip_valid="NO",
            semantic_match="NO",
            member_count=0,
            data_member_count=0,
            documentation_member_count=0,
            alternate_member_count=0,
            member_extensions="",
            member_names="",
            schema_fingerprints="",
            notes="; ".join(notes + ["Artifact is not a valid ZIP"]),
        )

    member_names: list[str] = []
    fingerprints: list[str] = []
    classifications: list[str] = []

    try:
        with zipfile.ZipFile(path) as zf:
            bad_member = zf.testzip()

            if bad_member is not None:
                notes.append(f"ZIP CRC failure: {bad_member}")
                zip_valid = "NO"
            else:
                zip_valid = "YES"

            infos = [x for x in zf.infolist() if not x.is_dir()]
            member_names = [clean_member_name(x.filename) for x in infos]

            if not infos:
                notes.append("ZIP contains no file members")
                zip_valid = "NO"

            for info in infos:
                name = clean_member_name(info.filename)
                cls = classify_member(name)
                classifications.append(cls)

                if info.file_size <= 0:
                    notes.append(f"Zero-byte member: {name}")

                ext = extension(name)

                try:
                    if ext == ".csv":
                        columns = open_csv_columns(zf, info.filename)
                        fp = schema_fingerprint(columns)
                        fingerprints.append(
                            f"{Path(name).name}:CSV:{len(columns)}:{fp}"
                        )

                    elif ext in {".xls", ".xlsx"}:
                        sheets, first_row = open_excel_structure(
                            zf,
                            info.filename,
                        )

                        fp = schema_fingerprint(
                            list(sheets) + ["--FIRSTROW--"] + list(first_row)
                        )

                        fingerprints.append(
                            f"{Path(name).name}:"
                            f"{ext[1:].upper()}:"
                            f"{len(sheets)}:{fp}"
                        )

                    elif ext == ".zip":
                        payload = zf.read(info.filename)

                        with zipfile.ZipFile(io.BytesIO(payload)) as nested:
                            nested_bad = nested.testzip()
                            nested_files = [
                                x
                                for x in nested.infolist()
                                if not x.is_dir()
                            ]

                            if nested_bad is not None:
                                notes.append(
                                    f"Nested ZIP CRC failure "
                                    f"{name}: {nested_bad}"
                                )

                            fingerprints.append(
                                f"{Path(name).name}:NESTED_ZIP:"
                                f"{len(nested_files)}"
                            )

                except Exception as exc:
                    notes.append(
                        f"Structure inspection failed for {name}: "
                        f"{type(exc).__name__}: {exc}"
                    )

    except Exception as exc:
        return ArtifactResult(
            source_type=source_type,
            identity=identity,
            local_path=str(path),
            status="FAIL",
            file_exists="YES",
            byte_match=byte_match,
            sha256_match=sha_match,
            zip_valid="NO",
            semantic_match="NO",
            member_count=0,
            data_member_count=0,
            documentation_member_count=0,
            alternate_member_count=0,
            member_extensions="",
            member_names="",
            schema_fingerprints="",
            notes="; ".join(
                notes
                + [
                    f"ZIP inspection failed: "
                    f"{type(exc).__name__}: {exc}"
                ]
            ),
        )

    semantic_ok, semantic_problems = expected_semantics(
        source_type,
        member_names,
    )

    if semantic_problems:
        notes.extend(semantic_problems)

    data_count = sum(
        x in {"DATA", "RAW_DATA"}
        for x in classifications
    )

    documentation_count = classifications.count("DOCUMENTATION")

    alternate_count = sum(
        x in {"ALTERNATE_ARCHIVE", "ALTERNATE_DATA"}
        for x in classifications
    )

    # ---------------------------------------------------------------------
    # Status logic
    #
    # FAIL:
    #   canonical identity/integrity or source-family semantics failed.
    #
    # REVIEW:
    #   integrity and semantics passed, but a structural inspection warning
    #   occurred. This prevents unusual historical packaging from silently
    #   becoming PASS.
    #
    # PASS:
    #   canonical artifact matches acquisition provenance, ZIP is sound,
    #   family semantics pass, and structural inspection produced no warning.
    # ---------------------------------------------------------------------

    hard_fail = (
        byte_match != "YES"
        or sha_match != "YES"
        or zip_valid != "YES"
        or not semantic_ok
    )

    if hard_fail:
        status = "FAIL"
    elif notes:
        status = "REVIEW"
    else:
        status = "PASS"

    extensions = sorted(extension(x) for x in member_names)

    return ArtifactResult(
        source_type=source_type,
        identity=identity,
        local_path=str(path),
        status=status,
        file_exists="YES",
        byte_match=byte_match,
        sha256_match=sha_match,
        zip_valid=zip_valid,
        semantic_match="YES" if semantic_ok else "NO",
        member_count=len(member_names),
        data_member_count=data_count,
        documentation_member_count=documentation_count,
        alternate_member_count=alternate_count,
        member_extensions="|".join(extensions),
        member_names="|".join(member_names),
        schema_fingerprints="|".join(fingerprints),
        notes="; ".join(notes),
    )


# ============================================================================
# Schema-family summary
# ============================================================================

def build_schema_manifest(results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    grouped: defaultdict[
        tuple[str, int, str, str],
        list[str],
    ] = defaultdict(list)

    for _, row in results.iterrows():
        key = (
            normalize_text(row["source_type"]),
            int(row["member_count"]),
            normalize_text(row["member_extensions"]),
            normalize_text(row["schema_fingerprints"]),
        )

        grouped[key].append(normalize_text(row["identity"]))

    for family_number, (key, identities) in enumerate(
        sorted(grouped.items()),
        start=1,
    ):
        source_type, member_count, extensions, fingerprints = key

        rows.append(
            {
                "schema_family_id": f"SF-{family_number:03d}",
                "source_type": source_type,
                "artifact_count": len(identities),
                "member_count": member_count,
                "member_extensions": extensions,
                "schema_fingerprints": fingerprints,
                "first_identity": identities[0] if identities else "",
                "last_identity": identities[-1] if identities else "",
                "identities": "|".join(identities),
            }
        )

    return pd.DataFrame(rows)


# ============================================================================
# Summary
# ============================================================================

def build_summary(
    acquisition: pd.DataFrame,
    results: pd.DataFrame,
    schemas: pd.DataFrame,
) -> str:
    lines: list[str] = []

    lines.append("=" * 80)
    lines.append("CMS MEDICARE ADVANTAGE PART C SOURCE ARCHIVE VALIDATION")
    lines.append("=" * 80)
    lines.append("")
    lines.append(
        "Validation universe: canonical acquisition-manifest artifacts only."
    )
    lines.append(
        "Noncanonical ZIPs present elsewhere on disk are outside this "
        "validation universe."
    )
    lines.append(
        "This validator is read-only with respect to CMS source artifacts "
        "and performs no database writes."
    )
    lines.append("")

    lines.append("SOURCE UNIVERSE")
    lines.append("-" * 80)
    lines.append(f"Expected canonical artifacts : {EXPECTED_TOTAL}")
    lines.append(f"Manifest rows                : {len(acquisition)}")
    lines.append(f"Validation result rows       : {len(results)}")
    lines.append("")

    for source_type, expected in EXPECTED_SOURCE_COUNTS.items():
        observed = int(
            (results["source_type"] == source_type).sum()
        )
        lines.append(
            f"{source_type:<14} expected {expected:>3} | "
            f"observed {observed:>3}"
        )

    lines.append("")
    lines.append("VALIDATION STATUS")
    lines.append("-" * 80)

    status_counts = Counter(results["status"])

    for status in ("PASS", "REVIEW", "FAIL"):
        lines.append(
            f"{status:<8}: {status_counts.get(status, 0):>3}"
        )

    lines.append("")
    lines.append("INTEGRITY")
    lines.append("-" * 80)

    for column, label in (
        ("file_exists", "File exists"),
        ("byte_match", "Byte count matches"),
        ("sha256_match", "SHA-256 matches"),
        ("zip_valid", "ZIP integrity passes"),
        ("semantic_match", "Source-family semantics pass"),
    ):
        yes = int((results[column] == "YES").sum())
        lines.append(f"{label:<30}: {yes:>3}/{len(results)}")

    lines.append("")
    lines.append("STRUCTURAL FAMILIES")
    lines.append("-" * 80)
    lines.append(f"Distinct schema families: {len(schemas)}")

    for source_type in EXPECTED_SOURCE_COUNTS:
        count = int(
            (schemas["source_type"] == source_type).sum()
        )
        lines.append(
            f"{source_type:<14}: {count:>3} schema families"
        )

    review = results[results["status"] == "REVIEW"]
    fail = results[results["status"] == "FAIL"]

    if not review.empty:
        lines.append("")
        lines.append("REVIEW REQUIRED")
        lines.append("-" * 80)

        for _, row in review.iterrows():
            lines.append(
                f"{row['source_type']} {row['identity']}: "
                f"{row['notes']}"
            )

    if not fail.empty:
        lines.append("")
        lines.append("FAILURES")
        lines.append("-" * 80)

        for _, row in fail.iterrows():
            lines.append(
                f"{row['source_type']} {row['identity']}: "
                f"{row['notes']}"
            )

    lines.append("")
    lines.append("INTERPRETATION")
    lines.append("-" * 80)

    if (
        len(acquisition) == EXPECTED_TOTAL
        and len(results) == EXPECTED_TOTAL
        and status_counts.get("FAIL", 0) == 0
        and status_counts.get("REVIEW", 0) == 0
    ):
        lines.append(
            "RESULT: PASS — all 371 canonical CMS Medicare Advantage "
            "Part C source artifacts passed archive-level provenance, "
            "integrity, structural, and source-family semantic validation."
        )
    elif status_counts.get("FAIL", 0) == 0:
        lines.append(
            "RESULT: REVIEW — no hard failures were detected, but one or "
            "more artifacts require structural review before archive-level "
            "validation can be closed."
        )
    else:
        lines.append(
            "RESULT: FAIL — one or more canonical artifacts failed "
            "archive-level validation."
        )

    lines.append("")
    lines.append(
        "Archive-level PASS does not establish economic reconstruction, "
        "payment completeness, statewide Medicare ledger readiness, or "
        "final fiscal-balance inclusion. Those are subsequent validation "
        "layers."
    )

    return "\n".join(lines) + "\n"


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    print("=" * 80)
    print("CMS MEDICARE ADVANTAGE PART C SOURCE ARCHIVE VALIDATOR")
    print("=" * 80)
    print()

    if not ACQUISITION_MANIFEST.exists():
        print(f"ERROR: acquisition manifest not found:")
        print(f"  {ACQUISITION_MANIFEST}")
        return 1

    acquisition = pd.read_csv(
        ACQUISITION_MANIFEST,
        dtype=str,
    ).fillna("")

    required_columns = {
        "source_type",
        "period",
        "payment_year",
        "local_path",
        "bytes",
        "sha256",
        "status",
    }

    missing_columns = sorted(
        required_columns - set(acquisition.columns)
    )

    if missing_columns:
        print(
            "ERROR: acquisition manifest missing required columns: "
            + ", ".join(missing_columns)
        )
        return 1

    print(f"Acquisition manifest rows: {len(acquisition)}")

    duplicate_keys = (
        acquisition.assign(
            _identity=acquisition.apply(source_identity, axis=1)
        )
        .groupby(["source_type", "_identity"])
        .size()
    )

    duplicate_keys = duplicate_keys[duplicate_keys > 1]

    if not duplicate_keys.empty:
        print("ERROR: duplicate canonical source identities:")
        print(duplicate_keys.to_string())
        return 1

    if len(acquisition) != EXPECTED_TOTAL:
        print(
            f"ERROR: expected {EXPECTED_TOTAL} canonical artifacts; "
            f"found {len(acquisition)}"
        )
        return 1

    for source_type, expected in EXPECTED_SOURCE_COUNTS.items():
        observed = int(
            (acquisition["source_type"] == source_type).sum()
        )

        if observed != expected:
            print(
                f"ERROR: {source_type} expected {expected}; "
                f"found {observed}"
            )
            return 1

    acquisition_failures = acquisition[
        acquisition["status"].str.upper() != "PASS"
    ]

    if not acquisition_failures.empty:
        print(
            "ERROR: acquisition manifest contains non-PASS canonical rows."
        )
        print(
            acquisition_failures[
                ["source_type", "period", "payment_year", "status"]
            ].to_string(index=False)
        )
        return 1

    print("Canonical source universe: PASS")
    print()

    results: list[ArtifactResult] = []

    for i, (_, row) in enumerate(acquisition.iterrows(), start=1):
        source_type = normalize_text(row["source_type"])
        identity = source_identity(row)

        print(
            f"[{i:03d}/{EXPECTED_TOTAL}] "
            f"{source_type:<12} {identity:<10}",
            end=" ",
            flush=True,
        )

        result = validate_artifact(row)
        results.append(result)

        print(result.status)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result_df = pd.DataFrame(
        [x.__dict__ for x in results]
    )

    result_df.to_csv(
        VALIDATION_MANIFEST,
        index=False,
        encoding="utf-8",
    )

    schema_df = build_schema_manifest(result_df)

    schema_df.to_csv(
        SCHEMA_MANIFEST,
        index=False,
        encoding="utf-8",
    )

    summary = build_summary(
        acquisition,
        result_df,
        schema_df,
    )

    SUMMARY_FILE.write_text(
        summary,
        encoding="utf-8",
    )

    print()
    print(summary)

    print("OUTPUTS")
    print("-" * 80)
    print(VALIDATION_MANIFEST)
    print(SCHEMA_MANIFEST)
    print(SUMMARY_FILE)

    fail_count = int((result_df["status"] == "FAIL").sum())
    review_count = int((result_df["status"] == "REVIEW").sum())

    if fail_count:
        return 2

    if review_count:
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())