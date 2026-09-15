"""
CMS Medicare Advantage CY2022 Washington Part C payment reconstruction v0.2

READ-ONLY:
    * no PostgreSQL writes
    * no source-file modification
    * no final-ledger certification

Purpose
-------
Perform a historical annual replication test of the Medicare Advantage
Part C methodology using official CMS CY2022 source artifacts.

For each month:

    1. Read Washington CPSC county enrollment.
    2. Join CPSC enrollment to CPSC contract-info to obtain Plan Type,
       SNP status, and EGHP status.
    3. Join non-EGHP SNP plans to the CMS SNP report to obtain SNP subtype.
    4. Aggregate published enrollment to the dimensional grain of the
       2022 Part C County Payment PUF:

           County
           Plan Type
           SNP Plan Type

    5. Join those cells to the payment PUF.
    6. Reconstruct published-enrollment Part C payment:

           PMPM =
               (Average AB PM/PM Payment
                * Average Part C Risk Score)
               + Average Rebate PM/PM Payment

           Payment = Enrollment * PMPM

    7. Use SCP HMO/HMOPOS + Local PPO county enrollment as the aggregate
       enrollment control.

    8. Explicitly preserve two disclosure/suppression layers:

       A. CPSC granular suppression:
          Difference between SCP control enrollment and published CPSC
          enrollment.

       B. SCP control suppression:
          A target SCP cell published as "." is NOT treated as zero.
          WCFFBP assigns a conservative analytical interval:

              lower   = 0 enrollees
              central = 5 enrollees
              upper   = 10 enrollees

          The midpoint is a sensitivity midpoint only. It is not a
          recovered CMS value and is never written back to source data.

Important
---------
The 2022 Washington Part C County Payment PUF contains:

    non-SNP
    Dual-Eligible
    Institutional

No Chronic/Disabling Washington payment cells were observed in the
2022 PUF. Published enrollment requiring an unsupported payment
dimension therefore causes a fail-loudly error.

This is a CY2022 methodological replication experiment. It is NOT
the final federal-fiscal-year ledger calculation.
"""

from __future__ import annotations

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

PAYMENT_ZIP = (
    ROOT
    / "plan_payment"
    / str(YEAR)
    / "2022_plan_payment.zip"
)

VALIDATION_DIR = (
    ROOT
    / "validation"
    / str(YEAR)
)

MONTHLY_OUTPUT = (
    VALIDATION_DIR
    / "cms_ma_partc_2022_monthly_reconstruction.csv"
)

SUMMARY_OUTPUT = (
    VALIDATION_DIR
    / "cms_ma_partc_2022_reconstruction_summary.txt"
)

CELL_OUTPUT = (
    VALIDATION_DIR
    / "cms_ma_partc_2022_payment_cells.csv"
)

SCP_SUPPRESSION_OUTPUT = (
    VALIDATION_DIR
    / "cms_ma_partc_2022_scp_suppressed_cells.csv"
)

SCP_SUPPRESSED_LOWER = 0.0
SCP_SUPPRESSED_CENTRAL = 5.0
SCP_SUPPRESSED_UPPER = 10.0

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

    return re.sub(
        r"\s+",
        " ",
        clean_text(value).upper(),
    )


def norm_col(value) -> str:

    return re.sub(
        r"[^A-Z0-9]+",
        "_",
        norm(value),
    ).strip("_")


def normalize_contract(value) -> str:

    return norm(value)


def normalize_plan_id(value) -> str:

    text = clean_text(value)

    if not text:
        return ""

    try:

        number = float(text)

        if number.is_integer():
            return str(
                int(number)
            ).zfill(3)

    except ValueError:
        pass

    return text.zfill(3)


def normalize_county(value) -> str:

    text = norm(value)

    text = re.sub(
        r"\s+COUNTY$",
        "",
        text,
    )

    return text


def normalize_plan_type(value) -> str:

    value = norm(value)

    if value in {
        "HMO",
        "HMO/HMOPOS",
    }:
        return "HMO"

    if value == "LOCAL PPO":
        return "LOCAL PPO"

    return value


def normalize_snp_type(value) -> str:

    value = norm(value)

    if not value:
        return "NON-SNP"

    if value in {
        "DUAL-ELIGIBLE",
        "DUAL ELIGIBLE",
    }:
        return "DUAL-ELIGIBLE"

    if value == "INSTITUTIONAL":
        return "INSTITUTIONAL"

    if value in {
        "CHRONIC OR DISABLING CONDITION",
        "CHRONIC/DISABLING",
        "CHRONIC OR DISABLING",
    }:
        return "CHRONIC OR DISABLING CONDITION"

    return value


def numeric_or_none(value):

    if value is None:
        return None

    if pd.isna(value):
        return None

    text = clean_text(value)

    if norm(text) in {
        "",
        ".",
        "*",
        "**",
        "***",
        "NA",
        "N/A",
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
        return float(text)

    except ValueError:
        return None


def is_yes(value) -> bool:

    return norm(value) in YES_VALUES


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str:

    lookup = {
        norm_col(c): c
        for c in df.columns
    }

    for candidate in candidates:

        key = norm_col(candidate)

        if key in lookup:
            return lookup[key]

    raise RuntimeError(
        "Required column not found. "
        f"Candidates={candidates}; "
        f"available={list(df.columns)}"
    )


# ============================================================================
# GENERIC FILE HELPERS
# ============================================================================

def read_csv_bytes(raw: bytes) -> pd.DataFrame:

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
        "Unable to parse CSV: "
        + " | ".join(errors)
    )


