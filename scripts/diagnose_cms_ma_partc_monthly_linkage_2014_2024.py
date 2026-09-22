from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

ACQ = (
    ROOT / "data/raw/cms/medicare_advantage/validation/"
    "source_acquisition/cms_ma_partc_source_acquisition_manifest.csv"
)

OUTDIR = (
    ROOT / "data/raw/cms/medicare_advantage/validation/"
    "monthly_linkage_diagnostic"
)

MONTH_OUT = OUTDIR / "cms_ma_partc_monthly_linkage_diagnostic.csv"
EXCEPTION_OUT = OUTDIR / "cms_ma_partc_monthly_linkage_exceptions.csv"

TARGET_PLAN_TYPES = {"HMO", "HMOPOS", "LOCAL PPO"}


def clean(x) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except (TypeError, ValueError):
        pass
    return " ".join(str(x).strip().split())

def normalize_plan_id(value):
    s = clean(value)

    if not s:
        return ""

    # CMS plan IDs are conventionally three-digit numeric identifiers.
    # Excel source workbooks may expose the same identifier as 4, 30,
    # 31, 004, 030, 031, etc. Normalize representation only; do not
    # alter the underlying source artifact.
    if re.fullmatch(r"\d+", s):
        return s.zfill(3)

    # Handle numeric-looking spreadsheet values such as "4.0".
    if re.fullmatch(r"\d+\.0+", s):
        return str(int(float(s))).zfill(3)

    return s

def key(x) -> str:
    return clean(x).casefold()


def path_from_manifest(x) -> Path:
    p = Path(clean(x))
    return p if p.is_absolute() else ROOT / p


def canonical_plan_type(x: str) -> str:
    x = clean(x).upper().replace("-", " ")
    x = re.sub(r"\s+", " ", x)

    if x in {"HMO", "HMO POS", "HMOPOS"}:
        return "HMO"

    if x in {"LOCAL PPO", "LOCAL PREFERRED PROVIDER ORGANIZATION"}:
        return "LOCAL PPO"

    return x


def canonical_snp_type(x: str) -> str:
    x = clean(x)
    k = x.casefold()

    if not x:
        return "NON-SNP"

    if "dual" in k:
        return "DUAL-ELIGIBLE"

    if "institution" in k:
        return "INSTITUTIONAL"

    if "chronic" in k:
        return "CHRONIC/DISABLING"

    return x.upper()


def excel_engine(name: str) -> str:
    return "xlrd" if Path(name).suffix.lower() == ".xls" else "openpyxl"


def find_member(zf, required_tokens, extensions):
    matches = []

    for info in zf.infolist():
        if info.is_dir():
            continue

        name = Path(info.filename).name
        compact = re.sub(r"[^a-z0-9]+", "", name.casefold())

        if Path(name).suffix.lower() not in extensions:
            continue

        if all(token in compact for token in required_tokens):
            matches.append(info.filename)

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one member for {required_tokens}; found {matches}"
        )

    return matches[0]


def read_csv_member(zf, member):
    payload = zf.read(member)

    for encoding in ("cp1252", "utf-8-sig", "latin1"):
        try:
            return pd.read_csv(
                io.BytesIO(payload),
                dtype=str,
                encoding=encoding,
                low_memory=False,
            ).fillna("")
        except UnicodeDecodeError:
            pass

    raise RuntimeError(f"Could not decode {member}")


def column(df, *aliases):
    lookup = {key(c): c for c in df.columns}

    for alias in aliases:
        if key(alias) in lookup:
            return lookup[key(alias)]

    raise KeyError(
        f"Missing column. Tried {aliases}. "
        f"Observed={list(df.columns)}"
    )


def load_cpsc(path: Path):
    with zipfile.ZipFile(path) as zf:
        contract_member = find_member(
            zf, ["contract", "info"], {".csv"}
        )
        enrollment_member = find_member(
            zf, ["enrollment", "info"], {".csv"}
        )

        contracts = read_csv_member(zf, contract_member)
        enrollment = read_csv_member(zf, enrollment_member)

    return contracts, enrollment


