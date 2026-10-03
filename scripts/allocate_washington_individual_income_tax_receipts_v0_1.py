from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any

import pandas as pd


# =============================================================================
# ETL-172G-3
# WASHINGTON INDIVIDUAL-INCOME-TAX RECEIPTS ALLOCATION
#
# Purpose:
#   Allocate certified national OMB Individual Income Taxes receipts to
#   Washington using certified IRS SOI Washington liability shares.
#
# Formula:
#
#       WA receipts_FFY
#           =
#       OMB national receipts_FFY
#           *
#       selected IRS WA liability share
#
# Principal WCFFBP historical mapping:
#
#   FFY2015 -> TY2015  CONTEMPORANEOUS_FINAL_SHARE
#   FFY2016 -> TY2016  CONTEMPORANEOUS_FINAL_SHARE
#   FFY2017 -> TY2017  CONTEMPORANEOUS_FINAL_SHARE
#   FFY2018 -> TY2018  CONTEMPORANEOUS_FINAL_SHARE
#   FFY2019 -> TY2019  CONTEMPORANEOUS_FINAL_SHARE
#   FFY2020 -> TY2020  CONTEMPORANEOUS_FINAL_SHARE
#   FFY2021 -> TY2021  CONTEMPORANEOUS_FINAL_SHARE
#   FFY2022 -> TY2022  CONTEMPORANEOUS_FINAL_SHARE
#   FFY2023 -> TY2023  CONTEMPORANEOUS_FINAL_SHARE
#   FFY2024 -> TY2023  LATEST_AVAILABLE_SHARE
#
# Interpretation:
#   This is the WCFFBP principal historical reconstruction using finalized
#   historical information available today.
#
#   It is NOT a Rockefeller-vintage replication. Rockefeller report vintages
#   used the latest IRS SOI liability shares available to the analysts at the
#   time, which could result in one tax-year share being applied to multiple
#   federal fiscal years.
#
# Boundaries:
#   - No Rockefeller-vintage replication.
#   - No forced reconciliation to IRS gross collections.
#   - No corporate-income-tax allocation.
#   - No database writes.
#   - No final receipts-ledger inclusion authorization.
# =============================================================================


getcontext().prec = 40


REPO_ROOT = Path(__file__).resolve().parents[1]


OMB_INPUT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "omb"
    / "historical_tables"
    / "FY2027"
    / "validation"
    / "individual_income_tax_receipt_controls_v0_1"
    / "national_individual_income_tax_receipt_controls.csv"
)


IRS_INPUT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "irs"
    / "historic_table_2"
    / "validation"
    / "individual_income_tax_allocator_certification_v0_1"
    / "washington_individual_income_tax_allocator.csv"
)


OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "irs"
    / "historic_table_2"
    / "validation"
    / "washington_individual_income_tax_receipts_v0_1"
)


OUTPUT_DETAIL = (
    OUTPUT_DIR
    / "washington_individual_income_tax_receipts.csv"
)


OUTPUT_JSON = (
    OUTPUT_DIR
    / "certification.json"
)


OUTPUT_REPORT = (
    OUTPUT_DIR
    / "certification_report.txt"
)


TARGET_FISCAL_YEARS = list(
    range(2015, 2025)
)


FISCAL_TO_TAX_YEAR = {
    2015: 2015,
    2016: 2016,
    2017: 2017,
    2018: 2018,
    2019: 2019,
    2020: 2020,
    2021: 2021,
    2022: 2022,
    2023: 2023,
    2024: 2023,
}


ALLOCATION_METHOD = {
    2015: "CONTEMPORANEOUS_FINAL_SHARE",
    2016: "CONTEMPORANEOUS_FINAL_SHARE",
    2017: "CONTEMPORANEOUS_FINAL_SHARE",
    2018: "CONTEMPORANEOUS_FINAL_SHARE",
    2019: "CONTEMPORANEOUS_FINAL_SHARE",
    2020: "CONTEMPORANEOUS_FINAL_SHARE",
    2021: "CONTEMPORANEOUS_FINAL_SHARE",
    2022: "CONTEMPORANEOUS_FINAL_SHARE",
    2023: "CONTEMPORANEOUS_FINAL_SHARE",
    2024: "LATEST_AVAILABLE_SHARE",
}


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest().upper()


