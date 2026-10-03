from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path


ROOT = Path(
    "data/raw/cms/medicare_rds/"
    "program_statistics_partd_enrollment"
)

OUTDIR = ROOT / "validation" / "mdcr_enroll_d3_profile_v0_1"

MEMBER_OUT = OUTDIR / "cms_mdcr_enroll_d3_member_inventory_v0_1.csv"
PREVIEW_OUT = OUTDIR / "cms_mdcr_enroll_d3_content_preview_v0_1.csv"
CHECKS_OUT = OUTDIR / "cms_mdcr_enroll_d3_profile_checks_v0_1.csv"
REPORT_OUT = OUTDIR / "cms_mdcr_enroll_d3_profile_report_v0_1.txt"

YEARS = list(range(2015, 2024))

TEXT_EXTENSIONS = {
    ".csv",
    ".txt",
    ".tsv",
}


def normalize(value: object) -> str:
    if value is None:
        return ""

    return " ".join(str(value).strip().split())


def decode_bytes(data: bytes) -> tuple[str, str]:
    """
    Decode text conservatively.

    Returns:
        decoded_text, encoding_used
    """
    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    ]

    for encoding in encodings:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    return "", "UNDECODED"


def sniff_delimiter(text: str) -> str:
    sample = text[:10000]

    try:
        dialect = csv.Sniffer().sniff(
            sample,
            delimiters=",\t|;",
        )
        return dialect.delimiter
    except csv.Error:
        if "\t" in sample:
            return "\t"
        return ","


def looks_like_d3(name: str, text: str = "") -> bool:
    blob = f"{name} {text[:10000]}".lower()

    patterns = [
        r"mdcr\s*enroll\s*d\s*3",
        r"enroll[_\s-]*d[_\s-]*3",
        r"03epd",
        r"retiree\s+drug\s+subsid",
        r"area\s+of\s+residence",
    ]

    return any(
        re.search(pattern, blob, flags=re.IGNORECASE)
        for pattern in patterns
    )


