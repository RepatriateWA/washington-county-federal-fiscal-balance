from pathlib import Path
from decimal import Decimal
import csv
import io
import shutil
import sys
import traceback

ROOT = Path("accounting_registry/v0_3_3_working")
MATRIX = ROOT / "annual_accounting_matrix.csv"
LEDGER = ROOT / "canonical_annual_ledger.csv"
CROSSWALK = ROOT / "evidence_crosswalk.csv"
CHANGELOG = ROOT / "CHANGELOG.md"
DECISION = ROOT / "SSI_AUTHORIZATION_DECISION.md"
EVIDENCE_SOURCE = Path("235c_ssi_annual_controls.txt")
EVIDENCE_DEST = Path("etl/validation/235c_ssi_annual_controls.txt")

AMOUNTS = {
    2018: ("995804337.00", 848),
    2019: ("1088456509.00", 810),
    2020: ("1104856696.00", 908),
    2021: ("1094843681.00", 905),
    2022: ("1191303562.00", 904),
    2023: ("1168650267.00", 924),
    2024: ("1116434589.00", 894),
}

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def load_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)

def save_csv_content(fields, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=fields, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()

def main():
    print("ETL-235D4 - SSI REGISTRY UPDATE")
    print("=" * 65)

    for path in (
        MATRIX, LEDGER, CROSSWALK, CHANGELOG, EVIDENCE_SOURCE
    ):
        require(path.is_file(), f"Missing file: {path}")

    require(not DECISION.exists(), "Decision file already exists")
    require(not EVIDENCE_DEST.exists(), "Evidence destination exists")

    fields, rows = load_csv(MATRIX)
    ledger_fields, ledger_rows = load_csv(LEDGER)
    cross_fields, cross_rows = load_csv(CROSSWALK)

    require(len(rows) == 161, "Matrix row count mismatch")
    require(len(ledger_rows) == 147, "Ledger row count mismatch")
    require(len(cross_rows) == 22, "Crosswalk row count mismatch")

    require(
        cross_fields == [
            "family_ids", "evidence_role",
            "repository_path", "review_status"
        ],
        "Crosswalk schema mismatch"
    )

    ssi = [r for r in rows if r["family_id"] == "SSA_SSI"]
    require(len(ssi) == 7, "Expected seven SSI observations")

    require(
        {int(r["source_year"]) for r in ssi} == set(AMOUNTS),
        "SSI year mismatch"
    )

    for row in ssi:
        require(
            not row["observed_amount_usd"].strip(),
            "SSI amount already populated"
        )
        require(
            row["ledger_authorization"] == "NOT_YET_AUTHORIZED",
            "Unexpected SSI authorization"
        )
        require(
            row["source_time_basis"] == "UNKNOWN"
            and row["coverage_status"]
                == "NOT_YET_VERIFIED_AT_ANNUAL_GRAIN"
            and row["accounting_status"]
                == "REQUIRES_FAMILY_SCOPED_REVIEW",
            "Unexpected SSI starting status"
        )

    ledger_ssi = [
        r for r in ledger_rows if r["family_id"] == "SSA_SSI"
    ]
    require(len(ledger_ssi) == 7, "SSI ledger mismatch")

    for row in ledger_ssi:
        require(
            row["ledger_status"] == "NOT_YET_AUTHORIZED"
            and not row["authorized_amount_usd"].strip()
            and not row["candidate_observed_amount_usd"].strip(),
            "Unexpected SSI ledger state"
        )

    total = sum(
        Decimal(amount) for amount, _ in AMOUNTS.values()
    )
    require(
        total == Decimal("7760349641.00"),
        "SSI obligation control mismatch"
    )

    source_text = EVIDENCE_SOURCE.read_text(
        encoding="utf-16"
    )
    for expected in (
        "995804337.00",
        "1088456509.00",
        "5676088795.00",
        "PASS",
    ):
        require(
            expected in source_text,
            f"Missing evidence control: {expected}"
        )

    # All preflight checks complete.

    for row in ssi:
        year = int(row["source_year"])
        amount, transactions = AMOUNTS[year]

        row["source_time_basis"] = (
            "FEDERAL_FISCAL_YEAR_OBLIGATION_ACTION_DATE"
        )
        row["observed_amount_usd"] = amount
        row["coverage_status"] = "VERIFIED_AT_ANNUAL_GRAIN"
        row["accounting_status"] = (
            "REQUIRES_EXPENDITURE_BASIS_RECONCILIATION"
        )
        row["evidence_path"] = EVIDENCE_DEST.as_posix()

        row["notes"] = (
            f"ETL-235C: {transactions} WA SSI transactions; "
            "net federal action obligations, not certified "
            "cash expenditures. "
            + (
                "FY2018-2019 historical semantics and missing "
                "recipient/FAIN fields require review."
                if year < 2020 else
                "FY2020-2024 ETL-176 control reproduced."
            )
        )

    cross_rows.append({
        "family_ids": "SSA_SSI",
        "evidence_role": "AUTHORIZATION_WITHHELD_DECISION",
        "repository_path": DECISION.as_posix(),
        "review_status": "ETL_235_EXPENDITURE_BASIS_REQUIRED",
    })

    decision_text = """# SSI Authorization Decision - ETL-235

## Disposition

**NOT_YET_AUTHORIZED â€” expenditure basis required.**

Seven annual Washington SSI observations have been
verified from USAspending Assistance Listing 96.006.

The amounts represent net federal action obligations,
not independently certified federal cash expenditures.

## Annual controls

| FFY | Transactions | Obligations USD |
|---|---:|---:|
| 2018 | 848 | 995804337.00 |
| 2019 | 810 | 1088456509.00 |
| 2020 | 908 | 1104856696.00 |
| 2021 | 905 | 1094843681.00 |
| 2022 | 904 | 1191303562.00 |
| 2023 | 924 | 1168650267.00 |
| 2024 | 894 | 1116434589.00 |

**Total: 6,193 transactions; $7,760,349,641.00.**

ETL-176's FY2020-FY2024 certification was reproduced
exactly: 4,535 transactions and $5,676,088,795.00.

FY2018-FY2019 observations were recovered from the
certified assistance view but remain outside the
original ETL-176 SSI-specific policy period.

## Accounting boundary

SSI is distinct from SSA OASDI under the established
ETL-135/176 overlap policy.

Prior inclusion of SSI in an obligation-based assistance
framework does not establish cash-expenditure eligibility
for the current statewide fiscal-balance ledger.

FY2018-FY2019 records have missing recipient names and
FAIN identifiers in the profiled view.

## Reopening requirements

- Identify an official SSI expenditure/payment source.
- Verify Washington geographic attribution.
- Establish federal fiscal-year cash-payment timing.
- Reconcile payments against obligation controls.
- Preserve OASDI nonduplication safeguards.
- Review FY2018-FY2019 historical semantics.
- Complete a separate ledger authorization decision.

## Registry effect

Seven annual accounting matrix observations populated.
Seven SSI ledger authorizations remain withheld.
Canonical annual ledger unchanged.

## Evidence

- `etl/sql/135_seed_oasdi_overlap_policy.sql`
- `etl/sql/176_seed_ssi_inflow_source_policy.sql`
- `etl/validation/assistance/174b_5b_profile_ssi.sql`
- `etl/validation/235c_ssi_annual_controls.txt`
"""

    changelog_text = CHANGELOG.read_text(
        encoding="utf-8-sig"
    )
    require(
        "ETL-235 - SSI" not in changelog_text,
        "ETL-235 already present in changelog"
    )

    changelog_text += """

## ETL-235 - SSI obligation evidence recovery

- Verified seven FFY2018-FFY2024 SSI observations.
- Recovered $7,760,349,641.00 in net obligations.
- Reproduced ETL-176 FY2020-FY2024 controls.
- Documented FY2018-FY2019 provenance limitations.
- Withheld all seven SSI ledger authorizations.
- Canonical annual ledger unchanged.
"""

    backup = MATRIX.with_name(
        MATRIX.name + ".pre235d.bak"
    )
    require(not backup.exists(), "Matrix backup exists")

    # Write only after all preflight checks pass.
    shutil.copy2(MATRIX, backup)
    shutil.copy2(EVIDENCE_SOURCE, EVIDENCE_DEST)

    MATRIX.write_text(
        save_csv_content(fields, rows),
        encoding="utf-8",
        newline=""
    )
    CROSSWALK.write_text(
        save_csv_content(cross_fields, cross_rows),
        encoding="utf-8",
        newline=""
    )
    DECISION.write_text(
        decision_text, encoding="utf-8"
    )
    CHANGELOG.write_text(
        changelog_text, encoding="utf-8"
    )

    # Post-write validation.
    _, verify_rows = load_csv(MATRIX)
    verify_ssi = [
        r for r in verify_rows if r["family_id"] == "SSA_SSI"
    ]

    require(len(verify_ssi) == 7, "Post-write row mismatch")
    require(
        sum(
            Decimal(r["observed_amount_usd"])
            for r in verify_ssi
        ) == Decimal("7760349641.00"),
        "Post-write amount mismatch"
    )
    require(
        all(
            r["ledger_authorization"] == "NOT_YET_AUTHORIZED"
            for r in verify_ssi
        ),
        "Post-write authorization mismatch"
    )

    _, verify_ledger = load_csv(LEDGER)
    require(
        verify_ledger == ledger_rows,
        "Canonical ledger unexpectedly changed"
    )

    print("ETL-235D4 PASS")
    print("Annual SSI observations updated: 7")
    print("Obligations: $7,760,349,641.00")
    print("SSI ledger authorizations changed: 0")
    print("Canonical ledger unchanged: PASS")
    print("Qualified provisional ledger: 28 / 147")

try:
    main()
except BaseException:
    traceback.print_exc(file=sys.stdout)
    sys.exit(1)
