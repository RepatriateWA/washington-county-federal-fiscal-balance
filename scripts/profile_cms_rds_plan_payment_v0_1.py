from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl


ROOT = Path("data/raw/cms/medicare_advantage/plan_payment")

OUTDIR = Path(
    "data/raw/cms/medicare_rds/validation/"
    "rds_plan_payment_profile_v0_1"
)

YEARS = range(2015, 2025)

INVENTORY_FILE = OUTDIR / "cms_rds_plan_payment_inventory_v0_1.csv"
SHEETS_FILE = OUTDIR / "cms_rds_plan_payment_sheets_v0_1.csv"
COLUMNS_FILE = OUTDIR / "cms_rds_plan_payment_columns_v0_1.csv"
SCHEMA_FILE = OUTDIR / "cms_rds_plan_payment_schema_v0_1.csv"
CHECKS_FILE = OUTDIR / "cms_rds_plan_payment_checks_v0_1.csv"
REPORT_FILE = OUTDIR / "cms_rds_plan_payment_report_v0_1.txt"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def norm_key(value: object) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        normalize(value).lower(),
    ).strip("_")


def check(
    label: str,
    passed: bool,
    detail: str,
) -> dict[str, str]:
    return {
        "check": label,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
    }


def discover_zip_for_year(year: int) -> list[Path]:
    candidates: list[Path] = []

    if not ROOT.exists():
        return candidates

    for path in ROOT.rglob("*.zip"):
        text = str(path).lower()

        if str(year) not in text:
            continue

        # Avoid unrelated archives if any coexist below this root.
        if "payment" not in text and "plan" not in text:
            continue

        candidates.append(path)

    return sorted(candidates)


def find_header_row(ws, max_rows: int = 30) -> tuple[int | None, list[str]]:
    """
    Identify the most plausible header row.

    RDS workbooks may contain title or note rows before the tabular header,
    so do not assume row 1.
    """
    best_row: int | None = None
    best_values: list[str] = []
    best_score = -1

    keywords = {
        "state",
        "organization",
        "sponsor",
        "plan",
        "employer",
        "union",
        "retiree",
        "subsidy",
        "payment",
        "amount",
        "rds",
        "participants",
        "beneficiaries",
        "zip",
        "county",
        "contract",
    }

    limit = min(ws.max_row, max_rows)

    for row_number in range(1, limit + 1):
        values = [
            normalize(cell.value)
            for cell in ws[row_number]
        ]

        nonblank = [v for v in values if v]

        if len(nonblank) < 2:
            continue

        normalized = {norm_key(v) for v in nonblank}

        keyword_hits = sum(
            any(keyword in item for item in normalized)
            for keyword in keywords
        )

        score = len(nonblank) + (keyword_hits * 5)

        if score > best_score:
            best_score = score
            best_row = row_number
            best_values = values

    return best_row, best_values