def find_zip(
    directory: Path,
    family: str,
) -> Path:

    if not directory.exists():

        raise RuntimeError(
            f"Missing directory: {directory}"
        )

    candidates = []

    for path in directory.iterdir():

        if not path.is_file():
            continue

        lower = path.name.lower()

        if not lower.endswith(".zip"):
            continue

        if family == "CPSC":

            if "cpsc" in lower:
                candidates.append(path)

        elif family == "SCP":

            if (
                "scp" in lower
                or "statecountyplan" in lower
            ):
                candidates.append(path)

        elif family == "SNP":

            if "snp" in lower:
                candidates.append(path)

    if len(candidates) != 1:

        raise RuntimeError(
            f"{family}: expected one ZIP "
            f"in {directory}; "
            f"found {candidates}"
        )

    return candidates[0]


def find_member(
    members,
    fragments,
    suffix,
):

    matches = []

    for member in members:

        lower = member.lower()

        if not lower.endswith(
            suffix.lower()
        ):
            continue

        if all(
            fragment.lower() in lower
            for fragment in fragments
        ):
            matches.append(member)

    if len(matches) != 1:

        raise RuntimeError(
            "Expected exactly one matching "
            f"archive member; fragments={fragments}; "
            f"matches={matches}"
        )

    return matches[0]


# ============================================================================
# PAYMENT PUF
# ============================================================================

def load_payment_puf() -> pd.DataFrame:

    if not PAYMENT_ZIP.exists():

        raise RuntimeError(
            f"Missing payment ZIP: {PAYMENT_ZIP}"
        )

    with zipfile.ZipFile(
        PAYMENT_ZIP
    ) as z:

        members = [
            m for m in z.namelist()
            if m.endswith(
                "2022PartCCountyLevel.xlsx"
            )
        ]

        if len(members) != 1:

            raise RuntimeError(
                "Could not uniquely locate "
                "2022 Part C County workbook"
            )

        raw = z.read(
            members[0]
        )

    df = pd.read_excel(
        io.BytesIO(raw),
        sheet_name="result.html",
        header=2,
        dtype=str,
        engine="openpyxl",
    )

    state_col = find_column(
        df,
        ["State Abbreviation"],
    )

    county_col = find_column(
        df,
        ["County Name"],
    )

    plan_type_col = find_column(
        df,
        ["Plan Type"],
    )

    snp_col = find_column(
        df,
        ["SNP Plan Type"],
    )

    risk_col = find_column(
        df,
        ["Average Part C Risk Score"],
    )

    ab_col = find_column(
        df,
        ["Average AB PM/PM Payment"],
    )

    rebate_col = find_column(
        df,
        ["Average Rebate PM/PM Payment"],
    )

    wa = df[
        df[state_col]
        .map(norm)
        == "WA"
    ].copy()

    if len(wa) != 130:

        raise RuntimeError(
            "Unexpected WA payment-cell count: "
            f"{len(wa)}; expected 130"
        )

    if (
        wa[county_col]
        .map(normalize_county)
        .nunique()
        != 39
    ):

        raise RuntimeError(
            "Payment PUF does not cover "
            "39 Washington counties"
        )

    wa["_county"] = (
        wa[county_col]
        .map(normalize_county)
    )

    wa["_plan_type"] = (
        wa[plan_type_col]
        .map(normalize_plan_type)
    )

    wa["_snp_type"] = (
        wa[snp_col]
        .map(normalize_snp_type)
    )

    wa["_risk"] = (
        wa[risk_col]
        .map(numeric_or_none)
    )

    wa["_ab_std"] = (
        wa[ab_col]
        .map(numeric_or_none)
    )

    wa["_rebate"] = (
        wa[rebate_col]
        .map(numeric_or_none)
    )

    if (
        wa[
            [
                "_risk",
                "_ab_std",
                "_rebate",
            ]
        ]
        .isna()
        .any()
        .any()
    ):

        raise RuntimeError(
            "Missing numeric payment value "
            "in WA payment PUF"
        )

    wa["_ab_actual"] = (
        wa["_ab_std"]
        * wa["_risk"]
    )

    wa["_pmpm"] = (
        wa["_ab_actual"]
        + wa["_rebate"]
    )

    key_cols = [
        "_county",
        "_plan_type",
        "_snp_type",
    ]

    duplicates = int(
        wa.duplicated(
            key_cols,
            keep=False,
        ).sum()
    )

    if duplicates:

        raise RuntimeError(
            f"Payment PUF contains "
            f"{duplicates} duplicate "
            "Washington payment-cell rows"
        )

    return wa[
        key_cols
        + [
            "_risk",
            "_ab_std",
            "_rebate",
            "_ab_actual",
            "_pmpm",
        ]
    ].copy()


# ============================================================================
# CPSC MONTH
# ============================================================================

