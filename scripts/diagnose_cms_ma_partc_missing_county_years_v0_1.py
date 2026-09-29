from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CERT_SCRIPT = ROOT / "scripts" / "validate_cms_ma_partc_payment_reconstruction_v0_2_certified.py"

OUTDIR = (
    ROOT / "data" / "raw" / "cms" / "medicare_advantage" / "validation"
    / "partc_county_missing_diagnostic_v0_1"
)
OUT_CSV = OUTDIR / "cms_ma_partc_missing_county_year_diagnostic_v0_1.csv"
OUT_TXT = OUTDIR / "cms_ma_partc_missing_county_year_diagnostic_v0_1.txt"

CELLS = (
    ROOT / "data" / "raw" / "cms" / "medicare_advantage" / "validation"
    / "payment_reconstruction_v0_2" / "cms_ma_partc_payment_reconstruction_cells.csv"
)
EXCEPTIONS = (
    ROOT / "data" / "raw" / "cms" / "medicare_advantage" / "validation"
    / "payment_reconstruction_v0_2" / "cms_ma_partc_payment_reconstruction_exceptions.csv"
)

CASES = {
    (2015, "53023"): "Garfield",
    (2016, "53019"): "Ferry",
    (2016, "53023"): "Garfield",
    (2017, "53019"): "Ferry",
    (2017, "53023"): "Garfield",
    (2018, "53023"): "Garfield",
    (2019, "53023"): "Garfield",
    (2020, "53019"): "Ferry",
    (2020, "53023"): "Garfield",
    (2020, "53043"): "Lincoln",
    (2021, "53019"): "Ferry",
    (2021, "53023"): "Garfield",
    (2022, "53019"): "Ferry",
    (2022, "53023"): "Garfield",
}


