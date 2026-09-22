from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPO_ROOT / "data" / "raw" / "opm" / "fedscope" / "employment"

YEARS = range(2015, 2025)


def clean(value: str | None) -> str:
    return (value or "").strip()


def number(value: str | None) -> float | None:
    s = clean(value).replace(",", "").replace("$", "")
    if not s:
        return None
    return float(s)


def find_zip(year: int) -> Path:
    folder = ROOT / f"{year}-09"
    zips = list(folder.glob("*.zip"))

    if len(zips) != 1:
        raise RuntimeError(
            f"{year}: expected exactly one ZIP in {folder}; found {len(zips)}"
        )

    return zips[0]


def read_text(zf: zipfile.ZipFile, member: str) -> str:
    raw = zf.read(member)

    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass

    raise RuntimeError(f"Could not decode {member}")


def discover_fact(zf: zipfile.ZipFile) -> str:
    candidates = []

    for member in zf.namelist():
        if member.endswith("/"):
            continue

        try:
            text = read_text(zf, member)
        except Exception:
            continue

        first = text.splitlines()[0] if text.splitlines() else ""

        fields = {x.strip().upper() for x in first.split(",")}

        required = {
            "LOC",
            "AGYSUB",
            "WORKSTAT",
            "EMPLOYMENT",
            "SALARY",
            "SALLVL",
        }

        if required.issubset(fields):
            candidates.append(member)

    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one FACT member; found {candidates}"
        )

    return candidates[0]


def discover_lookup(zf: zipfile.ZipFile, field: str) -> list[str]:
    """
    Discover lookup members from their headers rather than filenames.
    """
    matches = []

    for member in zf.namelist():
        if member.endswith("/"):
            continue

        try:
            text = read_text(zf, member)
        except Exception:
            continue

        lines = text.splitlines()
        if not lines:
            continue

        header = {
            x.strip().upper()
            for x in lines[0].split(",")
        }

        if field.upper() in header and member != discover_fact(zf):
            matches.append(member)

    return matches


def read_lookup(zf: zipfile.ZipFile, member: str) -> list[dict[str, str]]:
    text = read_text(zf, member)

    return list(
        csv.DictReader(
            io.StringIO(text)
        )
    )