def load_cpsc_month(
    month: int,
) -> pd.DataFrame:

    path = find_zip(
        CPSC_ROOT
        / f"{month:02d}",
        "CPSC",
    )

    with zipfile.ZipFile(path) as z:

        members = z.namelist()

        enrollment_member = find_member(
            members,
            ["enrollment_info"],
            ".csv",
        )

        contract_member = find_member(
            members,
            ["contract_info"],
            ".csv",
        )

        enrollment = read_csv_bytes(
            z.read(enrollment_member)
        )

        contracts = read_csv_bytes(
            z.read(contract_member)
        )

    e_contract = find_column(
        enrollment,
        ["Contract Number"],
    )

    e_plan = find_column(
        enrollment,
        ["Plan ID"],
    )

    e_state = find_column(
        enrollment,
        ["State"],
    )

    e_county = find_column(
        enrollment,
        ["County"],
    )

    e_enrollment = find_column(
        enrollment,
        ["Enrollment"],
    )

    c_contract = find_column(
        contracts,
        ["Contract ID"],
    )

    c_plan = find_column(
        contracts,
        ["Plan ID"],
    )

    c_plan_type = find_column(
        contracts,
        ["Plan Type"],
    )

    c_snp = find_column(
        contracts,
        ["SNP Plan"],
    )

    c_eghp = find_column(
        contracts,
        ["EGHP"],
    )

    enrollment = enrollment.copy()
    contracts = contracts.copy()

    enrollment["_contract"] = (
        enrollment[e_contract]
        .map(normalize_contract)
    )

    enrollment["_plan"] = (
        enrollment[e_plan]
        .map(normalize_plan_id)
    )

    contracts["_contract"] = (
        contracts[c_contract]
        .map(normalize_contract)
    )

    contracts["_plan"] = (
        contracts[c_plan]
        .map(normalize_plan_id)
    )

    contract_info = contracts[
        [
            "_contract",
            "_plan",
            c_plan_type,
            c_snp,
            c_eghp,
        ]
    ].copy()

    if contract_info.duplicated(
        [
            "_contract",
            "_plan",
        ]
    ).any():

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            "duplicate CPSC contract-info keys"
        )

    contract_info = contract_info.rename(
        columns={
            c_plan_type: "_plan_type_raw",
            c_snp: "_snp_raw",
            c_eghp: "_eghp_raw",
        }
    )

    wa = enrollment[
        enrollment[e_state]
        .map(norm)
        == "WA"
    ].copy()

    joined = wa.merge(
        contract_info,
        on=[
            "_contract",
            "_plan",
        ],
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    unresolved = int(
        (
            joined["_merge"]
            != "both"
        ).sum()
    )

    if unresolved:

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            f"{unresolved} WA enrollment rows "
            "do not resolve to contract-info"
        )

    joined["_county"] = (
        joined[e_county]
        .map(normalize_county)
    )

    joined["_plan_type"] = (
        joined["_plan_type_raw"]
        .map(normalize_plan_type)
    )

    joined["_is_snp"] = (
        joined["_snp_raw"]
        .map(is_yes)
    )

    joined["_is_eghp"] = (
        joined["_eghp_raw"]
        .map(is_yes)
    )

    joined["_enrollment"] = (
        joined[e_enrollment]
        .map(numeric_or_none)
    )

    target = joined[
        joined["_plan_type"]
        .isin(
            {
                "HMO",
                "LOCAL PPO",
            }
        )
    ].copy()

    return target


# ============================================================================
# SNP MONTH
# ============================================================================

def load_snp_mapping(
    month: int,
) -> dict:

    path = find_zip(
        SNP_ROOT
        / f"{month:02d}",
        "SNP",
    )

    with zipfile.ZipFile(path) as z:

        workbooks = [
            m for m in z.namelist()
            if m.lower().endswith(
                (
                    ".xls",
                    ".xlsx",
                )
            )
        ]

        if len(workbooks) != 1:

            raise RuntimeError(
                f"{YEAR}-{month:02d}: "
                "expected one SNP workbook"
            )

        member = workbooks[0]
        raw = z.read(member)

    suffix = Path(member).suffix.lower()

    if suffix == ".xls":

        raw_df = pd.read_excel(
            io.BytesIO(raw),
            header=None,
            dtype=str,
            engine="xlrd",
        )

    else:

        raw_df = pd.read_excel(
            io.BytesIO(raw),
            header=None,
            dtype=str,
            engine="openpyxl",
        )

    header_candidates = []

    for idx, row in raw_df.iterrows():

        values = {
            norm(v)
            for v in row.tolist()
        }

        if (
            "CONTRACT NUMBER" in values
            and "PLAN ID" in values
            and "SPECIAL NEEDS PLAN TYPE"
            in values
        ):

            header_candidates.append(
                int(idx)
            )

    if len(header_candidates) != 1:

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            "cannot uniquely locate SNP "
            f"detail header: {header_candidates}"
        )

    header_row = header_candidates[0]

    headers = [
        clean_text(v)
        for v
        in raw_df.iloc[
            header_row
        ].tolist()
    ]

    df = (
        raw_df.iloc[
            header_row + 1:
        ]
        .copy()
    )

    df.columns = headers

    df = df.dropna(
        how="all"
    )

    contract_col = find_column(
        df,
        ["Contract Number"],
    )

    plan_col = find_column(
        df,
        ["Plan ID"],
    )

    subtype_col = find_column(
        df,
        ["Special Needs Plan Type"],
    )

    df["_contract"] = (
        df[contract_col]
        .map(normalize_contract)
    )

    df["_plan"] = (
        df[plan_col]
        .map(normalize_plan_id)
    )

    df["_snp_type"] = (
        df[subtype_col]
        .map(normalize_snp_type)
    )

    # Synthetic CMS Under-11 records are privacy
    # aggregates, not real contract-plan identities.
    df = df[
        df["_contract"]
        .str.replace(
            " ",
            "",
            regex=False,
        )
        != "UNDER-11"
    ].copy()

    mapping = defaultdict(set)

    for _, row in df.iterrows():

        key = (
            row["_contract"],
            row["_plan"],
        )

        if (
            not key[0]
            or not key[1]
        ):
            continue

        mapping[key].add(
            row["_snp_type"]
        )

    ambiguous = {
        key: values
        for key, values
        in mapping.items()
        if len(values) != 1
    }

    if ambiguous:

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            f"{len(ambiguous)} ambiguous "
            "SNP contract-plan mappings"
        )

    return {
        key: next(
            iter(values)
        )
        for key, values
        in mapping.items()
    }


