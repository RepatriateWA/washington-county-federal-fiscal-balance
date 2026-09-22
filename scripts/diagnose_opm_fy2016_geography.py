from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ZIP_PATH = (
    REPO_ROOT
    / "data"
    / "raw"
    / "opm"
    / "fedscope"
    / "employment"
    / "2016-09"
    / "opm_fedscope_employment_201609_raw_data_retrieved_20260903T234148Z.zip"
)


def clean_number(value: str) -> float | None:
    value = (value or "").strip()

    if not value:
        return None

    value = value.replace("$", "").replace(",", "")
    return float(value)


def main():
    with zipfile.ZipFile(ZIP_PATH) as zf:

        names = zf.namelist()

        fact_name = next(
            n for n in names
            if "factdata" in Path(n).name.lower()
        )

        loc_name = next(
            n for n in names
            if Path(n).name.lower() == "dtloc.txt"
        )

        # ----------------------------------------------------------
        # Location lookup
        # ----------------------------------------------------------

        with zf.open(loc_name) as raw:
            text = io.TextIOWrapper(
                raw,
                encoding="cp1252",
                newline="",
            )
            reader = csv.DictReader(text)

            locations = {}

            for row in reader:
                loc = row["LOC"].strip()

                locations[loc] = {
                    "LOCTYP": row["LOCTYP"].strip(),
                    "LOCTYPT": row["LOCTYPT"].strip(),
                    "LOCT": row["LOCT"].strip(),
                }

        # ----------------------------------------------------------
        # Aggregate WORKSTAT=1 by exact LOC
        # ----------------------------------------------------------

        agg = defaultdict(
            lambda: {
                "rows": 0,
                "employment": 0.0,
                "salary_mass": 0.0,
                "missing_salary_rows": 0,
                "missing_salary_employment": 0.0,
            }
        )

        with zf.open(fact_name) as raw:
            text = io.TextIOWrapper(
                raw,
                encoding="cp1252",
                newline="",
            )
            reader = csv.DictReader(text)

            for row in reader:

                if row["WORKSTAT"].strip() != "1":
                    continue

                loc = row["LOC"].strip()

                employment = clean_number(
                    row["EMPLOYMENT"]
                )

                salary = clean_number(
                    row["SALARY"]
                )

                if employment is None:
                    raise RuntimeError(
                        f"Blank EMPLOYMENT: {row}"
                    )

                a = agg[loc]

                a["rows"] += 1
                a["employment"] += employment

                if salary is None:
                    a["missing_salary_rows"] += 1
                    a["missing_salary_employment"] += employment
                else:
                    a["salary_mass"] += (
                        employment * salary
                    )

    # --------------------------------------------------------------
    # Print every location category, sorted by type then LOC
    # --------------------------------------------------------------

    records = []

    for loc, values in agg.items():

        lookup = locations.get(
            loc,
            {
                "LOCTYP": "<UNKNOWN>",
                "LOCTYPT": "<UNKNOWN>",
                "LOCT": "<UNKNOWN>",
            },
        )

        records.append(
            {
                "LOC": loc,
                "LOCTYP": lookup["LOCTYP"],
                "LOCTYPT": lookup["LOCTYPT"],
                "LOCT": lookup["LOCT"],
                **values,
            }
        )

    records.sort(
        key=lambda r: (
            r["LOCTYPT"],
            r["LOC"],
        )
    )

    print()
    print("=" * 120)
    print("FY2016 OPM WORKSTAT=1 — EXACT LOCATION RECONCILIATION")
    print("=" * 120)

    for r in records:
        print(
            f"{r['LOC']:<5} "
            f"{r['LOCTYPT']:<22} "
            f"{r['LOCT']:<45} "
            f"EMP={r['employment']:>10,.0f} "
            f"SALARY_MASS=${r['salary_mass']:>16,.0f} "
            f"MISS={r['missing_salary_employment']:>6,.0f}"
        )

    # --------------------------------------------------------------
    # Aggregate by OPM's own LOCTYPT classification
    # --------------------------------------------------------------

    by_type = defaultdict(
        lambda: {
            "employment": 0.0,
            "salary_mass": 0.0,
            "missing_salary_employment": 0.0,
        }
    )

    for r in records:

        t = r["LOCTYPT"]

        by_type[t]["employment"] += r["employment"]
        by_type[t]["salary_mass"] += r["salary_mass"]
        by_type[t]["missing_salary_employment"] += (
            r["missing_salary_employment"]
        )

    print()
    print("=" * 120)
    print("SUMMARY BY OPM LOCTYPT")
    print("=" * 120)

    total_emp = 0.0
    total_salary = 0.0

    for t in sorted(by_type):

        x = by_type[t]

        total_emp += x["employment"]
        total_salary += x["salary_mass"]

        print(
            f"{t:<30}"
            f"EMP={x['employment']:>12,.0f}  "
            f"SALARY_MASS=${x['salary_mass']:>18,.0f}  "
            f"MISS_EMP={x['missing_salary_employment']:>8,.0f}"
        )

    print()
    print("=" * 120)
    print(f"ALL WORKSTAT=1 EMPLOYMENT: {total_emp:,.0f}")
    print(f"ALL KNOWN SALARY MASS:     ${total_salary:,.0f}")
    print()

    print("TARGETS FROM PRIOR RECONSTRUCTION")
    print("---------------------------------")
    print("Employment denominator:       1,838,738")
    print("Salary-mass denominator: $152,965,712,849")
    print()

    print(
        "Difference from all employment: "
        f"{total_emp - 1_838_738:,.0f}"
    )

    print(
        "Difference from target salary mass: "
        f"${total_salary - 152_965_712_849:,.0f}"
    )


if __name__ == "__main__":
    main()