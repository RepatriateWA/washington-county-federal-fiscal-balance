#!/usr/bin/env python3
"""
WCFFBP — Certify CMS Medicare Trustees preferred vintages v0.1
READ-ONLY certification gate.

Policy being certified
----------------------
For each Trustees natural control series in CY2015-CY2024, select the latest
PUBLISHED observation whose Trustees vintage is independently certified as
source-determined for that observation year.

Natural series key:
  table_id + observation_year + accounting_scope + plan_type_normalized
  + component_normalized + unit + basis

Important:
- The script does NOT hard-code CY2015->2025 or CY2016-CY2024->2026.
- Eligibility comes only from the independently certified vintage boundaries.
- Selection is max(trustees_vintage) among published numeric eligible observations.
- Earlier vintages remain provenance; nothing is imputed.
- Trustees values are not labeled "actual".
- No WA reconciliation, DB writes, or ledger authorization occur here.

Run from repository root:
  python scripts/certify_cms_medicare_trustees_preferred_vintages_v0_1.py
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "raw" / "cms" / "medicare_trustees" / "validation"

OBS = (
    BASE / "source_determined_revision_profile_v0_4"
    / "trustees_source_determined_observations.csv"
)
CERT = (
    BASE / "status_boundary_certification_v0_2"
    / "trustees_status_boundary_certification.csv"
)
OUT = BASE / "preferred_vintage_certification_v0_1"

YEARS = set(range(2015, 2025))
TABLES = {"IV.C2", "IV.C3"}
KEY = [
    "table_id",
    "observation_year",
    "accounting_scope",
    "plan_type_normalized",
    "component_normalized",
    "unit",
    "basis",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def as_int(x: Any) -> int | None:
    try:
        return int(float(str(x).strip()))
    except Exception:
        return None


def as_float(x: Any) -> float | None:
    try:
        return float(str(x).strip().replace(",", "").replace("$", ""))
    except Exception:
        return None


def boundary_through(row: dict[str, str]) -> int | None:
    # Use only the field established by the status-boundary certification.
    return as_int(row.get("source_determined_through_year"))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [p for p in (OBS, CERT) if not p.exists()]
    if missing:
        print("FAIL: required validated input(s) missing:")
        for p in missing:
            print(p)
        return 1

    observations = read_csv(OBS)
    certifications = read_csv(CERT)

    errors: list[dict[str, Any]] = []

    cert_by_vintage: dict[int, dict[str, str]] = {}
    duplicate_cert_vintages: list[int] = []
    for r in certifications:
        v = as_int(r.get("trustees_vintage"))
        if v is None:
            continue
        if v in cert_by_vintage:
            duplicate_cert_vintages.append(v)
        cert_by_vintage[v] = r

    # Re-establish eligibility from certified boundaries rather than trusting
    # a preferred-vintage field (which intentionally does not exist yet).
    eligible_by_key: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    focus_numeric = 0

    for r in observations:
        y = as_int(r.get("observation_year"))
        v = as_int(r.get("trustees_vintage"))
        table = r.get("table_id", "")
        value = as_float(r.get("value"))

        if y not in YEARS or table not in TABLES:
            continue
        if value is None:
            continue
        focus_numeric += 1

        cert = cert_by_vintage.get(v) if v is not None else None
        through = boundary_through(cert) if cert else None
        resolution = cert.get("resolution_status", "") if cert else ""

        eligible = (
            cert is not None
            and resolution == "SOURCE_RESOLVED"
            and through is not None
            and y <= through
        )
        if not eligible:
            # Source-determined v0.4 input should already satisfy this.
            errors.append({
                "error_type": "OBSERVATION_NOT_SUPPORTED_BY_CERTIFIED_BOUNDARY",
                "table_id": table,
                "observation_year": y,
                "trustees_vintage": v,
                "plan_type_normalized": r.get("plan_type_normalized", ""),
                "component_normalized": r.get("component_normalized", ""),
                "detail": f"resolution={resolution}; through={through}",
            })
            continue

        k = tuple(str(r.get(d, "")) for d in KEY)
        eligible_by_key[k].append({
            **r,
            "observation_year": y,
            "trustees_vintage": v,
            "_certified_through": through,
            "_certification_channel": cert.get("certification_channel", ""),
        })

    selected: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []

    for k, rows in sorted(eligible_by_key.items()):
        rows = sorted(rows, key=lambda x: x["trustees_vintage"])
        max_v = max(r["trustees_vintage"] for r in rows)
        winners = [r for r in rows if r["trustees_vintage"] == max_v]

        if len(winners) != 1:
            errors.append({
                "error_type": "NONUNIQUE_LATEST_ELIGIBLE_OBSERVATION",
                "table_id": rows[0].get("table_id", ""),
                "observation_year": rows[0].get("observation_year", ""),
                "trustees_vintage": max_v,
                "plan_type_normalized": rows[0].get("plan_type_normalized", ""),
                "component_normalized": rows[0].get("component_normalized", ""),
                "detail": f"winner_count={len(winners)}",
            })
            continue

        w = winners[0]
        later = [r for r in rows if r["trustees_vintage"] > max_v]
        # Mathematically impossible after max(), retained as an explicit proof check.
        if later:
            errors.append({
                "error_type": "LATER_ELIGIBLE_OBSERVATION_EXISTS",
                "table_id": w.get("table_id", ""),
                "observation_year": w["observation_year"],
                "trustees_vintage": max_v,
                "plan_type_normalized": w.get("plan_type_normalized", ""),
                "component_normalized": w.get("component_normalized", ""),
                "detail": ",".join(str(r["trustees_vintage"]) for r in later),
            })

        prior = [r["trustees_vintage"] for r in rows if r["trustees_vintage"] < max_v]
        selected.append({
            **{d: w.get(d, "") for d in KEY},
            "selected_trustees_vintage": max_v,
            "selected_value": w.get("value", ""),
            "source_determined_through_year": w["_certified_through"],
            "certification_channel": w["_certification_channel"],
            "eligible_vintage_count": len(rows),
            "earliest_eligible_vintage": min(r["trustees_vintage"] for r in rows),
            "latest_eligible_vintage": max_v,
            "prior_eligible_vintages": ";".join(map(str, prior)),
            "selection_reason":
                "LATEST_PUBLISHED_NUMERIC_OBSERVATION_CERTIFIED_SOURCE_DETERMINED",
            "preferred_vintage_status": "CERTIFIED",
            "source_file": w.get("source_file", ""),
            "source_sha256": w.get("source_sha256", ""),
            "source_page": w.get("source_page", ""),
            "source_row_number": w.get("source_row_number", ""),
            "source_row_text": w.get("source_row_text", ""),
        })

        for r in rows:
            audit.append({
                **{d: r.get(d, "") for d in KEY},
                "trustees_vintage": r["trustees_vintage"],
                "value": r.get("value", ""),
                "certified_source_determined": "YES",
                "selected_preferred_vintage":
                    "YES" if r["trustees_vintage"] == max_v else "NO",
                "selected_vintage_for_series": max_v,
                "selection_reason":
                    "LATEST_ELIGIBLE" if r["trustees_vintage"] == max_v
                    else "SUPERSEDED_BY_LATER_ELIGIBLE_PRESERVED_VINTAGE",
            })

    # Structural uniqueness.
    selected_key_counts = Counter(
        tuple(str(r.get(d, "")) for d in KEY) for r in selected
    )
    duplicate_selected = [
        k for k, n in selected_key_counts.items() if n != 1
    ]

    # Summaries make the empirical year->vintage result visible without encoding it.
    year_table: list[dict[str, Any]] = []
    for y in sorted(YEARS):
        for table in sorted(TABLES):
            rr = [
                r for r in selected
                if as_int(r.get("observation_year")) == y
                and r.get("table_id") == table
            ]
            if not rr:
                continue
            vintages = sorted({as_int(r["selected_trustees_vintage"]) for r in rr})
            year_table.append({
                "observation_year": y,
                "table_id": table,
                "selected_series_count": len(rr),
                "selected_vintages": ";".join(map(str, vintages)),
                "single_selected_vintage_for_year_table":
                    "YES" if len(vintages) == 1 else "NO",
            })

    selected_years = {as_int(r.get("observation_year")) for r in selected}
    selected_tables = {r.get("table_id") for r in selected}

    checks = [
        ("Certified boundary vintages loaded", bool(cert_by_vintage)),
        ("No duplicate certification vintage rows", not duplicate_cert_vintages),
        ("Numeric focus observations recognized", focus_numeric > 0),
        ("At least one eligible natural series selected", bool(selected)),
        ("CY2015-CY2024 represented", selected_years == YEARS),
        ("Both IV.C2 and IV.C3 represented", selected_tables == TABLES),
        ("Exactly one selected observation per natural series",
         not duplicate_selected and len(selected) == len(eligible_by_key)),
        ("Every selection equals its series latest eligible vintage",
         all(as_int(r["selected_trustees_vintage"]) ==
             as_int(r["latest_eligible_vintage"]) for r in selected)),
        ("No certification errors", not errors),
    ]
    overall = all(ok for _, ok in checks)

    selected_fields = KEY + [
        "selected_trustees_vintage",
        "selected_value",
        "source_determined_through_year",
        "certification_channel",
        "eligible_vintage_count",
        "earliest_eligible_vintage",
        "latest_eligible_vintage",
        "prior_eligible_vintages",
        "selection_reason",
        "preferred_vintage_status",
        "source_file",
        "source_sha256",
        "source_page",
        "source_row_number",
        "source_row_text",
    ]
    audit_fields = KEY + [
        "trustees_vintage",
        "value",
        "certified_source_determined",
        "selected_preferred_vintage",
        "selected_vintage_for_series",
        "selection_reason",
    ]
    summary_fields = [
        "observation_year",
        "table_id",
        "selected_series_count",
        "selected_vintages",
        "single_selected_vintage_for_year_table",
    ]
    error_fields = [
        "error_type",
        "table_id",
        "observation_year",
        "trustees_vintage",
        "plan_type_normalized",
        "component_normalized",
        "detail",
    ]

    write_csv(
        OUT / "trustees_preferred_vintage_controls.csv",
        selected, selected_fields
    )
    write_csv(
        OUT / "trustees_preferred_vintage_selection_audit.csv",
        audit, audit_fields
    )
    write_csv(
        OUT / "trustees_preferred_vintage_year_table_summary.csv",
        year_table, summary_fields
    )
    write_csv(
        OUT / "trustees_preferred_vintage_certification_errors.csv",
        errors, error_fields
    )

    lines = [
        "=" * 120,
        "CMS MEDICARE TRUSTEES PREFERRED-VINTAGE CERTIFICATION v0.1",
        "=" * 120,
        "",
        "READ-ONLY CERTIFICATION GATE",
        "",
        "Selection policy:",
        "  latest PUBLISHED numeric observation independently certified",
        "  source-determined for the control year, by natural series.",
        "",
        f"Certified vintage boundaries loaded          : {len(cert_by_vintage):,}",
        f"Numeric focus observations examined          : {focus_numeric:,}",
        f"Natural series eligible for selection        : {len(eligible_by_key):,}",
        f"Preferred control observations selected      : {len(selected):,}",
        f"Selection audit rows                         : {len(audit):,}",
        f"Certification errors                         : {len(errors):,}",
        "",
        "EMPIRICAL SELECTED VINTAGES BY CONTROL YEAR / TABLE",
        "-" * 120,
    ]
    for r in year_table:
        lines.append(
            f"CY{r['observation_year']} {r['table_id']}: "
            f"series={r['selected_series_count']} "
            f"selected-vintage(s)={r['selected_vintages']} "
            f"single-vintage={r['single_selected_vintage_for_year_table']}"
        )

    lines += ["", "VALIDATION CHECKS", "-" * 120]
    lines.extend(
        f"{'PASS' if ok else 'FAIL'}  {label}" for label, ok in checks
    )
    lines += [
        "",
        f"OVERALL CERTIFICATION STATUS: {'PASS' if overall else 'FAIL'}",
        "",
        "INTERPRETATION",
        "PASS means the preferred Trustees control observations were selected",
        "deterministically from published, independently source-certified observations.",
        "No year-to-vintage mapping was hard-coded.",
        "PASS closes the Trustees preferred-vintage selection gate.",
        "PASS does NOT perform Washington reconciliation or authorize ledger inclusion.",
        "",
        "NEXT GATE",
        "Washington-vs-Trustees Medicare Part C reconciliation.",
        "",
        f"Output directory: {OUT}",
    ]

    text = "\n".join(lines) + "\n"
    (OUT / "trustees_preferred_vintage_certification_summary.txt").write_text(
        text, encoding="utf-8"
    )
    print(text)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
