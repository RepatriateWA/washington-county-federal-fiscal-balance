"""
Validate CY2022 CMS Medicare Advantage source files for Washington State.

Sources
-------
CPSC Enrollment:
    Contract Number + Plan ID + county + enrollment

CPSC Contract Info:
    Contract ID + Plan ID + Plan Type + SNP Plan + EGHP

SCP:
    State/county/plan-type aggregate enrollment controls

SNP Comprehensive Report:
    Contract Number + Plan ID + SNP subtype + plan enrollment

Purpose
-------
Validate whether all 12 months of CY2022 support the Washington
Medicare Advantage enrollment and suppression-reconciliation
architecture required for later payment reconstruction.

This script is READ-ONLY.

It does NOT:
* write to PostgreSQL;
* modify source artifacts;
* estimate Medicare Advantage payments;
* convert suppressed enrollment to zero;
* certify final Medicare expenditures.

Important source rules
----------------------
1. CPSC enrollment does not contain Plan Type. Plan Type must be
   obtained from CPSC Contract Info using Contract + Plan.
2. SNP status is obtained from CPSC Contract Info.
3. Only SNP plans are expected to resolve against the SNP report.
4. Employer-group plans may be absent from the SNP report because
   CMS explicitly omits employer-only group plans from that report.
5. SNP "Under-11" records are aggregate privacy records, not real
   contract/plan identities.
"""

from __future__ import annotations

import csv
import io
import re
import sys
import zipfile

from collections import defaultdict
from pathlib import Path

import pandas as pd


# ============================================================================
# CONFIGURATION
# ============================================================================

YEAR = 2022

ROOT = Path(
    r"data\raw\cms\medicare_advantage"
)

CPSC_ROOT = (
    ROOT
    / "enrollment"
    / str(YEAR)
)

SCP_ROOT = (
    ROOT
    / "enrollment_controls"
    / str(YEAR)
)

SNP_ROOT = (
    ROOT
    / "snp"
    / str(YEAR)
)

VALIDATION_DIR = (
    ROOT
    / "validation"
    / str(YEAR)
)

MONTHLY_CSV = (
    VALIDATION_DIR
    / "cms_ma_2022_source_validation_monthly.csv"
)

SUMMARY_TXT = (
    VALIDATION_DIR
    / "cms_ma_2022_source_validation_summary.txt"
)

EXPECTED_WA_COUNTIES = 39

TARGET_PLAN_TYPES = {
    "HMO",
    "HMO/HMOPOS",
    "LOCAL PPO",
}

YES_VALUES = {
    "YES",
    "Y",
    "TRUE",
    "1",
}


# ============================================================================
# NORMALIZATION
# ============================================================================

def clean_text(value) -> str:

    if value is None:
        return ""

    if pd.isna(value):
        return ""

    return str(value).strip()


def norm(value) -> str:

    text = clean_text(
        value
    ).upper()

    return re.sub(
        r"\s+",
        " ",
        text,
    )


def norm_column(value) -> str:

    text = norm(
        value
    )

    text = re.sub(
        r"[^A-Z0-9]+",
        "_",
        text,
    )

    return text.strip("_")


def normalize_plan_id(
    value,
) -> str:

    text = clean_text(
        value
    )

    if not text:
        return ""

    # Excel may render numeric plan IDs
    # as 39.0. Normalize to 039.
    try:

        number = float(
            text
        )

        if number.is_integer():

            return str(
                int(number)
            ).zfill(3)

    except ValueError:
        pass

    return text.zfill(3)


def normalize_contract(
    value,
) -> str:

    return norm(
        value
    )


def numeric_or_none(
    value,
):

    if value is None:
        return None

    if pd.isna(value):
        return None

    text = clean_text(
        value
    )

    if norm(text) in {
        "",
        ".",
        "*",
        "**",
        "***",
        "N/A",
        "NA",
        "NULL",
        "NONE",
        "-",
    }:
        return None

    text = text.replace(
        ",",
        "",
    )

    try:
        return float(
            text
        )

    except ValueError:
        return None


def is_yes(
    value,
) -> bool:

    return norm(
        value
    ) in YES_VALUES


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
    required: bool = True,
) -> str | None:

    lookup = {
        norm_column(c): c
        for c in df.columns
    }

    for candidate in candidates:

        key = norm_column(
            candidate
        )

        if key in lookup:
            return lookup[key]

    if required:

        raise RuntimeError(
            "Required column not found. "
            f"Candidates={candidates}; "
            f"available={list(df.columns)}"
        )

    return None


# ============================================================================
# ARTIFACT DISCOVERY
# ============================================================================

def find_single_artifact(
    month_dir: Path,
    family: str,
) -> Path:

    if not month_dir.exists():

        raise RuntimeError(
            f"Missing directory: {month_dir}"
        )

    candidates = []

    for path in month_dir.iterdir():

        if not path.is_file():
            continue

        lower = path.name.lower()

        if family == "CPSC":

            if (
                "cpsc" in lower
                and lower.endswith(".zip")
            ):
                candidates.append(
                    path
                )

        elif family == "SCP":

            if (
                (
                    "scp" in lower
                    or "statecountyplan" in lower
                )
                and lower.endswith(".zip")
            ):
                candidates.append(
                    path
                )

        elif family == "SNP":

            if (
                "snp" in lower
                and (
                    lower.endswith(".zip")
                    or lower.endswith(".xls")
                    or lower.endswith(".xlsx")
                )
            ):
                candidates.append(
                    path
                )

    if len(candidates) != 1:

        raise RuntimeError(
            f"{family}: expected exactly one artifact "
            f"in {month_dir}; found {len(candidates)}: "
            f"{candidates}"
        )

    return candidates[0]


