from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


# =============================================================================
# ETL-172J-5
#
# Washington Federal Receipts Final Reconstruction v0.1
#
# Purpose
# -------
# Assemble the certified Washington federal-receipts allocations for
# FFY2015-FFY2024 into one auditable receipts-side reconstruction.
#
# This stage:
#   * consumes certified upstream allocation artifacts;
#   * does not introduce a new allocation methodology;
#   * proves the national receipts disposition identity;
#   * sums certified Washington receipt allocations;
#   * compares the reconstruction diagnostically with ETL-171 IRS gross
#     collections;
#   * does not force reconciliation with IRS gross collections;
#   * does not write to PostgreSQL;
#   * does not authorize the final fiscal-balance ledger.
#
# Principal identities
# --------------------
#
# National:
#
#   OMB total federal receipts
#       =
#   national controls represented by certified WA allocation methods
#       + intentionally unallocable national receipts
#       + withheld unresolved national receipts
#
# Washington:
#
#   WA reconstructed federal receipts
#       =
#   sum of certified Washington component allocations
#
# ETL-171 IRS gross collections remain an independent administrative
# benchmark and are NOT forced to equal the economic-incidence reconstruction.
# =============================================================================


STUDY_FY_START = 2015
STUDY_FY_END = 2024

YEARS = list(
    range(
        STUDY_FY_START,
        STUDY_FY_END + 1,
    )
)

TOLERANCE_MILLIONS = 0.01
TOLERANCE_DOLLARS = 1.00


# =============================================================================
# Paths
# =============================================================================


OMB_VALIDATION_ROOT = Path(
    r"data\raw\omb\historical_tables\FY2027\validation"
)

IRS_HT2_VALIDATION_ROOT = Path(
    r"data\raw\irs\historic_table_2\validation"
)

BEA_CORPORATE_VALIDATION_ROOT = Path(
    r"data\raw\bea\corporate_incidence\validation"
)

IRS_GROSS_VALIDATION_ROOT = Path(
    r"data\raw\irs\gross_collections\validation"
)


# G
INDIVIDUAL_DIR = (
    IRS_HT2_VALIDATION_ROOT
    / "washington_individual_income_tax_receipts_v0_1"
)

INDIVIDUAL_FILE = (
    INDIVIDUAL_DIR
    / "washington_individual_income_tax_receipts.csv"
)

INDIVIDUAL_CERT = (
    INDIVIDUAL_DIR
    / "certification.json"
)


# H
CORPORATE_DIR = (
    BEA_CORPORATE_VALIDATION_ROOT
    / "washington_corporate_income_tax_receipts_v0_1"
)

CORPORATE_FILE = (
    CORPORATE_DIR
    / "washington_corporate_income_tax_receipts.csv"
)

CORPORATE_CERT = (
    CORPORATE_DIR
    / "certification.json"
)


# F-3
SOCIAL_DIR = (
    OMB_VALIDATION_ROOT
    / "washington_social_insurance_receipts_v0_1"
)

SOCIAL_FILE = (
    SOCIAL_DIR
    / "washington_social_insurance_receipts.csv"
)

SOCIAL_CERT = (
    SOCIAL_DIR
    / "certification.json"
)


# J-1
J1_DIR = (
    OMB_VALIDATION_ROOT
    / "washington_irs_table5_remaining_receipts_v0_1"
)

J1_FILE = (
    J1_DIR
    / "washington_irs_table5_receipts_allocation.csv"
)

J1_CERT = (
    J1_DIR
    / "certification.json"
)


# J-2
J2_DIR = (
    OMB_VALIDATION_ROOT
    / "washington_population_receipts_v0_1"
)

J2_FILE = (
    J2_DIR
    / "washington_population_receipts_allocation.csv"
)

J2_CERT = (
    J2_DIR
    / "certification.json"
)


# J-3
J3_DIR = (
    OMB_VALIDATION_ROOT
    / "washington_specialized_receipts_v0_1"
)

J3_FILE = (
    J3_DIR
    / "washington_specialized_receipts_allocation.csv"
)

J3_CERT = (
    J3_DIR
    / "certification.json"
)


# J-4B
J4B_DIR = (
    OMB_VALIDATION_ROOT
    / "washington_ui_receipts_v0_1"
)

J4B_FILE = (
    J4B_DIR
    / "washington_ui_receipts_allocation.csv"
)

J4B_CERT = (
    J4B_DIR
    / "certification.json"
)


# J-4C
J4C_DIR = (
    OMB_VALIDATION_ROOT
    / "health_insurance_provider_receipts_disposition_v0_1"
)

J4C_FILE = (
    J4C_DIR
    / "health_insurance_provider_disposition.csv"
)

J4C_QUEUE = (
    J4C_DIR
    / "remaining_receipts_work_queue_after_j4c.csv"
)

