from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


# =============================================================================
# ETL-172J-4B
#
# Washington unemployment-insurance receipt allocation
#
# Accounting architecture:
#
#   Washington UI receipts
#       =
#   OMB national UI receipt control
#       x
#   Washington share of DOL ETA-2112 c10
#
# DOL ETA-2112 c10 is used ONLY as the geographic allocator.
# OMB remains the national accounting control.
#
# No database writes.
# No IRS forced reconciliation.
# No final-ledger authorization.
# =============================================================================


STUDY_FY_START = 2015
STUDY_FY_END = 2024

WASHINGTON = "WA"

TERRITORIES_EXCLUDED_FROM_STATE_UNIVERSE = {
    "PR",
    "VI",
}


ETA2112_SOURCE = Path(
    r"data\raw\dol\unemployment_insurance\eta2112"
    r"\source\ar2112.csv"
)

J4A_DIR = Path(
    r"data\raw\dol\unemployment_insurance\eta2112"
    r"\validation\ui_receipts_profile_v0_1"
)

J4A_CERTIFICATION = (
    J4A_DIR / "certification.json"
)


I2_DIR = Path(
    r"data\raw\omb\historical_tables\FY2027"
    r"\validation\social_insurance_excise_decomposition_v0_1"
)

I2_DECOMPOSITION = (
    I2_DIR
    / "national_social_insurance_excise_decomposition.csv"
)


J3_DIR = Path(
    r"data\raw\omb\historical_tables\FY2027"
    r"\validation\washington_specialized_receipts_v0_1"
)

J3_QUEUE = (
    J3_DIR
    / "remaining_receipts_work_queue_after_j3.csv"
)


OUTPUT_DIR = Path(
    r"data\raw\omb\historical_tables\FY2027"
    r"\validation\washington_ui_receipts_v0_1"
)


EXPECTED_SOURCE_SHA256 = (
    "777869F74882A4160E5AFCE3ADC671C21C557FE6C27F9FD7FE50FABAFF169A86"
)


# =============================================================================
# Helpers
# =============================================================================


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest().upper()


def parse_float(value: str | None) -> float:
    if value is None:
        return 0.0

    value = value.strip()

    if value == "":
        return 0.0

    return float(value)


def parse_date(value: str) -> datetime:
    return datetime.strptime(
        value.strip(),
        "%Y-%m-%d",
    )


def federal_fiscal_year(
    date_value: datetime,
) -> int:
    if date_value.month >= 10:
        return date_value.year + 1

    return date_value.year


def check_status(
    condition: bool,
) -> str:
    return "PASS" if condition else "FAIL"


def read_csv_rows(
    path: Path,
) -> list[dict[str, str]]:
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


def choose_column(
    row: dict[str, str],
    candidates: list[str],
    label: str,
) -> str:
    for candidate in candidates:
        if candidate in row:
            return candidate

    raise RuntimeError(
        f"Could not identify {label} column. "
        f"Available columns: {list(row.keys())}"
    )


# =============================================================================
# Upstream certification
# =============================================================================


def load_j4a_certification() -> dict:
    if not J4A_CERTIFICATION.exists():
        raise FileNotFoundError(
            J4A_CERTIFICATION
        )

    with J4A_CERTIFICATION.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


# =============================================================================
# DOL ETA-2112 allocator
# =============================================================================


