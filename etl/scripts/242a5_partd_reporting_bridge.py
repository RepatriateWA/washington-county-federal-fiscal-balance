
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import csv
import sys

ROOT = Path.cwd()
REG = ROOT / "accounting_registry/v0_3_3_working"
SRC = ROOT / "evidence/statewide/provisional_v0_1"
OUT = SRC / "242a5_partd_inclusive_balance.csv"
VALID = ROOT / "242a5_partd_validation.txt"
DECISION = REG / "MEDICARE_PART_D_PROVISIONAL_DECISION.md"
CHANGELOG = REG / "CHANGELOG.md"

CENT = Decimal("0.01")
YEARS = list(range(2018, 2025))

def money(v):
    return Decimal(str(v)).quantize(CENT, rounding=ROUND_HALF_UP)

def fmt(v):
    return f"{money(v):.2f}"

def read_csv(path):
    if not path.exists():
        raise RuntimeError(f"Missing required file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def by_year(rows, key):
    result = {}
    for r in rows:
        year = int(r[key])
        if year in result:
            raise RuntimeError(f"Duplicate year: {year}")
        result[year] = r
    if sorted(result) != YEARS:
        raise RuntimeError("Expected exactly 2018-2024")
    return result

def run():
    balance = by_year(
        read_csv(SRC / "238b8_expanded_balance.csv"),
        "fiscal_year"
    )

    ledger_rows = [
        r for r in read_csv(REG / "canonical_annual_ledger.csv")
        if r["family_id"] == "MEDICARE_PART_D"
    ]
    partd = by_year(ledger_rows, "fiscal_year")

    matrix_rows = [
        r for r in read_csv(REG / "annual_accounting_matrix.csv")
        if r["family_id"] == "MEDICARE_PART_D"
    ]
    matrix = by_year(matrix_rows, "source_year")

    cms_path = (
        ROOT / "data/raw/cms/medicare/validation/"
        "accounting_boundary_v0_1/"
        "cms_medicare_accounting_boundary_annual_v0_1.csv"
    )
    cms_rows = read_csv(cms_path)
    cms = {int(r["year"]): r for r in cms_rows}

    if not all(y in cms for y in YEARS):
        raise RuntimeError("CMS annual observations incomplete")

    output = []
    total_partd = Decimal("0")
    total_original = Decimal("0")
    total_revised = Decimal("0")
    total_irs_gross = Decimal("0")

    for year in YEARS:
        b, d, m, c = (
            balance[year], partd[year],
            matrix[year], cms[year]
        )

        observed = money(d["candidate_observed_amount_usd"])

        assert d["ledger_status"] == "NOT_YET_AUTHORIZED"
        assert not d["authorized_amount_usd"].strip()
        assert d["measure_basis"] == "CALENDAR_YEAR"
        assert d["direction"] == "INFLOW"

        assert m["ledger_authorization"] == "NOT_YET_AUTHORIZED"
        assert m["accounting_status"] == "ADDITIVITY_CERTIFIED_WITHIN_CORE"
        assert money(m["observed_amount_usd"]) == observed

        assert money(c["partd_dollars"]) == observed
        assert c["payment_stream_additivity"] == "CERTIFIED_ADDITIVE"
        assert c["partd_coverage_status"] == "PARTIAL_DOLLAR_COVERAGE"
        assert c["final_ledger_status"] == "NOT_YET_AUTHORIZED"
        assert c["ffy_conversion_status"] == "NOT_AUTHORIZED"

        if year == 2024:
            assert "JAN_SEP" in c["annual_completeness"]
        else:
            assert "FULL_YEAR_WINDOW" in c["annual_completeness"]

        assert b["refund_adjustment_applied"] == "NO"

        old_inflow = money(b["expanded_inflows_usd"])
        old_balance = money(b["expanded_provisional_balance_usd"])
        irs_gross = money(b["irs_gross_collections_usd"])

        assert old_inflow - irs_gross == old_balance

        new_inflow = old_inflow + observed
        new_balance = old_balance + observed

        output.append({
            "reporting_year": year,
            "existing_expanded_inflows_usd": fmt(old_inflow),
            "partd_qualified_addition_usd": fmt(observed),
            "partd_inclusive_inflows_usd": fmt(new_inflow),
            "irs_gross_collections_usd": fmt(irs_gross),
            "existing_gross_basis_balance_usd": fmt(old_balance),
            "partd_inclusive_gross_basis_balance_usd": fmt(new_balance),
            "partd_measure_basis": "CALENDAR_YEAR",
            "partd_coverage": (
                "PARTIAL_DOLLAR_COVERAGE_JAN_SEP"
                if year == 2024
                else "PARTIAL_DOLLAR_COVERAGE"
            ),
            "cross_family_overlap_status": "QUALIFIED_NOT_UNIVERSALLY_CERTIFIED",
            "reporting_status": "QUALIFIED_PROVISIONAL",
            "canonical_ledger_changed": "NO",
        })

        total_partd += observed
        total_original += old_inflow
        total_revised += new_inflow
        total_irs_gross += irs_gross

    assert total_partd == Decimal("9869347614.65")
    assert total_original == Decimal("577050573172.54")
    assert total_revised == Decimal("586919920787.19")
    assert total_irs_gross == Decimal("877156759000.00")

    # Existing seven-year IRS refund control. This is an aggregate
    # reconciliation, NOT a substitute for annual IRS-net observations.
    refunds = Decimal("92094284000.00")
    irs_net = total_irs_gross - refunds
    net_balance = total_revised - irs_net

    assert irs_net == Decimal("785062475000.00")
    assert net_balance == Decimal("-198142554212.81")

    validation = f"""ETL-242A5 PART D REPORTING BRIDGE
RESULT: PASS
Years: 2018-2024
CMS/registry/annual-matrix amounts: MATCH TO CENT
Part D additivity within Medicare: CERTIFIED
Selected-assistance cross-family overlap: QUALIFIED, NOT UNIVERSALLY CERTIFIED
Part D coverage: PARTIAL IN ALL YEARS
2024 Part D: JAN-SEP ONLY
Calendar-to-FFY conversion: NOT AUTHORIZED
Canonical ledger modification: NONE

Existing expanded inflows: ${fmt(total_original)}
Part D qualified addition: ${fmt(total_partd)}
Part D-inclusive inflows: ${fmt(total_revised)}
IRS gross collections: ${fmt(total_irs_gross)}
Seven-year IRS refunds control: ${fmt(refunds)}
IRS net collections control: ${fmt(irs_net)}
Part D-inclusive seven-year IRS-net balance: ${fmt(net_balance)}

IMPORTANT:
The annual CSV reports gross-basis balances because the
source expanded-balance file has no annual refund adjustment.
The seven-year net control is not an annual net-balance series.
"""

    decision = f"""# Medicare Part D - Qualified Provisional Reporting Decision

## ETL-242A5

**Disposition: INCLUDE IN QUALIFIED PROVISIONAL REPORTING.**

Seven-year observed Part D addition: **${fmt(total_partd)}**.

This is a reporting-layer decision, not canonical-ledger authorization.

## Evidence

- CMS Medicare accounting boundary certification v0.1.
- CMS payment-stream additivity certification v0.1.
- CMS Medicare accounting integration annual profile.
- ETL-242A2 and ETL-242A3 evidence reviews.
- ETL-242A5 exact registry/annual-matrix/CMS reconciliation.

Original Medicare A/B, Part C, and Part D represent distinct
payment streams. Do not separately add the Medicare Core parent.
The Part D reconciliation workbook is a control, not another inflow.
USAspending AL 93.774 is an identified Medicare SMI duplicate.

## Scope and limitations

- Part D uses observed Washington county CPSC enrollment linked
  to CMS plan-payment observations.
- Only exact same-year contract/PBP matches are reconstructed.
- Unmatched and suppressed payment dollars are not imputed.
- Part D has partial dollar coverage in all seven years.
- Calendar year 2024 contains January-September Part D only.
- Calendar-year observations are not converted to FFY cash flows.
- The selected-assistance cross-family nonduplication review is
  qualified, not universally certified.
- Prior Part D reconciliation parent-organization failures remain
  documented; no failed control has been silently overridden.

## Ledger protection

All seven MEDICARE_PART_D canonical rows retain
NOT_YET_AUTHORIZED, with blank authorized amounts.
No database writes or canonical ledger modifications.

## Reporting

Use 242a5_partd_inclusive_balance.csv as a separate qualified
reporting bridge. Preserve the existing expanded-balance file.
The bridge's annual balances use IRS gross collections.
A separate seven-year IRS-net control incorporates aggregate refunds;
do not present it as annual IRS-net evidence.

## Reopening criteria

Reopen only for materially new federal payment evidence,
a demonstrated cross-family overlap, corrected CMS observations,
revised source coverage, or an approved CY-to-FFY conversion.

Do not repeat the already certified Medicare A/B-Part C-Part D
payment-stream additivity investigation without new evidence.
"""

    entry = """
## ETL-242A5 - Medicare Part D qualified provisional reporting

- Recovered and reused certified Medicare stream additivity.
- Reconciled seven 2018-2024 Part D candidate amounts to CMS and registry.
- Qualified provisional addition: $9,869,347,614.65.
- Preserved partial-dollar coverage and 2024 Jan-Sep limitation.
- Preserved calendar-year labels and mixed-basis reporting warning.
- Cross-family selected-assistance nonduplication remains qualified.
- Created separate reporting bridge; canonical ledger unchanged.
- Decision: MEDICARE_PART_D_PROVISIONAL_DECISION.md.
"""

    # Numerical and status checks are complete before any writes.
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)

    VALID.write_text(validation, encoding="utf-8")
    DECISION.write_text(decision, encoding="utf-8")

    changelog = CHANGELOG.read_text(encoding="utf-8-sig")
    if "## ETL-242A5 - Medicare Part D" not in changelog:
        with CHANGELOG.open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n" + entry)

    print(validation)
    print("ETL-242A5: PASS - reporting bridge and registry decision written")

if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"ETL-242A5: FAIL - {exc}", file=sys.stderr)
        sys.exit(1)
