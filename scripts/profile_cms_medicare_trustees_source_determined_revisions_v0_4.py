#!/usr/bin/env python3
"""
CMS Medicare Trustees source-determined revision profiler v0.4
WCFFBP read-only validation artifact.

v0.4 is a surgical validation-type fix to v0.3.

v0.3 correctly established the natural series key and produced zero duplicate
series-vintage rows, but preserved observation_year from CSV as a string in
the output record. The coverage validator then compared string years to the
integer CY2015-CY2024 set and falsely failed.

v0.4 normalizes observation_year to the already parsed integer y before
constructing the natural key. No revision logic, source-status logic,
preferred-vintage logic, or analytical threshold changes.

v0.3 fixed the natural series key after direct inspection of the validated
raw-control schema. It preserves these source dimensions:
  table_id, observation_year, accounting_scope, plan_type_normalized,
  component_normalized, unit, basis.

trustees_vintage identifies the observation within a series.

No preferred vintage is selected. No status is inferred from report-year
arithmetic. No imputation, reconciliation, database write, or ledger action.
"""

from __future__ import annotations
import csv, math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees" / "validation"
RAW = BASE / "private_health_plans_controls_raw_v0_2" / "cms_medicare_trustees_private_plan_controls_raw.csv"
CERT = BASE / "status_boundary_certification_v0_2" / "trustees_status_boundary_certification.csv"
OUT = BASE / "source_determined_revision_profile_v0_4"
YEARS = set(range(2015, 2025))
TABLES = {"IV.C2", "IV.C3"}

KEY_DIMS = [
    "table_id", "observation_year", "accounting_scope",
    "plan_type_normalized", "component_normalized", "unit", "basis"
]

def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def i(x):
    try: return int(float(str(x).strip()))
    except: return None

def fnum(x):
    s = str(x).strip().replace(",", "").replace("$", "")
    if s in {"", "-", "—", "–", "NA", "N/A"}: return None
    if s.startswith("(") and s.endswith(")"): s = "-" + s[1:-1]
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except: return None