def load_snp(path: Path):
    with zipfile.ZipFile(path) as zf:
        books = [
            x.filename
            for x in zf.infolist()
            if not x.is_dir()
            and Path(x.filename).suffix.lower() in {".xls", ".xlsx"}
            and "raw data" not in Path(x.filename).name.casefold()
        ]

        if len(books) != 1:
            raise RuntimeError(
                f"Expected one primary SNP workbook; found {books}"
            )

        member = books[0]
        payload = zf.read(member)

    engine = excel_engine(member)
    book = pd.ExcelFile(io.BytesIO(payload), engine=engine)

    def normalize_header(value):
        k = key(value)

        aliases = {
            "segment id": "segment_id",
            "segment_id": "segment_id",
            "plan geographic name": "geographic_name",
            "geographic name": "geographic_name",
            "plan enrollment": "enrollment",
            "enrollment": "enrollment",
        }

        return aliases.get(k, k)

    required = {
        "contract number",
        "contract name",
        "organization type",
        "plan id",
        "segment_id",
        "plan name",
        "plan type",
        "geographic_name",
        "state(s)",
        "enrollment",
        "special needs plan type",
        "specialty diseases",
    }

    candidates = []

    for sheet in book.sheet_names:
        preview = pd.read_excel(
            io.BytesIO(payload),
            sheet_name=sheet,
            header=None,
            nrows=40,
            engine=engine,
        )

        for idx, row in preview.iterrows():
            raw_values = [
                clean(x)
                for x in row.tolist()
                if clean(x)
            ]

            normalized_values = {
                normalize_header(x)
                for x in raw_values
            }

            if required.issubset(normalized_values):
                raw_keys = {key(x) for x in raw_values}

                candidates.append({
                    "sheet": sheet,
                    "header_row": int(idx),
                    "exact_enrollment": (
                        "enrollment" in raw_keys
                    ),
                    "raw_values": raw_values,
                })

    if not candidates:
        raise RuntimeError(
            "Could not locate normalized SNP semantic header. "
            f"Workbook={member!r}; sheets={book.sheet_names!r}"
        )

    # CMS may expose the same logical table in both a presentation
    # worksheet and a machine-oriented worksheet. Prefer the primary
    # human-facing report when it has the exact normalized Enrollment
    # header.
    preferred = [
        x for x in candidates
        if key(x["sheet"]) == "special needs plan report"
        and x["exact_enrollment"]
    ]

    if len(preferred) == 1:
        selected = preferred[0]

    else:
        # Historical workbooks often use "Plan Enrollment" rather than
        # "Enrollment". If there is exactly one semantic table in the
        # primary report, use it.
        primary = [
            x for x in candidates
            if key(x["sheet"]) == "special needs plan report"
        ]

        if len(primary) == 1:
            selected = primary[0]

        else:
            exact = [
                x for x in candidates
                if x["exact_enrollment"]
            ]

            if len(exact) == 1:
                selected = exact[0]

            elif len(candidates) == 1:
                selected = candidates[0]

            else:
                diagnostic = [
                    (
                        x["sheet"],
                        x["header_row"],
                        x["exact_enrollment"],
                    )
                    for x in candidates
                ]

                raise RuntimeError(
                    "Ambiguous normalized SNP header after "
                    f"alias-aware selection: {diagnostic}"
                )

    sheet = selected["sheet"]
    header_row = selected["header_row"]

    return pd.read_excel(
        io.BytesIO(payload),
        sheet_name=sheet,
        header=header_row,
        dtype=str,
        engine=engine,
    ).fillna("")

def load_payment(path: Path):
    with zipfile.ZipFile(path) as zf:
        books = []

        for info in zf.infolist():
            if info.is_dir():
                continue

            name = Path(info.filename).name
            compact = re.sub(
                r"[^a-z0-9]+",
                "",
                name.casefold(),
            )

            if (
                Path(name).suffix.lower() in {".xls", ".xlsx"}
                and "partc" in compact
                and "county" in compact
            ):
                books.append(info.filename)

        if len(books) != 1:
            raise RuntimeError(
                "Expected one Part C county workbook; "
                f"found {books}"
            )

        member = books[0]
        payload = zf.read(member)

    engine = excel_engine(member)

    book = pd.ExcelFile(
        io.BytesIO(payload),
        engine=engine,
    )

    risk_aliases = {
        "average part c risk score",
        "average part risk score",
    }

    ab_aliases = {
        "average ab pm/pm payment",
        "average a/b pm/pm payment",
    }

    rebate_aliases = {
        "average rebate pm/pm payment",
    }

    candidates = []

    for sheet in book.sheet_names:
        preview = pd.read_excel(
            io.BytesIO(payload),
            sheet_name=sheet,
            header=None,
            nrows=40,
            engine=engine,
        )

        for idx, row in preview.iterrows():
            keys = {
                key(value)
                for value in row.tolist()
                if clean(value)
            }

            required = {
                "county code",
                "state abbreviation",
                "county name",
                "plan type",
                "snp plan type",
            }

            if (
                required.issubset(keys)
                and bool(keys & risk_aliases)
                and bool(keys & ab_aliases)
                and bool(keys & rebate_aliases)
            ):
                candidates.append(
                    (sheet, int(idx))
                )

    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one semantic Part C county "
            f"payment table; found {candidates}"
        )

    sheet, header_row = candidates[0]

    return pd.read_excel(
        io.BytesIO(payload),
        sheet_name=sheet,
        header=header_row,
        dtype=str,
        engine=engine,
    ).fillna("")