def zip_members(
    path: Path,
) -> list[str]:

    if not zipfile.is_zipfile(
        path
    ):

        raise RuntimeError(
            f"Invalid ZIP: {path}"
        )

    with zipfile.ZipFile(
        path
    ) as z:

        return [
            name
            for name in z.namelist()
            if not name.endswith("/")
        ]


def find_member(
    members: list[str],
    required_fragments: list[str],
    suffix: str,
    description: str,
) -> str:

    matches = []

    for member in members:

        lower = member.lower()

        if not lower.endswith(
            suffix.lower()
        ):
            continue

        if all(
            fragment.lower() in lower
            for fragment
            in required_fragments
        ):

            matches.append(
                member
            )

    if len(matches) != 1:

        raise RuntimeError(
            f"Expected exactly one {description}; "
            f"found {len(matches)}: {matches}"
        )

    return matches[0]


# ============================================================================
# FILE READERS
# ============================================================================

def read_csv_bytes(
    raw: bytes,
) -> pd.DataFrame:

    errors = []

    for encoding in (
        "cp1252",
        "utf-8-sig",
        "latin1",
    ):

        try:

            return pd.read_csv(
                io.BytesIO(raw),
                dtype=str,
                encoding=encoding,
                low_memory=False,
            )

        except Exception as exc:

            errors.append(
                f"{encoding}: {exc}"
            )

    raise RuntimeError(
        "Could not parse CSV: "
        + " | ".join(errors)
    )


def read_zip_csv(
    zip_path: Path,
    member: str,
) -> pd.DataFrame:

    with zipfile.ZipFile(
        zip_path
    ) as z:

        raw = z.read(
            member
        )

    return read_csv_bytes(
        raw
    )


def read_excel_raw(
    raw: bytes,
    suffix: str,
    header=None,
) -> pd.DataFrame:

    if suffix.lower() == ".xls":

        return pd.read_excel(
            io.BytesIO(raw),
            dtype=str,
            header=header,
            engine="xlrd",
        )

    return pd.read_excel(
        io.BytesIO(raw),
        dtype=str,
        header=header,
        engine="openpyxl",
    )


# ============================================================================
# CPSC
# ============================================================================

def load_cpsc(
    month: int,
):

    artifact = find_single_artifact(
        CPSC_ROOT
        / f"{month:02d}",
        "CPSC",
    )

    members = zip_members(
        artifact
    )

    enrollment_member = find_member(
        members,
        ["enrollment_info"],
        ".csv",
        "CPSC enrollment CSV",
    )

    contract_member = find_member(
        members,
        ["contract_info"],
        ".csv",
        "CPSC contract-info CSV",
    )

    enrollment = read_zip_csv(
        artifact,
        enrollment_member,
    )

    contracts = read_zip_csv(
        artifact,
        contract_member,
    )

    return (
        artifact,
        enrollment_member,
        contract_member,
        enrollment,
        contracts,
    )


