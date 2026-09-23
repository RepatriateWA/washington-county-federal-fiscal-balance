#!/usr/bin/env python
"""
Diagnose the CY2022 CMS Medicare Advantage Part C plan-type boundary.

READ-ONLY diagnostic. No database writes and no source-file modifications.

Purpose
-------
Trace Washington CY2022 enrollment through the generalized production
monthly-linkage pipeline at the CPSC contract-dimension boundary and compare
the resulting HMO / Local PPO member-months with the already-established
dedicated CY2022 reconstruction controls:

    HMO        5,498,705 member-months
    LOCAL PPO  1,821,310 member-months
    COMBINED   7,320,015 member-months

This script intentionally reuses the production linkage script's loaders and
canonicalization functions so that the diagnostic tests the same code path
rather than creating a parallel interpretation of the CMS source files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.validate_cms_ma_partc_monthly_linkage as prod
except Exception as exc:
    raise SystemExit(
        "FAIL: could not import "
        "scripts.validate_cms_ma_partc_monthly_linkage.py\n"
        f"{type(exc).__name__}: {exc}"
    )

OUTDIR = (
    ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_advantage"
    / "validation"
    / "cy2022_plan_type_boundary_diagnostic_v0_1"
)
MONTHLY_OUT = OUTDIR / "cy2022_plan_type_boundary_monthly.csv"
PLAN_OUT = OUTDIR / "cy2022_plan_type_boundary_plan_type.csv"
UNRESOLVED_OUT = OUTDIR / "cy2022_plan_type_boundary_unresolved.csv"
SUMMARY_OUT = OUTDIR / "cy2022_plan_type_boundary_summary.txt"

CONTROL = {
    "HMO": 5_498_705.0,
    "LOCAL PPO": 1_821_310.0,
}
CONTROL_COMBINED = 7_320_015.0

TOL_MM = 0.01


def clean(x) -> str:
    return prod.clean(x)


def column(df, *aliases):
    return prod.column(df, *aliases)


def path_from_manifest(x) -> Path:
    return prod.path_from_manifest(x)


def find_manifest() -> Path:
    candidates = [
        ROOT
        / "data"
        / "raw"
        / "cms"
        / "medicare_advantage"
        / "validation"
        / "source_acquisition"
        / "cms_ma_partc_source_acquisition_manifest.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Could not find CMS MA Part C source acquisition manifest."
    )


def normalize_manifest_period(x) -> str:
    s = clean(x)
    try:
        return str(pd.Period(s, freq="M"))
    except Exception:
        return s


def fmt_num(x) -> str:
    if pd.isna(x):
        return ""
    return f"{float(x):,.0f}"


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    monthly_rows: list[dict] = []
    plan_rows: list[dict] = []
    unresolved_rows: list[dict] = []

    manifest_path = find_manifest()
    manifest = pd.read_csv(manifest_path, dtype=str).fillna("")

    required_cols = {"source_type", "period", "status", "local_path"}
    missing = required_cols - set(manifest.columns)
    if missing:
        raise SystemExit(
            "FAIL: source manifest missing columns: "
            + ", ".join(sorted(missing))
        )

    manifest["source_type"] = manifest["source_type"].map(clean).str.upper()
    manifest["status"] = manifest["status"].map(clean).str.upper()
    manifest["period_norm"] = manifest["period"].map(normalize_manifest_period)

    cpsc = manifest[
        (manifest["source_type"] == "CPSC")
        & (manifest["status"] == "PASS")
    ].copy()

    by_period = {}
    for _, row in cpsc.iterrows():
        period = row["period_norm"]
        if period:
            by_period[period] = path_from_manifest(row["local_path"])

    periods = [str(x) for x in pd.period_range("2022-01", "2022-12", freq="M")]

    print("=" * 112)
    print("CMS MA PART C — CY2022 PLAN-TYPE BOUNDARY DIAGNOSTIC v0.1")
    print("=" * 112)
    print()
    print("READ-ONLY DIAGNOSTIC")
    print()

    for n, period in enumerate(periods, 1):
        print(f"[{n:02d}/12] {period}", end=" ", flush=True)

        path = by_period.get(period)
        if path is None:
            errors.append(f"{period}: no PASS CPSC source in manifest")
            print("FAIL: no source")
            continue
        if not path.exists():
            errors.append(f"{period}: CPSC path does not exist: {path}")
            print("FAIL: missing file")
            continue

        try:
            contracts, enrollment = prod.load_cpsc(path)

            c_contract = column(contracts, "Contract ID")
            c_plan = column(contracts, "Plan ID")
            c_type = column(contracts, "Plan Type")
            c_snp = column(contracts, "SNP Plan")
            c_eghp = column(contracts, "EGHP")

            contract_dim = pd.DataFrame({
                "contract": contracts[c_contract].map(clean),
                "plan_id": contracts[c_plan].map(prod.normalize_plan_id),
                "raw_plan_type": contracts[c_type].map(clean),
                "plan_type": contracts[c_type].map(prod.canonical_plan_type),
                "snp_flag": contracts[c_snp].map(clean).str.upper(),
                "eghp": contracts[c_eghp].map(clean).str.upper(),
            })

            duplicate_keys = int(
                contract_dim.loc[
                    contract_dim.duplicated(
                        ["contract", "plan_id"], keep=False
                    ),
                    ["contract", "plan_id"],
                ]
                .drop_duplicates()
                .shape[0]
            )

            # Match production behavior: drop duplicate contract-plan keys.
            contract_dim = contract_dim.drop_duplicates(
                ["contract", "plan_id"]
            )

            e_contract = column(enrollment, "Contract Number")
            e_plan = column(enrollment, "Plan ID")
            e_state = column(enrollment, "State")
            e_county = column(enrollment, "County")
            e_ssa = column(enrollment, "SSA State County Code")
            e_fips = column(enrollment, "FIPS State County Code")
            e_enroll = column(enrollment, "Enrollment")

            e = pd.DataFrame({
                "contract": enrollment[e_contract].map(clean),
                "plan_id": enrollment[e_plan].map(prod.normalize_plan_id),
                "state": enrollment[e_state].map(clean).str.upper(),
                "county": enrollment[e_county].map(clean),
                "ssa_code": enrollment[e_ssa].map(clean),
                "fips_code": enrollment[e_fips].map(clean),
                "enrollment_raw": enrollment[e_enroll].map(clean),
            })

            e = e[e["state"] == "WA"].copy()
            e["enrollment"] = pd.to_numeric(
                e["enrollment_raw"], errors="coerce"
            )

            wa_numeric_before_merge = float(
                e.loc[e["enrollment"].notna(), "enrollment"].sum()
            )

            merged = e.merge(
                contract_dim,
                on=["contract", "plan_id"],
                how="left",
                validate="many_to_one",
                indicator="contract_join",
            )

            resolved = merged[merged["contract_join"] == "both"].copy()
            unresolved = merged[merged["contract_join"] != "both"].copy()

            resolved_numeric_mm = float(
                resolved.loc[
                    resolved["enrollment"].notna(), "enrollment"
                ].sum()
            )
            unresolved_numeric_mm = float(
                unresolved.loc[
                    unresolved["enrollment"].notna(), "enrollment"
                ].sum()
            )

            target = resolved[
                resolved["plan_type"].isin({"HMO", "LOCAL PPO"})
            ].copy()
            target_numeric = target[target["enrollment"].notna()].copy()

            hmo_mm = float(
                target_numeric.loc[
                    target_numeric["plan_type"] == "HMO", "enrollment"
                ].sum()
            )
            ppo_mm = float(
                target_numeric.loc[
                    target_numeric["plan_type"] == "LOCAL PPO", "enrollment"
                ].sum()
            )

            monthly_rows.append({
                "period": period,
                "cpsc_source": str(path),
                "raw_contract_rows": len(contracts),
                "contract_dim_rows": len(contract_dim),
                "duplicate_contract_plan_keys": duplicate_keys,
                "wa_enrollment_rows_before_merge": len(e),
                "wa_numeric_member_months_before_merge": wa_numeric_before_merge,
                "resolved_wa_enrollment_rows": len(resolved),
                "resolved_numeric_member_months": resolved_numeric_mm,
                "unresolved_wa_enrollment_rows": len(unresolved),
                "unresolved_numeric_member_months": unresolved_numeric_mm,
                "target_rows": len(target),
                "target_numeric_rows": len(target_numeric),
                "hmo_member_months": hmo_mm,
                "local_ppo_member_months": ppo_mm,
                "target_member_months": hmo_mm + ppo_mm,
            })

            # Raw/canonical plan-type distribution among WA enrollment after
            # contract-plan resolution. This is the critical classification
            # boundary.
            dist = (
                resolved[resolved["enrollment"].notna()]
                .groupby(["raw_plan_type", "plan_type"], dropna=False)
                .agg(
                    rows=("enrollment", "size"),
                    member_months=("enrollment", "sum"),
                )
                .reset_index()
            )
            for _, r in dist.iterrows():
                plan_rows.append({
                    "period": period,
                    "raw_plan_type": r["raw_plan_type"],
                    "canonical_plan_type": r["plan_type"],
                    "rows": int(r["rows"]),
                    "member_months": float(r["member_months"]),
                })

            for _, r in unresolved.iterrows():
                unresolved_rows.append({
                    "period": period,
                    "contract": r["contract"],
                    "plan_id": r["plan_id"],
                    "county": r["county"],
                    "enrollment_raw": r["enrollment_raw"],
                    "enrollment": r["enrollment"],
                })

            print(
                f"HMO={hmo_mm:,.0f} "
                f"PPO={ppo_mm:,.0f} "
                f"unresolved={unresolved_numeric_mm:,.0f}"
            )

        except Exception as exc:
            errors.append(
                f"{period}: {type(exc).__name__}: {exc}"
            )
            print(f"FAIL: {type(exc).__name__}: {exc}")

    monthly_df = pd.DataFrame(monthly_rows)
    plan_df = pd.DataFrame(plan_rows)
    unresolved_df = pd.DataFrame(unresolved_rows)

    monthly_df.to_csv(MONTHLY_OUT, index=False)
    plan_df.to_csv(PLAN_OUT, index=False)
    unresolved_df.to_csv(UNRESOLVED_OUT, index=False)

    hmo = (
        float(monthly_df["hmo_member_months"].sum())
        if not monthly_df.empty else 0.0
    )
    ppo = (
        float(monthly_df["local_ppo_member_months"].sum())
        if not monthly_df.empty else 0.0
    )
    combined = hmo + ppo
    unresolved_mm = (
        float(monthly_df["unresolved_numeric_member_months"].sum())
        if not monthly_df.empty else 0.0
    )
    dup_keys = (
        int(monthly_df["duplicate_contract_plan_keys"].sum())
        if not monthly_df.empty else 0
    )

    checks = [
        (
            "All 12 CY2022 CPSC months processed",
            len(monthly_df) == 12,
            f"{len(monthly_df)}/12",
        ),
        (
            "No diagnostic execution/source errors",
            len(errors) == 0,
            str(len(errors)),
        ),
        (
            "No duplicate contract-plan keys",
            dup_keys == 0,
            str(dup_keys),
        ),
        (
            "No unresolved WA contract-plan member-months",
            abs(unresolved_mm) <= TOL_MM,
            f"{unresolved_mm:,.0f}",
        ),
        (
            "HMO member-months reproduce dedicated CY2022 control",
            abs(hmo - CONTROL["HMO"]) <= TOL_MM,
            f"observed={hmo:,.0f}; control={CONTROL['HMO']:,.0f}; "
            f"diff={hmo-CONTROL['HMO']:,.0f}",
        ),
        (
            "Local PPO member-months reproduce dedicated CY2022 control",
            abs(ppo - CONTROL["LOCAL PPO"]) <= TOL_MM,
            f"observed={ppo:,.0f}; control={CONTROL['LOCAL PPO']:,.0f}; "
            f"diff={ppo-CONTROL['LOCAL PPO']:,.0f}",
        ),
        (
            "Combined HMO + Local PPO member-months reproduce control",
            abs(combined - CONTROL_COMBINED) <= TOL_MM,
            f"observed={combined:,.0f}; control={CONTROL_COMBINED:,.0f}; "
            f"diff={combined-CONTROL_COMBINED:,.0f}",
        ),
    ]

    overall = all(x[1] for x in checks)

    lines = []
    lines.append("=" * 112)
    lines.append(
        "CMS MA PART C — CY2022 PLAN-TYPE BOUNDARY DIAGNOSTIC v0.1"
    )
    lines.append("=" * 112)
    lines.append("")
    lines.append("READ-ONLY DIAGNOSTIC")
    lines.append("")
    lines.append(f"Months processed                         : {len(monthly_df)}")
    lines.append(f"HMO member-months                       : {hmo:,.0f}")
    lines.append(f"Local PPO member-months                 : {ppo:,.0f}")
    lines.append(f"HMO + Local PPO member-months           : {combined:,.0f}")
    lines.append(f"Unresolved contract-plan member-months  : {unresolved_mm:,.0f}")
    lines.append(f"Duplicate contract-plan keys            : {dup_keys:,}")
    lines.append("")
    lines.append("DEDICATED CY2022 CONTROLS")
    lines.append("-" * 112)
    lines.append(f"HMO                                      : {CONTROL['HMO']:,.0f}")
    lines.append(f"Local PPO                                : {CONTROL['LOCAL PPO']:,.0f}")
    lines.append(f"Combined                                 : {CONTROL_COMBINED:,.0f}")
    lines.append("")
    lines.append("VALIDATION CHECKS")
    lines.append("-" * 112)
    for label, passed, detail in checks:
        lines.append(
            f"{'PASS' if passed else 'FAIL'}  {label}: {detail}"
        )
    lines.append("")
    lines.append(
        "OVERALL CY2022 PLAN-TYPE BOUNDARY DIAGNOSTIC STATUS: "
        + ("PASS" if overall else "FAIL")
    )
    lines.append("")
    lines.append("INTERPRETATION")
    lines.append("-" * 112)
    if overall:
        lines.append(
            "PASS establishes that the generalized production CPSC "
            "contract-dimension boundary retains both HMO and Local PPO "
            "and exactly reproduces the dedicated CY2022 member-month "
            "controls. If downstream production reconstruction remains "
            "Local-PPO-only, the HMO loss occurs after this boundary."
        )
    else:
        lines.append(
            "FAIL is informative. The detailed monthly, plan-type, and "
            "unresolved outputs identify whether HMO is lost or "
            "misclassified at the CPSC contract-dimension boundary. "
            "Do not weaken controls or modify source data merely to "
            "obtain PASS."
        )

    if errors:
        lines.append("")
        lines.append("ERRORS")
        lines.append("-" * 112)
        lines.extend(errors)

    lines.append("")
    lines.append(f"Output directory: {OUTDIR}")

    summary = "\n".join(lines) + "\n"
    SUMMARY_OUT.write_text(summary, encoding="utf-8")

    print()
    print(summary)

    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
