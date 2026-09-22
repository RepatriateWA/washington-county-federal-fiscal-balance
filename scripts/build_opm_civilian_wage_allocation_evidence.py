"""
Build OPM FedScope civilian federal wage allocation evidence for FFY2015-FF2024.

Accounting control:
    OMB nonmilitary wage obligations = object classes 11.1 + 11.3 + 11.5 + 11.8

Allocation source:
    OPM FedScope September Employment Cube, WORKSTAT=1
    ("Non-Seasonal Full Time Permanent")

Allocation weight:
    EMPLOYMENT * SALARY

Washington:
    LOC=53

Denominator:
    Explicit 50 states + District of Columbia FIPS whitelist.

Notes:
    OPM location is official duty station, not residence.
    OPM is used for geographic allocation only; OMB remains the accounting control.
    Blank SALARY values are preserved as diagnostics and are not converted to zero.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from etl.common.db import get_connection


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = REPO_ROOT / "data" / "raw" / "opm" / "fedscope" / "employment"
INTERIM_ROOT = REPO_ROOT / "data" / "interim" / "opm"

YEARS = tuple(range(2015, 2025))
WA_LOC = "53"

STATE_DC_FIPS = {
    "01","02","04","05","06","08","09","10","11","12","13","15","16",
    "17","18","19","20","21","22","23","24","25","26","27","28","29",
    "30","31","32","33","34","35","36","37","38","39","40","41","42",
    "44","45","46","47","48","49","50","51","53","54","55","56"
}

OUTPUT_EVIDENCE = INTERIM_ROOT / "opm_fedscope_civilian_wage_allocation_evidence_2015_2024.csv"
OUTPUT_GEOGRAPHY = INTERIM_ROOT / "opm_fedscope_civilian_geography_diagnostic_2015_2024.csv"
OUTPUT_MISSING_SALARY = INTERIM_ROOT / "opm_fedscope_civilian_missing_salary_diagnostic_2015_2024.csv"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_code(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    return text.zfill(2) if text.isdigit() else text


def parse_numeric(
    value: Any,
    field: str,
    year: int,
    *,
    allow_blank: bool = False,
) -> float | None:
    text = "" if value is None else str(value).strip()

    if not text:
        if allow_blank:
            return None
        raise RuntimeError(f"{year}: blank numeric field {field}")

    text = text.replace(",", "")
    if field == "SALARY":
        text = text.replace("$", "")

    try:
        number = float(text)
    except ValueError as exc:
        raise RuntimeError(
            f"{year}: invalid numeric {field}={value!r}"
        ) from exc

    if not math.isfinite(number):
        raise RuntimeError(
            f"{year}: non-finite numeric {field}={value!r}"
        )
    if number < 0:
        raise RuntimeError(
            f"{year}: negative numeric {field}={value!r}"
        )

    return number


def find_year_zip(year: int) -> Path:
    directory = RAW_ROOT / f"{year}-09"
    if not directory.exists():
        raise RuntimeError(f"{year}: missing OPM directory: {directory}")

    candidates = sorted(directory.glob("*.zip"))
    if len(candidates) != 1:
        raise ValueError(
            f"{year}: expected exactly one ZIP in {directory}; "
            f"found {[p.name for p in candidates]}"
        )
    return candidates[0]


def find_member_by_basename(names: list[str], basename: str) -> str:
    matches = [
        name for name in names
        if Path(name).name.lower() == basename.lower() and not name.endswith("/")
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one archive member named {basename!r}; found {matches}"
        )
    return matches[0]


def find_fact_member(names: list[str]) -> str:
    matches = [
        name for name in names
        if "factdata" in Path(name).name.lower() and not name.endswith("/")
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one FACTDATA member; found {matches}"
        )
    return matches[0]


def read_lookup(zf: zipfile.ZipFile, member: str) -> list[dict[str, str]]:
    with zf.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding="cp1252", newline="")
        reader = csv.DictReader(text)
        return [
            {
                str(k).strip(): ("" if v is None else str(v).strip())
                for k, v in row.items()
            }
            for row in reader
        ]


def stream_fact(zf: zipfile.ZipFile, member: str):
    with zf.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding="cp1252", newline="")
        reader = csv.DictReader(text)
        fieldnames = [str(x).strip() for x in (reader.fieldnames or [])]
        yield "__FIELDNAMES__", fieldnames
        for row_number, row in enumerate(reader, start=2):
            yield row_number, {
                str(k).strip(): ("" if v is None else str(v).strip())
                for k, v in row.items()
            }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write empty CSV: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_omb_controls() -> dict[int, int]:
    sql = """
        SELECT
            fiscal_year,
            nonmilitary_wage_obligations_dollars
        FROM omb.v_federal_wage_obligation_control
        WHERE fiscal_year BETWEEN 2015 AND 2024
        ORDER BY fiscal_year;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    controls = {int(year): int(value) for year, value in rows}

    expected = set(YEARS)
    observed = set(controls)
    if observed != expected:
        raise RuntimeError(
            "OMB control view coverage mismatch. "
            f"Missing={sorted(expected - observed)}, "
            f"unexpected={sorted(observed - expected)}"
        )

    return controls