# ============================================================================
# SCP MONTH
# ============================================================================

def load_scp_control(
    month: int,
):

    """
    Return the published SCP subtotal and explicit
    0/5/10 bounds for suppressed target cells.

    A "." is never converted to an observed zero.
    """

    path = find_zip(
        SCP_ROOT
        / f"{month:02d}",
        "SCP",
    )

    with zipfile.ZipFile(path) as z:

        members = [
            m for m in z.namelist()
            if m.lower().endswith(
                ".csv"
            )
        ]

        if len(members) != 1:

            raise RuntimeError(
                f"{YEAR}-{month:02d}: "
                "expected one SCP CSV"
            )

        df = read_csv_bytes(
            z.read(
                members[0]
            )
        )

    county_col = find_column(
        df,
        ["County"],
    )

    state_col = find_column(
        df,
        ["State"],
    )

    plan_col = find_column(
        df,
        ["Plan Type"],
    )

    enrollment_col = find_column(
        df,
        [
            "Enrolled",
            "Enrollment",
        ],
    )

    ssa_col = find_column(
        df,
        ["SSA Code"],
    )

    fips_col = find_column(
        df,
        ["FIPS Code"],
    )

    wa = df[
        df[state_col]
        .map(norm)
        == "WA"
    ].copy()

    wa["_county"] = (
        wa[county_col]
        .map(normalize_county)
    )

    wa["_plan_type"] = (
        wa[plan_col]
        .map(normalize_plan_type)
    )

    wa["_enrollment"] = (
        wa[enrollment_col]
        .map(numeric_or_none)
    )

    target = wa[
        wa["_plan_type"]
        .isin(
            {
                "HMO",
                "LOCAL PPO",
            }
        )
    ].copy()

    if len(target) != 78:

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            f"expected 78 SCP target rows; "
            f"found {len(target)}"
        )

    if (
        target["_county"]
        .nunique()
        != 39
    ):

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            "SCP target does not cover "
            "39 Washington counties"
        )

    for plan_type in (
        "HMO",
        "LOCAL PPO",
    ):

        count = int(
            (
                target["_plan_type"]
                == plan_type
            ).sum()
        )

        if count != 39:

            raise RuntimeError(
                f"{YEAR}-{month:02d}: "
                f"{plan_type} has {count} "
                "SCP county rows; expected 39"
            )

    published_subtotal = float(
        target["_enrollment"]
        .dropna()
        .sum()
    )

    suppressed = target[
        target["_enrollment"]
        .isna()
    ].copy()

    suppressed_count = len(
        suppressed
    )

    lower_control = (
        published_subtotal
        + suppressed_count
        * SCP_SUPPRESSED_LOWER
    )

    central_control = (
        published_subtotal
        + suppressed_count
        * SCP_SUPPRESSED_CENTRAL
    )

    upper_control = (
        published_subtotal
        + suppressed_count
        * SCP_SUPPRESSED_UPPER
    )

    suppressed_rows = []

    for _, row in suppressed.iterrows():

        suppressed_rows.append(
            {
                "year": YEAR,
                "month": month,
                "county": clean_text(
                    row[county_col]
                ),
                "plan_type": clean_text(
                    row[plan_col]
                ),
                "ssa_code": clean_text(
                    row[ssa_col]
                ),
                "fips_code": clean_text(
                    row[fips_col]
                ),
                "source_value": clean_text(
                    row[enrollment_col]
                ),
                "analytical_lower": (
                    SCP_SUPPRESSED_LOWER
                ),
                "analytical_central": (
                    SCP_SUPPRESSED_CENTRAL
                ),
                "analytical_upper": (
                    SCP_SUPPRESSED_UPPER
                ),
                "method": (
                    "WCFFBP conservative "
                    "SCP suppression bound"
                ),
            }
        )

    return {
        "published_subtotal":
            published_subtotal,

        "suppressed_cells":
            suppressed_count,

        "control_lower":
            lower_control,

        "control_central":
            central_control,

        "control_upper":
            upper_control,

        "suppressed_rows":
            suppressed_rows,
    }


# ============================================================================
# SNP TYPE ASSIGNMENT
# ============================================================================

def assign_snp_types(
    cpsc: pd.DataFrame,
    snp_mapping: dict,
    month: int,
) -> pd.DataFrame:

    df = cpsc.copy()

    snp_types = []
    unresolved = []

    for _, row in df.iterrows():

        if not row["_is_snp"]:

            snp_types.append(
                "NON-SNP"
            )

            continue

        key = (
            row["_contract"],
            row["_plan"],
        )

        subtype = snp_mapping.get(
            key
        )

        if subtype is None:

            if row["_is_eghp"]:

                # CMS SNP reports omit employer-only
                # group plans. Do not guess subtype.
                snp_types.append(
                    None
                )

                continue

            unresolved.append(
                key
            )

            snp_types.append(
                None
            )

            continue

        snp_types.append(
            subtype
        )

    df["_snp_type"] = (
        snp_types
    )

    if unresolved:

        unique = sorted(
            set(unresolved)
        )

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            f"{len(unique)} non-EGHP SNP plans "
            "lack SNP subtype mapping"
        )

    unresolved_published = df[
        df["_snp_type"].isna()
        & df["_enrollment"].notna()
    ]

    unresolved_published_enrollment = float(
        unresolved_published[
            "_enrollment"
        ].sum()
    )

    if (
        unresolved_published_enrollment
        > 0
    ):

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            "published enrollment exists for "
            "SNP/EGHP rows without a source-supported "
            "SNP subtype; enrollment="
            f"{unresolved_published_enrollment:,.0f}"
        )

    return df


