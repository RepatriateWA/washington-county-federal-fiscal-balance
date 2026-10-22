"""ETL-226C5G: read-only accounting registry baseline validation."""

import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "accounting_registry" / "v0_3_0_working"

BASELINE = {
    "source_family_registry.csv": (
        23,
        "2B5DC11EC6864B9F769DB5E9E5002533C71E44236C946DCF14DF5710A5BAC3C2",
    ),
    "annual_accounting_matrix.csv": (
        161,
        "CE767BC3E944B987D04F03E763FC8A63E042A2A25831BD3458527C85D805871A",
    ),
    "canonical_annual_ledger.csv": (
        147,
        "4CE062B76A769C561C2BE5733D18702EE8F6A26C0F2B79C8229AD1143F2426CE",
    ),
    "evidence_crosswalk.csv": (
        17,
        "33C487BBCEE96B50F0C0E9FAC22DEE396D812FDF7343F51C337E7BD0AB0782E5",
    ),
}

YEARS = {str(year) for year in range(2018, 2025)}
CANDIDATE_ROLE = "CANDIDATE_PAYMENT_STREAM"
NONADDITIVE_ROLES = {
    "REFERENCE_CONTROL",
    "REPORTING_AGGREGATE_NON_ADDITIVE",
}

failures = []
reviews = []


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"{status}: {description}")
    if not condition:
        failures.append(description)


def read_csv(name):
    path = REGISTRY / name
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        check(
            bool(reader.fieldnames)
            and len(reader.fieldnames) == len(set(reader.fieldnames)),
            f"{name}: valid unique column headers",
        )
        return list(reader)


def keys(rows, year_field):
    return [(row["family_id"], row[year_field]) for row in rows]


def unique_keys(values, description):
    duplicates = [
        (key, count)
        for key, count in Counter(values).items()
        if count > 1
    ]
    check(not duplicates, description)
    for key, count in duplicates:
        print(f"  DUPLICATE: {key} count={count}")


def main():
    print("ETL-226C5G REGISTRY BASELINE VALIDATOR v0.1")
    print("READ ONLY - NO REGISTRY OR DATABASE WRITES")
    print("=" * 72)

    tables = {}

    for name, (expected_count, expected_hash) in BASELINE.items():
        path = REGISTRY / name

        if not path.is_file():
            check(False, f"Required file exists: {name}")
            return

        data = path.read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest().upper()
        rows = read_csv(name)
        tables[name] = rows

        print(f"\nFILE: {name}")
        print(f"ROWS: {len(rows)}")
        print(f"SHA256: {actual_hash}")

        if actual_hash != expected_hash:
            reviews.append(f"Content changed from baseline: {name}")
            print("REVIEW: Fingerprint differs from baseline")
        else:
            print("PASS: Fingerprint matches baseline")

        if len(rows) != expected_count:
            reviews.append(f"Row count changed: {name}")
            print(f"REVIEW: Baseline row count was {expected_count}")

    families = tables["source_family_registry.csv"]
    matrix = tables["annual_accounting_matrix.csv"]
    ledger = tables["canonical_annual_ledger.csv"]
    crosswalk = tables["evidence_crosswalk.csv"]

    family_ids = [row["family_id"] for row in families]
    unique_keys(family_ids, "Unique family identifiers")

    family_by_id = {row["family_id"]: row for row in families}

    matrix_keys = keys(matrix, "source_year")
    ledger_keys = keys(ledger, "fiscal_year")

    unique_keys(matrix_keys, "Unique matrix family-year keys")
    unique_keys(ledger_keys, "Unique ledger family-year keys")

    expected_matrix = {
        (family_id, year)
        for family_id in family_ids
        for year in YEARS
    }

    expected_ledger = {
        (row["family_id"], year)
        for row in families
        if row["registry_role"] == CANDIDATE_ROLE
        for year in YEARS
    }

    actual_matrix = set(matrix_keys)
    actual_ledger = set(ledger_keys)

    check(
        actual_matrix == expected_matrix,
        "Matrix covers every registered family-year exactly",
    )

    check(
        actual_ledger == expected_ledger,
        "Ledger membership matches candidate-payment family roles",
    )

    for key in sorted(expected_matrix - actual_matrix):
        print(f"  MISSING MATRIX: {key}")

    for key in sorted(actual_matrix - expected_matrix):
        print(f"  EXTRA MATRIX: {key}")

    for key in sorted(expected_ledger - actual_ledger):
        print(f"  MISSING LEDGER: {key}")

    for key in sorted(actual_ledger - expected_ledger):
        print(f"  EXTRA LEDGER: {key}")

    check(
        all(
            row["registry_role"] in
            ({CANDIDATE_ROLE} | NONADDITIVE_ROLES)
            for row in families
        ),
        "All family roles are recognized",
    )

    check(
        all(
            not row["parent_family_id"]
            or row["parent_family_id"] in family_by_id
            for row in families
        ),
        "All parent-family references resolve",
    )

    check(
        all(
            row["ledger_status"] == "NOT_YET_AUTHORIZED"
            and not row["authorized_amount_usd"].strip()
            for row in ledger
        ),
        "No ledger entries have been prematurely authorized",
    )

    check(
        all(
            row["ledger_authorization"] == "NOT_YET_AUTHORIZED"
            for row in matrix
        ),
        "Matrix contains no premature ledger authorizations",
    )

    check(
        all(
            row["ledger_authorization"] == "NOT_YET_AUTHORIZED"
            for row in families
        ),
        "Family registry contains no premature authorizations",
    )

    check(
        all(row["repository_path"].strip() for row in crosswalk),
        "All evidence crosswalk entries have repository references",
    )

    matrix_by_key = dict(zip(matrix_keys, matrix))
    amount_mismatches = []

    for key, ledger_row in zip(ledger_keys, ledger):
        matrix_row = matrix_by_key.get(key)

        if matrix_row is None:
            continue

        matrix_amount = matrix_row["observed_amount_usd"].strip()
        ledger_amount = ledger_row[
            "candidate_observed_amount_usd"
        ].strip()

        if matrix_amount != ledger_amount:
            amount_mismatches.append(
                (key, matrix_amount, ledger_amount)
            )

    check(
        not amount_mismatches,
        "Matrix and ledger candidate amounts agree",
    )

    for key, matrix_amount, ledger_amount in amount_mismatches:
        print(
            f"  AMOUNT MISMATCH: {key} "
            f"matrix={matrix_amount!r} ledger={ledger_amount!r}"
        )

    print("\n" + "=" * 72)
    print(f"FAILURES: {len(failures)}")
    print(f"BASELINE REVIEWS: {len(reviews)}")

    for item in reviews:
        print(f"REVIEW: {item}")

    if failures:
        print("RESULT: FAIL")
        return 1

    if reviews:
        print("RESULT: PASS WITH BASELINE REVIEW REQUIRED")
        return 0

    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
