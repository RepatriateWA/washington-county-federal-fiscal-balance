from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

RAW_ROOT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "opm"
    / "fedscope"
    / "employment"
)

INTERIM_ROOT = REPO_ROOT / "data" / "interim" / "opm"

CSV_OUTPUT = (
    INTERIM_ROOT
    / "opm_civilian_wage_allocation_evidence_2015_2024.csv"
)

SQL_OUTPUT = (
    REPO_ROOT
    / "etl"
    / "sql"
    / "159_create_opm_civilian_wage_allocation.sql"
)

YEARS = range(2015, 2025)

WA_LOC = "53"

METHODOLOGY_VERSION = "ANALYSIS-158-v1"


def clean(value: str | None) -> str:
    return (value or "").strip()


def as_number(value: str | None) -> float | None:
    value = clean(value).replace(",", "").replace("$", "")

    if not value:
        return None

    return float(value)


def pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return 100.0 * numerator / denominator


def find_zip(year: int) -> Path:
    folder = RAW_ROOT / f"{year}-09"
    zips = list(folder.glob("*.zip"))

    if len(zips) != 1:
        raise RuntimeError(
            f"FY{year}: expected exactly one ZIP in {folder}; "
            f"found {len(zips)}"
        )

    return zips[0]


def decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise RuntimeError("Unable to decode ZIP member")


def read_member(zf: zipfile.ZipFile, member: str) -> str:
    return decode(zf.read(member))


def csv_header(zf: zipfile.ZipFile, member: str) -> list[str]:
    text = read_member(zf, member)
    lines = text.splitlines()

    if not lines:
        return []

    return [
        x.strip().upper()
        for x in next(csv.reader([lines[0]]))
    ]


def discover_fact(zf: zipfile.ZipFile) -> str:
    required = {
        "LOC",
        "AGYSUB",
        "WORKSTAT",
        "EMPLOYMENT",
        "SALARY",
        "SALLVL",
    }

    matches = []

    for member in zf.namelist():
        if member.endswith("/"):
            continue

        try:
            header = set(csv_header(zf, member))
        except Exception:
            continue

        if required.issubset(header):
            matches.append(member)

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one FACT member; found {matches}"
        )

    return matches[0]


def discover_location_lookup(
    zf: zipfile.ZipFile,
    fact_member: str,
) -> str:

    matches = []

    for member in zf.namelist():
        if member.endswith("/") or member == fact_member:
            continue

        try:
            header = set(csv_header(zf, member))
        except Exception:
            continue

        if {"LOC", "LOCTYP", "LOCTYPT"}.issubset(header):
            matches.append(member)

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one location lookup; found {matches}"
        )

    return matches[0]


def discover_agency_lookup(
    zf: zipfile.ZipFile,
    fact_member: str,
) -> str:

    matches = []

    for member in zf.namelist():
        if member.endswith("/") or member == fact_member:
            continue

        try:
            header = set(csv_header(zf, member))
        except Exception:
            continue

        if "AGYSUB" not in header:
            continue

        # Avoid FACTDATA itself; lookup should contain text description fields.
        if any(
            col.endswith("T")
            for col in header
            if col != "AGYSUB"
        ):
            matches.append(member)

    if not matches:
        raise RuntimeError(
            "Could not discover AGYSUB agency lookup"
        )

    # DTagy should normally be the single match.
    if len(matches) > 1:
        matches.sort(
            key=lambda x: (
                0 if "agy" in x.lower() else 1,
                x.lower(),
            )
        )

    return matches[0]


def load_location_lookup(
    zf: zipfile.ZipFile,
    member: str,
) -> dict[str, dict[str, str]]:

    text = read_member(zf, member)
    rows = csv.DictReader(io.StringIO(text))

    result = {}

    for row in rows:
        loc = clean(row.get("LOC"))

        if loc:
            result[loc] = {
                "LOCTYP": clean(row.get("LOCTYP")),
                "LOCTYPT": clean(row.get("LOCTYPT")),
                "LOCT": clean(row.get("LOCT")),
            }

    return result


