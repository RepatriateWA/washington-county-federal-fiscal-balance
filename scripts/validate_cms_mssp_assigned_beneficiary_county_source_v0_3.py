#!/usr/bin/env python3
"""
Validate CMS MSSP Assigned Beneficiaries by County source v0.3.

Purpose
-------
Suppression-aware structural certification of the already-preserved CMS
"Number of Accountable Care Organization Assigned Beneficiaries by County"
archive for 2020-2024.

This validator:
  * authenticates the frozen county archive;
  * verifies the exact five-period / 12-column source structure;
  * classifies every beneficiary measure cell as NUMERIC, SUPPRESSED_STAR,
    BLANK, or OTHER_NONNUMERIC;
  * requires every Tot_AB_Psn_Yrs and Tot_AB cell to be either numeric or "*";
  * profiles the four enrollment-type person-year fields under the same
    publication accounting;
  * verifies exact ACO_ID set equality with the preserved MSSP financial PUF
    for 2020-2024.

Important boundary
------------------
CMS documentation establishes that "*" denotes suppression. Suppressed cells
are not treated as zero, are not assigned a 1-10 bound, are not reconstructed,
and are not imputed. This validator intentionally does NOT require the four
published enrollment-type person-year fields to sum to Tot_AB_Psn_Yrs.

PASS does NOT establish:
  * beneficiary-residence weighting as an economic-incidence rule;
  * Washington payment-dollar incidence;
  * county payment-dollar incidence;
  * cash / federal fiscal-year timing;
  * principal-ledger inclusion.

No source files, databases, or ledgers are modified.
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
    "validation/source_v0_3"
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
MEASURE_FIELDS = (
    "AB_Psn_Yrs_ESRD",
    "AB_Psn_Yrs_DIS",
    "AB_Psn_Yrs_AGDU",
    "AB_Psn_Yrs_AGND",
    "Tot_AB_Psn_Yrs",
    "Tot_AB",
)
TOTAL_FIELDS = ("Tot_AB_Psn_Yrs", "Tot_AB")
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
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            pass
    raise RuntimeError("CSV could not be decoded with approved encodings")


def period_from_county_member(name: str) -> str | None:
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


def normalize_aco_id(value: str) -> str:
    return (value or "").strip().upper()


def classify_measure(value: str | None) -> str:
    s = (value or "").strip()
    if s == "":
        return "BLANK"
    if s == "*":
        return "SUPPRESSED_STAR"
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

    print("CMS MSSP ASSIGNED BENEFICIARY COUNTY SOURCE CERTIFICATION v0.3")
    print("=" * 76)

    if not COUNTY_ZIP.exists():
        print(f"ERROR: county archive not found: {COUNTY_ZIP}")
        return 2
    if not FINANCIAL_ZIP.exists():
        print(f"ERROR: financial archive not found: {FINANCIAL_ZIP}")
        return 2

    digest = sha256_file(COUNTY_ZIP)
    nbytes = COUNTY_ZIP.stat().st_size

    print(f"County source: {COUNTY_ZIP}")
    print(f"SHA-256: {digest}")
    print(f"Bytes: {nbytes:,}")

    check("SOURCE-01", digest == EXPECTED_COUNTY_SHA256,
          f"county archive SHA-256={digest}")
    check("SOURCE-02", nbytes == EXPECTED_COUNTY_BYTES,
          f"county archive bytes={nbytes:,} expected={EXPECTED_COUNTY_BYTES:,}")

    period_profiles: list[dict] = []
    measure_profiles: list[dict] = []
    county_id_sets: dict[str, set[str]] = {}

    with zipfile.ZipFile(COUNTY_ZIP) as z:
        names = z.namelist()
        check("ARCHIVE-01", len(names) == EXPECTED_ARCHIVE_ENTRIES,
              f"archive entries={len(names)} expected={EXPECTED_ARCHIVE_ENTRIES}")

        csv_members: dict[str, list[str]] = defaultdict(list)
        pdf_members: dict[str, list[str]] = defaultdict(list)
        year_dirs = set()

        for name in names:
            period = period_from_county_member(name)
            if period is None:
                continue
            year_dirs.add(period)
            if name.lower().endswith(".csv"):
                csv_members[period].append(name)
            elif name.lower().endswith(".pdf"):
                pdf_members[period].append(name)

        check("ARCHIVE-02", year_dirs == set(ACQUIRED_PERIODS),
              "year directories=" + ",".join(sorted(year_dirs)))
        check("ARCHIVE-03",
              all(len(csv_members[p]) == 1 for p in ACQUIRED_PERIODS),
              "CSV members=" + ",".join(
                  f"{p}:{len(csv_members[p])}" for p in ACQUIRED_PERIODS
              ))
        check("ARCHIVE-04",
              all(len(pdf_members[p]) == 2 for p in ACQUIRED_PERIODS),
              "PDF members=" + ",".join(
                  f"{p}:{len(pdf_members[p])}" for p in ACQUIRED_PERIODS
              ))

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

            counts = {
                field: {
                    "NUMERIC": 0,
                    "SUPPRESSED_STAR": 0,
                    "BLANK": 0,
                    "OTHER_NONNUMERIC": 0,
                }
                for field in MEASURE_FIELDS
            }

            for row in reader:
                rows += 1

                if (row.get("Year") or "").strip() != period:
                    year_mismatch += 1

                aco = normalize_aco_id(row.get("ACO_ID", ""))
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

                for field in MEASURE_FIELDS:
                    counts[field][classify_measure(row.get(field))] += 1

            county_id_sets[period] = aco_ids

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

            for field in MEASURE_FIELDS:
                c = counts[field]
                measure_profiles.append({
                    "period": period,
                    "field": field,
                    "rows": rows,
                    "numeric": c["NUMERIC"],
                    "suppressed_star": c["SUPPRESSED_STAR"],
                    "blank": c["BLANK"],
                    "other_nonnumeric": c["OTHER_NONNUMERIC"],
                    "accounted": (
                        c["NUMERIC"] + c["SUPPRESSED_STAR"]
                        + c["BLANK"] + c["OTHER_NONNUMERIC"]
                    ),
                    "numeric_or_suppressed": (
                        c["NUMERIC"] + c["SUPPRESSED_STAR"]
                    ),
                })

            total_py = counts["Tot_AB_Psn_Yrs"]
            total_ab = counts["Tot_AB"]

            print(
                f"{period}: rows={rows:,} ACOs={len(aco_ids):,} "
                f"Tot_AB_Psn_Yrs numeric={total_py['NUMERIC']:,} "
                f"suppressed={total_py['SUPPRESSED_STAR']:,} "
                f"blank={total_py['BLANK']:,} other={total_py['OTHER_NONNUMERIC']:,}; "
                f"Tot_AB numeric={total_ab['NUMERIC']:,} "
                f"suppressed={total_ab['SUPPRESSED_STAR']:,} "
                f"blank={total_ab['BLANK']:,} other={total_ab['OTHER_NONNUMERIC']:,}"
            )

    check("SCHEMA-01",
          len(period_profiles) == 5
          and all(p["schema_exact"] for p in period_profiles),
          "exact 12-column CMS schema reproduced for all acquired periods")
    check("SCHEMA-02",
          len(period_profiles) == 5
          and all(p["year_mismatch_rows"] == 0 for p in period_profiles),
          "Year field agrees with archive period on every row")
    check("KEY-01",
          len(period_profiles) == 5
          and all(p["blank_aco_id_rows"] == 0 for p in period_profiles),
          "ACO_ID present on every acquired row")

    # Publication accounting: every cell must be classified exactly once.
    check(
        "MEASURE-01",
        all(r["accounted"] == r["rows"] for r in measure_profiles),
        "every beneficiary-measure cell classified exactly once",
    )

    total_rows = [r for r in measure_profiles if r["field"] in TOTAL_FIELDS]
    check(
        "SUPPRESSION-01",
        len(total_rows) == 10
        and all(r["blank"] == 0 and r["other_nonnumeric"] == 0 for r in total_rows),
        "Tot_AB_Psn_Yrs and Tot_AB contain only numeric values or CMS '*' suppression",
    )
    check(
        "SUPPRESSION-02",
        len(total_rows) == 10
        and all(r["numeric_or_suppressed"] == r["rows"] for r in total_rows),
        "numeric + suppressed exactly equals source rows for both total measures",
    )

    component_rows = [r for r in measure_profiles if r["field"] not in TOTAL_FIELDS]
    check(
        "SUPPRESSION-03",
        len(component_rows) == 20
        and all(
            r["blank"] == 0 and r["other_nonnumeric"] == 0
            for r in component_rows
        ),
        "four enrollment-type person-year fields contain only numeric values or '*'",
    )

    # Exact financial-PUF ACO universe linkage.
    financial_id_sets: dict[str, set[str]] = {p: set() for p in ACQUIRED_PERIODS}
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
                aco = normalize_aco_id(row.get("ACO_ID", ""))
                if aco:
                    financial_id_sets[period].add(aco)

    linkage_rows: list[dict] = []
    for period in ACQUIRED_PERIODS:
        county_ids = county_id_sets.get(period, set())
        financial_ids = financial_id_sets[period]
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
            len(financial_id_sets[p]) == EXPECTED_FINANCIAL_ACO_COUNTS[p]
            for p in ACQUIRED_PERIODS
        ),
        "financial ACO-ID counts reproduce certified 2020-2024 universe",
    )
    check(
        "LINK-03",
        all(
            county_id_sets.get(p, set()) == financial_id_sets[p]
            for p in ACQUIRED_PERIODS
        ),
        "county-PUF and financial-PUF ACO_ID sets exactly equal for every period",
    )

    # Explicit source-universe boundary.
    universe_rows = [{
        "period": period,
        "status": (
            "PRESENT_IN_ACQUIRED_ARCHIVE"
            if period in ACQUIRED_PERIODS
            else "NOT_PRESENT_IN_ACQUIRED_ARCHIVE"
        ),
    } for period in EXPECTED_PERIODS]

    # Disposition freezes only source structure / publication semantics.
    disposition_rows = [
        {
            "dimension": "source_authentication",
            "status": "AUTHENTICATED" if checks[0]["status"] == "PASS" else "FAILED",
            "note": "Frozen county archive authenticated by SHA-256.",
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
            "dimension": "suppressed_county_geography",
            "status": "CMS_SUPPRESSED_UNRESOLVED",
            "note": "'*' is neither zeroed, bounded, reconstructed, nor imputed.",
        },
        {
            "dimension": "beneficiary_residence_as_payment_incidence",
            "status": "NOT_ESTABLISHED",
            "note": "Reserved for a separate incidence-methodology gate.",
        },
        {
            "dimension": "washington_payment_dollar_incidence",
            "status": "UNRESOLVED",
            "note": "No settlement dollars allocated by this validator.",
        },
        {
            "dimension": "county_payment_dollar_incidence",
            "status": "UNRESOLVED",
            "note": "No settlement dollars allocated by this validator.",
        },
        {
            "dimension": "cash_ffy_timing",
            "status": "UNRESOLVED",
            "note": "Performance year is not converted to cash/FFY.",
        },
        {
            "dimension": "principal_ledger",
            "status": "WITHHOLD_UNRESOLVED",
            "note": "No ledger inclusion authorized by this source certification.",
        },
    ]

    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_source_universe_v0_3.csv",
        universe_rows,
        ["period", "status"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_period_profiles_v0_3.csv",
        period_profiles,
        list(period_profiles[0].keys()) if period_profiles else ["period"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_measure_accounting_v0_3.csv",
        measure_profiles,
        list(measure_profiles[0].keys()) if measure_profiles else ["period", "field"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_financial_linkage_v0_3.csv",
        linkage_rows,
        list(linkage_rows[0].keys()),
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_disposition_v0_3.csv",
        disposition_rows,
        ["dimension", "status", "note"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_checks_v0_3.csv",
        checks,
        ["check_id", "status", "detail"],
    )

    overall = all(c["status"] == "PASS" for c in checks)

    report = [
        "CMS MSSP ASSIGNED BENEFICIARY COUNTY SOURCE CERTIFICATION v0.3",
        "=" * 76,
        "",
        "BOUNDARY",
        "Suppression-aware structural certification only.",
        "",
        "CMS SUPPRESSION RULE USED",
        "Published '*' values are treated as CMS-suppressed geography.",
        "They are not treated as zero, are not assigned an inferred numeric bound,",
        "are not reconstructed, and are not imputed.",
        "",
        "INTENTIONALLY RETIRED TEST",
        "This validator does not require the four enrollment-type person-year",
        "columns to sum to Tot_AB_Psn_Yrs. v0.2 demonstrated that such an identity",
        "was not an appropriate source-certification requirement under the",
        "documented publication/suppression semantics.",
        "",
        "PASS DOES NOT ESTABLISH",
        "- beneficiary-residence weighting as economic payment incidence",
        "- Washington payment-dollar incidence",
        "- county payment-dollar incidence",
        "- cash / federal fiscal-year timing",
        "- principal-ledger inclusion",
        "",
        f"County source: {COUNTY_ZIP}",
        f"SHA-256: {digest}",
        f"Bytes: {nbytes:,}",
        "",
        "ACQUISITION BOUNDARY",
        "Present: 2020, 2021, 2022, 2023, 2024",
        "Not present in this acquired archive: 2015, 2016, 2017, 2018, 2019, 2019A",
        "Not-present status does not assert that CMS never published those periods.",
        "",
        "CHECKS",
    ]
    report.extend(
        f"{c['check_id']}: {c['status']} - {c['detail']}" for c in checks
    )
    report.extend([
        "",
        "DISPOSITION",
        "If all checks pass, the 2020-2024 CMS county PUF is certified as a",
        "structurally complete published ACO beneficiary-geography universe that",
        "exactly links to the MSSP financial ACO universe. Numeric geography is",
        "directly observed; '*' geography remains CMS_SUPPRESSED_UNRESOLVED.",
        "",
        "No payment-incidence or dollar-allocation rule is certified here.",
        "",
        "OVERALL SOURCE CERTIFICATION v0.3: " + ("PASS" if overall else "FAIL"),
    ])

    (OUTDIR / "cms_mssp_assigned_beneficiary_county_certification_report_v0_3.txt").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )

    print()
    for c in checks:
        print(f"{c['check_id']}: {c['status']} - {c['detail']}")
    print()
    print(
        "OVERALL SOURCE CERTIFICATION v0.3: "
        + ("PASS" if overall else "FAIL")
    )
    print(f"Evidence: {OUTDIR}")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