def prepare_cpsc(
    month: int,
):

    (
        artifact,
        enrollment_member,
        contract_member,
        enrollment,
        contracts,
    ) = load_cpsc(
        month
    )

    # ----------------------------------------------------------------
    # Enrollment schema
    # ----------------------------------------------------------------

    e_contract = find_column(
        enrollment,
        [
            "Contract Number",
            "Contract ID",
        ],
    )

    e_plan = find_column(
        enrollment,
        [
            "Plan ID",
        ],
    )

    e_state = find_column(
        enrollment,
        [
            "State",
            "State Abbreviation",
        ],
    )

    e_county = find_column(
        enrollment,
        [
            "County",
            "County Name",
        ],
    )

    e_enrollment = find_column(
        enrollment,
        [
            "Enrollment",
        ],
    )

    # ----------------------------------------------------------------
    # Contract-info schema
    # ----------------------------------------------------------------

    c_contract = find_column(
        contracts,
        [
            "Contract ID",
            "Contract Number",
        ],
    )

    c_plan = find_column(
        contracts,
        [
            "Plan ID",
        ],
    )

    c_plan_type = find_column(
        contracts,
        [
            "Plan Type",
        ],
    )

    c_snp = find_column(
        contracts,
        [
            "SNP Plan",
        ],
    )

    c_eghp = find_column(
        contracts,
        [
            "EGHP",
        ],
    )

    # ----------------------------------------------------------------
    # Canonical join keys
    # ----------------------------------------------------------------

    enrollment = enrollment.copy()
    contracts = contracts.copy()

    enrollment[
        "_contract"
    ] = enrollment[
        e_contract
    ].map(
        normalize_contract
    )

    enrollment[
        "_plan"
    ] = enrollment[
        e_plan
    ].map(
        normalize_plan_id
    )

    contracts[
        "_contract"
    ] = contracts[
        c_contract
    ].map(
        normalize_contract
    )

    contracts[
        "_plan"
    ] = contracts[
        c_plan
    ].map(
        normalize_plan_id
    )

    # Contract-info should define each
    # contract-plan identity once.
    contract_key_counts = (
        contracts
        .groupby(
            [
                "_contract",
                "_plan",
            ],
            dropna=False,
        )
        .size()
    )

    duplicate_contract_keys = int(
        (
            contract_key_counts
            > 1
        ).sum()
    )

    contract_subset = contracts[
        [
            "_contract",
            "_plan",
            c_plan_type,
            c_snp,
            c_eghp,
        ]
    ].copy()

    contract_subset = (
        contract_subset
        .drop_duplicates(
            subset=[
                "_contract",
                "_plan",
            ],
            keep=False,
        )
    )

    contract_subset = (
        contract_subset.rename(
            columns={
                c_plan_type: "_plan_type",
                c_snp: "_snp_plan",
                c_eghp: "_eghp",
            }
        )
    )

    # Washington enrollment only.
    wa = enrollment[
        enrollment[
            e_state
        ].map(norm)
        == "WA"
    ].copy()

    if wa.empty:

        raise RuntimeError(
            "CPSC enrollment contains "
            "no Washington rows"
        )

    joined = wa.merge(
        contract_subset,
        how="left",
        on=[
            "_contract",
            "_plan",
        ],
        indicator=True,
        validate="many_to_one",
    )

    unresolved_join_rows = int(
        (
            joined["_merge"]
            != "both"
        ).sum()
    )

    joined[
        "_plan_type_norm"
    ] = joined[
        "_plan_type"
    ].map(
        norm
    )

    joined[
        "_is_snp"
    ] = joined[
        "_snp_plan"
    ].map(
        is_yes
    )

    joined[
        "_is_eghp"
    ] = joined[
        "_eghp"
    ].map(
        is_yes
    )

    joined[
        "_enrollment_numeric"
    ] = joined[
        e_enrollment
    ].map(
        numeric_or_none
    )

    target = joined[
        joined[
            "_plan_type_norm"
        ].isin(
            TARGET_PLAN_TYPES
        )
    ].copy()

    if target.empty:

        raise RuntimeError(
            "No WA HMO/HMOPOS or "
            "Local PPO rows after "
            "contract-info join"
        )

    published = target[
        target[
            "_enrollment_numeric"
        ].notna()
    ].copy()

    suppressed = target[
        target[
            "_enrollment_numeric"
        ].isna()
    ].copy()

    counties = {
        norm(v)
        for v in target[
            e_county
        ]
        if norm(v)
    }

    snp_target = target[
        target["_is_snp"]
    ].copy()

    snp_non_eghp = snp_target[
        ~snp_target[
            "_is_eghp"
        ]
    ].copy()

    snp_eghp = snp_target[
        snp_target[
            "_is_eghp"
        ]
    ].copy()

    return {
        "artifact": str(
            artifact
        ),

        "enrollment_member": (
            enrollment_member
        ),

        "contract_member": (
            contract_member
        ),

        "contract_duplicate_keys": (
            duplicate_contract_keys
        ),

        "wa_rows": len(
            wa
        ),

        "join_unresolved_rows": (
            unresolved_join_rows
        ),

        "target_rows": len(
            target
        ),

        "published_rows": len(
            published
        ),

        "suppressed_rows": len(
            suppressed
        ),

        "published_enrollment": float(
            published[
                "_enrollment_numeric"
            ].sum()
        ),

        "counties": len(
            counties
        ),

        "target": target,

        "snp_non_eghp": (
            snp_non_eghp
        ),

        "snp_eghp": (
            snp_eghp
        ),
    }


# ============================================================================
# SCP
# ============================================================================

