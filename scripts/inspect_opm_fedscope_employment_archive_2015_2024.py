from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RAW_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "opm"
    / "fedscope"
    / "employment"
)

OUTPUT_DIR = (
    ROOT
    / "data"
    / "interim"
    / "opm"
)

YEARS = range(2015, 2025)

REQUIRED_FACT_FIELDS = {
    "LOC",
    "WORKSTAT",
    "WORKSCH",
    "EMPLOYMENT",
    "SALARY",
}


def find_zip(year: int) -> Path:
    snapshot = f"{year}-09"
    year_dir = RAW_ROOT / snapshot

    matches = sorted(
        year_dir.glob(
            f"opm_fedscope_employment_{year}09_"
            "raw_data_retrieved_*.zip"
        )
    )

    if len(matches) != 1:
        raise RuntimeError(
            f"{snapshot}: expected exactly one raw ZIP; "
            f"found {len(matches)}"
        )

    return matches[0]


def normalize_name(name: str) -> str:
    return Path(name).name.upper()


def find_member(
    names: list[str],
    candidates: list[str],
) -> str | None:

    by_basename = {
        normalize_name(name): name
        for name in names
    }

    for candidate in candidates:
        candidate_upper = candidate.upper()

        if candidate_upper in by_basename:
            return by_basename[candidate_upper]

    return None


def find_fact_member(names: list[str]) -> str:

    candidates = []

    for name in names:
        base = normalize_name(name)

        if (
            base.startswith("FACTDATA")
            and base.endswith((".TXT", ".CSV"))
        ):
            candidates.append(name)

    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one FACTDATA text/CSV member; "
            f"found {len(candidates)}: {candidates}"
        )

    return candidates[0]


def open_text(
    zf: zipfile.ZipFile,
    member: str,
):
    return io.TextIOWrapper(
        zf.open(member, "r"),
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    )


def read_header(
    zf: zipfile.ZipFile,
    member: str,
) -> list[str]:

    with open_text(zf, member) as f:
        reader = csv.reader(f)
        row = next(reader)

    return [
        value.strip().upper()
        for value in row
    ]


def count_data_rows(
    zf: zipfile.ZipFile,
    member: str,
) -> int:

    count = 0

    with zf.open(member, "r") as f:
        # Skip header.
        next(f, None)

        for _ in f:
            count += 1

    return count


def inspect_lookup(
    zf: zipfile.ZipFile,
    member: str | None,
) -> tuple[list[str], list[dict[str, str]]]:

    if member is None:
        return [], []

    with open_text(zf, member) as f:
        reader = csv.DictReader(f)

        fields = [
            (x or "").strip().upper()
            for x in (reader.fieldnames or [])
        ]

        rows = []

        for raw in reader:
            row = {
                (k or "").strip().upper():
                    (v or "").strip()
                for k, v in raw.items()
            }
            rows.append(row)

    return fields, rows


def first_present(
    row: dict[str, str],
    names: list[str],
) -> str:

    for name in names:
        value = row.get(name, "").strip()

        if value:
            return value

    return ""


