from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EVIDENCE_CSV = (
    ROOT
    / "data"
    / "interim"
    / "omb"
    / "omb_federal_wage_object_class_actuals_2015_2024.csv"
)

REQUIRED_CODES = {
    "11.1",
    "11.3",
    "11.5",
    "11.6",
    "11.7",
    "11.8",
}

EXPECTED_YEARS = set(
    range(2015, 2025)
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def load_rows() -> list[dict]:
    if not EVIDENCE_CSV.exists():
        raise RuntimeError(
            f"Evidence CSV does not exist: {EVIDENCE_CSV}"
        )

    with EVIDENCE_CSV.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as f:
        return list(
            csv.DictReader(f)
        )


def main() -> None:
    rows = load_rows()

    print(f"Evidence file: {EVIDENCE_CSV}")
    print(f"Rows read:     {len(rows)}")
    print()

    # ------------------------------------------------------------------
    # Gate 1 — exactly 60 atomic observations
    # ------------------------------------------------------------------

    if len(rows) != 60:
        raise RuntimeError(
            f"Expected exactly 60 observations; found {len(rows)}."
        )

    # ------------------------------------------------------------------
    # Normalize and validate atomic values
    # ------------------------------------------------------------------

    normalized = []

    for row_number, row in enumerate(
        rows,
        start=2,
    ):
        fiscal_year = int(
            row["target_fiscal_year"]
        )

        budget_vintage = int(
            row["budget_vintage"]
        )

        code = row[
            "object_class_code"
        ].strip()

        millions = int(
            row["obligation_millions"]
        )

        dollars = int(
            row["obligation_dollars"]
        )

        source_page = int(
            row["source_page"]
        )

        if fiscal_year not in EXPECTED_YEARS:
            raise RuntimeError(
                f"Row {row_number}: unexpected fiscal year "
                f"{fiscal_year}."
            )

        if budget_vintage != fiscal_year + 2:
            raise RuntimeError(
                f"Row {row_number}: FFY{fiscal_year} maps to "
                f"FY{budget_vintage}; expected FY{fiscal_year + 2}."
            )

        if row["value_status"] != "ACTUAL":
            raise RuntimeError(
                f"Row {row_number}: expected ACTUAL; "
                f"found {row['value_status']!r}."
            )

        if (
            row["accounting_measure"]
            != "OBLIGATIONS_BY_OBJECT_CLASS"
        ):
            raise RuntimeError(
                f"Row {row_number}: unexpected accounting measure."
            )

        if row["scope"] != "GOVERNMENT_WIDE":
            raise RuntimeError(
                f"Row {row_number}: expected GOVERNMENT_WIDE scope."
            )

        if code not in REQUIRED_CODES:
            raise RuntimeError(
                f"Row {row_number}: unexpected object class {code!r}."
            )

        if millions <= 0:
            raise RuntimeError(
                f"Row {row_number}: obligation amount must be positive."
            )

        if dollars != millions * 1_000_000:
            raise RuntimeError(
                f"Row {row_number}: dollar conversion failure for "
                f"FFY{fiscal_year} object class {code}."
            )

        if source_page != 3:
            raise RuntimeError(
                f"Row {row_number}: expected source page 3; "
                f"found {source_page}."
            )

        if (
            row["source_verification"]
            != "MANUALLY_VERIFIED"
        ):
            raise RuntimeError(
                f"Row {row_number}: source is not marked "
                "MANUALLY_VERIFIED."
            )

        source_path = (
            ROOT
            / row["source_file"]
        )

        if not source_path.exists():
            raise RuntimeError(
                f"Row {row_number}: source PDF does not exist: "
                f"{source_path}"
            )

        actual_sha256 = sha256_file(
            source_path
        )

        expected_sha256 = row[
            "source_sha256"
        ].strip()

        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"Row {row_number}: SHA-256 mismatch for "
                f"{source_path}"
            )

        normalized.append(
            {
                "fiscal_year":
                    fiscal_year,
                "budget_vintage":
                    budget_vintage,
                "code":
                    code,
                "millions":
                    millions,
            }
        )

    # ------------------------------------------------------------------
    # Gate 2 — fiscal-year coverage
    # ------------------------------------------------------------------

    observed_years = {
        row["fiscal_year"]
        for row in normalized
    }

    if observed_years != EXPECTED_YEARS:
        raise RuntimeError(
            "Fiscal-year coverage is not exactly FFY2015-FFY2024."
        )

    # ------------------------------------------------------------------
    # Gate 3 — duplicate atomic keys
    # ------------------------------------------------------------------

    keys = [
        (
            row["fiscal_year"],
            row["budget_vintage"],
            row["code"],
        )
        for row in normalized
    ]

    if len(keys) != len(set(keys)):
        raise RuntimeError(
            "Duplicate atomic observation key detected."
        )

    # ------------------------------------------------------------------
    # Gate 4 — exactly six required classes per fiscal year
    # ------------------------------------------------------------------

    by_year: dict[int, dict[str, int]] = defaultdict(dict)

    for row in normalized:
        by_year[
            row["fiscal_year"]
        ][
            row["code"]
        ] = row["millions"]

    for fiscal_year in sorted(
        EXPECTED_YEARS
    ):
        observed_codes = set(
            by_year[fiscal_year]
        )

        if observed_codes != REQUIRED_CODES:
            raise RuntimeError(
                f"FFY{fiscal_year}: object-class coverage failure. "
                f"Observed: {sorted(observed_codes)}"
            )

    # ------------------------------------------------------------------
    # Gate 5 — derive accounting controls independently
    # ------------------------------------------------------------------

    controls = []

    for fiscal_year in sorted(
        EXPECTED_YEARS
    ):
        oc = by_year[
            fiscal_year
        ]

        military = (
            oc["11.6"]
            + oc["11.7"]
        )

        nonmilitary = (
            oc["11.1"]
            + oc["11.3"]
            + oc["11.5"]
            + oc["11.8"]
        )

        total = (
            military
            + nonmilitary
        )

        controls.append(
            {
                "fiscal_year":
                    fiscal_year,
                "nonmilitary":
                    nonmilitary,
                "military":
                    military,
                "total":
                    total,
            }
        )

    # ------------------------------------------------------------------
    # Gate 6 — explicitly detect and acknowledge FY2017/FY2018
    # source duplication
    # ------------------------------------------------------------------

    fy2017 = by_year[
        2017
    ]

    fy2018 = by_year[
        2018
    ]

    if fy2017 != fy2018:
        raise RuntimeError(
            "Expected manually verified FY2017/FY2018 source "
            "duplication is no longer present. Investigate before "
            "continuing."
        )

    # ------------------------------------------------------------------
    # Success report
    # ------------------------------------------------------------------

    print("=" * 72)
    print("OMB WAGE OBJECT-CLASS EVIDENCE VALIDATION PASSED")
    print("=" * 72)

    print()
    print("Atomic evidence:")
    print("  Observations:       60")
    print("  Fiscal years:       FFY2015-FFY2024")
    print("  Classes per year:   6")
    print("  Value status:       ACTUAL")
    print("  Scope:              GOVERNMENT_WIDE")
    print("  Source verification: MANUALLY_VERIFIED")
    print("  Source SHA-256:     VERIFIED")
    print()

    print(
        "FY2017/FY2018 identical published source values: "
        "VERIFIED AND PRESERVED"
    )

    print()
    print(
        f"{'FFY':<6}"
        f"{'Nonmilitary':>16}"
        f"{'Military':>16}"
        f"{'Total':>16}"
    )

    print("-" * 54)

    for row in controls:
        print(
            f"{row['fiscal_year']:<6}"
            f"{row['nonmilitary']:>15,}"
            f"{row['military']:>16,}"
            f"{row['total']:>16,}"
        )

    print()
    print(
        "Units: millions of dollars of obligations."
    )


if __name__ == "__main__":
    main()