def decimal_from_value(
    value: Any,
    *,
    context: str,
) -> Decimal:
    if value is None:
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: value is NULL"
        )

    if isinstance(
        value,
        bool,
    ):
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: boolean value"
        )

    try:
        if pd.isna(value):
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: value is NA"
            )
    except TypeError:
        pass

    if isinstance(
        value,
        Decimal,
    ):
        result = value

    elif isinstance(
        value,
        int,
    ):
        result = Decimal(
            value
        )

    elif isinstance(
        value,
        float,
    ):
        if not math.isfinite(
            value
        ):
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: non-finite value"
            )

        result = Decimal(
            str(value)
        )

    else:
        text = (
            str(value)
            .strip()
            .replace(",", "")
        )

        if not text:
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: blank value"
            )

        try:
            result = Decimal(
                text
            )
        except InvalidOperation as exc:
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: "
                f"non-numeric value {value!r}"
            ) from exc

    if not result.is_finite():
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: non-finite Decimal"
        )

    return result


def plain_decimal(
    value: Decimal,
) -> str:
    return format(
        value,
        "f",
    )


def certify_inputs() -> dict[str, Any]:
    missing = [
        path
        for path in [
            OMB_INPUT,
            IRS_INPUT,
        ]
        if not path.exists()
    ]

    if missing:
        raise RuntimeError(
            "INPUT COVERAGE FAILURE\n"
            + "\n".join(
                str(
                    path.relative_to(
                        REPO_ROOT
                    )
                )
                for path in missing
            )
        )

    return {
        "omb": {
            "path": str(
                OMB_INPUT.relative_to(
                    REPO_ROOT
                )
            ),
            "bytes": (
                OMB_INPUT.stat().st_size
            ),
            "sha256": (
                sha256_file(
                    OMB_INPUT
                )
            ),
        },
        "irs": {
            "path": str(
                IRS_INPUT.relative_to(
                    REPO_ROOT
                )
            ),
            "bytes": (
                IRS_INPUT.stat().st_size
            ),
            "sha256": (
                sha256_file(
                    IRS_INPUT
                )
            ),
        },
    }


def load_omb() -> pd.DataFrame:
    frame = pd.read_csv(
        OMB_INPUT,
        dtype=str,
        keep_default_na=False,
    )

    required = {
        "fiscal_year",
        "receipt_series",
        "national_receipts_dollars",
    }

    missing = sorted(
        required
        - set(
            frame.columns
        )
    )

    if missing:
        raise RuntimeError(
            "OMB SCHEMA CERTIFICATION FAILURE\n"
            f"Missing columns: {missing}"
        )

    if len(frame) != len(
        TARGET_FISCAL_YEARS
    ):
        raise RuntimeError(
            "OMB OBSERVATION COUNT FAILURE\n"
            f"Expected "
            f"{len(TARGET_FISCAL_YEARS)}; "
            f"found {len(frame)}"
        )

    frame[
        "fiscal_year_int"
    ] = frame[
        "fiscal_year"
    ].astype(
        int
    )

    years = sorted(
        frame[
            "fiscal_year_int"
        ].tolist()
    )

    if years != TARGET_FISCAL_YEARS:
        raise RuntimeError(
            "OMB YEAR COVERAGE FAILURE\n"
            f"Expected: "
            f"{TARGET_FISCAL_YEARS}\n"
            f"Actual  : {years}"
        )

    if (
        frame[
            "fiscal_year_int"
        ].duplicated()
        .any()
    ):
        raise RuntimeError(
            "OMB YEAR UNIQUENESS FAILURE"
        )

    series_values = set(
        frame[
            "receipt_series"
        ].str.strip()
    )

    if series_values != {
        "INDIVIDUAL_INCOME_TAX"
    }:
        raise RuntimeError(
            "OMB SERIES CERTIFICATION FAILURE\n"
            f"Actual values: "
            f"{sorted(series_values)}"
        )

    return frame