def main():

    print("=" * 110)
    print("OPM FEDSCOPE SALARY-SUPPRESSION DIAGNOSTIC")
    print("=" * 110)
    print()

    archive_summary = []

    for year in YEARS:

        zip_path = find_zip(year)

        print()
        print("=" * 110)
        print(f"FY{year}")
        print("=" * 110)
        print(f"ZIP: {zip_path}")

        with zipfile.ZipFile(zip_path) as zf:

            fact_member = discover_fact(zf)

            print(f"FACT member: {fact_member}")

            salary_lookups = discover_lookup(zf, "SALLVL")
            agency_lookups = discover_lookup(zf, "AGYSUB")

            print(f"SALLVL lookup candidates: {salary_lookups}")
            print(f"AGYSUB lookup candidates: {agency_lookups}")

            # ------------------------------------------------------
            # Show salary lookup contents.
            # ------------------------------------------------------

            for member in salary_lookups:
                print()
                print(f"--- Salary lookup: {member} ---")

                rows = read_lookup(zf, member)

                for row in rows:
                    print(row)

            # ------------------------------------------------------
            # Aggregate missing SALARY within Rockefeller population.
            # ------------------------------------------------------

            fact_text = read_text(zf, fact_member)
            reader = csv.DictReader(io.StringIO(fact_text))

            total_rows = 0
            total_emp = 0.0

            blank_rows = 0
            blank_emp = 0.0

            blank_by_sallvl = Counter()
            blank_emp_by_sallvl = Counter()

            blank_by_agysub = Counter()
            blank_emp_by_agysub = Counter()

            blank_by_loc = Counter()
            blank_emp_by_loc = Counter()

            blank_by_workschedule = Counter()
            blank_emp_by_workschedule = Counter()

            for row in reader:

                # Rockefeller population definition
                if clean(row.get("WORKSTAT")) != "1":
                    continue

                emp = number(row.get("EMPLOYMENT"))

                if emp is None:
                    raise RuntimeError(
                        f"FY{year}: blank EMPLOYMENT in WORKSTAT=1 row"
                    )

                total_rows += 1
                total_emp += emp

                salary = number(row.get("SALARY"))

                if salary is not None:
                    continue

                blank_rows += 1
                blank_emp += emp

                sallvl = clean(row.get("SALLVL")) or "<BLANK>"
                agysub = clean(row.get("AGYSUB")) or "<BLANK>"
                loc = clean(row.get("LOC")) or "<BLANK>"
                worksch = clean(row.get("WORKSCH")) or "<BLANK>"

                blank_by_sallvl[sallvl] += 1
                blank_emp_by_sallvl[sallvl] += emp

                blank_by_agysub[agysub] += 1
                blank_emp_by_agysub[agysub] += emp

                blank_by_loc[loc] += 1
                blank_emp_by_loc[loc] += emp

                blank_by_workschedule[worksch] += 1
                blank_emp_by_workschedule[worksch] += emp

            pct_emp = (
                100.0 * blank_emp / total_emp
                if total_emp else 0.0
            )

            print()
            print("--- WORKSTAT=1 SALARY COMPLETENESS ---")
            print(f"Rows:                  {total_rows:,}")
            print(f"Employment:            {total_emp:,.0f}")
            print(f"Blank SALARY rows:     {blank_rows:,}")
            print(f"Blank SALARY employment: {blank_emp:,.0f}")
            print(f"Percent employment blank: {pct_emp:.6f}%")

            print()
            print("--- BLANK SALARY BY SALLVL ---")
            for code, emp in blank_emp_by_sallvl.most_common():
                print(
                    f"{code:<12} "
                    f"EMP={emp:>12,.0f} "
                    f"ROWS={blank_by_sallvl[code]:>10,}"
                )

            print()
            print("--- TOP 30 BLANK SALARY AGYSUB ---")
            for code, emp in blank_emp_by_agysub.most_common(30):
                print(
                    f"{code:<12} "
                    f"EMP={emp:>12,.0f} "
                    f"ROWS={blank_by_agysub[code]:>10,}"
                )

            print()
            print("--- TOP 30 BLANK SALARY LOC ---")
            for code, emp in blank_emp_by_loc.most_common(30):
                print(
                    f"{code:<12} "
                    f"EMP={emp:>12,.0f} "
                    f"ROWS={blank_by_loc[code]:>10,}"
                )

            print()
            print("--- BLANK SALARY BY WORKSCH ---")
            for code, emp in blank_emp_by_workschedule.most_common():
                print(
                    f"{code:<12} "
                    f"EMP={emp:>12,.0f} "
                    f"ROWS={blank_by_workschedule[code]:>10,}"
                )

            archive_summary.append(
                {
                    "year": year,
                    "workstat1_rows": total_rows,
                    "workstat1_employment": int(total_emp),
                    "blank_salary_rows": blank_rows,
                    "blank_salary_employment": int(blank_emp),
                    "blank_salary_employment_pct": pct_emp,
                    "fact_member": fact_member,
                    "sallvl_lookup_members": "|".join(salary_lookups),
                    "agysub_lookup_members": "|".join(agency_lookups),
                }
            )

    # --------------------------------------------------------------
    # Cross-year summary
    # --------------------------------------------------------------

    print()
    print()
    print("=" * 110)
    print("CROSS-YEAR SUMMARY")
    print("=" * 110)

    print(
        f"{'YEAR':<6}"
        f"{'EMPLOYMENT':>15}"
        f"{'BLANK EMP':>15}"
        f"{'BLANK %':>14}"
        f"{'BLANK ROWS':>15}"
    )

    for r in archive_summary:
        print(
            f"{r['year']:<6}"
            f"{r['workstat1_employment']:>15,}"
            f"{r['blank_salary_employment']:>15,}"
            f"{r['blank_salary_employment_pct']:>13.4f}%"
            f"{r['blank_salary_rows']:>15,}"
        )

    # --------------------------------------------------------------
    # Save compact evidence artifact.
    # --------------------------------------------------------------

    output = (
        REPO_ROOT
        / "data"
        / "interim"
        / "opm"
        / "opm_fedscope_salary_suppression_diagnostic_2015_2024.csv"
    )

    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(archive_summary[0].keys()),
        )

        writer.writeheader()
        writer.writerows(archive_summary)

    print()
    print(f"Evidence CSV written: {output}")


if __name__ == "__main__":
    main()