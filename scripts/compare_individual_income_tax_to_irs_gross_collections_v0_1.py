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
# ETL-172G-4
# IRS GROSS COLLECTIONS / ECONOMIC-INCIDENCE DIAGNOSTIC BRIDGE
#
# Purpose:
#   Compare the certified WCFFBP Washington individual-income-tax
#   economic-incidence allocation with certified IRS Washington gross
#   collections controls.
#
# IMPORTANT:
#   This is a diagnostic comparison, NOT a reconciliation.
#
#   ETL-172G-3:
#       Economic-incidence allocation of national Individual Income Taxes
#       receipts using Washington's IRS SOI tax-liability share.
#
#   ETL-171:
#       IRS administrative gross collections attributed to Washington.
#
#   IRS Table 5 does NOT provide a directly equivalent individual-income-tax
#   administrative series. Its narrower relevant category combines:
#
#       individual income tax
#       + employment taxes
#       + estate/trust income tax
#
# Therefore:
#   - differences are DIAGNOSTIC_ONLY;
#   - ratios are DIAGNOSTIC_ONLY;
#   - differences are NOT residuals, errors, gaps, or unexplained amounts;
#   - ETL-171 and ETL-172G-3 are NOT additive.
#
# Boundaries:
#   - No forced reconciliation.
#   - No employment-tax subtraction.
#   - No corporate-income-tax allocation.
#   - No Rockefeller-vintage replication.
#   - No database writes.
#   - No final receipts-ledger inclusion authorization.
# =============================================================================


getcontext().prec = 40


REPO_ROOT = Path(__file__).resolve().parents[1]


G3_INPUT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "irs"
    / "historic_table_2"
    / "validation"
    / "washington_individual_income_tax_receipts_v0_1"
    / "washington_individual_income_tax_receipts.csv"
)


IRS_SEMANTIC_INPUT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "irs"
    / "gross_collections"
    / "validation"
    / "semantic_certification_v0_1"
    / "washington_semantic_extract.csv"
)


IRS_RECON_INPUT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "irs"
    / "gross_collections"
    / "validation"
    / "semantic_certification_v0_1"
    / "washington_reconciliation.csv"
)


OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "irs"
    / "historic_table_2"
    / "validation"
    / "individual_income_tax_gross_collections_bridge_v0_1"
)


OUTPUT_DETAIL = (
    OUTPUT_DIR
    / "washington_individual_income_tax_gross_collections_bridge.csv"
)


OUTPUT_JSON = (
    OUTPUT_DIR
    / "certification.json"
)


OUTPUT_REPORT = (
    OUTPUT_DIR
    / "certification_report.txt"
)


TARGET_YEARS = list(
    range(2015, 2025)
)


COMPARISON_STATUS = "DIAGNOSTIC_ONLY"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest().upper()


def decimal_from_value(
    value: Any,
    *,
    context: str,
) -> Decimal:
    if value is None:
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: NULL"
        )

    if isinstance(value, bool):
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: boolean"
        )

    try:
        if pd.isna(value):
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: NA"
            )
    except TypeError:
        pass

    if isinstance(value, Decimal):
        result = value

    elif isinstance(value, int):
        result = Decimal(value)

    elif isinstance(value, float):
        if not math.isfinite(value):
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: non-finite"
            )

        result = Decimal(str(value))

    else:
        text = (
            str(value)
            .strip()
            .replace(",", "")
        )

        if not text:
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: blank"
            )

        try:
            result = Decimal(text)
        except InvalidOperation as exc:
            raise RuntimeError(
                "NUMERIC CERTIFICATION FAILURE\n"
                f"{context}: non-numeric {value!r}"
            ) from exc

    if not result.is_finite():
        raise RuntimeError(
            "NUMERIC CERTIFICATION FAILURE\n"
            f"{context}: non-finite Decimal"
        )

    return result


def plain_decimal(value: Decimal) -> str:
    return format(value, "f")


