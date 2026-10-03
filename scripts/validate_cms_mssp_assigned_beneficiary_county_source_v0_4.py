#!/usr/bin/env python3
"""
CMS MSSP Assigned Beneficiary County Source Certification v0.4

Documentation-governed, suppression-aware structural certification for the
CMS "Number of Accountable Care Organization Assigned Beneficiaries by County"
PUF, 2020-2024.

Certified publication semantics
-------------------------------
For the four enrollment-type person-year fields:
  numeric  = published person-year value
  "*"      = CMS suppressed; underlying value remains unresolved
  "."      = CMS Missing: county has no assigned beneficiaries with this
             enrollment type

For Tot_AB_Psn_Yrs and Tot_AB:
  numeric  = published value
  "*"      = CMS suppressed

The raw "." representation is preserved as a distinct provenance state. It is
not silently rewritten in source data.

Boundary
--------
This validator certifies source structure, publication semantics, and exact
ACO_ID linkage to the MSSP financial PUF for 2020-2024.

It does NOT:
  * reconstruct or impute suppressed cells;
  * require enrollment-type components to sum to Tot_AB_Psn_Yrs;
  * allocate EarnSaveLoss;
  * establish beneficiary geography as payment-dollar incidence;
  * establish Washington/county dollar incidence;
  * establish cash or federal fiscal-year timing;
  * write to a database or principal ledger.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COUNTY_ZIP = ROOT / (
    "data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county/"
    "Number of Accountable Care Organization Assigned Beneficiaries by County.zip"
)
FINANCIAL_ZIP = ROOT / (
    "data/raw/cms/medicare_aco/mssp_performance_results/"
    "Performance Year Financial and Quality Results.zip"
)
OUTDIR = ROOT / (
    "data/raw/cms/medicare_aco/mssp_assigned_beneficiaries_by_county/"
    "validation/source_v0_4"
)

EXPECTED_COUNTY_SHA256 = (
    "2BDD88C3B00B3035914426286BE38E518FA6E552D54285B19289EB964878F942"
)
EXPECTED_COUNTY_BYTES = 8_450_964
EXPECTED_ARCHIVE_ENTRIES = 21

ACQUIRED_PERIODS = ("2020", "2021", "2022", "2023", "2024")
EXPECTED_PERIODS = (
    "2015", "2016", "2017", "2018", "2019", "2019A",
    "2020", "2021", "2022", "2023", "2024",
)

EXPECTED_SCHEMA = (
    "Year",
    "ACO_ID",
    "State_Name",
    "County_Name",
    "State_ID",
    "County_ID",
    "AB_Psn_Yrs_ESRD",
    "AB_Psn_Yrs_DIS",
    "AB_Psn_Yrs_AGDU",
    "AB_Psn_Yrs_AGND",
    "Tot_AB_Psn_Yrs",
    "Tot_AB",
)

COMPONENT_FIELDS = (
    "AB_Psn_Yrs_ESRD",
    "AB_Psn_Yrs_DIS",
    "AB_Psn_Yrs_AGDU",
    "AB_Psn_Yrs_AGND",
)
TOTAL_FIELDS = ("Tot_AB_Psn_Yrs", "Tot_AB")
MEASURE_FIELDS = COMPONENT_FIELDS + TOTAL_FIELDS

EXPECTED_FINANCIAL_ACO_COUNTS = {
    "2020": 513,
    "2021": 475,
    "2022": 482,
    "2023": 453,
    "2024": 476,
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def decode_csv(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise RuntimeError("CSV could not be decoded with approved encodings")


def county_period(name: str) -> str | None:
    m = re.search(r"/(20(?:20|21|22|23|24))/", name)
    return m.group(1) if m else None


def financial_period(name: str) -> str | None:
    if not name.lower().endswith(".csv"):
        return None
    low = name.lower()
    for period in ACQUIRED_PERIODS:
        if period in low:
            return period
    return None


def normalize_aco_id(value: str | None) -> str:
    return (value or "").strip().upper()


def classify_component(value: str | None) -> str:
    s = (value or "").strip()
    if s == "":
        return "BLANK"
    if s == "*":
        return "SUPPRESSED_STAR"
    if s == ".":
        return "CMS_MISSING_ZERO_DOT"
    try:
        Decimal(s.replace(",", ""))
        return "NUMERIC"
    except InvalidOperation:
        return "OTHER_NONNUMERIC"


def classify_total(value: str | None) -> str:
    s = (value or "").strip()
    if s == "":
        return "BLANK"
    if s == "*":
        return "SUPPRESSED_STAR"
    if s == ".":
        return "UNEXPECTED_DOT"
    try:
        Decimal(s.replace(",", ""))
        return "NUMERIC"
    except InvalidOperation:
        return "OTHER_NONNUMERIC"


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []

    def check(cid: str, passed: bool, detail: str) -> None:
        checks.append({
            "check_id": cid,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
        })

    print("CMS MSSP ASSIGNED BENEFICIARY COUNTY SOURCE CERTIFICATION v0.4")
    print("=" * 76)

    if not COUNTY_ZIP.exists():
        print(f"ERROR: county archive not found: {COUNTY_ZIP}")
        return 2
    if not FINANCIAL_ZIP.exists():
        print(f"ERROR: financial archive not found: {FINANCIAL_ZIP}")
        return 2

    source_sha = sha256_file(COUNTY_ZIP)
    source_bytes = COUNTY_ZIP.stat().st_size

    print(f"County source: {COUNTY_ZIP}")
    print(f"SHA-256: {source_sha}")
    print(f"Bytes: {source_bytes:,}")

    check(
        "SOURCE-01",
        source_sha == EXPECTED_COUNTY_SHA256,
        f"county archive SHA-256={source_sha}",
    )
    check(
        "SOURCE-02",
        source_bytes == EXPECTED_COUNTY_BYTES,
        f"county archive bytes={source_bytes:,} expected={EXPECTED_COUNTY_BYTES:,}",
    )

    period_profiles: list[dict] = []
    measure_profiles: list[dict] = []
    county_aco_sets: dict[str, set[str]] = {}

    with zipfile.ZipFile(COUNTY_ZIP) as z:
        names = z.namelist()

        check(
            "ARCHIVE-01",
            len(names) == EXPECTED_ARCHIVE_ENTRIES,
            f"archive entries={len(names)} expected={EXPECTED_ARCHIVE_ENTRIES}",
        )

        csv_members: dict[str, list[str]] = defaultdict(list)
        pdf_members: dict[str, list[str]] = defaultdict(list)
        year_dirs: set[str] = set()

        for name in names:
            period = county_period(name)
            if period is None:
                continue
            year_dirs.add(period)
            if name.lower().endswith(".csv"):
                csv_members[period].append(name)
            elif name.lower().endswith(".pdf"):
                pdf_members[period].append(name)

        check(
            "ARCHIVE-02",
            year_dirs == set(ACQUIRED_PERIODS),
            "year directories=" + ",".join(sorted(year_dirs)),
        )
        check(
            "ARCHIVE-03",
            all(len(csv_members[p]) == 1 for p in ACQUIRED_PERIODS),
            "CSV members="
            + ",".join(f"{p}:{len(csv_members[p])}" for p in ACQUIRED_PERIODS),
        )
        check(
            "ARCHIVE-04",
            all(len(pdf_members[p]) == 2 for p in ACQUIRED_PERIODS),
            "PDF members="
            + ",".join(f"{p}:{len(pdf_members[p])}" for p in ACQUIRED_PERIODS),
        )

        for period in ACQUIRED_PERIODS:
            if len(csv_members[period]) != 1:
                continue

            member = csv_members[period][0]
            text, encoding = decode_csv(z.read(member))
            reader = csv.DictReader(io.StringIO(text))
            schema = tuple(reader.fieldnames or [])

            rows = 0
            year_mismatch = 0
            blank_aco = 0
            aco_ids: set[str] = set()
            state_ids: set[str] = set()
            county_ids: set[str] = set()

            component_counts = {
                field: {
                    "NUMERIC": 0,
                    "SUPPRESSED_STAR": 0,
                    "CMS_MISSING_ZERO_DOT": 0,
                    "BLANK": 0,
                    "OTHER_NONNUMERIC": 0,
                }
                for field in COMPONENT_FIELDS
            }
            total_counts = {
                field: {
                    "NUMERIC": 0,
                    "SUPPRESSED_STAR": 0,
                    "UNEXPECTED_DOT": 0,
                    "BLANK": 0,
                    "OTHER_NONNUMERIC": 0,
                }
                for field in TOTAL_FIELDS
            }

            for row in reader:
                rows += 1

                if (row.get("Year") or "").strip() != period:
                    year_mismatch += 1

                aco = normalize_aco_id(row.get("ACO_ID"))
                if aco:
                    aco_ids.add(aco)
                else:
                    blank_aco += 1

                state = (row.get("State_ID") or "").strip()
                county = (row.get("County_ID") or "").strip()
                if state:
                    state_ids.add(state)
                if county:
                    county_ids.add(county)

                for field in COMPONENT_FIELDS:
                    component_counts[field][classify_component(row.get(field))] += 1

                for field in TOTAL_FIELDS:
                    total_counts[field][classify_total(row.get(field))] += 1

            county_aco_sets[period] = aco_ids

            period_profiles.append({
                "period": period,
                "csv_member": member,
                "encoding": encoding,
                "rows": rows,
                "columns": len(schema),
                "schema_exact": schema == EXPECTED_SCHEMA,
                "year_mismatch_rows": year_mismatch,
                "blank_aco_id_rows": blank_aco,
                "distinct_aco_ids": len(aco_ids),
                "distinct_state_ids": len(state_ids),
                "distinct_county_ids": len(county_ids),
                "schema": "|".join(schema),
            })

            for field in COMPONENT_FIELDS:
                c = component_counts[field]
                measure_profiles.append({
                    "period": period,
                    "field": field,
                    "field_class": "ENROLLMENT_COMPONENT",
                    "rows": rows,
                    "numeric": c["NUMERIC"],
                    "suppressed_star": c["SUPPRESSED_STAR"],
                    "cms_missing_zero_dot": c["CMS_MISSING_ZERO_DOT"],
                    "unexpected_dot": 0,
                    "blank": c["BLANK"],
                    "other_nonnumeric": c["OTHER_NONNUMERIC"],
                    "accounted": sum(c.values()),
                    "documented_states": (
                        c["NUMERIC"]
                        + c["SUPPRESSED_STAR"]
                        + c["CMS_MISSING_ZERO_DOT"]
                    ),
                })

            for field in TOTAL_FIELDS:
                c = total_counts[field]
                measure_profiles.append({
                    "period": period,
                    "field": field,
                    "field_class": "TOTAL_MEASURE",
                    "rows": rows,
                    "numeric": c["NUMERIC"],
                    "suppressed_star": c["SUPPRESSED_STAR"],
                    "cms_missing_zero_dot": 0,
                    "unexpected_dot": c["UNEXPECTED_DOT"],
                    "blank": c["BLANK"],
                    "other_nonnumeric": c["OTHER_NONNUMERIC"],
                    "accounted": sum(c.values()),
                    "documented_states": c["NUMERIC"] + c["SUPPRESSED_STAR"],
                })

            py = total_counts["Tot_AB_Psn_Yrs"]
            ab = total_counts["Tot_AB"]
            print(
                f"{period}: rows={rows:,} ACOs={len(aco_ids):,} "
                f"Tot_AB_Psn_Yrs numeric={py['NUMERIC']:,} "
                f"suppressed={py['SUPPRESSED_STAR']:,} "
                f"unexpected-dot={py['UNEXPECTED_DOT']:,} "
                f"blank={py['BLANK']:,} other={py['OTHER_NONNUMERIC']:,}; "
                f"Tot_AB numeric={ab['NUMERIC']:,} "
                f"suppressed={ab['SUPPRESSED_STAR']:,} "
                f"unexpected-dot={ab['UNEXPECTED_DOT']:,} "
                f"blank={ab['BLANK']:,} other={ab['OTHER_NONNUMERIC']:,}"
            )

            for field in COMPONENT_FIELDS:
                c = component_counts[field]
                print(
                    f"  {field}: numeric={c['NUMERIC']:,} "
                    f"suppressed={c['SUPPRESSED_STAR']:,} "
                    f"cms-zero-dot={c['CMS_MISSING_ZERO_DOT']:,} "
                    f"blank={c['BLANK']:,} other={c['OTHER_NONNUMERIC']:,}"
                )

    check(
        "SCHEMA-01",
        len(period_profiles) == 5
        and all(p["schema_exact"] for p in period_profiles),
        "exact 12-column CMS schema reproduced for all acquired periods",
    )
    check(
        "SCHEMA-02",
        len(period_profiles) == 5
        and all(p["year_mismatch_rows"] == 0 for p in period_profiles),
        "Year field agrees with archive period on every row",
    )
    check(
        "KEY-01",
        len(period_profiles) == 5
        and all(p["blank_aco_id_rows"] == 0 for p in period_profiles),
        "ACO_ID present on every acquired row",
    )

    check(
        "MEASURE-01",
        all(r["accounted"] == r["rows"] for r in measure_profiles),
        "every beneficiary-measure cell classified exactly once",
    )

    component_rows = [
        r for r in measure_profiles
        if r["field_class"] == "ENROLLMENT_COMPONENT"
    ]
    total_rows = [
        r for r in measure_profiles
        if r["field_class"] == "TOTAL_MEASURE"
    ]

    check(
        "SEMANTICS-01",
        len(component_rows) == 20
        and all(
            r["blank"] == 0
            and r["other_nonnumeric"] == 0
            and r["documented_states"] == r["rows"]
            for r in component_rows
        ),
        "component fields contain only documented numeric, '*', or '.' states",
    )
    check(
        "SEMANTICS-02",
        len(component_rows) == 20
        and all(
            r["numeric"]
            + r["suppressed_star"]
            + r["cms_missing_zero_dot"]
            == r["rows"]
            for r in component_rows
        ),
        "numeric + '*' + CMS zero-beneficiary '.' exactly equals source rows "
        "for every component/year",
    )
    check(
        "SEMANTICS-03",
        len(total_rows) == 10
        and all(
            r["unexpected_dot"] == 0
            and r["blank"] == 0
            and r["other_nonnumeric"] == 0
            and r["documented_states"] == r["rows"]
            for r in total_rows
        ),
        "Tot_AB_Psn_Yrs and Tot_AB contain only documented numeric or '*' states",
    )
    check(
        "SEMANTICS-04",
        len(total_rows) == 10
        and all(
            r["numeric"] + r["suppressed_star"] == r["rows"]
            for r in total_rows
        ),
        "numeric + '*' exactly equals source rows for both total measures",
    )

    # Financial-PUF linkage.
    financial_aco_sets: dict[str, set[str]] = {
        p: set() for p in ACQUIRED_PERIODS
    }
    financial_members: defaultdict[str, int] = defaultdict(int)

    with zipfile.ZipFile(FINANCIAL_ZIP) as z:
        for name in z.namelist():
            period = financial_period(name)
            if period is None:
                continue

            text, _ = decode_csv(z.read(name))
            reader = csv.DictReader(io.StringIO(text))
            if "ACO_ID" not in (reader.fieldnames or []):
                continue

            financial_members[period] += 1
            for row in reader:
                aco = normalize_aco_id(row.get("ACO_ID"))
                if aco:
                    financial_aco_sets[period].add(aco)

    linkage_rows: list[dict] = []

    for period in ACQUIRED_PERIODS:
        county_ids = county_aco_sets.get(period, set())
        financial_ids = financial_aco_sets[period]
        county_only = sorted(county_ids - financial_ids)
        financial_only = sorted(financial_ids - county_ids)

        linkage_rows.append({
            "period": period,
            "county_aco_ids": len(county_ids),
            "financial_aco_ids": len(financial_ids),
            "expected_financial_aco_ids": EXPECTED_FINANCIAL_ACO_COUNTS[period],
            "county_only_count": len(county_only),
            "financial_only_count": len(financial_only),
            "county_only_ids": "|".join(county_only),
            "financial_only_ids": "|".join(financial_only),
            "exact_set_equality": county_ids == financial_ids,
            "financial_csv_members_with_aco_id": financial_members[period],
        })

        print(
            f"{period} ACO linkage: county={len(county_ids):,} "
            f"financial={len(financial_ids):,} "
            f"county-only={len(county_only):,} "
            f"financial-only={len(financial_only):,}"
        )

    check(
        "LINK-01",
        all(financial_members[p] == 1 for p in ACQUIRED_PERIODS),
        "exactly one governing financial CSV with ACO_ID found per 2020-2024 period",
    )
    check(
        "LINK-02",
        all(
            len(financial_aco_sets[p]) == EXPECTED_FINANCIAL_ACO_COUNTS[p]
            for p in ACQUIRED_PERIODS
        ),
        "financial ACO-ID counts reproduce certified 2020-2024 universe",
    )
    check(
        "LINK-03",
        all(
            county_aco_sets.get(p, set()) == financial_aco_sets[p]
            for p in ACQUIRED_PERIODS
        ),
        "county-PUF and financial-PUF ACO_ID sets exactly equal for every period",
    )

    universe_rows = [{
        "period": period,
        "status": (
            "PRESENT_IN_ACQUIRED_ARCHIVE"
            if period in ACQUIRED_PERIODS
            else "NOT_PRESENT_IN_ACQUIRED_ARCHIVE"
        ),
    } for period in EXPECTED_PERIODS]

    semantics_rows = [
        {
            "field_scope": "ENROLLMENT_COMPONENTS",
            "raw_value": "<numeric>",
            "certified_semantic_state": "PUBLISHED_NUMERIC_VALUE",
            "accounting_treatment": "OBSERVED",
            "note": "Published CMS person-year value.",
        },
        {
            "field_scope": "ENROLLMENT_COMPONENTS",
            "raw_value": "*",
            "certified_semantic_state": "CMS_SUPPRESSED",
            "accounting_treatment": "UNRESOLVED",
            "note": "Do not zero, bound, reconstruct, or impute.",
        },
        {
            "field_scope": "ENROLLMENT_COMPONENTS",
            "raw_value": ".",
            "certified_semantic_state": "CMS_MISSING_ZERO_BENEFICIARIES",
            "accounting_treatment": "KNOWN_ZERO_BENEFICIARY_STATE",
            "note": (
                "CMS dictionary: county has no assigned beneficiaries with "
                "this enrollment type. Preserve raw '.' in provenance."
            ),
        },
        {
            "field_scope": "TOTAL_MEASURES",
            "raw_value": "<numeric>",
            "certified_semantic_state": "PUBLISHED_NUMERIC_VALUE",
            "accounting_treatment": "OBSERVED",
            "note": "Published CMS total value.",
        },
        {
            "field_scope": "TOTAL_MEASURES",
            "raw_value": "*",
            "certified_semantic_state": "CMS_SUPPRESSED",
            "accounting_treatment": "UNRESOLVED",
            "note": "Do not zero, bound, reconstruct, or impute.",
        },
    ]

    disposition_rows = [
        {
            "dimension": "source_authentication",
            "status": "AUTHENTICATED",
            "note": "Subject to SOURCE-01 and SOURCE-02 PASS.",
        },
        {
            "dimension": "publication_semantics",
            "status": "DOCUMENTATION_GOVERNED",
            "note": "Numeric, '*', and component-field '.' states explicitly separated.",
        },
        {
            "dimension": "aco_universe_2020_2024",
            "status": "EXACTLY_LINKED_TO_FINANCIAL_PUF",
            "note": "Subject to LINK-03 PASS.",
        },
        {
            "dimension": "numeric_county_geography",
            "status": "DIRECTLY_OBSERVED",
            "note": "Published numeric beneficiary measures are observed CMS values.",
        },
        {
            "dimension": "component_dot_state",
            "status": "CMS_MISSING_ZERO_BENEFICIARIES",
            "note": "Known no-beneficiary enrollment-type state; raw '.' preserved.",
        },
        {
            "dimension": "suppressed_county_geography",
            "status": "CMS_SUPPRESSED_UNRESOLVED",
            "note": "'*' is neither zeroed, bounded, reconstructed, nor imputed.",
        },
        {
            "dimension": "beneficiary_geography_as_payment_incidence",
            "status": "NOT_ESTABLISHED",
            "note": "Requires separate incidence-methodology certification.",
        },
        {
            "dimension": "washington_payment_dollar_incidence",
            "status": "UNRESOLVED",
            "note": "No settlement dollars allocated here.",
        },
        {
            "dimension": "county_payment_dollar_incidence",
            "status": "UNRESOLVED",
            "note": "No settlement dollars allocated here.",
        },
        {
            "dimension": "cash_ffy_timing",
            "status": "UNRESOLVED",
            "note": "Performance year is not converted to cash/FFY.",
        },
        {
            "dimension": "principal_ledger",
            "status": "WITHHOLD_UNRESOLVED",
            "note": "No ledger inclusion authorized by this certification.",
        },
    ]

    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_source_universe_v0_4.csv",
        universe_rows,
        ["period", "status"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_period_profiles_v0_4.csv",
        period_profiles,
        list(period_profiles[0].keys()) if period_profiles else ["period"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_measure_accounting_v0_4.csv",
        measure_profiles,
        list(measure_profiles[0].keys()) if measure_profiles else ["period", "field"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_financial_linkage_v0_4.csv",
        linkage_rows,
        list(linkage_rows[0].keys()),
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_semantic_states_v0_4.csv",
        semantics_rows,
        [
            "field_scope",
            "raw_value",
            "certified_semantic_state",
            "accounting_treatment",
            "note",
        ],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_disposition_v0_4.csv",
        disposition_rows,
        ["dimension", "status", "note"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_checks_v0_4.csv",
        checks,
        ["check_id", "status", "detail"],
    )

    overall = all(c["status"] == "PASS" for c in checks)

    report = [
        "CMS MSSP ASSIGNED BENEFICIARY COUNTY SOURCE CERTIFICATION v0.4",
        "=" * 76,
        "",
        "PURPOSE",
        "Documentation-governed, suppression-aware source certification.",
        "",
        "CERTIFIED PUBLICATION SEMANTICS",
        "Enrollment-type person-year fields:",
        "  numeric = published CMS person-year value",
        "  *       = CMS suppressed; underlying value unresolved",
        "  .       = CMS Missing: county has no assigned beneficiaries with this",
        "            enrollment type",
        "",
        "Total measures Tot_AB_Psn_Yrs and Tot_AB:",
        "  numeric = published CMS value",
        "  *       = CMS suppressed; underlying value unresolved",
        "",
        "PROVENANCE RULE",
        "The raw '.' representation remains distinct in source/provenance.",
        "It is not silently rewritten in the preserved CMS source.",
        "",
        "SUPPRESSION RULE",
        "CMS '*' values are not treated as zero, are not assigned an inferred",
        "numeric bound, are not reconstructed, and are not imputed.",
        "",
        "INTENTIONALLY RETIRED TEST",
        "The four enrollment-type person-year fields are not required to sum to",
        "Tot_AB_Psn_Yrs. Suppression prevents that from being a valid universal",
        "source-certification identity.",
        "",
        "PASS DOES NOT ESTABLISH",
        "- beneficiary geography as economic payment-dollar incidence",
        "- Washington payment-dollar incidence",
        "- county payment-dollar incidence",
        "- cash / federal fiscal-year timing",
        "- principal-ledger inclusion",
        "",
        f"County source: {COUNTY_ZIP}",
        f"SHA-256: {source_sha}",
        f"Bytes: {source_bytes:,}",
        "",
        "ACQUISITION BOUNDARY",
        "Present: 2020, 2021, 2022, 2023, 2024",
        "Not present in this acquired archive: 2015, 2016, 2017, 2018, 2019, 2019A",
        "Not-present status does not assert that CMS never published those periods.",
        "",
        "CHECKS",
    ]
    report.extend(
        f"{c['check_id']}: {c['status']} - {c['detail']}"
        for c in checks
    )
    report.extend([
        "",
        "CERTIFIED DISPOSITION IF PASS",
        "The 2020-2024 county PUF is a documentation-governed published",
        "ACO beneficiary-geography universe exactly linked to the corresponding",
        "MSSP financial ACO universe. Numeric geography is directly observed;",
        "component '.' denotes CMS's no-assigned-beneficiary state; '*' remains",
        "CMS_SUPPRESSED_UNRESOLVED.",
        "",
        "No settlement-dollar incidence or allocation rule is certified here.",
        "",
        "OVERALL SOURCE CERTIFICATION v0.4: "
        + ("PASS" if overall else "FAIL"),
    ])

    (
        OUTDIR
        / "cms_mssp_assigned_beneficiary_county_certification_report_v0_4.txt"
    ).write_text("\n".join(report) + "\n", encoding="utf-8")

    print()
    for c in checks:
        print(f"{c['check_id']}: {c['status']} - {c['detail']}")

    print()
    print(
        "OVERALL SOURCE CERTIFICATION v0.4: "
        + ("PASS" if overall else "FAIL")
    )
    print(f"Evidence: {OUTDIR}")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