def load_certified_module():
    if not CERT_SCRIPT.exists():
        raise FileNotFoundError(CERT_SCRIPT)
    spec = importlib.util.spec_from_file_location("partc_cert_v02", CERT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def locate_manifest(mod) -> Path:
    required = {"source_type", "status", "period", "local_path"}

    # Prefer Path constants already defined by the certified script.
    candidates = []
    for name, value in vars(mod).items():
        if isinstance(value, Path) and value.suffix.lower() == ".csv" and value.exists():
            candidates.append(value)

    # Conservative fallback: only manifest-named CSVs in the MA raw tree.
    ma_root = ROOT / "data" / "raw" / "cms" / "medicare_advantage"
    candidates.extend(ma_root.rglob("*manifest*.csv"))

    seen = set()
    for path in candidates:
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        try:
            cols = set(pd.read_csv(path, nrows=0).columns)
        except Exception:
            continue
        if required.issubset(cols):
            return path

    raise RuntimeError(
        "Could not locate the certified source manifest containing "
        "source_type/status/period/local_path."
    )


def norm_fips(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(5)
    )


def main():
    mod = load_certified_module()
    manifest_path = locate_manifest(mod)
    manifest = pd.read_csv(manifest_path, dtype=str).fillna("")

    manifest["source_type"] = manifest["source_type"].map(mod.clean).str.upper()
    manifest["status"] = manifest["status"].map(mod.clean).str.upper()
    manifest["period"] = manifest["period"].map(mod.clean)

    cpsc = manifest[
        (manifest["source_type"] == "CPSC") &
        (manifest["status"] == "PASS")
    ].copy()

    by_period = {
        row["period"]: mod.path_from_manifest(row["local_path"])
        for _, row in cpsc.iterrows()
    }

    periods_needed = sorted(
        p for p in by_period
        if len(p) >= 7
        and p[:4].isdigit()
        and 2015 <= int(p[:4]) <= 2022
        and any(y == int(p[:4]) for y, _ in CASES)
    )

    # Existing certified outputs are used only to distinguish upstream target
    # enrollment from downstream reconstruction/payment-cell outcomes.
    cells = pd.read_csv(CELLS, dtype=str).fillna("") if CELLS.exists() else pd.DataFrame()
    exc = pd.read_csv(EXCEPTIONS, dtype=str).fillna("") if EXCEPTIONS.exists() else pd.DataFrame()

    if not cells.empty:
        cells["payment_year"] = pd.to_numeric(cells["payment_year"], errors="coerce")
        cells["fips_code"] = norm_fips(cells["fips_code"])
    if not exc.empty:
        exc["payment_year"] = pd.to_numeric(exc["payment_year"], errors="coerce")
        exc["fips_code"] = norm_fips(exc["fips_code"])

    monthly = []

    for period in periods_needed:
        year = int(period[:4])
        relevant = {f for (y, f) in CASES if y == year}
        if not relevant:
            continue

        contracts, enrollment = mod.load_cpsc(by_period[period])

        c_contract = mod.column(contracts, "Contract ID")
        c_plan = mod.column(contracts, "Plan ID")
        c_type = mod.column(contracts, "Plan Type")
        c_snp = mod.column(contracts, "SNP Plan")
        c_eghp = mod.column(contracts, "EGHP")

        contract_dim = pd.DataFrame({
            "contract": contracts[c_contract].map(mod.clean),
            "plan_id": contracts[c_plan].map(mod.normalize_plan_id),
            "plan_type": contracts[c_type].map(mod.canonical_plan_type),
            "snp_flag": contracts[c_snp].map(mod.clean).str.upper(),
            "eghp": contracts[c_eghp].map(mod.clean).str.upper(),
        }).drop_duplicates(["contract", "plan_id"])

        e_contract = mod.column(enrollment, "Contract Number")
        e_plan = mod.column(enrollment, "Plan ID")
        e_state = mod.column(enrollment, "State")
        e_county = mod.column(enrollment, "County")
        e_ssa = mod.column(enrollment, "SSA State County Code")
        e_fips = mod.column(enrollment, "FIPS State County Code")
        e_enroll = mod.column(enrollment, "Enrollment")

        e = pd.DataFrame({
            "contract": enrollment[e_contract].map(mod.clean),
            "plan_id": enrollment[e_plan].map(mod.normalize_plan_id),
            "state": enrollment[e_state].map(mod.clean).str.upper(),
            "county": enrollment[e_county].map(mod.clean),
            "ssa_code": enrollment[e_ssa].map(mod.clean),
            "fips_code": enrollment[e_fips].map(mod.clean),
            "enrollment_raw": enrollment[e_enroll].map(mod.clean),
        })
        e = e[e["state"] == "WA"].copy()
        e["fips_code"] = norm_fips(e["fips_code"])
        e["enrollment"] = pd.to_numeric(e["enrollment_raw"], errors="coerce")

        e = e.merge(
            contract_dim,
            on=["contract", "plan_id"],
            how="left",
            validate="many_to_one",
            indicator="contract_join",
        )

        for fips in sorted(relevant):
            county = CASES[(year, fips)]
            q = e[e["fips_code"] == fips].copy()
            target = q[q["plan_type"].isin({"HMO", "LOCAL PPO"})].copy()

            monthly.append({
                "payment_year": year,
                "period": period,
                "fips_code": fips,
                "county": county,
                "cpsc_rows": len(q),
                "resolved_contract_rows": int((q["contract_join"] == "both").sum()),
                "unresolved_contract_rows": int((q["contract_join"] != "both").sum()),
                "target_rows": len(target),
                "target_numeric_rows": int(target["enrollment"].notna().sum()),
                "target_suppressed_or_nonnumeric_rows": int(target["enrollment"].isna().sum()),
                "target_numeric_enrollment": float(target["enrollment"].sum(min_count=1))
                    if target["enrollment"].notna().any() else 0.0,
                "non_target_rows": int(len(q) - len(target)),
            })

    m = pd.DataFrame(monthly)
    if m.empty:
        raise RuntimeError("No diagnostic monthly observations were produced.")

    annual = (
        m.groupby(["payment_year", "fips_code", "county"], as_index=False)
        .agg(
            months_examined=("period", "nunique"),
            months_with_any_cpsc_rows=("cpsc_rows", lambda x: int((x > 0).sum())),
            cpsc_rows=("cpsc_rows", "sum"),
            resolved_contract_rows=("resolved_contract_rows", "sum"),
            unresolved_contract_rows=("unresolved_contract_rows", "sum"),
            target_rows=("target_rows", "sum"),
            target_numeric_rows=("target_numeric_rows", "sum"),
            target_suppressed_or_nonnumeric_rows=("target_suppressed_or_nonnumeric_rows", "sum"),
            target_numeric_enrollment_member_months=("target_numeric_enrollment", "sum"),
            non_target_rows=("non_target_rows", "sum"),
        )
    )

    # Add frozen v0.2 reconstruction/exception evidence.
    def count_rows(df, year, fips):
        if df.empty:
            return 0
        return int(((df["payment_year"] == year) & (df["fips_code"] == fips)).sum())

    annual["reconstructed_cell_rows"] = [
        count_rows(cells, int(r.payment_year), r.fips_code)
        for r in annual.itertuples()
    ]

    if not exc.empty and "exception" in exc.columns:
        exc_types = sorted(set(exc["exception"]) - {""})
        for et in exc_types:
            col = "exception_" + "".join(ch.lower() if ch.isalnum() else "_" for ch in et).strip("_") + "_rows"
            annual[col] = [
                int(
                    (
                        (exc["payment_year"] == int(r.payment_year))
                        & (exc["fips_code"] == r.fips_code)
                        & (exc["exception"] == et)
                    ).sum()
                )
                for r in annual.itertuples()
            ]

    exception_cols = [c for c in annual.columns if c.startswith("exception_")]

    def classify(row):
        if row["cpsc_rows"] == 0:
            return "NO_CPSC_ROWS"
        if row["target_rows"] == 0:
            if row["unresolved_contract_rows"] > 0:
                return "NO_TARGET_ACTIVITY_WITH_UNRESOLVED_CONTRACT_ROWS"
            return "NO_TARGET_HMO_LOCAL_PPO_ACTIVITY"
        if row["target_numeric_rows"] == 0 and row["target_suppressed_or_nonnumeric_rows"] > 0:
            return "TARGET_SUPPRESSED_OR_NONNUMERIC_ONLY"
        if row["target_numeric_rows"] > 0 and row["reconstructed_cell_rows"] == 0:
            if any(row[c] > 0 for c in exception_cols):
                return "NUMERIC_TARGET_BUT_RECONSTRUCTION_EXCEPTION"
            return "NUMERIC_TARGET_BUT_NO_RECONSTRUCTED_CELL"
        if row["reconstructed_cell_rows"] > 0:
            return "RECONSTRUCTED_CELL_PRESENT_UNEXPECTED"
        return "OTHER_SOURCE_LIMITATION"

    annual["classification"] = annual.apply(classify, axis=1)

    # Guarantee exactly the intended 14-case universe.
    expected = pd.DataFrame(
        [{"payment_year": y, "fips_code": f, "county": c}
         for (y, f), c in sorted(CASES.items())]
    )
    result = expected.merge(
        annual,
        on=["payment_year", "fips_code", "county"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if not (result["_merge"] == "both").all():
        missing = result.loc[result["_merge"] != "both",
                             ["payment_year", "fips_code", "county"]]
        raise RuntimeError(f"Missing diagnostic cases:\n{missing.to_string(index=False)}")
    result = result.drop(columns="_merge")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_CSV, index=False)

    lines = [
        "=" * 100,
        "CMS MEDICARE ADVANTAGE PART C MISSING COUNTY-YEAR DIAGNOSTIC v0.1",
        "=" * 100,
        "READ-ONLY; no source modification, imputation, dollar assignment, DB writes, or ledger inclusion.",
        "",
        f"Certified source script: {CERT_SCRIPT}",
        f"Manifest: {manifest_path}",
        "",
        "Purpose: classify the 14 county-years absent from the certified v0.2 reconstructed cell artifact.",
        "Target definition is inherited exactly from the certified reconstruction: HMO + LOCAL PPO.",
        "Suppressed/non-numeric enrollment is never converted to zero.",
        "",
        result.to_string(index=False),
        "",
        "CLASSIFICATION COUNTS",
        "-" * 100,
        result["classification"].value_counts(dropna=False).to_string(),
        "",
        f"Evidence written: {OUT_CSV}",
    ]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print(f"  {OUT_TXT}")


if __name__ == "__main__":
    main()
