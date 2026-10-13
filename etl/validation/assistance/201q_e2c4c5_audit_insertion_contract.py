
"""
ETL-201Q E.2C.4C.5
Independent static audit of the locked historical insertion loader.

Source inspection only:
- No import or execution of the target loader
- No database connection
- No production DML
- No sequence consumption

An audit PASS means only that the specified static checks passed.
It does not authorize production insertion.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import sys


TARGET = Path(
    "etl/loaders/"
    "load_usaspending_assistance_historical_transactions_201q_e2c4c4.py"
)

REQUIRED_FUNCTIONS = (
    "prepare_stage",
    "insert_canonical",
    "verify_generated_id_mapping",
    "insert_provenance",
    "verify_post_insert",
    "production_insertion_contract",
    "main",
)

INSERTION_FUNCTIONS = {
    "insert_canonical",
    "insert_provenance",
    "production_insertion_contract",
}

PROHIBITED_SQL = (
    "ON CONFLICT",
    "DO UPDATE",
    "DO NOTHING",
    "MERGE INTO",
    "NEXTVAL(",
    "SETVAL(",
    "TRUNCATE ",
)

EXPECTED = {
    "canonical_insert": (
        "INSERT INTO ASSISTANCE.AWARD_TRANSACTION (",
        "RETURNING",
        "ASSISTANCE_TRANSACTION_ID",
    ),
    "provenance_insert": (
        "INSERT INTO ASSISTANCE.AWARD_TRANSACTION_OBSERVATION (",
        "RAW_ASSISTANCE_TRANSACTION_ID",
        "ASSISTANCE_TRANSACTION_ID",
    ),
}


def check(condition, label, failures):
    status = "PASS" if condition else "FAIL"
    print(f"{status}: {label}", flush=True)

    if not condition:
        failures.append(label)


def calls_in(node):
    """Return simple names of functions invoked within an AST node."""

    names = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func

            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)

    return names


def strings_in(node):
    """Collect string constants, including SQL embedded in f-strings."""

    parts = []

    for child in ast.walk(node):
        if isinstance(child, ast.Constant):
            if isinstance(child.value, str):
                parts.append(child.value)

    return "\n".join(parts).upper()


def audit():
    failures = []

    print("=" * 76)
    print("ETL-201Q E.2C.4C.5")
    print("INDEPENDENT STATIC INSERTION CONTRACT AUDIT")
    print("=" * 76)

    if not TARGET.is_file():
        raise FileNotFoundError(TARGET)

    source = TARGET.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(TARGET))

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assignments = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value

    check(
        all(name in functions for name in REQUIRED_FUNCTIONS),
        "Required insertion functions present",
        failures,
    )

    authorization = assignments.get("COMMIT_AUTHORIZED")

    check(
        isinstance(authorization, ast.Constant)
        and authorization.value is False,
        "Commit authorization constant is False",
        failures,
    )

    main = functions.get("main")

    if main is not None:
        main_calls = calls_in(main)
        main_text = strings_in(main)

        check(
            not (main_calls & INSERTION_FUNCTIONS),
            "Main does not directly invoke insertion functions",
            failures,
        )

        check(
            "PRODUCTION INSERTION IS NOT AUTHORIZED" in main_text,
            "Main contains explicit commit refusal",
            failures,
        )

        check(
            "CONNECT" not in main_calls,
            "Main contains no direct database connection",
            failures,
        )

        check(
            not ({"commit", "rollback"} & main_calls),
            "Main contains no transaction completion calls",
            failures,
        )

    canonical = functions.get("insert_canonical")
    provenance = functions.get("insert_provenance")
    contract = functions.get("production_insertion_contract")

    if canonical is not None:
        sql = strings_in(canonical)

        check(
            all(token in sql for token in EXPECTED["canonical_insert"]),
            "Canonical INSERT and RETURNING contract present",
            failures,
        )

        check(
            not any(token in sql for token in PROHIBITED_SQL),
            "Canonical insertion has no prohibited SQL clauses",
            failures,
        )

        check(
            "EXECUTE_VALUES" in {
                name.upper() for name in calls_in(canonical)
            },
            "Generated-ID mapping uses temporary-table bulk insertion",
            failures,
        )

    if provenance is not None:
        sql = "\n".join(
            strings_in(call)
            for call in ast.walk(provenance)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "execute"
        ).upper()

        check(
            all(token in sql for token in EXPECTED["provenance_insert"]),
            "Strict provenance INSERT contract present",
            failures,
        )

        check(
            not any(token in sql for token in PROHIBITED_SQL),
            "Provenance insertion has no conflict suppression",
            failures,
        )

    if contract is not None:
        contract_calls = calls_in(contract)
        sql = strings_in(contract)

        check(
            all(
                name in contract_calls
                for name in (
                    "prepare_stage",
                    "insert_canonical",
                    "verify_generated_id_mapping",
                    "insert_provenance",
                    "verify_post_insert",
                )
            ),
            "Contract invokes all required insertion stages",
            failures,
        )

        check(
            "LOCK TABLE" in sql,
            "Contract contains destination-table locking",
            failures,
        )

    print()
    print("=" * 76)

    if failures:
        print("E.2C.4C.5 STATIC AUDIT: FAIL")
        print(f"Failed controls: {len(failures)}")
        for label in failures:
            print(f"  - {label}")
    else:
        print("E.2C.4C.5 STATIC AUDIT: PASS")

    print()
    print("STATIC AUDIT ONLY")
    print("NO DATABASE CONNECTION")
    print("NO PRODUCTION DML")
    print("NO SEQUENCE CONSUMPTION")
    print("PERMANENT INSERTION: NOT AUTHORIZED")
    print("=" * 76)

    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    if args.commit:
        print("REFUSED: production insertion is not authorized.")
        return 2

    if not args.audit:
        parser.error("Specify --audit")

    return audit()


if __name__ == "__main__":
    sys.exit(main())
