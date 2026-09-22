#!/usr/bin/env python3
"""
Profile Medicare Trustees source-determined vintage revisions v0.2
=================================================================

WCFFBP read-only diagnostic.

Purpose
-------
For CY2015-CY2024, combine:
  1) validated Trustees IV.C2 / IV.C3 raw controls, and
  2) certified Trustees source-status boundaries,

then measure how each control observation evolves across vintages in which
that control year is already source-determined.

This script DOES NOT:
- select a preferred vintage;
- infer status from vintage arithmetic;
- call any value "actual";
- impute missing values;
- reconcile Trustees controls to Washington;
- write to the database.

It measures before policy selection.

v0.2 change
-----------
Surgical path correction only: uses the established validated raw-control
artifact filename produced by the v0.2 extractor. No analytical logic,
status logic, revision logic, or validation threshold was changed.

Expected inputs
---------------
data/raw/cms/medicare_trustees/validation/private_health_plans_controls_raw_v0_2/cms_medicare_trustees_private_plan_controls_raw.csv
data/raw/cms/medicare_trustees/validation/status_boundary_certification_v0_2/trustees_status_boundary_certification.csv

Outputs
-------
data/raw/cms/medicare_trustees/validation/source_determined_revision_profile_v0_2/
  trustees_source_determined_observations.csv
  trustees_source_determined_revision_steps.csv
  trustees_source_determined_series_summary.csv
  trustees_source_determined_control_year_summary.csv
  trustees_source_determined_revision_profile_errors.csv
  trustees_source_determined_revision_profile_summary.txt

Run from repository root:
  python scripts/profile_cms_medicare_trustees_source_determined_revisions_v0_2.py
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees" / "validation"
RAW = BASE / "private_health_plans_controls_raw_v0_2" / "cms_medicare_trustees_private_plan_controls_raw.csv"
CERT = (
    BASE / "status_boundary_certification_v0_2"
    / "trustees_status_boundary_certification.csv"
)
OUTDIR = BASE / "source_determined_revision_profile_v0_2"
CONTROL_YEARS = set(range(2015, 2025))
TARGET_TABLES = {"IV.C2", "IV.C3"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def pick(row: dict[str, str], names: list[str]) -> str:
    for name in names:
        if name in row and str(row[name]).strip() != "":
            return str(row[name]).strip()
    return ""


def as_int(s: str) -> int | None:
    try:
        return int(float(str(s).replace(",", "").strip()))
    except Exception:
        return None


def as_float(s: str) -> float | None:
    t = str(s).strip().replace(",", "").replace("$", "")
    if t in {"", "-", "—", "–", "NA", "N/A", "nan", "None"}:
        return None
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1]
    try:
        x = float(t)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def norm_table(s: str) -> str:
    x = str(s).upper().replace("TABLE", "").replace(" ", "").strip()
    x = x.replace("IV.C.2", "IV.C2").replace("IV.C.3", "IV.C3")
    return x


def series_key(row: dict[str, Any]) -> tuple:
    return (
        row["table_id"],
        row["control_year"],
        row["accounting_basis"],
        row["component"],
        row["plan_type"],
        row["unit"],
        row["measure"],
    )


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    errors: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    series_summary: list[dict[str, Any]] = []
    year_summary: list[dict[str, Any]] = []

    if not RAW.exists():
        print(f"FAIL: missing raw controls: {RAW}")
        return 1
    if not CERT.exists():
        print(f"FAIL: missing boundary certification: {CERT}")
        return 1

    raw_rows = read_csv(RAW)
    cert_rows = read_csv(CERT)

    cert: dict[int, dict[str, Any]] = {}
    for r in cert_rows:
        v = as_int(r.get("trustees_vintage", ""))
        through = as_int(r.get("source_determined_through_year", ""))
        if v is None:
            continue
        cert[v] = {
            "resolution_status": r.get("resolution_status", ""),
            "source_determined_through_year": through,
            "boundary_evidence_type": r.get("boundary_evidence_type", ""),
        }

    # Adapt to the validated raw extractor's column vocabulary.
    for idx, r in enumerate(raw_rows, start=2):
        vintage = as_int(pick(r, [
            "trustees_vintage", "report_year", "vintage", "trustees_report_year"
        ]))
        control_year = as_int(pick(r, [
            "calendar_year", "control_year", "year", "observation_year"
        ]))
        table_id = norm_table(pick(r, [
            "table_id", "table", "table_number", "source_table"
        ]))
        value_text = pick(r, [
            "numeric_value", "value", "parsed_value", "observation_value"
        ])
        value = as_float(value_text)

        if vintage is None or control_year is None:
            continue
        if control_year not in CONTROL_YEARS:
            continue
        if table_id not in TARGET_TABLES:
            continue

        c = cert.get(vintage)
        if not c:
            errors.append({
                "row_number": idx,
                "trustees_vintage": vintage,
                "control_year": control_year,
                "error": "No certification row for vintage",
            })
            continue
        if c["resolution_status"] != "SOURCE_RESOLVED":
            continue
        through = c["source_determined_through_year"]
        if through is None or control_year > through:
            continue
        if value is None:
            # Preserve source-missing/non-numeric rows separately from numeric
            # revision analysis; they are not imputed.
            continue

        observations.append({
            "trustees_vintage": vintage,
            "control_year": control_year,
            "table_id": table_id,
            "accounting_basis": pick(r, [
                "accounting_basis", "basis", "expenditure_basis"
            ]),
            "component": pick(r, [
                "component", "payment_component", "category", "row_label",
                "expenditure_component"
            ]),
            "plan_type": pick(r, [
                "plan_type", "plan_category", "column_label", "plan"
            ]),
            "unit": pick(r, ["unit", "units"]),
            "measure": pick(r, [
                "measure", "metric", "value_type", "observation_type"
            ]),
            "value": value,
            "source_determined_through_year": through,
            "boundary_evidence_type": c["boundary_evidence_type"],
            "source_file": pick(r, ["source_file", "report_file"]),
            "source_sheet": pick(r, ["source_sheet", "sheet_name", "sheet"]),
            "source_row": pick(r, ["source_row", "row_number"]),
            "source_column": pick(r, ["source_column", "column_name", "column"]),
        })

    # Guard against schema mismatch producing an empty result.
    if not observations:
        errors.append({
            "row_number": "",
            "trustees_vintage": "",
            "control_year": "",
            "error": (
                "No numeric source-determined IV.C2/IV.C3 observations were "
                "recognized. Inspect raw.csv headers before modifying logic."
            ),
        })

    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in observations:
        groups[series_key(r)].append(r)

    duplicate_vintage_keys = 0
    for key, rows in groups.items():
        rows.sort(key=lambda x: x["trustees_vintage"])
        seen = set()
        for r in rows:
            if r["trustees_vintage"] in seen:
                duplicate_vintage_keys += 1
            seen.add(r["trustees_vintage"])

        first = rows[0]
        last = rows[-1]
        changed_steps = 0
        max_abs_step = 0.0

        for seq, (prev, cur) in enumerate(zip(rows, rows[1:]), start=1):
            delta = cur["value"] - prev["value"]
            pct = None if prev["value"] == 0 else delta / prev["value"] * 100.0
            changed = not math.isclose(cur["value"], prev["value"], rel_tol=0.0, abs_tol=1e-12)
            if changed:
                changed_steps += 1
            max_abs_step = max(max_abs_step, abs(delta))
            steps.append({
                "table_id": key[0],
                "control_year": key[1],
                "accounting_basis": key[2],
                "component": key[3],
                "plan_type": key[4],
                "unit": key[5],
                "measure": key[6],
                "step_number": seq,
                "from_vintage": prev["trustees_vintage"],
                "to_vintage": cur["trustees_vintage"],
                "from_value": prev["value"],
                "to_value": cur["value"],
                "revision_amount": delta,
                "revision_percent": "" if pct is None else pct,
                "value_changed": "YES" if changed else "NO",
            })

        net = last["value"] - first["value"]
        net_pct = None if first["value"] == 0 else net / first["value"] * 100.0
        last_change_vintage = ""
        for prev, cur in zip(rows, rows[1:]):
            if not math.isclose(cur["value"], prev["value"], rel_tol=0.0, abs_tol=1e-12):
                last_change_vintage = cur["trustees_vintage"]

        series_summary.append({
            "table_id": key[0],
            "control_year": key[1],
            "accounting_basis": key[2],
            "component": key[3],
            "plan_type": key[4],
            "unit": key[5],
            "measure": key[6],
            "source_determined_vintage_count": len(rows),
            "first_source_determined_vintage": first["trustees_vintage"],
            "latest_source_determined_vintage": last["trustees_vintage"],
            "first_source_determined_value": first["value"],
            "latest_source_determined_value": last["value"],
            "changed_revision_steps": changed_steps,
            "last_change_vintage": last_change_vintage,
            "net_revision_amount": net,
            "net_revision_percent": "" if net_pct is None else net_pct,
            "max_absolute_step_revision": max_abs_step,
            "stable_after_first_source_determined": "YES" if changed_steps == 0 else "NO",
        })

    # Aggregate descriptive behavior by control year and table only.
    by_year_table: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in series_summary:
        by_year_table[(r["control_year"], r["table_id"])].append(r)

    for (year, table), rows in sorted(by_year_table.items()):
        revised = [r for r in rows if r["stable_after_first_source_determined"] == "NO"]
        multi = [r for r in rows if int(r["source_determined_vintage_count"]) > 1]
        year_summary.append({
            "control_year": year,
            "table_id": table,
            "series_count": len(rows),
            "series_with_multiple_source_determined_vintages": len(multi),
            "series_revised_after_first_source_determined": len(revised),
            "revision_rate_among_all_series_percent":
                100.0 * len(revised) / len(rows) if rows else 0.0,
            "latest_source_determined_vintage_observed":
                max(int(r["latest_source_determined_vintage"]) for r in rows),
            "latest_revision_vintage_observed":
                max(
                    [int(r["last_change_vintage"]) for r in revised
                     if str(r["last_change_vintage"]).strip()],
                    default="",
                ),
        })

    obs_fields = [
        "trustees_vintage", "control_year", "table_id", "accounting_basis",
        "component", "plan_type", "unit", "measure", "value",
        "source_determined_through_year", "boundary_evidence_type",
        "source_file", "source_sheet", "source_row", "source_column",
    ]
    step_fields = [
        "table_id", "control_year", "accounting_basis", "component", "plan_type",
        "unit", "measure", "step_number", "from_vintage", "to_vintage",
        "from_value", "to_value", "revision_amount", "revision_percent",
        "value_changed",
    ]
    summary_fields = [
        "table_id", "control_year", "accounting_basis", "component", "plan_type",
        "unit", "measure", "source_determined_vintage_count",
        "first_source_determined_vintage", "latest_source_determined_vintage",
        "first_source_determined_value", "latest_source_determined_value",
        "changed_revision_steps", "last_change_vintage", "net_revision_amount",
        "net_revision_percent", "max_absolute_step_revision",
        "stable_after_first_source_determined",
    ]
    year_fields = [
        "control_year", "table_id", "series_count",
        "series_with_multiple_source_determined_vintages",
        "series_revised_after_first_source_determined",
        "revision_rate_among_all_series_percent",
        "latest_source_determined_vintage_observed",
        "latest_revision_vintage_observed",
    ]

    write_csv(OUTDIR / "trustees_source_determined_observations.csv", observations, obs_fields)
    write_csv(OUTDIR / "trustees_source_determined_revision_steps.csv", steps, step_fields)
    write_csv(OUTDIR / "trustees_source_determined_series_summary.csv", series_summary, summary_fields)
    write_csv(OUTDIR / "trustees_source_determined_control_year_summary.csv", year_summary, year_fields)
    write_csv(
        OUTDIR / "trustees_source_determined_revision_profile_errors.csv",
        errors,
        ["row_number", "trustees_vintage", "control_year", "error"],
    )

    checks = [
        ("Certified boundary vintages loaded", len(cert) == 12),
        ("Numeric source-determined observations recognized", len(observations) > 0),
        ("Both IV.C2 and IV.C3 represented",
         {r["table_id"] for r in observations} == TARGET_TABLES if observations else False),
        ("CY2015-CY2024 represented",
         {r["control_year"] for r in observations} == CONTROL_YEARS if observations else False),
        ("No duplicate series-vintage keys", duplicate_vintage_keys == 0),
        ("No profiler errors", len(errors) == 0),
    ]
    overall = all(ok for _, ok in checks)

    revised_series = sum(
        r["stable_after_first_source_determined"] == "NO" for r in series_summary
    )
    stable_series = sum(
        r["stable_after_first_source_determined"] == "YES" for r in series_summary
    )

    lines = [
        "=" * 120,
        "CMS MEDICARE TRUSTEES SOURCE-DETERMINED VINTAGE REVISION PROFILE v0.2",
        "=" * 120,
        "",
        "READ-ONLY: measures post-source-determination revisions; selects no preferred vintage.",
        "",
        f"Raw control rows read                         : {len(raw_rows):,}",
        f"Certified vintage boundaries loaded           : {len(cert):,}",
        f"Source-determined numeric observations         : {len(observations):,}",
        f"Distinct source-determined series              : {len(series_summary):,}",
        f"Adjacent vintage revision steps                : {len(steps):,}",
        f"Series stable after first source-determined    : {stable_series:,}",
        f"Series revised after first source-determined   : {revised_series:,}",
        f"Duplicate series-vintage keys                  : {duplicate_vintage_keys:,}",
        f"Errors                                         : {len(errors):,}",
        "",
        "CONTROL-YEAR / TABLE SUMMARY",
        "-" * 120,
    ]

    for r in year_summary:
        lines.append(
            f"CY{r['control_year']} {r['table_id']}: "
            f"series={r['series_count']} "
            f"multi-vintage={r['series_with_multiple_source_determined_vintages']} "
            f"revised={r['series_revised_after_first_source_determined']} "
            f"latest-source-determined-vintage={r['latest_source_determined_vintage_observed']} "
            f"latest-revision-vintage={r['latest_revision_vintage_observed'] or 'NONE'}"
        )

    lines += ["", "VALIDATION CHECKS", "-" * 120]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks)
    lines += [
        "",
        f"OVERALL PROFILER STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "PASS means the profiler successfully measured revisions among already source-determined observations.",
        "PASS does NOT select a preferred Trustees vintage or authorize reconciliation/ledger inclusion.",
        "A revision is measured exactly from the validated extracted numeric values; no tolerance is used to hide changes.",
        "",
        "OUTPUTS",
        "-" * 120,
        str(OUTDIR / "trustees_source_determined_observations.csv"),
        str(OUTDIR / "trustees_source_determined_revision_steps.csv"),
        str(OUTDIR / "trustees_source_determined_series_summary.csv"),
        str(OUTDIR / "trustees_source_determined_control_year_summary.csv"),
        str(OUTDIR / "trustees_source_determined_revision_profile_errors.csv"),
    ]

    (OUTDIR / "trustees_source_determined_revision_profile_summary.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print("\n".join(lines))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