def prepare_scp(
    month: int,
):

    artifact = find_single_artifact(
        SCP_ROOT
        / f"{month:02d}",
        "SCP",
    )

    members = zip_members(
        artifact
    )

    csv_members = [
        member
        for member in members
        if member.lower().endswith(
            ".csv"
        )
    ]

    if len(csv_members) != 1:

        raise RuntimeError(
            "Expected exactly one SCP CSV; "
            f"found {len(csv_members)}: "
            f"{csv_members}"
        )

    member = csv_members[0]

    df = read_zip_csv(
        artifact,
        member,
    )

    state_col = find_column(
        df,
        [
            "State",
            "State Abbreviation",
        ],
    )

    county_col = find_column(
        df,
        [
            "County",
            "County Name",
        ],
    )

    plan_type_col = find_column(
        df,
        [
            "Plan Type",
        ],
    )

    enrollment_col = find_column(
        df,
        [
            "Enrolled",
            "Enrollment",
        ],
    )

    wa = df[
        df[
            state_col
        ].map(norm)
        == "WA"
    ].copy()

    if wa.empty:

        raise RuntimeError(
            "SCP contains no "
            "Washington rows"
        )

    wa[
        "_plan_type_norm"
    ] = wa[
        plan_type_col
    ].map(
        norm
    )

    wa[
        "_enrollment_numeric"
    ] = wa[
        enrollment_col
    ].map(
        numeric_or_none
    )

    hmo = wa[
        wa[
            "_plan_type_norm"
        ].isin(
            {
                "HMO",
                "HMO/HMOPOS",
            }
        )
    ].copy()

    ppo = wa[
        wa[
            "_plan_type_norm"
        ]
        == "LOCAL PPO"
    ].copy()

    target = pd.concat(
        [
            hmo,
            ppo,
        ],
        ignore_index=True,
    )

    if target.empty:

        raise RuntimeError(
            "SCP contains no WA "
            "HMO/HMOPOS or Local PPO rows"
        )

    hmo_counties = {
        norm(v)
        for v in hmo[
            county_col
        ]
        if norm(v)
    }

    ppo_counties = {
        norm(v)
        for v in ppo[
            county_col
        ]
        if norm(v)
    }

    combined_counties = (
        hmo_counties
        | ppo_counties
    )

    published = target[
        target[
            "_enrollment_numeric"
        ].notna()
    ]

    suppressed = target[
        target[
            "_enrollment_numeric"
        ].isna()
    ]

    return {
        "artifact": str(
            artifact
        ),

        "member": member,

        "wa_rows": len(
            wa
        ),

        "target_rows": len(
            target
        ),

        "published_rows": len(
            published
        ),

        "suppressed_rows": len(
            suppressed
        ),

        "enrollment": float(
            published[
                "_enrollment_numeric"
            ].sum()
        ),

        "hmo_counties": len(
            hmo_counties
        ),

        "ppo_counties": len(
            ppo_counties
        ),

        "combined_counties": len(
            combined_counties
        ),
    }


# ============================================================================
# SNP REPORT
# ============================================================================

def load_snp_raw(
    artifact: Path,
):

    if artifact.suffix.lower() in {
        ".xls",
        ".xlsx",
    }:

        suffix = artifact.suffix

        raw = artifact.read_bytes()

        return (
            read_excel_raw(
                raw,
                suffix,
                header=None,
            ),
            artifact.name,
        )

    members = zip_members(
        artifact
    )

    workbook_members = [
        member
        for member in members
        if member.lower().endswith(
            (
                ".xls",
                ".xlsx",
            )
        )
    ]

    if len(workbook_members) != 1:

        raise RuntimeError(
            "Expected exactly one SNP workbook; "
            f"found {len(workbook_members)}: "
            f"{workbook_members}"
        )

    member = workbook_members[0]

    with zipfile.ZipFile(
        artifact
    ) as z:

        raw = z.read(
            member
        )

    suffix = Path(
        member
    ).suffix

    df = read_excel_raw(
        raw,
        suffix,
        header=None,
    )

    return (
        df,
        member,
    )


def locate_snp_detail_header(
    raw_df: pd.DataFrame,
) -> int:

    candidates = []

    for idx, row in raw_df.iterrows():

        values = [
            norm(v)
            for v in row.tolist()
        ]

        value_set = set(
            values
        )

        has_contract = (
            "CONTRACT NUMBER"
            in value_set
        )

        has_plan = (
            "PLAN ID"
            in value_set
        )

        has_snp_type = (
            "SPECIAL NEEDS PLAN TYPE"
            in value_set
        )

        if (
            has_contract
            and has_plan
            and has_snp_type
        ):

            candidates.append(
                int(idx)
            )

    if len(candidates) != 1:

        raise RuntimeError(
            "Could not uniquely locate SNP "
            "detail-table header; candidates="
            f"{candidates}"
        )

    return candidates[0]