def certify_inputs() -> dict[str, Any]:
    inputs = {
        "g3": G3_INPUT,
        "irs_semantic": IRS_SEMANTIC_INPUT,
        "irs_reconciliation": IRS_RECON_INPUT,
    }

    missing = [
        path
        for path in inputs.values()
        if not path.exists()
    ]

    if missing:
        raise RuntimeError(
            "INPUT COVERAGE FAILURE\n"
            + "\n".join(
                str(path.relative_to(REPO_ROOT))
                for path in missing
            )
        )

    return {
        name: {
            "path": str(
                path.relative_to(REPO_ROOT)
            ),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for name, path in inputs.items()
    }


def certify_years(
    frame: pd.DataFrame,
    *,
    year_column: str,
    label: str,
) -> None:
    years = frame[
        year_column
    ].astype(int).tolist()

    if sorted(years) != TARGET_YEARS:
        raise RuntimeError(
            f"{label} YEAR COVERAGE FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {sorted(years)}"
        )

    if len(set(years)) != len(years):
        raise RuntimeError(
            f"{label} YEAR UNIQUENESS FAILURE"
        )


def load_g3() -> pd.DataFrame:
    frame = pd.read_csv(
        G3_INPUT,
        dtype=str,
        keep_default_na=False,
    )

    required = {
        "fiscal_year",
        "receipt_series",
        "national_receipts_dollars",
        "allocator_tax_year",
        "wa_liability_share",
        "allocation_method",
        "washington_receipts_dollars",
        "rockefeller_replication",
        "ledger_status",
    }

    missing = sorted(
        required - set(frame.columns)
    )

    if missing:
        raise RuntimeError(
            "G3 SCHEMA CERTIFICATION FAILURE\n"
            f"Missing columns: {missing}"
        )

    if len(frame) != 10:
        raise RuntimeError(
            "G3 OBSERVATION COUNT FAILURE\n"
            f"Expected 10; found {len(frame)}"
        )

    certify_years(
        frame,
        year_column="fiscal_year",
        label="G3",
    )

    series = set(
        frame["receipt_series"].str.strip()
    )

    if series != {
        "INDIVIDUAL_INCOME_TAX"
    }:
        raise RuntimeError(
            "G3 SERIES CERTIFICATION FAILURE\n"
            f"Actual: {sorted(series)}"
        )

    rockefeller = set(
        frame[
            "rockefeller_replication"
        ].str.strip().str.upper()
    )

    if rockefeller != {"NO"}:
        raise RuntimeError(
            "G3 ROCKEFELLER BOUNDARY FAILURE\n"
            f"Actual: {sorted(rockefeller)}"
        )

    return frame


def load_irs_semantic() -> pd.DataFrame:
    frame = pd.read_csv(
        IRS_SEMANTIC_INPUT,
        dtype=str,
        keep_default_na=False,
    )

    required = {
        "fiscal_year",
        "source_file",
        "source_sha256",
        "source_units",
        "dollar_conversion_factor",
        "total_internal_revenue_collections_dollars",
        "business_income_taxes_dollars",
        "individual_income_employment_estate_trust_total_dollars",
        "individual_income_tax_withheld_and_fica_dollars",
        "individual_income_tax_payments_and_seca_dollars",
        "unemployment_insurance_tax_dollars",
        "railroad_retirement_tax_dollars",
        "estate_and_trust_income_tax_dollars",
        "estate_tax_dollars",
        "gift_tax_dollars",
        "excise_taxes_dollars",
        "nested_identity_status",
        "top_level_identity_status",
    }

    missing = sorted(
        required - set(frame.columns)
    )

    if missing:
        raise RuntimeError(
            "IRS SEMANTIC SCHEMA FAILURE\n"
            f"Missing columns: {missing}"
        )

    if len(frame) != 10:
        raise RuntimeError(
            "IRS SEMANTIC OBSERVATION COUNT FAILURE\n"
            f"Expected 10; found {len(frame)}"
        )

    certify_years(
        frame,
        year_column="fiscal_year",
        label="IRS SEMANTIC",
    )

    allowed_identity_statuses = {
        "EXACT_PASS",
        "PUBLICATION_PRECISION_PASS",
    }

    nested_status = set(
        frame[
            "nested_identity_status"
        ].str.strip().str.upper()
    )

    top_status = set(
        frame[
            "top_level_identity_status"
        ].str.strip().str.upper()
    )

    unexpected_nested_statuses = (
        nested_status
        - allowed_identity_statuses
    )

    unexpected_top_statuses = (
        top_status
        - allowed_identity_statuses
    )

    if unexpected_nested_statuses:
        raise RuntimeError(
            "IRS NESTED IDENTITY STATUS FAILURE\n"
            "Allowed statuses: "
            f"{sorted(allowed_identity_statuses)}\n"
            "Actual statuses : "
            f"{sorted(nested_status)}\n"
            "Unexpected      : "
            f"{sorted(unexpected_nested_statuses)}"
        )

    if unexpected_top_statuses:
        raise RuntimeError(
            "IRS TOP-LEVEL IDENTITY STATUS FAILURE\n"
            "Allowed statuses: "
            f"{sorted(allowed_identity_statuses)}\n"
            "Actual statuses : "
            f"{sorted(top_status)}\n"
            "Unexpected      : "
            f"{sorted(unexpected_top_statuses)}"
        )

    return frame


def load_irs_reconciliation() -> pd.DataFrame:
    frame = pd.read_csv(
        IRS_RECON_INPUT,
        dtype=str,
        keep_default_na=False,
    )

    required = {
        "fiscal_year",
        "irs_source_total_dollars",
        "reporting_control_dollars",
        "difference_dollars",
        "reconciliation_status",
    }

    missing = sorted(
        required - set(frame.columns)
    )

    if missing:
        raise RuntimeError(
            "IRS RECONCILIATION SCHEMA FAILURE\n"
            f"Missing columns: {missing}"
        )

    if len(frame) != 10:
        raise RuntimeError(
            "IRS RECONCILIATION OBSERVATION COUNT FAILURE\n"
            f"Expected 10; found {len(frame)}"
        )

    certify_years(
        frame,
        year_column="fiscal_year",
        label="IRS RECONCILIATION",
    )

    statuses = set(
        frame[
            "reconciliation_status"
        ].str.strip().str.upper()
    )

    if statuses != {"PASS"}:
        raise RuntimeError(
            "IRS RECONCILIATION STATUS FAILURE\n"
            f"Actual: {sorted(statuses)}"
        )

    for _, row in frame.iterrows():
        difference = decimal_from_value(
            row["difference_dollars"],
            context=(
                f"FFY{row['fiscal_year']} "
                "IRS reconciliation difference"
            ),
        )

        if difference != 0:
            raise RuntimeError(
                "IRS RECONCILIATION DIFFERENCE FAILURE\n"
                f"FFY{row['fiscal_year']}: {difference}"
            )

    return frame


def build_bridge(
    g3: pd.DataFrame,
    irs_semantic: pd.DataFrame,
    irs_recon: pd.DataFrame,
) -> list[dict[str, Any]]:
    g3_by_year = {
        int(row["fiscal_year"]): row
        for _, row in g3.iterrows()
    }

    semantic_by_year = {
        int(row["fiscal_year"]): row
        for _, row in irs_semantic.iterrows()
    }

    recon_by_year = {
        int(row["fiscal_year"]): row
        for _, row in irs_recon.iterrows()
    }

    rows: list[dict[str, Any]] = []

    for year in TARGET_YEARS:
        g3_row = g3_by_year[year]
        irs_row = semantic_by_year[year]
        recon_row = recon_by_year[year]

        allocated = decimal_from_value(
            g3_row[
                "washington_receipts_dollars"
            ],
            context=(
                f"FFY{year} allocated "
                "individual income tax"
            ),
        )

        irs_total = decimal_from_value(
            irs_row[
                "total_internal_revenue_collections_dollars"
            ],
            context=(
                f"FFY{year} IRS total"
            ),
        )

        irs_combined = decimal_from_value(
            irs_row[
                "individual_income_employment_estate_trust_total_dollars"
            ],
            context=(
                f"FFY{year} IRS combined category"
            ),
        )

        reporting_control = decimal_from_value(
            recon_row[
                "reporting_control_dollars"
            ],
            context=(
                f"FFY{year} reporting control"
            ),
        )

        if irs_total != reporting_control:
            raise RuntimeError(
                "IRS CONTROL CROSS-CHECK FAILURE\n"
                f"FFY{year}: semantic total "
                f"{irs_total} != reporting control "
                f"{reporting_control}"
            )

        if irs_total <= 0:
            raise RuntimeError(
                "IRS TOTAL DENOMINATOR FAILURE\n"
                f"FFY{year}"
            )

        if irs_combined <= 0:
            raise RuntimeError(
                "IRS COMBINED DENOMINATOR FAILURE\n"
                f"FFY{year}"
            )

        difference_total = (
            allocated - irs_total
        )

        difference_combined = (
            allocated - irs_combined
        )

        ratio_total = (
            allocated / irs_total
        )

        ratio_combined = (
            allocated / irs_combined
        )

        def irs_value(column: str) -> Decimal:
            return decimal_from_value(
                irs_row[column],
                context=(
                    f"FFY{year} {column}"
                ),
            )

        rows.append(
            {
                "fiscal_year": year,
                "wcffbp_individual_income_tax_receipts_dollars": (
                    plain_decimal(allocated)
                ),
                "wcffbp_allocator_tax_year": (
                    g3_row["allocator_tax_year"]
                ),
                "wcffbp_allocation_method": (
                    g3_row["allocation_method"]
                ),
                "irs_total_gross_collections_dollars": (
                    plain_decimal(irs_total)
                ),
                "irs_business_income_taxes_dollars": (
                    plain_decimal(
                        irs_value(
                            "business_income_taxes_dollars"
                        )
                    )
                ),
                "irs_individual_employment_estate_trust_total_dollars": (
                    plain_decimal(irs_combined)
                ),
                "irs_individual_income_tax_withheld_and_fica_dollars": (
                    plain_decimal(
                        irs_value(
                            "individual_income_tax_withheld_and_fica_dollars"
                        )
                    )
                ),
                "irs_individual_income_tax_payments_and_seca_dollars": (
                    plain_decimal(
                        irs_value(
                            "individual_income_tax_payments_and_seca_dollars"
                        )
                    )
                ),
                "irs_unemployment_insurance_tax_dollars": (
                    plain_decimal(
                        irs_value(
                            "unemployment_insurance_tax_dollars"
                        )
                    )
                ),
                "irs_railroad_retirement_tax_dollars": (
                    plain_decimal(
                        irs_value(
                            "railroad_retirement_tax_dollars"
                        )
                    )
                ),
                "irs_estate_and_trust_income_tax_dollars": (
                    plain_decimal(
                        irs_value(
                            "estate_and_trust_income_tax_dollars"
                        )
                    )
                ),
                "irs_estate_tax_dollars": (
                    plain_decimal(
                        irs_value(
                            "estate_tax_dollars"
                        )
                    )
                ),
                "irs_gift_tax_dollars": (
                    plain_decimal(
                        irs_value(
                            "gift_tax_dollars"
                        )
                    )
                ),
                "irs_excise_taxes_dollars": (
                    plain_decimal(
                        irs_value(
                            "excise_taxes_dollars"
                        )
                    )
                ),
                "difference_vs_irs_total_dollars": (
                    plain_decimal(difference_total)
                ),
                "ratio_to_irs_total": (
                    plain_decimal(ratio_total)
                ),
                "difference_vs_irs_combined_category_dollars": (
                    plain_decimal(difference_combined)
                ),
                "ratio_to_irs_combined_category": (
                    plain_decimal(ratio_combined)
                ),
                "comparison_status": (
                    COMPARISON_STATUS
                ),
                "concept_equivalent": "NO",
                "additive": "NO",
                "irs_source_file": (
                    irs_row["source_file"]
                ),
                "irs_source_sha256": (
                    irs_row["source_sha256"]
                ),
            }
        )

    return rows


def certify_bridge(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(rows) != 10:
        raise RuntimeError(
            "BRIDGE OBSERVATION COUNT FAILURE\n"
            f"Expected 10; found {len(rows)}"
        )

    years = [
        int(row["fiscal_year"])
        for row in rows
    ]

    if years != TARGET_YEARS:
        raise RuntimeError(
            "BRIDGE YEAR COVERAGE FAILURE\n"
            f"Expected: {TARGET_YEARS}\n"
            f"Actual  : {years}"
        )

    if len(set(years)) != 10:
        raise RuntimeError(
            "BRIDGE YEAR UNIQUENESS FAILURE"
        )

    for row in rows:
        year = int(
            row["fiscal_year"]
        )

        allocated = Decimal(
            row[
                "wcffbp_individual_income_tax_receipts_dollars"
            ]
        )

        irs_total = Decimal(
            row[
                "irs_total_gross_collections_dollars"
            ]
        )

        irs_combined = Decimal(
            row[
                "irs_individual_employment_estate_trust_total_dollars"
            ]
        )

        difference_total = Decimal(
            row[
                "difference_vs_irs_total_dollars"
            ]
        )

        difference_combined = Decimal(
            row[
                "difference_vs_irs_combined_category_dollars"
            ]
        )

        ratio_total = Decimal(
            row[
                "ratio_to_irs_total"
            ]
        )

        ratio_combined = Decimal(
            row[
                "ratio_to_irs_combined_category"
            ]
        )

        if difference_total != (
            allocated - irs_total
        ):
            raise RuntimeError(
                "TOTAL DIFFERENCE ARITHMETIC FAILURE\n"
                f"FFY{year}"
            )

        if difference_combined != (
            allocated - irs_combined
        ):
            raise RuntimeError(
                "COMBINED DIFFERENCE ARITHMETIC FAILURE\n"
                f"FFY{year}"
            )

        if ratio_total != (
            allocated / irs_total
        ):
            raise RuntimeError(
                "TOTAL RATIO ARITHMETIC FAILURE\n"
                f"FFY{year}"
            )

        if ratio_combined != (
            allocated / irs_combined
        ):
            raise RuntimeError(
                "COMBINED RATIO ARITHMETIC FAILURE\n"
                f"FFY{year}"
            )

        if (
            row["comparison_status"]
            != COMPARISON_STATUS
        ):
            raise RuntimeError(
                "DIAGNOSTIC STATUS FAILURE\n"
                f"FFY{year}"
            )

        if row["concept_equivalent"] != "NO":
            raise RuntimeError(
                "CONCEPT EQUIVALENCE BOUNDARY FAILURE\n"
                f"FFY{year}"
            )

        if row["additive"] != "NO":
            raise RuntimeError(
                "ADDITIVITY BOUNDARY FAILURE\n"
                f"FFY{year}"
            )

    return {
        "expected_observations": 10,
        "actual_observations": 10,
        "year_coverage": "PASS",
        "year_uniqueness": "PASS",
        "irs_control_cross_check": "PASS",
        "difference_arithmetic": "PASS",
        "ratio_arithmetic": "PASS",
        "diagnostic_only_boundary": "PASS",
        "concept_equivalence_boundary": "PASS",
        "nonadditivity_boundary": "PASS",
    }


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        raise RuntimeError(
            "Refusing to write empty bridge."
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
    inputs: dict[str, Any],
    certification: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    lines.extend(
        [
            "=" * 100,
            (
                "IRS GROSS COLLECTIONS / ECONOMIC-INCIDENCE "
                "DIAGNOSTIC BRIDGE - ETL-172G-4"
            ),
            "=" * 100,
            "",
            (
                "Diagnostic comparison only. "
                "The compared series are not concept-equivalent "
                "and are not additive."
            ),
            "",
            "INPUT CERTIFICATION",
            "-" * 100,
            (
                "G3 input SHA256           : "
                f"{inputs['g3']['sha256']}"
            ),
            (
                "IRS semantic input SHA256 : "
                f"{inputs['irs_semantic']['sha256']}"
            ),
            (
                "IRS control input SHA256  : "
                f"{inputs['irs_reconciliation']['sha256']}"
            ),
            "",
            "COMPARISON DESIGN",
            "-" * 100,
            (
                "WCFFBP series : Economic-incidence allocation "
                "of national Individual Income Taxes receipts."
            ),
            (
                "IRS total     : Administrative gross collections "
                "attributed to Washington."
            ),
            (
                "IRS narrower  : Individual income + employment "
                "+ estate/trust income tax combined category."
            ),
            (
                "No IRS Table 5 field in this certified extract "
                "isolates individual income tax from employment taxes."
            ),
            (
                "Differences and ratios below are DIAGNOSTIC_ONLY."
            ),
            "",
            "CERTIFICATION",
            "-" * 100,
        ]
    )

    labels = [
        (
            "Expected observations",
            certification[
                "expected_observations"
            ],
        ),
        (
            "Actual observations",
            certification[
                "actual_observations"
            ],
        ),
        (
            "Year coverage",
            certification[
                "year_coverage"
            ],
        ),
        (
            "Year uniqueness",
            certification[
                "year_uniqueness"
            ],
        ),
        (
            "IRS control cross-check",
            certification[
                "irs_control_cross_check"
            ],
        ),
        (
            "Difference arithmetic",
            certification[
                "difference_arithmetic"
            ],
        ),
        (
            "Ratio arithmetic",
            certification[
                "ratio_arithmetic"
            ],
        ),
        (
            "Diagnostic-only boundary",
            certification[
                "diagnostic_only_boundary"
            ],
        ),
        (
            "Concept-equivalence boundary",
            certification[
                "concept_equivalence_boundary"
            ],
        ),
        (
            "Nonadditivity boundary",
            certification[
                "nonadditivity_boundary"
            ],
        ),
    ]

    for label, value in labels:
        lines.append(
            f"{label:<32}: {value}"
        )

    lines.extend(
        [
            "",
            "DIAGNOSTIC BRIDGE",
            "-" * 100,
            (
                f"{'FFY':<6}"
                f"{'WCFFBP IIT':>18}"
                f"{'IRS TOTAL':>18}"
                f"{'IIT/TOTAL':>12}"
                f"{'IRS COMBINED':>18}"
                f"{'IIT/COMB':>12}"
            ),
            "-" * 100,
        ]
    )

    for row in rows:
        allocated = Decimal(
            row[
                "wcffbp_individual_income_tax_receipts_dollars"
            ]
        )

        irs_total = Decimal(
            row[
                "irs_total_gross_collections_dollars"
            ]
        )

        irs_combined = Decimal(
            row[
                "irs_individual_employment_estate_trust_total_dollars"
            ]
        )

        ratio_total = Decimal(
            row[
                "ratio_to_irs_total"
            ]
        )

        ratio_combined = Decimal(
            row[
                "ratio_to_irs_combined_category"
            ]
        )

        lines.append(
            f"{row['fiscal_year']:<6}"
            f"{allocated:>18,.0f}"
            f"{irs_total:>18,.0f}"
            f"{ratio_total:>12.4%}"
            f"{irs_combined:>18,.0f}"
            f"{ratio_combined:>12.4%}"
        )

    lines.extend(
        [
            "",
            "INTERPRETATION BOUNDARY",
            "-" * 100,
            (
                "The WCFFBP individual-income-tax series and IRS "
                "gross-collections series measure different concepts."
            ),
            (
                "A positive or negative difference is not an error, "
                "residual, unexplained amount, or reconciliation gap."
            ),
            (
                "The IRS combined category contains employment taxes "
                "and estate/trust income tax in addition to individual "
                "income tax."
            ),
            (
                "The IRS total additionally contains business income "
                "taxes, estate tax, gift tax, excise taxes, and other "
                "components represented in the certified Table 5 structure."
            ),
            (
                "ETL-171 and ETL-172G-3 must not be added together."
            ),
            (
                "This bridge is intended to become more informative as "
                "additional ETL-172 receipt categories are reconstructed."
            ),
            (
                "Final receipts-ledger inclusion remains unauthorized."
            ),
            "",
            "ETL-172G-4 RESULT: PASS",
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
        "IRS GROSS COLLECTIONS / ECONOMIC-INCIDENCE "
        "DIAGNOSTIC BRIDGE - ETL-172G-4"
    )
    print("=" * 100)
    print()
    print(
        "Diagnostic comparison only. "
        "The compared series are not concept-equivalent "
        "and are not additive."
    )
    print()

    inputs = certify_inputs()

    g3 = load_g3()
    irs_semantic = load_irs_semantic()
    irs_recon = load_irs_reconciliation()

    rows = build_bridge(
        g3,
        irs_semantic,
        irs_recon,
    )

    certification = certify_bridge(
        rows
    )

    write_csv(
        OUTPUT_DETAIL,
        rows,
    )

    payload = {
        "etl_step": "ETL-172G-4",
        "result": "PASS",
        "artifact_type": (
            "DIAGNOSTIC_MEASUREMENT_BRIDGE"
        ),
        "inputs": inputs,
        "comparison_design": {
            "wcffbp_series": (
                "Economic-incidence allocation of national "
                "Individual Income Taxes receipts"
            ),
            "irs_total_series": (
                "Administrative Washington gross collections"
            ),
            "irs_narrower_series": (
                "Individual income + employment + "
                "estate/trust income tax combined"
            ),
            "concept_equivalent": False,
            "additive": False,
            "comparison_status": (
                COMPARISON_STATUS
            ),
        },
        "certification": certification,
        "interpretation_boundary": {
            "difference_is_error": False,
            "difference_is_residual": False,
            "difference_is_unexplained_amount": False,
            "forced_reconciliation": False,
            "employment_tax_subtraction": False,
            "corporate_income_tax_allocation": False,
            "rockefeller_vintage_replication": False,
            "database_writes": False,
            "final_ledger_inclusion_authorized": False,
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
        inputs,
        certification,
        rows,
    )

    OUTPUT_REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print("INPUT CERTIFICATION")
    print("-" * 100)
    print(
        "G3 input SHA256           : "
        f"{inputs['g3']['sha256']}"
    )
    print(
        "IRS semantic input SHA256 : "
        f"{inputs['irs_semantic']['sha256']}"
    )
    print(
        "IRS control input SHA256  : "
        f"{inputs['irs_reconciliation']['sha256']}"
    )
    print()

    print("COMPARISON DESIGN")
    print("-" * 100)
    print(
        "WCFFBP series : Economic-incidence allocation "
        "of national Individual Income Taxes receipts"
    )
    print(
        "IRS total     : Administrative Washington "
        "gross collections"
    )
    print(
        "IRS narrower  : Individual income + employment "
        "+ estate/trust income tax combined"
    )
    print(
        "Status        : DIAGNOSTIC_ONLY"
    )
    print()

    print("CERTIFICATION")
    print("-" * 100)
    print(
        "Expected observations          : "
        f"{certification['expected_observations']}"
    )
    print(
        "Actual observations            : "
        f"{certification['actual_observations']}"
    )
    print(
        "Year coverage                  : "
        f"{certification['year_coverage']}"
    )
    print(
        "Year uniqueness                : "
        f"{certification['year_uniqueness']}"
    )
    print(
        "IRS control cross-check        : "
        f"{certification['irs_control_cross_check']}"
    )
    print(
        "Difference arithmetic          : "
        f"{certification['difference_arithmetic']}"
    )
    print(
        "Ratio arithmetic               : "
        f"{certification['ratio_arithmetic']}"
    )
    print(
        "Diagnostic-only boundary       : "
        f"{certification['diagnostic_only_boundary']}"
    )
    print(
        "Concept-equivalence boundary   : "
        f"{certification['concept_equivalence_boundary']}"
    )
    print(
        "Nonadditivity boundary         : "
        f"{certification['nonadditivity_boundary']}"
    )
    print()

    print("DIAGNOSTIC BRIDGE")
    print("-" * 100)
    print(
        f"{'FFY':<6}"
        f"{'WCFFBP IIT':>18}"
        f"{'IRS TOTAL':>18}"
        f"{'IIT/TOTAL':>12}"
        f"{'IRS COMBINED':>18}"
        f"{'IIT/COMB':>12}"
    )

    for row in rows:
        allocated = Decimal(
            row[
                "wcffbp_individual_income_tax_receipts_dollars"
            ]
        )

        irs_total = Decimal(
            row[
                "irs_total_gross_collections_dollars"
            ]
        )

        irs_combined = Decimal(
            row[
                "irs_individual_employment_estate_trust_total_dollars"
            ]
        )

        ratio_total = Decimal(
            row[
                "ratio_to_irs_total"
            ]
        )

        ratio_combined = Decimal(
            row[
                "ratio_to_irs_combined_category"
            ]
        )

        print(
            f"{row['fiscal_year']:<6}"
            f"{allocated:>18,.0f}"
            f"{irs_total:>18,.0f}"
            f"{ratio_total:>12.4%}"
            f"{irs_combined:>18,.0f}"
            f"{ratio_combined:>12.4%}"
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
        "ETL-172G-4 RESULT: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )