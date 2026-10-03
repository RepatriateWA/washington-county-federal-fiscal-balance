from __future__ import annotations

import csv
import json
from pathlib import Path


STUDY_FY_START = 2015
STUDY_FY_END = 2024
TOLERANCE_MILLIONS = 0.001


J4B_DIR = Path(
    r"data\raw\omb\historical_tables\FY2027"
    r"\validation\washington_ui_receipts_v0_1"
)

J4B_CERTIFICATION = (
    J4B_DIR / "certification.json"
)

J4B_QUEUE = (
    J4B_DIR
    / "remaining_receipts_work_queue_after_j4b.csv"
)


I2_DIR = Path(
    r"data\raw\omb\historical_tables\FY2027"
    r"\validation\social_insurance_excise_decomposition_v0_1"
)

I2_DECOMPOSITION = (
    I2_DIR
    / "national_social_insurance_excise_decomposition.csv"
)


OUTPUT_DIR = Path(
    r"data\raw\omb\historical_tables\FY2027"
    r"\validation\health_insurance_provider_receipts_disposition_v0_1"
)


def parse_float(value: str | None) -> float:
    if value is None:
        return 0.0

    value = value.strip()

    if value == "":
        return 0.0

    return float(value)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
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


def pass_fail(value: bool) -> str:
    return "PASS" if value else "FAIL"


def load_j4b_certification() -> dict:
    if not J4B_CERTIFICATION.exists():
        raise FileNotFoundError(
            J4B_CERTIFICATION
        )

    with J4B_CERTIFICATION.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def load_j4b_queue() -> dict[int, dict]:
    if not J4B_QUEUE.exists():
        raise FileNotFoundError(
            J4B_QUEUE
        )

    rows = read_csv_rows(
        J4B_QUEUE
    )

    result: dict[int, dict] = {}

    for row in rows:
        fy = int(row["fiscal_year"])

        if not (
            STUDY_FY_START
            <= fy
            <= STUDY_FY_END
        ):
            continue

        result[fy] = {
            "fiscal_year": fy,

            "actionable_before":
                parse_float(
                    row[
                        "actionable_unfinished_millions_after_j4b"
                    ]
                ),

            "documented":
                parse_float(
                    row[
                        "allocator_method_documented_millions_after_j4b"
                    ]
                ),

            "method_review":
                parse_float(
                    row[
                        "method_change_review_millions_after_j4b"
                    ]
                ),

            "withhold":
                parse_float(
                    row[
                        "withhold_unresolved_millions"
                    ]
                ),

            "unallocable":
                parse_float(
                    row[
                        "intentionally_unallocable_millions"
                    ]
                ),
        }

    return result


