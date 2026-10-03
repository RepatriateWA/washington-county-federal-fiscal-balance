from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


# =============================================================================
# ETL-172F-3
# WASHINGTON OASI / DI / HI RECEIPTS ALLOCATION
#
# Purpose:
#   Allocate certified OMB national OASI, DI, and HI receipt controls to
#   Washington using certified SSA state contribution shares.
#
# Method:
#   OASI -> SSA OASDI contribution share
#   DI   -> SSA OASDI contribution share
#   HI   -> SSA HI contribution share
#
# Timing:
#   FY2015-FY2023 -> contemporaneous SSA allocator year
#   FY2024        -> SSA 2023 latest-available contribution share
#
# Boundaries:
#   - No database writes.
#   - No final federal-receipts ledger inclusion.
#   - No forced reconciliation to IRS gross collections.
#   - No Rockefeller dollar target is imposed.
#   - No interpolation or extrapolation of SSA shares.
# =============================================================================


REPO_ROOT = Path(__file__).resolve().parents[1]


OMB_CONTROL_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "social_insurance_receipt_controls_v0_1"
    / "national_social_insurance_receipt_controls.csv"
)


SSA_ALLOCATOR_FILE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "ssa"
    / "earnings_employment"
    / "validation"
    / "allocator_certification_v0_1"
    / "washington_ssa_receipts_allocator_extract.csv"
)


OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "washington_social_insurance_receipts_v0_1"
)


DETAIL_CSV = (
    OUTPUT_DIR
    / "washington_social_insurance_receipts.csv"
)

ANNUAL_CSV = (
    OUTPUT_DIR
    / "washington_social_insurance_receipts_annual.csv"
)

CERTIFICATION_JSON = (
    OUTPUT_DIR
    / "certification.json"
)

CERTIFICATION_REPORT = (
    OUTPUT_DIR
    / "certification_report.txt"
)


TARGET_YEARS = list(range(2015, 2025))

SERIES_ORDER = (
    "OASI",
    "DI",
    "HI",
)

EXPECTED_DETAIL_ROWS = (
    len(TARGET_YEARS)
    * len(SERIES_ORDER)
)

EXPECTED_ANNUAL_ROWS = len(TARGET_YEARS)


# -----------------------------------------------------------------------------
# Allocation policy
# -----------------------------------------------------------------------------

ALLOCATOR_POLICY = {
    "OASI": {
        "ssa_program": "OASDI",
        "allocator_measure": "contributions",
    },
    "DI": {
        "ssa_program": "OASDI",
        "allocator_measure": "contributions",
    },
    "HI": {
        "ssa_program": "HI",
        "allocator_measure": "contributions",
    },
}


# Explicit timing policy.
#
# No attempt is made to manufacture a 2024 SSA observation.
#
ALLOCATOR_YEAR_POLICY = {
    year: year
    for year in range(2015, 2024)
}
ALLOCATOR_YEAR_POLICY[2024] = 2023