def aggregate_published_cells(
    cpsc: pd.DataFrame,
) -> pd.DataFrame:

    published = cpsc[
        cpsc["_enrollment"]
        .notna()
    ].copy()

    published = published[
        published["_snp_type"]
        .notna()
    ].copy()

    return (
        published
        .groupby(
            [
                "_county",
                "_plan_type",
                "_snp_type",
            ],
            as_index=False,
        )["_enrollment"]
        .sum()
    )


# ============================================================================
# CPSC SUPPRESSION PAYMENT MODEL
# ============================================================================

def cpsc_suppression_payment(
    residual: float,
    published_payment: float,
    published_enrollment: float,
    payment_puf: pd.DataFrame,
):

    """
    Convert an enrollment residual into conservative
    lower/central/upper payment corrections.

    LOWER:
        residual * minimum WA PUF PMPM

    CENTRAL:
        residual * published-enrollment-weighted PMPM

    UPPER:
        residual * maximum WA PUF PMPM

    This does not invent county/SNP identities.
    """

    if residual < -0.000001:

        raise RuntimeError(
            "Negative CPSC suppression residual"
        )

    residual = max(
        0.0,
        residual,
    )

    if published_enrollment <= 0:

        raise RuntimeError(
            "Published enrollment is zero"
        )

    min_pmpm = float(
        payment_puf["_pmpm"]
        .min()
    )

    max_pmpm = float(
        payment_puf["_pmpm"]
        .max()
    )

    weighted_pmpm = (
        published_payment
        / published_enrollment
    )

    return {
        "residual":
            residual,

        "lower":
            residual
            * min_pmpm,

        "central":
            residual
            * weighted_pmpm,

        "upper":
            residual
            * max_pmpm,

        "min_pmpm":
            min_pmpm,

        "weighted_pmpm":
            weighted_pmpm,

        "max_pmpm":
            max_pmpm,
    }


# ============================================================================
# MONTH RECONSTRUCTION
# ============================================================================

