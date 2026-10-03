"""
WCFFBP
CMS MSSP Settlement Amounts Profiler v0.1

PURPOSE
-------
Numerically profile MSSP settlement-related fields from the already
preserved CMS Performance Year Financial and Quality Results archive.

This profiler answers:

    1. What are the national observed amounts for:
         EarnSaveLoss positive
         EarnSaveLoss negative
         EarnSaveLoss zero
         GenSaveLoss
         Adv_Pay_Amt
         Adv_Pay_Recoup
         AIPBalance
         AIPRecoup
         AIPOwe

    2. Which settlement fields actually occur in each performance period?

    3. Can an already-certified MSSP historical-linkage v0.3 artifact
       provide a machine-readable WA-connected financial identifier
       without reconstructing linkage?

ACCOUNTING BOUNDARY
-------------------
This script does NOT:

    - calculate EarnSaveLoss - recoupment;
    - treat GenSaveLoss as an additive expenditure;
    - infer cash-payment timing;
    - infer Washington payment-dollar incidence;
    - treat ACO organizational connection as beneficiary incidence;
    - treat absent fields as zero-dollar programs;
    - reconstruct historical linkage;
    - perform fuzzy matching;
    - write to PostgreSQL;
    - alter the principal ledger.

All observed settlement quantities remain separate.

A negative EarnSaveLoss is reported separately from positive
EarnSaveLoss. It is not automatically treated as negative federal
spending.

No source is additive by default.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]

PERFORMANCE_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "Performance Year Financial and Quality Results.zip"
)

EXPECTED_PERFORMANCE_ZIP_SHA256 = (
    "C7555FA4849ADCA9AB4ECACAC607715F3B6BAA2DDA5CE4D422CA8668B1A9F128"
)

LINKAGE_V03_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "validation"
    / "historical_linkage_v0_3"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "validation"
    / "settlement_amounts_v0_1"
)

PERIOD_PROFILE_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_amounts_period_profile_v0_1.csv"
)

FIELD_PROFILE_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_amounts_field_profile_v0_1.csv"
)

SOURCE_INVENTORY_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_amounts_source_inventory_v0_1.csv"
)

WA_LINKAGE_DIAGNOSTIC_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_amounts_wa_linkage_diagnostic_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_settlement_amounts_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_mssp_settlement_amounts_report_v0_1.txt"
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


SETTLEMENT_FIELDS = [
    "EarnSaveLoss",
    "GenSaveLoss",
    "Adv_Pay_Amt",
    "Adv_Pay_Recoup",
    "AIPBalance",
    "AIPRecoup",
    "AIPOwe",
]


IDENTIFIER_CANDIDATES = [
    "ACO_ID",
    "ACO_Num",
    "ACO_NUM",
    "aco_id",
    "aco_num",
]


WA_ID_COLUMN_CANDIDATES = [
    "ACO_ID",
    "ACO_Num",
    "ACO_NUM",
    "aco_id",
    "aco_num",
    "financial_aco_id",
    "financial_identifier",
    "resolved_aco_id",
]


WA_PERIOD_COLUMN_CANDIDATES = [
    "performance_period",
    "period",
    "performance_year",
    "year",
]


WA_FLAG_COLUMN_CANDIDATES = [
    "wa_connected",
    "wa_connection",
    "wa_organizational_connection",
    "explicit_wa_service_area",
    "is_wa",
]


NULL_TOKENS = {
    "",
    "-",
    "--",
    "—",
    "–",
    "na",
    "n/a",
    "nan",
    "none",
    "null",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            h.update(block)

    return h.hexdigest().upper()


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
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def infer_period(member_name: str) -> str:
    text = member_name.replace(
        "\\",
        "/",
    ).lower()

    if (
        "2019_off-cycle_1" in text
        or "2019_off_cycle_1" in text
        or "2019a" in text
        or "2019a_" in text
    ):
        return "2019A"

    for year in range(
        2015,
        2025,
    ):
        if re.search(
            rf"(?<!\d){year}(?!\d)",
            text,
        ):
            return str(year)

    return "UNRESOLVED"


def decimal_from_value(value) -> Decimal | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    text = str(value).strip()

    if text.lower() in NULL_TOKENS:
        return None

    text = (
        text
        .replace("$", "")
        .replace(",", "")
        .replace("(", "-")
        .replace(")", "")
        .strip()
    )

    if text.endswith("%"):
        return None

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def decimal_sum(values) -> Decimal:
    total = Decimal("0")

    for value in values:
        parsed = decimal_from_value(
            value
        )

        if parsed is not None:
            total += parsed

    return total


def money(value: Decimal | None) -> str:
    if value is None:
        return ""

    return f"{value:.2f}"


def display_money(value: Decimal) -> str:
    return f"${value:,.2f}"


def choose_identifier_column(
    columns: list[str],
) -> str | None:
    for candidate in IDENTIFIER_CANDIDATES:
        if candidate in columns:
            return candidate

    lower_map = {
        column.lower(): column
        for column in columns
    }

    for candidate in IDENTIFIER_CANDIDATES:
        actual = lower_map.get(
            candidate.lower()
        )

        if actual:
            return actual

    return None


def truthy(value) -> bool:
    text = str(value).strip().lower()

    return text in {
        "1",
        "true",
        "yes",
        "y",
        "wa",
        "wa_connected",
        "connected",
        "explicit_wa",
        "explicit_wa_service_area",
    }


def find_column(
    columns: list[str],
    candidates: list[str],
) -> str | None:
    exact = {
        column: column
        for column in columns
    }

    lower = {
        column.lower(): column
        for column in columns
    }

    for candidate in candidates:
        if candidate in exact:
            return exact[candidate]

        if candidate.lower() in lower:
            return lower[
                candidate.lower()
            ]

    return None


def inspect_wa_linkage_artifacts() -> tuple[
    list[dict],
    dict[str, set[str]],
]:
    """
    Inspect certified v0.3 CSV artifacts conservatively.

    We only construct a period -> identifier set if a CSV exposes:
        - a recognizable period column,
        - a recognizable ACO identifier column,
        - AND an explicit recognizable WA flag column.

    We do not infer WA connection from names, addresses, service areas,
    filenames, or row membership.

    If such a table does not exist, WA numerical profiling is deferred.
    """
    diagnostics: list[dict] = []
    wa_ids: dict[
        str,
        set[str],
    ] = defaultdict(set)

    if not LINKAGE_V03_DIR.exists():
        diagnostics.append(
            {
                "artifact": str(
                    LINKAGE_V03_DIR.relative_to(
                        REPO_ROOT
                    )
                ),
                "period_column": "",
                "identifier_column": "",
                "wa_flag_column": "",
                "rows": 0,
                "usable_for_wa_subset": "NO",
                "reason": "historical_linkage_v0_3 directory not found",
            }
        )

        return diagnostics, wa_ids

    csv_paths = sorted(
        LINKAGE_V03_DIR.glob(
            "*.csv"
        )
    )

    for path in csv_paths:
        try:
            df = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
            )

            columns = list(
                df.columns
            )

            period_col = find_column(
                columns,
                WA_PERIOD_COLUMN_CANDIDATES,
            )

            id_col = find_column(
                columns,
                WA_ID_COLUMN_CANDIDATES,
            )

            flag_col = find_column(
                columns,
                WA_FLAG_COLUMN_CANDIDATES,
            )

            usable = (
                period_col is not None
                and id_col is not None
                and flag_col is not None
            )

            reason = ""

            if not usable:
                missing = []

                if period_col is None:
                    missing.append(
                        "period"
                    )

                if id_col is None:
                    missing.append(
                        "identifier"
                    )

                if flag_col is None:
                    missing.append(
                        "explicit WA flag"
                    )

                reason = (
                    "missing "
                    + ", ".join(
                        missing
                    )
                )

            diagnostics.append(
                {
                    "artifact": str(
                        path.relative_to(
                            REPO_ROOT
                        )
                    ),
                    "period_column": (
                        period_col
                        or ""
                    ),
                    "identifier_column": (
                        id_col
                        or ""
                    ),
                    "wa_flag_column": (
                        flag_col
                        or ""
                    ),
                    "rows": len(
                        df
                    ),
                    "usable_for_wa_subset": (
                        "YES"
                        if usable
                        else "NO"
                    ),
                    "reason": reason,
                }
            )

            if not usable:
                continue

            for _, row in df.iterrows():
                if not truthy(
                    row[
                        flag_col
                    ]
                ):
                    continue

                period = str(
                    row[
                        period_col
                    ]
                ).strip()

                identifier = str(
                    row[
                        id_col
                    ]
                ).strip()

                if (
                    period
                    in EXPECTED_PERIODS
                    and identifier
                ):
                    wa_ids[
                        period
                    ].add(
                        identifier
                    )

        except Exception as exc:
            diagnostics.append(
                {
                    "artifact": str(
                        path.relative_to(
                            REPO_ROOT
                        )
                    ),
                    "period_column": "",
                    "identifier_column": "",
                    "wa_flag_column": "",
                    "rows": "",
                    "usable_for_wa_subset": "NO",
                    "reason": (
                        "parse error: "
                        + str(exc)
                    ),
                }
            )

    return diagnostics, wa_ids


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    checks: list[dict] = []
    errors: list[str] = []

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

    # ------------------------------------------------------------
    # Source integrity
    # ------------------------------------------------------------
    add_check(
        "Preserved MSSP performance-results ZIP exists",
        PERFORMANCE_ZIP.exists(),
        str(
            PERFORMANCE_ZIP.relative_to(
                REPO_ROOT
            )
        ),
    )

    if not PERFORMANCE_ZIP.exists():
        write_csv(
            CHECKS_CSV,
            [
                "check",
                "status",
                "detail",
            ],
            checks,
        )

        print(
            f"FAIL: missing source archive: {PERFORMANCE_ZIP}"
        )

        return 1

    actual_sha = sha256_file(
        PERFORMANCE_ZIP
    )

    add_check(
        "Performance-results ZIP SHA-256 matches preserved acquisition",
        actual_sha
        == EXPECTED_PERFORMANCE_ZIP_SHA256,
        actual_sha,
    )

    # ------------------------------------------------------------
    # Certified WA-linkage artifact inspection
    # ------------------------------------------------------------
    (
        wa_diagnostics,
        wa_ids,
    ) = inspect_wa_linkage_artifacts()

    usable_wa_periods = sorted(
        [
            period
            for period, ids
            in wa_ids.items()
            if ids
        ],
        key=lambda value: (
            2019.5
            if value == "2019A"
            else int(value)
        ),
    )

    # ------------------------------------------------------------
    # Performance-result source inventory and profiling
    # ------------------------------------------------------------
    inventory_rows: list[dict] = []
    field_rows: list[dict] = []
    period_rows: list[dict] = []

    observed_periods = []
    period_data: dict[
        str,
        dict,
    ] = {}

    with zipfile.ZipFile(
        PERFORMANCE_ZIP,
        "r",
    ) as archive:
        csv_members = [
            info
            for info in archive.infolist()
            if (
                not info.is_dir()
                and info.filename.lower().endswith(
                    ".csv"
                )
            )
        ]

        for info in csv_members:
            period = infer_period(
                info.filename
            )

            try:
                raw = archive.read(
                    info
                )

                df = pd.read_csv(
                    io.BytesIO(raw),
                    dtype=str,
                    keep_default_na=False,
                    low_memory=False,
                )

                columns = list(
                    df.columns
                )

                id_col = (
                    choose_identifier_column(
                        columns
                    )
                )

                present_fields = [
                    field
                    for field in SETTLEMENT_FIELDS
                    if field in columns
                ]

                inventory_rows.append(
                    {
                        "performance_period": period,
                        "member_name": info.filename,
                        "rows": len(
                            df
                        ),
                        "columns": len(
                            columns
                        ),
                        "identifier_column": (
                            id_col
                            or ""
                        ),
                        "settlement_fields_present": ";".join(
                            present_fields
                        ),
                    }
                )

                if period not in EXPECTED_PERIODS:
                    continue

                if period in period_data:
                    errors.append(
                        "Multiple financial CSVs inferred for "
                        f"period {period}: "
                        f"{period_data[period]['member_name']} "
                        f"and {info.filename}"
                    )

                    continue

                observed_periods.append(
                    period
                )

                period_data[
                    period
                ] = {
                    "member_name": info.filename,
                    "df": df,
                    "id_col": id_col,
                    "present_fields": present_fields,
                }

            except Exception as exc:
                errors.append(
                    f"{info.filename}: {exc}"
                )

    # ------------------------------------------------------------
    # Numerical profiles
    # ------------------------------------------------------------
    for period in EXPECTED_PERIODS:
        source = period_data.get(
            period
        )

        if source is None:
            continue

        df = source[
            "df"
        ]

        id_col = source[
            "id_col"
        ]

        # National EarnSaveLoss sign decomposition
        earn_values = []

        if "EarnSaveLoss" in df.columns:
            earn_values = [
                decimal_from_value(
                    value
                )
                for value in df[
                    "EarnSaveLoss"
                ]
            ]

        earn_numeric = [
            value
            for value in earn_values
            if value is not None
        ]

        earn_positive = [
            value
            for value in earn_numeric
            if value > 0
        ]

        earn_negative = [
            value
            for value in earn_numeric
            if value < 0
        ]

        earn_zero = [
            value
            for value in earn_numeric
            if value == 0
        ]

        # Conservative WA-connected subset:
        # only if v0.3 artifact explicitly exposes usable period/id/WA flag.
        wa_subset_status = (
            "DEFERRED_NO_MACHINE_READABLE_CERTIFIED_WA_FLAG"
        )

        wa_rows = 0
        wa_earn_positive_total = Decimal(
            "0"
        )
        wa_earn_negative_total = Decimal(
            "0"
        )

        if (
            period in wa_ids
            and wa_ids[
                period
            ]
            and id_col is not None
        ):
            wa_subset_status = (
                "ORGANIZATIONAL_CONNECTION_ONLY_NOT_PAYMENT_INCIDENCE"
            )

            normalized_ids = {
                str(value).strip()
                for value
                in wa_ids[
                    period
                ]
            }

            mask = df[
                id_col
            ].astype(
                str
            ).str.strip().isin(
                normalized_ids
            )

            wa_df = df[
                mask
            ]

            wa_rows = len(
                wa_df
            )

            if (
                "EarnSaveLoss"
                in wa_df.columns
            ):
                for raw_value in wa_df[
                    "EarnSaveLoss"
                ]:
                    value = decimal_from_value(
                        raw_value
                    )

                    if value is None:
                        continue

                    if value > 0:
                        wa_earn_positive_total += (
                            value
                        )
                    elif value < 0:
                        wa_earn_negative_total += (
                            value
                        )

        period_rows.append(
            {
                "performance_period": period,
                "financial_rows": len(
                    df
                ),
                "identifier_column": (
                    id_col
                    or ""
                ),
                "earn_numeric_rows": len(
                    earn_numeric
                ),
                "earn_positive_rows": len(
                    earn_positive
                ),
                "earn_positive_total": money(
                    sum(
                        earn_positive,
                        Decimal("0"),
                    )
                ),
                "earn_negative_rows": len(
                    earn_negative
                ),
                "earn_negative_total": money(
                    sum(
                        earn_negative,
                        Decimal("0"),
                    )
                ),
                "earn_zero_rows": len(
                    earn_zero
                ),
                "earn_net_arithmetic_total_control_only": money(
                    sum(
                        earn_numeric,
                        Decimal("0"),
                    )
                ),
                "wa_subset_status": wa_subset_status,
                "wa_connected_financial_rows": wa_rows,
                "wa_connected_earn_positive_total": money(
                    wa_earn_positive_total
                ),
                "wa_connected_earn_negative_total": money(
                    wa_earn_negative_total
                ),
            }
        )

        for field in SETTLEMENT_FIELDS:
            if field not in df.columns:
                field_rows.append(
                    {
                        "performance_period": period,
                        "field_name": field,
                        "field_present": "NO",
                        "numeric_rows": "",
                        "positive_rows": "",
                        "positive_total": "",
                        "negative_rows": "",
                        "negative_total": "",
                        "zero_rows": "",
                        "arithmetic_total": "",
                    }
                )

                continue

            numeric = []

            for raw_value in df[
                field
            ]:
                value = decimal_from_value(
                    raw_value
                )

                if value is not None:
                    numeric.append(
                        value
                    )

            positive = [
                value
                for value in numeric
                if value > 0
            ]

            negative = [
                value
                for value in numeric
                if value < 0
            ]

            zero = [
                value
                for value in numeric
                if value == 0
            ]

            field_rows.append(
                {
                    "performance_period": period,
                    "field_name": field,
                    "field_present": "YES",
                    "numeric_rows": len(
                        numeric
                    ),
                    "positive_rows": len(
                        positive
                    ),
                    "positive_total": money(
                        sum(
                            positive,
                            Decimal("0"),
                        )
                    ),
                    "negative_rows": len(
                        negative
                    ),
                    "negative_total": money(
                        sum(
                            negative,
                            Decimal("0"),
                        )
                    ),
                    "zero_rows": len(
                        zero
                    ),
                    "arithmetic_total": money(
                        sum(
                            numeric,
                            Decimal("0"),
                        )
                    ),
                }
            )

    # ------------------------------------------------------------
    # Validation checks
    # ------------------------------------------------------------
    add_check(
        "All source CSVs parse without profiler errors",
        len(
            errors
        )
        == 0,
        (
            f"{len(inventory_rows)} CSV members profiled; "
            f"{len(errors)} errors"
        ),
    )

    add_check(
        "Exactly 11 expected performance periods discovered",
        set(
            observed_periods
        )
        == set(
            EXPECTED_PERIODS
        )
        and len(
            observed_periods
        )
        == 11,
        (
            f"{len(observed_periods)}/11 | "
            + ",".join(
                observed_periods
            )
        ),
    )

    expected_rows = {
        "2015": 392,
        "2016": 432,
        "2017": 472,
        "2018": 548,
        "2019": 475,
        "2019A": 205,
        "2020": 513,
        "2021": 475,
        "2022": 482,
        "2023": 453,
        "2024": 476,
    }

    row_count_mismatches = []

    for period, expected in expected_rows.items():
        source = period_data.get(
            period
        )

        if source is None:
            row_count_mismatches.append(
                f"{period}=MISSING"
            )

            continue

        actual = len(
            source[
                "df"
            ]
        )

        if actual != expected:
            row_count_mismatches.append(
                f"{period}={actual}/{expected}"
            )

    add_check(
        "Financial row counts reproduce certified source profile",
        len(
            row_count_mismatches
        )
        == 0,
        (
            "11/11"
            if not row_count_mismatches
            else "; ".join(
                row_count_mismatches
            )
        ),
    )

    earn_missing = [
        period
        for period in EXPECTED_PERIODS
        if (
            period not in period_data
            or "EarnSaveLoss"
            not in period_data[
                period
            ][
                "df"
            ].columns
        )
    ]

    gen_missing = [
        period
        for period in EXPECTED_PERIODS
        if (
            period not in period_data
            or "GenSaveLoss"
            not in period_data[
                period
            ][
                "df"
            ].columns
        )
    ]

    add_check(
        "EarnSaveLoss present in all 11 periods",
        not earn_missing,
        (
            "11/11"
            if not earn_missing
            else "missing: "
            + ",".join(
                earn_missing
            )
        ),
    )

    add_check(
        "GenSaveLoss present in all 11 periods",
        not gen_missing,
        (
            "11/11"
            if not gen_missing
            else "missing: "
            + ",".join(
                gen_missing
            )
        ),
    )

    # This is intentionally informational rather than a PASS condition.
    # Failure to expose a machine-readable WA flag must NOT cause us
    # to reconstruct or infer WA linkage here.
    wa_linkage_available = bool(
        usable_wa_periods
    )

    # ------------------------------------------------------------
    # Write artifacts
    # ------------------------------------------------------------
    write_csv(
        SOURCE_INVENTORY_CSV,
        [
            "performance_period",
            "member_name",
            "rows",
            "columns",
            "identifier_column",
            "settlement_fields_present",
        ],
        inventory_rows,
    )

    write_csv(
        PERIOD_PROFILE_CSV,
        [
            "performance_period",
            "financial_rows",
            "identifier_column",
            "earn_numeric_rows",
            "earn_positive_rows",
            "earn_positive_total",
            "earn_negative_rows",
            "earn_negative_total",
            "earn_zero_rows",
            "earn_net_arithmetic_total_control_only",
            "wa_subset_status",
            "wa_connected_financial_rows",
            "wa_connected_earn_positive_total",
            "wa_connected_earn_negative_total",
        ],
        period_rows,
    )

    write_csv(
        FIELD_PROFILE_CSV,
        [
            "performance_period",
            "field_name",
            "field_present",
            "numeric_rows",
            "positive_rows",
            "positive_total",
            "negative_rows",
            "negative_total",
            "zero_rows",
            "arithmetic_total",
        ],
        field_rows,
    )

    write_csv(
        WA_LINKAGE_DIAGNOSTIC_CSV,
        [
            "artifact",
            "period_column",
            "identifier_column",
            "wa_flag_column",
            "rows",
            "usable_for_wa_subset",
            "reason",
        ],
        wa_diagnostics,
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
            check[
                "status"
            ]
            == "PASS"
            for check in checks
        )
    )

    # ------------------------------------------------------------
    # Human-readable report
    # ------------------------------------------------------------
    lines: list[str] = []

    lines.append(
        "=" * 120
    )
    lines.append(
        "CMS MSSP SETTLEMENT AMOUNTS PROFILE v0.1"
    )
    lines.append(
        "=" * 120
    )
    lines.append("")

    lines.append(
        "BOUNDARY"
    )
    lines.append(
        "-" * 120
    )
    lines.append(
        "READ-ONLY numerical profile of preserved CMS MSSP performance-result fields."
    )
    lines.append(
        "EarnSaveLoss and recoupment quantities remain separate."
    )
    lines.append(
        "No net settlement formula inferred."
    )
    lines.append(
        "Negative EarnSaveLoss is not classified as negative federal spending."
    )
    lines.append(
        "ACO organizational connection is not payment-dollar incidence."
    )
    lines.append(
        "Absent fields are not interpreted as zero-dollar programs."
    )
    lines.append(
        "No database writes."
    )
    lines.append(
        "No ledger inclusion."
    )
    lines.append("")

    lines.append(
        "SOURCE"
    )
    lines.append(
        "-" * 120
    )
    lines.append(
        str(
            PERFORMANCE_ZIP.relative_to(
                REPO_ROOT
            )
        )
    )
    lines.append(
        f"SHA-256: {actual_sha}"
    )
    lines.append("")

    lines.append(
        "NATIONAL EARNED SHARED SAVINGS / LOSSES"
    )
    lines.append(
        "-" * 120
    )

    national_positive_total = Decimal(
        "0"
    )
    national_negative_total = Decimal(
        "0"
    )

    for row in period_rows:
        positive = Decimal(
            row[
                "earn_positive_total"
            ]
            or "0"
        )

        negative = Decimal(
            row[
                "earn_negative_total"
            ]
            or "0"
        )

        national_positive_total += (
            positive
        )
        national_negative_total += (
            negative
        )

        lines.append(
            f"{row['performance_period']:<6} | "
            f"rows={row['financial_rows']:>4} | "
            f"positive={row['earn_positive_rows']:>4} "
            f"{display_money(positive):>18} | "
            f"negative={row['earn_negative_rows']:>4} "
            f"{display_money(negative):>18} | "
            f"zero={row['earn_zero_rows']:>4}"
        )

    lines.append(
        "-" * 120
    )
    lines.append(
        "TOTAL positive EarnSaveLoss: "
        + display_money(
            national_positive_total
        )
    )
    lines.append(
        "TOTAL negative EarnSaveLoss: "
        + display_money(
            national_negative_total
        )
    )
    lines.append("")

    lines.append(
        "SETTLEMENT FIELD AMOUNTS"
    )
    lines.append(
        "-" * 120
    )

    for period in EXPECTED_PERIODS:
        rows = [
            row
            for row in field_rows
            if row[
                "performance_period"
            ]
            == period
        ]

        lines.append(
            f"[{period}]"
        )

        for row in rows:
            if row[
                "field_present"
            ] != "YES":
                continue

            total = Decimal(
                row[
                    "arithmetic_total"
                ]
                or "0"
            )

            lines.append(
                f"  {row['field_name']:<18} "
                f"numeric={str(row['numeric_rows']):>4} | "
                f"positive={str(row['positive_rows']):>4} | "
                f"negative={str(row['negative_rows']):>4} | "
                f"zero={str(row['zero_rows']):>4} | "
                f"arithmetic_total={display_money(total)}"
            )

    lines.append("")
    lines.append(
        "CERTIFIED WA-LINKAGE ARTIFACT DIAGNOSTIC"
    )
    lines.append(
        "-" * 120
    )

    if wa_linkage_available:
        lines.append(
            "Machine-readable explicit WA identifiers were found for: "
            + ", ".join(
                usable_wa_periods
            )
        )

        lines.append(
            "Any resulting amounts are ORGANIZATIONAL_CONNECTION_ONLY_NOT_PAYMENT_INCIDENCE."
        )
    else:
        lines.append(
            "No certified v0.3 artifact exposed period + identifier + explicit WA flag in a form this profiler can safely consume."
        )

        lines.append(
            "WA-connected numerical profiling is therefore DEFERRED rather than reconstructed or inferred."
        )

    lines.append("")

    for row in wa_diagnostics:
        lines.append(
            f"{row['usable_for_wa_subset']:<3} | "
            f"{row['artifact']} | "
            f"{row['reason']}"
        )

    lines.append("")
    lines.append(
        "CHECKS"
    )
    lines.append(
        "-" * 120
    )

    for check in checks:
        lines.append(
            f"{check['status']} | "
            f"{check['check']} | "
            f"{check['detail']}"
        )

    if errors:
        lines.append("")
        lines.append(
            "ERRORS"
        )
        lines.append(
            "-" * 120
        )

        for error in errors:
            lines.append(
                f"FAIL | {error}"
            )

    lines.append("")
    lines.append(
        "=" * 120
    )
    lines.append(
        "OVERALL CMS MSSP SETTLEMENT AMOUNTS PROFILE v0.1: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )
    lines.append(
        "=" * 120
    )
    lines.append("")

    lines.append(
        "Interpretive boundary:"
    )
    lines.append(
        "  PASS certifies reproducible numerical profiling of the preserved MSSP performance-result fields."
    )
    lines.append(
        "  PASS does not certify economic additivity, cash timing, Washington incidence, or ledger inclusion."
    )
    lines.append(
        "  GenSaveLoss remains a derived/control quantity."
    )
    lines.append(
        "  Positive EarnSaveLoss remains an additive-in-principle candidate pending remaining gates."
    )
    lines.append(
        "  Advance/AIM/AIP amounts and recoupments remain separately reported; no netting formula is imposed."
    )
    lines.append(
        "  No source is additive by default."
    )

    report = "\n".join(
        lines
    )

    REPORT_TXT.write_text(
        report,
        encoding="utf-8",
    )

    print(
        report
    )
    print("")
    print(
        "Evidence written:"
    )

    for path in [
        SOURCE_INVENTORY_CSV,
        PERIOD_PROFILE_CSV,
        FIELD_PROFILE_CSV,
        WA_LINKAGE_DIAGNOSTIC_CSV,
        CHECKS_CSV,
        REPORT_TXT,
    ]:
        print(
            f"  {path.relative_to(REPO_ROOT)}"
        )

    return (
        0
        if overall_pass
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )
