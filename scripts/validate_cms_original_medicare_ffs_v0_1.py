from __future__ import annotations

from pathlib import Path

import pandas as pd


SOURCE = Path(
    "data/raw/cms/medicare_geographic_variation/"
    "2014-2024 Original Medicare Geographic Variation Public Use File.csv"
)

OUTDIR = Path(
    "data/raw/cms/medicare_geographic_variation/validation/"
    "original_medicare_ffs_v0_1"
)

YEARS = list(range(2015, 2025))

EXPECTED_COUNTIES = 39
UNKNOWN_CODE = "53000"

REQUIRED_COLUMNS = [
    "YEAR",
    "BENE_GEO_LVL",
    "BENE_GEO_DESC",
    "BENE_GEO_CD",
    "BENE_AGE_LVL",
    "BENES_TOTAL_CNT",
    "BENES_WTH_PTAPTB_CNT",
    "BENES_OM_CNT",
    "BENES_MA_CNT",
    "MA_PRTCPTN_RATE",
    "TOT_MDCR_PYMT_AMT",
    "TOT_MDCR_STDZD_PYMT_AMT",
    "TOT_MDCR_PYMT_PC",
    "TOT_MDCR_STDZD_PYMT_PC",
]


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def result(label: str, passed: bool, detail: str) -> dict:
    return {
        "check": label,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
    }