J4C_CERT = (
    J4C_DIR
    / "certification.json"
)


# OMB complete national universe
UNIVERSE_DIR = (
    OMB_VALIDATION_ROOT
    / "federal_receipts_universe_v0_1"
)

UNIVERSE_FILE = (
    UNIVERSE_DIR
    / "national_federal_receipts_universe.csv"
)

UNIVERSE_CERT = (
    UNIVERSE_DIR
    / "certification.json"
)


# ETL-171 certified IRS gross-collections benchmark
IRS_GROSS_SEMANTIC_DIR = (
    IRS_GROSS_VALIDATION_ROOT
    / "semantic_certification_v0_1"
)

IRS_GROSS_FILE = (
    IRS_GROSS_SEMANTIC_DIR
    / "washington_semantic_extract.csv"
)

IRS_GROSS_CERT_REPORT = (
    IRS_GROSS_SEMANTIC_DIR
    / "certification_report.txt"
)


OUTPUT_DIR = (
    OMB_VALIDATION_ROOT
    / "washington_federal_receipts_reconstruction_v0_1"
)


# =============================================================================
# Helpers
# =============================================================================


def parse_float(value: str | None) -> float:
    if value is None:
        return 0.0

    text = str(value).strip()

    if text == "":
        return 0.0

    return float(text.replace(",", ""))


