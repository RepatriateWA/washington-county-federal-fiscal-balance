#!/usr/bin/env python3
"""
Inventory and structurally certify the CMS MSSP Assigned Beneficiaries by County
source universe v0.2.

Boundary
--------
Read-only with respect to source data and databases. This script:
  * authenticates the acquired CMS county archive;
  * preserves the v0.1 historical acquisition boundary (2020-2024 present;
    2015-2019A not present in this acquired archive);
  * verifies the exact 12-column county-PUF schema;
  * profiles Tot_AB_Psn_Yrs and Tot_AB numeric usability;
  * tests the four-category person-year accounting identity; and
  * tests exact ACO_ID set equality against the already-preserved MSSP
    performance-results PUF for 2020-2024.

PASS does NOT establish Washington payment-dollar incidence, county dollar
incidence, cash/FFY timing, or principal-ledger inclusion. No allocation or
settlement-dollar calculation is performed.
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
    "validation/source_universe_v0_2"
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
PERSON_YEAR_COMPONENTS = (
    "AB_Psn_Yrs_ESRD",
    "AB_Psn_Yrs_DIS",
    "AB_Psn_Yrs_AGDU",
    "AB_Psn_Yrs_AGND",
)

# Certified financial-PUF national row/ACO counts already established upstream.
EXPECTED_FINANCIAL_ACO_COUNTS = {
    "2020": 513,
    "2021": 475,
    "2022": 482,
    "2023": 453,
    "2024": 476,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def decode_csv(raw: bytes) -> tuple[str, str]:
    """Return decoded text and explicit encoding used."""
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            pass
    raise UnicodeDecodeError(
        "unknown", raw, 0, min(1, len(raw)),
        "CSV could not be decoded with approved encodings"
    )


def decimal_value(value: str) -> Decimal | None:
    s = (value or "").strip().replace(",", "")
    if s == "":
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def period_from_county_member(name: str) -> str | None:
    m = re.search(r"/(20(?:20|21|22|23|24))/", name)
    return m.group(1) if m else None


def classify_financial_period(name: str) -> str | None:
    """
    Identify 2020-2024 financial PUF members from filenames/paths.
    This deliberately ignores 2019/2019A and documentation.
    """
    if not name.lower().endswith(".csv"):
        return None
    low = name.lower()
    for year in ACQUIRED_PERIODS:
        if year in low:
            return year
    return None


def normalize_aco_id(value: str) -> str:
    return (value or "").strip().upper()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({
            "check_id": check_id,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
        })

    print("CMS MSSP ASSIGNED BENEFICIARY COUNTY SOURCE UNIVERSE v0.2")
    print("=" * 72)

    if not COUNTY_ZIP.exists():
        print(f"ERROR: county archive not found: {COUNTY_ZIP}")
        return 2
    if not FINANCIAL_ZIP.exists():
        print(f"ERROR: financial-results archive not found: {FINANCIAL_ZIP}")
        return 2

    county_hash = sha256(COUNTY_ZIP)
    county_bytes = COUNTY_ZIP.stat().st_size

    print(f"County source: {COUNTY_ZIP}")
    print(f"SHA-256: {county_hash}")
    print(f"Bytes: {county_bytes:,}")

    check("SOURCE-01", county_hash == EXPECTED_COUNTY_SHA256,
          f"county archive SHA-256={county_hash}")
    check("SOURCE-02", county_bytes == EXPECTED_COUNTY_BYTES,
          f"county archive bytes={county_bytes:,} expected={EXPECTED_COUNTY_BYTES:,}")

    with zipfile.ZipFile(COUNTY_ZIP) as z:
        names = z.namelist()
        check("ARCHIVE-01", len(names) == EXPECTED_ARCHIVE_ENTRIES,
              f"archive entries={len(names)} expected={EXPECTED_ARCHIVE_ENTRIES}")

        csv_members: dict[str, str] = {}
        pdf_members: defaultdict[str, list[str]] = defaultdict(list)
        year_dirs = set()

        for name in names:
            p = period_from_county_member(name)
            if p:
                year_dirs.add(p)
                if name.lower().endswith(".csv"):
                    if p in csv_members:
                        csv_members[p] += "||DUPLICATE||" + name
                    else:
                        csv_members[p] = name
                elif name.lower().endswith(".pdf"):
                    pdf_members[p].append(name)

        check("ARCHIVE-02", year_dirs == set(ACQUIRED_PERIODS),
              f"year directories={','.join(sorted(year_dirs))}")
        check("ARCHIVE-03",
              set(csv_members) == set(ACQUIRED_PERIODS)
              and all("||DUPLICATE||" not in v for v in csv_members.values()),
              f"exactly one CSV for acquired periods={','.join(sorted(csv_members))}")
        check("ARCHIVE-04",
              all(len(pdf_members[p]) == 2 for p in ACQUIRED_PERIODS),
              "PDF counts=" + ",".join(f"{p}:{len(pdf_members[p])}" for p in ACQUIRED_PERIODS))

        profiles: list[dict] = []
        county_id_sets: dict[str, set[str]] = {}

        for period in ACQUIRED_PERIODS:
            member = csv_members.get(period)
            if not member or "||DUPLICATE||" in member:
                continue

            raw = z.read(member)
            text, encoding = decode_csv(raw)
            reader = csv.DictReader(io.StringIO(text))
            schema = tuple(reader.fieldnames or [])

            row_count = 0
            aco_ids: set[str] = set()
            state_ids: set[str] = set()
            county_ids: set[str] = set()

            total_py_numeric = 0
            total_py_blank = 0
            total_py_nonnumeric = 0
            total_ab_numeric = 0
            total_ab_blank = 0
            total_ab_nonnumeric = 0

            identity_testable = 0
            identity_match = 0
            identity_mismatch = 0
            identity_unavailable = 0
            max_identity_abs_diff = Decimal("0")

            year_value_mismatch = 0

            for row in reader:
                row_count += 1
                aco = normalize_aco_id(row.get("ACO_ID", ""))
                if aco:
                    aco_ids.add(aco)
                if (row.get("State_ID") or "").strip():
                    state_ids.add(row["State_ID"].strip())
                if (row.get("County_ID") or "").strip():
                    county_ids.add(row["County_ID"].strip())

                if (row.get("Year") or "").strip() != period:
                    year_value_mismatch += 1

                raw_total_py = (row.get("Tot_AB_Psn_Yrs") or "").strip()
                total_py = decimal_value(raw_total_py)
                if raw_total_py == "":
                    total_py_blank += 1
                elif total_py is None:
                    total_py_nonnumeric += 1
                else:
                    total_py_numeric += 1

                raw_total_ab = (row.get("Tot_AB") or "").strip()
                total_ab = decimal_value(raw_total_ab)
                if raw_total_ab == "":
                    total_ab_blank += 1
                elif total_ab is None:
                    total_ab_nonnumeric += 1
                else:
                    total_ab_numeric += 1

                components = [decimal_value(row.get(c, "")) for c in PERSON_YEAR_COMPONENTS]
                if total_py is not None and all(v is not None for v in components):
                    identity_testable += 1
                    diff = total_py - sum(components, Decimal("0"))
                    abs_diff = abs(diff)
                    if abs_diff > max_identity_abs_diff:
                        max_identity_abs_diff = abs_diff
                    if diff == 0:
                        identity_match += 1
                    else:
                        identity_mismatch += 1
                else:
                    identity_unavailable += 1

            county_id_sets[period] = aco_ids
            profiles.append({
                "period": period,
                "csv_member": member,
                "encoding": encoding,
                "rows": row_count,
                "columns": len(schema),
                "schema_exact": schema == EXPECTED_SCHEMA,
                "distinct_aco_ids": len(aco_ids),
                "distinct_state_ids": len(state_ids),
                "distinct_county_ids": len(county_ids),
                "year_value_mismatch_rows": year_value_mismatch,
                "tot_ab_psn_yrs_numeric": total_py_numeric,
                "tot_ab_psn_yrs_blank": total_py_blank,
                "tot_ab_psn_yrs_nonnumeric": total_py_nonnumeric,
                "tot_ab_numeric": total_ab_numeric,
                "tot_ab_blank": total_ab_blank,
                "tot_ab_nonnumeric": total_ab_nonnumeric,
                "py_identity_testable": identity_testable,
                "py_identity_match": identity_match,
                "py_identity_mismatch": identity_mismatch,
                "py_identity_unavailable": identity_unavailable,
                "py_identity_max_abs_diff": str(max_identity_abs_diff),
                "schema": "|".join(schema),
            })

            print(
                f"{period}: rows={row_count:,} cols={len(schema)} "
                f"ACOs={len(aco_ids):,} states={len(state_ids):,} "
                f"counties={len(county_ids):,} "
                f"Tot_AB_Psn_Yrs numeric={total_py_numeric:,}/{row_count:,} "
                f"Tot_AB numeric={total_ab_numeric:,}/{row_count:,} "
                f"PY identity={identity_match:,}/{identity_testable:,}"
            )

    # Source-universe status is explicit and intentionally does not equate
    # "not present here" with "not published by CMS."
    universe_rows = []
    for period in EXPECTED_PERIODS:
        universe_rows.append({
            "period": period,
            "status": (
                "PRESENT_IN_ACQUIRED_ARCHIVE"
                if period in ACQUIRED_PERIODS
                else "NOT_PRESENT_IN_ACQUIRED_ARCHIVE"
            ),
        })

    check("SCHEMA-01",
          len(profiles) == 5 and all(p["schema_exact"] for p in profiles),
          "exact 12-column CMS schema reproduced for all acquired periods")
    check("SCHEMA-02",
          len(profiles) == 5 and all(p["year_value_mismatch_rows"] == 0 for p in profiles),
          "Year field agrees with archive period for every row")
    check("MEASURE-01",
          len(profiles) == 5 and all(
              p["tot_ab_psn_yrs_numeric"] == p["rows"]
              and p["tot_ab_psn_yrs_blank"] == 0
              and p["tot_ab_psn_yrs_nonnumeric"] == 0
              for p in profiles
          ),
          "Tot_AB_Psn_Yrs numeric on every acquired row")
    check("MEASURE-02",
          len(profiles) == 5 and all(
              p["tot_ab_numeric"] == p["rows"]
              and p["tot_ab_blank"] == 0
              and p["tot_ab_nonnumeric"] == 0
              for p in profiles
          ),
          "Tot_AB numeric on every acquired row")
    check("IDENTITY-01",
          len(profiles) == 5 and all(
              p["py_identity_testable"] == p["rows"]
              and p["py_identity_mismatch"] == 0
              and p["py_identity_unavailable"] == 0
              for p in profiles
          ),
          "Tot_AB_Psn_Yrs equals ESRD+DIS+AGDU+AGND on every acquired row")

    # Exact ACO-ID set comparison to preserved MSSP financial PUF.
    financial_id_sets: dict[str, set[str]] = {p: set() for p in ACQUIRED_PERIODS}
    financial_member_counts: defaultdict[str, int] = defaultdict(int)
    financial_encodings: dict[str, set[str]] = {p: set() for p in ACQUIRED_PERIODS}

    with zipfile.ZipFile(FINANCIAL_ZIP) as z:
        for name in z.namelist():
            period = classify_financial_period(name)
            if period is None:
                continue

            raw = z.read(name)
            text, encoding = decode_csv(raw)
            reader = csv.DictReader(io.StringIO(text))
            fields = reader.fieldnames or []
            if "ACO_ID" not in fields:
                # Avoid accidentally treating a non-performance CSV as the
                # governing financial file.
                continue

            financial_member_counts[period] += 1
            financial_encodings[period].add(encoding)
            for row in reader:
                aco = normalize_aco_id(row.get("ACO_ID", ""))
                if aco:
                    financial_id_sets[period].add(aco)

    linkage_rows = []
    for period in ACQUIRED_PERIODS:
        county_ids = county_id_sets.get(period, set())
        financial_ids = financial_id_sets.get(period, set())
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
            "financial_csv_members_with_aco_id": financial_member_counts[period],
            "financial_encodings": "|".join(sorted(financial_encodings[period])),
            "exact_set_equality": county_ids == financial_ids,
        })
        print(
            f"{period} ACO linkage: county={len(county_ids):,} "
            f"financial={len(financial_ids):,} "
            f"county-only={len(county_only):,} "
            f"financial-only={len(financial_only):,}"
        )

    check("LINK-01",
          all(financial_member_counts[p] == 1 for p in ACQUIRED_PERIODS),
          "exactly one governing financial CSV with ACO_ID found for each 2020-2024 period")
    check("LINK-02",
          all(
              len(financial_id_sets[p]) == EXPECTED_FINANCIAL_ACO_COUNTS[p]
              for p in ACQUIRED_PERIODS
          ),
          "financial ACO-ID counts reproduce previously certified 2020-2024 universe")
    check("LINK-03",
          all(county_id_sets.get(p, set()) == financial_id_sets[p] for p in ACQUIRED_PERIODS),
          "county-PUF and financial-PUF ACO_ID sets are exactly equal for every 2020-2024 period")

    # Evidence outputs.
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_source_universe_v0_2.csv",
        universe_rows,
        ["period", "status"],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_profiles_v0_2.csv",
        profiles,
        list(profiles[0].keys()) if profiles else [
            "period", "csv_member", "encoding", "rows", "columns"
        ],
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_financial_linkage_v0_2.csv",
        linkage_rows,
        list(linkage_rows[0].keys()),
    )
    write_csv(
        OUTDIR / "cms_mssp_assigned_beneficiary_county_checks_v0_2.csv",
        checks,
        ["check_id", "status", "detail"],
    )

    overall = all(c["status"] == "PASS" for c in checks)

    report_lines = [
        "CMS MSSP ASSIGNED BENEFICIARY COUNTY SOURCE UNIVERSE v0.2",
        "=" * 72,
        "",
        "BOUNDARY",
        "Read-only source authentication, schema/measure profiling, person-year",
        "identity testing, and exact ACO-ID linkage to the preserved MSSP financial",
        "PUF for 2020-2024.",
        "",
        "PASS DOES NOT ESTABLISH:",
        "- Washington payment-dollar incidence",
        "- county payment-dollar incidence",
        "- beneficiary-residence weighting as an allocation rule",
        "- cash / federal fiscal-year timing",
        "- principal-ledger inclusion",
        "",
        f"County archive: {COUNTY_ZIP}",
        f"County SHA-256: {county_hash}",
        f"County bytes: {county_bytes:,}",
        f"Financial archive: {FINANCIAL_ZIP}",
        "",
        "ACQUISITION BOUNDARY",
        "Present in acquired county archive: " + ", ".join(ACQUIRED_PERIODS),
        "Not present in acquired county archive: 2015, 2016, 2017, 2018, 2019, 2019A",
        "The latter status does NOT assert that CMS never published those periods.",
        "",
        "CHECKS",
    ]
    report_lines.extend(
        f"{c['check_id']}: {c['status']} - {c['detail']}" for c in checks
    )
    report_lines.extend([
        "",
        "DISPOSITION",
        "Beneficiary-residence geography is structurally linked to the MSSP financial",
        "ACO universe only if LINK-03 passes. This artifact makes no economic-incidence",
        "or allocation decision.",
        "",
        "OVERALL SOURCE-UNIVERSE INVENTORY v0.2: " + ("PASS" if overall else "FAIL"),
    ])

    report_path = OUTDIR / "cms_mssp_assigned_beneficiary_county_certification_report_v0_2.txt"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print()
    for c in checks:
        print(f"{c['check_id']}: {c['status']} - {c['detail']}")
    print()
    print(
        "OVERALL SOURCE-UNIVERSE INVENTORY v0.2: "
        + ("PASS" if overall else "FAIL")
    )
    print(f"Evidence: {OUTDIR}")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
