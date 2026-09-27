#!/usr/bin/env python
"""
CMS Original Medicare Geographic Variation source certification v0.2.

Read-only profiler. No database writes, allocation, Trustees scaling,
accounting-additivity decision, or ledger treatment.

v0.2 changes:
- Defines Washington counties by the canonical 39 county FIPS codes.
- Explicitly identifies/excludes CMS 53000 WA-UNKNOWN from county sums.
- Separates exact arithmetic reconciliation from material reconciliation.
- Preserves suppressed service-component observations as missing, never zero.
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "cms" / "medicare_geographic_variation"
CSV_PATH = RAW_DIR / "2014-2024 Original Medicare Geographic Variation Public Use File.csv"
OUT_DIR = RAW_DIR / "validation" / "source_v0_2"

STUDY_YEARS = list(range(2015, 2025))
WA_UNKNOWN = "53000"
WA_COUNTY_FIPS = {
    "53001","53003","53005","53007","53009","53011","53013","53015","53017","53019",
    "53021","53023","53025","53027","53029","53031","53033","53035","53037","53039",
    "53041","53043","53045","53047","53049","53051","53053","53055","53057","53059",
    "53061","53063","53065","53067","53069","53071","53073","53075","53077",
}

CONTROL_FIELDS = [
    "BENES_TOTAL_CNT",
    "BENES_WTH_PTAPTB_CNT",
    "BENES_OM_CNT",
    "BENES_MA_CNT",
    "TOT_MDCR_PYMT_AMT",
    "TOT_MDCR_STDZD_PYMT_AMT",
    "IP_MDCR_PYMT_AMT",
    "OP_MDCR_PYMT_AMT",
    "SNF_MDCR_PYMT_AMT",
    "IRF_MDCR_PYMT_AMT",
    "LTCH_MDCR_PYMT_AMT",
    "HH_MDCR_PYMT_AMT",
    "HOSPC_MDCR_PYMT_AMT",
    "PTB_OTHR_SRVCS_MDCR_PYMT_AMT",
]

# Material reconciliation threshold: <= $1,000 OR <= 1 part per million
# of the state control. Exact reconciliation is reported independently.
ABS_DOLLAR_TOLERANCE = Decimal("1000")
REL_TOLERANCE = Decimal("0.000001")
MISSING_TOKENS = {"", "NA", "*", "."}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def decimal_or_none(value: str):
    value = (value or "").strip()
    if value in MISSING_TOKENS:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def lexical_class(value: str) -> str:
    value = (value or "").strip()
    if value == "":
        return "BLANK"
    if value == "NA":
        return "NA"
    if value == "*":
        return "STAR"
    if value == ".":
        return "DOT"
    try:
        Decimal(value)
        return "NUMERIC"
    except InvalidOperation:
        return "OTHER"


def main() -> int:
    if not CSV_PATH.exists():
        print(f"ERROR: source not found: {CSV_PATH}")
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    source_rows = Counter()
    wa_state = defaultdict(list)
    wa_unknown = defaultdict(list)
    wa_counties = defaultdict(list)
    other_53xxx = defaultdict(list)
    lexical_counts = defaultdict(Counter)
    fieldnames = []

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        required = {
            "YEAR", "BENE_GEO_LVL", "BENE_GEO_DESC", "BENE_GEO_CD",
            "BENE_AGE_LVL", *CONTROL_FIELDS
        }
        missing = sorted(required - set(fieldnames))
        if missing:
            print("ERROR: required fields missing:")
            for name in missing:
                print(f"  {name}")
            return 2

        for row in reader:
            try:
                year = int(row["YEAR"])
            except (TypeError, ValueError):
                continue

            source_rows[year] += 1
            if year not in STUDY_YEARS or row["BENE_AGE_LVL"].strip() != "All":
                continue

            level = row["BENE_GEO_LVL"].strip()
            code = row["BENE_GEO_CD"].strip()

            if level == "State" and code == "53":
                wa_state[year].append(row)
            elif level == "County" and code == WA_UNKNOWN:
                wa_unknown[year].append(row)
            elif level == "County" and code in WA_COUNTY_FIPS:
                wa_counties[year].append(row)
                for field in fieldnames:
                    lexical_counts[(year, field)][lexical_class(row.get(field, ""))] += 1
            elif level == "County" and len(code) == 5 and code.startswith("53"):
                other_53xxx[year].append(row)

    checks = []
    reconciliation = []
    detail = []
    unknown_detail = []

    def add_check(name: str, passed: bool, detail_text: str):
        checks.append((name, "PASS" if passed else "FAIL", detail_text))

    add_check("source_year_min", min(source_rows) == 2014,
              f"observed={min(source_rows)} expected=2014")
    add_check("source_year_max", max(source_rows) == 2024,
              f"observed={max(source_rows)} expected=2024")
    add_check("study_years_present",
              all(year in source_rows for year in STUDY_YEARS),
              "expected=2015-2024")

    for year in STUDY_YEARS:
        states = wa_state[year]
        counties = wa_counties[year]
        unknowns = wa_unknown[year]
        extras = other_53xxx[year]
        county_codes = [r["BENE_GEO_CD"].strip() for r in counties]

        add_check(f"{year}_wa_state_all_unique", len(states) == 1,
                  f"rows={len(states)}")
        add_check(f"{year}_canonical_county_count", len(counties) == 39,
                  f"rows={len(counties)} expected=39")
        add_check(f"{year}_canonical_county_fips_complete",
                  set(county_codes) == WA_COUNTY_FIPS,
                  f"distinct={len(set(county_codes))} expected=39")
        add_check(f"{year}_wa_unknown_unique", len(unknowns) == 1,
                  f"rows={len(unknowns)} expected=1")
        add_check(f"{year}_no_other_53xxx_county_geographies", len(extras) == 0,
                  f"rows={len(extras)} expected=0")

        for row in unknowns:
            unknown_detail.append({
                "year": year,
                "bene_geo_cd": row["BENE_GEO_CD"].strip(),
                "bene_geo_desc": row["BENE_GEO_DESC"].strip(),
                "benes_total_cnt": row["BENES_TOTAL_CNT"],
                "benes_om_cnt": row["BENES_OM_CNT"],
                "benes_ma_cnt": row["BENES_MA_CNT"],
                "tot_mdcr_pymt_amt": row["TOT_MDCR_PYMT_AMT"],
                "tot_mdcr_stdzd_pymt_amt": row["TOT_MDCR_STDZD_PYMT_AMT"],
            })

        if len(states) != 1:
            continue

        state = states[0]
        for field in CONTROL_FIELDS:
            state_value = decimal_or_none(state[field])
            county_values = [decimal_or_none(r[field]) for r in counties]
            numeric = [v for v in county_values if v is not None]
            missing_count = len(county_values) - len(numeric)
            county_sum = sum(numeric, Decimal(0))
            delta = None if state_value is None else county_sum - state_value
            relative_residual = None
            if state_value not in (None, Decimal(0)) and delta is not None:
                relative_residual = abs(delta) / abs(state_value)

            exact = (
                state_value is not None
                and len(counties) == 39
                and missing_count == 0
                and delta == 0
            )

            is_dollar_field = "PYMT" in field
            materially_reconciled = False
            if (
                state_value is not None
                and len(counties) == 39
                and missing_count == 0
                and delta is not None
            ):
                if is_dollar_field:
                    materially_reconciled = (
                        abs(delta) <= ABS_DOLLAR_TOLERANCE
                        or (
                            relative_residual is not None
                            and relative_residual <= REL_TOLERANCE
                        )
                    )
                else:
                    # Beneficiary-count controls are discrete counts; do not
                    # apply a dollar/ppm tolerance. Preserve exactness only.
                    materially_reconciled = exact

            reconciliation.append({
                "year": year,
                "field": field,
                "state_value": "" if state_value is None else str(state_value),
                "county_numeric_count": len(numeric),
                "county_missing_count": missing_count,
                "county_sum": str(county_sum),
                "county_minus_state": "" if delta is None else str(delta),
                "absolute_residual": "" if delta is None else str(abs(delta)),
                "relative_residual": "" if relative_residual is None else str(relative_residual),
                "exact_reconciliation": "PASS" if exact else "FAIL",
                "material_reconciliation": "PASS" if materially_reconciled else "FAIL",
            })

            # Hard certification checks:
            # - Total actual and standardized payment measures must be complete
            #   across all 39 canonical counties and materially reconcile.
            # - Service components are diagnostic: suppression is allowed and
            #   therefore does not fail source certification by itself.
            if field in {"TOT_MDCR_PYMT_AMT", "TOT_MDCR_STDZD_PYMT_AMT"}:
                add_check(
                    f"{year}_{field}_39_counties_numeric",
                    missing_count == 0,
                    f"numeric={len(numeric)} missing={missing_count}"
                )
                add_check(
                    f"{year}_{field}_material_reconciliation",
                    materially_reconciled,
                    f"state={state_value} county_sum={county_sum} delta={delta} "
                    f"relative={relative_residual}"
                )

        for row in sorted(counties, key=lambda r: r["BENE_GEO_CD"]):
            detail.append({
                "year": year,
                "county_fips": row["BENE_GEO_CD"].strip(),
                "county_desc": row["BENE_GEO_DESC"].strip(),
                "benes_total_cnt": row["BENES_TOTAL_CNT"],
                "benes_om_cnt": row["BENES_OM_CNT"],
                "benes_ma_cnt": row["BENES_MA_CNT"],
                "tot_mdcr_pymt_amt": row["TOT_MDCR_PYMT_AMT"],
                "tot_mdcr_stdzd_pymt_amt": row["TOT_MDCR_STDZD_PYMT_AMT"],
            })

    lexical_rows = []
    for (year, field), counts in sorted(lexical_counts.items()):
        lexical_rows.append({
            "year": year,
            "field": field,
            "numeric": counts["NUMERIC"],
            "na": counts["NA"],
            "star": counts["STAR"],
            "dot": counts["DOT"],
            "blank": counts["BLANK"],
            "other": counts["OTHER"],
        })

    with (OUT_DIR / "checks.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["check", "status", "detail"])
        writer.writerows(checks)

    with (OUT_DIR / "reconciliation.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(reconciliation[0].keys()))
        writer.writeheader()
        writer.writerows(reconciliation)

    with (OUT_DIR / "wa_county_all_detail.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(detail[0].keys()))
        writer.writeheader()
        writer.writerows(detail)

    with (OUT_DIR / "wa_unknown_detail.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(unknown_detail[0].keys()))
        writer.writeheader()
        writer.writerows(unknown_detail)

    with (OUT_DIR / "wa_county_lexical_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(lexical_rows[0].keys()))
        writer.writeheader()
        writer.writerows(lexical_rows)

    passed = sum(status == "PASS" for _, status, _ in checks)
    failed = len(checks) - passed
    overall = failed == 0

    report = [
        "=" * 108,
        "CMS ORIGINAL MEDICARE GEOGRAPHIC VARIATION SOURCE CERTIFICATION v0.2",
        "=" * 108,
        "Read-only certification. No DB writes, allocation, Trustees scaling, accounting-additivity decision, or ledger treatment.",
        "",
        f"Source: {CSV_PATH}",
        f"Bytes: {CSV_PATH.stat().st_size:,}",
        f"SHA256: {sha256(CSV_PATH)}",
        f"Columns: {len(fieldnames)}",
        f"Observed years: {min(source_rows)}-{max(source_rows)}",
        "",
        "GEOGRAPHIC RULE",
        "-" * 108,
        "Washington county observations are selected only from the canonical 39 Washington county FIPS codes.",
        "CMS 53000 WA-UNKNOWN is retained as provenance but excluded from canonical county sums.",
        "",
        "WASHINGTON ALL-AGE GEOGRAPHY",
        "-" * 108,
    ]

    for year in STUDY_YEARS:
        report.append(
            f"{year}: state={len(wa_state[year])}; canonical_counties={len(wa_counties[year])}; "
            f"distinct_county_fips={len(set(r['BENE_GEO_CD'].strip() for r in wa_counties[year]))}; "
            f"WA-UNKNOWN={len(wa_unknown[year])}; other_53xxx={len(other_53xxx[year])}"
        )

    report += [
        "",
        "TOTAL PAYMENT RECONCILIATION — 39 CANONICAL COUNTIES TO WASHINGTON STATE CONTROL",
        "-" * 108,
    ]
    for year in STUDY_YEARS:
        report.append(f"\n{year}")
        for row in reconciliation:
            if row["year"] == year and row["field"] in {
                "TOT_MDCR_PYMT_AMT", "TOT_MDCR_STDZD_PYMT_AMT"
            }:
                report.append(
                    f"  {row['field']:<30} exact={row['exact_reconciliation']:<4} "
                    f"material={row['material_reconciliation']:<4} "
                    f"state={row['state_value']:<14} county_sum={row['county_sum']:<14} "
                    f"delta={row['county_minus_state']:<8} missing={row['county_missing_count']}"
                )

    report += [
        "",
        "SERVICE-COMPONENT SUPPRESSION DIAGNOSTIC",
        "-" * 108,
        "Component rows below are diagnostic. Missing/suppressed county observations are not converted to zero.",
    ]
    for year in STUDY_YEARS:
        suppressed = [
            row for row in reconciliation
            if row["year"] == year
            and row["field"] not in {
                "BENES_TOTAL_CNT","BENES_WTH_PTAPTB_CNT","BENES_OM_CNT","BENES_MA_CNT",
                "TOT_MDCR_PYMT_AMT","TOT_MDCR_STDZD_PYMT_AMT"
            }
            and row["county_missing_count"] > 0
        ]
        if suppressed:
            report.append(
                f"{year}: " +
                "; ".join(f"{r['field']} missing={r['county_missing_count']}" for r in suppressed)
            )
        else:
            report.append(f"{year}: no missing component observations in profiled fields")

    report += [
        "",
        "CHECK SUMMARY",
        "-" * 108,
        f"Checks: {len(checks)}",
        f"PASS:   {passed}",
        f"FAIL:   {failed}",
    ]

    if failed:
        report += ["", "FAILED CERTIFICATION CHECKS"]
        report += [f"  {name}: {detail_text}" for name, status, detail_text in checks if status == "FAIL"]

    report += [
        "",
        "INTERPRETIVE BOUNDARY",
        "-" * 108,
        "* v0.1 is preserved as provenance; v0.2 corrects its over-broad 53xxx county-selection rule.",
        "* CMS 53000 WA-UNKNOWN is not treated as a Washington county and is not silently allocated.",
        "* Actual TOT_MDCR_PYMT_AMT remains distinct from standardized TOT_MDCR_STDZD_PYMT_AMT.",
        "* Material reconciliation does not overwrite the published Washington state control or force residuals to zero.",
        "* Service-component suppression is retained explicitly; incomplete component sums are not treated as complete county totals.",
        "* BENES_MA_CNT does not authorize treating Original Medicare payment fields as Medicare Advantage payments.",
        "* No county allocation model, Trustees scaling, accounting-additivity decision, or ledger value is created.",
        "",
        f"OVERALL SOURCE CERTIFICATION v0.2: {'PASS' if overall else 'FAIL'}",
    ]

    text = "\n".join(report) + "\n"
    (OUT_DIR / "report.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"Evidence written to: {OUT_DIR}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
