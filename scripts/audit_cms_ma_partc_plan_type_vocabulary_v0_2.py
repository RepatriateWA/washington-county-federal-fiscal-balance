#!/usr/bin/env python
"""
CMS MA Part C raw CPSC plan-type vocabulary audit v0.2

READ-ONLY with respect to source files and PostgreSQL.

Scope
-----
October 2014 through September 2024 (120 months).

Purpose
-------
Inventory every raw CPSC contract Plan Type observed among Washington county
enrollment after successful Contract Number + Plan ID linkage, show how the
current production canonical_plan_type() classifies it, quantify numeric
member-months, and flag whether the current production target filter
{"HMO", "LOCAL PPO"} includes it.

This audit is deliberately run BEFORE changing the production canonicalizer.
It is intended to establish an evidence-based vocabulary for the entire
validated monthly source universe.
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
        "FAIL: could not import production linkage module\n"
        f"{type(exc).__name__}: {exc}"
    )

OUTDIR = (
    ROOT / "data" / "raw" / "cms" / "medicare_advantage" / "validation"
    / "plan_type_vocabulary_audit_v0_2"
)
DETAIL_OUT = OUTDIR / "cms_ma_partc_plan_type_vocabulary_monthly_v0_2.csv"
SUMMARY_CSV = OUTDIR / "cms_ma_partc_plan_type_vocabulary_summary_v0_2.csv"
UNRESOLVED_OUT = OUTDIR / "cms_ma_partc_plan_type_unresolved_v0_2.csv"
SUMMARY_TXT = OUTDIR / "cms_ma_partc_plan_type_vocabulary_audit_summary_v0_2.txt"

START = "2014-10"
END = "2024-09"
EXPECTED_MONTHS = 120
CURRENT_TARGET = {"HMO", "LOCAL PPO"}


def clean(x) -> str:
    return prod.clean(x)


def column(df, *aliases):
    return prod.column(df, *aliases)


def normalize_manifest_period(x) -> str:
    s = clean(x)
    try:
        return str(pd.Period(s, freq="M"))
    except Exception:
        return s


def resolve_source_path(value: str) -> Path:
    """Resolve manifest path robustly without assuming one path representation."""
    s = clean(value)
    p = Path(s)
    if p.is_absolute():
        return p
    return ROOT / p


def find_manifest() -> Path:
    p = (
        ROOT / "data" / "raw" / "cms" / "medicare_advantage" / "validation"
        / "source_acquisition"
        / "cms_ma_partc_source_acquisition_manifest.csv"
    )
    if not p.exists():
        raise FileNotFoundError(f"Manifest not found: {p}")
    return p


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    manifest_path = find_manifest()
    manifest = pd.read_csv(manifest_path, dtype=str).fillna("")

    required = {"source_type", "period", "status", "local_path"}
    missing = required - set(manifest.columns)
    if missing:
        raise SystemExit(
            "FAIL: manifest missing required columns: "
            + ", ".join(sorted(missing))
        )

    manifest["source_type_norm"] = manifest["source_type"].map(clean).str.upper()
    manifest["status_norm"] = manifest["status"].map(clean).str.upper()
    manifest["period_norm"] = manifest["period"].map(normalize_manifest_period)

    cpsc = manifest[
        (manifest["source_type_norm"] == "CPSC")
        & (manifest["status_norm"] == "PASS")
    ].copy()

    by_period = {}
    duplicate_manifest_periods = []
    for period, group in cpsc.groupby("period_norm"):
        if len(group) != 1:
            duplicate_manifest_periods.append((period, len(group)))
            continue
        by_period[period] = resolve_source_path(group.iloc[0]["local_path"])

    periods = [str(p) for p in pd.period_range(START, END, freq="M")]

    detail_rows = []
    unresolved_rows = []
    errors = []
    months_processed = 0
    total_duplicate_contract_keys = 0

    print("=" * 112)
    print("CMS MA PART C — RAW CPSC PLAN-TYPE VOCABULARY AUDIT v0.2")
    print("=" * 112)
    print(f"Scope: {START} through {END} ({EXPECTED_MONTHS} months)")
    print("READ-ONLY SOURCE/DB AUDIT")
    print()

    for i, period in enumerate(periods, 1):
        print(f"[{i:03d}/{EXPECTED_MONTHS}] {period}", end=" ", flush=True)

        path = by_period.get(period)
        if path is None:
            errors.append(f"{period}: no unique PASS CPSC source in manifest")
            print("FAIL: source resolution")
            continue
        if not path.exists():
            errors.append(f"{period}: source path missing: {path}")
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
                "canonical_plan_type": contracts[c_type].map(
                    prod.canonical_plan_type
                ),
                "snp_flag": contracts[c_snp].map(clean).str.upper(),
                "eghp": contracts[c_eghp].map(clean).str.upper(),
            })

            dup_keys = int(
                contract_dim.loc[
                    contract_dim.duplicated(
                        ["contract", "plan_id"], keep=False
                    ),
                    ["contract", "plan_id"],
                ].drop_duplicates().shape[0]
            )
            total_duplicate_contract_keys += dup_keys

            # Mirror production behavior.
            contract_dim = contract_dim.drop_duplicates(
                ["contract", "plan_id"]
            )

            e_contract = column(enrollment, "Contract Number")
            e_plan = column(enrollment, "Plan ID")
            e_state = column(enrollment, "State")
            e_county = column(enrollment, "County")
            e_enroll = column(enrollment, "Enrollment")

            e = pd.DataFrame({
                "contract": enrollment[e_contract].map(clean),
                "plan_id": enrollment[e_plan].map(prod.normalize_plan_id),
                "state": enrollment[e_state].map(clean).str.upper(),
                "county": enrollment[e_county].map(clean),
                "enrollment_raw": enrollment[e_enroll].map(clean),
            })
            e = e[e["state"] == "WA"].copy()
            e["enrollment"] = pd.to_numeric(
                e["enrollment_raw"], errors="coerce"
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

            for _, row in unresolved.iterrows():
                unresolved_rows.append({
                    "period": period,
                    "contract": row["contract"],
                    "plan_id": row["plan_id"],
                    "county": row["county"],
                    "enrollment_raw": row["enrollment_raw"],
                    "enrollment": row["enrollment"],
                })

            numeric = resolved[resolved["enrollment"].notna()].copy()
            suppressed = resolved[resolved["enrollment"].isna()].copy()

            # Aggregate both numeric and suppressed row counts by raw/canonical
            # vocabulary so source terminology is visible even where enrollment
            # is not numeric.
            keys = ["raw_plan_type", "canonical_plan_type"]

            num_agg = (
                numeric.groupby(keys, dropna=False)
                .agg(
                    numeric_rows=("enrollment", "size"),
                    numeric_member_months=("enrollment", "sum"),
                )
                .reset_index()
            )

            sup_agg = (
                suppressed.groupby(keys, dropna=False)
                .size()
                .reset_index(name="suppressed_rows")
            )

            vocab = num_agg.merge(sup_agg, on=keys, how="outer").fillna({
                "numeric_rows": 0,
                "numeric_member_months": 0.0,
                "suppressed_rows": 0,
            })

            for _, row in vocab.iterrows():
                canonical = clean(row["canonical_plan_type"])
                detail_rows.append({
                    "period": period,
                    "raw_plan_type": clean(row["raw_plan_type"]),
                    "canonical_plan_type": canonical,
                    "included_by_current_target_filter": (
                        canonical in CURRENT_TARGET
                    ),
                    "numeric_rows": int(row["numeric_rows"]),
                    "numeric_member_months": float(
                        row["numeric_member_months"]
                    ),
                    "suppressed_rows": int(row["suppressed_rows"]),
                    "duplicate_contract_plan_keys_in_month": dup_keys,
                })

            months_processed += 1

            hmo_slash = float(
                numeric.loc[
                    numeric["raw_plan_type"].str.upper() == "HMO/HMOPOS",
                    "enrollment",
                ].sum()
            )
            hmo_current = float(
                numeric.loc[
                    numeric["canonical_plan_type"] == "HMO",
                    "enrollment",
                ].sum()
            )
            ppo_current = float(
                numeric.loc[
                    numeric["canonical_plan_type"] == "LOCAL PPO",
                    "enrollment",
                ].sum()
            )
            print(
                f"raw HMO/HMOPOS={hmo_slash:,.0f} "
                f"canonical HMO={hmo_current:,.0f} "
                f"PPO={ppo_current:,.0f}"
            )

        except Exception as exc:
            errors.append(f"{period}: {type(exc).__name__}: {exc}")
            print(f"FAIL: {type(exc).__name__}: {exc}")

    detail = pd.DataFrame(detail_rows)
    unresolved = pd.DataFrame(unresolved_rows)

    detail.to_csv(DETAIL_OUT, index=False)
    unresolved.to_csv(UNRESOLVED_OUT, index=False)

    if detail.empty:
        summary = pd.DataFrame(columns=[
            "raw_plan_type", "canonical_plan_type",
            "included_by_current_target_filter",
            "first_month", "last_month", "months_observed",
            "numeric_rows", "numeric_member_months", "suppressed_rows",
        ])
    else:
        summary = (
            detail.groupby(
                [
                    "raw_plan_type",
                    "canonical_plan_type",
                    "included_by_current_target_filter",
                ],
                dropna=False,
            )
            .agg(
                first_month=("period", "min"),
                last_month=("period", "max"),
                months_observed=("period", "nunique"),
                numeric_rows=("numeric_rows", "sum"),
                numeric_member_months=("numeric_member_months", "sum"),
                suppressed_rows=("suppressed_rows", "sum"),
            )
            .reset_index()
            .sort_values(
                ["numeric_member_months", "raw_plan_type"],
                ascending=[False, True],
            )
        )

    summary.to_csv(SUMMARY_CSV, index=False)

    unresolved_numeric_mm = (
        float(unresolved["enrollment"].dropna().sum())
        if not unresolved.empty else 0.0
    )

    hmo_slash_rows = summary[
        summary["raw_plan_type"].str.upper() == "HMO/HMOPOS"
    ] if not summary.empty else summary
    hmo_slash_mm = (
        float(hmo_slash_rows["numeric_member_months"].sum())
        if not hmo_slash_rows.empty else 0.0
    )
    hmo_slash_months = (
        int(hmo_slash_rows["months_observed"].max())
        if not hmo_slash_rows.empty else 0
    )

    suspicious = summary[
        (~summary["included_by_current_target_filter"])
        & (
            summary["raw_plan_type"].str.upper().str.contains(
                r"HMO|PPO|PREFERRED PROVIDER|HEALTH MAINTENANCE",
                regex=True,
                na=False,
            )
        )
    ].copy() if not summary.empty else summary

    checks = [
        (
            "All required months processed",
            months_processed == EXPECTED_MONTHS,
            f"{months_processed}/{EXPECTED_MONTHS}",
        ),
        (
            "No execution/source-resolution errors",
            len(errors) == 0,
            str(len(errors)),
        ),
        (
            "No duplicate contract-plan keys",
            total_duplicate_contract_keys == 0,
            str(total_duplicate_contract_keys),
        ),
        (
            "No unresolved numeric WA member-months",
            abs(unresolved_numeric_mm) < 0.01,
            f"{unresolved_numeric_mm:,.0f}",
        ),
        (
            "Raw HMO/HMOPOS vocabulary observed",
            hmo_slash_mm > 0,
            f"{hmo_slash_mm:,.0f} member-months; "
            f"{hmo_slash_months} months represented",
        ),
    ]

    # This is an AUDIT, not a demand that the old canonicalizer be correct.
    # Presence of an HMO-like excluded label is the evidence we are looking for.
    audit_complete = all(passed for _, passed, _ in checks)

    lines = [
        "=" * 112,
        "CMS MA PART C — RAW CPSC PLAN-TYPE VOCABULARY AUDIT v0.2",
        "=" * 112,
        "",
        f"Scope                                  : {START} through {END}",
        f"Required months                        : {EXPECTED_MONTHS}",
        f"Months processed                       : {months_processed}",
        f"Distinct raw/canonical vocabulary rows : {len(summary)}",
        f"Unresolved numeric WA member-months    : {unresolved_numeric_mm:,.0f}",
        f"Duplicate contract-plan keys           : {total_duplicate_contract_keys:,}",
        "",
        "AUDIT CHECKS",
        "-" * 112,
    ]

    for label, passed, detail_text in checks:
        lines.append(
            f"{'PASS' if passed else 'FAIL'}  {label}: {detail_text}"
        )

    lines += [
        "",
        "PLAN-TYPE VOCABULARY",
        "-" * 112,
    ]

    for _, r in summary.iterrows():
        lines.append(
            f"{r['raw_plan_type']!r} -> "
            f"{r['canonical_plan_type']!r} | "
            f"target={'YES' if r['included_by_current_target_filter'] else 'NO'} | "
            f"{r['first_month']}..{r['last_month']} | "
            f"months={int(r['months_observed'])} | "
            f"member-months={float(r['numeric_member_months']):,.0f} | "
            f"suppressed rows={int(r['suppressed_rows']):,}"
        )

    lines += [
        "",
        "HMO/PPO-LIKE LABELS EXCLUDED BY CURRENT TARGET FILTER",
        "-" * 112,
    ]

    if suspicious.empty:
        lines.append("None observed.")
    else:
        for _, r in suspicious.iterrows():
            lines.append(
                f"{r['raw_plan_type']!r} -> "
                f"{r['canonical_plan_type']!r} | "
                f"{r['first_month']}..{r['last_month']} | "
                f"months={int(r['months_observed'])} | "
                f"member-months={float(r['numeric_member_months']):,.0f}"
            )

    lines += [
        "",
        "AUDIT STATUS",
        "-" * 112,
        (
            "PASS — full requested source universe inventoried successfully."
            if audit_complete
            else
            "FAIL — source-universe audit is incomplete; inspect errors before "
            "changing production canonicalization."
        ),
        "",
        "IMPORTANT",
        "-" * 112,
        "PASS here does NOT certify the current production target filter. "
        "It certifies that the requested vocabulary audit completed and "
        "quantified the source terminology. Excluded HMO/PPO-like labels are "
        "expected evidence for the defect investigation.",
        "",
        f"Detailed monthly output : {DETAIL_OUT}",
        f"Vocabulary summary       : {SUMMARY_CSV}",
        f"Unresolved rows          : {UNRESOLVED_OUT}",
    ]

    if errors:
        lines += ["", "ERRORS", "-" * 112]
        lines.extend(errors)

    text = "\n".join(lines) + "\n"
    SUMMARY_TXT.write_text(text, encoding="utf-8")
    print()
    print(text)

    return 0 if audit_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