# Known source limitation established during SSA source certification.
#
# Preserve as metadata. Do not modify the value.
#
KNOWN_LIMITATIONS = {
    (2015, "HI"): (
        "SSA_SOURCE_LIMITATION_2015_HI_STATE_SELF_EMPLOYED"
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest().upper()


def decimal_value(
    value: Any,
    *,
    field_name: str,
) -> Decimal:
    if value is None:
        raise ValueError(
            f"{field_name} is NULL."
        )

    text = str(value).strip().replace(",", "")

    if not text:
        raise ValueError(
            f"{field_name} is blank."
        )

    # Permit percentages if a source happens to serialize them
    # with a percent sign. The calling code still validates range.
    if text.endswith("%"):
        text = text[:-1].strip()

    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"{field_name} is non-numeric: {value!r}"
        ) from exc

    if not result.is_finite():
        raise ValueError(
            f"{field_name} is non-finite: {value!r}"
        )

    return result


def plain_decimal(value: Decimal) -> str:
    return format(value, "f")


def find_column(
    fieldnames: list[str],
    candidates: tuple[str, ...],
    *,
    semantic_name: str,
) -> str:
    normalized = {
        name.strip().lower(): name
        for name in fieldnames
    }

    for candidate in candidates:
        match = normalized.get(
            candidate.lower()
        )

        if match is not None:
            return match

    raise RuntimeError(
        "INPUT SCHEMA CERTIFICATION FAILURE\n"
        f"Could not identify {semantic_name} column.\n"
        f"Candidates : {candidates}\n"
        f"Available  : {fieldnames}"
    )


def read_csv(
    path: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Required certified input not found: {path}"
        )

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames is None:
            raise RuntimeError(
                f"CSV has no header: {path}"
            )

        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    return fieldnames, rows


def load_omb_controls() -> tuple[
    dict[tuple[int, str], dict[str, Any]],
    dict[str, Any],
]:
    fieldnames, rows = read_csv(
        OMB_CONTROL_FILE
    )

    required = {
        "fiscal_year",
        "receipt_series",
        "source_label",
        "source_cell",
        "source_units",
        "national_receipts_dollars",
    }

    missing = sorted(
        required - set(fieldnames)
    )

    if missing:
        raise RuntimeError(
            "OMB INPUT SCHEMA CERTIFICATION FAILURE\n"
            f"Missing columns: {missing}"
        )

    if len(rows) != EXPECTED_DETAIL_ROWS:
        raise RuntimeError(
            "OMB INPUT ROW-COUNT CERTIFICATION FAILURE\n"
            f"Expected: {EXPECTED_DETAIL_ROWS}\n"
            f"Actual  : {len(rows)}"
        )

    controls: dict[
        tuple[int, str],
        dict[str, Any],
    ] = {}

    for row in rows:
        fiscal_year = int(
            row["fiscal_year"]
        )

        series = (
            row["receipt_series"]
            .strip()
            .upper()
        )

        key = (
            fiscal_year,
            series,
        )

        if key in controls:
            raise RuntimeError(
                "OMB INPUT UNIQUENESS FAILURE\n"
                f"Duplicate key: {key}"
            )

        national_dollars = decimal_value(
            row["national_receipts_dollars"],
            field_name=(
                "national_receipts_dollars"
            ),
        )

        if national_dollars < 0:
            raise RuntimeError(
                "OMB CONTROL VALUE FAILURE\n"
                f"Negative national control: "
                f"{key} = {national_dollars}"
            )

        controls[key] = {
            "fiscal_year": fiscal_year,
            "receipt_series": series,
            "source_label": (
                row["source_label"]
            ),
            "source_cell": (
                row["source_cell"]
            ),
            "source_units": (
                row["source_units"]
            ),
            "national_receipts_dollars": (
                national_dollars
            ),
        }

    expected_keys = {
        (year, series)
        for year in TARGET_YEARS
        for series in SERIES_ORDER
    }

    actual_keys = set(
        controls.keys()
    )

    if actual_keys != expected_keys:
        raise RuntimeError(
            "OMB INPUT COVERAGE FAILURE\n"
            f"Missing    : "
            f"{sorted(expected_keys - actual_keys)}\n"
            f"Unexpected : "
            f"{sorted(actual_keys - expected_keys)}"
        )

    profile = {
        "path": str(
            OMB_CONTROL_FILE.relative_to(
                REPO_ROOT
            )
        ),
        "sha256": sha256_file(
            OMB_CONTROL_FILE
        ),
        "rows": len(rows),
        "coverage": "PASS",
    }

    return controls, profile


def identify_ssa_schema(
    fieldnames: list[str],
) -> dict[str, str]:
    """
    ETL-172E-5 was built before this step, so this function
    identifies its columns by semantic alternatives rather than
    assuming one exact serialization.

    It still fails closed if the necessary fields cannot be found.
    """

    year_col = find_column(
        fieldnames,
        (
            "year",
            "data_year",
            "ssa_year",
            "calendar_year",
            "tax_year",
        ),
        semantic_name="SSA allocator year",
    )

    program_col = find_column(
        fieldnames,
        (
            "program",
            "series",
            "receipt_series",
            "allocator_series",
            "insurance_program",
        ),
        semantic_name="SSA program",
    )

    contribution_share_col = find_column(
        fieldnames,
        (
            "contribution_share",
            "contributions_share",
            "wa_contribution_share",
            "washington_contribution_share",
            "candidate_contribution_share",
            "contribution_share_pct",
            "contributions_share_pct",
        ),
        semantic_name=(
            "SSA Washington contribution share"
        ),
    )

    return {
        "year": year_col,
        "program": program_col,
        "contribution_share": (
            contribution_share_col
        ),
    }


def normalize_ssa_program(
    value: str,
) -> str:
    text = (
        value.strip()
        .upper()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

    if "OASDI" in text:
        return "OASDI"

    if (
        text == "HI"
        or text == "MEDICAREHI"
        or "HOSPITALINSURANCE" in text
        or "MEDICAREPARTA" in text
    ):
        return "HI"

    raise RuntimeError(
        "SSA PROGRAM CERTIFICATION FAILURE\n"
        f"Unrecognized program value: {value!r}"
    )


def normalize_share(
    raw_value: Any,
    *,
    field_name: str,
) -> tuple[Decimal, str]:
    """
    Return share as a proportion in [0, 1].

    ETL-172E-5 console values were expressed as percentages,
    e.g. approximately 2.60 rather than 0.0260.

    We preserve the detected representation in metadata.
    """

    raw_text = str(raw_value).strip()

    value = decimal_value(
        raw_value,
        field_name=field_name,
    )

    explicit_percent = (
        raw_text.endswith("%")
    )

    if explicit_percent:
        proportion = (
            value / Decimal("100")
        )
        representation = (
            "PERCENT_EXPLICIT"
        )

    elif (
        value > Decimal("1")
        and value <= Decimal("100")
    ):
        proportion = (
            value / Decimal("100")
        )
        representation = (
            "PERCENT_NUMERIC"
        )

    elif (
        value >= Decimal("0")
        and value <= Decimal("1")
    ):
        proportion = value
        representation = "PROPORTION"

    else:
        raise RuntimeError(
            "SSA SHARE RANGE CERTIFICATION FAILURE\n"
            f"Unexpected share value: {raw_value!r}"
        )

    if not (
        Decimal("0")
        <= proportion
        <= Decimal("1")
    ):
        raise RuntimeError(
            "SSA SHARE NORMALIZATION FAILURE\n"
            f"Normalized share outside [0,1]: "
            f"{proportion}"
        )

    return (
        proportion,
        representation,
    )


def load_ssa_allocators() -> tuple[
    dict[tuple[int, str], dict[str, Any]],
    dict[str, Any],
]:
    fieldnames, rows = read_csv(
        SSA_ALLOCATOR_FILE
    )

    schema = identify_ssa_schema(
        fieldnames
    )

    allocators: dict[
        tuple[int, str],
        dict[str, Any],
    ] = {}

    for row in rows:
        year = int(
            row[schema["year"]]
        )

        program = normalize_ssa_program(
            row[schema["program"]]
        )

        share, representation = (
            normalize_share(
                row[
                    schema[
                        "contribution_share"
                    ]
                ],
                field_name=(
                    "SSA contribution share"
                ),
            )
        )

        key = (
            year,
            program,
        )

        if key in allocators:
            raise RuntimeError(
                "SSA INPUT UNIQUENESS FAILURE\n"
                f"Duplicate key: {key}"
            )

        allocators[key] = {
            "allocator_data_year": year,
            "ssa_program": program,
            "contribution_share": share,
            "share_representation": (
                representation
            ),
            "raw_contribution_share": (
                row[
                    schema[
                        "contribution_share"
                    ]
                ]
            ),
        }

    expected_keys = {
        (year, program)
        for year in range(2015, 2024)
        for program in (
            "OASDI",
            "HI",
        )
    }

    missing = sorted(
        expected_keys
        - set(allocators.keys())
    )

    if missing:
        raise RuntimeError(
            "SSA INPUT COVERAGE FAILURE\n"
            "Missing certified allocator observations:\n"
            f"{missing}"
        )

    profile = {
        "path": str(
            SSA_ALLOCATOR_FILE.relative_to(
                REPO_ROOT
            )
        ),
        "sha256": sha256_file(
            SSA_ALLOCATOR_FILE
        ),
        "rows": len(rows),
        "schema": schema,
        "required_coverage": "PASS",
    }

    return allocators, profile


def allocation_method(
    fiscal_year: int,
    allocator_year: int,
) -> str:
    if fiscal_year == allocator_year:
        return (
            "CONTEMPORANEOUS_CONTRIBUTION_SHARE"
        )

    if (
        fiscal_year == 2024
        and allocator_year == 2023
    ):
        return "LATEST_AVAILABLE_SHARE"

    raise RuntimeError(
        "ALLOCATOR TIMING POLICY FAILURE\n"
        f"Unexpected control/allocator pairing: "
        f"FY{fiscal_year} <- {allocator_year}"
    )


def allocate(
    controls: dict[
        tuple[int, str],
        dict[str, Any],
    ],
    allocators: dict[
        tuple[int, str],
        dict[str, Any],
    ],
) -> list[dict[str, Any]]:
    output: list[
        dict[str, Any]
    ] = []

    for fiscal_year in TARGET_YEARS:
        allocator_year = (
            ALLOCATOR_YEAR_POLICY[
                fiscal_year
            ]
        )

        lag_years = (
            fiscal_year
            - allocator_year
        )

        for series in SERIES_ORDER:
            control = controls[
                (
                    fiscal_year,
                    series,
                )
            ]

            policy = (
                ALLOCATOR_POLICY[
                    series
                ]
            )

            ssa_program = (
                policy["ssa_program"]
            )

            allocator_key = (
                allocator_year,
                ssa_program,
            )

            if allocator_key not in allocators:
                raise RuntimeError(
                    "ALLOCATOR LOOKUP FAILURE\n"
                    f"Missing allocator: "
                    f"{allocator_key}"
                )

            allocator = allocators[
                allocator_key
            ]

            share = allocator[
                "contribution_share"
            ]

            national_dollars = control[
                "national_receipts_dollars"
            ]

            washington_dollars = (
                national_dollars
                * share
            )

            method = allocation_method(
                fiscal_year,
                allocator_year,
            )

            limitation = (
                KNOWN_LIMITATIONS.get(
                    (
                        allocator_year,
                        series,
                    ),
                    "",
                )
            )

            output.append(
                {
                    "fiscal_year": (
                        fiscal_year
                    ),
                    "receipt_series": (
                        series
                    ),
                    "omb_source_cell": (
                        control[
                            "source_cell"
                        ]
                    ),
                    "omb_source_label": (
                        control[
                            "source_label"
                        ]
                    ),
                    "national_receipts_dollars": (
                        plain_decimal(
                            national_dollars
                        )
                    ),
                    "ssa_program": (
                        ssa_program
                    ),
                    "allocator_measure": (
                        policy[
                            "allocator_measure"
                        ]
                    ),
                    "allocator_data_year": (
                        allocator_year
                    ),
                    "allocator_lag_years": (
                        lag_years
                    ),
                    "allocation_method": (
                        method
                    ),
                    "ssa_contribution_share": (
                        plain_decimal(
                            share
                        )
                    ),
                    "ssa_share_raw": (
                        allocator[
                            "raw_contribution_share"
                        ]
                    ),
                    "ssa_share_representation": (
                        allocator[
                            "share_representation"
                        ]
                    ),
                    "washington_receipts_dollars": (
                        plain_decimal(
                            washington_dollars
                        )
                    ),
                    "source_limitation_flag": (
                        limitation
                    ),
                }
            )

    return output


def certify_detail(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(rows) != EXPECTED_DETAIL_ROWS:
        raise RuntimeError(
            "DETAIL ROW-COUNT FAILURE\n"
            f"Expected: {EXPECTED_DETAIL_ROWS}\n"
            f"Actual  : {len(rows)}"
        )

    keys = [
        (
            int(row["fiscal_year"]),
            str(row["receipt_series"]),
        )
        for row in rows
    ]

    if len(set(keys)) != len(keys):
        raise RuntimeError(
            "DETAIL UNIQUENESS FAILURE"
        )

    expected_keys = {
        (year, series)
        for year in TARGET_YEARS
        for series in SERIES_ORDER
    }

    if set(keys) != expected_keys:
        raise RuntimeError(
            "DETAIL COVERAGE FAILURE\n"
            f"Missing: "
            f"{sorted(expected_keys - set(keys))}\n"
            f"Unexpected: "
            f"{sorted(set(keys) - expected_keys)}"
        )

    # OASI and DI must use exactly the same OASDI share
    # within each fiscal year.
    by_year = defaultdict(dict)

    for row in rows:
        by_year[
            int(row["fiscal_year"])
        ][
            str(row["receipt_series"])
        ] = row

    for year in TARGET_YEARS:
        oasi = by_year[year]["OASI"]
        di = by_year[year]["DI"]
        hi = by_year[year]["HI"]

        if (
            oasi["ssa_program"]
            != "OASDI"
            or di["ssa_program"]
            != "OASDI"
        ):
            raise RuntimeError(
                "OASDI ALLOCATOR POLICY FAILURE\n"
                f"FY{year}"
            )

        if (
            oasi[
                "ssa_contribution_share"
            ]
            != di[
                "ssa_contribution_share"
            ]
        ):
            raise RuntimeError(
                "OASI/DI SHARE CONSISTENCY FAILURE\n"
                f"FY{year}"
            )

        if hi["ssa_program"] != "HI":
            raise RuntimeError(
                "HI ALLOCATOR POLICY FAILURE\n"
                f"FY{year}"
            )

        expected_allocator_year = (
            ALLOCATOR_YEAR_POLICY[
                year
            ]
        )

        for series in SERIES_ORDER:
            row = by_year[
                year
            ][series]

            if (
                int(
                    row[
                        "allocator_data_year"
                    ]
                )
                != expected_allocator_year
            ):
                raise RuntimeError(
                    "ALLOCATOR YEAR POLICY FAILURE\n"
                    f"FY{year} {series}"
                )

    return {
        "expected_rows": (
            EXPECTED_DETAIL_ROWS
        ),
        "actual_rows": len(rows),
        "coverage": "PASS",
        "uniqueness": "PASS",
        "oasi_di_share_consistency": (
            "PASS"
        ),
        "allocator_timing_policy": (
            "PASS"
        ),
    }


def build_annual(
    detail_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[
        int,
        dict[str, Decimal],
    ] = defaultdict(
        lambda: {
            "OASI": Decimal("0"),
            "DI": Decimal("0"),
            "HI": Decimal("0"),
        }
    )

    methods: dict[
        int,
        set[str],
    ] = defaultdict(set)

    allocator_years: dict[
        int,
        set[int],
    ] = defaultdict(set)

    limitation_flags: dict[
        int,
        set[str],
    ] = defaultdict(set)

    for row in detail_rows:
        year = int(
            row["fiscal_year"]
        )

        series = str(
            row["receipt_series"]
        )

        amount = decimal_value(
            row[
                "washington_receipts_dollars"
            ],
            field_name=(
                "washington_receipts_dollars"
            ),
        )

        grouped[year][series] += amount

        methods[year].add(
            str(
                row[
                    "allocation_method"
                ]
            )
        )

        allocator_years[year].add(
            int(
                row[
                    "allocator_data_year"
                ]
            )
        )

        flag = str(
            row[
                "source_limitation_flag"
            ]
        ).strip()

        if flag:
            limitation_flags[
                year
            ].add(flag)

    annual: list[
        dict[str, Any]
    ] = []

    for year in TARGET_YEARS:
        oasi = grouped[year]["OASI"]
        di = grouped[year]["DI"]
        hi = grouped[year]["HI"]

        total = (
            oasi
            + di
            + hi
        )

        annual.append(
            {
                "fiscal_year": year,
                "washington_oasi_receipts_dollars": (
                    plain_decimal(oasi)
                ),
                "washington_di_receipts_dollars": (
                    plain_decimal(di)
                ),
                "washington_oasdi_receipts_dollars": (
                    plain_decimal(
                        oasi + di
                    )
                ),
                "washington_hi_receipts_dollars": (
                    plain_decimal(hi)
                ),
                "washington_social_insurance_receipts_dollars": (
                    plain_decimal(total)
                ),
                "allocator_data_years": (
                    ";".join(
                        str(value)
                        for value in sorted(
                            allocator_years[
                                year
                            ]
                        )
                    )
                ),
                "allocation_methods": (
                    ";".join(
                        sorted(
                            methods[
                                year
                            ]
                        )
                    )
                ),
                "source_limitation_flags": (
                    ";".join(
                        sorted(
                            limitation_flags[
                                year
                            ]
                        )
                    )
                ),
            }
        )

    return annual


def certify_annual(
    annual_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(annual_rows) != EXPECTED_ANNUAL_ROWS:
        raise RuntimeError(
            "ANNUAL ROW-COUNT FAILURE\n"
            f"Expected: {EXPECTED_ANNUAL_ROWS}\n"
            f"Actual  : {len(annual_rows)}"
        )

    years = [
        int(row["fiscal_year"])
        for row in annual_rows
    ]

    if years != TARGET_YEARS:
        raise RuntimeError(
            "ANNUAL YEAR COVERAGE FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {years}"
        )

    for row in annual_rows:
        oasi = decimal_value(
            row[
                "washington_oasi_receipts_dollars"
            ],
            field_name="annual OASI",
        )

        di = decimal_value(
            row[
                "washington_di_receipts_dollars"
            ],
            field_name="annual DI",
        )

        oasdi = decimal_value(
            row[
                "washington_oasdi_receipts_dollars"
            ],
            field_name="annual OASDI",
        )

        hi = decimal_value(
            row[
                "washington_hi_receipts_dollars"
            ],
            field_name="annual HI",
        )

        total = decimal_value(
            row[
                "washington_social_insurance_receipts_dollars"
            ],
            field_name="annual total",
        )

        if oasdi != (
            oasi + di
        ):
            raise RuntimeError(
                "ANNUAL OASDI ARITHMETIC FAILURE\n"
                f"FY{row['fiscal_year']}"
            )

        if total != (
            oasi + di + hi
        ):
            raise RuntimeError(
                "ANNUAL TOTAL ARITHMETIC FAILURE\n"
                f"FY{row['fiscal_year']}"
            )

    return {
        "expected_rows": (
            EXPECTED_ANNUAL_ROWS
        ),
        "actual_rows": (
            len(annual_rows)
        ),
        "year_coverage": "PASS",
        "oasdi_arithmetic": "PASS",
        "annual_total_arithmetic": (
            "PASS"
        ),
    }


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        raise RuntimeError(
            f"Refusing to write empty CSV: {path}"
        )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(
                rows[0].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(rows)


def build_report(
    omb_profile: dict[str, Any],
    ssa_profile: dict[str, Any],
    detail_cert: dict[str, Any],
    annual_cert: dict[str, Any],
    annual_rows: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    lines.extend(
        [
            "=" * 100,
            (
                "WASHINGTON SOCIAL-INSURANCE "
                "RECEIPTS ALLOCATION - ETL-172F-3"
            ),
            "=" * 100,
            "",
            (
                "Allocation/certification only. "
                "No database writes, final receipts-ledger "
                "inclusion, forced IRS reconciliation, "
                "or Rockefeller dollar target."
            ),
            "",
            "CERTIFIED INPUTS",
            "-" * 100,
            (
                "OMB controls : "
                f"{omb_profile['path']}"
            ),
            (
                "OMB SHA256   : "
                f"{omb_profile['sha256']}"
            ),
            (
                "SSA shares   : "
                f"{ssa_profile['path']}"
            ),
            (
                "SSA SHA256   : "
                f"{ssa_profile['sha256']}"
            ),
            "",
            "ALLOCATION POLICY",
            "-" * 100,
            (
                "OASI = national OASI receipts "
                "x WA OASDI contribution share"
            ),
            (
                "DI   = national DI receipts "
                "x WA OASDI contribution share"
            ),
            (
                "HI   = national HI receipts "
                "x WA HI contribution share"
            ),
            "",
            (
                "FY2015-FY2023: contemporaneous "
                "certified SSA contribution shares"
            ),
            (
                "FY2024: certified 2023 SSA contribution "
                "share as latest available; lag explicitly "
                "preserved"
            ),
            "",
            "CERTIFICATION",
            "-" * 100,
            (
                "Detail observations          : "
                f"{detail_cert['actual_rows']} / "
                f"{detail_cert['expected_rows']}"
            ),
            (
                "Detail coverage              : "
                f"{detail_cert['coverage']}"
            ),
            (
                "Detail uniqueness            : "
                f"{detail_cert['uniqueness']}"
            ),
            (
                "OASI/DI share consistency    : "
                f"{detail_cert['oasi_di_share_consistency']}"
            ),
            (
                "Allocator timing policy      : "
                f"{detail_cert['allocator_timing_policy']}"
            ),
            (
                "Annual observations          : "
                f"{annual_cert['actual_rows']} / "
                f"{annual_cert['expected_rows']}"
            ),
            (
                "Annual arithmetic            : "
                f"{annual_cert['annual_total_arithmetic']}"
            ),
            "",
            "WASHINGTON RECEIPTS",
            "-" * 100,
            (
                "FY       OASI              DI"
                "              OASDI"
                "             HI"
                "                TOTAL"
            ),
            "-" * 100,
        ]
    )

    for row in annual_rows:
        oasi = Decimal(
            row[
                "washington_oasi_receipts_dollars"
            ]
        )
        di = Decimal(
            row[
                "washington_di_receipts_dollars"
            ]
        )
        oasdi = Decimal(
            row[
                "washington_oasdi_receipts_dollars"
            ]
        )
        hi = Decimal(
            row[
                "washington_hi_receipts_dollars"
            ]
        )
        total = Decimal(
            row[
                "washington_social_insurance_receipts_dollars"
            ]
        )

        lines.append(
            f"{row['fiscal_year']} "
            f"{oasi:>17,.0f} "
            f"{di:>15,.0f} "
            f"{oasdi:>17,.0f} "
            f"{hi:>17,.0f} "
            f"{total:>20,.0f}"
        )

    lines.extend(
        [
            "",
            "INTERPRETATION BOUNDARY",
            "-" * 100,
            (
                "These values are reconstructed Washington "
                "economic-incidence estimates produced from "
                "certified national OMB controls and certified "
                "SSA state contribution shares."
            ),
            (
                "They are not IRS administrative collections "
                "and are not forced to equal IRS gross collections."
            ),
            (
                "FY2024 uses the FY2023 SSA contribution share "
                "as a documented latest-available-data substitution."
            ),
            (
                "The FY2015 HI estimate retains the known "
                "SSA 2015 HI state-source limitation flag."
            ),
            (
                "This certification does not yet authorize "
                "final federal-receipts ledger inclusion."
            ),
            "",
            "ETL-172F-3 RESULT: PASS",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 100)
    print(
        "WASHINGTON SOCIAL-INSURANCE "
        "RECEIPTS ALLOCATION - ETL-172F-3"
    )
    print("=" * 100)
    print()
    print(
        "Allocation/certification only. No DB writes, "
        "final receipts-ledger inclusion, forced IRS "
        "reconciliation, or Rockefeller dollar target."
    )
    print()

    controls, omb_profile = (
        load_omb_controls()
    )

    allocators, ssa_profile = (
        load_ssa_allocators()
    )

    detail_rows = allocate(
        controls,
        allocators,
    )

    detail_cert = certify_detail(
        detail_rows
    )

    annual_rows = build_annual(
        detail_rows
    )

    annual_cert = certify_annual(
        annual_rows
    )

    write_csv(
        DETAIL_CSV,
        detail_rows,
    )

    write_csv(
        ANNUAL_CSV,
        annual_rows,
    )

    certification = {
        "etl_step": "ETL-172F-3",
        "result": "PASS",
        "purpose": (
            "Allocate certified national OASI, DI, "
            "and HI receipt controls to Washington "
            "using certified SSA contribution shares."
        ),
        "inputs": {
            "omb_controls": omb_profile,
            "ssa_allocators": ssa_profile,
        },
        "allocation_policy": {
            "OASI": (
                "OMB OASI x WA OASDI contribution share"
            ),
            "DI": (
                "OMB DI x WA OASDI contribution share"
            ),
            "HI": (
                "OMB HI x WA HI contribution share"
            ),
        },
        "allocator_year_policy": {
            str(year): (
                ALLOCATOR_YEAR_POLICY[
                    year
                ]
            )
            for year in TARGET_YEARS
        },
        "detail_certification": (
            detail_cert
        ),
        "annual_certification": (
            annual_cert
        ),
        "known_limitations": {
            "2015_HI": (
                KNOWN_LIMITATIONS[
                    (2015, "HI")
                ]
            ),
            "2024_allocator": (
                "SSA_2023_LATEST_AVAILABLE_SHARE"
            ),
        },
        "interpretation_boundary": {
            "database_writes": False,
            "final_ledger_inclusion_authorized": False,
            "forced_irs_reconciliation": False,
            "rockefeller_target_imposed": False,
        },
    }

    CERTIFICATION_JSON.write_text(
        json.dumps(
            certification,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        omb_profile,
        ssa_profile,
        detail_cert,
        annual_cert,
        annual_rows,
    )

    CERTIFICATION_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print("CERTIFIED INPUTS")
    print("-" * 100)
    print(
        f"OMB controls : {omb_profile['path']}"
    )
    print(
        f"OMB rows     : {omb_profile['rows']}"
    )
    print(
        f"OMB SHA256   : {omb_profile['sha256']}"
    )
    print()
    print(
        f"SSA shares   : {ssa_profile['path']}"
    )
    print(
        f"SSA rows     : {ssa_profile['rows']}"
    )
    print(
        f"SSA SHA256   : {ssa_profile['sha256']}"
    )
    print()

    print("ALLOCATION CERTIFICATION")
    print("-" * 100)
    print(
        f"Detail observations       : "
        f"{detail_cert['actual_rows']} / "
        f"{detail_cert['expected_rows']}"
    )
    print(
        f"Coverage                  : "
        f"{detail_cert['coverage']}"
    )
    print(
        f"Uniqueness                : "
        f"{detail_cert['uniqueness']}"
    )
    print(
        f"OASI/DI share consistency : "
        f"{detail_cert['oasi_di_share_consistency']}"
    )
    print(
        f"Allocator timing policy   : "
        f"{detail_cert['allocator_timing_policy']}"
    )
    print(
        f"Annual observations       : "
        f"{annual_cert['actual_rows']} / "
        f"{annual_cert['expected_rows']}"
    )
    print(
        f"Annual arithmetic         : "
        f"{annual_cert['annual_total_arithmetic']}"
    )
    print()

    print("WASHINGTON SOCIAL-INSURANCE RECEIPTS")
    print("-" * 100)
    print(
        f"{'FY':<6}"
        f"{'OASI':>18}"
        f"{'DI':>18}"
        f"{'OASDI':>18}"
        f"{'HI':>18}"
        f"{'TOTAL':>20}"
    )

    for row in annual_rows:
        oasi = Decimal(
            row[
                "washington_oasi_receipts_dollars"
            ]
        )
        di = Decimal(
            row[
                "washington_di_receipts_dollars"
            ]
        )
        oasdi = Decimal(
            row[
                "washington_oasdi_receipts_dollars"
            ]
        )
        hi = Decimal(
            row[
                "washington_hi_receipts_dollars"
            ]
        )
        total = Decimal(
            row[
                "washington_social_insurance_receipts_dollars"
            ]
        )

        print(
            f"{row['fiscal_year']:<6}"
            f"{oasi:>18,.0f}"
            f"{di:>18,.0f}"
            f"{oasdi:>18,.0f}"
            f"{hi:>18,.0f}"
            f"{total:>20,.0f}"
        )

    print()
    print(
        "FY2024 allocator year : 2023 "
        "(LATEST_AVAILABLE_SHARE)"
    )
    print(
        "FY2015 HI limitation  : "
        "preserved as source flag"
    )
    print()

    print(
        f"Detail : "
        f"{DETAIL_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"Annual : "
        f"{ANNUAL_CSV.relative_to(REPO_ROOT)}"
    )
    print(
        f"JSON   : "
        f"{CERTIFICATION_JSON.relative_to(REPO_ROOT)}"
    )
    print(
        f"Report : "
        f"{CERTIFICATION_REPORT.relative_to(REPO_ROOT)}"
    )
    print()
    print(
        "ETL-172F-3 RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())