def read_csv_rows(
    path: Path,
) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def write_csv(
    path: Path,
    rows: list[dict],
    fieldnames: list[str],
) -> None:
    with path.open(
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


def load_json(
    path: Path,
) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def certification_pass(
    path: Path,
) -> bool:
    """
    Validate an upstream JSON certification using the certification
    conventions actually present in the WCFFBP ETL artifacts.

    Supported native result fields:
        result
        overall_status

    A certification passes only when one of those explicit top-level
    fields exists and has the value PASS.

    Nested PASS values are deliberately not searched because their
    presence does not establish the overall certification result.
    """

    obj = load_json(path)

    recognized_fields = (
        "result",
        "overall_status",
    )

    present_fields = [
        field
        for field in recognized_fields
        if field in obj
    ]

    if not present_fields:
        raise RuntimeError(
            "Certification JSON contains neither "
            "'result' nor 'overall_status': "
            f"{path}"
        )

    statuses = {
        field: str(obj[field]).strip().upper()
        for field in present_fields
    }

    # If an artifact ever contains both conventions, require them
    # to agree rather than silently choosing one.
    if len(set(statuses.values())) > 1:
        raise RuntimeError(
            "Conflicting top-level certification statuses "
            f"in {path}: {statuses}"
        )

    return all(
        status == "PASS"
        for status in statuses.values()
    )

def certification_report_pass(
    path: Path,
) -> bool:
    """
    Validate ETL-171C using its native certification contract.

    ETL-171C predates the certification.json convention and records
    its authoritative result in certification_report.txt as:

        FINAL RESULT: PASS

    This check certifies only that J-5 is consuming an ETL-171C
    artifact whose own certification completed successfully. It does
    not expand ETL-171C's stated certification scope.
    """

    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(
        encoding="utf-8-sig",
    )

    normalized_lines = [
        " ".join(line.upper().split())
        for line in text.splitlines()
    ]

    if "FINAL RESULT: PASS" in normalized_lines:
        return True

    raise RuntimeError(
        "ETL-171C certification report exists, "
        "but its native certification marker "
        "'FINAL RESULT: PASS' was not found. "
        f"Inspect: {path}"
    )

def pass_fail(
    condition: bool,
) -> str:
    return "PASS" if condition else "FAIL"


def require_years(
    values: dict[int, object],
    label: str,
) -> None:
    actual = set(values)
    expected = set(YEARS)

    if actual != expected:
        raise RuntimeError(
            f"{label} year coverage mismatch. "
            f"Expected {sorted(expected)}; "
            f"found {sorted(actual)}"
        )


def normalized_component(
    value: str,
) -> str:
    return (
        str(value)
        .strip()
        .upper()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


# =============================================================================
# Component ledger
# =============================================================================


component_rows: list[dict] = []


def add_component(
    *,
    fiscal_year: int,
    component_code: str,
    component_group: str,
    national_control_dollars: float,
    washington_receipts_dollars: float,
    source_stage: str,
    accounting_treatment: str,
    allocator_description: str,
) -> None:
    component_rows.append(
        {
            "fiscal_year":
                fiscal_year,

            "component_code":
                component_code,

            "component_group":
                component_group,

            "national_control_dollars":
                national_control_dollars,

            "national_control_millions":
                national_control_dollars
                / 1_000_000.0,

            "washington_receipts_dollars":
                washington_receipts_dollars,

            "washington_receipts_millions":
                washington_receipts_dollars
                / 1_000_000.0,

            "source_stage":
                source_stage,

            "accounting_treatment":
                accounting_treatment,

            "allocator_description":
                allocator_description,
        }
    )


# =============================================================================
# G - individual income
# =============================================================================


def load_individual() -> None:
    rows = read_csv_rows(
        INDIVIDUAL_FILE
    )

    seen: set[int] = set()

    for row in rows:
        fy = int(row["fiscal_year"])

        if fy not in YEARS:
            continue

        if fy in seen:
            raise RuntimeError(
                f"Duplicate individual-income year {fy}"
            )

        seen.add(fy)

        national = parse_float(
            row["national_receipts_dollars"]
        )

        wa = parse_float(
            row["washington_receipts_dollars"]
        )

        add_component(
            fiscal_year=fy,
            component_code=
                "INDIVIDUAL_INCOME_TAX",
            component_group=
                "INDIVIDUAL_INCOME_TAX",
            national_control_dollars=
                national,
            washington_receipts_dollars=
                wa,
            source_stage=
                "ETL-172G",
            accounting_treatment=
                "ALLOCATED_CERTIFIED",
            allocator_description=
                (
                    "IRS SOI individual-income "
                    "tax-liability share"
                ),
        )

    if seen != set(YEARS):
        raise RuntimeError(
            "Individual-income year coverage "
            f"mismatch: {sorted(seen)}"
        )


# =============================================================================
# H - corporate income
# =============================================================================


def load_corporate() -> None:
    rows = read_csv_rows(
        CORPORATE_FILE
    )

    seen: set[int] = set()

    for row in rows:
        fy = int(row["fiscal_year"])

        if fy not in YEARS:
            continue

        if fy in seen:
            raise RuntimeError(
                f"Duplicate corporate-income year {fy}"
            )

        seen.add(fy)

        national = parse_float(
            row[
                "national_corporate_income_tax_receipts_dollars"
            ]
        )

        wa = parse_float(
            row[
                "washington_corporate_income_tax_receipts_dollars"
            ]
        )

        add_component(
            fiscal_year=fy,
            component_code=
                "CORPORATE_INCOME_TAX",
            component_group=
                "CORPORATE_INCOME_TAX",
            national_control_dollars=
                national,
            washington_receipts_dollars=
                wa,
            source_stage=
                "ETL-172H",
            accounting_treatment=
                "ALLOCATED_CERTIFIED",
            allocator_description=
                (
                    "Rockefeller-style 75% capital / "
                    "25% labor BEA incidence allocator"
                ),
        )

    if seen != set(YEARS):
        raise RuntimeError(
            "Corporate-income year coverage "
            f"mismatch: {sorted(seen)}"
        )


# =============================================================================
# F-3 - OASI, DI, HI
# =============================================================================


def load_social() -> None:
    rows = read_csv_rows(
        SOCIAL_FILE
    )

    count_by_year: dict[int, int] = defaultdict(int)

    mapping = {
        "OASI":
            "OASI",

        "DI":
            "DI",

        "HI":
            "MEDICARE_HI",

        "MEDICARE_HI":
            "MEDICARE_HI",
    }

    for row in rows:
        fy = int(row["fiscal_year"])

        if fy not in YEARS:
            continue

        raw_series = normalized_component(
            row["receipt_series"]
        )

        if raw_series not in mapping:
            raise RuntimeError(
                "Unexpected certified social "
                f"receipt_series: {raw_series}"
            )

        component = mapping[
            raw_series
        ]

        national = parse_float(
            row["national_receipts_dollars"]
        )

        wa = parse_float(
            row["washington_receipts_dollars"]
        )

        add_component(
            fiscal_year=fy,
            component_code=
                component,
            component_group=
                "SOCIAL_INSURANCE",
            national_control_dollars=
                national,
            washington_receipts_dollars=
                wa,
            source_stage=
                "ETL-172F-3",
            accounting_treatment=
                "ALLOCATED_CERTIFIED",
            allocator_description=
                (
                    "SSA covered-worker "
                    "contribution share"
                ),
        )

        count_by_year[fy] += 1

    require_years(
        count_by_year,
        "Social insurance",
    )

    if not all(
        count_by_year[fy] == 3
        for fy in YEARS
    ):
        raise RuntimeError(
            "Expected exactly three certified "
            "social components per fiscal year."
        )


# =============================================================================
# J-1 - Railroad + Estate/Gift
# =============================================================================


def load_j1() -> None:
    rows = read_csv_rows(
        J1_FILE
    )

    count_by_year: dict[int, int] = defaultdict(int)

    for row in rows:
        fy = int(row["fiscal_year"])

        if fy not in YEARS:
            continue

        category = normalized_component(
            row["receipt_category"]
        )

        national = (
            parse_float(
                row["national_control_dollars"]
            )
        )

        wa = parse_float(
            row[
                "washington_allocated_receipts_dollars"
            ]
        )

        add_component(
            fiscal_year=fy,
            component_code=
                category,
            component_group=
                "OTHER_SOCIAL_OR_OTHER_RECEIPTS",
            national_control_dollars=
                national,
            washington_receipts_dollars=
                wa,
            source_stage=
                "ETL-172J-1",
            accounting_treatment=
                "ALLOCATED_CERTIFIED",
            allocator_description=
                "IRS Gross Collections Table 5",
        )

        count_by_year[fy] += 1

    require_years(
        count_by_year,
        "J-1",
    )

    if not all(
        count_by_year[fy] == 2
        for fy in YEARS
    ):
        raise RuntimeError(
            "Expected exactly two J-1 "
            "components per fiscal year."
        )


# =============================================================================
# J-2 - population allocated components
# =============================================================================


def load_j2() -> None:
    rows = read_csv_rows(
        J2_FILE
    )

    count_by_year: dict[int, int] = defaultdict(int)

    for row in rows:
        fy = int(row["fiscal_year"])

        if fy not in YEARS:
            continue

        component = normalized_component(
            row["component_code"]
        )

        national = parse_float(
            row["national_control_dollars"]
        )

        wa = parse_float(
            row["washington_allocated_dollars"]
        )

        add_component(
            fiscal_year=fy,
            component_code=
                component,
            component_group=
                "POPULATION_ALLOCATED_RECEIPTS",
            national_control_dollars=
                national,
            washington_receipts_dollars=
                wa,
            source_stage=
                "ETL-172J-2",
            accounting_treatment=
                "ALLOCATED_CERTIFIED",
            allocator_description=
                "Census resident-population share",
        )

        count_by_year[fy] += 1

    require_years(
        count_by_year,
        "J-2",
    )

    if not all(
        count_by_year[fy] == 4
        for fy in YEARS
    ):
        raise RuntimeError(
            "Expected exactly four J-2 "
            "components per fiscal year."
        )


# =============================================================================
# J-3 - FHWA + NIAAA
# =============================================================================


def load_j3() -> None:
    rows = read_csv_rows(
        J3_FILE
    )

    count_by_year: dict[int, int] = defaultdict(int)

    for row in rows:
        fy = int(row["fiscal_year"])

        if fy not in YEARS:
            continue

        component = normalized_component(
            row["component_code"]
        )

        national = parse_float(
            row["national_control_dollars"]
        )

        wa = parse_float(
            row["washington_allocated_dollars"]
        )

        allocator = (
            row.get(
                "allocator_source",
                "",
            )
            .strip()
        )

        add_component(
            fiscal_year=fy,
            component_code=
                component,
            component_group=
                "SPECIALIZED_EXCISE",
            national_control_dollars=
                national,
            washington_receipts_dollars=
                wa,
            source_stage=
                "ETL-172J-3",
            accounting_treatment=
                "ALLOCATED_CERTIFIED",
            allocator_description=
                allocator,
        )

        count_by_year[fy] += 1

    require_years(
        count_by_year,
        "J-3",
    )

    if not all(
        count_by_year[fy] == 2
        for fy in YEARS
    ):
        raise RuntimeError(
            "Expected exactly two J-3 "
            "components per fiscal year."
        )


# =============================================================================
# J-4B - unemployment insurance
# =============================================================================


def load_j4b() -> None:
    rows = read_csv_rows(
        J4B_FILE
    )

    seen: set[int] = set()

    for row in rows:
        fy = int(row["fiscal_year"])

        if fy not in YEARS:
            continue

        if fy in seen:
            raise RuntimeError(
                f"Duplicate J-4B year {fy}"
            )

        seen.add(fy)

        national = parse_float(
            row["national_control_dollars"]
        )

        wa = parse_float(
            row["washington_receipts_dollars"]
        )

        add_component(
            fiscal_year=fy,
            component_code=
                "UNEMPLOYMENT_INSURANCE",
            component_group=
                "SOCIAL_INSURANCE",
            national_control_dollars=
                national,
            washington_receipts_dollars=
                wa,
            source_stage=
                "ETL-172J-4B",
            accounting_treatment=
                "ALLOCATED_CERTIFIED",
            allocator_description=
                (
                    "DOL ETA-2112 c10; "
                    "50 states + DC denominator"
                ),
        )

    if seen != set(YEARS):
        raise RuntimeError(
            "J-4B year coverage mismatch: "
            f"{sorted(seen)}"
        )


# =============================================================================
# J-4C - HIP withheld
# =============================================================================


def load_j4c_hip() -> None:
    rows = read_csv_rows(
        J4C_FILE
    )

    seen: set[int] = set()

    for row in rows:
        fy = int(row["fiscal_year"])

        if fy not in YEARS:
            continue

        if fy in seen:
            raise RuntimeError(
                f"Duplicate HIP year {fy}"
            )

        seen.add(fy)

        national_millions = parse_float(
            row["national_control_millions"]
        )

        national = (
            national_millions
            * 1_000_000.0
        )

        disposition = (
            row["wcffbp_disposition"]
            .strip()
        )

        if national_millions == 0:
            treatment = (
                "ZERO_NATIONAL_CONTROL"
            )
        else:
            treatment = disposition

        add_component(
            fiscal_year=fy,
            component_code=
                "HEALTH_INSURANCE_PROVIDERS",
            component_group=
                "EXCISE",
            national_control_dollars=
                national,
            washington_receipts_dollars=
                0.0,
            source_stage=
                "ETL-172J-4C",
            accounting_treatment=
                treatment,
            allocator_description=
                (
                    "Rockefeller Oliver Wyman "
                    "allocator not independently "
                    "certified for principal ledger"
                ),
        )

    if seen != set(YEARS):
        raise RuntimeError(
            "HIP year coverage mismatch: "
            f"{sorted(seen)}"
        )


# =============================================================================
# OMB universe
# =============================================================================


def load_universe() -> dict[int, dict]:
    rows = read_csv_rows(
        UNIVERSE_FILE
    )

    result: dict[int, dict] = {}

    for row in rows:
        fy = int(row["fiscal_year"])

        if fy not in YEARS:
            continue

        result[fy] = {
            "total_receipts_dollars":
                parse_float(
                    row[
                        "total_receipts_dollars"
                    ]
                ),

            "total_receipts_millions":
                parse_float(
                    row[
                        "total_receipts_millions"
                    ]
                ),
        }

    require_years(
        result,
        "OMB receipts universe",
    )

    return result


# =============================================================================
# J-4C final disposition queue
# =============================================================================


def load_final_queue() -> dict[int, dict]:
    rows = read_csv_rows(
        J4C_QUEUE
    )

    result: dict[int, dict] = {}

    for row in rows:
        fy = int(row["fiscal_year"])

        if fy not in YEARS:
            continue

        result[fy] = {
            "actionable":
                parse_float(
                    row[
                        "actionable_unfinished_after_j4c_millions"
                    ]
                ),

            "documented":
                parse_float(
                    row[
                        "allocator_method_documented_millions_after_j4c"
                    ]
                ),

            "method_review":
                parse_float(
                    row[
                        "method_change_review_millions_after_j4c"
                    ]
                ),

            "withheld":
                parse_float(
                    row[
                        "withhold_unresolved_millions_after_j4c"
                    ]
                ),

            "unallocable":
                parse_float(
                    row[
                        "intentionally_unallocable_millions"
                    ]
                ),
        }

    require_years(
        result,
        "J-4C final queue",
    )

    return result


# =============================================================================
# ETL-171 IRS gross-collections diagnostic
# =============================================================================


def load_irs_gross() -> dict[int, float]:
    rows = read_csv_rows(
        IRS_GROSS_FILE
    )

    if not rows:
        raise RuntimeError(
            "ETL-171 semantic extract is empty."
        )

    # ETL-171C's certified semantic extract has evolved during development.
    # Identify the fiscal-year and total-collections fields conservatively.

    columns = set(rows[0])

    fy_candidates = [
        "fiscal_year",
        "year",
        "ffy",
    ]

    total_candidates = [
        "total_internal_revenue_collections_thousands",
        "total_internal_revenue_collections",
        "total_collections_thousands",
        "total_collections",
        "washington_total_collections_thousands",
        "washington_total_internal_revenue_collections_thousands",
    ]

    fy_col = next(
        (
            x
            for x in fy_candidates
            if x in columns
        ),
        None,
    )

    total_col = next(
        (
            x
            for x in total_candidates
            if x in columns
        ),
        None,
    )

    if fy_col is None:
        raise RuntimeError(
            "Could not identify fiscal-year "
            "column in ETL-171 semantic extract. "
            f"Columns: {sorted(columns)}"
        )

    if total_col is None:
        raise RuntimeError(
            "Could not identify total IRS "
            "collections column in ETL-171 "
            "semantic extract. "
            f"Columns: {sorted(columns)}"
        )

    result: dict[int, float] = {}

    for row in rows:
        fy = int(row[fy_col])

        if fy not in YEARS:
            continue

        raw = parse_float(
            row[total_col]
        )

        # ETL-171 Table 5 source values are in thousands.
        # If the selected field explicitly says thousands,
        # convert to dollars. Otherwise preserve the stored value.
        if "thousand" in total_col.lower():
            dollars = raw * 1_000.0
        else:
            dollars = raw

        result[fy] = dollars

    require_years(
        result,
        "ETL-171 IRS gross collections",
    )

    return result


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -------------------------------------------------------------------------
    # Upstream certifications
    # -------------------------------------------------------------------------

    certification_paths = {
        "individual_income":
            INDIVIDUAL_CERT,

        "corporate_income":
            CORPORATE_CERT,

        "social_insurance":
            SOCIAL_CERT,

        "j1_irs_table5":
            J1_CERT,

        "j2_population":
            J2_CERT,

        "j3_specialized":
            J3_CERT,

        "j4b_ui":
            J4B_CERT,

        "j4c_hip":
            J4C_CERT,

        "omb_receipts_universe":
            UNIVERSE_CERT,
    }

    upstream_checks: dict[str, bool] = {}

    for name, path in certification_paths.items():
        upstream_checks[
            f"upstream_{name}_certification"
        ] = certification_pass(path)

    # ETL-171C predates the certification.json convention.
    # Its authoritative certification artifact is the preserved
    # certification_report.txt.
    upstream_checks[
        "upstream_irs_gross_collections_certification"
    ] = certification_report_pass(
        IRS_GROSS_CERT_REPORT
    )

    # -------------------------------------------------------------------------
    # Load certified components
    # -------------------------------------------------------------------------

    load_individual()
    load_corporate()
    load_social()
    load_j1()
    load_j2()
    load_j3()
    load_j4b()
    load_j4c_hip()

    universe = load_universe()
    final_queue = load_final_queue()
    irs_gross = load_irs_gross()

    # -------------------------------------------------------------------------
    # Component uniqueness
    # -------------------------------------------------------------------------

    component_keys: set[
        tuple[int, str]
    ] = set()

    duplicate_component_key = False

    for row in component_rows:
        key = (
            int(row["fiscal_year"]),
            str(row["component_code"]),
        )

        if key in component_keys:
            duplicate_component_key = True

        component_keys.add(key)

    # -------------------------------------------------------------------------
    # Aggregate
    # -------------------------------------------------------------------------

    allocated_national: dict[int, float] = defaultdict(float)
    wa_reconstructed: dict[int, float] = defaultdict(float)
    withheld_from_components: dict[int, float] = defaultdict(float)

    for row in component_rows:
        fy = int(
            row["fiscal_year"]
        )

        treatment = str(
            row["accounting_treatment"]
        )

        national = float(
            row["national_control_dollars"]
        )

        wa = float(
            row["washington_receipts_dollars"]
        )

        if treatment == "ALLOCATED_CERTIFIED":
            allocated_national[fy] += national
            wa_reconstructed[fy] += wa

        elif treatment == "WITHHOLD_UNRESOLVED":
            withheld_from_components[fy] += national

        elif treatment == "ZERO_NATIONAL_CONTROL":
            if abs(national) > TOLERANCE_DOLLARS:
                raise RuntimeError(
                    "ZERO_NATIONAL_CONTROL component "
                    f"has nonzero control in {fy}."
                )

        else:
            raise RuntimeError(
                "Unexpected accounting treatment: "
                f"{treatment}"
            )

    # -------------------------------------------------------------------------
    # National disposition identity and final reconstruction
    # -------------------------------------------------------------------------

    reconstruction_rows: list[dict] = []

    national_identity_ok = True
    queue_zero_ok = True
    withheld_identity_ok = True
    wa_component_sum_ok = True

    for fy in YEARS:
        total = universe[fy][
            "total_receipts_dollars"
        ]

        allocated = allocated_national[fy]

        withheld_queue = (
            final_queue[fy]["withheld"]
            * 1_000_000.0
        )

        unallocable = (
            final_queue[fy]["unallocable"]
            * 1_000_000.0
        )

        actionable = (
            final_queue[fy]["actionable"]
        )

        documented = (
            final_queue[fy]["documented"]
        )

        method_review = (
            final_queue[fy]["method_review"]
        )

        if any(
            abs(x) > TOLERANCE_MILLIONS
            for x in (
                actionable,
                documented,
                method_review,
            )
        ):
            queue_zero_ok = False

        if abs(
            withheld_from_components[fy]
            - withheld_queue
        ) > 10.0:
            withheld_identity_ok = False

        disposition_sum = (
            allocated
            + withheld_queue
            + unallocable
        )

        national_difference = (
            total
            - disposition_sum
        )

        if abs(
            national_difference
        ) > 10.0:
            national_identity_ok = False

        wa = wa_reconstructed[fy]

        # Independent component re-sum.
        wa_check = sum(
            float(
                row[
                    "washington_receipts_dollars"
                ]
            )
            for row in component_rows
            if (
                int(row["fiscal_year"])
                == fy
                and row[
                    "accounting_treatment"
                ]
                == "ALLOCATED_CERTIFIED"
            )
        )

        if abs(
            wa - wa_check
        ) > TOLERANCE_DOLLARS:
            wa_component_sum_ok = False

        irs = irs_gross[fy]

        diagnostic_difference = (
            wa - irs
        )

        diagnostic_pct_of_irs = (
            diagnostic_difference
            / irs
            * 100.0
            if irs != 0
            else None
        )

        national_allocated_pct = (
            allocated / total * 100.0
            if total != 0
            else None
        )

        national_withheld_pct = (
            withheld_queue / total * 100.0
            if total != 0
            else None
        )

        national_unallocable_pct = (
            unallocable / total * 100.0
            if total != 0
            else None
        )

        reconstruction_rows.append(
            {
                "fiscal_year":
                    fy,

                "omb_total_federal_receipts_dollars":
                    total,

                "national_controls_allocated_by_certified_methods_dollars":
                    allocated,

                "national_withheld_unresolved_dollars":
                    withheld_queue,

                "national_intentionally_unallocable_dollars":
                    unallocable,

                "national_disposition_sum_dollars":
                    disposition_sum,

                "national_identity_difference_dollars":
                    national_difference,

                "national_allocated_percent":
                    national_allocated_pct,

                "national_withheld_percent":
                    national_withheld_pct,

                "national_intentionally_unallocable_percent":
                    national_unallocable_pct,

                "washington_reconstructed_federal_receipts_dollars":
                    wa,

                "washington_reconstructed_federal_receipts_billions":
                    wa / 1_000_000_000.0,

                "irs_washington_gross_collections_benchmark_dollars":
                    irs,

                "irs_washington_gross_collections_benchmark_billions":
                    irs / 1_000_000_000.0,

                "reconstruction_minus_irs_dollars":
                    diagnostic_difference,

                "reconstruction_minus_irs_billions":
                    diagnostic_difference
                    / 1_000_000_000.0,

                "reconstruction_minus_irs_percent_of_irs":
                    diagnostic_pct_of_irs,

                "irs_comparison_status":
                    "DIAGNOSTIC_ONLY_NO_FORCED_RECONCILIATION",
            }
        )

    # -------------------------------------------------------------------------
    # Certification
    # -------------------------------------------------------------------------

    checks = {
        **upstream_checks,

        "component_keys_unique":
            not duplicate_component_key,

        "study_year_component_coverage":
            set(
                int(row["fiscal_year"])
                for row in component_rows
            )
            == set(YEARS),

        "post_j4c_actionable_documented_method_review_queues_zero":
            queue_zero_ok,

        "withheld_component_matches_final_queue":
            withheld_identity_ok,

        "national_receipts_disposition_identity":
            national_identity_ok,

        "washington_component_sum_identity":
            wa_component_sum_ok,

        "irs_comparison_diagnostic_only":
            True,

        "irs_forced_reconciliation_boundary":
            True,

        "database_write_boundary":
            True,

        "final_fiscal_balance_ledger_boundary":
            True,
    }

    overall_status = (
        "PASS"
        if all(checks.values())
        else "REVIEW"
    )

    # -------------------------------------------------------------------------
    # Write component ledger
    # -------------------------------------------------------------------------

    component_rows.sort(
        key=lambda x: (
            int(x["fiscal_year"]),
            str(x["component_group"]),
            str(x["component_code"]),
        )
    )

    write_csv(
        OUTPUT_DIR
        / "washington_federal_receipts_components.csv",
        component_rows,
        [
            "fiscal_year",
            "component_code",
            "component_group",
            "national_control_dollars",
            "national_control_millions",
            "washington_receipts_dollars",
            "washington_receipts_millions",
            "source_stage",
            "accounting_treatment",
            "allocator_description",
        ],
    )

    write_csv(
        OUTPUT_DIR
        / "washington_federal_receipts_reconstruction.csv",
        reconstruction_rows,
        [
            "fiscal_year",
            "omb_total_federal_receipts_dollars",
            "national_controls_allocated_by_certified_methods_dollars",
            "national_withheld_unresolved_dollars",
            "national_intentionally_unallocable_dollars",
            "national_disposition_sum_dollars",
            "national_identity_difference_dollars",
            "national_allocated_percent",
            "national_withheld_percent",
            "national_intentionally_unallocable_percent",
            "washington_reconstructed_federal_receipts_dollars",
            "washington_reconstructed_federal_receipts_billions",
            "irs_washington_gross_collections_benchmark_dollars",
            "irs_washington_gross_collections_benchmark_billions",
            "reconstruction_minus_irs_dollars",
            "reconstruction_minus_irs_billions",
            "reconstruction_minus_irs_percent_of_irs",
            "irs_comparison_status",
        ],
    )

    certification = {
        "etl_stage":
            "ETL-172J-5",

        "title":
            "Washington Federal Receipts Final Reconstruction v0.1",

        "overall_status":
            overall_status,

        "study_period":
            {
                "first_fiscal_year":
                    STUDY_FY_START,

                "last_fiscal_year":
                    STUDY_FY_END,
            },

        "accounting_architecture":
            {
                "national_control":
                    (
                        "OMB Historical Tables complete "
                        "federal receipts universe"
                    ),

                "washington_reconstruction":
                    (
                        "Sum of independently certified "
                        "Washington component allocations"
                    ),

                "withheld_treatment":
                    (
                        "National control preserved; "
                        "no Washington amount imputed"
                    ),

                "intentionally_unallocable_treatment":
                    (
                        "National control preserved outside "
                        "Washington allocated numerator"
                    ),

                "irs_gross_collections":
                    (
                        "Independent administrative benchmark; "
                        "diagnostic comparison only"
                    ),
            },

        "checks": {
            key: pass_fail(value)
            for key, value in checks.items()
        },

        "boundaries": [
            (
                "No new state-allocation methodology "
                "introduced in ETL-172J-5."
            ),
            (
                "Health Insurance Providers remains "
                "WITHHOLD_UNRESOLVED where the national "
                "control is nonzero."
            ),
            (
                "Customs duties and fees, Federal Reserve "
                "deposits, and miscellaneous all-other "
                "receipts remain intentionally unallocable "
                "under the certified methodology crosswalk."
            ),
            (
                "ETL-171 IRS gross collections are "
                "diagnostic only and are not forced to "
                "reconcile with the economic-incidence "
                "reconstruction."
            ),
            "No PostgreSQL writes.",
            (
                "No final taxes-out minus spending-in "
                "balance is authorized by this stage."
            ),
        ],
    }

    with (
        OUTPUT_DIR
        / "certification.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            certification,
            f,
            indent=2,
        )

    # -------------------------------------------------------------------------
    # Console report
    # -------------------------------------------------------------------------

    lines = [
        "=" * 122,
        "ETL-172J-5 WASHINGTON FEDERAL RECEIPTS FINAL RECONSTRUCTION v0.1",
        "=" * 122,
        "",
        f"Overall status : {overall_status}",
        "",
        "CERTIFICATION CHECKS",
        "-" * 122,
    ]

    for key, value in checks.items():
        lines.append(
            f"{key:<88} "
            f"{pass_fail(value)}"
        )

    lines.extend(
        [
            "",
            "WASHINGTON FEDERAL RECEIPTS RECONSTRUCTION",
            "-" * 122,
            (
                "FFY   OMB TOTAL     NATIONAL ALLOCATED   "
                "WITHHELD   UNALLOCABLE   "
                "WA RECONSTRUCTED   IRS GROSS    "
                "RECON - IRS"
            ),
            "-" * 122,
        ]
    )

    for row in reconstruction_rows:
        lines.append(
            f"{row['fiscal_year']}   "
            f"${row['omb_total_federal_receipts_dollars'] / 1e12:>6.3f}T   "
            f"${row['national_controls_allocated_by_certified_methods_dollars'] / 1e12:>6.3f}T          "
            f"${row['national_withheld_unresolved_dollars'] / 1e9:>6.1f}B   "
            f"${row['national_intentionally_unallocable_dollars'] / 1e9:>7.1f}B   "
            f"${row['washington_reconstructed_federal_receipts_billions']:>8.3f}B   "
            f"${row['irs_washington_gross_collections_benchmark_billions']:>7.3f}B   "
            f"${row['reconstruction_minus_irs_billions']:>+8.3f}B"
        )

    lines.extend(
        [
            "",
            "IRS DIAGNOSTIC DIFFERENCE",
            "-" * 122,
            (
                "FFY   WA RECONSTRUCTED   IRS GROSS   "
                "DIFFERENCE   DIFFERENCE / IRS"
            ),
            "-" * 122,
        ]
    )

    for row in reconstruction_rows:
        lines.append(
            f"{row['fiscal_year']}   "
            f"${row['washington_reconstructed_federal_receipts_billions']:>8.3f}B   "
            f"${row['irs_washington_gross_collections_benchmark_billions']:>8.3f}B   "
            f"${row['reconstruction_minus_irs_billions']:>+8.3f}B   "
            f"{row['reconstruction_minus_irs_percent_of_irs']:>+8.2f}%"
        )

    lines.extend(
        [
            "",
            "INTERPRETATION BOUNDARIES",
            "-" * 122,
            (
                "WA reconstructed receipts are an "
                "economic-incidence reconstruction from "
                "certified national controls and allocators."
            ),
            (
                "IRS gross collections are an independent "
                "administrative collection benchmark."
            ),
            (
                "A difference between the two is diagnostic "
                "information, not a certification failure."
            ),
            (
                "WITHHOLD_UNRESOLVED and intentionally "
                "unallocable national receipts are not "
                "silently assigned to Washington."
            ),
            "No PostgreSQL writes.",
            (
                "No final statewide fiscal-balance "
                "calculation is authorized by this stage."
            ),
            "",
        ]
    )

    report = "\n".join(lines)

    (
        OUTPUT_DIR
        / "certification_report.txt"
    ).write_text(
        report,
        encoding="utf-8",
    )

    print(report)


if __name__ == "__main__":
    main()