def prepare_snp(
    month: int,
):

    artifact = find_single_artifact(
        SNP_ROOT
        / f"{month:02d}",
        "SNP",
    )

    (
        raw_df,
        member,
    ) = load_snp_raw(
        artifact
    )

    header_row = (
        locate_snp_detail_header(
            raw_df
        )
    )

    header_values = [
        clean_text(v)
        for v
        in raw_df.iloc[
            header_row
        ].tolist()
    ]

    detail = (
        raw_df.iloc[
            header_row + 1:
        ]
        .copy()
    )

    detail.columns = (
        header_values
    )

    detail = (
        detail
        .dropna(
            how="all"
        )
        .reset_index(
            drop=True
        )
    )

    contract_col = find_column(
        detail,
        [
            "Contract Number",
        ],
    )

    plan_col = find_column(
        detail,
        [
            "Plan ID",
        ],
    )

    plan_type_col = find_column(
        detail,
        [
            "Plan Type",
        ],
    )

    enrollment_col = find_column(
        detail,
        [
            "Plan Enrollment",
        ],
    )

    subtype_col = find_column(
        detail,
        [
            "Special Needs Plan Type",
        ],
    )

    state_col = find_column(
        detail,
        [
            "State(s)",
            "States",
            "State",
        ],
    )

    detail[
        "_contract"
    ] = detail[
        contract_col
    ].map(
        normalize_contract
    )

    detail[
        "_plan"
    ] = detail[
        plan_col
    ].map(
        normalize_plan_id
    )

    detail[
        "_subtype"
    ] = detail[
        subtype_col
    ].map(
        norm
    )

    detail[
        "_plan_type"
    ] = detail[
        plan_type_col
    ].map(
        norm
    )

    detail[
        "_enrollment_numeric"
    ] = detail[
        enrollment_col
    ].map(
        numeric_or_none
    )

    detail[
        "_states"
    ] = detail[
        state_col
    ].map(
        norm
    )

    # Exclude CMS's synthetic privacy aggregate
    # from the real contract-plan identity map.
    synthetic_under11 = detail[
        detail[
            "_contract"
        ].str.replace(
            " ",
            "",
            regex=False,
        )
        == "UNDER-11"
    ].copy()

    real = detail[
        detail[
            "_contract"
        ].str.replace(
            " ",
            "",
            regex=False,
        )
        != "UNDER-11"
    ].copy()

    mapping = defaultdict(
        set
    )

    for _, row in real.iterrows():

        contract = row[
            "_contract"
        ]

        plan = row[
            "_plan"
        ]

        subtype = row[
            "_subtype"
        ]

        if (
            not contract
            or not plan
            or not subtype
        ):
            continue

        mapping[
            (
                contract,
                plan,
            )
        ].add(
            subtype
        )

    ambiguous = sum(
        len(values) > 1
        for values
        in mapping.values()
    )

    # State(s) may contain multiple states separated
    # by semicolons. Identify plans whose geography
    # explicitly includes Washington.
    def includes_wa(value) -> bool:

        states = {
            token.strip()
            for token in re.split(
                r"[;,]",
                norm(value),
            )
            if token.strip()
        }

        return "WA" in states

    wa_real = real[
        real[
            "_states"
        ].map(
            includes_wa
        )
    ].copy()

    return {
        "artifact": str(
            artifact
        ),

        "member": member,

        "header_row": (
            header_row
        ),

        "detail_rows": len(
            detail
        ),

        "real_rows": len(
            real
        ),

        "under11_rows": len(
            synthetic_under11
        ),

        "wa_rows": len(
            wa_real
        ),

        "unique_contract_plans": len(
            mapping
        ),

        "ambiguous_contract_plans": int(
            ambiguous
        ),

        "mapping": dict(
            mapping
        ),

        "real": real,
    }


# ============================================================================
# MONTH VALIDATION
# ============================================================================

MONTHLY_FIELDS = [
    "year",
    "month",
    "status",

    "cpsc_wa_rows",
    "cpsc_contract_duplicate_keys",
    "cpsc_join_unresolved_rows",
    "cpsc_target_rows",
    "cpsc_published_rows",
    "cpsc_suppressed_rows",
    "cpsc_published_enrollment",
    "cpsc_counties",

    "scp_wa_rows",
    "scp_target_rows",
    "scp_published_rows",
    "scp_suppressed_rows",
    "scp_enrollment",
    "scp_hmo_counties",
    "scp_local_ppo_counties",
    "scp_combined_counties",

    "enrollment_residual",
    "cpsc_coverage_pct",

    "cpsc_snp_non_eghp_rows",
    "cpsc_snp_eghp_rows",
    "cpsc_snp_non_eghp_unique_plans",

    "snp_header_row",
    "snp_detail_rows",
    "snp_real_rows",
    "snp_under11_rows",
    "snp_wa_rows",
    "snp_unique_contract_plans",
    "snp_ambiguous_contract_plans",

    "snp_resolved_non_eghp_plans",
    "snp_unresolved_non_eghp_plans",
    "snp_ambiguous_links",

    "checks_passed",
    "checks_total",
    "failure_reasons",
]