def find_year_zip(year: int) -> Path:
    year_dir = ROOT / str(year)

    matches = sorted(year_dir.glob("*.zip"))

    if len(matches) != 1:
        raise RuntimeError(
            f"CY{year}: expected exactly one ZIP, found "
            f"{len(matches)}: {matches}"
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


def main() -> None:
    print("=" * 100)
    print("CMS MDCR ENROLL D 3 STRUCTURAL PROFILER v0.1")
    print("=" * 100)
    print()
    print("READ-ONLY")
    print("No database writes.")
    print("No RDS dollar allocation.")
    print("No interpretation of geographic incidence.")
    print()

    OUTDIR.mkdir(parents=True, exist_ok=True)

    member_rows: list[dict[str, str]] = []
    preview_rows: list[dict[str, str]] = []
    errors: list[str] = []

    print("=" * 100)
    print("ZIP / MEMBER INVENTORY")
    print("=" * 100)

    for year in YEARS:
        try:
            zpath = find_year_zip(year)
        except Exception as exc:
            errors.append(str(exc))
            print(f"{year}: ERROR | {exc}")
            continue

        print()
        print(f"CY{year}")
        print(f"ZIP: {zpath}")

        try:
            with zipfile.ZipFile(zpath) as zf:
                members = [
                    info
                    for info in zf.infolist()
                    if not info.is_dir()
                ]

                print(f"Members: {len(members)}")

                for info in members:
                    suffix = Path(info.filename).suffix.lower()

                    data = zf.read(info.filename)

                    decoded = ""
                    encoding = ""
                    delimiter = ""
                    row_count = ""
                    column_count = ""
                    header = ""
                    d3_candidate = False

                    if suffix in TEXT_EXTENSIONS:
                        decoded, encoding = decode_bytes(data)

                        if decoded:
                            delimiter = sniff_delimiter(decoded)

                            reader = csv.reader(
                                io.StringIO(decoded),
                                delimiter=delimiter,
                            )

                            rows = list(reader)

                            row_count = str(len(rows))

                            if rows:
                                column_count = str(
                                    max(len(row) for row in rows)
                                )

                                header = " | ".join(
                                    normalize(x)
                                    for x in rows[0]
                                )

                            d3_candidate = looks_like_d3(
                                info.filename,
                                decoded,
                            )

                            # Preserve only a bounded preview.
                            for row_number, row in enumerate(
                                rows[:25],
                                start=1,
                            ):
                                preview_rows.append(
                                    {
                                        "year": str(year),
                                        "zip_path": str(zpath),
                                        "member_name": info.filename,
                                        "row_number": str(row_number),
                                        "values": " | ".join(
                                            normalize(x)
                                            for x in row
                                        ),
                                        "d3_candidate": (
                                            "YES"
                                            if d3_candidate
                                            else "NO"
                                        ),
                                    }
                                )

                    else:
                        d3_candidate = looks_like_d3(
                            info.filename
                        )

                    member_rows.append(
                        {
                            "year": str(year),
                            "zip_path": str(zpath),
                            "member_name": info.filename,
                            "extension": suffix,
                            "compressed_bytes": str(info.compress_size),
                            "uncompressed_bytes": str(info.file_size),
                            "encoding": encoding,
                            "delimiter": (
                                repr(delimiter)
                                if delimiter
                                else ""
                            ),
                            "row_count": row_count,
                            "column_count": column_count,
                            "header": header,
                            "d3_candidate": (
                                "YES"
                                if d3_candidate
                                else "NO"
                            ),
                        }
                    )

                    print(
                        f"  {info.filename} | "
                        f"{info.file_size:,} bytes | "
                        f"D3={'YES' if d3_candidate else 'NO'}"
                    )

                    if header:
                        print(f"    Header: {header}")

        except Exception as exc:
            message = f"CY{year}: ZIP profiling error: {exc!r}"
            errors.append(message)
            print(f"  ERROR: {exc!r}")

    # --------------------------------------------------------------
    # Write inventories
    # --------------------------------------------------------------

    member_fields = [
        "year",
        "zip_path",
        "member_name",
        "extension",
        "compressed_bytes",
        "uncompressed_bytes",
        "encoding",
        "delimiter",
        "row_count",
        "column_count",
        "header",
        "d3_candidate",
    ]

    with MEMBER_OUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=member_fields,
        )
        writer.writeheader()
        writer.writerows(member_rows)

    preview_fields = [
        "year",
        "zip_path",
        "member_name",
        "row_number",
        "values",
        "d3_candidate",
    ]

    with PREVIEW_OUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=preview_fields,
        )
        writer.writeheader()
        writer.writerows(preview_rows)

    # --------------------------------------------------------------
    # Structural checks
    # --------------------------------------------------------------

    years_profiled = {
        int(row["year"])
        for row in member_rows
    }

    candidate_rows = [
        row
        for row in member_rows
        if row["d3_candidate"] == "YES"
    ]

    candidate_years = {
        int(row["year"])
        for row in candidate_rows
    }

    text_members = [
        row
        for row in member_rows
        if row["extension"] in TEXT_EXTENSIONS
    ]

    parsed_text_members = [
        row
        for row in text_members
        if row["row_count"]
    ]

    checks = [
        make_check(
            "CY2015-CY2023 source ZIPs profiled",
            years_profiled == set(YEARS),
            f"{len(years_profiled)}/9 years",
        ),
        make_check(
            "All text members parsed",
            len(parsed_text_members) == len(text_members),
            (
                f"{len(parsed_text_members)}/"
                f"{len(text_members)} text members"
            ),
        ),
        make_check(
            "At least one D3 candidate identified",
            len(candidate_rows) > 0,
            (
                f"{len(candidate_rows)} candidate members "
                f"across {len(candidate_years)} years"
            ),
        ),
        make_check(
            "No structural profiling errors",
            len(errors) == 0,
            (
                "0 errors"
                if not errors
                else "; ".join(errors)
            ),
        ),
    ]

    with CHECKS_OUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["check", "status", "detail"],
        )
        writer.writeheader()
        writer.writerows(checks)

    # --------------------------------------------------------------
    # Console candidate detail
    # --------------------------------------------------------------

    print()
    print("=" * 100)
    print("D3 CANDIDATE MEMBERS")
    print("=" * 100)

    if not candidate_rows:
        print("NONE")
    else:
        for row in candidate_rows:
            print(
                f"CY{row['year']} | "
                f"{row['member_name']} | "
                f"rows={row['row_count'] or '?'} | "
                f"cols={row['column_count'] or '?'}"
            )

            if row["header"]:
                print(f"  Header: {row['header']}")

    print()
    print("=" * 100)
    print("CONTENT PREVIEW — D3 CANDIDATES")
    print("=" * 100)

    candidate_preview = [
        row
        for row in preview_rows
        if row["d3_candidate"] == "YES"
    ]

    if not candidate_preview:
        print("No parsed D3 candidate preview rows.")
    else:
        current_key = None

        for row in candidate_preview:
            key = (
                row["year"],
                row["member_name"],
            )

            if key != current_key:
                print()
                print(
                    f"CY{row['year']} | "
                    f"{row['member_name']}"
                )
                print("-" * 100)
                current_key = key

            print(
                f"{int(row['row_number']):3d} | "
                f"{row['values']}"
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

    # --------------------------------------------------------------
    # Report
    # --------------------------------------------------------------

    report_lines = [
        "CMS MDCR ENROLL D 3 STRUCTURAL PROFILER v0.1",
        "=" * 78,
        "",
        "Scope: CY2015-CY2023",
        f"ZIP/member observations: {len(member_rows)}",
        f"Parsed preview observations: {len(preview_rows)}",
        f"D3 candidate members: {len(candidate_rows)}",
        f"D3 candidate years: {len(candidate_years)}",
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

    report_lines.extend(
        [
            "",
            "BOUNDARY",
            "-" * 78,
            (
                "D3 candidate identification is structural only. "
                "A filename or textual match does not establish "
                "the geographic semantics of Area of Residence."
            ),
            (
                "No RDS enrollment count has been used for "
                "Washington allocation."
            ),
            (
                "No RDS payment dollar has been assigned to "
                "Washington or any Washington county."
            ),
        ]
    )

    REPORT_OUT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 100)
    print(
        "OVERALL STRUCTURAL PROFILE: "
        + ("PASS" if overall else "FAIL")
    )
    print("=" * 100)

    print()
    print("Evidence written:")
    print(f"  {MEMBER_OUT}")
    print(f"  {PREVIEW_OUT}")
    print(f"  {CHECKS_OUT}")
    print(f"  {REPORT_OUT}")

    print()
    print("No geographic interpretation has been made.")

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
