"""
WCFFBP
CMS MSSP Performance Results Profiler v0.1

Purpose
-------
Certify the structure of the official CMS Medicare Shared Savings
Program (MSSP) Performance Year Financial and Quality Results package
for performance periods 2015-2024, including the special 2019A /
2019 Off-cycle-1 period.

This is a READ-ONLY source profiler.

It DOES:
    - fingerprint the preserved outer CMS ZIP;
    - inventory every embedded CSV;
    - fingerprint each embedded CSV;
    - identify the performance period from the CMS archive path;
    - preserve the distinction between 2019 and 2019A;
    - capture row counts and column counts;
    - inventory headers;
    - identify candidate identity, geography, expenditure,
      benchmark, savings/loss, and advance-payment fields;
    - compare schemas across performance periods;
    - write validation evidence.

It DOES NOT:
    - extract or modify the CMS source package;
    - calculate Washington dollars;
    - infer Washington payment-dollar incidence;
    - infer economic additivity;
    - allocate payments geographically;
    - write to PostgreSQL;
    - authorize ledger inclusion.

Methodological principle
------------------------
Different CMS datasets and different fields within the MSSP PUF are
not additive by default.  This profiler establishes source structure
only.  Financial semantics and accounting treatment require a
separate certification gate.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "Performance Year Financial and Quality Results.zip"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "validation"
    / "performance_results_profile_v0_1"
)

MEMBER_INVENTORY_CSV = (
    OUTPUT_DIR
    / "cms_mssp_performance_results_member_inventory_v0_1.csv"
)

SCHEMA_CSV = (
    OUTPUT_DIR
    / "cms_mssp_performance_results_schema_v0_1.csv"
)

CANDIDATE_FIELDS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_performance_results_candidate_fields_v0_1.csv"
)

CROSS_YEAR_CSV = (
    OUTPUT_DIR
    / "cms_mssp_performance_results_cross_period_schema_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_performance_results_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_mssp_performance_results_report_v0_1.txt"
)


EXPECTED_PERIODS = [
    "2015",
    "2016",
    "2017",
    "2018",
    "2019",
    "2019A",
    "2020",
    "2021",
    "2022",
    "2023",
    "2024",
]


# These are discovery patterns, not semantic conclusions.
FIELD_PATTERNS = {
    "ACO_IDENTITY": [
        r"\baco\b",
        r"aco[_ ]?id",
        r"aco[_ ]?num",
        r"organization",
        r"name",
    ],
    "GEOGRAPHY_CANDIDATE": [
        r"state",
        r"county",
        r"zip",
        r"address",
        r"location",
        r"region",
    ],
    "BENEFICIARY_CANDIDATE": [
        r"benef",
        r"assign",
        r"person",
        r"enroll",
    ],
    "EXPENDITURE_CANDIDATE": [
        r"expend",
        r"expense",
        r"cost",
        r"payment",
        r"paid",
        r"pay",
    ],
    "BENCHMARK_CANDIDATE": [
        r"bench",
    ],
    "SAVINGS_LOSS_CANDIDATE": [
        r"sav",
        r"loss",
        r"earn",
        r"share",
    ],
    "ADVANCE_PAYMENT_CANDIDATE": [
        r"advance",
        r"aim",
        r"recoup",
        r"recover",
        r"prepay",
    ],
    "QUALITY_CANDIDATE": [
        r"quality",
        r"score",
    ],
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            h.update(block)

    return h.hexdigest().upper()


def detect_period(member_name: str) -> str:
    """
    Determine CMS performance period from the archive path/name.

    Important:
        2019_off-cycle_1 / 2019A must be tested before ordinary 2019.
    """
    text = member_name.replace("\\", "/").lower()

    if (
        "2019_off-cycle_1" in text
        or "2019_off_cycle_1" in text
        or "2019a" in text
    ):
        return "2019A"

    for year in range(2015, 2025):
        if re.search(
            rf"(?<!\d){year}(?!\d)",
            text,
        ):
            return str(year)

    return "UNRESOLVED"


def decode_csv_bytes(data: bytes) -> tuple[str, str]:
    """
    Decode without changing source bytes.

    utf-8-sig is preferred because it safely removes a UTF-8 BOM from
    the parsed text while the original bytes remain untouched.
    """
    attempts = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    ]

    last_error: Exception | None = None

    for encoding in attempts:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc

    raise RuntimeError(
        f"Could not decode CSV bytes: {last_error}"
    )


def parse_csv(
    data: bytes,
) -> tuple[list[str], int, str]:
    text, encoding = decode_csv_bytes(data)

    stream = io.StringIO(
        text,
        newline="",
    )

    reader = csv.reader(stream)

    try:
        header = next(reader)
    except StopIteration:
        return [], 0, encoding

    header = [
        "" if value is None else str(value)
        for value in header
    ]

    data_rows = 0

    for _ in reader:
        data_rows += 1

    return header, data_rows, encoding


def normalize_field(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        value.lower(),
    ).strip()


def classify_field(field_name: str) -> list[str]:
    normalized = normalize_field(field_name)
    classes: list[str] = []

    for category, patterns in FIELD_PATTERNS.items():
        if any(
            re.search(pattern, normalized)
            for pattern in patterns
        ):
            classes.append(category)

    return classes


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    errors: list[str] = []

    if not SOURCE_ZIP.exists():
        raise FileNotFoundError(
            f"Required CMS source package not found: {SOURCE_ZIP}"
        )

    outer_bytes = SOURCE_ZIP.stat().st_size
    outer_sha256 = sha256_file(SOURCE_ZIP)

    member_rows: list[dict] = []
    schema_rows: list[dict] = []
    candidate_rows: list[dict] = []

    period_headers: dict[str, list[str]] = {}
    period_row_counts: dict[str, int] = {}
    period_member_names: dict[str, str] = {}

    with zipfile.ZipFile(
        SOURCE_ZIP,
        "r",
    ) as archive:

        all_members = archive.infolist()

        csv_members = [
            info
            for info in all_members
            if (
                not info.is_dir()
                and info.filename.lower().endswith(".csv")
            )
        ]

        for info in csv_members:
            data = archive.read(info)

            period = detect_period(
                info.filename
            )

            try:
                (
                    header,
                    data_rows,
                    encoding,
                ) = parse_csv(data)

                parse_status = "PASS"

            except Exception as exc:
                header = []
                data_rows = 0
                encoding = ""
                parse_status = "FAIL"

                errors.append(
                    f"{info.filename}: "
                    f"CSV parse failure: {exc}"
                )

            member_sha256 = sha256_bytes(data)

            member_rows.append(
                {
                    "performance_period": period,
                    "member_name": info.filename,
                    "member_bytes": len(data),
                    "compressed_bytes": info.compress_size,
                    "sha256": member_sha256,
                    "encoding_used_for_parse": encoding,
                    "data_rows": data_rows,
                    "columns": len(header),
                    "parse_status": parse_status,
                }
            )

            if period == "UNRESOLVED":
                errors.append(
                    "Could not resolve performance period for "
                    f"{info.filename}"
                )

            elif period in period_headers:
                errors.append(
                    "More than one CSV resolved to performance "
                    f"period {period}"
                )

            else:
                period_headers[period] = header
                period_row_counts[period] = data_rows
                period_member_names[period] = info.filename

            for position, field_name in enumerate(
                header,
                start=1,
            ):
                classes = classify_field(
                    field_name
                )

                schema_rows.append(
                    {
                        "performance_period": period,
                        "column_position": position,
                        "field_name": field_name,
                        "normalized_field_name": normalize_field(
                            field_name
                        ),
                        "candidate_classes": ";".join(
                            classes
                        ),
                    }
                )

                for category in classes:
                    candidate_rows.append(
                        {
                            "performance_period": period,
                            "candidate_class": category,
                            "column_position": position,
                            "field_name": field_name,
                            "normalized_field_name": normalize_field(
                                field_name
                            ),
                        }
                    )

    # ------------------------------------------------------------
    # Cross-period schema inventory.
    # Exact field names are deliberately preserved.
    # ------------------------------------------------------------
    field_periods: dict[str, set[str]] = {}

    for period, header in period_headers.items():
        for field_name in header:
            field_periods.setdefault(
                field_name,
                set(),
            ).add(period)

    cross_year_rows: list[dict] = []

    for field_name in sorted(
        field_periods,
        key=lambda value: value.lower(),
    ):
        periods = field_periods[field_name]

        row = {
            "field_name": field_name,
            "period_count": len(periods),
            "all_11_periods": (
                "YES"
                if set(EXPECTED_PERIODS) == periods
                else "NO"
            ),
        }

        for period in EXPECTED_PERIODS:
            row[f"period_{period}"] = (
                "YES"
                if period in periods
                else "NO"
            )

        cross_year_rows.append(row)

    # ------------------------------------------------------------
    # Deterministic checks.
    # ------------------------------------------------------------
    observed_periods = sorted(
        period_headers.keys(),
        key=lambda value: (
            2019.5
            if value == "2019A"
            else int(value)
            if value.isdigit()
            else 9999
        ),
    )

    expected_set = set(EXPECTED_PERIODS)
    observed_set = set(observed_periods)

    duplicate_member_hashes = [
        sha
        for sha, count in Counter(
            row["sha256"]
            for row in member_rows
        ).items()
        if count > 1
    ]

    empty_members = [
        row
        for row in member_rows
        if row["member_bytes"] <= 0
    ]

    parse_failures = [
        row
        for row in member_rows
        if row["parse_status"] != "PASS"
    ]

    empty_headers = [
        period
        for period, header in period_headers.items()
        if not header
    ]

    zero_data_rows = [
        period
        for period, count in period_row_counts.items()
        if count <= 0
    ]

    checks: list[dict] = []

    def add_check(
        name: str,
        passed: bool,
        detail: str,
    ) -> None:
        checks.append(
            {
                "check": name,
                "status": (
                    "PASS"
                    if passed
                    else "FAIL"
                ),
                "detail": detail,
            }
        )

    add_check(
        "Source ZIP exists and is nonzero",
        outer_bytes > 0,
        f"{outer_bytes:,} bytes",
    )

    add_check(
        "Exactly 11 CSV members observed",
        len(member_rows) == 11,
        f"{len(member_rows)}/11",
    )

    add_check(
        "Expected performance-period universe resolved",
        observed_set == expected_set,
        (
            "Observed: "
            + ", ".join(observed_periods)
        ),
    )

    add_check(
        "Ordinary 2019 and 2019A remain distinct",
        (
            "2019" in observed_set
            and "2019A" in observed_set
            and period_member_names.get("2019")
            != period_member_names.get("2019A")
        ),
        (
            f"2019={period_member_names.get('2019', 'MISSING')} | "
            f"2019A={period_member_names.get('2019A', 'MISSING')}"
        ),
    )

    add_check(
        "All CSV members are nonzero",
        not empty_members,
        f"{len(empty_members)} zero-byte CSV members",
    )

    add_check(
        "All CSV members parse",
        not parse_failures,
        f"{len(parse_failures)} parse failures",
    )

    add_check(
        "All performance periods have headers",
        not empty_headers,
        (
            "Empty-header periods: "
            + (
                ", ".join(empty_headers)
                if empty_headers
                else "none"
            )
        ),
    )

    add_check(
        "All performance periods contain data rows",
        not zero_data_rows,
        (
            "Zero-row periods: "
            + (
                ", ".join(zero_data_rows)
                if zero_data_rows
                else "none"
            )
        ),
    )

    add_check(
        "Embedded CSV SHA-256 values are distinct",
        not duplicate_member_hashes,
        (
            f"{len(duplicate_member_hashes)} "
            "duplicate embedded hashes"
        ),
    )

    add_check(
        "No unresolved archive period",
        all(
            row["performance_period"]
            != "UNRESOLVED"
            for row in member_rows
        ),
        (
            f"{sum(row['performance_period'] == 'UNRESOLVED' for row in member_rows)} "
            "unresolved CSV members"
        ),
    )

    # This is filename provenance only.  We do not infer anything
    # about whether 2024 values are "more correct" than an earlier
    # vintage; we merely certify the observed revision label.
    file_2024 = period_member_names.get(
        "2024",
        "",
    )

    add_check(
        "2024 CMS revision label preserved",
        (
            "revised" in file_2024.lower()
            and "2026_07_17" in file_2024.lower()
        ),
        file_2024 or "MISSING",
    )

    # Candidate field discovery gates.
    candidate_classes_present = {
        row["candidate_class"]
        for row in candidate_rows
    }

    add_check(
        "ACO identity candidate fields discovered",
        "ACO_IDENTITY" in candidate_classes_present,
        (
            f"{sum(row['candidate_class'] == 'ACO_IDENTITY' for row in candidate_rows)} "
            "field-period observations"
        ),
    )

    add_check(
        "Savings/loss candidate fields discovered",
        "SAVINGS_LOSS_CANDIDATE"
        in candidate_classes_present,
        (
            f"{sum(row['candidate_class'] == 'SAVINGS_LOSS_CANDIDATE' for row in candidate_rows)} "
            "field-period observations"
        ),
    )

    add_check(
        "Expenditure/payment candidate fields discovered",
        "EXPENDITURE_CANDIDATE"
        in candidate_classes_present,
        (
            f"{sum(row['candidate_class'] == 'EXPENDITURE_CANDIDATE' for row in candidate_rows)} "
            "field-period observations"
        ),
    )

    # ------------------------------------------------------------
    # Write evidence.
    # ------------------------------------------------------------
    write_csv(
        MEMBER_INVENTORY_CSV,
        [
            "performance_period",
            "member_name",
            "member_bytes",
            "compressed_bytes",
            "sha256",
            "encoding_used_for_parse",
            "data_rows",
            "columns",
            "parse_status",
        ],
        sorted(
            member_rows,
            key=lambda row: (
                2019.5
                if row["performance_period"] == "2019A"
                else int(row["performance_period"])
                if row["performance_period"].isdigit()
                else 9999
            ),
        ),
    )

    write_csv(
        SCHEMA_CSV,
        [
            "performance_period",
            "column_position",
            "field_name",
            "normalized_field_name",
            "candidate_classes",
        ],
        schema_rows,
    )

    write_csv(
        CANDIDATE_FIELDS_CSV,
        [
            "performance_period",
            "candidate_class",
            "column_position",
            "field_name",
            "normalized_field_name",
        ],
        candidate_rows,
    )

    cross_fields = [
        "field_name",
        "period_count",
        "all_11_periods",
    ]

    cross_fields.extend(
        f"period_{period}"
        for period in EXPECTED_PERIODS
    )

    write_csv(
        CROSS_YEAR_CSV,
        cross_fields,
        cross_year_rows,
    )

    write_csv(
        CHECKS_CSV,
        [
            "check",
            "status",
            "detail",
        ],
        checks,
    )

    overall_pass = (
        not errors
        and all(
            check["status"] == "PASS"
            for check in checks
        )
    )

    # ------------------------------------------------------------
    # Human-readable report.
    # ------------------------------------------------------------
    lines: list[str] = []

    lines.append("=" * 100)
    lines.append(
        "CMS MSSP PERFORMANCE RESULTS SOURCE PROFILE v0.1"
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("SOURCE ARTIFACT")
    lines.append("-" * 100)
    lines.append(
        f"Path:    {SOURCE_ZIP.relative_to(REPO_ROOT)}"
    )
    lines.append(
        f"Bytes:   {outer_bytes:,}"
    )
    lines.append(
        f"SHA-256: {outer_sha256}"
    )
    lines.append("")

    lines.append("BOUNDARY")
    lines.append("-" * 100)
    lines.append(
        "READ-ONLY source profiling."
    )
    lines.append(
        "No Washington-dollar calculation."
    )
    lines.append(
        "No geographic allocation."
    )
    lines.append(
        "No economic-additivity conclusion."
    )
    lines.append(
        "No database writes."
    )
    lines.append(
        "No ledger inclusion."
    )
    lines.append("")

    lines.append("PERFORMANCE PERIODS")
    lines.append("-" * 100)

    for period in EXPECTED_PERIODS:
        header = period_headers.get(
            period,
            [],
        )

        lines.append(
            f"{period:<6} | "
            f"rows={period_row_counts.get(period, 0):>6,} | "
            f"columns={len(header):>3} | "
            f"{period_member_names.get(period, 'MISSING')}"
        )

    lines.append("")

    lines.append("CANDIDATE FIELD CLASSES")
    lines.append("-" * 100)

    class_counts = Counter(
        row["candidate_class"]
        for row in candidate_rows
    )

    for category in FIELD_PATTERNS:
        lines.append(
            f"{category:<30} "
            f"{class_counts.get(category, 0):>5}"
        )

    lines.append("")

    # Print exact candidate field names by category.  This is useful
    # for deciding which CMS documentation must be acquired next.
    for category in FIELD_PATTERNS:
        names = sorted(
            {
                row["field_name"]
                for row in candidate_rows
                if row["candidate_class"] == category
            },
            key=lambda value: value.lower(),
        )

        lines.append(category)
        lines.append("-" * len(category))

        if names:
            for name in names:
                periods = sorted(
                    {
                        row["performance_period"]
                        for row in candidate_rows
                        if (
                            row["candidate_class"] == category
                            and row["field_name"] == name
                        )
                    },
                    key=lambda value: (
                        2019.5
                        if value == "2019A"
                        else int(value)
                        if value.isdigit()
                        else 9999
                    ),
                )

                lines.append(
                    f"  {name} | "
                    + ",".join(periods)
                )
        else:
            lines.append("  NONE DISCOVERED")

        lines.append("")

    lines.append("CHECKS")
    lines.append("-" * 100)

    for check in checks:
        lines.append(
            f"{check['status']} | "
            f"{check['check']} | "
            f"{check['detail']}"
        )

    lines.append("")

    if errors:
        lines.append("ERRORS")
        lines.append("-" * 100)

        for error in errors:
            lines.append(
                f"FAIL | {error}"
            )

        lines.append("")

    lines.append("=" * 100)
    lines.append(
        "OVERALL MSSP PERFORMANCE RESULTS SOURCE PROFILE v0.1: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("Interpretive boundary:")
    lines.append(
        "  Candidate-field discovery is lexical only."
    )
    lines.append(
        "  A field name containing payment, savings, loss, "
        "expenditure, AIM, advance, or geography terminology "
        "does not establish accounting meaning."
    )
    lines.append(
        "  Ordinary PY2019 and CMS 2019A / Off-cycle-1 are "
        "preserved as distinct source periods."
    )
    lines.append(
        "  The observed 2024 revised source vintage is preserved "
        "as provenance and is not silently generalized to other years."
    )
    lines.append(
        "  No source or field is additive by default."
    )
    lines.append(
        "  Washington beneficiary, participant, provider, or ACO "
        "presence does not by itself establish Washington "
        "payment-dollar incidence."
    )
    lines.append(
        "  This profile supports systematic and reproducible review; "
        "it makes no claim of definitive Medicare completeness."
    )

    report = "\n".join(lines)

    REPORT_TXT.write_text(
        report,
        encoding="utf-8",
    )

    print(report)
    print("")
    print("Evidence written:")

    for path in [
        MEMBER_INVENTORY_CSV,
        SCHEMA_CSV,
        CANDIDATE_FIELDS_CSV,
        CROSS_YEAR_CSV,
        CHECKS_CSV,
        REPORT_TXT,
    ]:
        print(
            f"  {path.relative_to(REPO_ROOT)}"
        )

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
