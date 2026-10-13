
"""
ETL-201Q E.2C.4B
Historical assistance transaction insertion preflight.

Runs previously certified validators without production writes.
Does not authorize or perform historical insertion.
"""

from __future__ import annotations

import argparse
import subprocess
import sys


VALIDATORS = (
    (
        "Exact population membership",
        "etl.validation.assistance."
        "201q_e2c3d2_verify_historical_membership",
        "--validate",
    ),
    (
        "Typed staging and field fidelity",
        "etl.validation.assistance."
        "201q_e2c3d3_verify_historical_field_fidelity",
        "--validate",
    ),
)


def main():
    parser = argparse.ArgumentParser()

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--commit", action="store_true")

    args = parser.parse_args()

    if args.commit:
        print(
            "REFUSED: production insertion is not authorized.",
            file=sys.stderr,
        )
        return 2

    if not args.preflight:
        parser.error("Specify --preflight")

    print("=" * 76, flush=True)
    print("ETL-201Q E.2C.4B INSERTION PREFLIGHT", flush=True)
    print("=" * 76, flush=True)

    for label, module, argument in VALIDATORS:
        print(flush=True)
        print(f"RUNNING: {label}", flush=True)
        print(f"MODULE : {module}", flush=True)

        result = subprocess.run(
            [sys.executable, "-m", module, argument],
            check=False,
        )

        if result.returncode != 0:
            print(
                f"PREFLIGHT FAILED: {label} "
                f"(exit code {result.returncode})",
                file=sys.stderr,
                flush=True,
            )
            return result.returncode

        print(f"PASS: {label}", flush=True)

    print(flush=True)
    print("=" * 76, flush=True)
    print("E.2C.4B INSERTION PREFLIGHT: PASS", flush=True)
    print("PERMANENT INSERTION: NOT AUTHORIZED", flush=True)
    print("=" * 76, flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