def load_irs() -> pd.DataFrame:
    frame = pd.read_csv(
        IRS_INPUT,
        dtype=str,
        keep_default_na=False,
    )

    required = {
        "tax_year",
        "wa_liability_share",
        "allocator_status",
        "source_file",
        "source_sha256",
    }

    missing = sorted(
        required
        - set(
            frame.columns
        )
    )

    if missing:
        raise RuntimeError(
            "IRS SCHEMA CERTIFICATION FAILURE\n"
            f"Missing columns: {missing}"
        )

    frame[
        "tax_year_int"
    ] = frame[
        "tax_year"
    ].astype(
        int
    )

    expected_tax_years = list(
        range(2015, 2024)
    )

    years = sorted(
        frame[
            "tax_year_int"
        ].tolist()
    )

    if years != expected_tax_years:
        raise RuntimeError(
            "IRS TAX-YEAR COVERAGE FAILURE\n"
            f"Expected: "
            f"{expected_tax_years}\n"
            f"Actual  : {years}"
        )

    if (
        frame[
            "tax_year_int"
        ].duplicated()
        .any()
    ):
        raise RuntimeError(
            "IRS TAX-YEAR UNIQUENESS FAILURE"
        )

    statuses = set(
        frame[
            "allocator_status"
        ].str.strip()
    )

    if statuses != {
        "CONTEMPORANEOUS_TAX_YEAR_SHARE"
    }:
        raise RuntimeError(
            "IRS ALLOCATOR STATUS FAILURE\n"
            f"Actual values: "
            f"{sorted(statuses)}"
        )

    return frame


def certify_mapping() -> None:
    if sorted(
        FISCAL_TO_TAX_YEAR.keys()
    ) != TARGET_FISCAL_YEARS:
        raise RuntimeError(
            "MAPPING COVERAGE FAILURE"
        )

    if sorted(
        ALLOCATION_METHOD.keys()
    ) != TARGET_FISCAL_YEARS:
        raise RuntimeError(
            "ALLOCATION METHOD COVERAGE FAILURE"
        )

    for fiscal_year in range(
        2015,
        2024,
    ):
        if (
            FISCAL_TO_TAX_YEAR[
                fiscal_year
            ]
            != fiscal_year
        ):
            raise RuntimeError(
                "CONTEMPORANEOUS MAPPING FAILURE\n"
                f"FFY{fiscal_year} mapped to "
                f"TY"
                f"{FISCAL_TO_TAX_YEAR[fiscal_year]}"
            )

        if (
            ALLOCATION_METHOD[
                fiscal_year
            ]
            != "CONTEMPORANEOUS_FINAL_SHARE"
        ):
            raise RuntimeError(
                "CONTEMPORANEOUS METHOD FAILURE\n"
                f"FFY{fiscal_year}"
            )

    if (
        FISCAL_TO_TAX_YEAR[
            2024
        ]
        != 2023
    ):
        raise RuntimeError(
            "FY2024 CARRY-FORWARD FAILURE"
        )

    if (
        ALLOCATION_METHOD[
            2024
        ]
        != "LATEST_AVAILABLE_SHARE"
    ):
        raise RuntimeError(
            "FY2024 METHOD FAILURE"
        )