def reconstruct_month(
    month: int,
    payment_puf: pd.DataFrame,
):

    print()
    print(
        f"[{YEAR}-{month:02d}]"
    )

    cpsc = load_cpsc_month(
        month
    )

    snp_mapping = load_snp_mapping(
        month
    )

    cpsc = assign_snp_types(
        cpsc,
        snp_mapping,
        month,
    )

    published_cells = (
        aggregate_published_cells(
            cpsc
        )
    )

    cpsc_published_enrollment = float(
        published_cells[
            "_enrollment"
        ].sum()
    )

    scp = load_scp_control(
        month
    )

    # ------------------------------------------------------------
    # Exact dimensional join to payment PUF
    # ------------------------------------------------------------

    merged = published_cells.merge(
        payment_puf,
        on=[
            "_county",
            "_plan_type",
            "_snp_type",
        ],
        how="left",
        indicator=True,
        validate="many_to_one",
    )

    unmatched = merged[
        merged["_merge"]
        != "both"
    ].copy()

    if not unmatched.empty:

        print()
        print(
            "UNMATCHED PAYMENT DIMENSIONS:"
        )

        print(
            unmatched[
                [
                    "_county",
                    "_plan_type",
                    "_snp_type",
                    "_enrollment",
                ]
            ]
            .to_string(
                index=False
            )
        )

        unmatched_enrollment = float(
            unmatched[
                "_enrollment"
            ].sum()
        )

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            f"{len(unmatched)} published "
            "enrollment cells representing "
            f"{unmatched_enrollment:,.0f} beneficiaries "
            "do not resolve to the 2022 "
            "Washington payment PUF"
        )

    merged["_payment"] = (
        merged["_enrollment"]
        * merged["_pmpm"]
    )

    published_payment = float(
        merged["_payment"]
        .sum()
    )

    published_weighted_pmpm = (
        published_payment
        / cpsc_published_enrollment
    )

    # ------------------------------------------------------------
    # TWO-LAYER SUPPRESSION MODEL
    #
    # SCP itself may have a 0-10 bounded hidden cell.
    # Therefore CPSC residual is also bounded.
    # ------------------------------------------------------------

    residual_lower = (
        scp["control_lower"]
        - cpsc_published_enrollment
    )

    residual_central = (
        scp["control_central"]
        - cpsc_published_enrollment
    )

    residual_upper = (
        scp["control_upper"]
        - cpsc_published_enrollment
    )

    if residual_lower < -0.000001:

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            "CPSC published enrollment exceeds "
            "the lower SCP control bound"
        )

    lower_model = (
        cpsc_suppression_payment(
            residual_lower,
            published_payment,
            cpsc_published_enrollment,
            payment_puf,
        )
    )

    central_model = (
        cpsc_suppression_payment(
            residual_central,
            published_payment,
            cpsc_published_enrollment,
            payment_puf,
        )
    )

    upper_model = (
        cpsc_suppression_payment(
            residual_upper,
            published_payment,
            cpsc_published_enrollment,
            payment_puf,
        )
    )

    # Conservative combined interval:
    #
    # lower:
    #   lowest SCP enrollment bound
    #   x lowest PMPM correction
    #
    # central:
    #   midpoint SCP bound
    #   x published weighted PMPM
    #
    # upper:
    #   highest SCP enrollment bound
    #   x highest PMPM correction

    suppression_lower = (
        lower_model["lower"]
    )

    suppression_central = (
        central_model["central"]
    )

    suppression_upper = (
        upper_model["upper"]
    )

    corrected_lower = (
        published_payment
        + suppression_lower
    )

    corrected_central = (
        published_payment
        + suppression_central
    )

    corrected_upper = (
        published_payment
        + suppression_upper
    )

    corrected_central_pmpm = (
        corrected_central
        / scp["control_central"]
    )

    cpsc_coverage_lower_pct = (
        cpsc_published_enrollment
        / scp["control_upper"]
        * 100.0
    )

    cpsc_coverage_central_pct = (
        cpsc_published_enrollment
        / scp["control_central"]
        * 100.0
    )

    cpsc_coverage_upper_pct = (
        cpsc_published_enrollment
        / scp["control_lower"]
        * 100.0
    )

    uncertainty_width = (
        corrected_upper
        - corrected_lower
    )

    uncertainty_pct = (
        uncertainty_width
        / corrected_central
        * 100.0
    )

    # ------------------------------------------------------------
    # Invariants
    # ------------------------------------------------------------

    checks = {
        "published_enrollment_positive":
            cpsc_published_enrollment > 0,

        "scp_lower_positive":
            scp["control_lower"] > 0,

        "scp_bounds_ordered":
            (
                scp["control_lower"]
                <= scp["control_central"]
                <= scp["control_upper"]
            ),

        "cpsc_within_scp_lower":
            (
                cpsc_published_enrollment
                <= scp["control_lower"]
            ),

        "all_payment_cells_resolved":
            unmatched.empty,

        "published_payment_positive":
            published_payment > 0,

        "residual_bounds_ordered":
            (
                residual_lower
                <= residual_central
                <= residual_upper
            ),

        "payment_bounds_ordered":
            (
                corrected_lower
                <= corrected_central
                <= corrected_upper
            ),

        "corrected_pmpm_positive":
            corrected_central_pmpm > 0,

        "scp_suppression_bound_valid":
            (
                scp["suppressed_cells"]
                >= 0
            ),
    }

    failed = [
        name
        for name, passed
        in checks.items()
        if not passed
    ]

    if failed:

        raise RuntimeError(
            f"{YEAR}-{month:02d}: "
            "invariant failures: "
            + ", ".join(failed)
        )

    print(
        "  CPSC published enrollment:       ",
        f"{cpsc_published_enrollment:,.0f}",
    )

    print(
        "  SCP published subtotal:          ",
        f"{scp['published_subtotal']:,.0f}",
    )

    print(
        "  SCP suppressed target cells:     ",
        f"{scp['suppressed_cells']:,}",
    )

    print(
        "  SCP enrollment bounds:           ",
        f"{scp['control_lower']:,.0f}"
        " / "
        f"{scp['control_central']:,.0f}"
        " / "
        f"{scp['control_upper']:,.0f}",
    )

    print(
        "  CPSC residual bounds:            ",
        f"{residual_lower:,.0f}"
        " / "
        f"{residual_central:,.0f}"
        " / "
        f"{residual_upper:,.0f}",
    )

    print(
        "  CPSC coverage central:            ",
        f"{cpsc_coverage_central_pct:.6f}%",
    )

    print(
        "  Payment cells used:               ",
        f"{len(merged):,}",
    )

    print(
        "  Published weighted PMPM:         $",
        f"{published_weighted_pmpm:,.2f}",
    )

    print(
        "  Published payment:               $",
        f"{published_payment:,.2f}",
    )

    print(
        "  Combined suppression correction:"
    )

    print(
        "    lower:                         $",
        f"{suppression_lower:,.2f}",
    )

    print(
        "    central:                       $",
        f"{suppression_central:,.2f}",
    )

    print(
        "    upper:                         $",
        f"{suppression_upper:,.2f}",
    )

    print(
        "  Corrected payment:"
    )

    print(
        "    lower:                         $",
        f"{corrected_lower:,.2f}",
    )

    print(
        "    central:                       $",
        f"{corrected_central:,.2f}",
    )

    print(
        "    upper:                         $",
        f"{corrected_upper:,.2f}",
    )

    print(
        "  Corrected central PMPM:          $",
        f"{corrected_central_pmpm:,.2f}",
    )

    print(
        "  Combined uncertainty:             ",
        f"{uncertainty_pct:.6f}%",
    )

    print(
        "  PASS: 10/10 reconstruction checks"
    )

    cell_output = merged[
        [
            "_county",
            "_plan_type",
            "_snp_type",
            "_enrollment",
            "_risk",
            "_ab_std",
            "_rebate",
            "_ab_actual",
            "_pmpm",
            "_payment",
        ]
    ].copy()

    cell_output.insert(
        0,
        "month",
        month,
    )

    cell_output.insert(
        0,
        "year",
        YEAR,
    )

    result = {
        "year": YEAR,
        "month": month,
        "status": "PASS",

        "cpsc_published_enrollment":
            cpsc_published_enrollment,

        "scp_published_subtotal":
            scp["published_subtotal"],

        "scp_suppressed_cells":
            scp["suppressed_cells"],

        "scp_control_lower":
            scp["control_lower"],

        "scp_control_central":
            scp["control_central"],

        "scp_control_upper":
            scp["control_upper"],

        "cpsc_residual_lower":
            residual_lower,

        "cpsc_residual_central":
            residual_central,

        "cpsc_residual_upper":
            residual_upper,

        "cpsc_coverage_lower_pct":
            cpsc_coverage_lower_pct,

        "cpsc_coverage_central_pct":
            cpsc_coverage_central_pct,

        "cpsc_coverage_upper_pct":
            cpsc_coverage_upper_pct,

        "payment_cells":
            len(merged),

        "published_weighted_pmpm":
            published_weighted_pmpm,

        "published_payment":
            published_payment,

        "suppression_lower":
            suppression_lower,

        "suppression_central":
            suppression_central,

        "suppression_upper":
            suppression_upper,

        "corrected_lower":
            corrected_lower,

        "corrected_central":
            corrected_central,

        "corrected_upper":
            corrected_upper,

        "corrected_central_pmpm":
            corrected_central_pmpm,

        "uncertainty_width":
            uncertainty_width,

        "uncertainty_pct":
            uncertainty_pct,

        "checks_passed":
            10,

        "checks_total":
            10,
    }

    return (
        result,
        cell_output,
        scp["suppressed_rows"],
    )


