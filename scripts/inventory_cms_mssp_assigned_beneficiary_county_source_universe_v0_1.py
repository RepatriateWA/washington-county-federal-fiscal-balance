#!/usr/bin/env python3
"""Inventory CMS MSSP Assigned Beneficiaries by County source universe v0.1.

Read-only with respect to source artifacts and databases. Writes only validation
outputs beneath the acquired archive's validation/source_universe_v0_1 folder.

Boundary: inventory and structural profiling only. Beneficiary-residence
geography does not establish payment-dollar incidence.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "raw" / "cms" / "medicare_aco" / "mssp_assigned_beneficiaries_by_county"
ZIP_PATH = SOURCE_DIR / "Number of Accountable Care Organization Assigned Beneficiaries by County.zip"
OUT_DIR = SOURCE_DIR / "validation" / "source_universe_v0_1"
EXPECTED_SHA256 = "2BDD88C3B00B3035914426286BE38E518FA6E552D54285B19289EB964878F942"
EXPECTED_PERIODS = ["2015", "2016", "2017", "2018", "2019", "2019A", "2020", "2021", "2022", "2023", "2024"]
ACQUIRED_PERIODS = ["2020", "2021", "2022", "2023", "2024"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def decode_csv_bytes(data: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            pass
    raise UnicodeDecodeError("unknown", b"", 0, 1, "No supported lossless decoding")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def find_col(headers: list[str], candidates: list[str]) -> str | None:
    by_norm = {norm(h): h for h in headers}
    for c in candidates:
        if norm(c) in by_norm:
            return by_norm[norm(c)]
    return None


def period_from_member(name: str) -> str | None:
    parts = name.split("/")
    for p in parts:
        if re.fullmatch(r"20\d{2}", p):
            return p
    return None


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []

    def check(cid: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": cid, "status": "PASS" if passed else "FAIL", "detail": detail})

    if not ZIP_PATH.exists():
        print(f"ERROR: source archive not found: {ZIP_PATH}", file=sys.stderr)
        return 2

    actual_hash = sha256(ZIP_PATH)
    check("SOURCE-01", actual_hash == EXPECTED_SHA256, f"archive SHA-256={actual_hash}")

    member_rows: list[dict] = []
    dataset_rows: list[dict] = []
    period_inventory: list[dict] = []

    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        infos = zf.infolist()
        check("ARCHIVE-01", len(infos) == 21, f"archive entries={len(infos)} expected=21")

        file_infos = [i for i in infos if not i.is_dir()]
        dir_infos = [i for i in infos if i.is_dir()]
        years = sorted({period_from_member(i.filename) for i in infos if period_from_member(i.filename)})
        check("ARCHIVE-02", years == ACQUIRED_PERIODS, f"year directories={','.join(years)}")

        for i in infos:
            p = period_from_member(i.filename) or ""
            ext = Path(i.filename).suffix.lower()
            role = "DIRECTORY" if i.is_dir() else ("DATASET" if ext == ".csv" else "DOCUMENTATION" if ext == ".pdf" else "OTHER")
            member_rows.append({
                "period": p,
                "role": role,
                "member_name": i.filename,
                "uncompressed_bytes": i.file_size,
                "compressed_bytes": i.compress_size,
                "crc32": f"{i.CRC:08X}",
            })

        csv_infos = [i for i in file_infos if i.filename.lower().endswith(".csv")]
        pdf_infos = [i for i in file_infos if i.filename.lower().endswith(".pdf")]
        check("ARCHIVE-03", len(csv_infos) == 5, f"CSV datasets={len(csv_infos)} expected=5")
        check("ARCHIVE-04", len(pdf_infos) == 10, f"PDF documentation files={len(pdf_infos)} expected=10")

        csv_by_period = Counter(period_from_member(i.filename) for i in csv_infos)
        pdf_by_period = Counter(period_from_member(i.filename) for i in pdf_infos)
        check("ARCHIVE-05", all(csv_by_period[y] == 1 for y in ACQUIRED_PERIODS), "exactly one CSV for each acquired period")
        check("ARCHIVE-06", all(pdf_by_period[y] == 2 for y in ACQUIRED_PERIODS), "exactly two PDFs for each acquired period")

        all_have_aco = True
        all_have_state = True
        all_have_county = True
        all_have_bene_measure = True
        schemas = []

        for info in sorted(csv_infos, key=lambda x: period_from_member(x.filename) or ""):
            period = period_from_member(info.filename) or ""
            raw = zf.read(info)
            text, encoding = decode_csv_bytes(raw)
            reader = csv.DictReader(io.StringIO(text, newline=""))
            headers = reader.fieldnames or []
            rows = list(reader)
            schemas.append(tuple(headers))

            aco_col = find_col(headers, ["ACO_ID", "ACO ID", "ACO_Num", "ACO Number"])
            state_col = find_col(headers, ["State_ID", "State ID", "State", "State_Code", "State Code", "State_FIPS", "State FIPS"])
            county_col = find_col(headers, ["County_ID", "County ID", "County", "County_Code", "County Code", "County_FIPS", "County FIPS"])
            person_year_col = find_col(headers, ["AB_Person_Years", "Assigned Beneficiary Person Years", "Assigned Beneficiary Person-Years", "Person Years", "Person-Years"])
            bene_count_col = find_col(headers, ["AB_Count", "Assigned Beneficiaries", "Assigned Beneficiary Count", "Beneficiary Count", "N_AB"])

            all_have_aco &= aco_col is not None
            all_have_state &= state_col is not None
            all_have_county &= county_col is not None
            all_have_bene_measure &= (person_year_col is not None or bene_count_col is not None)

            distinct_aco = len({r.get(aco_col, "").strip() for r in rows if aco_col and r.get(aco_col, "").strip()}) if aco_col else 0
            distinct_state = len({r.get(state_col, "").strip() for r in rows if state_col and r.get(state_col, "").strip()}) if state_col else 0
            distinct_county = len({r.get(county_col, "").strip() for r in rows if county_col and r.get(county_col, "").strip()}) if county_col else 0

            dataset_rows.append({
                "period": period,
                "member_name": info.filename,
                "encoding": encoding,
                "row_count": len(rows),
                "column_count": len(headers),
                "aco_id_column": aco_col or "NOT_FOUND",
                "state_column": state_col or "NOT_FOUND",
                "county_column": county_col or "NOT_FOUND",
                "person_year_column": person_year_col or "NOT_FOUND",
                "beneficiary_count_column": bene_count_col or "NOT_FOUND",
                "distinct_aco_ids": distinct_aco,
                "distinct_state_values": distinct_state,
                "distinct_county_values": distinct_county,
                "header": " | ".join(headers),
            })

        check("SCHEMA-01", all_have_aco, "ACO identity field found in every acquired CSV")
        check("SCHEMA-02", all_have_state, "state geography field found in every acquired CSV")
        check("SCHEMA-03", all_have_county, "county geography field found in every acquired CSV")
        check("SCHEMA-04", all_have_bene_measure, "beneficiary count/person-year measure found in every acquired CSV")
        check("SCHEMA-05", len(schemas) == 5, "all five acquired CSV schemas profiled")

        for p in EXPECTED_PERIODS:
            present = p in years
            if present:
                status = "PRESENT_IN_ACQUIRED_ARCHIVE"
            else:
                status = "NOT_PRESENT_IN_ACQUIRED_ARCHIVE"
            period_inventory.append({
                "period": p,
                "archive_status": status,
                "csv_count": csv_by_period[p],
                "pdf_count": pdf_by_period[p],
                "interpretive_note": (
                    "Presence only; no payment-incidence conclusion." if present else
                    "This does not mean CMS did not publish the period; only that it is absent from this acquired archive."
                ),
            })

    write_csv(OUT_DIR / "cms_mssp_assigned_beneficiary_county_archive_members_v0_1.csv", member_rows,
              ["period", "role", "member_name", "uncompressed_bytes", "compressed_bytes", "crc32"])
    write_csv(OUT_DIR / "cms_mssp_assigned_beneficiary_county_dataset_profile_v0_1.csv", dataset_rows,
              ["period", "member_name", "encoding", "row_count", "column_count", "aco_id_column", "state_column", "county_column", "person_year_column", "beneficiary_count_column", "distinct_aco_ids", "distinct_state_values", "distinct_county_values", "header"])
    write_csv(OUT_DIR / "cms_mssp_assigned_beneficiary_county_period_inventory_v0_1.csv", period_inventory,
              ["period", "archive_status", "csv_count", "pdf_count", "interpretive_note"])
    write_csv(OUT_DIR / "cms_mssp_assigned_beneficiary_county_source_universe_checks_v0_1.csv", checks,
              ["check_id", "status", "detail"])

    overall = all(c["status"] == "PASS" for c in checks)
    report = OUT_DIR / "cms_mssp_assigned_beneficiary_county_source_universe_report_v0_1.txt"
    with report.open("w", encoding="utf-8") as f:
        f.write("CMS MSSP ASSIGNED BENEFICIARY COUNTY SOURCE UNIVERSE v0.1\n")
        f.write("=" * 72 + "\n\n")
        f.write("BOUNDARY\n")
        f.write("Inventory and structural profiling only. Beneficiary-residence geography does not establish payment-dollar incidence.\n")
        f.write("No geographic allocation, no settlement-dollar allocation, no DB writes, and no ledger writes are performed.\n\n")
        f.write(f"Source archive: {ZIP_PATH.relative_to(ROOT)}\n")
        f.write(f"SHA-256: {actual_hash}\n")
        f.write(f"Archive bytes: {ZIP_PATH.stat().st_size:,}\n\n")
        f.write("PERIOD STATUS\n")
        for r in period_inventory:
            f.write(f"{r['period']}: {r['archive_status']} (CSV={r['csv_count']}, PDF={r['pdf_count']})\n")
        f.write("\nDATASET PROFILE\n")
        for r in dataset_rows:
            f.write(f"{r['period']}: rows={r['row_count']:,}; cols={r['column_count']}; ACOs={r['distinct_aco_ids']:,}; encoding={r['encoding']}\n")
            f.write(f"  ACO={r['aco_id_column']}; state={r['state_column']}; county={r['county_column']}; person-years={r['person_year_column']}; beneficiary-count={r['beneficiary_count_column']}\n")
        f.write("\nCHECKS\n")
        for c in checks:
            f.write(f"{c['check_id']}: {c['status']} — {c['detail']}\n")
        f.write("\nINTERPRETIVE GUARDRAILS\n")
        f.write("1. NOT_PRESENT_IN_ACQUIRED_ARCHIVE does not mean NOT_PUBLISHED_BY_CMS.\n")
        f.write("2. ACO organizational connection is not payment-dollar incidence.\n")
        f.write("3. Beneficiary residence is not certified as an allocation rule by this profiler.\n")
        f.write("4. Economic additivity and geographic allocatability remain independent gates.\n")
        f.write("5. No missing historical period is imputed or back-cast.\n\n")
        f.write(f"OVERALL SOURCE-UNIVERSE INVENTORY v0.1: {'PASS' if overall else 'FAIL'}\n")

    print("CMS MSSP ASSIGNED BENEFICIARY COUNTY SOURCE UNIVERSE v0.1")
    print("=" * 72)
    print(f"Source: {ZIP_PATH}")
    print(f"SHA-256: {actual_hash}")
    print(f"Archive entries: {len(member_rows)}")
    print("Acquired periods: " + ", ".join(ACQUIRED_PERIODS))
    print("Not present in acquired archive: 2015, 2016, 2017, 2018, 2019, 2019A")
    print()
    for r in dataset_rows:
        print(f"{r['period']}: rows={r['row_count']:,} cols={r['column_count']} ACOs={r['distinct_aco_ids']:,} "
              f"ACO={r['aco_id_column']} state={r['state_column']} county={r['county_column']} "
              f"person-years={r['person_year_column']} beneficiary-count={r['beneficiary_count_column']}")
    print()
    for c in checks:
        print(f"{c['check_id']}: {c['status']} - {c['detail']}")
    print()
    print(f"OVERALL SOURCE-UNIVERSE INVENTORY v0.1: {'PASS' if overall else 'FAIL'}")
    print(f"Evidence: {OUT_DIR}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