def allocate(
    omb: pd.DataFrame,
    irs: pd.DataFrame,
) -> list[dict[str, Any]]:
    omb_by_year = {
        int(
            row[
                "fiscal_year_int"
            ]
        ): row
        for _, row in (
            omb.iterrows()
        )
    }

    irs_by_year = {
        int(
            row[
                "tax_year_int"
            ]
        ): row
        for _, row in (
            irs.iterrows()
        )
    }

    rows: list[
        dict[str, Any]
    ] = []

    for fiscal_year in (
        TARGET_FISCAL_YEARS
    ):
        tax_year = (
            FISCAL_TO_TAX_YEAR[
                fiscal_year
            ]
        )

        if tax_year not in irs_by_year:
            raise RuntimeError(
                "ALLOCATOR LOOKUP FAILURE\n"
                f"FFY{fiscal_year}: "
                f"TY{tax_year} not found"
            )

        omb_row = omb_by_year[
            fiscal_year
        ]

        irs_row = irs_by_year[
            tax_year
        ]

        national_receipts = (
            decimal_from_value(
                omb_row[
                    "national_receipts_dollars"
                ],
                context=(
                    f"FFY{fiscal_year} "
                    "national receipts"
                ),
            )
        )

        share = (
            decimal_from_value(
                irs_row[
                    "wa_liability_share"
                ],
                context=(
                    f"TY{tax_year} "
                    "WA liability share"
                ),
            )
        )

        if national_receipts < 0:
            raise RuntimeError(
                "NEGATIVE NATIONAL CONTROL FAILURE\n"
                f"FFY{fiscal_year}"
            )

        if not (
            Decimal("0")
            <= share
            <= Decimal("1")
        ):
            raise RuntimeError(
                "ALLOCATOR RANGE FAILURE\n"
                f"TY{tax_year}: "
                f"{share}"
            )

        washington_receipts = (
            national_receipts
            * share
        )

        rows.append(
            {
                "fiscal_year": (
                    fiscal_year
                ),
                "receipt_series": (
                    "INDIVIDUAL_INCOME_TAX"
                ),
                "national_receipts_dollars": (
                    plain_decimal(
                        national_receipts
                    )
                ),
                "allocator_tax_year": (
                    tax_year
                ),
                "wa_liability_share": (
                    plain_decimal(
                        share
                    )
                ),
                "wa_liability_share_percent": (
                    plain_decimal(
                        share
                        * Decimal("100")
                    )
                ),
                "allocation_method": (
                    ALLOCATION_METHOD[
                        fiscal_year
                    ]
                ),
                "washington_receipts_dollars": (
                    plain_decimal(
                        washington_receipts
                    )
                ),
                "omb_source_file": (
                    str(
                        OMB_INPUT.relative_to(
                            REPO_ROOT
                        )
                    )
                ),
                "irs_allocator_source_file": (
                    irs_row[
                        "source_file"
                    ]
                ),
                "irs_allocator_source_sha256": (
                    irs_row[
                        "source_sha256"
                    ]
                ),
                "rockefeller_replication": (
                    "NO"
                ),
                "ledger_status": (
                    "NOT_YET_AUTHORIZED"
                ),
            }
        )

    return rows


