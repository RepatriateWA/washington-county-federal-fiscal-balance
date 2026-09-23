#!/usr/bin/env python3
"""
WCFFBP — Weighted Washington vs Medicare Trustees IV.C3 reconciliation v0.1

READ-ONLY diagnostic.

Uses validated WA payment-reconstruction cells to derive actual WA member-month
weights for HMO/HMOPOS and Local PPO, then applies those weights to certified
preferred Medicare Trustees IV.C3 HMO/PPO controls.

CY2015 is preserved as Trustees LOCAL_CCP_COMBINED because the certified
preferred-control series retains that combined category.

CY2016-CY2024:
  weighted Trustees component =
      WA HMO member-month share * Trustees HMO component
    + WA Local PPO member-month share * Trustees PPO component

No imputation. No DB writes. No ledger authorization.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CMS = ROOT / "data" / "raw" / "cms"

CELLS = (
    CMS / "medicare_advantage" / "validation" / "payment_reconstruction"
    / "cms_ma_partc_payment_reconstruction_cells.csv"
)
ANNUAL = (
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
    / "trustees_ivc3_weighted_reconciliation_v0_2"
)

YEARS = range(2015, 2025)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(x: Any) -> float | None:
    try:
        v = float(str(x).strip().replace(",", "").replace("$", ""))
        return v if math.isfinite(v) else None
    except Exception:
        return None


def integer(x: Any) -> int | None:
    v = num(x)
    return int(v) if v is not None else None


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def pct(a: float, b: float) -> float | str:
    return "" if b == 0 else (a - b) / b * 100.0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    missing = [p for p in (CELLS, ANNUAL, TR) if not p.exists()]
    if missing:
        print("FAIL: required validated input(s) missing:")
        for p in missing:
            print(p)
        return 1

    cells = read_csv(CELLS)
    annual = read_csv(ANNUAL)
    controls = read_csv(TR)

    errors: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # WA plan-type member-month weights from validated reconstruction cells
    # ------------------------------------------------------------------
    mm = defaultdict(lambda: defaultdict(float))
    cell_dollars = defaultdict(lambda: defaultdict(float))

    recognized_plan_types = {"HMO": "HMO", "LOCAL PPO": "PPO"}
    observed_plan_types = set()

    for r in cells:
        y = integer(r.get("payment_year"))
        if y not in YEARS:
            continue
        raw_plan = (r.get("plan_type") or "").strip().upper()
        observed_plan_types.add(raw_plan)

        if raw_plan not in recognized_plan_types:
            errors.append({
                "error_type": "UNEXPECTED_WA_PLAN_TYPE",
                "year": y,
                "detail": raw_plan,
            })
            continue

        plan = recognized_plan_types[raw_plan]
        enrollment = num(r.get("enrollment"))
        ab = num(r.get("ab_dollars"))
        rebate = num(r.get("rebate_dollars"))
        total = num(r.get("partc_dollars"))

        if enrollment is None or ab is None or rebate is None or total is None:
            errors.append({
                "error_type": "NONNUMERIC_WA_CELL",
                "year": y,
                "detail": f"{r.get('period')} {r.get('contract')} {r.get('plan_id')} {r.get('county')}",
            })
            continue

        mm[y][plan] += enrollment
        cell_dollars[y][f"{plan}_AB"] += ab
        cell_dollars[y][f"{plan}_REBATE"] += rebate
        cell_dollars[y][f"{plan}_TOTAL"] += total

    # ------------------------------------------------------------------
    # Annual validated controls for cross-check
    # ------------------------------------------------------------------
    annual_idx = {}
    for r in annual:
        y = integer(r.get("payment_year"))
        if y in YEARS:
            annual_idx[y] = r

    # ------------------------------------------------------------------
    # Trustees preferred IV.C3 index
    # ------------------------------------------------------------------
    t = {}
    for r in controls:
        if r.get("table_id") != "IV.C3":
            continue
        y = integer(r.get("observation_year"))
        if y not in YEARS:
            continue
        v = num(r.get("selected_value"))
        if v is None:
            continue
        key = (
            y,
            (r.get("plan_type_normalized") or "").strip(),
            (r.get("component_normalized") or "").strip(),
        )
        t[key] = {
            "value": v,
            "vintage": integer(r.get("selected_trustees_vintage")),
            "unit": r.get("unit", ""),
            "basis": r.get("basis", ""),
        }

    rows = []
    weights = []

    for y in YEARS:
        hmo_mm = mm[y]["HMO"]
        ppo_mm = mm[y]["PPO"]
        total_mm = hmo_mm + ppo_mm

        if total_mm <= 0:
            errors.append({"error_type": "NO_WA_MEMBER_MONTHS", "year": y, "detail": ""})
            continue

        wh = hmo_mm / total_mm
        wp = ppo_mm / total_mm

        weights.append({
            "calendar_year": y,
            "hmo_member_months": hmo_mm,
            "local_ppo_member_months": ppo_mm,
            "total_member_months": total_mm,
            "hmo_weight": wh,
            "local_ppo_weight": wp,
            "weight_identity_difference": wh + wp - 1.0,
        })

        ar = annual_idx.get(y)
        if not ar:
            errors.append({"error_type": "ANNUAL_ROW_MISSING", "year": y, "detail": ""})
            continue

        annual_mm = num(ar.get("reconstructed_enrollment"))
        annual_ab = num(ar.get("ab_dollars"))
        annual_rebate = num(ar.get("rebate_dollars"))
        annual_total = num(ar.get("partc_dollars"))
        completeness = ar.get("year_completeness", "")

        if None in (annual_mm, annual_ab, annual_rebate, annual_total):
            errors.append({"error_type": "ANNUAL_NUMERIC_FIELD_MISSING", "year": y, "detail": str(ar)})
            continue

        # Cross-check cells against already validated annual reconstruction.
        mm_diff = total_mm - annual_mm
        ab_cell = cell_dollars[y]["HMO_AB"] + cell_dollars[y]["PPO_AB"]
        rebate_cell = cell_dollars[y]["HMO_REBATE"] + cell_dollars[y]["PPO_REBATE"]
        total_cell = cell_dollars[y]["HMO_TOTAL"] + cell_dollars[y]["PPO_TOTAL"]

        ab_diff = ab_cell - annual_ab
        rebate_diff = rebate_cell - annual_rebate
        total_diff = total_cell - annual_total

        wa_ab_annual = annual_ab / annual_mm * 12.0
        wa_rebate_annual = annual_rebate / annual_mm * 12.0
        wa_total_annual = annual_total / annual_mm * 12.0

        if y == 2015:
            plan = "LOCAL_CCP_COMBINED"
            tb = t.get((y, plan, "BID_BASED"))
            trb = t.get((y, plan, "REBATE"))
            tt = t.get((y, plan, "TOTAL"))
            if not all((tb, trb, tt)):
                errors.append({
                    "error_type": "TRUSTEES_2015_COMBINED_CONTROL_MISSING",
                    "year": y, "detail": plan
                })
                continue
            trustees_ab = tb["value"]
            trustees_rebate = trb["value"]
            trustees_total = tt["value"]
            vintage_note = str(tt["vintage"])
            scope = "CERTIFIED_COMBINED_LOCAL_CCP"
        else:
            needed = {}
            for plan in ("LOCAL_CCP_HMO", "LOCAL_CCP_PPO"):
                for comp in ("BID_BASED", "REBATE", "TOTAL"):
                    needed[(plan, comp)] = t.get((y, plan, comp))
            if not all(needed.values()):
                errors.append({
                    "error_type": "TRUSTEES_HMO_PPO_CONTROL_MISSING",
                    "year": y,
                    "detail": str([k for k, v in needed.items() if not v]),
                })
                continue

            trustees_ab = (
                wh * needed[("LOCAL_CCP_HMO", "BID_BASED")]["value"]
                + wp * needed[("LOCAL_CCP_PPO", "BID_BASED")]["value"]
            )
            trustees_rebate = (
                wh * needed[("LOCAL_CCP_HMO", "REBATE")]["value"]
                + wp * needed[("LOCAL_CCP_PPO", "REBATE")]["value"]
            )
            trustees_total = (
                wh * needed[("LOCAL_CCP_HMO", "TOTAL")]["value"]
                + wp * needed[("LOCAL_CCP_PPO", "TOTAL")]["value"]
            )
            vintages = sorted({
                needed[(p, c)]["vintage"]
                for p in ("LOCAL_CCP_HMO", "LOCAL_CCP_PPO")
                for c in ("BID_BASED", "REBATE", "TOTAL")
            })
            vintage_note = ";".join(str(v) for v in vintages)
            scope = "WA_MEMBER_MONTH_WEIGHTED_HMO_PLUS_LOCAL_PPO"

        rows.append({
            "calendar_year": y,
            "wa_period_status": completeness,
            "comparison_scope": scope,
            "hmo_member_months": hmo_mm,
            "local_ppo_member_months": ppo_mm,
            "total_member_months": total_mm,
            "hmo_weight": wh,
            "local_ppo_weight": wp,
            "annual_vs_cell_member_month_difference": mm_diff,
            "annual_vs_cell_ab_dollar_difference": ab_diff,
            "annual_vs_cell_rebate_dollar_difference": rebate_diff,
            "annual_vs_cell_total_dollar_difference": total_diff,
            "wa_ab_annual_per_enrollee": wa_ab_annual,
            "wa_rebate_annual_per_enrollee": wa_rebate_annual,
            "wa_total_annual_per_enrollee": wa_total_annual,
            "trustees_ab_weighted_annual_per_enrollee": trustees_ab,
            "trustees_rebate_weighted_annual_per_enrollee": trustees_rebate,
            "trustees_total_weighted_annual_per_enrollee": trustees_total,
            "trustees_component_identity_difference": trustees_ab + trustees_rebate - trustees_total,
            "wa_vs_trustees_ab_percent": pct(wa_ab_annual, trustees_ab),
            "wa_vs_trustees_rebate_percent": pct(wa_rebate_annual, trustees_rebate),
            "wa_vs_trustees_total_percent": pct(wa_total_annual, trustees_total),
            "trustees_selected_vintages": vintage_note,
            "reconciliation_status": "DIAGNOSTIC_ONLY",
        })

    # Structural/accounting gates, not numerical-closeness gates.
    years_out = {integer(r["calendar_year"]) for r in rows}
    weight_ok = all(abs(float(r["hmo_weight"]) + float(r["local_ppo_weight"]) - 1.0) < 1e-12 for r in rows)
    cell_mm_ok = all(abs(float(r["annual_vs_cell_member_month_difference"])) < 1e-6 for r in rows)
    cell_ab_ok = all(abs(float(r["annual_vs_cell_ab_dollar_difference"])) < 0.01 for r in rows)
    cell_rebate_ok = all(abs(float(r["annual_vs_cell_rebate_dollar_difference"])) < 0.01 for r in rows)
    cell_total_ok = all(abs(float(r["annual_vs_cell_total_dollar_difference"])) < 0.01 for r in rows)
    trustees_identity_ok = all(abs(float(r["trustees_component_identity_difference"])) <= 1.1 for r in rows)

    checks = [
        ("Validated WA cells loaded", bool(cells)),
        ("Validated WA annual reconstruction loaded", bool(annual)),
        ("Certified preferred Trustees controls loaded", bool(controls)),
        ("Only expected WA plan types observed", observed_plan_types <= set(recognized_plan_types)),
        ("CY2015-CY2024 represented", years_out == set(YEARS)),
        ("WA HMO + PPO weights sum to 1", weight_ok),
        ("Cell member-month totals reproduce annual reconstruction", cell_mm_ok),
        ("Cell A/B dollars reproduce annual reconstruction", cell_ab_ok),
        ("Cell rebate dollars reproduce annual reconstruction", cell_rebate_ok),
        ("Cell total Part C dollars reproduce annual reconstruction", cell_total_ok),
        ("Trustees BID + REBATE = TOTAL within published precision", trustees_identity_ok),
        ("CY2024 remains partial", any(
            integer(r["calendar_year"]) == 2024
            and "PARTIAL" in str(r["wa_period_status"]).upper()
            for r in rows
        )),
        ("No source-resolution errors", not errors),
    ]
    overall = all(ok for _, ok in checks)

    weight_fields = [
        "calendar_year", "hmo_member_months", "local_ppo_member_months",
        "total_member_months", "hmo_weight", "local_ppo_weight",
        "weight_identity_difference"
    ]
    write_csv(OUT / "wa_plan_type_member_month_weights.csv", weights, weight_fields)

    fields = [
        "calendar_year", "wa_period_status", "comparison_scope",
        "hmo_member_months", "local_ppo_member_months", "total_member_months",
        "hmo_weight", "local_ppo_weight",
        "annual_vs_cell_member_month_difference",
        "annual_vs_cell_ab_dollar_difference",
        "annual_vs_cell_rebate_dollar_difference",
        "annual_vs_cell_total_dollar_difference",
        "wa_ab_annual_per_enrollee", "wa_rebate_annual_per_enrollee",
        "wa_total_annual_per_enrollee",
        "trustees_ab_weighted_annual_per_enrollee",
        "trustees_rebate_weighted_annual_per_enrollee",
        "trustees_total_weighted_annual_per_enrollee",
        "trustees_component_identity_difference",
        "wa_vs_trustees_ab_percent", "wa_vs_trustees_rebate_percent",
        "wa_vs_trustees_total_percent", "trustees_selected_vintages",
        "reconciliation_status"
    ]
    write_csv(OUT / "wa_vs_trustees_ivc3_weighted_reconciliation.csv", rows, fields)
    write_csv(
        OUT / "wa_vs_trustees_ivc3_weighted_reconciliation_errors.csv",
        errors, ["error_type", "year", "detail"]
    )

    lines = [
        "=" * 124,
        "CMS MA PART C — WA-MEMBER-MONTH-WEIGHTED TRUSTEES IV.C3 RECONCILIATION v0.2",
        "=" * 124,
        "",
        "READ-ONLY DIAGNOSTIC RECONCILIATION",
        "",
        f"WA cell rows read                             : {len(cells):,}",
        f"WA annual rows read                           : {len(annual):,}",
        f"Weighted/combined comparison years            : {len(rows):,}",
        f"Source-resolution errors                      : {len(errors):,}",
        "",
        "YEAR RESULTS",
        "-" * 124,
    ]

    for r in rows:
        lines.append(
            f"CY{r['calendar_year']} [{r['wa_period_status']}]: "
            f"HMO wt={float(r['hmo_weight']):.4%}; PPO wt={float(r['local_ppo_weight']):.4%}; "
            f"WA total={float(r['wa_total_annual_per_enrollee']):,.2f}; "
            f"Trustees comparator={float(r['trustees_total_weighted_annual_per_enrollee']):,.2f}; "
            f"diff={float(r['wa_vs_trustees_total_percent']):+.2f}% | "
            f"A/B={float(r['wa_vs_trustees_ab_percent']):+.2f}% | "
            f"Rebate={float(r['wa_vs_trustees_rebate_percent']):+.2f}%"
        )

    lines += ["", "VALIDATION CHECKS", "-" * 124]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)
    lines += [
        "",
        f"OVERALL WEIGHTED RECONCILIATION PROFILER STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "PASS establishes that actual WA plan-type member-month weights were derived",
        "from the validated reconstruction cells and applied to certified Trustees",
        "IV.C3 HMO/PPO controls without invented weights.",
        "",
        "The percentage differences remain reconciliation evidence, not pass/fail",
        "thresholds. Washington and national Trustees populations need not be equal.",
        "",
        "CY2015 retains the certified combined Local CCP comparator.",
        "CY2024 remains partial until Oct-Dec 2024 are acquired and reconstructed.",
        "This script does not authorize database or final-ledger inclusion.",
        "",
        f"Output directory: {OUT}",
    ]
    summary = "\n".join(lines) + "\n"
    (OUT / "wa_vs_trustees_ivc3_weighted_reconciliation_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