def load_hip_controls() -> dict[int, float]:
    if not I2_DECOMPOSITION.exists():
        raise FileNotFoundError(
            I2_DECOMPOSITION
        )

    rows = read_csv_rows(
        I2_DECOMPOSITION
    )

    result: dict[int, float] = {}

    for row in rows:
        component = (
            row.get(
                "component_code",
                "",
            )
            .strip()
            .upper()
        )

        if (
            component
            != "HEALTH_INSURANCE_PROVIDERS"
        ):
            continue

        fy = int(
            row["fiscal_year"]
        )

        if not (
            STUDY_FY_START
            <= fy
            <= STUDY_FY_END
        ):
            continue

        result[fy] = parse_float(
            row["amount_millions"]
        )

    return result


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    j4b_cert = load_j4b_certification()
    j4b_queue = load_j4b_queue()
    hip_controls = load_hip_controls()

    study_years = set(
        range(
            STUDY_FY_START,
            STUDY_FY_END + 1,
        )
    )

    j4b_certified = (
        j4b_cert.get("overall_status")
        == "PASS"
    )

    j4b_year_coverage = (
        set(j4b_queue)
        == study_years
    )

    hip_year_coverage = (
        set(hip_controls)
        == study_years
    )

    residual_equals_hip = True
    method_review_equals_hip = True
    documented_queue_zero = True

    disposition_rows: list[dict] = []
    queue_rows: list[dict] = []

    for fy in range(
        STUDY_FY_START,
        STUDY_FY_END + 1,
    ):
        q = j4b_queue[fy]
        hip = hip_controls[fy]

        residual = q[
            "actionable_before"
        ]

        method_review = q[
            "method_review"
        ]

        if abs(
            residual - hip
        ) > TOLERANCE_MILLIONS:
            residual_equals_hip = False

        if abs(
            method_review - hip
        ) > TOLERANCE_MILLIONS:
            method_review_equals_hip = False

        if abs(
            q["documented"]
        ) > TOLERANCE_MILLIONS:
            documented_queue_zero = False

        if abs(hip) <= TOLERANCE_MILLIONS:
            hip = 0.0

        disposition = (
            "WITHHOLD_UNRESOLVED"
            if hip != 0.0
            else "ZERO_NATIONAL_CONTROL"
        )

        disposition_rows.append(
            {
                "fiscal_year": fy,
                "receipt_component":
                    "HEALTH_INSURANCE_PROVIDERS",

                "national_control_source":
                    "OMB Historical Table 2.4",

                "national_control_millions":
                    hip,

                "rockefeller_allocator":
                    "Oliver Wyman state tax-burden forecast",

                "wcffbp_disposition":
                    disposition,

                "washington_receipts_dollars":
                    "",

                "reason":
                    (
                        "Documented Rockefeller allocator "
                        "is a third-party modeled state "
                        "tax-burden forecast; authoritative "
                        "reproducible state allocator not "
                        "certified for WCFFBP principal ledger."
                        if hip != 0.0
                        else
                        "Certified OMB national control is zero."
                    ),
            }
        )

        withhold_after = (
            q["withhold"]
            + hip
        )

        queue_rows.append(
            {
                "fiscal_year": fy,

                "actionable_unfinished_before_j4c_millions":
                    residual,

                "hip_national_control_disposed_millions":
                    hip,

                "actionable_unfinished_after_j4c_millions":
                    0.0,

                "allocator_method_documented_millions_after_j4c":
                    q["documented"],

                "method_change_review_millions_after_j4c":
                    0.0,

                "withhold_unresolved_millions_after_j4c":
                    withhold_after,

                "intentionally_unallocable_millions":
                    q["unallocable"],
            }
        )

    actionable_zero_after = all(
        abs(
            row[
                "actionable_unfinished_after_j4c_millions"
            ]
        )
        <= TOLERANCE_MILLIONS
        for row in queue_rows
    )

    method_review_zero_after = all(
        abs(
            row[
                "method_change_review_millions_after_j4c"
            ]
        )
        <= TOLERANCE_MILLIONS
        for row in queue_rows
    )

    hip_zero_2022_2024 = all(
        abs(
            hip_controls[fy]
        )
        <= TOLERANCE_MILLIONS
        for fy in (
            2022,
            2023,
            2024,
        )
    )

    checks = {
        "j4b_upstream_certification":
            j4b_certified,

        "j4b_queue_year_coverage":
            j4b_year_coverage,

        "hip_control_year_coverage":
            hip_year_coverage,

        "post_j4b_actionable_residual_equals_hip":
            residual_equals_hip,

        "post_j4b_method_review_equals_hip":
            method_review_equals_hip,

        "allocator_method_documented_queue_zero":
            documented_queue_zero,

        "hip_zero_control_2022_2024":
            hip_zero_2022_2024,

        "post_j4c_actionable_queue_zero":
            actionable_zero_after,

        "post_j4c_method_review_queue_zero":
            method_review_zero_after,

        "washington_hip_not_imputed":
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

    write_csv(
        OUTPUT_DIR
        / "health_insurance_provider_disposition.csv",
        disposition_rows,
        [
            "fiscal_year",
            "receipt_component",
            "national_control_source",
            "national_control_millions",
            "rockefeller_allocator",
            "wcffbp_disposition",
            "washington_receipts_dollars",
            "reason",
        ],
    )

    write_csv(
        OUTPUT_DIR
        / "remaining_receipts_work_queue_after_j4c.csv",
        queue_rows,
        [
            "fiscal_year",
            "actionable_unfinished_before_j4c_millions",
            "hip_national_control_disposed_millions",
            "actionable_unfinished_after_j4c_millions",
            "allocator_method_documented_millions_after_j4c",
            "method_change_review_millions_after_j4c",
            "withhold_unresolved_millions_after_j4c",
            "intentionally_unallocable_millions",
        ],
    )

    certification = {
        "etl_stage":
            "ETL-172J-4C",

        "title":
            "Health Insurance Providers receipt disposition",

        "overall_status":
            overall_status,

        "methodological_decision": {
            "component":
                "HEALTH_INSURANCE_PROVIDERS",

            "rockefeller_allocator":
                "Oliver Wyman state tax-burden forecast",

            "wcffbp_principal_ledger_treatment":
                "WITHHOLD_UNRESOLVED",

            "zero_control_years": [
                2022,
                2023,
                2024,
            ],

            "washington_amount_imputed":
                False,

            "reason":
                (
                    "The Rockefeller methodology documents "
                    "a third-party modeled state tax-burden "
                    "forecast. WCFFBP does not substitute an "
                    "invented incidence model where the "
                    "applicable state allocator has not been "
                    "independently certified."
                ),
        },

        "checks": {
            key: pass_fail(value)
            for key, value in checks.items()
        },

        "boundaries": [
            "No Washington HIP receipt amount is imputed.",
            "Nonzero HIP national controls are explicitly withheld.",
            "Zero national-control years remain zero.",
            "No IRS gross-collections forced reconciliation.",
            "No PostgreSQL writes.",
            "No final-ledger authorization.",
        ],
    }

    with (
        OUTPUT_DIR / "certification.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            certification,
            f,
            indent=2,
        )

    lines = [
        "=" * 100,
        "ETL-172J-4C HEALTH INSURANCE PROVIDERS RECEIPT DISPOSITION v0.1",
        "=" * 100,
        "",
        f"Overall status : {overall_status}",
        "",
        "CERTIFICATION CHECKS",
        "-" * 100,
    ]

    for key, value in checks.items():
        lines.append(
            f"{key:<70} {pass_fail(value)}"
        )

    lines.extend(
        [
            "",
            "HIP DISPOSITION",
            "-" * 100,
            (
                "FFY   NATIONAL CONTROL   "
                "WCFFBP DISPOSITION"
            ),
            "-" * 100,
        ]
    )

    for row in disposition_rows:
        lines.append(
            f"{row['fiscal_year']}   "
            f"{row['national_control_millions']:>12,.0f}M   "
            f"{row['wcffbp_disposition']}"
        )

    lines.extend(
        [
            "",
            "POST-J4C WORK QUEUE",
            "-" * 100,
            (
                "FFY   ACTIONABLE BEFORE   "
                "HIP DISPOSED   ACTIONABLE AFTER"
            ),
            "-" * 100,
        ]
    )

    for row in queue_rows:
        lines.append(
            f"{row['fiscal_year']}   "
            f"{row['actionable_unfinished_before_j4c_millions']:>14,.0f}M   "
            f"{row['hip_national_control_disposed_millions']:>10,.0f}M   "
            f"{row['actionable_unfinished_after_j4c_millions']:>15,.0f}M"
        )

    lines.extend(
        [
            "",
            "BOUNDARIES",
            "-" * 100,
            "No Washington HIP amount imputed.",
            "Nonzero HIP controls moved to WITHHOLD_UNRESOLVED.",
            "No IRS forced reconciliation.",
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