def normalize_payment(df):
    county_code = column(df, "County Code")
    state = column(df, "State Abbreviation")
    county = column(df, "County Name")
    plan = column(df, "Plan Type")
    snp = column(df, "SNP Plan Type")

    out = pd.DataFrame({
        "county_code": df[county_code].map(clean),
        "state": df[state].map(clean).str.upper(),
        "county": df[county].map(clean),
        "plan_type": df[plan].map(canonical_plan_type),
        "snp_type": df[snp].map(canonical_snp_type),
    })

    return out[out["state"] == "WA"].copy()


def build_snp_lookup(snp):
    contract = column(snp, "Contract Number")
    plan = column(snp, "Plan ID")
    snp_type = column(snp, "Special Needs Plan Type")

    # Employer-only group plans are not required to appear in SNP reports.
    # We only use rows actually published here.
    x = pd.DataFrame({
        "contract": snp[contract].map(clean),
        "plan_id": snp[plan].map(normalize_plan_id),
        "snp_type": snp[snp_type].map(canonical_snp_type),
    })

    x = x[
        x["contract"].ne("")
        & x["plan_id"].ne("")
        & x["snp_type"].ne("")
    ].drop_duplicates()

    counts = (
        x.groupby(["contract", "plan_id"])["snp_type"]
        .nunique()
        .reset_index(name="n")
    )

    ambiguous = counts[counts["n"] > 1]

    lookup = (
        x.merge(
            counts[counts["n"] == 1][["contract", "plan_id"]],
            on=["contract", "plan_id"],
            how="inner",
        )
        .drop_duplicates(["contract", "plan_id"])
    )

    return lookup, ambiguous


def main():
    manifest = pd.read_csv(ACQ, dtype=str).fillna("")

    manifest["payment_year_norm"] = (
        manifest["payment_year"]
        .map(clean)
        .str.replace(r"\.0$", "", regex=True)
    )

    by_period = {}
    for source in ("CPSC", "SNP"):
        subset = manifest[
            (manifest["source_type"] == source)
            & (manifest["status"].str.upper() == "PASS")
        ]

        for _, row in subset.iterrows():
            by_period[(source, clean(row["period"]))] = path_from_manifest(
                row["local_path"]
            )

    payment_paths = {}
    subset = manifest[
        (manifest["source_type"] == "PLAN_PAYMENT")
        & (manifest["status"].str.upper() == "PASS")
    ]

    for _, row in subset.iterrows():
        payment_paths[row["payment_year_norm"]] = path_from_manifest(
            row["local_path"]
        )

    periods = pd.period_range(
        "2014-10",
        "2024-09",
        freq="M",
    )

    monthly = []
    exceptions = []

    payment_cache = {}

    for number, period in enumerate(periods, start=1):
        period_text = str(period)
        year = str(period.year)

        print(
            f"[{number:03d}/120] {period_text}",
            end=" ",
            flush=True,
        )

        cpsc_path = by_period[("CPSC", period_text)]
        snp_path = by_period[("SNP", period_text)]
        payment_path = payment_paths[year]

        contracts, enrollment = load_cpsc(cpsc_path)
        snp = load_snp(snp_path)

        if year not in payment_cache:
            payment_cache[year] = normalize_payment(
                load_payment(payment_path)
            )

        pay = payment_cache[year]

        # ----- Contract/plan attributes -----

        c_contract = column(contracts, "Contract ID")
        c_plan = column(contracts, "Plan ID")
        c_type = column(contracts, "Plan Type")
        c_snp = column(contracts, "SNP Plan")
        c_eghp = column(contracts, "EGHP")

        contract_dim = pd.DataFrame({
            "contract": contracts[c_contract].map(clean),
            "plan_id": contracts[c_plan].map(normalize_plan_id),
            "plan_type": contracts[c_type].map(canonical_plan_type),
            "snp_flag": contracts[c_snp].map(clean).str.upper(),
            "eghp": contracts[c_eghp].map(clean).str.upper(),
        })

        dup_contract = contract_dim.duplicated(
            ["contract", "plan_id"],
            keep=False,
        )

        duplicate_contract_keys = int(
            contract_dim.loc[
                dup_contract,
                ["contract", "plan_id"]
            ].drop_duplicates().shape[0]
        )

        contract_dim = contract_dim.drop_duplicates(
            ["contract", "plan_id"]
        )

        # ----- Enrollment -----

        e_contract = column(enrollment, "Contract Number")
        e_plan = column(enrollment, "Plan ID")
        e_state = column(enrollment, "State")
        e_county = column(enrollment, "County")
        e_ssa = column(
            enrollment,
            "SSA State County Code",
        )
        e_fips = column(
            enrollment,
            "FIPS State County Code",
        )
        e_enroll = column(enrollment, "Enrollment")

        e = pd.DataFrame({
            "contract": enrollment[e_contract].map(clean),
            "plan_id": enrollment[e_plan].map(normalize_plan_id),
            "state": enrollment[e_state].map(clean).str.upper(),
            "county": enrollment[e_county].map(clean),
            "ssa_code": enrollment[e_ssa].map(clean),
            "fips_code": enrollment[e_fips].map(clean),
            "enrollment_raw": enrollment[e_enroll].map(clean),
        })

        e = e[e["state"] == "WA"].copy()

        e["enrollment"] = pd.to_numeric(
            e["enrollment_raw"],
            errors="coerce",
        )

        e = e.merge(
            contract_dim,
            on=["contract", "plan_id"],
            how="left",
            validate="many_to_one",
            indicator="contract_join",
        )

        unresolved_contract_rows = int(
            (e["contract_join"] != "both").sum()
        )

        # Current validated reconstruction scope.
        target = e[
            e["plan_type"].isin({"HMO", "LOCAL PPO"})
        ].copy()

        target["published_numeric"] = target["enrollment"].notna()

        # ----- SNP subtype -----

        snp_lookup, ambiguous_snp = build_snp_lookup(snp)

        target = target.merge(
            snp_lookup,
            on=["contract", "plan_id"],
            how="left",
            validate="many_to_one",
            indicator="snp_join",
        )

        # Non-SNP contract rows map directly to NON-SNP.
        non_snp_mask = ~target["snp_flag"].isin(
            {"YES", "Y", "TRUE", "1"}
        )

        target.loc[
            non_snp_mask,
            "snp_type"
        ] = "NON-SNP"

        # SNP rows lacking a published subtype remain unresolved.
        snp_required = ~non_snp_mask

        unresolved_snp = (
            snp_required
            & target["snp_type"].map(clean).eq("")
        )

        # ----- Payment linkage -----
        #
        # CMS County Code is not Census FIPS.  We therefore use the
        # county-name dimension here; code crosswalking is a separate
        # provenance concern already identified in prior work.

        target["county_key"] = target["county"].map(
            lambda x: key(x).replace(" county", "")
        )

        pay_work = pay.copy()

        pay_work["county_key"] = pay_work["county"].map(
            lambda x: key(x).replace(" county", "")
        )

        pay_keys = pay_work[
            [
                "county_key",
                "plan_type",
                "snp_type",
            ]
        ].drop_duplicates()

        duplicate_payment_keys = int(
            pay_keys.duplicated(
                ["county_key", "plan_type", "snp_type"],
                keep=False,
            ).sum()
        )

        target = target.merge(
            pay_keys.assign(payment_cell=True),
            on=[
                "county_key",
                "plan_type",
                "snp_type",
            ],
            how="left",
            validate="many_to_one",
        )

        target["payment_cell"] = (
            target["payment_cell"]
            .fillna(False)
            .astype(bool)
        )

        published = target[
            target["published_numeric"]
        ].copy()

        matched = published[
            published["payment_cell"]
        ]

        unmatched = published[
            ~published["payment_cell"]
        ]

        published_enrollment = float(
            published["enrollment"].sum()
        )

        matched_enrollment = float(
            matched["enrollment"].sum()
        )

        unmatched_enrollment = float(
            unmatched["enrollment"].sum()
        )

        coverage = (
            matched_enrollment / published_enrollment
            if published_enrollment
            else None
        )

        monthly.append({
            "period": period_text,
            "payment_year": year,
            "wa_cpsc_rows": len(e),
            "duplicate_contract_keys": duplicate_contract_keys,
            "unresolved_contract_rows": unresolved_contract_rows,
            "target_rows": len(target),
            "target_published_numeric_rows": len(published),
            "target_suppressed_rows": int(
                (~target["published_numeric"]).sum()
            ),
            "ambiguous_snp_contract_plan_keys": len(ambiguous_snp),
            "unresolved_snp_rows": int(unresolved_snp.sum()),
            "payment_cells": len(pay_keys),
            "duplicate_payment_keys": duplicate_payment_keys,
            "matched_published_rows": len(matched),
            "unmatched_published_rows": len(unmatched),
            "published_enrollment": published_enrollment,
            "matched_enrollment": matched_enrollment,
            "unmatched_enrollment": unmatched_enrollment,
            "published_enrollment_linkage_pct": (
                coverage * 100
                if coverage is not None
                else None
            ),
        })

        for _, row in unmatched.iterrows():
            exceptions.append({
                "period": period_text,
                "payment_year": year,
                "exception": "PUBLISHED_ENROLLMENT_WITHOUT_PAYMENT_CELL",
                "contract": row["contract"],
                "plan_id": row["plan_id"],
                "county": row["county"],
                "ssa_code": row["ssa_code"],
                "fips_code": row["fips_code"],
                "plan_type": row["plan_type"],
                "snp_type": row["snp_type"],
                "eghp": row["eghp"],
                "enrollment": row["enrollment"],
            })

        for _, row in target[unresolved_snp].iterrows():
            exceptions.append({
                "period": period_text,
                "payment_year": year,
                "exception": "UNRESOLVED_SNP_TYPE",
                "contract": row["contract"],
                "plan_id": row["plan_id"],
                "county": row["county"],
                "ssa_code": row["ssa_code"],
                "fips_code": row["fips_code"],
                "plan_type": row["plan_type"],
                "snp_type": "",
                "eghp": row["eghp"],
                "enrollment": row["enrollment"],
            })

        print(
            f"published={int(published_enrollment):,} "
            f"matched={int(matched_enrollment):,} "
            f"unmatched={int(unmatched_enrollment):,} "
            f"coverage={coverage * 100:.6f}%"
            if coverage is not None
            else "no published enrollment"
        )

    OUTDIR.mkdir(parents=True, exist_ok=True)

    monthly_df = pd.DataFrame(monthly)
    exceptions_df = pd.DataFrame(exceptions)

    monthly_df.to_csv(
        MONTH_OUT,
        index=False,
    )

    exceptions_df.to_csv(
        EXCEPTION_OUT,
        index=False,
    )

    print()
    print("=" * 88)
    print("DECADE-WIDE MONTHLY LINKAGE DIAGNOSTIC")
    print("=" * 88)
    print(f"Periods                              : {len(monthly_df)}")
    print(
        "Published target member-months       : "
        f"{monthly_df['published_enrollment'].sum():,.0f}"
    )
    print(
        "Matched published member-months      : "
        f"{monthly_df['matched_enrollment'].sum():,.0f}"
    )
    print(
        "Unmatched published member-months    : "
        f"{monthly_df['unmatched_enrollment'].sum():,.0f}"
    )

    total_published = monthly_df["published_enrollment"].sum()
    total_matched = monthly_df["matched_enrollment"].sum()

    pct = (
        total_matched / total_published * 100
        if total_published
        else float("nan")
    )

    print(
        "Published enrollment linkage         : "
        f"{pct:.6f}%"
    )
    print(
        "Months with unmatched published rows : "
        f"{(monthly_df['unmatched_published_rows'] > 0).sum()}"
    )
    print(
        "Months with unresolved SNP rows      : "
        f"{(monthly_df['unresolved_snp_rows'] > 0).sum()}"
    )
    print(
        "Months with unresolved contract rows : "
        f"{(monthly_df['unresolved_contract_rows'] > 0).sum()}"
    )
    print(
        "Months with duplicate payment keys   : "
        f"{(monthly_df['duplicate_payment_keys'] > 0).sum()}"
    )
    print()
    print("Lowest monthly published-enrollment linkage:")
    print(
        monthly_df[
            [
                "period",
                "published_enrollment",
                "matched_enrollment",
                "unmatched_enrollment",
                "published_enrollment_linkage_pct",
            ]
        ]
        .sort_values(
            [
                "published_enrollment_linkage_pct",
                "period",
            ]
        )
        .head(12)
        .to_string(index=False)
    )
    print()
    print("OUTPUTS")
    print("-" * 88)
    print(MONTH_OUT)
    print(EXCEPTION_OUT)
    print()
    print(
        "Diagnostic only: no CMS source artifacts modified, "
        "no database writes, no payment reconstruction, "
        "and no suppressed enrollment values imputed."
    )


if __name__ == "__main__":
    main()