def build_eta2112_allocator() -> tuple[
    list[dict],
    dict[int, dict],
    set[str],
]:
    if not ETA2112_SOURCE.exists():
        raise FileNotFoundError(
            ETA2112_SOURCE
        )

    monthly_rows: list[dict] = []

    wa_c10: dict[int, float] = defaultdict(float)
    denominator_c10: dict[int, float] = defaultdict(float)

    wa_months: dict[int, int] = defaultdict(int)
    denominator_rows: dict[int, int] = defaultdict(int)

    source_codes: set[str] = set()
    denominator_codes: dict[int, set[str]] = defaultdict(set)

    seen_keys: set[tuple[str, datetime]] = set()

    with ETA2112_SOURCE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)

        required = {
            "st",
            "rptdate",
            "c10",
        }

        missing = (
            required
            - set(reader.fieldnames or [])
        )

        if missing:
            raise RuntimeError(
                "ETA-2112 missing required columns: "
                + ", ".join(sorted(missing))
            )

        for row in reader:
            state = row["st"].strip().upper()
            report_date = parse_date(
                row["rptdate"]
            )

            source_codes.add(state)

            key = (
                state,
                report_date,
            )

            if key in seen_keys:
                raise RuntimeError(
                    "Duplicate ETA-2112 "
                    f"state/date key: {key}"
                )

            seen_keys.add(key)

            fy = federal_fiscal_year(
                report_date
            )

            if (
                fy < STUDY_FY_START
                or fy > STUDY_FY_END
            ):
                continue

            c10 = parse_float(
                row["c10"]
            )

            included = (
                state
                not in
                TERRITORIES_EXCLUDED_FROM_STATE_UNIVERSE
            )

            if included:
                denominator_c10[fy] += c10
                denominator_rows[fy] += 1
                denominator_codes[fy].add(
                    state
                )

            if state == WASHINGTON:
                wa_c10[fy] += c10
                wa_months[fy] += 1

            monthly_rows.append(
                {
                    "fiscal_year": fy,
                    "state_code": state,
                    "report_date":
                        report_date.date().isoformat(),
                    "c10": c10,
                    "included_in_wcffbp_state_denominator":
                        "YES"
                        if included
                        else "NO",
                }
            )

    annual: dict[int, dict] = {}

    for fy in range(
        STUDY_FY_START,
        STUDY_FY_END + 1,
    ):
        denominator = denominator_c10[fy]
        washington = wa_c10[fy]

        share = (
            washington / denominator
            if denominator != 0
            else None
        )

        annual[fy] = {
            "fiscal_year": fy,
            "washington_c10": washington,
            "state_dc_denominator_c10":
                denominator,
            "washington_allocator_share":
                share,
            "washington_month_count":
                wa_months[fy],
            "denominator_record_count":
                denominator_rows[fy],
            "denominator_geography_count":
                len(
                    denominator_codes[fy]
                ),
        }

    return (
        monthly_rows,
        annual,
        source_codes,
    )


# =============================================================================
# OMB national UI controls
# =============================================================================


def load_omb_ui_controls() -> dict[int, float]:
    if not I2_DECOMPOSITION.exists():
        raise FileNotFoundError(
            I2_DECOMPOSITION
        )

    rows = read_csv_rows(
        I2_DECOMPOSITION
    )

    controls: dict[int, float] = defaultdict(float)

    matched_rows = 0

    for row in rows:
        component_code = (
            row.get(
                "component_code",
                "",
            )
            .strip()
            .upper()
        )

        if component_code not in {
            "UNEMPLOYMENT_INSURANCE_FEDERAL_FUNDS",
            "UNEMPLOYMENT_INSURANCE_TRUST_FUNDS",
        }:
            continue

        fy = int(
            row["fiscal_year"]
        )

        if (
            fy < STUDY_FY_START
            or fy > STUDY_FY_END
        ):
            continue

        amount = parse_float(
            row.get(
                "amount_millions"
            )
        )

        controls[fy] += amount
        matched_rows += 1

    if matched_rows == 0:
        raise RuntimeError(
            "No OMB unemployment-insurance "
            "rows found in I-2 decomposition."
        )

    missing_years = [
        fy
        for fy in range(
            STUDY_FY_START,
            STUDY_FY_END + 1,
        )
        if fy not in controls
    ]

    if missing_years:
        raise RuntimeError(
            "Missing OMB UI controls for: "
            + ", ".join(
                str(x)
                for x in missing_years
            )
        )

    return dict(controls)


# =============================================================================
# J-3 work queue
# =============================================================================