def validate_month(
    month: int,
) -> dict:

    row = {
        field: ""
        for field
        in MONTHLY_FIELDS
    }

    row["year"] = YEAR
    row["month"] = (
        f"{month:02d}"
    )
    row["status"] = "FAIL"

    failures = []

    print()
    print(
        f"[{YEAR}-{month:02d}]"
    )

    try:

        cpsc = prepare_cpsc(
            month
        )

        scp = prepare_scp(
            month
        )

        snp = prepare_snp(
            month
        )

    except Exception as exc:

        row[
            "failure_reasons"
        ] = str(exc)

        print(
            "  FAIL:",
            exc,
        )

        return row

    # ----------------------------------------------------------------
    # Populate metrics.
    # ----------------------------------------------------------------

    row[
        "cpsc_wa_rows"
    ] = cpsc[
        "wa_rows"
    ]

    row[
        "cpsc_contract_duplicate_keys"
    ] = cpsc[
        "contract_duplicate_keys"
    ]

    row[
        "cpsc_join_unresolved_rows"
    ] = cpsc[
        "join_unresolved_rows"
    ]

    row[
        "cpsc_target_rows"
    ] = cpsc[
        "target_rows"
    ]

    row[
        "cpsc_published_rows"
    ] = cpsc[
        "published_rows"
    ]

    row[
        "cpsc_suppressed_rows"
    ] = cpsc[
        "suppressed_rows"
    ]

    row[
        "cpsc_published_enrollment"
    ] = int(
        round(
            cpsc[
                "published_enrollment"
            ]
        )
    )

    row[
        "cpsc_counties"
    ] = cpsc[
        "counties"
    ]

    row[
        "scp_wa_rows"
    ] = scp[
        "wa_rows"
    ]

    row[
        "scp_target_rows"
    ] = scp[
        "target_rows"
    ]

    row[
        "scp_published_rows"
    ] = scp[
        "published_rows"
    ]

    row[
        "scp_suppressed_rows"
    ] = scp[
        "suppressed_rows"
    ]

       # IMPORTANT:
    # scp["enrollment"] is the sum of numeric/published
    # HMO/HMOPOS + Local PPO SCP enrollment cells only.
    #
    # When an SCP target cell is suppressed (for example "."),
    # its unknown enrollment is NOT included in this sum.
    # Therefore this quantity is a published subtotal, not an
    # exact statewide enrollment control when suppressed_rows > 0.
    #
    # Analytical bounds for suppressed SCP cells belong in the
    # reconstruction layer, not in this source validator.
    row[
        "scp_enrollment"
    ] = int(
        round(
            scp[
                "enrollment"
            ]
        )
    )

    row[
        "scp_hmo_counties"
    ] = scp[
        "hmo_counties"
    ]

    row[
        "scp_local_ppo_counties"
    ] = scp[
        "ppo_counties"
    ]

    row[
        "scp_combined_counties"
    ] = scp[
        "combined_counties"
    ]

    # This is the difference between the SCP published numeric
    # subtotal and CPSC published enrollment. It is an exact
    # control residual only when scp["suppressed_rows"] == 0.
    residual = (
        scp[
            "enrollment"
        ]
        - cpsc[
            "published_enrollment"
        ]
    )

    row[
        "enrollment_residual"
    ] = int(
        round(
            residual
        )
    )

    if scp[
        "enrollment"
    ] > 0:

        coverage_pct = (
            cpsc[
                "published_enrollment"
            ]
            / scp[
                "enrollment"
            ]
            * 100.0
        )

    else:
        coverage_pct = None

    row[
        "cpsc_coverage_pct"
    ] = (
        ""
        if coverage_pct is None
        else round(
            coverage_pct,
            6,
        )
    )

    snp_non_eghp = cpsc[
        "snp_non_eghp"
    ]

    snp_eghp = cpsc[
        "snp_eghp"
    ]

    non_eghp_keys = {
        (
            normalize_contract(
                r["_contract"]
            ),
            normalize_plan_id(
                r["_plan"]
            ),
        )
        for _, r
        in snp_non_eghp.iterrows()
        if (
            normalize_contract(
                r["_contract"]
            )
            and normalize_plan_id(
                r["_plan"]
            )
        )
    }

    row[
        "cpsc_snp_non_eghp_rows"
    ] = len(
        snp_non_eghp
    )

    row[
        "cpsc_snp_eghp_rows"
    ] = len(
        snp_eghp
    )

    row[
        "cpsc_snp_non_eghp_unique_plans"
    ] = len(
        non_eghp_keys
    )

    row[
        "snp_header_row"
    ] = snp[
        "header_row"
    ]

    row[
        "snp_detail_rows"
    ] = snp[
        "detail_rows"
    ]

    row[
        "snp_real_rows"
    ] = snp[
        "real_rows"
    ]

    row[
        "snp_under11_rows"
    ] = snp[
        "under11_rows"
    ]

    row[
        "snp_wa_rows"
    ] = snp[
        "wa_rows"
    ]

    row[
        "snp_unique_contract_plans"
    ] = snp[
        "unique_contract_plans"
    ]

    row[
        "snp_ambiguous_contract_plans"
    ] = snp[
        "ambiguous_contract_plans"
    ]

    resolved = 0
    unresolved = 0
    ambiguous_links = 0

    for key in sorted(
        non_eghp_keys
    ):

        values = snp[
            "mapping"
        ].get(
            key
        )

        if values is None:
            unresolved += 1

        elif len(values) == 1:
            resolved += 1

        else:
            ambiguous_links += 1

    row[
        "snp_resolved_non_eghp_plans"
    ] = resolved

    row[
        "snp_unresolved_non_eghp_plans"
    ] = unresolved

    row[
        "snp_ambiguous_links"
    ] = ambiguous_links

    # ----------------------------------------------------------------
    # Invariants.
    # ----------------------------------------------------------------

    checks = []

    def check(
        name: str,
        condition: bool,
        message: str,
    ):

        checks.append(
            (
                name,
                condition,
            )
        )

        if not condition:

            failures.append(
                f"{name}: {message}"
            )

    check(
        "CPSC_WA_PRESENT",
        cpsc[
            "wa_rows"
        ] > 0,
        "No Washington enrollment rows.",
    )

    check(
        "CPSC_CONTRACT_KEYS_UNIQUE",
        cpsc[
            "contract_duplicate_keys"
        ] == 0,
        (
            "CPSC contract-info contains "
            f"{cpsc['contract_duplicate_keys']} "
            "duplicate contract-plan keys."
        ),
    )

    check(
        "CPSC_CONTRACT_JOIN_COMPLETE",
        cpsc[
            "join_unresolved_rows"
        ] == 0,
        (
            f"{cpsc['join_unresolved_rows']} "
            "Washington enrollment rows did "
            "not resolve to contract-info."
        ),
    )

    check(
        "CPSC_TARGET_PRESENT",
        cpsc[
            "target_rows"
        ] > 0,
        (
            "No Washington HMO/HMOPOS "
            "or Local PPO rows."
        ),
    )

    check(
        "CPSC_PUBLISHED_ENROLLMENT_POSITIVE",
        cpsc[
            "published_enrollment"
        ] > 0,
        (
            "Published target enrollment "
            "is not positive."
        ),
    )

    check(
        "CPSC_COUNTY_COVERAGE",
        cpsc[
            "counties"
        ] == EXPECTED_WA_COUNTIES,
        (
            f"CPSC target rows cover "
            f"{cpsc['counties']} counties, "
            f"expected {EXPECTED_WA_COUNTIES}."
        ),
    )

    check(
        "SCP_WA_PRESENT",
        scp[
            "wa_rows"
        ] > 0,
        "No Washington SCP rows.",
    )

    check(
        "SCP_HMO_39_COUNTIES",
        scp[
            "hmo_counties"
        ] == EXPECTED_WA_COUNTIES,
        (
            f"HMO/HMOPOS covers "
            f"{scp['hmo_counties']} counties."
        ),
    )

    check(
        "SCP_LOCAL_PPO_39_COUNTIES",
        scp[
            "ppo_counties"
        ] == EXPECTED_WA_COUNTIES,
        (
            f"Local PPO covers "
            f"{scp['ppo_counties']} counties."
        ),
    )

    check(
        "SCP_COMBINED_39_COUNTIES",
        scp[
            "combined_counties"
        ] == EXPECTED_WA_COUNTIES,
        (
            f"Combined target products cover "
            f"{scp['combined_counties']} counties."
        ),
    )

    check(
        "SCP_ENROLLMENT_POSITIVE",
        scp[
            "enrollment"
        ] > 0,
        (
            "SCP target enrollment "
            "is not positive."
        ),
    )

    check(
        "CPSC_NOT_GREATER_THAN_SCP",
        cpsc[
            "published_enrollment"
        ] <= scp[
            "enrollment"
        ],
        (
            "Published CPSC enrollment exceeds "
            "SCP published subtotal: "
            f"{cpsc['published_enrollment']} > "
            f"{scp['enrollment']}."
        ),
    )

    check(
        "SNP_DETAIL_PRESENT",
        snp[
            "real_rows"
        ] > 0,
        (
            "No real SNP detail rows "
            "were parsed."
        ),
    )

    check(
        "SNP_WA_PRESENT",
        snp[
            "wa_rows"
        ] > 0,
        (
            "No SNP detail rows explicitly "
            "include Washington."
        ),
    )

    check(
        "SNP_MAPPING_UNAMBIGUOUS",
        snp[
            "ambiguous_contract_plans"
        ] == 0,
        (
            f"{snp['ambiguous_contract_plans']} "
            "SNP contract-plan identities map "
            "to multiple SNP subtypes."
        ),
    )

    check(
        "SNP_CPSC_LINKS_UNAMBIGUOUS",
        ambiguous_links == 0,
        (
            f"{ambiguous_links} CPSC SNP "
            "contract-plan identities have "
            "ambiguous SNP mappings."
        ),
    )

    check(
        "SNP_NON_EGHP_LINK_COMPLETE",
        unresolved == 0,
        (
            f"{unresolved} non-EGHP CPSC SNP "
            "contract-plan identities do not "
            "resolve to the SNP report."
        ),
    )

    passed = sum(
        condition
        for _, condition
        in checks
    )

    row[
        "checks_passed"
    ] = passed

    row[
        "checks_total"
    ] = len(
        checks
    )

    if failures:

        row[
            "failure_reasons"
        ] = " | ".join(
            failures
        )

        print(
            f"  FAIL: {passed}/{len(checks)} checks"
        )

        for failure in failures:

            print(
                "   -",
                failure,
            )

    else:

        row[
            "status"
        ] = "PASS"

        print(
            f"  PASS: {passed}/{len(checks)} checks"
        )

    print(
        "  CPSC published enrollment:",
        f"{cpsc['published_enrollment']:,.0f}",
    )

    print(
        "  SCP published subtotal:    ",
        f"{scp['enrollment']:,.0f}",
    )

    print(
        "  Suppression residual:       ",
        f"{residual:,.0f}",
    )

    if coverage_pct is not None:

        print(
            "  CPSC/SCP published ratio:   ",
            f"{coverage_pct:.6f}%",
        )

    print(
        "  CPSC suppressed rows:       ",
        f"{cpsc['suppressed_rows']:,}",
    )

    print(
        "  CPSC county coverage:       ",
        f"{cpsc['counties']}/39",
    )

    print(
        "  SCP HMO/PPO counties:       ",
        (
            f"{scp['hmo_counties']}/"
            f"{scp['ppo_counties']}"
        ),
    )

    print(
        "  CPSC SNP non-EGHP plans:    ",
        f"{len(non_eghp_keys):,}",
    )

    print(
        "  SNP resolved:               ",
        f"{resolved:,}",
    )

    print(
        "  SNP unresolved:             ",
        f"{unresolved:,}",
    )

    print(
        "  SNP ambiguous:              ",
        f"{ambiguous_links:,}",
    )

    return row