def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 118)
    print(
        "OPM FEDSCOPE SEPTEMBER EMPLOYMENT ARCHIVE "
        "STRUCTURAL INSPECTION 2015-2024"
    )
    print("=" * 118)

    results = []

    reference_header = None

    for year in YEARS:

        snapshot = f"{year}-09"
        source = find_zip(year)

        print()
        print("-" * 118)
        print(snapshot)
        print(f"ZIP: {source}")
        print("-" * 118)

        with zipfile.ZipFile(source, "r") as zf:

            bad = zf.testzip()

            if bad is not None:
                raise RuntimeError(
                    f"{snapshot}: corrupt ZIP member: {bad}"
                )

            names = [
                x.filename
                for x in zf.infolist()
                if not x.is_dir()
            ]

            print(f"Archive members: {len(names)}")

            for name in names:
                info = zf.getinfo(name)

                print(
                    f"  {name} "
                    f"({info.file_size:,} bytes)"
                )

            fact_member = find_fact_member(names)

            wkstat_member = find_member(
                names,
                ["DTwkstat.txt", "DTwkstat.csv"],
            )

            wrksch_member = find_member(
                names,
                ["DTwrksch.txt", "DTwrksch.csv"],
            )

            loc_member = find_member(
                names,
                ["DTloc.txt", "DTloc.csv"],
            )

            agy_member = find_member(
                names,
                ["DTagy.txt", "DTagy.csv"],
            )

            print()
            print(f"FACT:     {fact_member}")
            print(f"WORKSTAT: {wkstat_member}")
            print(f"WORKSCH:  {wrksch_member}")
            print(f"LOCATION: {loc_member}")
            print(f"AGENCY:   {agy_member}")

            missing_lookups = [
                label
                for label, member in (
                    ("WORKSTAT", wkstat_member),
                    ("WORKSCH", wrksch_member),
                    ("LOCATION", loc_member),
                    ("AGENCY", agy_member),
                )
                if member is None
            ]

            header = read_header(
                zf,
                fact_member,
            )

            missing_fields = sorted(
                REQUIRED_FACT_FIELDS
                - set(header)
            )

            if missing_fields:
                raise RuntimeError(
                    f"{snapshot}: FACTDATA missing required "
                    f"fields: {missing_fields}"
                )

            print()
            print(
                f"FACT columns ({len(header)}): "
                + ",".join(header)
            )

            if reference_header is None:
                reference_header = header

            added_vs_2015 = [
                x
                for x in header
                if x not in reference_header
            ]

            removed_vs_2015 = [
                x
                for x in reference_header
                if x not in header
            ]

            fact_rows = count_data_rows(
                zf,
                fact_member,
            )

            print(
                f"FACT data rows: {fact_rows:,}"
            )

            #
            # WORKSTAT
            #
            wkstat_fields, wkstat_rows = inspect_lookup(
                zf,
                wkstat_member,
            )

            workstat_1_label = ""

            for row in wkstat_rows:

                code = first_present(
                    row,
                    [
                        "WORKSTAT",
                        "WKSTAT",
                        "CODE",
                    ],
                )

                if code == "1":

                    workstat_1_label = first_present(
                        row,
                        [
                            "WORKSTATT",
                            "WKSTATT",
                            "DESCRIPTION",
                            "DESC",
                            "TEXT",
                        ],
                    )

                    # If the label field name changed,
                    # fall back to any non-code value.
                    if not workstat_1_label:
                        for key, value in row.items():
                            if (
                                key not in {
                                    "WORKSTAT",
                                    "WKSTAT",
                                    "CODE",
                                }
                                and value
                            ):
                                workstat_1_label = value
                                break

                    break

            print(
                "WORKSTAT=1: "
                f"{workstat_1_label or 'NOT RESOLVED'}"
            )

            #
            # LOCATION
            #
            loc_fields, loc_rows = inspect_lookup(
                zf,
                loc_member,
            )

            wa_label = ""
            location_types = Counter()

            for row in loc_rows:

                loc_code = first_present(
                    row,
                    [
                        "LOC",
                        "LOCATION",
                        "CODE",
                    ],
                )

                loc_text = first_present(
                    row,
                    [
                        "LOCT",
                        "LOCATIONT",
                        "DESCRIPTION",
                        "DESC",
                        "TEXT",
                    ],
                )

                loc_type = first_present(
                    row,
                    [
                        "LOCTYPT",
                        "LOCATIONTYPE",
                        "TYPE",
                    ],
                )

                if loc_type:
                    location_types[loc_type] += 1

                if loc_code == "53":
                    wa_label = loc_text

            print(
                f"Location rows: {len(loc_rows):,}"
            )

            print(
                f"LOC=53: "
                f"{wa_label or 'NOT RESOLVED'}"
            )

            print(
                "Location types: "
                + (
                    "; ".join(
                        f"{k}={v}"
                        for k, v in sorted(
                            location_types.items()
                        )
                    )
                    if location_types
                    else "NOT RESOLVED"
                )
            )

            schema_same = (
                header == reference_header
            )

            result = {
                "snapshot": snapshot,
                "year": year,
                "source_zip":
                    str(source.relative_to(ROOT)),
                "archive_member_count":
                    len(names),
                "fact_member":
                    fact_member,
                "fact_column_count":
                    len(header),
                "fact_header":
                    "|".join(header),
                "fact_rows":
                    fact_rows,
                "required_fields_present":
                    not missing_fields,
                "missing_required_fields":
                    "|".join(missing_fields),
                "workstat_member":
                    wkstat_member or "",
                "workstat_1_label":
                    workstat_1_label,
                "wrksch_member":
                    wrksch_member or "",
                "location_member":
                    loc_member or "",
                "location_rows":
                    len(loc_rows),
                "wa_loc_53_label":
                    wa_label,
                "location_types":
                    json.dumps(
                        dict(
                            sorted(
                                location_types.items()
                            )
                        ),
                        sort_keys=True,
                    ),
                "agency_member":
                    agy_member or "",
                "missing_lookup_files":
                    "|".join(missing_lookups),
                "schema_identical_to_2015":
                    schema_same,
                "columns_added_vs_2015":
                    "|".join(added_vs_2015),
                "columns_removed_vs_2015":
                    "|".join(removed_vs_2015),
            }

            results.append(result)

    output_csv = (
        OUTPUT_DIR
        / "opm_fedscope_employment_archive_"
          "structure_2015_2024.csv"
    )

    with output_csv.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(results[0].keys()),
        )

        writer.writeheader()
        writer.writerows(results)

    print()
    print("=" * 118)
    print("TEN-YEAR SUMMARY")
    print("=" * 118)

    print(
        f"{'YEAR':<6}"
        f"{'MEMBERS':>9}"
        f"{'COLS':>7}"
        f"{'FACT ROWS':>14}  "
        f"{'WORKSTAT=1':<38}"
        f"{'WA LOC':<20}"
        f"{'LOC ROWS':>10}"
    )

    print("-" * 118)

    for row in results:

        print(
            f"{row['year']:<6}"
            f"{row['archive_member_count']:>9}"
            f"{row['fact_column_count']:>7}"
            f"{row['fact_rows']:>14,}  "
            f"{row['workstat_1_label'][:36]:<38}"
            f"{row['wa_loc_53_label'][:18]:<20}"
            f"{row['location_rows']:>10,}"
        )

    print()
    print("SCHEMA DIFFERENCES VS 2015")
    print("-" * 118)

    for row in results:

        if row["schema_identical_to_2015"]:
            print(
                f"{row['year']}: IDENTICAL"
            )
        else:
            print(
                f"{row['year']}: DIFFERENT"
            )
            print(
                "  added:   "
                f"{row['columns_added_vs_2015'] or '(none)'}"
            )
            print(
                "  removed: "
                f"{row['columns_removed_vs_2015'] or '(none)'}"
            )

    #
    # Validation gates.
    #
    failures = []

    for row in results:

        if not row["required_fields_present"]:
            failures.append(
                f"{row['year']}: missing required FACT fields"
            )

        if row["missing_lookup_files"]:
            failures.append(
                f"{row['year']}: missing lookup files "
                f"{row['missing_lookup_files']}"
            )

        if not row["workstat_1_label"]:
            failures.append(
                f"{row['year']}: WORKSTAT=1 unresolved"
            )

        if not row["wa_loc_53_label"]:
            failures.append(
                f"{row['year']}: LOC=53 unresolved"
            )

        if row["fact_rows"] <= 0:
            failures.append(
                f"{row['year']}: no FACT rows"
            )

    print()
    print("=" * 118)

    if failures:

        print("STRUCTURAL VALIDATION: FAIL")

        for failure in failures:
            print(f"  - {failure}")

        print("=" * 118)

        raise RuntimeError(
            "OPM structural validation failed."
        )

    print("STRUCTURAL VALIDATION: PASS")
    print(
        "All ten archives contain the required "
        "civilian-wage allocation fields and lookups."
    )
    print(f"Evidence CSV: {output_csv}")
    print("=" * 118)


if __name__ == "__main__":
    main()