def discover_postal_agysub_codes(
    zf: zipfile.ZipFile,
    member: str,
) -> set[str]:
    """
    USPS is excluded from the Rockefeller civilian Federal Budget wage concept.

    Public FedScope agency labels may contain unrelated entities with the word
    'Postal' (for example, regulatory bodies). WCFFBP therefore does NOT use
    fuzzy text matching to infer USPS records.

    The preserved public FedScope employment files are treated as already
    excluding USPS unless an exact, explicitly identified USPS agency code is
    demonstrated from the source data.

    Current production rule:
        no AGYSUB codes are removed by inference.
    """
    return set()


def analyze_year(year: int) -> dict[str, object]:

    zip_path = find_zip(year)

    with zipfile.ZipFile(zip_path) as zf:

        fact_member = discover_fact(zf)

        loc_member = discover_location_lookup(
            zf,
            fact_member,
        )

        agy_member = discover_agency_lookup(
            zf,
            fact_member,
        )

        location_lookup = load_location_lookup(
            zf,
            loc_member,
        )

        postal_codes = discover_postal_agysub_codes(
            zf,
            agy_member,
        )

        fact_text = read_member(zf, fact_member)
        reader = csv.DictReader(io.StringIO(fact_text))

        workstat1_employment = 0.0
        workstat1_blank_salary_employment = 0.0

        us_type_employment = 0.0
        us_type_known_salary_mass = 0.0
        us_type_blank_salary_employment = 0.0

        wa_employment = 0.0
        wa_known_salary_mass = 0.0
        wa_blank_salary_employment = 0.0

        usps_excluded_employment = 0.0
        usps_excluded_known_salary_mass = 0.0

        for row in reader:

            if clean(row.get("WORKSTAT")) != "1":
                continue

            emp = as_number(row.get("EMPLOYMENT"))

            if emp is None:
                raise RuntimeError(
                    f"FY{year}: WORKSTAT=1 row has blank EMPLOYMENT"
                )

            salary = as_number(row.get("SALARY"))
            agysub = clean(row.get("AGYSUB"))
            loc = clean(row.get("LOC"))

            # ----------------------------------------------------------
            # USPS exclusion
            # ----------------------------------------------------------

            if agysub in postal_codes:

                usps_excluded_employment += emp

                if salary is not None:
                    usps_excluded_known_salary_mass += (
                        emp * salary
                    )

                continue

            # ----------------------------------------------------------
            # Overall eligible OPM population
            # ----------------------------------------------------------

            workstat1_employment += emp

            if salary is None:
                workstat1_blank_salary_employment += emp

            # ----------------------------------------------------------
            # OPM U.S.-type denominator
            #
            # Includes normal state/DC locations AND LOC='US' suppressed
            # because OPM itself classifies that suppressed geography as
            # LOCTYPT='United States'.
            #
            # Excludes foreign countries, territories, and unspecified.
            # ----------------------------------------------------------

            loc_info = location_lookup.get(loc)

            if loc_info is None:
                raise RuntimeError(
                    f"FY{year}: LOC={loc!r} missing from location lookup"
                )

            is_us_type = (
                loc_info["LOCTYPT"].strip().upper()
                == "UNITED STATES"
            )

            if is_us_type:

                us_type_employment += emp

                if salary is None:
                    us_type_blank_salary_employment += emp
                else:
                    us_type_known_salary_mass += (
                        emp * salary
                    )

            # ----------------------------------------------------------
            # Washington numerator
            # ----------------------------------------------------------

            if loc == WA_LOC:

                wa_employment += emp

                if salary is None:
                    wa_blank_salary_employment += emp
                else:
                    wa_known_salary_mass += (
                        emp * salary
                    )

        if us_type_known_salary_mass <= 0:
            raise RuntimeError(
                f"FY{year}: U.S.-type known salary mass is not positive"
            )

        if wa_known_salary_mass <= 0:
            raise RuntimeError(
                f"FY{year}: Washington known salary mass is not positive"
            )

        wa_share = (
            wa_known_salary_mass
            / us_type_known_salary_mass
        )

        confidence = (
            "MEDIUM_HIGH"
            if year <= 2016
            else "MEDIUM"
        )

        return {
            "fiscal_year": year,
            "snapshot_month": f"{year}-09",
            "fact_member": fact_member,
            "location_lookup_member": loc_member,
            "agency_lookup_member": agy_member,
            "workstat1_employment": int(
                workstat1_employment
            ),
            "workstat1_blank_salary_employment": int(
                workstat1_blank_salary_employment
            ),
            "workstat1_blank_salary_employment_pct":
                pct(
                    workstat1_blank_salary_employment,
                    workstat1_employment,
                ),
            "us_type_employment": int(
                us_type_employment
            ),
            "us_type_known_salary_mass_dollars":
                round(
                    us_type_known_salary_mass,
                    2,
                ),
            "us_type_blank_salary_employment": int(
                us_type_blank_salary_employment
            ),
            "us_type_blank_salary_employment_pct":
                pct(
                    us_type_blank_salary_employment,
                    us_type_employment,
                ),
            "wa_employment": int(
                wa_employment
            ),
            "wa_known_salary_mass_dollars":
                round(
                    wa_known_salary_mass,
                    2,
                ),
            "wa_blank_salary_employment": int(
                wa_blank_salary_employment
            ),
            "wa_blank_salary_employment_pct":
                pct(
                    wa_blank_salary_employment,
                    wa_employment,
                ),
            "wa_known_salary_share":
                wa_share,
            "usps_excluded_employment": int(
                usps_excluded_employment
            ),
            "usps_excluded_known_salary_mass_dollars":
                round(
                    usps_excluded_known_salary_mass,
                    2,
                ),
            "allocation_confidence": confidence,
            "methodology_version":
                METHODOLOGY_VERSION,
        }


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_sql(rows: list[dict[str, object]]) -> str:

    values = []

    for r in rows:

        values.append(
            "("
            + ", ".join(
                [
                    str(r["fiscal_year"]),
                    sql_quote(str(r["snapshot_month"])),
                    sql_quote(str(r["fact_member"])),
                    sql_quote(
                        str(r["location_lookup_member"])
                    ),
                    sql_quote(
                        str(r["agency_lookup_member"])
                    ),
                    str(r["workstat1_employment"]),
                    str(
                        r[
                            "workstat1_blank_salary_employment"
                        ]
                    ),
                    f"{r['workstat1_blank_salary_employment_pct']:.12f}",
                    str(r["us_type_employment"]),
                    f"{r['us_type_known_salary_mass_dollars']:.2f}",
                    str(
                        r[
                            "us_type_blank_salary_employment"
                        ]
                    ),
                    f"{r['us_type_blank_salary_employment_pct']:.12f}",
                    str(r["wa_employment"]),
                    f"{r['wa_known_salary_mass_dollars']:.2f}",
                    str(
                        r[
                            "wa_blank_salary_employment"
                        ]
                    ),
                    f"{r['wa_blank_salary_employment_pct']:.12f}",
                    f"{r['wa_known_salary_share']:.15f}",
                    str(r["usps_excluded_employment"]),
                    f"{r['usps_excluded_known_salary_mass_dollars']:.2f}",
                    sql_quote(
                        str(r["allocation_confidence"])
                    ),
                    sql_quote(
                        str(r["methodology_version"])
                    ),
                ]
            )
            + ")"
        )

    values_sql = ",\n".join(values)

    return f"""-- ============================================================================
-- ETL-159 — OPM Civilian Wage Allocation Evidence
-- ============================================================================
--
-- GENERATED BY:
--     scripts/build_opm_civilian_wage_allocation_evidence.py
--
-- PURPOSE:
--     Preserve the OPM public-FedScope evidence used to geographically allocate
--     OMB civilian/nonmilitary federal wage obligations to Washington State.
--
-- ACCOUNTING CONTROL:
--     omb.v_federal_wage_obligation_control
--
-- ALLOCATION:
--     Washington known OPM salary mass
--     --------------------------------
--     OPM U.S.-type known salary mass
--
-- U.S.-TYPE:
--     OPM LOCTYPT='United States', including LOC='US' suppressed geography.
--
-- SUPPRESSION:
--     Missing exact salary and suppressed geography are preserved as evidence.
--     They are not imputed.
--
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS opm;


CREATE TABLE IF NOT EXISTS opm.civilian_wage_allocation_evidence (
    fiscal_year INTEGER PRIMARY KEY,

    snapshot_month TEXT NOT NULL,

    fact_member TEXT NOT NULL,
    location_lookup_member TEXT NOT NULL,
    agency_lookup_member TEXT NOT NULL,

    workstat1_employment BIGINT NOT NULL,
    workstat1_blank_salary_employment BIGINT NOT NULL,
    workstat1_blank_salary_employment_pct NUMERIC(18,12) NOT NULL,

    us_type_employment BIGINT NOT NULL,
    us_type_known_salary_mass_dollars NUMERIC(24,2) NOT NULL,
    us_type_blank_salary_employment BIGINT NOT NULL,
    us_type_blank_salary_employment_pct NUMERIC(18,12) NOT NULL,

    wa_employment BIGINT NOT NULL,
    wa_known_salary_mass_dollars NUMERIC(24,2) NOT NULL,
    wa_blank_salary_employment BIGINT NOT NULL,
    wa_blank_salary_employment_pct NUMERIC(18,12) NOT NULL,

    wa_known_salary_share NUMERIC(20,15) NOT NULL,

    usps_excluded_employment BIGINT NOT NULL,
    usps_excluded_known_salary_mass_dollars NUMERIC(24,2) NOT NULL,

    allocation_confidence TEXT NOT NULL,

    methodology_version TEXT NOT NULL,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP
);


DO $$
BEGIN

    IF EXISTS (
        SELECT 1
        FROM opm.civilian_wage_allocation_evidence
        WHERE fiscal_year BETWEEN 2015 AND 2024
    ) THEN
        RAISE EXCEPTION
            'ETL-159 refuses to overwrite existing FFY2015-FFY2024 OPM civilian wage evidence.';
    END IF;

END
$$;


INSERT INTO opm.civilian_wage_allocation_evidence (
    fiscal_year,
    snapshot_month,
    fact_member,
    location_lookup_member,
    agency_lookup_member,
    workstat1_employment,
    workstat1_blank_salary_employment,
    workstat1_blank_salary_employment_pct,
    us_type_employment,
    us_type_known_salary_mass_dollars,
    us_type_blank_salary_employment,
    us_type_blank_salary_employment_pct,
    wa_employment,
    wa_known_salary_mass_dollars,
    wa_blank_salary_employment,
    wa_blank_salary_employment_pct,
    wa_known_salary_share,
    usps_excluded_employment,
    usps_excluded_known_salary_mass_dollars,
    allocation_confidence,
    methodology_version
)
VALUES
{values_sql};


CREATE OR REPLACE VIEW opm.v_omb_civilian_wage_allocation AS
SELECT
    e.fiscal_year,

    o.budget_vintage,
    o.value_status,
    o.accounting_measure,
    o.scope,

    o.nonmilitary_wage_obligations_dollars
        AS omb_nonmilitary_wage_obligations_dollars,

    e.snapshot_month,

    e.workstat1_employment,
    e.workstat1_blank_salary_employment,
    e.workstat1_blank_salary_employment_pct,

    e.us_type_employment,
    e.us_type_known_salary_mass_dollars,
    e.us_type_blank_salary_employment,
    e.us_type_blank_salary_employment_pct,

    e.wa_employment,
    e.wa_known_salary_mass_dollars,
    e.wa_blank_salary_employment,
    e.wa_blank_salary_employment_pct,

    e.wa_known_salary_share,

    (
        o.nonmilitary_wage_obligations_dollars
        * e.wa_known_salary_share
    )::NUMERIC(24,2)
        AS allocated_wa_civilian_wage_dollars,

    e.usps_excluded_employment,
    e.usps_excluded_known_salary_mass_dollars,

    e.allocation_confidence,
    e.methodology_version

FROM opm.civilian_wage_allocation_evidence e

JOIN omb.v_federal_wage_obligation_control o
    ON o.fiscal_year = e.fiscal_year;


-- ============================================================================
-- Validation
-- ============================================================================

DO $$
DECLARE
    v_evidence_rows INTEGER;
    v_view_rows INTEGER;
    v_bad_years INTEGER;
    v_bad_values INTEGER;
    v_bad_confidence INTEGER;
BEGIN

    SELECT COUNT(*)
    INTO v_evidence_rows
    FROM opm.civilian_wage_allocation_evidence
    WHERE fiscal_year BETWEEN 2015 AND 2024;

    IF v_evidence_rows <> 10 THEN
        RAISE EXCEPTION
            'ETL-159 validation failed: expected 10 evidence rows; found %.',
            v_evidence_rows;
    END IF;


    SELECT COUNT(*)
    INTO v_view_rows
    FROM opm.v_omb_civilian_wage_allocation
    WHERE fiscal_year BETWEEN 2015 AND 2024;

    IF v_view_rows <> 10 THEN
        RAISE EXCEPTION
            'ETL-159 validation failed: expected 10 allocation rows; found %.',
            v_view_rows;
    END IF;


    SELECT COUNT(*)
    INTO v_bad_years
    FROM (
        SELECT fiscal_year
        FROM opm.civilian_wage_allocation_evidence
        WHERE fiscal_year BETWEEN 2015 AND 2024
        GROUP BY fiscal_year
        HAVING COUNT(*) <> 1
    ) AS bad;

    IF v_bad_years <> 0 THEN
        RAISE EXCEPTION
            'ETL-159 validation failed: % fiscal year(s) do not occur exactly once.',
            v_bad_years;
    END IF;


    SELECT COUNT(*)
    INTO v_bad_values
    FROM opm.v_omb_civilian_wage_allocation
    WHERE us_type_known_salary_mass_dollars <= 0
       OR wa_known_salary_mass_dollars <= 0
       OR wa_known_salary_share <= 0
       OR wa_known_salary_share >= 1
       OR allocated_wa_civilian_wage_dollars <= 0;

    IF v_bad_values <> 0 THEN
        RAISE EXCEPTION
            'ETL-159 validation failed: % year(s) contain invalid allocation values.',
            v_bad_values;
    END IF;


    SELECT COUNT(*)
    INTO v_bad_confidence
    FROM opm.civilian_wage_allocation_evidence
    WHERE
        (fiscal_year IN (2015, 2016)
            AND allocation_confidence <> 'MEDIUM_HIGH')
        OR
        (fiscal_year BETWEEN 2017 AND 2024
            AND allocation_confidence <> 'MEDIUM');

    IF v_bad_confidence <> 0 THEN
        RAISE EXCEPTION
            'ETL-159 validation failed: confidence classification mismatch in % row(s).',
            v_bad_confidence;
    END IF;


    RAISE NOTICE
        'ETL-159 validation PASSED: 10-year OPM civilian wage allocation evidence and OMB-controlled Washington allocation established.';

END
$$;


COMMIT;
"""


def main():

    INTERIM_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []

    print("=" * 100)
    print("BUILD OPM CIVILIAN WAGE ALLOCATION EVIDENCE")
    print("=" * 100)

    for year in YEARS:

        result = analyze_year(year)
        rows.append(result)

        print(
            f"FY{year}: "
            f"WA salary=${result['wa_known_salary_mass_dollars']:,.0f} | "
            f"US-type salary=${result['us_type_known_salary_mass_dollars']:,.0f} | "
            f"WA share={100 * result['wa_known_salary_share']:.6f}% | "
            f"blank={result['workstat1_blank_salary_employment_pct']:.4f}% | "
            f"confidence={result['allocation_confidence']}"
        )

    fieldnames = list(rows[0].keys())

    with CSV_OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    SQL_OUTPUT.write_text(
        build_sql(rows),
        encoding="utf-8",
    )

    print()
    print(f"Evidence CSV: {CSV_OUTPUT}")
    print(f"Generated SQL: {SQL_OUTPUT}")
    print()
    print("PASS: OPM civilian wage allocation evidence generated.")


if __name__ == "__main__":
    main()