def certify_allocations(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(
        rows
    ) != len(
        TARGET_FISCAL_YEARS
    ):
        raise RuntimeError(
            "OUTPUT OBSERVATION COUNT FAILURE"
        )

    years = [
        int(
            row[
                "fiscal_year"
            ]
        )
        for row in rows
    ]

    if years != TARGET_FISCAL_YEARS:
        raise RuntimeError(
            "OUTPUT YEAR COVERAGE FAILURE\n"
            f"Expected: "
            f"{TARGET_FISCAL_YEARS}\n"
            f"Actual  : {years}"
        )

    if len(
        set(
            years
        )
    ) != len(
        years
    ):
        raise RuntimeError(
            "OUTPUT YEAR UNIQUENESS FAILURE"
        )

    for row in rows:
        fiscal_year = int(
            row[
                "fiscal_year"
            ]
        )

        national = (
            Decimal(
                row[
                    "national_receipts_dollars"
                ]
            )
        )

        share = (
            Decimal(
                row[
                    "wa_liability_share"
                ]
            )
        )

        allocated = (
            Decimal(
                row[
                    "washington_receipts_dollars"
                ]
            )
        )

        recomputed = (
            national
            * share
        )

        if allocated != recomputed:
            raise RuntimeError(
                "ALLOCATION ARITHMETIC FAILURE\n"
                f"FFY{fiscal_year}"
            )

        expected_tax_year = (
            FISCAL_TO_TAX_YEAR[
                fiscal_year
            ]
        )

        if int(
            row[
                "allocator_tax_year"
            ]
        ) != expected_tax_year:
            raise RuntimeError(
                "ALLOCATOR YEAR FAILURE\n"
                f"FFY{fiscal_year}"
            )

        expected_method = (
            ALLOCATION_METHOD[
                fiscal_year
            ]
        )

        if (
            row[
                "allocation_method"
            ]
            != expected_method
        ):
            raise RuntimeError(
                "ALLOCATION METHOD FAILURE\n"
                f"FFY{fiscal_year}"
            )

        if (
            row[
                "rockefeller_replication"
            ]
            != "NO"
        ):
            raise RuntimeError(
                "ROCKEFELLER REPLICATION "
                "BOUNDARY FAILURE"
            )

    return {
        "expected_observations": (
            len(
                TARGET_FISCAL_YEARS
            )
        ),
        "actual_observations": (
            len(
                rows
            )
        ),
        "fiscal_year_coverage": (
            "PASS"
        ),
        "fiscal_year_uniqueness": (
            "PASS"
        ),
        "mapping_certification": (
            "PASS"
        ),
        "allocation_arithmetic": (
            "PASS"
        ),
        "fy2024_carry_forward": (
            "PASS"
        ),
        "rockefeller_replication_boundary": (
            "PASS"
        ),
    }


def write_csv(
    path: Path,
    rows: list[
        dict[str, Any]
    ],
) -> None:
    if not rows:
        raise RuntimeError(
            "Refusing to write empty output."
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

        writer.writerows(
            rows
        )


def build_report(
    input_profile: dict[str, Any],
    certification: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    lines.extend(
        [
            "=" * 100,
            (
                "WASHINGTON INDIVIDUAL-INCOME-TAX "
                "RECEIPTS ALLOCATION - ETL-172G-3"
            ),
            "=" * 100,
            "",
            (
                "WCFFBP principal historical reconstruction. "
                "Not a Rockefeller-vintage replication."
            ),
            "",
            "INPUT CERTIFICATION",
            "-" * 100,
            (
                "OMB input : "
                f"{input_profile['omb']['path']}"
            ),
            (
                "OMB SHA256: "
                f"{input_profile['omb']['sha256']}"
            ),
            (
                "IRS input : "
                f"{input_profile['irs']['path']}"
            ),
            (
                "IRS SHA256: "
                f"{input_profile['irs']['sha256']}"
            ),
            "",
            "METHOD",
            "-" * 100,
            (
                "WA receipts = "
                "OMB national Individual Income Taxes receipts "
                "* WA IRS SOI liability share"
            ),
            (
                "Liability allocator = "
                "A06500 + A85530 + A85300"
            ),
            (
                "FFY2015-FFY2023 use the corresponding "
                "finalized tax-year share."
            ),
            (
                "FFY2024 uses TY2023 as the latest "
                "certified available share."
            ),
            "",
            "CERTIFICATION",
            "-" * 100,
            (
                "Expected observations          : "
                f"{certification['expected_observations']}"
            ),
            (
                "Actual observations            : "
                f"{certification['actual_observations']}"
            ),
            (
                "Fiscal-year coverage           : "
                f"{certification['fiscal_year_coverage']}"
            ),
            (
                "Fiscal-year uniqueness         : "
                f"{certification['fiscal_year_uniqueness']}"
            ),
            (
                "FFY-to-TY mapping              : "
                f"{certification['mapping_certification']}"
            ),
            (
                "Allocation arithmetic          : "
                f"{certification['allocation_arithmetic']}"
            ),
            (
                "FFY2024 TY2023 carry-forward   : "
                f"{certification['fy2024_carry_forward']}"
            ),
            (
                "Rockefeller replication boundary: "
                f"{certification['rockefeller_replication_boundary']}"
            ),
            "",
            "WASHINGTON INDIVIDUAL-INCOME-TAX RECEIPTS",
            "-" * 100,
            (
                f"{'FFY':<6}"
                f"{'TY':<6}"
                f"{'NATIONAL':>20}"
                f"{'WA SHARE':>14}"
                f"{'WA RECEIPTS':>20}"
                f"{'METHOD':>30}"
            ),
            "-" * 100,
        ]
    )

    for row in rows:
        national = Decimal(
            row[
                "national_receipts_dollars"
            ]
        )

        share = Decimal(
            row[
                "wa_liability_share"
            ]
        )

        wa_receipts = Decimal(
            row[
                "washington_receipts_dollars"
            ]
        )

        lines.append(
            f"{row['fiscal_year']:<6}"
            f"{row['allocator_tax_year']:<6}"
            f"{national:>20,.0f}"
            f"{share:>14.8%}"
            f"{wa_receipts:>20,.0f}"
            f"{row['allocation_method']:>30}"
        )

    lines.extend(
        [
            "",
            "INTERPRETATION BOUNDARY",
            "-" * 100,
            (
                "These values estimate Washington's share "
                "of national federal Individual Income Taxes "
                "receipts using IRS SOI tax-liability shares."
            ),
            (
                "They are an economic-incidence allocation "
                "series, not IRS administrative collections "
                "recorded in Washington."
            ),
            (
                "They must therefore be compared with, not "
                "added to, the ETL-171 IRS gross-collections "
                "benchmark."
            ),
            (
                "This series does not reproduce the information "
                "set of a particular Rockefeller report vintage."
            ),
            (
                "No corporate-income-tax receipts are included."
            ),
            (
                "Final receipts-ledger inclusion remains "
                "unauthorized pending broader ETL-172 "
                "receipts reconciliation."
            ),
            "",
            "ETL-172G-3 RESULT: PASS",
            "",
        ]
    )

    return "\n".join(
        lines
    )


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "=" * 100
    )
    print(
        "WASHINGTON INDIVIDUAL-INCOME-TAX "
        "RECEIPTS ALLOCATION - ETL-172G-3"
    )
    print(
        "=" * 100
    )
    print()
    print(
        "WCFFBP principal historical reconstruction. "
        "Not a Rockefeller-vintage replication."
    )
    print()

    input_profile = (
        certify_inputs()
    )

    certify_mapping()

    omb = load_omb()

    irs = load_irs()

    rows = allocate(
        omb,
        irs,
    )

    certification = (
        certify_allocations(
            rows
        )
    )

    write_csv(
        OUTPUT_DETAIL,
        rows,
    )

    payload = {
        "etl_step": (
            "ETL-172G-3"
        ),
        "result": (
            "PASS"
        ),
        "series": (
            "WASHINGTON_INDIVIDUAL_INCOME_TAX_RECEIPTS"
        ),
        "accounting_role": (
            "FEDERAL_RECEIPTS_OUTFLOW"
        ),
        "reconstruction_type": (
            "WCFFBP_PRINCIPAL_HISTORICAL"
        ),
        "rockefeller_replication": (
            False
        ),
        "inputs": (
            input_profile
        ),
        "method": {
            "formula": (
                "OMB national Individual Income Taxes "
                "* Washington IRS SOI liability share"
            ),
            "liability_formula": (
                "A06500 + A85530 + A85300"
            ),
            "mapping": {
                str(
                    fiscal_year
                ): {
                    "tax_year": (
                        FISCAL_TO_TAX_YEAR[
                            fiscal_year
                        ]
                    ),
                    "allocation_method": (
                        ALLOCATION_METHOD[
                            fiscal_year
                        ]
                    ),
                }
                for fiscal_year in (
                    TARGET_FISCAL_YEARS
                )
            },
        },
        "certification": (
            certification
        ),
        "interpretation_boundary": {
            "irs_gross_collections_additive": (
                False
            ),
            "corporate_income_tax_included": (
                False
            ),
            "rockefeller_vintage_replication": (
                False
            ),
            "database_writes": (
                False
            ),
            "final_ledger_inclusion_authorized": (
                False
            ),
        },
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        input_profile,
        certification,
        rows,
    )

    OUTPUT_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print(
        "INPUT CERTIFICATION"
    )
    print(
        "-" * 100
    )
    print(
        f"OMB input : "
        f"{input_profile['omb']['path']}"
    )
    print(
        f"OMB SHA256: "
        f"{input_profile['omb']['sha256']}"
    )
    print(
        f"IRS input : "
        f"{input_profile['irs']['path']}"
    )
    print(
        f"IRS SHA256: "
        f"{input_profile['irs']['sha256']}"
    )
    print()

    print(
        "METHOD"
    )
    print(
        "-" * 100
    )
    print(
        "WA receipts = "
        "OMB national Individual Income Taxes receipts "
        "* WA IRS SOI liability share"
    )
    print(
        "Liability allocator = "
        "A06500 + A85530 + A85300"
    )
    print(
        "FFY2015-FFY2023 = corresponding finalized TY share"
    )
    print(
        "FFY2024 = TY2023 latest certified available share"
    )
    print()

    print(
        "CERTIFICATION"
    )
    print(
        "-" * 100
    )
    print(
        f"Expected observations          : "
        f"{certification['expected_observations']}"
    )
    print(
        f"Actual observations            : "
        f"{certification['actual_observations']}"
    )
    print(
        f"Fiscal-year coverage           : "
        f"{certification['fiscal_year_coverage']}"
    )
    print(
        f"Fiscal-year uniqueness         : "
        f"{certification['fiscal_year_uniqueness']}"
    )
    print(
        f"FFY-to-TY mapping              : "
        f"{certification['mapping_certification']}"
    )
    print(
        f"Allocation arithmetic          : "
        f"{certification['allocation_arithmetic']}"
    )
    print(
        f"FFY2024 TY2023 carry-forward   : "
        f"{certification['fy2024_carry_forward']}"
    )
    print(
        f"Rockefeller replication boundary: "
        f"{certification['rockefeller_replication_boundary']}"
    )
    print()

    print(
        "WASHINGTON INDIVIDUAL-INCOME-TAX RECEIPTS"
    )
    print(
        "-" * 100
    )
    print(
        f"{'FFY':<6}"
        f"{'TY':<6}"
        f"{'NATIONAL':>20}"
        f"{'WA SHARE':>14}"
        f"{'WA RECEIPTS':>20}"
        f"{'METHOD':>30}"
    )

    for row in rows:
        national = Decimal(
            row[
                "national_receipts_dollars"
            ]
        )

        share = Decimal(
            row[
                "wa_liability_share"
            ]
        )

        wa_receipts = Decimal(
            row[
                "washington_receipts_dollars"
            ]
        )

        print(
            f"{row['fiscal_year']:<6}"
            f"{row['allocator_tax_year']:<6}"
            f"{national:>20,.0f}"
            f"{share:>14.8%}"
            f"{wa_receipts:>20,.0f}"
            f"{row['allocation_method']:>30}"
        )

    print()
    print(
        f"Output : "
        f"{OUTPUT_DETAIL.relative_to(REPO_ROOT)}"
    )
    print(
        f"JSON   : "
        f"{OUTPUT_JSON.relative_to(REPO_ROOT)}"
    )
    print(
        f"Report : "
        f"{OUTPUT_REPORT.relative_to(REPO_ROOT)}"
    )
    print()
    print(
        "ETL-172G-3 RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )