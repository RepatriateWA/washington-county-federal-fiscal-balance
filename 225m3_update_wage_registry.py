#!/usr/bin/env python3
"""ETL-225M3: Evidence-only wage registry update.

Run from the WCFFBP repository root. Verifies seven annual wage controls
against the existing matrix before updating only coverage_status and
 evidence_path for the 14 civilian/military wage observations.

No database or canonical ledger writes. Creates a pre-update backup.
"""

import csv
import re
import shutil
from decimal import Decimal
from pathlib import Path

ROOT = Path("accounting_registry/v0_3_0_working")
MATRIX = ROOT / "annual_accounting_matrix.csv"
EVIDENCE = Path("225m2_stdout.txt")
BACKUP = ROOT / "annual_accounting_matrix.csv.pre225m3.bak"


def read_console_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8")


def main() -> None:
    with MATRIX.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)

    assert fields is not None, "Missing CSV header"
    assert len(rows) == 161, f"Expected 161 matrix rows; got {len(rows)}"

    pattern = re.compile(
        r"^\s*(20(?:18|19|2[0-4]))\s*\|\s*"
        r"([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*"
        r"([\d.]+)\s*\|\s*([-\d.]+)\s*\|\s*(\w+)\s*$"
    )

    controls = {}
    for line in read_console_text(EVIDENCE).splitlines():
        match = pattern.match(line)
        if match:
            year, civilian, military, total, difference, confidence = match.groups()
            assert year not in controls, f"Duplicate wage control year: {year}"
            controls[year] = (
                Decimal(civilian), Decimal(military), Decimal(total),
                Decimal(difference), confidence,
            )

    assert len(controls) == 7, f"Expected seven wage-control years; got {len(controls)}"
    for year, (civilian, military, total, difference, confidence) in controls.items():
        assert civilian + military == total, f"Component mismatch: {year}"
        assert difference == 0, f"Nonzero reconciliation: {year}"
        assert confidence == "MEDIUM", f"Unexpected confidence: {year}"

    families = {"FEDERAL_CIVILIAN_WAGES": 0, "FEDERAL_MILITARY_WAGES": 1}
    changed = []
    for row in rows:
        family = row["family_id"]
        if family not in families:
            continue

        year = row["source_year"]
        assert year in controls, f"Missing control: {family} {year}"
        expected = controls[year][families[family]]
        actual = Decimal(row["observed_amount_usd"])
        assert actual == expected, f"Amount mismatch: {family} {year}"
        assert row["coverage_status"] == "PRIOR_STATEWIDE_AUDIT_REPORTED", (
            f"Unexpected coverage status: {family} {year}"
        )
        assert row["accounting_status"] == "REQUIRES_FAMILY_SCOPED_REVIEW", (
            f"Unexpected accounting status: {family} {year}"
        )
        assert row["ledger_authorization"] == "NOT_YET_AUTHORIZED", (
            f"Unexpected ledger authorization: {family} {year}"
        )

        row["coverage_status"] = "ETL_225M2_WAGE_COMPONENT_REPRODUCED"
        row["evidence_path"] = (
            "etl/sql/222b_statewide_component_matrix.sql; 225m2_stdout.txt"
        )
        changed.append((family, year))

    assert len(changed) == 14, f"Expected 14 records; got {len(changed)}"
    assert len(set(changed)) == 14, "Duplicate family-year records"

    if BACKUP.exists():
        raise FileExistsError(
            f"Backup already exists: {BACKUP}. Refusing to overwrite it."
        )
    shutil.copy2(MATRIX, BACKUP)

    with MATRIX.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print("ETL-225M3 PASS")
    print("Wage records updated: 14")
    print("Amount mismatches: 0")
    print("Observed dollar amounts: unchanged")
    print("Accounting statuses: unchanged")
    print("Ledger authorizations: unchanged")
    print("Database writes: none")


if __name__ == "__main__":
    main()
