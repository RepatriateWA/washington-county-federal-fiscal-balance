from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from typing import Any

import openpyxl


ROOT = Path(
    "data/raw/cms/medicare_rds/"
    "program_statistics_partd_enrollment"
)

OUTDIR = (
    ROOT
    / "validation"
    / "mdcr_enroll_d3_wa_residence_v0_3"
)

ANNUAL_OUT = (
    OUTDIR
    / "cms_mdcr_enroll_d3_wa_rds_enrollment_v0_3.csv"
)

GEOGRAPHY_OUT = (
    OUTDIR
    / "cms_mdcr_enroll_d3_geography_profile_v0_3.csv"
)

CHECKS_OUT = (
    OUTDIR
    / "cms_mdcr_enroll_d3_wa_residence_checks_v0_3.csv"
)

REPORT_OUT = (
    OUTDIR
    / "cms_mdcr_enroll_d3_wa_residence_report_v0_3.txt"
)

YEARS = list(range(2015, 2024))

EXPECTED_AREA_HEADER = "Area of Residence"

RDS_HEADER_PATTERN = re.compile(
    r"Retiree\s+Drug\s+Subsidy\s*"
    r"\(\s*No\s+Part\s+D\s+Plan\s*\)",
    flags=re.IGNORECASE,
)

D3_SHEET_PATTERN = re.compile(
    r"^MDCR\s+ENROLL\s+D\s+3(?:_CPS_03EPD)?$",
    flags=re.IGNORECASE,
)

EXCLUDED_METADATA_SHEETS = {
    "table of contents",
}


def clean(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value)
        .replace("\r", " ")
        .replace("\n", " ")
        .split()
    )


def normalize_name(value: Any) -> str:
    return clean(value).casefold()


def numeric_value(value: Any) -> int | float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return value

    text = clean(value)

    if not text:
        return None

    text = text.replace(",", "")

    try:
        number = float(text)
    except ValueError:
        return None

    if number.is_integer():
        return int(number)

    return number


def find_zip(year: int) -> Path:
    matches = sorted(
        (ROOT / str(year)).glob("*.zip")
    )

    if len(matches) != 1:
        raise RuntimeError(
            f"CY{year}: expected exactly one ZIP; "
            f"found {len(matches)}: {matches}"
        )

    return matches[0]


def make_check(
    label: str,
    passed: bool,
    detail: str,
) -> dict[str, str]:
    return {
        "check": label,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
    }


def worksheet_rows(
    ws: openpyxl.worksheet.worksheet.Worksheet,
) -> list[list[Any]]:
    return [
        list(row)
        for row in ws.iter_rows(values_only=True)
    ]


def find_header_row(
    rows: list[list[Any]],
) -> tuple[int, list[str]] | None:

    for index, row in enumerate(rows):
        values = [clean(value) for value in row]

        if EXPECTED_AREA_HEADER in values:
            return index, values

    return None


def find_rds_column(
    headers: list[str],
) -> int | None:

    matches = [
        index
        for index, value in enumerate(headers)
        if RDS_HEADER_PATTERN.search(value)
    ]

    if len(matches) != 1:
        return None

    return matches[0]


def find_area_column(
    headers: list[str],
) -> int | None:

    matches = [
        index
        for index, value in enumerate(headers)
        if value == EXPECTED_AREA_HEADER
    ]

    if len(matches) != 1:
        return None

    return matches[0]


def title_text(
    rows: list[list[Any]],
    header_index: int,
) -> str:

    pieces: list[str] = []

    for row in rows[:header_index]:
        for value in row:
            text = clean(value)

            if text:
                pieces.append(text)

    return " ".join(pieces)


def classify_area(
    area: str,
) -> str:

    normalized = normalize_name(area)

    if not normalized:
        return "BLANK"

    if normalized == "all areas":
        return "CONTROL_ALL_AREAS"

    if normalized == "united states":
        return "CONTROL_UNITED_STATES"

    if normalized == "washington":
        return "TARGET_WASHINGTON"

    # We deliberately do not claim that every remaining
    # observation is a U.S. state. The source can include
    # territories and other residence categories.
    return "OTHER_RESIDENCE_AREA"


