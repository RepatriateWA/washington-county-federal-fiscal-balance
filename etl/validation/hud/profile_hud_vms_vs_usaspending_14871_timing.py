"""
ETL-174B-5Y-2D-3
HUD VMS HAP Total vs USAspending AL 14.871
monthly residual and timing profile.

INPUT
-----
Certified ETL-174B-5Y-2D-2 monthly reconciliation CSV.

PURPOSE
-------
Describe:
    * monthly obligation and HAP behavior,
    * monthly residuals,
    * concentration / volatility,
    * largest positive and negative obligation months,
    * simple contemporaneous and lagged relationships.

This is exploratory reconciliation evidence only.

IMPORTANT
---------
Correlation does not establish causation or accounting equivalence.
A lag correlation does not establish that a specific obligation funded
a later HAP expenditure.

READ ONLY.

NO:
    new source extraction,
    database access,
    accounting-source selection,
    county allocation,
    ledger decision.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


CHECKPOINT = "ETL-174B-5Y-2D-3"

REPO_ROOT = Path(__file__).resolve().parents[3]

INPUT_ROOT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "hud"
    / "vms"
    / "validation"
    / "reconcile_vms_hap_vs_usaspending_14871"
)

OUTPUT_ROOT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "hud"
    / "vms"
    / "validation"
    / "profile_vms_vs_usaspending_14871_timing"
)

LAGS = tuple(range(-6, 7))


def money(value) -> str:
    if value is None:
        return "NULL"
    return f"${Decimal(str(value)):,.2f}"


def pct(value) -> str:
    if value is None:
        return "NULL"
    return f"{value * 100:.4f}%"


def number(value) -> str:
    if value is None:
        return "NULL"
    return f"{value:.6f}"


def parse_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")

    text = str(value).strip()

    if not text:
        return Decimal("0")

    return Decimal(text)


def discover_latest_input() -> Path:
    candidates = sorted(
        INPUT_ROOT.glob(
            "reconcile_vms_hap_vs_14871_*.csv"
        )
    )

    if not candidates:
        raise FileNotFoundError(
            "No ETL-174B-5Y-2D-2 reconciliation CSV "
            f"found under {INPUT_ROOT}"
        )

    return candidates[-1]


def load_rows(path: Path):
    rows = []

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:

        reader = csv.DictReader(handle)

        required = {
            "fiscal_year",
            "action_month",
            "vms_pha_count",
            "vms_hap_total",
            "usaspending_transaction_count",
            "usaspending_positive_obligation",
            "usaspending_negative_obligation",
            "usaspending_net_obligation",
            "net_minus_hap",
        }

        missing = required - set(
            reader.fieldnames or []
        )

        if missing:
            raise RuntimeError(
                "Input CSV missing required fields: "
                + ", ".join(sorted(missing))
            )

        for raw in reader:

            month = date.fromisoformat(
                raw["action_month"][:10]
            )

            rows.append(
                {
                    "fiscal_year":
                        int(raw["fiscal_year"]),
                    "action_month":
                        month,
                    "vms_pha_count":
                        int(raw["vms_pha_count"]),
                    "vms_hap_total":
                        parse_decimal(
                            raw["vms_hap_total"]
                        ),
                    "transaction_count":
                        int(
                            raw[
                                "usaspending_transaction_count"
                            ]
                        ),
                    "positive_obligation":
                        parse_decimal(
                            raw[
                                "usaspending_positive_obligation"
                            ]
                        ),
                    "negative_obligation":
                        parse_decimal(
                            raw[
                                "usaspending_negative_obligation"
                            ]
                        ),
                    "net_obligation":
                        parse_decimal(
                            raw[
                                "usaspending_net_obligation"
                            ]
                        ),
                    "residual":
                        parse_decimal(
                            raw["net_minus_hap"]
                        ),
                }
            )

    rows.sort(
        key=lambda row:
            row["action_month"]
    )

    return rows


def mean_decimal(values):
    if not values:
        return None

    return sum(
        values,
        Decimal("0"),
    ) / Decimal(len(values))


def population_sd(values):
    if not values:
        return None

    if len(values) == 1:
        return Decimal("0")

    mean = mean_decimal(values)

    variance = (
        sum(
            (
                (value - mean) ** 2
                for value in values
            ),
            Decimal("0"),
        )
        / Decimal(len(values))
    )

    return Decimal(
        str(
            math.sqrt(
                float(variance)
            )
        )
    )


def coefficient_of_variation(values):
    mean = mean_decimal(values)
    sd = population_sd(values)

    if mean is None or sd is None:
        return None

    if mean == 0:
        return None

    return float(
        sd / abs(mean)
    )


def pearson(x_values, y_values):
    if len(x_values) != len(y_values):
        raise ValueError(
            "Pearson vectors must have equal length."
        )

    n = len(x_values)

    if n < 3:
        return None

    x = [
        float(value)
        for value in x_values
    ]

    y = [
        float(value)
        for value in y_values
    ]

    mean_x = statistics.fmean(x)
    mean_y = statistics.fmean(y)

    numerator = sum(
        (a - mean_x) * (b - mean_y)
        for a, b in zip(x, y)
    )

    denominator_x = math.sqrt(
        sum(
            (a - mean_x) ** 2
            for a in x
        )
    )

    denominator_y = math.sqrt(
        sum(
            (b - mean_y) ** 2
            for b in y
        )
    )

    denominator = (
        denominator_x
        * denominator_y
    )

    if denominator == 0:
        return None

    return numerator / denominator


def lag_profile(rows):
    """
    Lag convention:

        lag = 0
            obligation[t] vs HAP[t]

        lag = +1
            obligation[t] vs HAP[t+1]

        lag = +N
            obligation precedes HAP by N months

        lag = -1
            HAP precedes obligation by one month

    This is descriptive only.
    """

    obligations = [
        row["net_obligation"]
        for row in rows
    ]

    hap = [
        row["vms_hap_total"]
        for row in rows
    ]

    results = []

    n = len(rows)

    for lag in LAGS:

        x_values = []
        y_values = []

        for index in range(n):

            hap_index = index + lag

            if (
                hap_index < 0
                or hap_index >= n
            ):
                continue

            x_values.append(
                obligations[index]
            )

            y_values.append(
                hap[hap_index]
            )

        results.append(
            {
                "lag_months": lag,
                "pair_count":
                    len(x_values),
                "correlation":
                    pearson(
                        x_values,
                        y_values,
                    ),
            }
        )

    return results


def concentration_profile(rows, field):
    ranked = sorted(
        rows,
        key=lambda row:
            row[field],
        reverse=True,
    )

    total = sum(
        (
            row[field]
            for row in rows
        ),
        Decimal("0"),
    )

    results = []

    for n in (1, 3, 6, 12):

        selected = ranked[:n]

        selected_total = sum(
            (
                row[field]
                for row in selected
            ),
            Decimal("0"),
        )

        share = (
            float(
                selected_total / total
            )
            if total != 0
            else None
        )

        results.append(
            {
                "top_n": n,
                "total":
                    selected_total,
                "share":
                    share,
            }
        )

    return results


def annual_profile(rows):
    results = []

    for fiscal_year in (2023, 2024):

        selected = [
            row
            for row in rows
            if row["fiscal_year"]
            == fiscal_year
        ]

        results.append(
            {
                "fiscal_year":
                    fiscal_year,
                "month_count":
                    len(selected),
                "hap_total":
                    sum(
                        (
                            row[
                                "vms_hap_total"
                            ]
                            for row
                            in selected
                        ),
                        Decimal("0"),
                    ),
                "positive_obligation":
                    sum(
                        (
                            row[
                                "positive_obligation"
                            ]
                            for row
                            in selected
                        ),
                        Decimal("0"),
                    ),
                "negative_obligation":
                    sum(
                        (
                            row[
                                "negative_obligation"
                            ]
                            for row
                            in selected
                        ),
                        Decimal("0"),
                    ),
                "net_obligation":
                    sum(
                        (
                            row[
                                "net_obligation"
                            ]
                            for row
                            in selected
                        ),
                        Decimal("0"),
                    ),
                "residual":
                    sum(
                        (
                            row[
                                "residual"
                            ]
                            for row
                            in selected
                        ),
                        Decimal("0"),
                    ),
            }
        )

    return results


def render_report(
    input_path,
    rows,
    lags,
    annual,
):
    lines = []

    def emit(text=""):
        lines.append(text)

    emit("=" * 112)
    emit(
        "HUD VMS HAP TOTAL vs USASPENDING AL 14.871 "
        "MONTHLY RESIDUAL AND TIMING PROFILE"
    )
    emit(CHECKPOINT)
    emit("=" * 112)
    emit()
    emit("Mode : READ ONLY")
    emit(
        "Input: "
        + str(
            input_path.relative_to(
                REPO_ROOT
            )
        )
    )
    emit(
        "Scope: 24 certified paired months, "
        "FFY2023 + FFY2024"
    )

    emit()
    emit("POPULATION CONTROL")
    emit("-" * 112)
    emit(
        f"Paired months        : "
        f"{len(rows)}"
    )
    emit(
        "Monthly PHA counts   : "
        + ", ".join(
            str(value)
            for value in sorted(
                {
                    row["vms_pha_count"]
                    for row in rows
                }
            )
        )
    )

    emit()
    emit("FISCAL-YEAR CONTROLS")
    emit("-" * 112)

    for item in annual:
        emit(
            f"FFY{item['fiscal_year']} | "
            f"months={item['month_count']} | "
            f"HAP={money(item['hap_total'])} | "
            f"USA+={money(item['positive_obligation'])} | "
            f"USA-={money(item['negative_obligation'])} | "
            f"USA net={money(item['net_obligation'])} | "
            f"residual={money(item['residual'])}"
        )

    hap_values = [
        row["vms_hap_total"]
        for row in rows
    ]

    net_values = [
        row["net_obligation"]
        for row in rows
    ]

    positive_values = [
        row["positive_obligation"]
        for row in rows
    ]

    negative_values = [
        row["negative_obligation"]
        for row in rows
    ]

    residual_values = [
        row["residual"]
        for row in rows
    ]

    emit()
    emit("VOLATILITY PROFILE")
    emit("-" * 112)

    for label, values in (
        ("HUD VMS HAP", hap_values),
        (
            "USAspending positive obligations",
            positive_values,
        ),
        (
            "USAspending net obligations",
            net_values,
        ),
        (
            "Monthly residual",
            residual_values,
        ),
    ):
        emit(label)
        emit(
            f"    mean               : "
            f"{money(mean_decimal(values))}"
        )
        emit(
            f"    population SD      : "
            f"{money(population_sd(values))}"
        )
        emit(
            f"    coefficient var.   : "
            f"{number(coefficient_of_variation(values))}"
        )
        emit(
            f"    minimum            : "
            f"{money(min(values))}"
        )
        emit(
            f"    maximum            : "
            f"{money(max(values))}"
        )

    emit()
    emit("MONTHLY DETAIL — CHRONOLOGICAL")
    emit("-" * 112)

    for row in rows:
        emit(
            f"{row['action_month']} | "
            f"FY{row['fiscal_year']} | "
            f"HAP={money(row['vms_hap_total'])} | "
            f"USA+={money(row['positive_obligation'])} | "
            f"USA-={money(row['negative_obligation'])} | "
            f"USA net={money(row['net_obligation'])} | "
            f"residual={money(row['residual'])}"
        )

    emit()
    emit("LARGEST NET-OBLIGATION MONTHS")
    emit("-" * 112)

    for rank, row in enumerate(
        sorted(
            rows,
            key=lambda item:
                item["net_obligation"],
            reverse=True,
        )[:10],
        start=1,
    ):
        emit(
            f"{rank:>2}. "
            f"{row['action_month']} | "
            f"net={money(row['net_obligation'])} | "
            f"HAP={money(row['vms_hap_total'])} | "
            f"residual={money(row['residual'])}"
        )

    emit()
    emit("LARGEST POSITIVE-OBLIGATION MONTHS")
    emit("-" * 112)

    for rank, row in enumerate(
        sorted(
            rows,
            key=lambda item:
                item["positive_obligation"],
            reverse=True,
        )[:10],
        start=1,
    ):
        emit(
            f"{rank:>2}. "
            f"{row['action_month']} | "
            f"positive={money(row['positive_obligation'])} | "
            f"negative={money(row['negative_obligation'])} | "
            f"net={money(row['net_obligation'])}"
        )

    emit()
    emit("LARGEST DEOBLIGATION MONTHS")
    emit("-" * 112)

    for rank, row in enumerate(
        sorted(
            rows,
            key=lambda item:
                item["negative_obligation"],
        )[:10],
        start=1,
    ):
        emit(
            f"{rank:>2}. "
            f"{row['action_month']} | "
            f"negative={money(row['negative_obligation'])} | "
            f"positive={money(row['positive_obligation'])} | "
            f"net={money(row['net_obligation'])}"
        )

    emit()
    emit("LARGEST POSITIVE RESIDUAL MONTHS")
    emit("-" * 112)

    for rank, row in enumerate(
        sorted(
            rows,
            key=lambda item:
                item["residual"],
            reverse=True,
        )[:10],
        start=1,
    ):
        emit(
            f"{rank:>2}. "
            f"{row['action_month']} | "
            f"residual={money(row['residual'])} | "
            f"net={money(row['net_obligation'])} | "
            f"HAP={money(row['vms_hap_total'])}"
        )

    emit()
    emit("MOST NEGATIVE RESIDUAL MONTHS")
    emit("-" * 112)

    for rank, row in enumerate(
        sorted(
            rows,
            key=lambda item:
                item["residual"],
        )[:10],
        start=1,
    ):
        emit(
            f"{rank:>2}. "
            f"{row['action_month']} | "
            f"residual={money(row['residual'])} | "
            f"net={money(row['net_obligation'])} | "
            f"HAP={money(row['vms_hap_total'])}"
        )

    emit()
    emit("CONCENTRATION PROFILE")
    emit("-" * 112)

    for label, field in (
        (
            "USAspending positive obligations",
            "positive_obligation",
        ),
        (
            "USAspending net obligations",
            "net_obligation",
        ),
        (
            "HUD VMS HAP",
            "vms_hap_total",
        ),
    ):
        emit(label)

        for item in concentration_profile(
            rows,
            field,
        ):
            emit(
                f"    top {item['top_n']:>2} months | "
                f"total={money(item['total'])} | "
                f"share={pct(item['share'])}"
            )

    emit()
    emit("CONTEMPORANEOUS / LAG PROFILE")
    emit("-" * 112)
    emit(
        "Convention: lag +N = USAspending obligation "
        "month precedes HAP month by N months."
    )
    emit()

    for item in lags:
        emit(
            f"lag {item['lag_months']:+3d} months | "
            f"pairs={item['pair_count']:>2} | "
            f"Pearson r={number(item['correlation'])}"
        )

    valid_lags = [
        item
        for item in lags
        if item["correlation"]
        is not None
    ]

    strongest_absolute = max(
        valid_lags,
        key=lambda item:
            abs(item["correlation"]),
    )

    strongest_positive = max(
        valid_lags,
        key=lambda item:
            item["correlation"],
    )

    emit()
    emit(
        "Strongest absolute observed correlation: "
        f"lag {strongest_absolute['lag_months']:+d}, "
        f"r={number(strongest_absolute['correlation'])}, "
        f"pairs={strongest_absolute['pair_count']}"
    )
    emit(
        "Strongest positive observed correlation: "
        f"lag {strongest_positive['lag_months']:+d}, "
        f"r={number(strongest_positive['correlation'])}, "
        f"pairs={strongest_positive['pair_count']}"
    )

    emit()
    emit("INTERPRETIVE BOUNDARY")
    emit("-" * 112)
    emit(
        "This profile is descriptive. Correlation does not "
        "establish funding identity, causation, or accounting equivalence."
    )
    emit(
        "Lag relationships are exploratory and use only 24 paired months."
    )
    emit(
        "Large monthly residuals may reflect timing, accounting stage, "
        "program composition, supplemental funding, deobligations, "
        "geography, or other mechanisms not identified by this test."
    )

    emit()
    emit("METHODOLOGICAL STOP")
    emit("-" * 112)
    emit(
        "No accounting-source selection was made."
    )
    emit(
        "No residual was classified as error or additional expenditure."
    )
    emit(
        "No county allocation was performed."
    )
    emit(
        "No database writes occurred."
    )
    emit(
        "No ledger decision was made."
    )

    emit()
    emit(
        "RESULT: PASS — MONTHLY RESIDUAL AND TIMING "
        "PROFILE COMPLETED"
    )

    return "\n".join(lines) + "\n"


def json_safe(value):
    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: json_safe(item)
            for key, item
            in value.items()
        }

    if isinstance(value, list):
        return [
            json_safe(item)
            for item in value
        ]

    return value


def main():
    print("=" * 92)
    print(
        "HUD VMS vs USASPENDING AL 14.871 "
        "MONTHLY RESIDUAL / TIMING PROFILE"
    )
    print(CHECKPOINT)
    print("=" * 92)
    print()
    print("Mode: READ ONLY")
    print()

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    input_path = discover_latest_input()

    print(
        "Input:",
        input_path.name,
    )

    rows = load_rows(
        input_path
    )

    if len(rows) != 24:
        print()
        print(
            "HOLD: expected exactly 24 paired "
            f"months; found {len(rows)}."
        )
        return 2

    if any(
        row["vms_pha_count"] != 28
        for row in rows
    ):
        print()
        print(
            "HOLD: at least one VMS month "
            "does not contain 28 PHAs."
        )
        return 2

    annual = annual_profile(
        rows
    )

    if any(
        item["month_count"] != 12
        for item in annual
    ):
        print()
        print(
            "HOLD: fiscal-year month "
            "completeness failed."
        )
        return 2

    lags = lag_profile(
        rows
    )

    report = render_report(
        input_path,
        rows,
        lags,
        annual,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    report_path = (
        OUTPUT_ROOT
        / f"profile_vms_vs_14871_timing_{timestamp}.txt"
    )

    json_path = (
        OUTPUT_ROOT
        / f"profile_vms_vs_14871_timing_{timestamp}.json"
    )

    report_path.write_text(
        report,
        encoding="utf-8",
    )

    payload = {
        "checkpoint": CHECKPOINT,
        "generated_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),
        "input":
            str(
                input_path.relative_to(
                    REPO_ROOT
                )
            ),
        "paired_months":
            len(rows),
        "annual_controls":
            annual,
        "lag_profile":
            lags,
        "monthly_rows":
            rows,
        "methodological_stop": {
            "accounting_source_selected":
                False,
            "residual_classified":
                False,
            "county_allocation_performed":
                False,
            "database_writes":
                False,
            "ledger_decision":
                False,
        },
    }

    json_path.write_text(
        json.dumps(
            json_safe(payload),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "Paired months :",
        len(rows),
    )

    for item in annual:
        print(
            f"FFY{item['fiscal_year']} residual:",
            money(
                item["residual"]
            ),
        )

    valid_lags = [
        item
        for item in lags
        if item["correlation"]
        is not None
    ]

    strongest = max(
        valid_lags,
        key=lambda item:
            abs(item["correlation"]),
    )

    print()
    print(
        "Strongest absolute lag correlation:",
        f"lag {strongest['lag_months']:+d},",
        f"r={number(strongest['correlation'])},",
        f"pairs={strongest['pair_count']}",
    )

    print()
    print(
        "Report:",
        report_path.relative_to(
            REPO_ROOT
        ),
    )

    print(
        "JSON  :",
        json_path.relative_to(
            REPO_ROOT
        ),
    )

    print()
    print(
        "RESULT: PASS — MONTHLY RESIDUAL "
        "AND TIMING PROFILE COMPLETED"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())