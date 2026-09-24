#!/usr/bin/env python3
"""
CMS Medicare Part D PBP mrx_drug_ben_yn semantic-value profile v0.1

READ-ONLY / PRE-CLASSIFICATION diagnostic.

Purpose
-------
Profile the source-native mrx_drug_ben_yn field across CY2015-CY2024 before
applying it to any disputed Contract+PBP population.

This script:
  * reads the already-preserved annual CMS PBP Benefits ZIPs;
  * reads pbp_mrx.txt as TAB-delimited;
  * requires source-native identifiers:
        pbp_a_hnumber + pbp_a_plan_identifier;
  * inventories mrx_drug_ben_yn values by year;
  * cross-tabulates those values against presence/absence of:
        mrx_benefit_type
        mrx_partd_network_loc
  * separately profiles whether mrx_drug_ben_yn is populated on every
    pbp_mrx.txt record;
  * does NOT decode the field's numeric values;
  * does NOT load the 241 disputed relationships;
  * does NOT classify Part D status;
  * does NOT propagate status or payment;
  * does NOT impute, reconstruct, write to the DB, or authorize ledger use.

The output is evidence for a later semantic decision only.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("data/raw/cms/medicare_partd/pbp_benefits")
OUT = ROOT / "validation" / "mrx_drug_ben_yn_semantic_profile_v0_1"
YEARS = range(2015, 2025)

csv.field_size_limit(min(sys.maxsize, 10_000_000))


def clean(x):
    return "" if x is None else str(x).strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    raise RuntimeError("Unable to decode pbp_mrx.txt")


def one_zip(year: int) -> Path:
    zips = sorted((ROOT / str(year)).glob("*.zip"))
    if len(zips) != 1:
        raise RuntimeError(f"CY{year}: expected exactly one source ZIP; found {len(zips)}")
    return zips[0]


def one_mrx_member(z: zipfile.ZipFile, year: int) -> str:
    names = [n for n in z.namelist() if Path(n).name.lower() == "pbp_mrx.txt"]
    if len(names) != 1:
        raise RuntimeError(f"CY{year}: expected exactly one pbp_mrx.txt; found {len(names)}")
    return names[0]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    value_rows = []
    year_rows = []
    errors = []
    all_values = Counter()
    total_records = 0
    total_populated = 0
    total_blank = 0

    for year in YEARS:
        try:
            zp = one_zip(year)
            with zipfile.ZipFile(zp) as z:
                bad = z.testzip()
                if bad is not None:
                    raise RuntimeError(f"ZIP integrity failure at member {bad}")
                member = one_mrx_member(z, year)
                text = decode(z.read(member))

            reader = csv.DictReader(io.StringIO(text, newline=""), delimiter="\t")
            fields = reader.fieldnames or []
            required = {
                "pbp_a_hnumber",
                "pbp_a_plan_identifier",
                "mrx_drug_ben_yn",
                "mrx_benefit_type",
                "mrx_partd_network_loc",
            }
            missing = sorted(required - set(fields))
            if missing:
                raise RuntimeError(f"missing required fields: {missing}")

            counts = Counter()
            cross = Counter()
            records = 0
            populated = 0
            blank = 0

            for row in reader:
                records += 1
                raw = clean(row.get("mrx_drug_ben_yn"))
                val = raw if raw else "<BLANK>"
                benefit_present = bool(clean(row.get("mrx_benefit_type")))
                network_present = bool(clean(row.get("mrx_partd_network_loc")))
                positive_fields_present = benefit_present or network_present

                counts[val] += 1
                cross[(val, benefit_present, network_present, positive_fields_present)] += 1
                all_values[val] += 1

                if raw:
                    populated += 1
                else:
                    blank += 1

            total_records += records
            total_populated += populated
            total_blank += blank

            year_rows.append({
                "year": year,
                "source_zip": str(zp),
                "source_zip_sha256": sha256_file(zp),
                "pbp_mrx_member": member,
                "records": records,
                "mrx_drug_ben_yn_populated": populated,
                "mrx_drug_ben_yn_blank": blank,
                "distinct_values_including_blank": len(counts),
                "values": "|".join(sorted(counts)),
            })

            for (val, bp, np, pp), n in sorted(cross.items()):
                value_rows.append({
                    "year": year,
                    "mrx_drug_ben_yn_value": val,
                    "record_count": n,
                    "mrx_benefit_type_populated": str(bp).upper(),
                    "mrx_partd_network_loc_populated": str(np).upper(),
                    "either_predeclared_positive_field_populated": str(pp).upper(),
                })

        except Exception as e:
            errors.append(f"CY{year}: {type(e).__name__}: {e}")

    checks = {
        "all_ten_years_profiled": len(year_rows) == 10,
        "no_source_profile_errors": len(errors) == 0,
        "all_profiled_years_have_records": len(year_rows) == 10 and all(r["records"] > 0 for r in year_rows),
        "record_accounting_exact": total_records == total_populated + total_blank,
    }
    overall = all(checks.values())

    write_csv(
        OUT / "cms_partd_mrx_drug_ben_yn_year_summary.csv",
        year_rows,
        [
            "year", "source_zip", "source_zip_sha256", "pbp_mrx_member",
            "records", "mrx_drug_ben_yn_populated", "mrx_drug_ben_yn_blank",
            "distinct_values_including_blank", "values",
        ],
    )
    write_csv(
        OUT / "cms_partd_mrx_drug_ben_yn_value_crosstab.csv",
        value_rows,
        [
            "year", "mrx_drug_ben_yn_value", "record_count",
            "mrx_benefit_type_populated", "mrx_partd_network_loc_populated",
            "either_predeclared_positive_field_populated",
        ],
    )

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "boundary": (
            "Source-value profiling only. Numeric/code values are not decoded. "
            "The disputed 241 relationships are not loaded or classified."
        ),
        "total_records": total_records,
        "total_populated": total_populated,
        "total_blank": total_blank,
        "aggregate_values": dict(sorted(all_values.items())),
        "checks": checks,
        "errors": errors,
        "overall": "PASS" if overall else "FAIL",
    }
    (OUT / "cms_partd_mrx_drug_ben_yn_semantic_profile_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("CMS MEDICARE PART D PBP mrx_drug_ben_yn SEMANTIC-VALUE PROFILE v0.1")
    print("=" * 76)
    print(f"Generated UTC: {report['generated_utc']}")
    print()
    print("BOUNDARY")
    print("-" * 76)
    print("Source-value profiling only. No code decoding and no disputed-plan classification.")
    print("No sibling/other-year propagation, payment propagation, imputation, reconstruction,")
    print("DB writes, or ledger inclusion.")
    print()
    print("YEAR PROFILE")
    print("-" * 76)
    for r in year_rows:
        print(
            f"CY{r['year']}: records={r['records']:,} | "
            f"populated={r['mrx_drug_ben_yn_populated']:,} | "
            f"blank={r['mrx_drug_ben_yn_blank']:,} | values={r['values']}"
        )
    print()
    print("AGGREGATE VALUES")
    print("-" * 76)
    for val, n in sorted(all_values.items()):
        print(f"{val}: {n:,}")
    print()
    print("CHECKS")
    print("-" * 76)
    for name, ok in checks.items():
        print(f"{name.replace('_', ' ')}: {'PASS' if ok else 'FAIL'}")
    print()
    print("ERRORS")
    print("-" * 76)
    if errors:
        for e in errors:
            print(e)
    else:
        print("None")
    print()
    print("OVERALL")
    print("-" * 76)
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    print()
    print(f"Outputs: {OUT}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
