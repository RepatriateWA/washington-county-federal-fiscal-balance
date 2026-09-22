from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

OMB_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "omb"
    / "object_class"
)

OUTPUT_DIR = (
    ROOT
    / "data"
    / "interim"
    / "omb"
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "omb_federal_wage_object_class_actuals_2015_2024.csv"
)

OUTPUT_MANIFEST = (
    OUTPUT_DIR
    / "omb_federal_wage_object_class_actuals_2015_2024_manifest.json"
)


OBJECT_CLASS_DESCRIPTIONS = {
    "11.1": "Full-time permanent",
    "11.3": "Other than full-time permanent",
    "11.5": "Other personnel compensation",
    "11.6": "Military personnel - basic allowance for housing",
    "11.7": "Military personnel",
    "11.8": "Special personal services payments",
}


# ============================================================================
# Manually verified primary-source observations
#
# Units:
#     Millions of dollars
#
# Source:
#     Government-wide Table 1, Obligations by Object Class
#
# Value status:
#     ACTUAL
#
# Each target fiscal year is taken from the subsequent Budget vintage in
# which that fiscal year is reported as actual.
#
# IMPORTANT:
# FFY2017 and FFY2018 are intentionally identical. Both source PDFs were
# manually rechecked and the published values are preserved without alteration.
# ============================================================================