def key(r): return tuple(r[d] for d in KEY_DIMS)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []

    if not RAW.exists() or not CERT.exists():
        print("FAIL: required input missing")
        print(RAW); print(CERT)
        return 1

    raw = read_csv(RAW)
    certrows = read_csv(CERT)

    required_raw = set(KEY_DIMS + [
        "trustees_vintage", "value", "value_status",
        "plan_type_source", "component_source"
    ])
    missing = sorted(required_raw - set(raw[0].keys() if raw else []))
    if missing:
        print("FAIL: raw schema missing required columns:", ", ".join(missing))
        return 1

    cert = {}
    for r in certrows:
        v = i(r.get("trustees_vintage"))
        y = i(r.get("source_determined_through_year"))
        if v is not None:
            cert[v] = {
                "through": y,
                "status": r.get("resolution_status", ""),
                "evidence": r.get("boundary_evidence_type", "")
            }

    obs = []
    source_missing = 0
    for n, r in enumerate(raw, 2):
        v = i(r["trustees_vintage"])
        y = i(r["observation_year"])
        if v is None or y not in YEARS or r["table_id"] not in TABLES:
            continue
        c = cert.get(v)
        if not c:
            errors.append({"row_number": n, "error": f"missing certification for vintage {v}"})
            continue
        if c["status"] != "SOURCE_RESOLVED" or c["through"] is None or y > c["through"]:
            continue
        value = fnum(r["value"])
        if value is None:
            source_missing += 1
            continue
        obs.append({
            **{d: r[d] for d in KEY_DIMS},
            "observation_year": y,
            "trustees_vintage": v,
            "value": value,
            "value_status": r["value_status"],
            "plan_type_source": r["plan_type_source"],
            "component_source": r["component_source"],
            "source_determined_through_year": c["through"],
            "boundary_evidence_type": c["evidence"],
            "source_file": r.get("source_file",""),
            "source_sha256": r.get("source_sha256",""),
            "source_page": r.get("source_page",""),
            "source_row_number": r.get("source_row_number",""),
        })

    groups = defaultdict(list)
    duplicate_keys = 0
    dup_rows = []
    for r in obs:
        groups[key(r)].append(r)

    for k, rows in groups.items():
        seen = defaultdict(list)
        for r in rows: seen[r["trustees_vintage"]].append(r)
        for v, rr in seen.items():
            if len(rr) > 1:
                duplicate_keys += len(rr) - 1
                dup_rows.append({
                    **dict(zip(KEY_DIMS, k)),
                    "trustees_vintage": v,
                    "duplicate_row_count": len(rr),
                    "values": "|".join(str(x["value"]) for x in rr),
                })

    steps, summaries = [], []
    for k, rows in sorted(groups.items(), key=lambda x: tuple(str(z) for z in x[0])):
        rows = sorted(rows, key=lambda r: r["trustees_vintage"])
        # Do not calculate revisions for structurally duplicated keys.
        if len({r["trustees_vintage"] for r in rows}) != len(rows):
            continue
        changed = 0
        maxabs = 0.0
        last_change = ""
        for seq, (a,b) in enumerate(zip(rows, rows[1:]), 1):
            delta = b["value"] - a["value"]
            is_changed = not math.isclose(a["value"], b["value"], rel_tol=0.0, abs_tol=1e-12)
            if is_changed:
                changed += 1; last_change = b["trustees_vintage"]
            maxabs = max(maxabs, abs(delta))
            pct = "" if a["value"] == 0 else delta/a["value"]*100
            steps.append({
                **dict(zip(KEY_DIMS, k)), "step_number": seq,
                "from_vintage": a["trustees_vintage"], "to_vintage": b["trustees_vintage"],
                "from_value": a["value"], "to_value": b["value"],
                "revision_amount": delta, "revision_percent": pct,
                "value_changed": "YES" if is_changed else "NO",
            })
        first, last = rows[0], rows[-1]
        net = last["value"] - first["value"]
        summaries.append({
            **dict(zip(KEY_DIMS, k)),
            "source_determined_vintage_count": len(rows),
            "first_source_determined_vintage": first["trustees_vintage"],
            "latest_source_determined_vintage": last["trustees_vintage"],
            "first_source_determined_value": first["value"],
            "latest_source_determined_value": last["value"],
            "changed_revision_steps": changed,
            "last_change_vintage": last_change,
            "net_revision_amount": net,
            "net_revision_percent": "" if first["value"] == 0 else net/first["value"]*100,
            "max_absolute_step_revision": maxabs,
            "stable_after_first_source_determined": "YES" if changed == 0 else "NO",
            "preferred_vintage": "UNASSIGNED",
            "selection_policy": "UNASSIGNED",
        })

    yt = defaultdict(list)
    for r in summaries: yt[(r["observation_year"], r["table_id"])].append(r)
    yearrows = []
    for (y,t), rr in sorted(yt.items()):
        revised = [x for x in rr if x["stable_after_first_source_determined"]=="NO"]
        multi = [x for x in rr if x["source_determined_vintage_count"]>1]
        yearrows.append({
            "observation_year": y, "table_id": t, "series_count": len(rr),
            "series_with_multiple_source_determined_vintages": len(multi),
            "series_revised_after_first_source_determined": len(revised),
            "revision_rate_percent": 100*len(revised)/len(rr) if rr else 0,
            "latest_source_determined_vintage_observed":
                max(x["latest_source_determined_vintage"] for x in rr),
            "latest_revision_vintage_observed":
                max([x["last_change_vintage"] for x in revised if x["last_change_vintage"]], default=""),
        })

    obs_fields = KEY_DIMS + [
        "trustees_vintage","value","value_status","plan_type_source","component_source",
        "source_determined_through_year","boundary_evidence_type","source_file",
        "source_sha256","source_page","source_row_number"
    ]
    step_fields = KEY_DIMS + [
        "step_number","from_vintage","to_vintage","from_value","to_value",
        "revision_amount","revision_percent","value_changed"
    ]
    sum_fields = KEY_DIMS + [
        "source_determined_vintage_count","first_source_determined_vintage",
        "latest_source_determined_vintage","first_source_determined_value",
        "latest_source_determined_value","changed_revision_steps","last_change_vintage",
        "net_revision_amount","net_revision_percent","max_absolute_step_revision",
        "stable_after_first_source_determined","preferred_vintage","selection_policy"
    ]
    dup_fields = KEY_DIMS + ["trustees_vintage","duplicate_row_count","values"]

    write_csv(OUT/"trustees_source_determined_observations.csv", obs, obs_fields)
    write_csv(OUT/"trustees_source_determined_revision_steps.csv", steps, step_fields)
    write_csv(OUT/"trustees_source_determined_series_summary.csv", summaries, sum_fields)
    write_csv(OUT/"trustees_source_determined_control_year_summary.csv", yearrows, [
        "observation_year","table_id","series_count",
        "series_with_multiple_source_determined_vintages",
        "series_revised_after_first_source_determined","revision_rate_percent",
        "latest_source_determined_vintage_observed","latest_revision_vintage_observed"
    ])
    write_csv(OUT/"trustees_source_determined_duplicate_keys.csv", dup_rows, dup_fields)
    write_csv(OUT/"trustees_source_determined_revision_profile_errors.csv", errors,
              ["row_number","error"])

    tables = {r["table_id"] for r in obs}
    years = {r["observation_year"] for r in obs}
    checks = [
        ("Certified boundary vintages loaded", len(cert)==12),
        ("Numeric source-determined observations recognized", bool(obs)),
        ("Both IV.C2 and IV.C3 represented", tables==TABLES),
        ("CY2015-CY2024 represented", years==YEARS),
        ("No duplicate natural series-vintage keys", duplicate_keys==0),
        ("No profiler errors", len(errors)==0),
    ]
    overall = all(x[1] for x in checks)
    stable = sum(r["stable_after_first_source_determined"]=="YES" for r in summaries)
    revised = len(summaries)-stable

    lines = [
        "="*120,
        "CMS MEDICARE TRUSTEES SOURCE-DETERMINED VINTAGE REVISION PROFILE v0.4",
        "="*120,"",
        "READ-ONLY: measures post-source-determination revisions; selects no preferred vintage.","",
        "Natural series key:",
        "  " + " + ".join(KEY_DIMS),"",
        f"Raw control rows read                         : {len(raw):,}",
        f"Certified vintage boundaries loaded           : {len(cert):,}",
        f"Source-determined numeric observations         : {len(obs):,}",
        f"Source-determined nonnumeric/source-missing    : {source_missing:,}",
        f"Distinct natural series                        : {len(groups):,}",
        f"Series eligible for revision analysis          : {len(summaries):,}",
        f"Adjacent vintage revision steps                : {len(steps):,}",
        f"Series stable after first source-determined    : {stable:,}",
        f"Series revised after first source-determined   : {revised:,}",
        f"Duplicate natural series-vintage rows          : {duplicate_keys:,}",
        f"Errors                                         : {len(errors):,}","",
        "CONTROL-YEAR / TABLE SUMMARY","-"*120
    ]
    for r in yearrows:
        lines.append(
            f"CY{r['observation_year']} {r['table_id']}: "
            f"series={r['series_count']} "
            f"multi-vintage={r['series_with_multiple_source_determined_vintages']} "
            f"revised={r['series_revised_after_first_source_determined']} "
            f"latest-source-determined-vintage={r['latest_source_determined_vintage_observed']} "
            f"latest-revision-vintage={r['latest_revision_vintage_observed'] or 'NONE'}"
        )
    lines += ["","VALIDATION CHECKS","-"*120]
    lines += [f"{'PASS' if ok else 'FAIL'}  {label}" for label,ok in checks]
    lines += [
        "",f"OVERALL PROFILER STATUS: {'PASS' if overall else 'FAIL'}","",
        "INTERPRETATION",
        "PASS means the validated source dimensions uniquely identify series-vintage observations",
        "and post-source-determination revision behavior was measured successfully.",
        "PASS does NOT select a preferred Trustees vintage or authorize WA reconciliation/ledger inclusion.",
        "preferred_vintage = UNASSIGNED",
        "selection_policy = UNASSIGNED",
    ]
    text = "\n".join(lines)+"\n"
    (OUT/"trustees_source_determined_revision_profile_summary.txt").write_text(text,encoding="utf-8")
    print(text)
    return 0 if overall else 1

if __name__ == "__main__":
    raise SystemExit(main())