def main() -> None:
    print("=" * 100)
    print("CMS RETIREE DRUG SUBSIDY PLAN PAYMENT STRUCTURAL PROFILER v0.1")
    print("=" * 100)
    print()
    print("READ-ONLY: no database writes")
    print("No Washington-dollar reconstruction is performed.")
    print()

    OUTDIR.mkdir(parents=True, exist_ok=True)

    inventory: list[dict] = []
    sheet_rows: list[dict] = []
    column_rows: list[dict] = []
    checks: list[dict] = []

    selected_by_year: dict[int, tuple[Path, str, bytes]] = {}

    # ------------------------------------------------------------------
    # Locate one RDS workbook for every required year.
    # ------------------------------------------------------------------

    for year in YEARS:
        zip_candidates = discover_zip_for_year(year)

        matches: list[tuple[Path, str, bytes]] = []

        for zip_path in zip_candidates:
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    for member in zf.namelist():
                        member_lower = member.lower()

                        if not member_lower.endswith(
                            (".xlsx", ".xlsm")
                        ):
                            continue

                        if "rds" not in member_lower:
                            continue

                        data = zf.read(member)
                        matches.append(
                            (zip_path, member, data)
                        )

            except zipfile.BadZipFile:
                inventory.append(
                    {
                        "year": year,
                        "zip_path": str(zip_path),
                        "member": "",
                        "member_bytes": "",
                        "member_sha256": "",
                        "status": "BAD_ZIP",
                    }
                )

        # Deduplicate identical embedded RDS workbook bytes.
        unique_by_hash: dict[
            str,
            tuple[Path, str, bytes]
        ] = {}

        for item in matches:
            digest = sha256_bytes(item[2])
            unique_by_hash.setdefault(digest, item)

        unique_matches = list(unique_by_hash.values())

        for zip_path, member, data in matches:
            inventory.append(
                {
                    "year": year,
                    "zip_path": str(zip_path),
                    "member": member,
                    "member_bytes": len(data),
                    "member_sha256": sha256_bytes(data),
                    "status": "RDS_CANDIDATE",
                }
            )

        if len(unique_matches) == 1:
            selected_by_year[year] = unique_matches[0]

        elif len(unique_matches) == 0:
            inventory.append(
                {
                    "year": year,
                    "zip_path": "",
                    "member": "",
                    "member_bytes": "",
                    "member_sha256": "",
                    "status": "NO_RDS_WORKBOOK",
                }
            )

        else:
            inventory.append(
                {
                    "year": year,
                    "zip_path": "",
                    "member": "",
                    "member_bytes": "",
                    "member_sha256": "",
                    "status": (
                        f"AMBIGUOUS_{len(unique_matches)}"
                        "_UNIQUE_RDS_WORKBOOKS"
                    ),
                }
            )

    checks.append(
        check(
            "Required CY2015-CY2024 RDS workbooks resolved uniquely",
            len(selected_by_year) == 10,
            f"{len(selected_by_year)}/10 years",
        )
    )

    # ------------------------------------------------------------------
    # Inspect workbook structure.
    # ------------------------------------------------------------------

    schemas_by_sheet: dict[str, defaultdict[str, set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )

    geography_terms = {
        "state",
        "state_code",
        "state_abbreviation",
        "county",
        "county_name",
        "county_code",
        "fips",
        "zip",
        "zip_code",
        "zipcode",
        "address",
        "city",
    }

    geography_columns_found: list[tuple[int, str, str]] = []

    for year in sorted(selected_by_year):
        zip_path, member, data = selected_by_year[year]

        try:
            wb = openpyxl.load_workbook(
                io.BytesIO(data),
                read_only=True,
                data_only=True,
            )

        except Exception as exc:
            sheet_rows.append(
                {
                    "year": year,
                    "zip_path": str(zip_path),
                    "member": member,
                    "sheet": "",
                    "max_row": "",
                    "max_column": "",
                    "header_row": "",
                    "status": f"WORKBOOK_ERROR: {exc}",
                }
            )
            continue

        for ws in wb.worksheets:
            header_row, headers = find_header_row(ws)

            sheet_rows.append(
                {
                    "year": year,
                    "zip_path": str(zip_path),
                    "member": member,
                    "sheet": ws.title,
                    "max_row": ws.max_row,
                    "max_column": ws.max_column,
                    "header_row": (
                        header_row
                        if header_row is not None
                        else ""
                    ),
                    "status": (
                        "PROFILED"
                        if header_row is not None
                        else "NO_HEADER_FOUND"
                    ),
                }
            )

            if header_row is None:
                continue

            for ordinal, header in enumerate(headers, start=1):
                if not header:
                    continue

                key = norm_key(header)

                column_rows.append(
                    {
                        "year": year,
                        "sheet": ws.title,
                        "header_row": header_row,
                        "ordinal": ordinal,
                        "column_name": header,
                        "normalized_column": key,
                    }
                )

                schemas_by_sheet[ws.title][key].add(year)

                if (
                    key in geography_terms
                    or any(
                        term in key
                        for term in [
                            "state",
                            "county",
                            "fips",
                            "zip",
                            "address",
                            "city",
                        ]
                    )
                ):
                    geography_columns_found.append(
                        (year, ws.title, header)
                    )

        wb.close()

    # ------------------------------------------------------------------
    # Build cross-year schema table.
    # ------------------------------------------------------------------

    schema_rows: list[dict] = []

    for sheet in sorted(schemas_by_sheet):
        for column in sorted(schemas_by_sheet[sheet]):
            years_present = sorted(
                schemas_by_sheet[sheet][column]
            )

            schema_rows.append(
                {
                    "sheet": sheet,
                    "normalized_column": column,
                    "years_present": ",".join(
                        str(y) for y in years_present
                    ),
                    "year_count": len(years_present),
                    "present_all_10_years": (
                        "YES"
                        if len(years_present) == 10
                        else "NO"
                    ),
                }
            )

    # ------------------------------------------------------------------
    # Structural checks.
    # ------------------------------------------------------------------

    profiled_years = {
        int(row["year"])
        for row in sheet_rows
        if row["status"] == "PROFILED"
    }

    checks.append(
        check(
            "All resolved RDS workbooks opened and profiled",
            profiled_years == set(YEARS),
            f"{len(profiled_years)}/10 years",
        )
    )

    checks.append(
        check(
            "At least one worksheet profiled per required year",
            all(
                any(
                    int(row["year"]) == year
                    and row["status"] == "PROFILED"
                    for row in sheet_rows
                )
                for year in YEARS
            ),
            (
                f"{len(sheet_rows):,} worksheet profile rows"
            ),
        )
    )

    checks.append(
        check(
            "RDS columns inventoried",
            len(column_rows) > 0,
            f"{len(column_rows):,} column observations",
        )
    )

    # This is intentionally informational rather than requiring geography.
    # We do not know yet whether RDS is geographically usable.
    geography_detail = (
        f"{len(geography_columns_found):,} geography-like "
        "column observations"
    )

    checks.append(
        check(
            "Geographic structure explicitly inventoried",
            True,
            geography_detail,
        )
    )

    # ------------------------------------------------------------------
    # Write evidence.
    # ------------------------------------------------------------------

    def write_csv(
        path: Path,
        rows: list[dict],
        fields: list[str],
    ) -> None:
        with path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=fields,
            )
            writer.writeheader()
            writer.writerows(rows)

    write_csv(
        INVENTORY_FILE,
        inventory,
        [
            "year",
            "zip_path",
            "member",
            "member_bytes",
            "member_sha256",
            "status",
        ],
    )

    write_csv(
        SHEETS_FILE,
        sheet_rows,
        [
            "year",
            "zip_path",
            "member",
            "sheet",
            "max_row",
            "max_column",
            "header_row",
            "status",
        ],
    )

    write_csv(
        COLUMNS_FILE,
        column_rows,
        [
            "year",
            "sheet",
            "header_row",
            "ordinal",
            "column_name",
            "normalized_column",
        ],
    )

    write_csv(
        SCHEMA_FILE,
        schema_rows,
        [
            "sheet",
            "normalized_column",
            "years_present",
            "year_count",
            "present_all_10_years",
        ],
    )

    write_csv(
        CHECKS_FILE,
        checks,
        [
            "check",
            "status",
            "detail",
        ],
    )

    # ------------------------------------------------------------------
    # Human-readable report.
    # ------------------------------------------------------------------

    lines: list[str] = []

    lines.append(
        "CMS RETIREE DRUG SUBSIDY PLAN PAYMENT "
        "STRUCTURAL PROFILE v0.1"
    )
    lines.append("=" * 78)
    lines.append("")
    lines.append(
        "Scope: CY2015-CY2024 annual CMS Plan Payment archives."
    )
    lines.append(
        "Purpose: source discovery and structural profiling only."
    )
    lines.append(
        "No Washington-dollar reconstruction or ledger inclusion "
        "is performed."
    )
    lines.append("")

    lines.append("RESOLVED WORKBOOKS")
    lines.append("-" * 78)

    for year in YEARS:
        if year in selected_by_year:
            zip_path, member, data = selected_by_year[year]
            lines.append(
                f"{year}: {member} "
                f"[{len(data):,} bytes; "
                f"SHA256={sha256_bytes(data)}]"
            )
        else:
            lines.append(f"{year}: UNRESOLVED")

    lines.append("")
    lines.append("GEOGRAPHY-LIKE COLUMNS")
    lines.append("-" * 78)

    if geography_columns_found:
        for year, sheet, header in geography_columns_found:
            lines.append(
                f"{year} | {sheet} | {header}"
            )
    else:
        lines.append("NONE IDENTIFIED")

    lines.append("")
    lines.append("BOUNDARY")
    lines.append("-" * 78)
    lines.append(
        "Presence of an RDS workbook does not establish that RDS "
        "is additive to Washington Medicare inflow."
    )
    lines.append(
        "Any sponsor, employer, address, state, county, or ZIP field "
        "must be semantically interpreted before geographic attribution."
    )
    lines.append(
        "No RDS dollar receives a plus sign until payment semantics, "
        "overlap, and Washington geographic incidence are certified."
    )

    REPORT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # Console.
    # ------------------------------------------------------------------

    print("=" * 100)
    print("RESOLVED RDS WORKBOOKS")
    print("=" * 100)

    for year in YEARS:
        if year not in selected_by_year:
            print(f"{year}: UNRESOLVED")
            continue

        zip_path, member, data = selected_by_year[year]

        print(
            f"{year}: {member} | "
            f"{len(data):,} bytes | "
            f"SHA256={sha256_bytes(data)[:16]}..."
        )

    print()
    print("=" * 100)
    print("WORKSHEETS")
    print("=" * 100)

    for row in sheet_rows:
        print(
            f"{row['year']} | "
            f"{row['sheet']} | "
            f"rows={row['max_row']} | "
            f"cols={row['max_column']} | "
            f"header={row['header_row']} | "
            f"{row['status']}"
        )

    print()
    print("=" * 100)
    print("COLUMN INVENTORY")
    print("=" * 100)

    by_year_sheet: dict[tuple[int, str], list[str]] = defaultdict(list)

    for row in column_rows:
        by_year_sheet[
            (int(row["year"]), row["sheet"])
        ].append(row["column_name"])

    for key in sorted(by_year_sheet):
        year, sheet = key
        print()
        print(f"{year} | {sheet}")
        for column in by_year_sheet[key]:
            print(f"  - {column}")

    print()
    print("=" * 100)
    print("GEOGRAPHY-LIKE COLUMNS")
    print("=" * 100)

    if geography_columns_found:
        for year, sheet, header in geography_columns_found:
            print(
                f"{year} | {sheet} | {header}"
            )
    else:
        print("NONE IDENTIFIED")

    print()
    print("=" * 100)
    print("CHECKS")
    print("=" * 100)

    for row in checks:
        print(
            f"{row['status']:4} | "
            f"{row['check']} | "
            f"{row['detail']}"
        )

    overall_pass = all(
        row["status"] == "PASS"
        for row in checks
    )

    print()
    print("=" * 100)
    print(
        "OVERALL: "
        + ("PASS" if overall_pass else "FAIL")
    )
    print("=" * 100)

    print()
    print("IMPORTANT:")
    print(
        "  Structural PASS does not mean RDS is additive "
        "or geographically attributable to Washington."
    )
    print(
        "  Next gate = RDS payment semantics and geographic meaning."
    )

    print()
    print("Evidence written:")
    print(f"  {INVENTORY_FILE}")
    print(f"  {SHEETS_FILE}")
    print(f"  {COLUMNS_FILE}")
    print(f"  {SCHEMA_FILE}")
    print(f"  {CHECKS_FILE}")
    print(f"  {REPORT_FILE}")

    if not overall_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