def build_location_lookup(
    rows: list[dict[str, str]],
    year: int,
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    lookup: dict[str, dict[str, str]] = {}

    for row in rows:
        loc = normalize_code(row.get("LOC", ""))
        if not loc:
            continue
        if loc in lookup:
            raise RuntimeError(f"{year}: duplicate location code {loc}")
        lookup[loc] = row

    missing = sorted(STATE_DC_FIPS - set(lookup))
    if missing:
        raise RuntimeError(
            f"{year}: missing expected state/DC location codes: {missing}"
        )

    for loc in sorted(STATE_DC_FIPS):
        loc_type = lookup[loc].get("LOCTYPT", "").strip()
        if loc_type != "United States":
            raise RuntimeError(
                f"{year}: LOC={loc} expected LOCTYPT='United States'; "
                f"observed {loc_type!r}"
            )

    wa_label = lookup[WA_LOC].get("LOCT", "").upper()
    if "WASHINGTON" not in wa_label:
        raise RuntimeError(
            f"{year}: LOC=53 does not resolve to Washington: {lookup[WA_LOC]}"
        )

    extra_us = []
    for loc, row in lookup.items():
        if (
            row.get("LOCTYPT", "").strip() == "United States"
            and loc not in STATE_DC_FIPS
        ):
            extra_us.append({"LOC": loc, **row})

    if len(extra_us) != 1:
        raise RuntimeError(
            f"{year}: expected exactly one extra United States location row; "
            f"found {extra_us}"
        )

    return lookup, extra_us


def validate_workstat_lookup(
    rows: list[dict[str, str]],
    year: int,
) -> None:
    matches = [
        row for row in rows
        if str(row.get("WORKSTAT", "")).strip() == "1"
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"{year}: expected exactly one WORKSTAT=1 lookup row; found {matches}"
        )

    label = " ".join(str(v) for v in matches[0].values() if v)
    if "Non-Seasonal Full Time Permanent" not in label:
        raise RuntimeError(
            f"{year}: unexpected WORKSTAT=1 label: {matches[0]}"
        )


def classify_geography(
    loc: str,
    location_lookup: dict[str, dict[str, str]],
) -> str:
    if loc in STATE_DC_FIPS:
        return "STATES_DC"

    row = location_lookup.get(loc)
    if row is None:
        return "UNKNOWN_LOCATION_CODE"

    loc_type = row.get("LOCTYPT", "").strip()
    mapping = {
        "U.S. Territories": "US_TERRITORIES",
        "Foreign Countries": "FOREIGN_COUNTRIES",
        "Unspecified": "UNSPECIFIED",
        "United States": "EXTRA_US_TYPE",
    }
    return mapping.get(loc_type, f"OTHER::{loc_type or 'BLANK'}")


def process_year(
    year: int,
    omb_control_dollars: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:

    zip_path = find_year_zip(year)
    zip_hash = sha256_file(zip_path)

    print()
    print("-" * 118)
    print(f"{year}-09")
    print(f"ZIP: {zip_path}")
    print(f"SHA-256: {zip_hash}")
    print("-" * 118)

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        fact_member = find_fact_member(names)
        dtloc_member = find_member_by_basename(names, "DTloc.txt")
        dtwkstat_member = find_member_by_basename(names, "DTwkstat.txt")

        location_rows = read_lookup(zf, dtloc_member)
        workstat_rows = read_lookup(zf, dtwkstat_member)

        location_lookup, extra_us_rows = build_location_lookup(
            location_rows, year
        )
        validate_workstat_lookup(workstat_rows, year)

        print(f"FACT member: {fact_member}")
        print(f"Location member: {dtloc_member}")
        print(f"Work-status member: {dtwkstat_member}")
        print("Extra U.S.-type lookup row:", extra_us_rows[0])

        fact_stream = stream_fact(zf, fact_member)
        marker, fieldnames = next(fact_stream)

        if marker != "__FIELDNAMES__":
            raise RuntimeError(f"{year}: FACT reader initialization failure")

        required_fields = {
            "LOC", "WORKSTAT", "WORKSCH", "EMPLOYMENT",
            "SALARY", "AGYSUB", "OCC", "SALLVL"
        }

        missing_fields = required_fields - set(fieldnames)
        if missing_fields:
            raise RuntimeError(
                f"{year}: FACTDATA missing required fields: "
                f"{sorted(missing_fields)}"
            )

        fact_rows = 0
        workstat_1_rows = 0

        all_employment = 0.0
        all_salary_mass = 0.0

        states_dc_employment = 0.0
        states_dc_salary_mass = 0.0

        wa_employment = 0.0
        wa_salary_mass = 0.0

        geography = defaultdict(
            lambda: {
                "row_count": 0,
                "employment": 0.0,
                "salary_mass": 0.0,
                "missing_salary_rows": 0,
                "missing_salary_employment": 0.0,
            }
        )

        missing_salary_rows: list[dict[str, Any]] = []
        missing_salary_by_sallvl = Counter()
        missing_salary_by_agysub = Counter()

        for row_number, row in fact_stream:
            fact_rows += 1

            workstat = str(row.get("WORKSTAT", "")).strip()
            if workstat != "1":
                continue

            workstat_1_rows += 1
            loc = normalize_code(row.get("LOC"))

            employment = parse_numeric(
                row.get("EMPLOYMENT"),
                "EMPLOYMENT",
                year,
            )
            assert employment is not None

            all_employment += employment

            geo_class = classify_geography(loc, location_lookup)
            geography[geo_class]["row_count"] += 1
            geography[geo_class]["employment"] += employment

            if loc in STATE_DC_FIPS:
                states_dc_employment += employment
            if loc == WA_LOC:
                wa_employment += employment

            salary = parse_numeric(
                row.get("SALARY"),
                "SALARY",
                year,
                allow_blank=True,
            )

            if salary is None:
                geography[geo_class]["missing_salary_rows"] += 1
                geography[geo_class]["missing_salary_employment"] += employment

                sallvl = str(row.get("SALLVL", "")).strip()
                agysub = str(row.get("AGYSUB", "")).strip()

                missing_salary_by_sallvl[sallvl] += 1
                missing_salary_by_agysub[agysub] += 1

                missing_salary_rows.append(
                    {
                        "fiscal_year": year,
                        "snapshot": f"{year}-09",
                        "source_row_number": row_number,
                        "LOC": loc,
                        "WORKSTAT": workstat,
                        "WORKSCH": str(row.get("WORKSCH", "")).strip(),
                        "EMPLOYMENT": employment,
                        "AGYSUB": agysub,
                        "OCC": str(row.get("OCC", "")).strip(),
                        "SALLVL": sallvl,
                        "SALARY_raw": row.get("SALARY"),
                        "geography_class": geo_class,
                        "treatment": (
                            "EXCLUDED_FROM_SALARY_MASS_MISSING_SOURCE_VALUE"
                        ),
                    }
                )
                continue

            salary_mass = employment * salary

            all_salary_mass += salary_mass
            geography[geo_class]["salary_mass"] += salary_mass

            if loc in STATE_DC_FIPS:
                states_dc_salary_mass += salary_mass
            if loc == WA_LOC:
                wa_salary_mass += salary_mass

    if workstat_1_rows <= 0:
        raise RuntimeError(f"{year}: no WORKSTAT=1 rows")
    if states_dc_employment <= 0:
        raise RuntimeError(f"{year}: state/DC employment denominator not positive")
    if states_dc_salary_mass <= 0:
        raise RuntimeError(f"{year}: state/DC salary denominator not positive")
    if wa_employment <= 0:
        raise RuntimeError(f"{year}: Washington employment not positive")
    if wa_salary_mass <= 0:
        raise RuntimeError(f"{year}: Washington salary mass not positive")

    wa_employment_share = wa_employment / states_dc_employment
    wa_salary_share = wa_salary_mass / states_dc_salary_mass

    if not 0 <= wa_employment_share <= 1:
        raise RuntimeError(
            f"{year}: invalid WA employment share {wa_employment_share}"
        )
    if not 0 <= wa_salary_share <= 1:
        raise RuntimeError(
            f"{year}: Washington salary share {wa_salary_share}"
        )

    allocated_wa_dollars = omb_control_dollars * wa_salary_share

    missing_count = len(missing_salary_rows)
    missing_employment = sum(
        float(row["EMPLOYMENT"]) for row in missing_salary_rows
    )

    extra_us_loc = normalize_code(extra_us_rows[0].get("LOC", ""))
    extra_us_diag = geography.get("EXTRA_US_TYPE", {})

    evidence = {
        "fiscal_year": year,
        "snapshot": f"{year}-09",
        "source_zip_path": str(zip_path.relative_to(REPO_ROOT)),
        "source_zip_sha256": zip_hash,
        "fact_member": fact_member,
        "fact_row_count": fact_rows,
        "workstat_1_row_count": workstat_1_rows,
        "workstat_1_all_location_employment": all_employment,
        "workstat_1_all_location_salary_mass_dollars": all_salary_mass,
        "states_dc_employment": states_dc_employment,
        "states_dc_salary_mass_dollars": states_dc_salary_mass,
        "washington_employment": wa_employment,
        "washington_salary_mass_dollars": wa_salary_mass,
        "washington_employment_share": wa_employment_share,
        "washington_salary_share": wa_salary_share,
        "omb_nonmilitary_wage_obligations_dollars": omb_control_dollars,
        "allocated_washington_civilian_wage_obligations_dollars": allocated_wa_dollars,
        "missing_salary_row_count": missing_count,
        "missing_salary_employment": missing_employment,
        "extra_us_type_location_code": extra_us_loc,
        "extra_us_type_employment": extra_us_diag.get("employment", 0.0),
        "extra_us_type_salary_mass_dollars": extra_us_diag.get("salary_mass", 0.0),
        "allocation_population": "WORKSTAT=1",
        "allocation_population_label": "Non-Seasonal Full Time Permanent",
        "allocation_denominator": "50_STATES_PLUS_DC",
        "allocation_weight": "EMPLOYMENT_X_SALARY",
        "accounting_control_source": "OMB_OBJECT_CLASS",
        "allocation_source": "OPM_FEDSCOPE",
        "location_concept": "OFFICIAL_DUTY_STATION",
    }

    geography_rows = []
    ordered = [
        "STATES_DC",
        "US_TERRITORIES",
        "FOREIGN_COUNTRIES",
        "UNSPECIFIED",
        "EXTRA_US_TYPE",
        "UNKNOWN_LOCATION_CODE",
    ]

    for geo_class in ordered + sorted(set(geography) - set(ordered)):
        values = geography.get(
            geo_class,
            {
                "row_count": 0,
                "employment": 0.0,
                "salary_mass": 0.0,
                "missing_salary_rows": 0,
                "missing_salary_employment": 0.0,
            },
        )

        geography_rows.append(
            {
                "fiscal_year": year,
                "snapshot": f"{year}-09",
                "geography_class": geo_class,
                "row_count": values["row_count"],
                "employment": values["employment"],
                "salary_mass_dollars": values["salary_mass"],
                "missing_salary_rows": values["missing_salary_rows"],
                "missing_salary_employment": values["missing_salary_employment"],
            }
        )

    print(f"FACT rows: {fact_rows:,}")
    print(f"WORKSTAT=1 rows: {workstat_1_rows:,}")
    print(f"All-location employment: {all_employment:,.0f}")
    print(f"States + DC employment: {states_dc_employment:,.0f}")
    print(f"WA employment: {wa_employment:,.0f}")
    print(f"States + DC salary mass: ${states_dc_salary_mass:,.0f}")
    print(f"WA salary_mass: ${wa_salary_mass:,.0f}")
    print(f"WA employment share: {wa_employment_share:.6%}")
    print(f"WA salary share: {wa_salary_share:.6%}")
    print(f"OMB nonmilitary wage control: ${omb_control_dollars:,.0f}")
    print(f"OMB -> WA civilian allocation: ${allocated_wa_dollars:,.0f}")
    print(f"Blank SALARY rows: {missing_count:,}")
    print(
        "Employment represented by blank SALARY rows: "
        f"{missing_employment:,.0f}"
    )

    if missing_salary_by_sallvl:
        print(
            "Blank SALARY rows by SALLVL:",
            dict(missing_salary_by_sallvl),
        )

    if missing_salary_by_agysub:
        print(
            "Top blank-SALARY AGYSUB values:",
            missing_salary_by_agysub.most_common(10),
        )

    return evidence, geography_rows, missing_salary_rows


def validate_final_evidence(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 10:
        raise RuntimeError(
            f"Expected 10 annual rows; found {len(rows)}"
        )

    years = {int(row["fiscal_year"]) for row in rows}
    if years != set(YEARS):
        raise RuntimeError(
            f"Unexpected annual coverage: {sorted(years)}"
        )

    row_2016 = next(
        row for row in rows
        if int(row["fiscal_year"]) == 2016
    )

    observed_wa_employment = float(
        row_2016["washington_employment"]
    )
    if abs(observed_wa_employment - 47170.0) > 0.5:
        raise RuntimeError(
            "FY2016 replication failure: "
            f"WA employment={observed_wa_employment:,.0f}; "
            "expected 47,170."
        )

    observed_share = float(
        row_2016["washington_salary_share"]
    )
    expected_share = 0.023868

    if abs(observed_share - expected_share) > 0.00002:
        raise RuntimeError(
            "FY2016 replication failure: "
            f"WA salary share={observed_share:.8f}; "
            f"expected approximately {expected_share:.6f}."
        )

    observed_allocation = float(
        row_2016[
            "allocated_washington_civilian_wage_obligations_dollars"
        ]
    )
    expected_allocation = 3.727e9

    if abs(observed_allocation - 3.727e9) > 500000:
        raise RuntimeError(
            "FY2016 replication failure: "
            f"allocated WA civilian wages=${observed_allocation:,.0}. "
            f"Expected approximately ${expected_allocation:,.0f}."
        )


def main() -> None:
    print("=" * 118)
    print("OPM FEDSCOPE CIVILIAN WAGE ALLOCATION EVIDENCE 2015-2024")
    print("=" * 118)

    INTERIM_ROOT.mkdir(parents=True, exist_ok=True)
    omb_controls = load_omb_controls()

    evidence_rows: list[dict[str, Any]] = []
    geography_rows: list[dict[str, Any]] = []
    missing_salary_rows: list[dict[str, Any]] = []

    for year in YEARS:
        evidence, geography, missing_salary = process_year(
            year,
            omb_controls[year],
        )
        evidence_rows.append(evidence)
        geography_rows.extend(geography)
        missing_salary_rows.extend(missing_salary)

    validate_final_evidence(evidence_rows)

    write_csv(OUTPUT_EVIDENCE, evidence_rows)
    write_csv(OUTPUT_GEOGRAPHY, geography_rows)

    if missing_salary_rows:
        write_csv(OUTPUT_MISSING_SALARY, missing_salary_rows)

    print()
    print("=" * 118)
    print("TEN-YEAR SUMMARY")
    print("=" * 118)

    print(
        f"{'FFY':<6}"
        f"{'WA EMP':>12}"
        f"{'WA SALARY MASS':>20}"
        f"{'WA SHARE':>12}"
        f"{'OMB CONTROL':>20}"
        f"{'OMB -> WA':>20}"
        f"{'MISS SAL':>12}"
    )

    for row in evidence_rows:
        print(
            f"{row['fiscal_year']:<6}"
            f"{row['washington_employment']:>12,.0f}"
            f"{row['washington_salary_mass_dollars']:>20,.0f}"
            f"{row['washington_salary_share']:>12.4%}"
            f"{row['omb_nonmilitary_wage_obligations_dollars']:>20,.0f}"
            f"{row['allocated_washington_civilian_wage_obligations_dollars']:>20,.0f}"
            f"{row['missing_salary_row_count']:>12,}"
        )

    print()
    print(f"Evidence: {OUTPUT_EVIDENCE}")
    print(f"Geography diagnostic: {OUTPUT_GEOGRAPHY}")
    if missing_salary_rows:
        print(f"Missing salary diagnostic: {OUTPUT_MISSING_SALARY}")

    print()
    print(
        "VALIDATION PASS: OPM civilian allocation evidence "
        "constructed for FFY2015-FFY2024."
    )


if __name__ == "__main__":
    main()
