#!/usr/bin/env python3
"""
WCFFBP — Reconcile WA Medicare Advantage Part C reconstruction to
Medicare Trustees IV.C3 preferred controls v0.1

READ-ONLY diagnostic reconciliation.

Purpose
-------
Join:
  1) validated Washington MA Part C calendar-year reconstruction; and
  2) certified preferred Medicare Trustees IV.C3 controls.

This first reconciliation does NOT require Washington to equal national
Trustees values. It measures comparable annual per-enrollee payment levels
and component relationships while preserving known universe differences.

Rules
-----
- CY2015-2016: Trustees Local CCP is combined; do not manufacture HMO/PPO split.
- CY2017-2024: use Trustees HMO and PPO controls where published.
- WA CY2024 remains PARTIAL_JAN_SEP.
- No imputation.
- No DB writes.
- No ledger authorization.
- Trustees selected controls come only from the preferred-vintage certification.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CMS = ROOT / "data" / "raw" / "cms"

WA = (
    CMS / "medicare_advantage" / "validation" / "payment_reconstruction"
    / "cms_ma_partc_payment_reconstruction_calendar_year.csv"
)
TR = (
    CMS / "medicare_trustees" / "validation"
    / "preferred_vintage_certification_v0_1"
    / "trustees_preferred_vintage_controls.csv"
)
OUT = (
    CMS / "medicare_advantage" / "validation"
    / "trustees_ivc3_reconciliation_v0_3"
)

YEARS = set(range(2015, 2025))


def rd(p: Path) -> list[dict[str, str]]:
    with p.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def wr(p: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def ii(x: Any) -> int | None:
    try:
        return int(float(str(x).strip().replace(",", "")))
    except Exception:
        return None


def ff(x: Any) -> float | None:
    try:
        v = float(str(x).strip().replace(",", "").replace("$", ""))
        return v if math.isfinite(v) else None
    except Exception:
        return None


def first_num(r: dict[str, str], names: list[str]) -> float | None:
    for n in names:
        if n in r:
            v = ff(r.get(n))
            if v is not None:
                return v
    return None


def first_int(r: dict[str, str], names: list[str]) -> int | None:
    for n in names:
        if n in r:
            v = ii(r.get(n))
            if v is not None:
                return v
    return None


def pct(a: float | None, b: float | None) -> float | str:
    # percent difference: WA relative to Trustees
    if a is None or b in (None, 0):
        return ""
    return (a - b) / b * 100.0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [p for p in (WA, TR) if not p.exists()]
    if missing:
        print("FAIL: required validated input(s) missing:")
        for p in missing:
            print(p)
        return 1

    wa = rd(WA)
    tr = rd(TR)
    errors: list[dict[str, Any]] = []

    print("=" * 120)
    print("CMS MA PART C — WASHINGTON vs MEDICARE TRUSTEES IV.C3 RECONCILIATION v0.3")
    print("=" * 120)
    print()
    print("READ-ONLY diagnostic reconciliation; equality is NOT required.")
    print()

    # Show detected WA schema because this is the first cross-source join.
    wa_fields = list(wa[0].keys()) if wa else []
    print("WA calendar-year source:", WA)
    print("WA rows read:", f"{len(wa):,}")
    print("WA columns:", ", ".join(wa_fields))
    print()

    # Normalize WA annual totals. Current validated reconstruction is an aggregate
    # HMO/HMOPOS + Local PPO universe, so this v0.1 compares that aggregate only
    # to an enrollment-weighted Trustees local-CCP control where possible.
    wa_by_year: dict[int, dict[str, Any]] = {}
    for r in wa:
        y = first_int(r, ["payment_year", "calendar_year", "year", "cy", "observation_year"])
        if y not in YEARS:
            continue

        mm = first_int(r, [
            "reconstructed_enrollment", "reconstructed_member_months", "member_months",
            "published_enrollment", "published_target_member_months", "published_member_months"
        ])
        ab = first_num(r, [
            "risk_adjusted_ab_dollars", "ab_payment_dollars_reconstructed",
            "ab_dollars", "reconstructed_ab_dollars"
        ])
        rebate = first_num(r, [
            "rebate_dollars", "reconstructed_rebate_dollars"
        ])
        total = first_num(r, [
            "reconstructed_part_c_dollars", "part_c_dollars",
            "total_part_c_dollars", "reconstructed_dollars"
        ])

        # Fallback: use component identity if total column name differs.
        if total is None and ab is not None and rebate is not None:
            total = ab + rebate

        if mm is None or mm <= 0:
            errors.append({
                "error_type": "WA_MEMBER_MONTHS_UNRESOLVED",
                "year": y,
                "detail": str(r),
            })
            continue
        if ab is None or rebate is None or total is None:
            errors.append({
                "error_type": "WA_PAYMENT_COMPONENT_UNRESOLVED",
                "year": y,
                "detail": str(r),
            })
            continue

        wa_by_year[y] = {
            "member_months": mm,
            "ab_dollars": ab,
            "rebate_dollars": rebate,
            "total_dollars": total,
            # Trustees IV.C3 is annual incurred expenditure per enrollee.
            # Annualizing WA PMPM by x12 creates the comparable scale.
            "ab_annual_per_enrollee": ab / mm * 12.0,
            "rebate_annual_per_enrollee": rebate / mm * 12.0,
            "total_annual_per_enrollee": total / mm * 12.0,
        }

    # Preferred IV.C3 controls.
    ivc3 = [
        r for r in tr
        if r.get("table_id") == "IV.C3"
        and ii(r.get("observation_year")) in YEARS
    ]

    # Inventory source plan labels before mapping.
    plan_inventory = sorted({
        (r.get("plan_type_normalized", ""), r.get("plan_type_source", ""))
        for r in ivc3
    })

    # Index component values by year and normalized plan.
    tindex: dict[tuple[int, str, str], dict[str, Any]] = {}
    for r in ivc3:
        y = ii(r.get("observation_year"))
        plan = r.get("plan_type_normalized", "")
        comp = r.get("component_normalized", "")
        val = ff(r.get("selected_value"))
        if y is None or val is None:
            continue
        tindex[(y, plan, comp)] = {
            "value": val,
            "vintage": ii(r.get("selected_trustees_vintage")),
            "unit": r.get("unit", ""),
            "basis": r.get("basis", ""),
            "accounting_scope": r.get("accounting_scope", ""),
        }

    # Candidate local-plan labels, based on previously validated Trustees structure.
    combined_candidates = ["LOCAL_CCP", "LCCP", "LOCAL_CCP_COMBINED"]
    hmo_candidates = ["LOCAL_CCP_HMO", "HMO"]
    ppo_candidates = ["LOCAL_CCP_PPO", "PPO", "LOCAL_PPO"]

    def find_plan(year: int, candidates: list[str]) -> str | None:
        available = {p for (y, p, c) in tindex if y == year}
        for p in candidates:
            if p in available:
                return p
        return None

    rows: list[dict[str, Any]] = []

    for y in sorted(YEARS):
        w = wa_by_year.get(y)
        if not w:
            continue

        if y <= 2016:
            plan = find_plan(y, combined_candidates)
            if not plan:
                errors.append({
                    "error_type": "TRUSTEES_COMBINED_LOCAL_CCP_NOT_FOUND",
                    "year": y,
                    "detail": "Expected combined Local CCP for early-year comparison",
                })
                continue
            plans = [plan]
            comparison_scope = "WA_HMO_HMOPOS_PLUS_LOCAL_PPO_vs_TRUSTEES_COMBINED_LOCAL_CCP"
        else:
            hmo = find_plan(y, hmo_candidates)
            ppo = find_plan(y, ppo_candidates)
            if not hmo or not ppo:
                errors.append({
                    "error_type": "TRUSTEES_HMO_PPO_NOT_FOUND",
                    "year": y,
                    "detail": f"hmo={hmo}; ppo={ppo}",
                })
                continue
            # WA annual reconstruction file is aggregate. We cannot validly create
            # an enrollment-weighted Trustees HMO+PPO value without independent
            # HMO/PPO WA member-month weights in this file. Therefore publish the
            # two national controls side-by-side and defer exact aggregate weighting.
            plans = [hmo, ppo]
            comparison_scope = "WA_AGGREGATE_WITH_TRUSTEES_HMO_AND_PPO_BOUNDS_CONTEXT"

        for plan in plans:
            bid = tindex.get((y, plan, "BID_BASED"))
            rebate = tindex.get((y, plan, "REBATE"))
            total = tindex.get((y, plan, "TOTAL"))

            if not bid or not rebate or not total:
                errors.append({
                    "error_type": "TRUSTEES_COMPONENT_MISSING",
                    "year": y,
                    "detail": f"plan={plan}; bid={bool(bid)} rebate={bool(rebate)} total={bool(total)}",
                })
                continue

            identity = bid["value"] + rebate["value"] - total["value"]

            rows.append({
                "calendar_year": y,
                "wa_period_status": "PARTIAL_JAN_SEP" if y == 2024 else "COMPLETE",
                "comparison_scope": comparison_scope,
                "trustees_plan_type": plan,
                "trustees_selected_vintage": total["vintage"],
                "trustees_unit": total["unit"],
                "trustees_basis": total["basis"],
                "wa_member_months": w["member_months"],
                "wa_ab_annual_per_enrollee": w["ab_annual_per_enrollee"],
                "wa_rebate_annual_per_enrollee": w["rebate_annual_per_enrollee"],
                "wa_total_annual_per_enrollee": w["total_annual_per_enrollee"],
                "trustees_bid_based_annual_per_enrollee": bid["value"],
                "trustees_rebate_annual_per_enrollee": rebate["value"],
                "trustees_total_annual_per_enrollee": total["value"],
                "trustees_component_identity_difference": identity,
                "wa_vs_trustees_bid_percent": pct(w["ab_annual_per_enrollee"], bid["value"]),
                "wa_vs_trustees_rebate_percent": pct(w["rebate_annual_per_enrollee"], rebate["value"]),
                "wa_vs_trustees_total_percent": pct(w["total_annual_per_enrollee"], total["value"]),
                "reconciliation_status": "DIAGNOSTIC_ONLY",
            })

    # Checks deliberately test structure/accounting, not equality.
    years_out = {ii(r["calendar_year"]) for r in rows}
    trustees_identity_ok = all(
        abs(float(r["trustees_component_identity_difference"])) <= 1.1
        for r in rows
    ) if rows else False

    checks = [
        ("WA validated calendar-year reconstruction loaded", bool(wa)),
        ("Preferred Trustees controls loaded", bool(tr)),
        ("WA CY2015-CY2024 recognized", set(wa_by_year) == YEARS),
        ("IV.C3 preferred controls recognized", bool(ivc3)),
        ("Reconciliation rows produced", bool(rows)),
        ("CY2015-CY2024 represented in reconciliation", years_out == YEARS),
        ("Trustees BID + REBATE = TOTAL within published precision", trustees_identity_ok),
        ("CY2024 explicitly marked PARTIAL_JAN_SEP",
         any(ii(r["calendar_year"]) == 2024 and r["wa_period_status"] == "PARTIAL_JAN_SEP" for r in rows)),
        ("No source-resolution errors", not errors),
    ]
    overall = all(ok for _, ok in checks)

    fields = [
        "calendar_year", "wa_period_status", "comparison_scope",
        "trustees_plan_type", "trustees_selected_vintage",
        "trustees_unit", "trustees_basis", "wa_member_months",
        "wa_ab_annual_per_enrollee", "wa_rebate_annual_per_enrollee",
        "wa_total_annual_per_enrollee",
        "trustees_bid_based_annual_per_enrollee",
        "trustees_rebate_annual_per_enrollee",
        "trustees_total_annual_per_enrollee",
        "trustees_component_identity_difference",
        "wa_vs_trustees_bid_percent", "wa_vs_trustees_rebate_percent",
        "wa_vs_trustees_total_percent", "reconciliation_status",
    ]
    wr(OUT / "wa_vs_trustees_ivc3_reconciliation.csv", rows, fields)
    wr(
        OUT / "wa_vs_trustees_ivc3_reconciliation_errors.csv",
        errors, ["error_type", "year", "detail"]
    )
    wr(
        OUT / "trustees_ivc3_plan_type_inventory.csv",
        [{"plan_type_normalized": a, "plan_type_source": b} for a, b in plan_inventory],
        ["plan_type_normalized", "plan_type_source"],
    )

    lines = [
        "=" * 120,
        "CMS MA PART C — WASHINGTON vs MEDICARE TRUSTEES IV.C3 RECONCILIATION v0.3",
        "=" * 120,
        "",
        "READ-ONLY DIAGNOSTIC RECONCILIATION",
        "",
        f"WA calendar-year rows read                    : {len(wa):,}",
        f"WA years normalized                           : {len(wa_by_year):,}",
        f"Preferred IV.C3 control rows                  : {len(ivc3):,}",
        f"Reconciliation comparison rows                : {len(rows):,}",
        f"Source-resolution errors                      : {len(errors):,}",
        "",
        "COMPARISON RESULTS",
        "-" * 120,
    ]
    for r in rows:
        lines.append(
            f"CY{r['calendar_year']} {r['trustees_plan_type']} "
            f"[{r['wa_period_status']}]: "
            f"WA total annual/enrollee={float(r['wa_total_annual_per_enrollee']):,.2f}; "
            f"Trustees={float(r['trustees_total_annual_per_enrollee']):,.2f}; "
            f"diff={r['wa_vs_trustees_total_percent']:.2f}%"
        )

    lines += ["", "VALIDATION CHECKS", "-" * 120]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)
    lines += [
        "",
        f"OVERALL RECONCILIATION PROFILER STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "PASS means the validated WA reconstruction and certified Trustees IV.C3 controls",
        "were joined successfully and compared on an annual-per-enrollee scale.",
        "PASS does NOT require WA to equal national Trustees values.",
        "PASS does NOT establish complete CY2024, final reconciliation certification,",
        "or ledger authorization.",
        "",
        "IMPORTANT v0.3 LIMITATION",
        "The validated WA calendar-year reconstruction is aggregate HMO/HMOPOS + Local PPO.",
        "For CY2017+, Trustees HMO and PPO controls are therefore shown separately rather",
        "than combined with invented weights. A later reconciliation step may use actual",
        "WA plan-type member-month weights if available from validated reconstruction cells.",
        "",
        f"Output directory: {OUT}",
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "wa_vs_trustees_ivc3_reconciliation_summary.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
