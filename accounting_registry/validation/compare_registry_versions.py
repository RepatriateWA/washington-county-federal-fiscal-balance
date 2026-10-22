"""Compare two WCFFBP accounting registry versions without modifying either."""

import argparse
import csv
import sys
from pathlib import Path

TABLES = {
    "source_family_registry.csv": ("family_id",),
    "annual_accounting_matrix.csv": ("family_id", "source_year"),
    "canonical_annual_ledger.csv": ("family_id", "fiscal_year"),
    "evidence_crosswalk.csv": ("family_ids", "evidence_role", "repository_path"),
}

PROTECTED_FIELDS = {
    "annual_accounting_matrix.csv": {
        "observed_amount_usd",
        "evidence_path",
    },
    "canonical_annual_ledger.csv": {
        "candidate_observed_amount_usd",
        "source_reference",
    },
    "source_family_registry.csv": {
        "primary_readiness_reference",
    },
    "evidence_crosswalk.csv": {
        "repository_path",
    },
}

failures = []
reviews = []
information = []


def report(level, message):
    print(f"{level}: {message}")

    if level == "FAIL":
        failures.append(message)
    elif level == "REVIEW":
        reviews.append(message)
    else:
        information.append(message)


def load_table(directory, filename, key_fields):
    path = directory / filename

    if not path.is_file():
        raise ValueError(f"Required file missing: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)

        if not reader.fieldnames:
            raise ValueError(f"Missing CSV header: {path}")

        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"Duplicate CSV headers: {path}")

        missing = set(key_fields) - set(reader.fieldnames)

        if missing:
            raise ValueError(
                f"Missing key columns in {path}: {sorted(missing)}"
            )

        rows = {}

        for line_number, row in enumerate(reader, start=2):
            key = tuple(row[field] for field in key_fields)

            if key in rows:
                raise ValueError(
                    f"Duplicate key in {path}, line {line_number}: {key}"
                )

            rows[key] = row

    return rows, set(reader.fieldnames)


def compare_table(baseline_dir, candidate_dir, filename, key_fields):
    old, old_columns = load_table(
        baseline_dir, filename, key_fields
    )
    new, new_columns = load_table(
        candidate_dir, filename, key_fields
    )

    print()
    print("=" * 78)
    print(f"TABLE: {filename}")
    print(f"BASELINE RECORDS: {len(old)}")
    print(f"CANDIDATE RECORDS: {len(new)}")

    for column in sorted(old_columns - new_columns):
        report("FAIL", f"{filename}: column removed: {column}")

    for column in sorted(new_columns - old_columns):
        report("INFO", f"{filename}: column added: {column}")

    for key in sorted(old.keys() - new.keys()):
        report("FAIL", f"{filename}: record removed: {key}")

    for key in sorted(new.keys() - old.keys()):
        report("INFO", f"{filename}: record added: {key}")

    for key in sorted(old.keys() & new.keys()):
        old_row = old[key]
        new_row = new[key]

        for field in sorted(old_columns & new_columns):
            before = (old_row.get(field) or "").strip()
            after = (new_row.get(field) or "").strip()

            if before == after:
                continue

            label = f"{filename} {key} {field}"

            if (
                field in PROTECTED_FIELDS.get(filename, set())
                and before
                and not after
            ):
                report(
                    "FAIL",
                    f"{label}: populated value removed; "
                    f"before={before!r}",
                )
            elif not before and after:
                report(
                    "INFO",
                    f"{label}: newly populated; after={after!r}",
                )
            else:
                report(
                    "REVIEW",
                    f"{label}: {before!r} -> {after!r}",
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    args = parser.parse_args()

    print("WCFFBP REGISTRY VERSION COMPARATOR v0.2")
    print("READ ONLY - NO REGISTRY OR DATABASE WRITES")
    print(f"BASELINE: {args.baseline}")
    print(f"CANDIDATE: {args.candidate}")

    try:
        if not args.baseline.is_dir():
            raise ValueError("Baseline directory does not exist")

        if not args.candidate.is_dir():
            raise ValueError("Candidate directory does not exist")

        for filename, key_fields in TABLES.items():
            compare_table(
                args.baseline,
                args.candidate,
                filename,
                key_fields,
            )

    except (OSError, ValueError, csv.Error) as exc:
        report("FAIL", str(exc))

    print()
    print("=" * 78)
    print(f"FAILURES: {len(failures)}")
    print(f"REVIEWS: {len(reviews)}")
    print(f"INFORMATIONAL CHANGES: {len(information)}")

    if failures:
        print("RESULT: FAIL")
        return 1

    if reviews:
        print("RESULT: REVIEW REQUIRED")
        return 2

    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
