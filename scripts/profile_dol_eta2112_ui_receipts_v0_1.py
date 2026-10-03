from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


SOURCE = Path(
    r"data\raw\dol\unemployment_insurance\eta2112\source\ar2112.csv"
)

OUTPUT_DIR = Path(
    r"data\raw\dol\unemployment_insurance\eta2112"
    r"\validation\ui_receipts_profile_v0_1"
)

STUDY_FY_START = 2015
STUDY_FY_END = 2024
WASHINGTON = "WA"

REQUIRED_COLUMNS = {
    "st",
    "rptdate",
    "c10",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest().upper()


def parse_date(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d")


def federal_fiscal_year(date_value: datetime) -> int:
    if date_value.month >= 10:
        return date_value.year + 1
    return date_value.year


def parse_number(value: str) -> float | None:
    value = value.strip()

    if value == "":
        return None

    return float(value)


def status(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    source_hash = sha256_file(SOURCE)
    source_bytes = SOURCE.stat().st_size

    row_count = 0
    states: set[str] = set()
    dates: set[datetime] = set()

    duplicate_keys: dict[tuple[str, datetime], int] = defaultdict(int)

    rows_by_fy: dict[int, int] = defaultdict(int)
    wa_rows_by_fy: dict[int, int] = defaultdict(int)

    wa_months_by_fy: dict[int, set[datetime]] = defaultdict(set)

    wa_c10_by_fy: dict[int, float] = defaultdict(float)
    us_state_sum_c10_by_fy: dict[int, float] = defaultdict(float)

    wa_nonnull_c10_by_fy: dict[int, int] = defaultdict(int)
    all_nonnull_c10_by_fy: dict[int, int] = defaultdict(int)

    min_date: datetime | None = None
    max_date: datetime | None = None

    with SOURCE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)

        fieldnames = reader.fieldnames or []
        missing_columns = REQUIRED_COLUMNS - set(fieldnames)

        if missing_columns:
            raise RuntimeError(
                "Missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        for row in reader:
            row_count += 1

            state = row["st"].strip().upper()
            report_date = parse_date(row["rptdate"])
            c10 = parse_number(row["c10"])

            states.add(state)
            dates.add(report_date)

            if min_date is None or report_date < min_date:
                min_date = report_date

            if max_date is None or report_date > max_date:
                max_date = report_date

            duplicate_keys[(state, report_date)] += 1

            fy = federal_fiscal_year(report_date)

            rows_by_fy[fy] += 1

            if c10 is not None:
                all_nonnull_c10_by_fy[fy] += 1
                us_state_sum_c10_by_fy[fy] += c10

            if state == WASHINGTON:
                wa_rows_by_fy[fy] += 1
                wa_months_by_fy[fy].add(report_date)

                if c10 is not None:
                    wa_nonnull_c10_by_fy[fy] += 1
                    wa_c10_by_fy[fy] += c10

    duplicate_count = sum(
        1
        for count in duplicate_keys.values()
        if count > 1
    )

    study_years = list(
        range(STUDY_FY_START, STUDY_FY_END + 1)
    )

    annual_rows = []

    for fy in study_years:
        wa_value = wa_c10_by_fy.get(fy, 0.0)
        us_value = us_state_sum_c10_by_fy.get(fy, 0.0)

        wa_share = (
            wa_value / us_value
            if us_value != 0
            else None
        )

        months = sorted(wa_months_by_fy.get(fy, set()))

        annual_rows.append(
            {
                "fiscal_year": fy,
                "wa_month_count": len(months),
                "wa_nonnull_c10_month_count":
                    wa_nonnull_c10_by_fy.get(fy, 0),
                "wa_c10_fy_sum": wa_value,
                "us_state_sum_c10_fy_sum": us_value,
                "wa_c10_share": wa_share,
                "first_wa_report_date":
                    months[0].date().isoformat()
                    if months else "",
                "last_wa_report_date":
                    months[-1].date().isoformat()
                    if months else "",
            }
        )

    annual_csv = OUTPUT_DIR / "annual_ui_allocator_profile.csv"

    with annual_csv.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        fieldnames = [
            "fiscal_year",
            "wa_month_count",
            "wa_nonnull_c10_month_count",
            "wa_c10_fy_sum",
            "us_state_sum_c10_fy_sum",
            "wa_c10_share",
            "first_wa_report_date",
            "last_wa_report_date",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(annual_rows)

    checks = {
        "source_exists":
            SOURCE.exists(),

        "required_columns_present":
            True,

        "study_years_present":
            all(
                wa_rows_by_fy.get(fy, 0) > 0
                for fy in study_years
            ),

        "wa_has_12_months_each_study_fy":
            all(
                len(wa_months_by_fy.get(fy, set())) == 12
                for fy in study_years
            ),

        "wa_c10_nonnull_12_months_each_study_fy":
            all(
                wa_nonnull_c10_by_fy.get(fy, 0) == 12
                for fy in study_years
            ),

        "state_date_keys_unique":
            duplicate_count == 0,

        "wa_allocator_denominator_nonzero":
            all(
                us_state_sum_c10_by_fy.get(fy, 0) != 0
                for fy in study_years
            ),

        "no_database_write":
            True,

        "no_receipt_allocation":
            True,

        "no_final_ledger_authorization":
            True,
    }

    overall_status = (
        "PASS"
        if all(checks.values())
        else "REVIEW"
    )

    certification = {
        "etl_stage":
            "ETL-172J-4A",

        "title":
            "DOL ETA-2112 unemployment-insurance "
            "receipt allocator profile",

        "overall_status":
            overall_status,

        "source": {
            "path": str(SOURCE),
            "bytes": source_bytes,
            "sha256": source_hash,
            "minimum_report_date":
                min_date.date().isoformat()
                if min_date else None,
            "maximum_report_date":
                max_date.date().isoformat()
                if max_date else None,
            "row_count": row_count,
            "distinct_state_codes": len(states),
            "distinct_report_dates": len(dates),
        },

        "methodology": {
            "rockefeller_allocator_variable":
                "c10",

            "rockefeller_variable_description":
                "net unemployment insurance contributions",

            "working_time_aggregation":
                "monthly rptdate observations summed "
                "October through September into federal "
                "fiscal years",

            "washington_geography":
                "st == WA",

            "national_denominator":
                "sum of c10 across all state-code records "
                "within each federal fiscal year",

            "allocation_performed":
                False,
        },

        "checks": {
            key: status(value)
            for key, value in checks.items()
        },

        "duplicate_state_date_keys":
            duplicate_count,

        "boundaries": [
            "Source profiling only.",
            "No OMB national receipt control multiplied "
            "by allocator share.",
            "No Washington UI receipt amount certified.",
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

    report_lines = [
        "=" * 88,
        "ETL-172J-4A DOL ETA-2112 UI RECEIPT "
        "ALLOCATOR PROFILE v0.1",
        "=" * 88,
        "",
        f"Overall status       : {overall_status}",
        f"Source               : {SOURCE}",
        f"Source bytes         : {source_bytes:,}",
        f"SHA256               : {source_hash}",
        f"Rows                 : {row_count:,}",
        f"Distinct state codes : {len(states):,}",
        f"Distinct dates       : {len(dates):,}",
        (
            "Date range           : "
            f"{min_date.date().isoformat()} through "
            f"{max_date.date().isoformat()}"
            if min_date and max_date
            else "Date range           : unavailable"
        ),
        "",
        "CERTIFICATION CHECKS",
        "-" * 88,
    ]

    for key, value in checks.items():
        report_lines.append(
            f"{key:<52} {status(value)}"
        )

    report_lines.extend(
        [
            "",
            "WASHINGTON / NATIONAL c10 PROFILE",
            "-" * 88,
            (
                "FFY   MONTHS   WA c10              "
                "US STATE-SUM c10      WA SHARE"
            ),
            "-" * 88,
        ]
    )

    for row in annual_rows:
        share = row["wa_c10_share"]

        report_lines.append(
            f"{row['fiscal_year']}   "
            f"{row['wa_month_count']:>2}       "
            f"{row['wa_c10_fy_sum']:>18,.2f}   "
            f"{row['us_state_sum_c10_fy_sum']:>18,.2f}   "
            f"{share:>10.6%}"
        )

    report_lines.extend(
        [
            "",
            "BOUNDARIES",
            "-" * 88,
            "No receipt allocation.",
            "No OMB control multiplication.",
            "No PostgreSQL writes.",
            "No final-ledger authorization.",
            "",
        ]
    )

    report = "\n".join(report_lines)

    (
        OUTPUT_DIR / "certification_report.txt"
    ).write_text(
        report,
        encoding="utf-8",
    )

    print(report)


if __name__ == "__main__":
    main()