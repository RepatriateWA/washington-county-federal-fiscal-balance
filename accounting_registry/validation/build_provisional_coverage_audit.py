"""ETL-245R6: read-only provisional presentation coverage audit."""

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "accounting_registry/v0_3_3_working"
CHART = ROOT / "docs/presentations/wcffbp-244b/data/244b_chart_data.csv"

# Direct chart-column matches only. No inferred inclusion.
DIRECT = {
    "IRS_GROSS_COLLECTIONS": "net_irs_billion_usd",
    "SSA_OASDI": "SSA_OASDI",
    "MEDICARE_FFS_AB": "MEDICARE_FFS_AB",
    "MEDICARE_PART_C": "MEDICARE_PART_C",
    "MEDICARE_PART_D": "MEDICARE_PART_D",
    "MEDICAID": "MEDICAID",
    "CHIP": "CHIP",
    "VA_GDX": "VA_GDX",
    "FEDERAL_CIVILIAN_WAGES": "FEDERAL_CIVILIAN_WAGES",
    "FEDERAL_MILITARY_WAGES": "FEDERAL_MILITARY_WAGES",
}

# These mappings require additional accounting reconciliation.
POSSIBLE_AGGREGATE = {
    "SSA_SSI",
    "RAILROAD_RETIREMENT",
    "HOUSING_CHOICE_VOUCHERS",
    "USASPENDING_ASSISTANCE",
}

REFERENCE = {
    "USASPENDING_PROCUREMENT":
        "DoD/DoE/other procurement reference columns",
    "ROCKEFELLER_BOP":
        "Independent benchmark; not a payment stream",
    "MEDICARE_CORE":
        "Non-additive reporting parent",
}

def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), set(reader.fieldnames or [])

def main():
    print("ETL-245R6 — PROVISIONAL COVERAGE AUDIT")
    print("READ ONLY — NO DATABASE OR REGISTRY WRITES")
    print("=" * 78)

    families, _ = read_csv(REGISTRY / "source_family_registry.csv")
    matrix, _ = read_csv(REGISTRY / "annual_accounting_matrix.csv")
    charts, columns = read_csv(CHART)

    if len(charts) != 7:
        raise ValueError("Expected seven annual chart records")

    years = {str(y) for y in range(2018, 2025)}
    if {r["fiscal_year"] for r in charts} != years:
        raise ValueError("Chart fiscal-year coverage mismatch")

    print(f"REGISTERED FAMILIES: {len(families)}")
    print(f"ANNUAL MATRIX ROWS: {len(matrix)}")
    print(f"CHART YEARS: {len(charts)}")
    print()

    counts = Counter()

    for family in families:
        fid = family["family_id"]
        annual = [r for r in matrix if r["family_id"] == fid]
        observed = sum(
            bool(r["observed_amount_usd"].strip())
            for r in annual
        )

        if fid in DIRECT:
            column = DIRECT[fid]
            if column not in columns:
                raise ValueError(f"Missing chart component: {column}")
            treatment = "EXPLICIT_CHART_COMPONENT"
            detail = column
        elif fid in REFERENCE:
            treatment = "REFERENCE_OR_NONADDITIVE"
            detail = REFERENCE[fid]
        elif fid in POSSIBLE_AGGREGATE:
            treatment = "AGGREGATE_MEMBERSHIP_UNVERIFIED"
            detail = "Requires transaction/program reconciliation"
        else:
            treatment = "PRESENTATION_TREATMENT_UNRESOLVED"
            detail = "No verified direct chart mapping"

        counts[treatment] += 1

        print(
            f"{fid} | {treatment} | "
            f"observed={observed}/{len(annual)} | "
            f"detail={detail}"
        )

    print("\n=== TREATMENT COUNTS ===")
    for treatment, count in sorted(counts.items()):
        print(f"{treatment}: {count}")

    print("\n=== REQUIRED REVIEW ALERTS ===")
    for fid in (
        "FEDERAL_MILITARY_RETIREMENT",
        "FEDERAL_CIVILIAN_RETIREMENT",
    ):
        print(f"REVIEW: {fid} — source and accounting treatment unresolved")

    print("\n=== LIMITATIONS ===")
    print("A direct chart mapping does not establish ledger authorization.")
    print("Aggregate membership is not inferred.")
    print("Procurement reference columns are not presumed additive.")
    print("Chart arithmetic and source-to-chart lineage are not tested here.")
    print("Missing annual amounts are not zeros.")
    print("\nRESULT: STRUCTURAL COVERAGE AUDIT COMPLETE")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, csv.Error) as exc:
        print(f"RESULT: FAIL — {exc}", file=sys.stderr)
        sys.exit(1)