def main() -> None:
    print("=" * 100)
    print(
        "CMS MDCR ENROLL D 3 WASHINGTON "
        "RESIDENCE CERTIFICATION v0.3"
    )
    print("=" * 100)
    print()
    print("READ-ONLY")
    print("No database writes.")
    print("No RDS dollar allocation.")
    print("No county allocation.")
    print()

    OUTDIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    annual_rows: list[dict[str, str]] = []
    geography_rows: list[dict[str, str]] = []
    errors: list[str] = []

    years_source_resolved: set[int] = set()
    years_unique_d3: set[int] = set()
    years_area_title: set[int] = set()
    years_area_header: set[int] = set()
    years_rds_header: set[int] = set()
    years_wa_unique: set[int] = set()
    years_wa_numeric: set[int] = set()
    years_us_numeric: set[int] = set()
    years_all_numeric: set[int] = set()

    print("=" * 100)
    print("YEAR-BY-YEAR CERTIFICATION")
    print("=" * 100)

    for year in YEARS:
        print()
        print(f"CY{year}")
        print("-" * 100)

        try:
            zpath = find_zip(year)
            years_source_resolved.add(year)

            with zipfile.ZipFile(zpath) as zf:

                xlsx_members = [
                    info
                    for info in zf.infolist()
                    if (
                        not info.is_dir()
                        and Path(info.filename)
                        .suffix.lower()
                        in {".xlsx", ".xlsm"}
                    )
                ]

                candidates: list[
                    tuple[
                        str,
                        str,
                        list[list[Any]],
                    ]
                ] = []

                for info in xlsx_members:
                    data = zf.read(info.filename)

                    wb = openpyxl.load_workbook(
                        io.BytesIO(data),
                        read_only=True,
                        data_only=True,
                    )

                    try:
                        for ws in wb.worksheets:
                            sheet_norm = normalize_name(
                                ws.title
                            )

                            if (
                                sheet_norm
                                in EXCLUDED_METADATA_SHEETS
                            ):
                                continue

                            if not D3_SHEET_PATTERN.match(
                                clean(ws.title)
                            ):
                                continue

                            rows = worksheet_rows(ws)

                            candidates.append(
                                (
                                    info.filename,
                                    ws.title,
                                    rows,
                                )
                            )

                    finally:
                        wb.close()

                print(
                    f"D3 data-sheet candidates: "
                    f"{len(candidates)}"
                )

                if len(candidates) != 1:
                    errors.append(
                        f"CY{year}: expected exactly one "
                        f"D3 data worksheet; found "
                        f"{len(candidates)}"
                    )
                    continue

                years_unique_d3.add(year)

                member_name, sheet_name, rows = (
                    candidates[0]
                )

                print(
                    f"Workbook member: {member_name}"
                )
                print(
                    f"Worksheet:       {sheet_name}"
                )

                header_result = find_header_row(rows)

                if header_result is None:
                    errors.append(
                        f"CY{year}: Area of Residence "
                        f"header row not found"
                    )
                    continue

                header_index, headers = (
                    header_result
                )

                area_col = find_area_column(
                    headers
                )

                rds_col = find_rds_column(
                    headers
                )

                title = title_text(
                    rows,
                    header_index,
                )

                title_has_area = bool(
                    re.search(
                        r"\bby\s+Area\s+of\s+Residence\b",
                        title,
                        flags=re.IGNORECASE,
                    )
                )

                if title_has_area:
                    years_area_title.add(year)

                if area_col is not None:
                    years_area_header.add(year)

                if rds_col is not None:
                    years_rds_header.add(year)

                print(
                    f"Title says by Area of Residence: "
                    f"{'YES' if title_has_area else 'NO'}"
                )

                print(
                    f"Area column: "
                    f"{area_col if area_col is not None else 'NOT FOUND'}"
                )

                print(
                    f"RDS column:  "
                    f"{rds_col if rds_col is not None else 'NOT FOUND'}"
                )

                if (
                    area_col is None
                    or rds_col is None
                ):
                    errors.append(
                        f"CY{year}: required Area/RDS "
                        f"columns unresolved"
                    )
                    continue

                data_rows = rows[
                    header_index + 1:
                ]

                observations: list[
                    tuple[str, Any]
                ] = []

                for row in data_rows:
                    area = (
                        clean(row[area_col])
                        if area_col < len(row)
                        else ""
                    )

                    if not area:
                        continue

                    rds_raw = (
                        row[rds_col]
                        if rds_col < len(row)
                        else None
                    )

                    observations.append(
                        (
                            area,
                            rds_raw,
                        )
                    )

                    geography_rows.append(
                        {
                            "year": str(year),
                            "member_name": member_name,
                            "sheet_name": sheet_name,
                            "area_of_residence": area,
                            "area_classification": (
                                classify_area(area)
                            ),
                            "rds_raw": clean(
                                rds_raw
                            ),
                            "rds_numeric": (
                                ""
                                if numeric_value(
                                    rds_raw
                                ) is None
                                else str(
                                    numeric_value(
                                        rds_raw
                                    )
                                )
                            ),
                        }
                    )

                wa = [
                    value
                    for area, value
                    in observations
                    if normalize_name(area)
                    == "washington"
                ]

                us = [
                    value
                    for area, value
                    in observations
                    if normalize_name(area)
                    == "united states"
                ]

                all_areas = [
                    value
                    for area, value
                    in observations
                    if normalize_name(area)
                    == "all areas"
                ]

                if len(wa) == 1:
                    years_wa_unique.add(year)

                wa_value = (
                    numeric_value(wa[0])
                    if len(wa) == 1
                    else None
                )

                us_value = (
                    numeric_value(us[0])
                    if len(us) == 1
                    else None
                )

                all_value = (
                    numeric_value(all_areas[0])
                    if len(all_areas) == 1
                    else None
                )

                if wa_value is not None:
                    years_wa_numeric.add(year)

                if us_value is not None:
                    years_us_numeric.add(year)

                if all_value is not None:
                    years_all_numeric.add(year)

                print(
                    f"Washington rows: {len(wa)}"
                )
                print(
                    f"Washington RDS enrollment: "
                    f"{wa_value if wa_value is not None else 'UNRESOLVED'}"
                )
                print(
                    f"United States RDS enrollment: "
                    f"{us_value if us_value is not None else 'UNRESOLVED'}"
                )
                print(
                    f"All Areas RDS enrollment: "
                    f"{all_value if all_value is not None else 'UNRESOLVED'}"
                )

                annual_rows.append(
                    {
                        "year": str(year),
                        "zip_path": str(zpath),
                        "member_name": member_name,
                        "sheet_name": sheet_name,
                        "title_text": title,
                        "area_header": headers[
                            area_col
                        ],
                        "rds_header": headers[
                            rds_col
                        ],
                        "washington_rds_enrollment": (
                            ""
                            if wa_value is None
                            else str(wa_value)
                        ),
                        "united_states_rds_enrollment": (
                            ""
                            if us_value is None
                            else str(us_value)
                        ),
                        "all_areas_rds_enrollment": (
                            ""
                            if all_value is None
                            else str(all_value)
                        ),
                        "published_residence_area_count": (
                            str(
                                len(
                                    {
                                        normalize_name(
                                            area
                                        )
                                        for area, _
                                        in observations
                                    }
                                )
                            )
                        ),
                    }
                )

        except Exception as exc:
            message = (
                f"CY{year}: {exc!r}"
            )
            errors.append(message)
            print(
                f"ERROR: {exc!r}"
            )

    # --------------------------------------------------
    # Geography vocabulary tests
    # --------------------------------------------------

    all_geographies = {
        normalize_name(
            row["area_of_residence"]
        )
        for row in geography_rows
    }

    county_like = sorted(
        {
            row["area_of_residence"]
            for row in geography_rows
            if re.search(
                r"\bcounty\b",
                row["area_of_residence"],
                flags=re.IGNORECASE,
            )
        }
    )

    washington_named = sorted(
        {
            row["area_of_residence"]
            for row in geography_rows
            if normalize_name(
                row["area_of_residence"]
            )
            == "washington"
        }
    )

    # A county-level source would normally expose
    # hundreds or thousands of distinct geographic
    # labels nationally. This table instead presents
    # a compact state/territory/other-area vocabulary.
    distinct_area_count = len(
        all_geographies
    )

    compact_geography = (
        distinct_area_count < 100
    )

    no_county_labels = (
        len(county_like) == 0
    )

    # --------------------------------------------------
    # Checks
    # --------------------------------------------------

    checks = [
        make_check(
            "CY2015-CY2023 source ZIPs resolved",
            years_source_resolved
            == set(YEARS),
            (
                f"{len(years_source_resolved)}"
                "/9 years"
            ),
        ),
        make_check(
            "Exactly one D3 data worksheet per year",
            years_unique_d3
            == set(YEARS),
            (
                f"{len(years_unique_d3)}"
                "/9 years"
            ),
        ),
        make_check(
            "D3 title says by Area of Residence",
            years_area_title
            == set(YEARS),
            (
                f"{len(years_area_title)}"
                "/9 years"
            ),
        ),
        make_check(
            "Area of Residence column present",
            years_area_header
            == set(YEARS),
            (
                f"{len(years_area_header)}"
                "/9 years"
            ),
        ),
        make_check(
            "RDS No Part D Plan column present",
            years_rds_header
            == set(YEARS),
            (
                f"{len(years_rds_header)}"
                "/9 years"
            ),
        ),
        make_check(
            "Exactly one Washington residence row per year",
            years_wa_unique
            == set(YEARS),
            (
                f"{len(years_wa_unique)}"
                "/9 years"
            ),
        ),
        make_check(
            "Washington RDS enrollment numeric every year",
            years_wa_numeric
            == set(YEARS),
            (
                f"{len(years_wa_numeric)}"
                "/9 years"
            ),
        ),
        make_check(
            "United States RDS control numeric every year",
            years_us_numeric
            == set(YEARS),
            (
                f"{len(years_us_numeric)}"
                "/9 years"
            ),
        ),
        make_check(
            "All Areas RDS control numeric every year",
            years_all_numeric
            == set(YEARS),
            (
                f"{len(years_all_numeric)}"
                "/9 years"
            ),
        ),
        make_check(
            "Published geography vocabulary is compact",
            compact_geography,
            (
                f"{distinct_area_count} "
                f"distinct residence labels"
            ),
        ),
        make_check(
            "No county-labelled residence observations",
            no_county_labels,
            (
                "0 county-labelled areas"
                if no_county_labels
                else (
                    f"{len(county_like)} "
                    f"county-labelled areas"
                )
            ),
        ),
        make_check(
            "Washington appears as residence geography",
            washington_named
            == ["Washington"],
            (
                "; ".join(washington_named)
                if washington_named
                else "Washington not found"
            ),
        ),
        make_check(
            "No certification errors",
            len(errors) == 0,
            (
                "0 errors"
                if not errors
                else "; ".join(errors)
            ),
        ),
    ]

    # --------------------------------------------------
    # Evidence outputs
    # --------------------------------------------------

    annual_fields = [
        "year",
        "zip_path",
        "member_name",
        "sheet_name",
        "title_text",
        "area_header",
        "rds_header",
        "washington_rds_enrollment",
        "united_states_rds_enrollment",
        "all_areas_rds_enrollment",
        "published_residence_area_count",
    ]

    with ANNUAL_OUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=annual_fields,
        )
        writer.writeheader()
        writer.writerows(
            sorted(
                annual_rows,
                key=lambda row: int(
                    row["year"]
                ),
            )
        )

    geography_fields = [
        "year",
        "member_name",
        "sheet_name",
        "area_of_residence",
        "area_classification",
        "rds_raw",
        "rds_numeric",
    ]

    with GEOGRAPHY_OUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=geography_fields,
        )
        writer.writeheader()
        writer.writerows(
            geography_rows
        )

    with CHECKS_OUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "check",
                "status",
                "detail",
            ],
        )
        writer.writeheader()
        writer.writerows(checks)

    # --------------------------------------------------
    # Console summary
    # --------------------------------------------------

    print()
    print("=" * 100)
    print("WASHINGTON RDS ENROLLMENT SERIES")
    print("=" * 100)

    for row in sorted(
        annual_rows,
        key=lambda x: int(x["year"]),
    ):
        print(
            f"CY{row['year']} | "
            f"WA={row['washington_rds_enrollment']} | "
            f"US={row['united_states_rds_enrollment']} | "
            f"All Areas={row['all_areas_rds_enrollment']}"
        )

    print()
    print("=" * 100)
    print("GEOGRAPHY PROFILE")
    print("=" * 100)

    print(
        f"Distinct residence labels: "
        f"{distinct_area_count}"
    )
    print(
        f"County-labelled observations: "
        f"{len(county_like)}"
    )
    print(
        "Washington geography: "
        + (
            "PRESENT"
            if washington_named
            else "ABSENT"
        )
    )

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

    overall = all(
        row["status"] == "PASS"
        for row in checks
    )

    # --------------------------------------------------
    # Report
    # --------------------------------------------------

    report_lines = [
        (
            "CMS MDCR ENROLL D 3 WASHINGTON "
            "RESIDENCE CERTIFICATION v0.3"
        ),
        "=" * 78,
        "",
        "Scope: CY2015-CY2023",
        "",
        "CERTIFIED SEMANTIC BOUNDARY",
        "-" * 78,
        (
            "MDCR ENROLL D 3 publishes Retiree Drug "
            "Subsidy (No Part D Plan) enrollment by "
            "Area of Residence."
        ),
        (
            "Washington is directly observed as a "
            "published residence geography."
        ),
        (
            "The source therefore supports a "
            "Washington-resident RDS enrollment "
            "series for CY2015-CY2023."
        ),
        "",
        "NON-CERTIFIED INFERENCES",
        "-" * 78,
        (
            "This source does not establish Washington "
            "RDS payment dollars."
        ),
        (
            "RDS beneficiary counts are not treated as "
            "payment-dollar allocation weights."
        ),
        (
            "This source does not establish county-level "
            "Washington RDS enrollment or payments."
        ),
        "",
        "CHECKS",
        "-" * 78,
    ]

    for row in checks:
        report_lines.append(
            f"{row['status']} | "
            f"{row['check']} | "
            f"{row['detail']}"
        )

    if errors:
        report_lines.extend(
            [
                "",
                "ERRORS",
                "-" * 78,
                *errors,
            ]
        )

    REPORT_OUT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 100)
    print(
        "OVERALL WASHINGTON RESIDENCE "
        "CERTIFICATION: "
        + (
            "PASS"
            if overall
            else "FAIL"
        )
    )
    print("=" * 100)

    print()
    print("Evidence written:")
    print(f"  {ANNUAL_OUT}")
    print(f"  {GEOGRAPHY_OUT}")
    print(f"  {CHECKS_OUT}")
    print(f"  {REPORT_OUT}")

    print()
    print("Boundary:")
    print(
        "  Washington RDS enrollment: "
        "candidate for certification."
    )
    print(
        "  Washington RDS dollars: "
        "NOT established."
    )
    print(
        "  Washington county RDS allocation: "
        "NOT established."
    )

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