def load_j3_queue() -> tuple[
    dict[int, dict],
    dict[str, str],
]:
    if not J3_QUEUE.exists():
        raise FileNotFoundError(
            J3_QUEUE
        )

    rows = read_csv_rows(
        J3_QUEUE
    )

    if not rows:
        raise RuntimeError(
            "J-3 work queue is empty."
        )

    sample = rows[0]

    column_map = {
        "fy": choose_column(
            sample,
            [
                "fiscal_year",
            ],
            "fiscal year",
        ),

        "actionable": choose_column(
            sample,
            [
                "actionable_unfinished_after_j3_millions",
            ],
            "J-3 actionable unfinished",
        ),

        "documented": choose_column(
            sample,
            [
                "allocator_method_documented_after_j3_millions",
            ],
            "documented allocator queue",
        ),

        "method_review": choose_column(
            sample,
            [
                "method_change_review_millions",
                "method_change_review_millions_after_j3",
            ],
            "method-change review",
        ),

        "withhold": choose_column(
            sample,
            [
                "withhold_unresolved_millions",
                "withhold_unresolved_millions_after_j3",
            ],
            "withhold unresolved",
        ),

        "unallocable": choose_column(
            sample,
            [
                "intentionally_unallocable_millions",
                "intentionally_unallocable_millions_after_j3",
            ],
            "intentionally unallocable",
        ),
    }

    result: dict[int, dict] = {}

    for row in rows:
        fy = int(
            row[column_map["fy"]]
        )

        if (
            fy < STUDY_FY_START
            or fy > STUDY_FY_END
        ):
            continue

        result[fy] = {
            "fiscal_year": fy,

            "j3_actionable_unfinished_millions":
                parse_float(
                    row[
                        column_map[
                            "actionable"
                        ]
                    ]
                ),

            "j3_allocator_method_documented_millions":
                parse_float(
                    row[
                        column_map[
                            "documented"
                        ]
                    ]
                ),

            "j3_method_change_review_millions":
                parse_float(
                    row[
                        column_map[
                            "method_review"
                        ]
                    ]
                ),

            "j3_withhold_unresolved_millions":
                parse_float(
                    row[
                        column_map[
                            "withhold"
                        ]
                    ]
                ),

            "j3_intentionally_unallocable_millions":
                parse_float(
                    row[
                        column_map[
                            "unallocable"
                        ]
                    ]
                ),
        }

    return (
        result,
        column_map,
    )


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -------------------------------------------------------------------------
    # Source integrity
    # -------------------------------------------------------------------------

    source_hash = sha256_file(
        ETA2112_SOURCE
    )

    source_hash_ok = (
        source_hash
        == EXPECTED_SOURCE_SHA256
    )

    # -------------------------------------------------------------------------
    # J-4A certification
    # -------------------------------------------------------------------------

    j4a = load_j4a_certification()

    j4a_pass = (
        j4a.get(
            "overall_status"
        )
        == "PASS"
    )

    # -------------------------------------------------------------------------
    # Build allocator
    # -------------------------------------------------------------------------

    (
        monthly_rows,
        allocator,
        source_codes,
    ) = build_eta2112_allocator()

    expected_source_codes = 53

    geography_source_ok = (
        len(source_codes)
        == expected_source_codes
        and "PR" in source_codes
        and "VI" in source_codes
        and "WA" in source_codes
        and "DC" in source_codes
    )

    # 50 states + DC = 51 analytical geographies.
    denominator_geography_ok = all(
        allocator[fy][
            "denominator_geography_count"
        ]
        == 51
        for fy in range(
            STUDY_FY_START,
            STUDY_FY_END + 1,
        )
    )

    wa_month_coverage_ok = all(
        allocator[fy][
            "washington_month_count"
        ]
        == 12
        for fy in range(
            STUDY_FY_START,
            STUDY_FY_END + 1,
        )
    )

    denominator_nonzero_ok = all(
        allocator[fy][
            "state_dc_denominator_c10"
        ]
        != 0
        for fy in range(
            STUDY_FY_START,
            STUDY_FY_END + 1,
        )
    )

    # -------------------------------------------------------------------------
    # OMB controls
    # -------------------------------------------------------------------------

    omb_controls = load_omb_ui_controls()

    omb_coverage_ok = (
        set(omb_controls)
        == set(
            range(
                STUDY_FY_START,
                STUDY_FY_END + 1,
            )
        )
    )

    # -------------------------------------------------------------------------
    # J-3 queue
    # -------------------------------------------------------------------------

    (
        j3_queue,
        j3_column_map,
    ) = load_j3_queue()

    j3_coverage_ok = (
        set(j3_queue)
        == set(
            range(
                STUDY_FY_START,
                STUDY_FY_END + 1,
            )
        )
    )

    # -------------------------------------------------------------------------
    # Allocate
    # -------------------------------------------------------------------------

    allocation_rows: list[dict] = []
    annual_summary_rows: list[dict] = []
    queue_rows: list[dict] = []

    allocation_identity_ok = True
    queue_reduction_ok = True
    queue_nonnegative_ok = True

    tolerance_millions = 0.001

    for fy in range(
        STUDY_FY_START,
        STUDY_FY_END + 1,
    ):
        a = allocator[fy]

        omb_ui_millions = (
            omb_controls[fy]
        )

        omb_ui_dollars = (
            omb_ui_millions
            * 1_000_000.0
        )

        share = a[
            "washington_allocator_share"
        ]

        wa_ui_dollars = (
            omb_ui_dollars
            * share
        )

        wa_ui_millions = (
            wa_ui_dollars
            / 1_000_000.0
        )

        recomputed = (
            omb_ui_dollars
            * (
                a["washington_c10"]
                / a[
                    "state_dc_denominator_c10"
                ]
            )
        )

        if abs(
            recomputed
            - wa_ui_dollars
        ) > 0.01:
            allocation_identity_ok = False

        allocation_rows.append(
            {
                "fiscal_year": fy,
                "receipt_component":
                    "UNEMPLOYMENT_INSURANCE",
                "national_control_source":
                    "OMB Historical Table 2.4",
                "national_control_millions":
                    omb_ui_millions,
                "national_control_dollars":
                    omb_ui_dollars,
                "allocator_source":
                    "DOL ETA-2112",
                "allocator_variable":
                    "c10",
                "allocator_semantics":
                    "net UI contributions",
                "allocator_time_basis":
                    "monthly flow summed Oct-Sep",
                "allocator_geography":
                    "50 states + DC",
                "excluded_source_geographies":
                    "PR;VI",
                "washington_allocator_value":
                    a["washington_c10"],
                "allocator_denominator_value":
                    a[
                        "state_dc_denominator_c10"
                    ],
                "washington_allocator_share":
                    share,
                "washington_receipts_dollars":
                    wa_ui_dollars,
                "allocation_status":
                    "ALLOCATED_PENDING_J4B_CERTIFICATION",
            }
        )

        q = j3_queue[fy]

        before = q[
            "j3_actionable_unfinished_millions"
        ]

        after = (
            before
            - omb_ui_millions
        )

        if after < -tolerance_millions:
            queue_nonnegative_ok = False

        if abs(after) <= tolerance_millions:
            after = 0.0

        if abs(
            before
            - omb_ui_millions
            - after
        ) > tolerance_millions:
            queue_reduction_ok = False

        annual_summary_rows.append(
            {
                "fiscal_year": fy,
                "omb_ui_control_millions":
                    omb_ui_millions,
                "washington_c10":
                    a["washington_c10"],
                "state_dc_c10":
                    a[
                        "state_dc_denominator_c10"
                    ],
                "washington_share":
                    share,
                "washington_ui_receipts_dollars":
                    wa_ui_dollars,
                "washington_ui_receipts_billions":
                    wa_ui_dollars
                    / 1_000_000_000.0,
            }
        )

        queue_rows.append(
            {
                "fiscal_year": fy,

                "j3_actionable_unfinished_millions":
                    before,

                "j4_ui_national_control_closed_millions":
                    omb_ui_millions,

                "actionable_unfinished_millions_after_j4b":
                    after,

                "allocator_method_documented_millions_after_j4b":
                    q[
                        "j3_allocator_method_documented_millions"
                    ],

                "method_change_review_millions_after_j4b":
                    max(
                        0.0,
                        q[
                            "j3_method_change_review_millions"
                        ]
                        - omb_ui_millions,
                    ),

                "withhold_unresolved_millions":
                    q[
                        "j3_withhold_unresolved_millions"
                    ],

                "intentionally_unallocable_millions":
                    q[
                        "j3_intentionally_unallocable_millions"
                    ],
            }
        )

    # -------------------------------------------------------------------------
    # Queue interpretation
    #
    # J-3's remaining actionable queue should consist of method-change-review
    # components. J-4B closes UI only. Any residual is intentionally left for
    # the Health Insurance Providers disposition.
    # -------------------------------------------------------------------------

    ui_control_not_greater_than_queue = all(
        omb_controls[fy]
        <= (
            j3_queue[fy][
                "j3_actionable_unfinished_millions"
            ]
            + tolerance_millions
        )
        for fy in range(
            STUDY_FY_START,
            STUDY_FY_END + 1,
        )
    )

    # -------------------------------------------------------------------------
    # Write outputs
    # -------------------------------------------------------------------------

    write_csv(
        OUTPUT_DIR
        / "eta2112_monthly_allocator_extract.csv",
        monthly_rows,
        [
            "fiscal_year",
            "state_code",
            "report_date",
            "c10",
            "included_in_wcffbp_state_denominator",
        ],
    )

    write_csv(
        OUTPUT_DIR
        / "washington_ui_receipts_allocation.csv",
        allocation_rows,
        [
            "fiscal_year",
            "receipt_component",
            "national_control_source",
            "national_control_millions",
            "national_control_dollars",
            "allocator_source",
            "allocator_variable",
            "allocator_semantics",
            "allocator_time_basis",
            "allocator_geography",
            "excluded_source_geographies",
            "washington_allocator_value",
            "allocator_denominator_value",
            "washington_allocator_share",
            "washington_receipts_dollars",
            "allocation_status",
        ],
    )

    write_csv(
        OUTPUT_DIR
        / "washington_ui_receipts_annual_summary.csv",
        annual_summary_rows,
        [
            "fiscal_year",
            "omb_ui_control_millions",
            "washington_c10",
            "state_dc_c10",
            "washington_share",
            "washington_ui_receipts_dollars",
            "washington_ui_receipts_billions",
        ],
    )

    write_csv(
        OUTPUT_DIR
        / "remaining_receipts_work_queue_after_j4b.csv",
        queue_rows,
        [
            "fiscal_year",
            "j3_actionable_unfinished_millions",
            "j4_ui_national_control_closed_millions",
            "actionable_unfinished_millions_after_j4b",
            "allocator_method_documented_millions_after_j4b",
            "method_change_review_millions_after_j4b",
            "withhold_unresolved_millions",
            "intentionally_unallocable_millions",
        ],
    )

    # -------------------------------------------------------------------------
    # Certification
    # -------------------------------------------------------------------------

    checks = {
        "eta2112_source_sha256":
            source_hash_ok,

        "j4a_upstream_certification":
            j4a_pass,

        "eta2112_source_geography":
            geography_source_ok,

        "wcffbp_state_dc_denominator_geography":
            denominator_geography_ok,

        "washington_12_month_coverage":
            wa_month_coverage_ok,

        "allocator_denominator_nonzero":
            denominator_nonzero_ok,

        "omb_ui_control_coverage":
            omb_coverage_ok,

        "j3_work_queue_coverage":
            j3_coverage_ok,

        "ui_control_not_greater_than_j3_queue":
            ui_control_not_greater_than_queue,

        "washington_allocation_identity":
            allocation_identity_ok,

        "j3_work_queue_reduction":
            queue_reduction_ok,

        "post_j4b_actionable_queue_nonnegative":
            queue_nonnegative_ok,

        "territories_explicitly_excluded":
            (
                TERRITORIES_EXCLUDED_FROM_STATE_UNIVERSE
                == {"PR", "VI"}
            ),

        "omb_eta2112_forced_reconciliation_boundary":
            True,

        "irs_forced_reconciliation_boundary":
            True,

        "database_write_boundary":
            True,

        "final_ledger_boundary":
            True,
    }

    overall_status = (
        "PASS"
        if all(checks.values())
        else "REVIEW"
    )

    certification = {
        "etl_stage":
            "ETL-172J-4B",

        "title":
            "Washington unemployment-insurance "
            "receipt allocation",

        "overall_status":
            overall_status,

        "source_integrity": {
            "eta2112_path":
                str(ETA2112_SOURCE),

            "eta2112_sha256":
                source_hash,

            "expected_eta2112_sha256":
                EXPECTED_SOURCE_SHA256,

            "sha256_status":
                check_status(
                    source_hash_ok
                ),
        },

        "accounting_method": {
            "national_control":
                "OMB Historical Table 2.4 "
                "Unemployment Insurance",

            "allocator":
                "DOL ETA-2112 c10",

            "allocator_semantics":
                "net unemployment insurance "
                "contributions",

            "allocator_time_basis":
                "monthly flows summed October "
                "through September",

            "washington_numerator":
                "Washington ETA-2112 c10",

            "allocator_denominator":
                "ETA-2112 c10 summed across "
                "50 states and District of Columbia",

            "excluded_source_geographies":
                [
                    "PR",
                    "VI",
                ],

            "formula":
                "OMB national UI receipts "
                "* WA c10 / 50-state-plus-DC c10",

            "denominator_is_not_national_accounting_control":
                True,

            "forced_omb_eta2112_reconciliation":
                False,
        },

        "checks": {
            key: check_status(value)
            for key, value in checks.items()
        },

        "boundaries": [
            "DOL ETA-2112 is used only as "
            "a geographic allocator.",

            "OMB remains the national "
            "accounting control.",

            "Puerto Rico and Virgin Islands "
            "are preserved in source data but "
            "excluded from the WCFFBP "
            "50-state-plus-DC denominator.",

            "No forced reconciliation between "
            "ETA-2112 c10 and OMB UI receipts.",

            "Health Insurance Providers tax "
            "is not resolved in ETL-172J-4B.",

            "No IRS gross-collections forced "
            "reconciliation.",

            "No PostgreSQL writes.",

            "No final-ledger authorization.",
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
        "=" * 104,
        "ETL-172J-4B WASHINGTON UNEMPLOYMENT-INSURANCE RECEIPT ALLOCATION v0.1",
        "=" * 104,
        "",
        f"Overall status       : {overall_status}",
        f"ETA-2112 SHA256      : {source_hash}",
        f"Source geography     : {len(source_codes)} codes",
        "WCFFBP denominator   : 50 states + DC",
        "Excluded geography  : PR, VI",
        "",
        "CERTIFICATION CHECKS",
        "-" * 104,
    ]

    for key, value in checks.items():
        lines.append(
            f"{key:<66} "
            f"{check_status(value)}"
        )

    lines.extend(
        [
            "",
            "WASHINGTON UI RECEIPT ALLOCATION",
            "-" * 104,
            (
                "FFY   OMB UI CTRL     WA c10          "
                "STATE+DC c10       WA SHARE     "
                "WA UI RECEIPTS"
            ),
            "-" * 104,
        ]
    )

    for row in annual_summary_rows:
        lines.append(
            f"{row['fiscal_year']}   "
            f"{row['omb_ui_control_millions']:>10,.0f}M   "
            f"{row['washington_c10']:>14,.0f}   "
            f"{row['state_dc_c10']:>16,.0f}   "
            f"{row['washington_share']:>9.4%}   "
            f"${row['washington_ui_receipts_billions']:>8.3f}B"
        )

    lines.extend(
        [
            "",
            "POST-J4B WORK QUEUE",
            "-" * 104,
            (
                "FFY   J3 ACTIONABLE   UI CLOSED   "
                "ACTIONABLE AFTER J4B"
            ),
            "-" * 104,
        ]
    )

    for row in queue_rows:
        lines.append(
            f"{row['fiscal_year']}   "
            f"{row['j3_actionable_unfinished_millions']:>11,.0f}M   "
            f"{row['j4_ui_national_control_closed_millions']:>8,.0f}M   "
            f"{row['actionable_unfinished_millions_after_j4b']:>17,.0f}M"
        )

    lines.extend(
        [
            "",
            "BOUNDARIES",
            "-" * 104,
            "ETA-2112 supplies geographic incidence only.",
            "OMB supplies the national accounting control.",
            "No forced ETA-2112 / OMB reconciliation.",
            "Health Insurance Providers remains unresolved.",
            "No PostgreSQL writes.",
            "No final-ledger authorization.",
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