def main() -> None:
    print("=" * 100)
    print("CMS ORIGINAL MEDICARE / FFS CERTIFICATION VALIDATOR v0.1")
    print("=" * 100)
    print()
    print("READ-ONLY: no database writes")
    print()

    checks: list[dict] = []

    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    df = pd.read_csv(SOURCE, dtype=str, low_memory=False)

    missing_columns = [
        column for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    checks.append(
        result(
            "Required source columns",
            not missing_columns,
            (
                "All required columns present"
                if not missing_columns
                else f"Missing: {missing_columns}"
            ),
        )
    )

    if missing_columns:
        print("FAIL: required columns missing.")
        for row in checks:
            print(row)
        raise SystemExit(1)

    # ------------------------------------------------------------
    # Restrict to Washington county-level, All-age observations.
    # ------------------------------------------------------------

    wa = df[
        (df["BENE_GEO_LVL"].str.strip() == "County")
        & (df["BENE_GEO_DESC"].str.startswith("WA-", na=False))
        & (df["BENE_AGE_LVL"].str.strip() == "All")
    ].copy()

    wa["YEAR_NUM"] = numeric(wa["YEAR"])
    wa = wa[wa["YEAR_NUM"].isin(YEARS)].copy()
    wa["YEAR_NUM"] = wa["YEAR_NUM"].astype(int)

    # Normalize FIPS because source may have numeric-looking strings.
    wa["FIPS"] = (
        wa["BENE_GEO_CD"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(5)
    )

    unknown = wa[wa["FIPS"] == UNKNOWN_CODE].copy()
    counties = wa[wa["FIPS"] != UNKNOWN_CODE].copy()

    # ------------------------------------------------------------
    # Geography gate.
    # ------------------------------------------------------------

    counts = (
        counties.groupby("YEAR_NUM")
        .agg(
            row_count=("FIPS", "size"),
            distinct_fips=("FIPS", "nunique"),
            distinct_names=("BENE_GEO_DESC", "nunique"),
        )
        .reset_index()
    )

    geography_pass = (
        len(counts) == len(YEARS)
        and (counts["row_count"] == EXPECTED_COUNTIES).all()
        and (counts["distinct_fips"] == EXPECTED_COUNTIES).all()
        and (counts["distinct_names"] == EXPECTED_COUNTIES).all()
    )

    checks.append(
        result(
            "39 named Washington counties per year",
            geography_pass,
            f"{len(counties):,} county-year rows",
        )
    )

    unknown_counts = (
        unknown.groupby("YEAR_NUM")
        .size()
        .reindex(YEARS, fill_value=0)
    )

    unknown_pass = (
        len(unknown) == len(YEARS)
        and (unknown_counts == 1).all()
    )

    checks.append(
        result(
            "WA-UNKNOWN isolated as FIPS 53000",
            unknown_pass,
            f"{len(unknown):,} unknown rows",
        )
    )

    # ------------------------------------------------------------
    # Payment completeness.
    # ------------------------------------------------------------

    for column in [
        "BENES_OM_CNT",
        "TOT_MDCR_PYMT_AMT",
        "TOT_MDCR_PYMT_PC",
        "TOT_MDCR_STDZD_PYMT_AMT",
        "TOT_MDCR_STDZD_PYMT_PC",
    ]:
        counties[column + "_NUM"] = numeric(counties[column])

    payment_complete = (
        counties["TOT_MDCR_PYMT_AMT_NUM"].notna().all()
    )

    checks.append(
        result(
            "Aggregate actual payment populated for all named counties",
            payment_complete,
            (
                f"{counties['TOT_MDCR_PYMT_AMT_NUM'].notna().sum():,}"
                f"/{len(counties):,} populated"
            ),
        )
    )

    # ------------------------------------------------------------
    # Core mechanical identity:
    #
    # aggregate actual payment / OM beneficiary count
    #     ~= published actual payment per capita
    #
    # Published PC values are rounded to cents.
    # ------------------------------------------------------------

    testable = counties[
        counties["TOT_MDCR_PYMT_AMT_NUM"].notna()
        & counties["BENES_OM_CNT_NUM"].notna()
        & (counties["BENES_OM_CNT_NUM"] > 0)
        & counties["TOT_MDCR_PYMT_PC_NUM"].notna()
    ].copy()

    testable["CALCULATED_PC"] = (
        testable["TOT_MDCR_PYMT_AMT_NUM"]
        / testable["BENES_OM_CNT_NUM"]
    )

    testable["PC_DIFF"] = (
        testable["CALCULATED_PC"]
        - testable["TOT_MDCR_PYMT_PC_NUM"]
    )

    max_abs_pc_diff = testable["PC_DIFF"].abs().max()
    mean_abs_pc_diff = testable["PC_DIFF"].abs().mean()

    # Half-cent rounding, with tiny floating-point allowance.
    identity_pass = (
        len(testable) == len(counties)
        and max_abs_pc_diff <= 0.0051
    )

    checks.append(
        result(
            "Aggregate/per-capita payment identity",
            identity_pass,
            (
                f"{len(testable):,}/{len(counties):,} rows testable; "
                f"max abs diff=${max_abs_pc_diff:.6f}; "
                f"mean abs diff=${mean_abs_pc_diff:.6f}"
            ),
        )
    )

    # ------------------------------------------------------------
    # Standardized payment identity as an independent structural
    # confirmation.
    # ------------------------------------------------------------

    standardized = counties[
        counties["TOT_MDCR_STDZD_PYMT_AMT_NUM"].notna()
        & counties["BENES_OM_CNT_NUM"].notna()
        & (counties["BENES_OM_CNT_NUM"] > 0)
        & counties["TOT_MDCR_STDZD_PYMT_PC_NUM"].notna()
    ].copy()

    standardized["CALCULATED_STDZD_PC"] = (
        standardized["TOT_MDCR_STDZD_PYMT_AMT_NUM"]
        / standardized["BENES_OM_CNT_NUM"]
    )

    standardized["STDZD_PC_DIFF"] = (
        standardized["CALCULATED_STDZD_PC"]
        - standardized["TOT_MDCR_STDZD_PYMT_PC_NUM"]
    )

    max_abs_stdzd_diff = standardized["STDZD_PC_DIFF"].abs().max()

    standardized_pass = (
        len(standardized) == len(counties)
        and max_abs_stdzd_diff <= 0.0051
    )

    checks.append(
        result(
            "Standardized aggregate/per-capita identity",
            standardized_pass,
            (
                f"{len(standardized):,}/{len(counties):,} rows testable; "
                f"max abs diff=${max_abs_stdzd_diff:.6f}"
            ),
        )
    )

    # ------------------------------------------------------------
    # Duplicate-key gate.
    # ------------------------------------------------------------

    duplicate_count = int(
        counties.duplicated(
            subset=["YEAR_NUM", "FIPS"],
            keep=False,
        ).sum()
    )

    checks.append(
        result(
            "Unique county-year keys",
            duplicate_count == 0,
            f"{duplicate_count:,} duplicate rows",
        )
    )

    # ------------------------------------------------------------
    # Annual Washington totals.
    # ------------------------------------------------------------

    annual = (
        counties.groupby("YEAR_NUM", as_index=False)
        .agg(
            county_rows=("FIPS", "size"),
            original_medicare_beneficiaries=(
                "BENES_OM_CNT_NUM",
                "sum",
            ),
            actual_ffs_payments_dollars=(
                "TOT_MDCR_PYMT_AMT_NUM",
                "sum",
            ),
            standardized_ffs_payments_dollars=(
                "TOT_MDCR_STDZD_PYMT_AMT_NUM",
                "sum",
            ),
        )
        .rename(columns={"YEAR_NUM": "year"})
    )

    # ------------------------------------------------------------
    # Save evidence.
    # ------------------------------------------------------------

    OUTDIR.mkdir(parents=True, exist_ok=True)

    annual.to_csv(
        OUTDIR / "washington_original_medicare_ffs_annual_v0_1.csv",
        index=False,
    )

    counts.to_csv(
        OUTDIR / "washington_original_medicare_ffs_geography_v0_1.csv",
        index=False,
    )

    testable[
        [
            "YEAR_NUM",
            "BENE_GEO_DESC",
            "FIPS",
            "BENES_OM_CNT_NUM",
            "TOT_MDCR_PYMT_AMT_NUM",
            "TOT_MDCR_PYMT_PC_NUM",
            "CALCULATED_PC",
            "PC_DIFF",
        ]
    ].to_csv(
        OUTDIR / "washington_original_medicare_ffs_identity_v0_1.csv",
        index=False,
    )

    pd.DataFrame(checks).to_csv(
        OUTDIR / "washington_original_medicare_ffs_checks_v0_1.csv",
        index=False,
    )

    # ------------------------------------------------------------
    # Console report.
    # ------------------------------------------------------------

    print("=" * 100)
    print("SOURCE")
    print("=" * 100)
    print(f"Source: {SOURCE}")
    print(f"Rows in source: {len(df):,}")
    print(f"WA named county-year rows, 2015-2024: {len(counties):,}")
    print(f"WA UNKNOWN rows, 2015-2024: {len(unknown):,}")

    print()
    print("=" * 100)
    print("CHECKS")
    print("=" * 100)

    for row in checks:
        print(
            f"{row['status']:4} | "
            f"{row['check']} | "
            f"{row['detail']}"
        )

    print()
    print("=" * 100)
    print("WASHINGTON ORIGINAL MEDICARE / FFS ANNUAL CONTROL")
    print("=" * 100)

    display = annual.copy()
    display["actual_ffs_payments_dollars"] = (
        display["actual_ffs_payments_dollars"]
        .map(lambda x: f"${x:,.2f}")
    )
    display["standardized_ffs_payments_dollars"] = (
        display["standardized_ffs_payments_dollars"]
        .map(lambda x: f"${x:,.2f}")
    )

    print(display.to_string(index=False))

    overall_pass = all(
        row["status"] == "PASS"
        for row in checks
    )

    print()
    print("=" * 100)
    print(
        "OVERALL: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )
    print("=" * 100)

    print()
    print("Semantic boundary:")
    print(
        "  Candidate accounting stream = "
        "Original Medicare / Fee-for-Service actual payments."
    )
    print(
        "  Principal dollar field = TOT_MDCR_PYMT_AMT."
    )
    print(
        "  Standardized payments are analytical controls, "
        "not ledger expenditures."
    )
    print(
        "  WA-UNKNOWN / FIPS 53000 is excluded."
    )
    print(
        "  No beneficiary multiplication is applied to "
        "TOT_MDCR_PYMT_AMT."
    )

    if not overall_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