# ============================================================================
# OUTPUT
# ============================================================================

def write_outputs(
    monthly_rows,
    cell_frames,
    scp_suppressed_rows,
):

    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    monthly_df = pd.DataFrame(
        monthly_rows
    )

    monthly_df.to_csv(
        MONTHLY_OUTPUT,
        index=False,
    )

    cells = pd.concat(
        cell_frames,
        ignore_index=True,
    )

    cells.to_csv(
        CELL_OUTPUT,
        index=False,
    )

    suppression_columns = [
        "year",
        "month",
        "county",
        "plan_type",
        "ssa_code",
        "fips_code",
        "source_value",
        "analytical_lower",
        "analytical_central",
        "analytical_upper",
        "method",
    ]

    suppression_df = pd.DataFrame(
        scp_suppressed_rows,
        columns=suppression_columns,
    )

    suppression_df.to_csv(
        SCP_SUPPRESSION_OUTPUT,
        index=False,
    )

    return (
        monthly_df,
        cells,
        suppression_df,
    )


def build_summary(
    monthly_df: pd.DataFrame,
    suppression_df: pd.DataFrame,
) -> str:

    lines = []

    lines.append(
        "=" * 108
    )

    lines.append(
        "CMS MEDICARE ADVANTAGE "
        "CY2022 WASHINGTON PART C "
        "PAYMENT RECONSTRUCTION v0.2"
    )

    lines.append(
        "=" * 108
    )

    lines.append("")

    lines.append(
        "Method:"
    )

    lines.append(
        "  Published CPSC enrollment is "
        "linked to the CMS 2022 county payment PUF."
    )

    lines.append(
        "  PMPM = "
        "(standardized A/B PMPM x risk score) "
        "+ rebate PMPM."
    )

    lines.append(
        "  SCP provides the HMO/HMOPOS + "
        "Local PPO aggregate enrollment control."
    )

    lines.append(
        "  SCP '.' cells remain suppressed "
        "and are modeled at 0 / 5 / 10 enrollees."
    )

    lines.append(
        "  The value 5 is a sensitivity midpoint, "
        "not a recovered CMS enrollment value."
    )

    lines.append("")

    lines.append(
        "MONTHLY RESULTS"
    )

    lines.append(
        "-" * 108
    )

    lines.append(
        (
            "Month    CPSC Enroll   SCP Published   "
            "SCP Supp   SCP Central   Residual Central   "
            "Central Payment"
        )
    )

    for _, row in monthly_df.iterrows():

        lines.append(
            (
                f"{YEAR}-{int(row['month']):02d}   "
                f"{row['cpsc_published_enrollment']:>11,.0f}   "
                f"{row['scp_published_subtotal']:>13,.0f}   "
                f"{row['scp_suppressed_cells']:>8,.0f}   "
                f"{row['scp_control_central']:>11,.0f}   "
                f"{row['cpsc_residual_central']:>16,.0f}   "
                f"${row['corrected_central']:>17,.2f}"
            )
        )

    published_annual = float(
        monthly_df[
            "published_payment"
        ].sum()
    )

    lower_annual = float(
        monthly_df[
            "corrected_lower"
        ].sum()
    )

    central_annual = float(
        monthly_df[
            "corrected_central"
        ].sum()
    )

    upper_annual = float(
        monthly_df[
            "corrected_upper"
        ].sum()
    )

    cpsc_member_months = float(
        monthly_df[
            "cpsc_published_enrollment"
        ].sum()
    )

    scp_published_member_months = float(
        monthly_df[
            "scp_published_subtotal"
        ].sum()
    )

    scp_lower_member_months = float(
        monthly_df[
            "scp_control_lower"
        ].sum()
    )

    scp_central_member_months = float(
        monthly_df[
            "scp_control_central"
        ].sum()
    )

    scp_upper_member_months = float(
        monthly_df[
            "scp_control_upper"
        ].sum()
    )

    residual_lower_annual = (
        scp_lower_member_months
        - cpsc_member_months
    )

    residual_central_annual = (
        scp_central_member_months
        - cpsc_member_months
    )

    residual_upper_annual = (
        scp_upper_member_months
        - cpsc_member_months
    )

    annual_coverage_central = (
        cpsc_member_months
        / scp_central_member_months
        * 100.0
    )

    annual_width = (
        upper_annual
        - lower_annual
    )

    annual_uncertainty_pct = (
        annual_width
        / central_annual
        * 100.0
    )

    annual_central_pmpm = (
        central_annual
        / scp_central_member_months
    )

    total_scp_suppressed_cells = int(
        monthly_df[
            "scp_suppressed_cells"
        ].sum()
    )

    lines.append("")
    lines.append(
        "CY2022 RECONSTRUCTION"
    )
    lines.append(
        "-" * 108
    )

    lines.append(
        "CPSC published member-months:       "
        f"{cpsc_member_months:,.0f}"
    )

    lines.append(
        "SCP published member-months:        "
        f"{scp_published_member_months:,.0f}"
    )

    lines.append(
        "SCP suppressed target cells:        "
        f"{total_scp_suppressed_cells:,}"
    )

    lines.append(
        "SCP member-month bounds:            "
        f"{scp_lower_member_months:,.0f}"
        " / "
        f"{scp_central_member_months:,.0f}"
        " / "
        f"{scp_upper_member_months:,.0f}"
    )

    lines.append(
        "CPSC residual member-month bounds:  "
        f"{residual_lower_annual:,.0f}"
        " / "
        f"{residual_central_annual:,.0f}"
        " / "
        f"{residual_upper_annual:,.0f}"
    )

    lines.append(
        "CPSC annual central coverage:       "
        f"{annual_coverage_central:.6f}%"
    )

    lines.append("")

    lines.append(
        "Published-enrollment payment:       "
        f"${published_annual:,.2f}"
    )

    lines.append(
        "Suppression-corrected lower:        "
        f"${lower_annual:,.2f}"
    )

    lines.append(
        "Suppression-corrected central:      "
        f"${central_annual:,.2f}"
    )

    lines.append(
        "Suppression-corrected upper:        "
        f"${upper_annual:,.2f}"
    )

    lines.append("")

    lines.append(
        "Central annual PMPM:                "
        f"${annual_central_pmpm:,.2f}"
    )

    lines.append(
        "Combined uncertainty width:         "
        f"${annual_width:,.2f}"
    )

    lines.append(
        "Combined uncertainty as % central:  "
        f"{annual_uncertainty_pct:.6f}%"
    )

    lines.append("")

    lines.append(
        "Months passing reconstruction:      "
        f"{int((monthly_df['status'] == 'PASS').sum())}/12"
    )

    lines.append("")

    lines.append(
        "SCP SUPPRESSION OBSERVATIONS"
    )

    lines.append(
        "-" * 108
    )

    if suppression_df.empty:

        lines.append(
            "None."
        )

    else:

        for _, row in suppression_df.iterrows():

            lines.append(
                (
                    f"{YEAR}-{int(row['month']):02d}: "
                    f"{row['county']} / "
                    f"{row['plan_type']} / "
                    f"source={repr(row['source_value'])} / "
                    "analytical bound=0/5/10"
                )
            )

    lines.append("")

    lines.append(
        "=" * 108
    )

    lines.append(
        "STATUS: CY2022 CMS MA PART C "
        "ANNUAL RECONSTRUCTION PASS"
    )

    lines.append("")

    lines.append(
        "This is a historical methodological "
        "replication using CMS source data."
    )

    lines.append(
        "SCP suppressed cells are explicitly "
        "bounded and are not treated as observed zeros."
    )

    lines.append(
        "This does NOT establish complete Medicare "
        "state-ledger readiness, complete Medicare "
        "coverage, or FFY accounting."
    )

    lines.append(
        "=" * 108
    )

    return "\n".join(
        lines
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    print(
        "=" * 108
    )

    print(
        "CMS MEDICARE ADVANTAGE "
        "CY2022 WASHINGTON PART C "
        "PAYMENT RECONSTRUCTION v0.2"
    )

    print(
        "=" * 108
    )

    print()

    print(
        "Read-only reconstruction. "
        "No database writes."
    )

    print()

    print(
        "SCP suppressed target cells are "
        "modeled at 0 / 5 / 10 enrollees."
    )

    print(
        "The midpoint is analytical only; "
        "source values remain suppressed."
    )

    print()

    print(
        "Loading 2022 Washington "
        "Part C County Payment PUF..."
    )

    payment_puf = (
        load_payment_puf()
    )

    print(
        "  WA payment cells:",
        len(payment_puf),
    )

    print(
        "  WA counties:",
        payment_puf[
            "_county"
        ].nunique(),
    )

    print(
        "  SNP dimensions:",
        sorted(
            payment_puf[
                "_snp_type"
            ].unique()
        ),
    )

    monthly_rows = []
    cell_frames = []
    scp_suppressed_rows = []

    try:

        for month in range(
            1,
            13,
        ):

            (
                result,
                cells,
                suppressed_rows,
            ) = reconstruct_month(
                month,
                payment_puf,
            )

            monthly_rows.append(
                result
            )

            cell_frames.append(
                cells
            )

            scp_suppressed_rows.extend(
                suppressed_rows
            )

    except Exception as exc:

        print()
        print(
            "=" * 108
        )

        print(
            "STATUS: CY2022 CMS MA "
            "PART C RECONSTRUCTION FAIL"
        )

        print()

        print(
            "ERROR:",
            exc,
        )

        print()

        print(
            "DO NOT TREAT THE CY2022 "
            "PAYMENT RECONSTRUCTION AS VALIDATED."
        )

        print(
            "=" * 108
        )

        return 1

    (
        monthly_df,
        _,
        suppression_df,
    ) = write_outputs(
        monthly_rows,
        cell_frames,
        scp_suppressed_rows,
    )

    summary = build_summary(
        monthly_df,
        suppression_df,
    )

    SUMMARY_OUTPUT.write_text(
        summary,
        encoding="utf-8",
    )

    print()
    print(
        summary
    )

    print()

    print(
        "Monthly output:",
        MONTHLY_OUTPUT,
    )

    print(
        "Payment-cell output:",
        CELL_OUTPUT,
    )

    print(
        "SCP suppression output:",
        SCP_SUPPRESSION_OUTPUT,
    )

    print(
        "Summary:",
        SUMMARY_OUTPUT,
    )

    return 0


if __name__ == "__main__":

    sys.exit(
        main()
    )