# ============================================================================
# OUTPUT
# ============================================================================

def write_monthly_csv(
    rows: list[dict],
):

    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with MONTHLY_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=MONTHLY_FIELDS,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


def build_summary(
    rows: list[dict],
) -> str:

    lines = []

    lines.append(
        "=" * 96
    )

    lines.append(
        "CMS MEDICARE ADVANTAGE "
        "CY2022 WASHINGTON SOURCE VALIDATION"
    )

    lines.append(
        "=" * 96
    )

    lines.append(
        ""
    )

    passed = sum(
        row[
            "status"
        ] == "PASS"
        for row in rows
    )

    lines.append(
        f"Months passing: {passed}/12"
    )

    lines.append(
        ""
    )

    lines.append(
        "MONTHLY ENROLLMENT RECONCILIATION"
    )

    lines.append(
        "-" * 96
    )

    lines.append(
        (
            "Month    Status   "
            "CPSC Published   "
            "SCP Published   "
            "Residual   "
            "Coverage %   "
            "Suppressed Rows"
        )
    )

    for row in rows:

        lines.append(
            (
                f"{row['year']}-{row['month']}   "
                f"{row['status']:<6}   "
                f"{str(row['cpsc_published_enrollment']):>14}   "
                f"{str(row['scp_enrollment']):>11}   "
                f"{str(row['enrollment_residual']):>8}   "
                f"{str(row['cpsc_coverage_pct']):>10}   "
                f"{str(row['cpsc_suppressed_rows']):>15}"
            )
        )

    lines.append(
        ""
    )

    lines.append(
        "CPSC CONTRACT-INFO JOIN"
    )

    lines.append(
        "-" * 96
    )

    for row in rows:

        lines.append(
            (
                f"{row['year']}-{row['month']}: "
                f"duplicate keys="
                f"{row['cpsc_contract_duplicate_keys']}; "
                f"unresolved WA rows="
                f"{row['cpsc_join_unresolved_rows']}; "
                f"target counties="
                f"{row['cpsc_counties']}"
            )
        )

    lines.append(
        ""
    )

    lines.append(
        "SNP LINKAGE"
    )

    lines.append(
        "-" * 96
    )

    for row in rows:

        lines.append(
            (
                f"{row['year']}-{row['month']}: "
                f"non-EGHP CPSC SNP plans="
                f"{row['cpsc_snp_non_eghp_unique_plans']}; "
                f"resolved="
                f"{row['snp_resolved_non_eghp_plans']}; "
                f"unresolved="
                f"{row['snp_unresolved_non_eghp_plans']}; "
                f"ambiguous="
                f"{row['snp_ambiguous_links']}; "
                f"CMS Under-11 rows="
                f"{row['snp_under11_rows']}"
            )
        )

    lines.append(
        ""
    )

    lines.append(
        "FAILURES"
    )

    lines.append(
        "-" * 96
    )

    failures = [
        row
        for row in rows
        if row[
            "status"
        ] != "PASS"
    ]

    if failures:

        for row in failures:

            lines.append(
                (
                    f"{row['year']}-"
                    f"{row['month']}: "
                    f"{row['failure_reasons']}"
                )
            )

    else:

        lines.append(
            "None"
        )

    lines.append(
        ""
    )

    lines.append(
        "=" * 96
    )

    if passed == 12:

        lines.append(
            "STATUS: CY2022 CMS MA "
            "WASHINGTON SOURCE VALIDATION PASS"
        )

        lines.append(
            ""
        )

        lines.append(
            "All 12 months support the Washington "
            "source-level enrollment, contract-info, "
            "suppression-observation, and SNP-linkage "
            "architecture."
        )

        lines.append(
            ""
        )

        lines.append(
            "This does NOT yet constitute "
            "Medicare Advantage payment validation "
            "or final-ledger certification."
        )

    else:

        lines.append(
            "STATUS: CY2022 CMS MA "
            "WASHINGTON SOURCE VALIDATION FAIL"
        )

        lines.append(
            ""
        )

        lines.append(
            "DO NOT PROCEED TO PAYMENT "
            "RECONSTRUCTION."
        )

    lines.append(
        "=" * 96
    )

    return "\n".join(
        lines
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    print(
        "=" * 96
    )

    print(
        "CMS MEDICARE ADVANTAGE "
        "CY2022 WASHINGTON SOURCE VALIDATION v0.2"
    )

    print(
        "=" * 96
    )

    print()

    print(
        "Read-only validation. "
        "No database writes. "
        "No payment reconstruction."
    )

    rows = []

    for month in range(
        1,
        13,
    ):

        row = validate_month(
            month
        )

        rows.append(
            row
        )

        write_monthly_csv(
            rows
        )

    summary = build_summary(
        rows
    )

    SUMMARY_TXT.write_text(
        summary,
        encoding="utf-8",
    )

    print()
    print(
        summary
    )

    print()
    print(
        "Monthly CSV:",
        MONTHLY_CSV,
    )

    print(
        "Summary:",
        SUMMARY_TXT,
    )

    passed = sum(
        row[
            "status"
        ] == "PASS"
        for row in rows
    )

    if passed == 12:
        return 0

    return 1


if __name__ == "__main__":

    sys.exit(
        main()
    )