SOURCE_DATA = {
    2015: {
        "budget_vintage": 2017,
        "page": 3,
        "values": {
            "11.1": 135108,
            "11.3": 5247,
            "11.5": 10189,
            "11.6": 22536,
            "11.7": 75722,
            "11.8": 1178,
        },
    },
    2016: {
        "budget_vintage": 2018,
        "page": 3,
        "values": {
            "11.1": 138862,
            "11.3": 5506,
            "11.5": 10609,
            "11.6": 22584,
            "11.7": 75654,
            "11.8": 1168,
        },
    },
    2017: {
        "budget_vintage": 2019,
        "page": 3,
        "values": {
            "11.1": 142140,
            "11.3": 5415,
            "11.5": 11523,
            "11.6": 23015,
            "11.7": 76456,
            "11.8": 1066,
        },
    },
    2018: {
        "budget_vintage": 2020,
        "page": 3,
        "values": {
            "11.1": 142140,
            "11.3": 5415,
            "11.5": 11523,
            "11.6": 23015,
            "11.7": 76456,
            "11.8": 1066,
        },
    },
    2019: {
        "budget_vintage": 2021,
        "page": 3,
        "values": {
            "11.1": 150607,
            "11.3": 5571,
            "11.5": 13052,
            "11.6": 24371,
            "11.7": 81528,
            "11.8": 1306,
        },
    },
    2020: {
        "budget_vintage": 2022,
        "page": 3,
        "values": {
            "11.1": 158719,
            "11.3": 7294,
            "11.5": 13763,
            "11.6": 25135,
            "11.7": 84437,
            "11.8": 1597,
        },
    },
    2021: {
        "budget_vintage": 2023,
        "page": 3,
        "values": {
            "11.1": 170661,
            "11.3": 7316,
            "11.5": 15481,
            "11.6": 25931,
            "11.7": 89071,
            "11.8": 2091,
        },
    },
    2022: {
        "budget_vintage": 2024,
        "page": 3,
        "values": {
            "11.1": 174304,
            "11.3": 6337,
            "11.5": 15003,
            "11.6": 26344,
            "11.7": 90206,
            "11.8": 2821,
        },
    },
    2023: {
        "budget_vintage": 2025,
        "page": 3,
        "values": {
            "11.1": 182672,
            "11.3": 6541,
            "11.5": 16069,
            "11.6": 28012,
            "11.7": 93010,
            "11.8": 2179,
        },
    },
    2024: {
        "budget_vintage": 2026,
        "page": 3,
        "values": {
            "11.1": 202948,
            "11.3": 6670,
            "11.5": 16231,
            "11.6": 29885,
            "11.7": 95162,
            "11.8": 1544,
        },
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def find_source_pdf(
    budget_vintage: int,
) -> Path:

    directory = (
        OMB_ROOT
        / f"FY{budget_vintage}"
    )

    matches = sorted(
        directory.glob(
            f"BUDGET-{budget_vintage}-OBJCLASS_retrieved_*.pdf"
        )
    )

    if not matches:
        raise RuntimeError(
            "No preserved source PDF found for "
            f"FY{budget_vintage}."
        )

    return matches[-1]


def build_rows() -> list[dict]:

    expected_years = set(
        range(2015, 2025)
    )

    if set(SOURCE_DATA) != expected_years:
        raise RuntimeError(
            "SOURCE_DATA must contain exactly "
            "FFY2015-FFY2024."
        )

    required_codes = set(
        OBJECT_CLASS_DESCRIPTIONS
    )

    rows = []

    for fiscal_year in sorted(
        SOURCE_DATA
    ):

        spec = SOURCE_DATA[
            fiscal_year
        ]

        budget_vintage = int(
            spec["budget_vintage"]
        )

        if (
            budget_vintage
            != fiscal_year + 2
        ):
            raise RuntimeError(
                "Unexpected budget-vintage mapping "
                f"for FFY{fiscal_year}: "
                f"FY{budget_vintage}"
            )

        values = spec[
            "values"
        ]

        if set(values) != required_codes:
            raise RuntimeError(
                f"FFY{fiscal_year} does not contain "
                "exactly the six required "
                "object classes."
            )

        source_pdf = find_source_pdf(
            budget_vintage
        )

        source_sha256 = sha256_file(
            source_pdf
        )

        for object_class_code in sorted(
            required_codes
        ):

            obligation_millions = int(
                values[
                    object_class_code
                ]
            )

            rows.append(
                {
                    "target_fiscal_year":
                        fiscal_year,

                    "budget_vintage":
                        budget_vintage,

                    "value_status":
                        "ACTUAL",

                    "accounting_measure":
                        "OBLIGATIONS_BY_OBJECT_CLASS",

                    "scope":
                        "GOVERNMENT_WIDE",

                    "object_class_code":
                        object_class_code,

                    "object_class_description":
                        OBJECT_CLASS_DESCRIPTIONS[
                            object_class_code
                        ],

                    "obligation_millions":
                        obligation_millions,

                    "obligation_dollars":
                        obligation_millions
                        * 1_000_000,

                    "source_page":
                        int(spec["page"]),

                    "source_file":
                        str(
                            source_pdf.relative_to(
                                ROOT
                            )
                        ),

                    "source_sha256":
                        source_sha256,

                    "source_verification":
                        "MANUALLY_VERIFIED",
                }
            )

    return rows


def validate_rows(
    rows: list[dict],
) -> None:

    if len(rows) != 60:
        raise RuntimeError(
            "Expected exactly 60 atomic "
            f"observations; found {len(rows)}."
        )

    expected_codes = set(
        OBJECT_CLASS_DESCRIPTIONS
    )

    for fiscal_year in range(
        2015,
        2025,
    ):

        year_rows = [
            row
            for row in rows
            if row[
                "target_fiscal_year"
            ] == fiscal_year
        ]

        if len(year_rows) != 6:
            raise RuntimeError(
                f"FFY{fiscal_year}: expected "
                f"6 rows; found {len(year_rows)}."
            )

        observed_codes = {
            row["object_class_code"]
            for row in year_rows
        }

        if (
            observed_codes
            != expected_codes
        ):
            raise RuntimeError(
                f"FFY{fiscal_year}: "
                "object-class coverage failure."
            )

    duplicate_keys = set()
    seen = set()

    for row in rows:

        key = (
            row["target_fiscal_year"],
            row["budget_vintage"],
            row["object_class_code"],
        )

        if key in seen:
            duplicate_keys.add(
                key
            )

        seen.add(
            key
        )

    if duplicate_keys:
        raise RuntimeError(
            "Duplicate atomic observation keys: "
            f"{sorted(duplicate_keys)}"
        )


def derive_controls(
    rows: list[dict],
) -> list[dict]:

    indexed = {}

    for row in rows:

        indexed[
            (
                row["target_fiscal_year"],
                row["object_class_code"],
            )
        ] = row[
            "obligation_millions"
        ]

    controls = []

    for fiscal_year in range(
        2015,
        2025,
    ):

        oc = {
            code:
                indexed[
                    (
                        fiscal_year,
                        code,
                    )
                ]
            for code
            in OBJECT_CLASS_DESCRIPTIONS
        }

        military = (
            oc["11.6"]
            + oc["11.7"]
        )

        nonmilitary = (
            oc["11.1"]
            + oc["11.3"]
            + oc["11.5"]
            + oc["11.8"]
        )

        total = (
            military
            + nonmilitary
        )

        controls.append(
            {
                "fiscal_year":
                    fiscal_year,

                "military_wage_obligations_millions":
                    military,

                "nonmilitary_wage_obligations_millions":
                    nonmilitary,

                "total_wage_obligations_millions":
                    total,
            }
        )

    return controls


def write_csv(
    rows: list[dict],
) -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "target_fiscal_year",
        "budget_vintage",
        "value_status",
        "accounting_measure",
        "scope",
        "object_class_code",
        "object_class_description",
        "obligation_millions",
        "obligation_dollars",
        "source_page",
        "source_file",
        "source_sha256",
        "source_verification",
    ]

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


def write_manifest(
    rows: list[dict],
    controls: list[dict],
) -> None:

    manifest = {
        "purpose":
            (
                "Normalized primary-source evidence "
                "for WCFFBP federal wage-obligation "
                "controls, FFY2015-FFY2024."
            ),

        "observation_count":
            len(rows),

        "expected_observation_count":
            60,

        "coverage":
            "FFY2015-FFY2024",

        "value_status":
            "ACTUAL",

        "accounting_measure":
            "OBLIGATIONS_BY_OBJECT_CLASS",

        "scope":
            "GOVERNMENT_WIDE",

        "object_classes": {
            code:
                description
            for code, description
            in OBJECT_CLASS_DESCRIPTIONS.items()
        },

        "derivation_rules": {
            "MILITARY_WAGES":
                "11.6 + 11.7",

            "NONMILITARY_WAGES":
                "11.1 + 11.3 + 11.5 + 11.8",

            "TOTAL_WAGES":
                (
                    "MILITARY_WAGES + "
                    "NONMILITARY_WAGES"
                ),
        },

        "source_verification":
            "MANUALLY_VERIFIED",

        "known_source_note":
            (
                "The FY2019 Budget publication's "
                "FFY2017 actual object-class values "
                "and the FY2020 Budget publication's "
                "FFY2018 actual values are identical "
                "for all six harvested object classes. "
                "Both source PDFs were manually "
                "rechecked and the published values "
                "are preserved without alteration. "
                "WCFFBP does not infer whether this "
                "reflects identical underlying actuals, "
                "a publication carry-forward, or another "
                "source-publication issue."
            ),

        "derived_controls":
            controls,

        "csv_file":
            str(
                OUTPUT_CSV.relative_to(
                    ROOT
                )
            ),

        "csv_sha256":
            sha256_file(
                OUTPUT_CSV
            ),
    }

    with OUTPUT_MANIFEST.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            manifest,
            f,
            indent=2,
        )

        f.write("\n")


def main() -> None:

    rows = build_rows()

    validate_rows(
        rows
    )

    write_csv(
        rows
    )

    controls = derive_controls(
        rows
    )

    write_manifest(
        rows,
        controls,
    )

    print()
    print("=" * 72)
    print(
        "OMB WAGE OBJECT-CLASS "
        "EVIDENCE BUILD COMPLETE"
    )
    print("=" * 72)

    print(
        f"Atomic observations: "
        f"{len(rows)}"
    )

    print(
        f"CSV:      {OUTPUT_CSV}"
    )

    print(
        f"SHA-256:  "
        f"{sha256_file(OUTPUT_CSV)}"
    )

    print(
        f"Manifest: {OUTPUT_MANIFEST}"
    )

    print()
    print(
        f"{'FFY':<6}"
        f"{'Nonmilitary':>16}"
        f"{'Military':>16}"
        f"{'Total':>16}"
    )

    print("-" * 54)

    for row in controls:

        print(
            f"{row['fiscal_year']:<6}"
            f"{row['nonmilitary_wage_obligations_millions']:>15,}"
            f"{row['military_wage_obligations_millions']:>16,}"
            f"{row['total_wage_obligations_millions']:>16,}"
        )


if __name__ == "__main__":
    main()