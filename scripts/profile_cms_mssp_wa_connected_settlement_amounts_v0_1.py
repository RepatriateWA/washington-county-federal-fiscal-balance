"""
WCFFBP
CMS MSSP WA-Connected Settlement Amounts Profile v0.1
Attempt 2

PURPOSE
-------
Join the frozen CMS MSSP Washington organizational-connection bridge
to the preserved MSSP Performance Year Financial and Quality Results
and profile EarnSaveLoss for the certified 132 ACO-period observations.

IDENTITY RULES
--------------
2015
    Use the financial identifier already certified through the frozen
    historical-linkage / bridge process.

2016-2017
    Financial ACO_Num
        -> official CMS ACO ID crosswalk
        -> canonical ACO_ID
        -> frozen bridge identifier.

2018-2024, including 2019A
    Direct ACO_ID linkage.

CRITICAL INTERPRETIVE BOUNDARY
------------------------------
The resulting dollar amounts are:

    EarnSaveLoss associated with ACO-period observations having
    certified Washington organizational connection.

They are NOT certified as:

    - federal dollars economically accruing to Washington;
    - Washington beneficiary incidence;
    - Washington provider-service incidence;
    - Washington payment-dollar incidence;
    - county payment-dollar incidence;
    - cash-year federal expenditure;
    - additive to Original Medicare / FFS;
    - principal-ledger inflow.

Positive and negative EarnSaveLoss are reported separately.

Negative EarnSaveLoss is NOT classified as negative federal spending.

2019A remains an independent CMS performance period.

No allocation is performed.
No netting against advance/AIM/AIP recoupment is performed.
No database writes.
No ledger inclusion.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile

from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]


# =====================================================================
# SOURCES
# =====================================================================

PERFORMANCE_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "Performance Year Financial and Quality Results.zip"
)

BRIDGE_CSV = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "validation"
    / "wa_organizational_connection_bridge_v0_1"
    / "cms_mssp_wa_organizational_connection_bridge_v0_1.csv"
)

CROSSWALK_XLSX = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_aco_id_crosswalk"
    / "ssp-aco-id-crosswalk.xlsx"
)


EXPECTED_PERFORMANCE_SHA = (
    "C7555FA4849ADCA9AB4ECACAC607715F3B6BAA2DDA5CE4D422CA8668B1A9F128"
)

EXPECTED_CROSSWALK_SHA = (
    "0996CC8DC0C15961FB99012734F236B656F4CA935D4D4B793EDB11F281B244F4"
)


# =====================================================================
# PERIOD UNIVERSE
# =====================================================================

PERIODS = [
    "2015",
    "2016",
    "2017",
    "2018",
    "2019",
    "2019A",
    "2020",
    "2021",
    "2022",
    "2023",
    "2024",
]


EXPECTED_BRIDGE_COUNTS = {
    "2015": 4,
    "2016": 6,
    "2017": 6,
    "2018": 12,
    "2019": 10,
    "2019A": 4,
    "2020": 13,
    "2021": 13,
    "2022": 16,
    "2023": 20,
    "2024": 28,
}

EXPECTED_BRIDGE_TOTAL = 132
EXPECTED_CROSSWALK_BRIDGE_TOTAL = 12
EXPECTED_CROSSWALK_UNIQUE_MAPPINGS = 767


# =====================================================================
# OUTPUTS
# =====================================================================

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "validation"
    / "wa_connected_settlement_amounts_v0_1"
)

JOINED_CSV = (
    OUTPUT_DIR
    / "cms_mssp_wa_connected_settlement_observations_v0_1.csv"
)

PERIOD_PROFILE_CSV = (
    OUTPUT_DIR
    / "cms_mssp_wa_connected_settlement_period_profile_v0_1.csv"
)

CROSSWALK_DIAGNOSTIC_CSV = (
    OUTPUT_DIR
    / "cms_mssp_wa_connected_settlement_crosswalk_diagnostic_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_wa_connected_settlement_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_mssp_wa_connected_settlement_report_v0_1.txt"
)


# =====================================================================
# HELPERS
# =====================================================================

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            h.update(block)

    return h.hexdigest().upper()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(
        data
    ).hexdigest().upper()


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(
            rows
        )


def infer_period(
    member_name: str,
) -> str:
    text = member_name.replace(
        "\\",
        "/",
    ).lower()

    if (
        "2019_off-cycle_1" in text
        or "2019_off_cycle_1" in text
        or "2019a" in text
    ):
        return "2019A"

    for year in range(
        2015,
        2025,
    ):
        if re.search(
            rf"(?<!\d){year}(?!\d)",
            text,
        ):
            return str(
                year
            )

    return "UNRESOLVED"


def choose_column(
    columns: list[str],
    candidates: list[str],
) -> str | None:
    lookup = {
        str(column).casefold(): column
        for column in columns
    }

    for candidate in candidates:
        actual = lookup.get(
            candidate.casefold()
        )

        if actual is not None:
            return actual

    return None


def clean_identifier(
    value,
) -> str:
    if value is None:
        return ""

    text = str(
        value
    ).strip()

    if text.lower() in {
        "",
        "nan",
        "none",
        "null",
        "-",
    }:
        return ""

    if re.fullmatch(
        r"\d+\.0",
        text,
    ):
        text = text[:-2]

    return text


def normalize_aco_id(
    value,
) -> str:
    text = clean_identifier(
        value
    ).upper()

    if not text:
        return ""

    if re.fullmatch(
        r"A\d+",
        text,
    ):
        return text

    if re.fullmatch(
        r"\d+",
        text,
    ):
        return (
            "A"
            + text.zfill(
                5
            )
        )

    return text


def decimal_from_value(
    value,
) -> Decimal | None:
    if value is None:
        return None

    text = str(
        value
    ).strip()

    if text.lower() in {
        "",
        "nan",
        "none",
        "null",
        "-",
        "n/a",
        "na",
    }:
        return None

    text = (
        text
        .replace(
            "$",
            "",
        )
        .replace(
            ",",
            "",
        )
        .replace(
            "(",
            "-",
        )
        .replace(
            ")",
            "",
        )
        .strip()
    )

    try:
        return Decimal(
            text
        )

    except InvalidOperation:
        return None


def money(
    value: Decimal,
) -> str:
    return f"${value:,.2f}"


# =====================================================================
# PERFORMANCE RESULTS
# =====================================================================

def load_performance_results() -> dict[str, dict]:
    result = {}

    with zipfile.ZipFile(
        PERFORMANCE_ZIP,
        "r",
    ) as archive:

        for info in archive.infolist():

            if (
                info.is_dir()
                or not info.filename.lower().endswith(
                    ".csv"
                )
            ):
                continue

            period = infer_period(
                info.filename
            )

            if period not in PERIODS:
                continue

            if period in result:
                raise RuntimeError(
                    "Duplicate performance CSV inferred for "
                    f"{period}: "
                    f"{result[period]['member_name']} "
                    f"and {info.filename}"
                )

            raw = archive.read(
                info
            )

            text = raw.decode(
                "utf-8-sig",
                errors="strict",
            )

            df = pd.read_csv(
                io.StringIO(
                    text
                ),
                dtype=str,
                keep_default_na=False,
                low_memory=False,
            )

            result[
                period
            ] = {
                "member_name": info.filename,
                "member_sha256": sha256_bytes(
                    raw
                ),
                "df": df,
            }

    return result


# =====================================================================
# BRIDGE
# =====================================================================

def load_bridge() -> pd.DataFrame:
    return pd.read_csv(
        BRIDGE_CSV,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )


# =====================================================================
# OFFICIAL CMS CROSSWALK
# =====================================================================

def load_crosswalk() -> tuple[
    dict[str, str],
    dict[str, str],
]:
    """
    Return:

        ACO_Num -> canonical ACO_ID

    and:

        canonical ACO_ID -> ACO_Num

    The reverse mapping is used only as a diagnostic / uniqueness
    control. Financial linkage remains forward:
        financial ACO_Num -> official crosswalk -> ACO_ID.
    """

    df = pd.read_excel(
        CROSSWALK_XLSX,
        sheet_name="ACO ID Crosswalk",
        dtype=str,
    )

    id_col = choose_column(
        list(
            df.columns
        ),
        [
            "ACO_ID",
            "ACO ID",
        ],
    )

    num_col = choose_column(
        list(
            df.columns
        ),
        [
            "ACO_NUM",
            "ACO_Num",
            "ACO Num",
        ],
    )

    if (
        id_col is None
        or num_col is None
    ):
        raise RuntimeError(
            "Could not identify ACO_ID / ACO_NUM "
            "columns in official CMS crosswalk."
        )

    forward = {}
    reverse = {}

    for _, row in df.iterrows():

        aco_num = clean_identifier(
            row[
                num_col
            ]
        )

        aco_id = normalize_aco_id(
            row[
                id_col
            ]
        )

        if (
            not aco_num
            or not aco_id
        ):
            continue

        if (
            aco_num in forward
            and forward[
                aco_num
            ]
            != aco_id
        ):
            raise RuntimeError(
                "Official crosswalk ACO_Num maps to "
                f"multiple ACO_ID values: {aco_num}"
            )

        if (
            aco_id in reverse
            and reverse[
                aco_id
            ]
            != aco_num
        ):
            raise RuntimeError(
                "Official crosswalk ACO_ID maps to "
                f"multiple ACO_Num values: {aco_id}"
            )

        forward[
            aco_num
        ] = aco_id

        reverse[
            aco_id
        ] = aco_num

    return (
        forward,
        reverse,
    )


# =====================================================================
# CANONICAL FINANCIAL IDENTIFIER
# =====================================================================

def canonical_financial_identifier(
    period: str,
    raw_identifier,
    crosswalk_forward: dict[str, str],
) -> tuple[str, str]:
    """
    Convert the financial PUF's period-specific identifier into the
    canonical identifier stored in the frozen bridge.

    Returns:
        canonical_identifier,
        identity_method
    """

    raw_id = clean_identifier(
        raw_identifier
    )

    if not raw_id:
        return (
            "",
            "MISSING_IDENTIFIER",
        )

    if period in {
        "2016",
        "2017",
    }:
        canonical_id = crosswalk_forward.get(
            raw_id,
            "",
        )

        return (
            canonical_id,
            "OFFICIAL_CMS_ACO_ID_CROSSWALK",
        )

    return (
        normalize_aco_id(
            raw_id
        ),
        (
            "2015_CERTIFIED_FINANCIAL_IDENTIFIER"
            if period == "2015"
            else "DIRECT_ACO_ID"
        ),
    )


# =====================================================================
# MAIN
# =====================================================================

def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    checks = []

    def check(
        name: str,
        passed: bool,
        detail: str,
    ) -> None:
        checks.append(
            {
                "check": name,
                "status": (
                    "PASS"
                    if passed
                    else "FAIL"
                ),
                "detail": detail,
            }
        )

    # -----------------------------------------------------------------
    # SOURCE EXISTENCE
    # -----------------------------------------------------------------

    performance_exists = (
        PERFORMANCE_ZIP.exists()
    )

    bridge_exists = (
        BRIDGE_CSV.exists()
    )

    crosswalk_exists = (
        CROSSWALK_XLSX.exists()
    )

    check(
        "Preserved MSSP performance-results ZIP exists",
        performance_exists,
        str(
            PERFORMANCE_ZIP.relative_to(
                REPO_ROOT
            )
        ),
    )

    check(
        "Frozen WA organizational-connection bridge exists",
        bridge_exists,
        str(
            BRIDGE_CSV.relative_to(
                REPO_ROOT
            )
        ),
    )

    check(
        "Official CMS ACO ID crosswalk exists",
        crosswalk_exists,
        str(
            CROSSWALK_XLSX.relative_to(
                REPO_ROOT
            )
        ),
    )

    if not (
        performance_exists
        and bridge_exists
        and crosswalk_exists
    ):
        write_csv(
            CHECKS_CSV,
            [
                "check",
                "status",
                "detail",
            ],
            checks,
        )

        print(
            "FAIL: required source artifact is missing."
        )

        return 1

    # -----------------------------------------------------------------
    # SOURCE HASHES
    # -----------------------------------------------------------------

    actual_performance_sha = (
        sha256_file(
            PERFORMANCE_ZIP
        )
    )

    actual_crosswalk_sha = (
        sha256_file(
            CROSSWALK_XLSX
        )
    )

    bridge_sha = (
        sha256_file(
            BRIDGE_CSV
        )
    )

    check(
        "Performance-results ZIP SHA-256 matches preserved acquisition",
        actual_performance_sha
        == EXPECTED_PERFORMANCE_SHA,
        actual_performance_sha,
    )

    check(
        "Official CMS crosswalk SHA-256 matches preserved acquisition",
        actual_crosswalk_sha
        == EXPECTED_CROSSWALK_SHA,
        actual_crosswalk_sha,
    )

    # -----------------------------------------------------------------
    # LOAD SOURCES
    # -----------------------------------------------------------------

    performance = (
        load_performance_results()
    )

    bridge = (
        load_bridge()
    )

    (
        crosswalk_forward,
        crosswalk_reverse,
    ) = load_crosswalk()

    check(
        "Exactly 11 expected performance periods discovered",
        set(
            performance
        )
        == set(
            PERIODS
        ),
        (
            f"{len(performance)}/11 | "
            + ",".join(
                performance.keys()
            )
        ),
    )

    check(
        "Official crosswalk reproduces 767 unique ACO_Num mappings",
        len(
            crosswalk_forward
        )
        == EXPECTED_CROSSWALK_UNIQUE_MAPPINGS,
        str(
            len(
                crosswalk_forward
            )
        ),
    )

    check(
        "Official crosswalk reproduces 767 unique canonical ACO_ID mappings",
        len(
            crosswalk_reverse
        )
        == EXPECTED_CROSSWALK_UNIQUE_MAPPINGS,
        str(
            len(
                crosswalk_reverse
            )
        ),
    )

    # -----------------------------------------------------------------
    # BRIDGE STRUCTURE
    # -----------------------------------------------------------------

    required_bridge_columns = {
        "performance_period",
        "financial_aco_identifier",
        "aco_name",
        "identity_method",
        "organization_wa_evidence",
        "participant_wa_evidence",
        "connection_class",
        "geographic_status",
    }

    missing_bridge_columns = (
        required_bridge_columns
        - set(
            bridge.columns
        )
    )

    check(
        "Bridge exposes required certified identity fields",
        not missing_bridge_columns,
        (
            "complete"
            if not missing_bridge_columns
            else ",".join(
                sorted(
                    missing_bridge_columns
                )
            )
        ),
    )

    # -----------------------------------------------------------------
    # BRIDGE ACCOUNTING
    # -----------------------------------------------------------------

    bridge_counts = Counter(
        bridge[
            "performance_period"
        ]
    )

    for period in PERIODS:

        observed = int(
            bridge_counts.get(
                period,
                0,
            )
        )

        expected = (
            EXPECTED_BRIDGE_COUNTS[
                period
            ]
        )

        check(
            f"{period} bridge count reproduces certified v0.1",
            observed == expected,
            f"{observed}/{expected}",
        )

    check(
        "Bridge contains exactly 132 certified observations",
        len(
            bridge
        )
        == EXPECTED_BRIDGE_TOTAL,
        (
            f"{len(bridge)}/"
            f"{EXPECTED_BRIDGE_TOTAL}"
        ),
    )

    bridge_keys = [
        (
            row[
                "performance_period"
            ],
            normalize_aco_id(
                row[
                    "financial_aco_identifier"
                ]
            ),
        )
        for _, row
        in bridge.iterrows()
    ]

    check(
        "Bridge keys are unique",
        len(
            bridge_keys
        )
        == len(
            set(
                bridge_keys
            )
        ),
        (
            f"{len(bridge_keys)} rows; "
            f"{len(set(bridge_keys))} unique keys"
        ),
    )

    expected_geo_status = (
        "ORGANIZATIONAL_CONNECTION_ONLY_"
        "NOT_PAYMENT_INCIDENCE"
    )

    check(
        "All bridge rows retain non-incidence geographic status",
        all(
            bridge[
                "geographic_status"
            ]
            == expected_geo_status
        ),
        (
            f"{len(bridge)}/"
            f"{len(bridge)}"
        ),
    )

    # -----------------------------------------------------------------
    # BUILD CANONICAL FINANCIAL INDEX
    # -----------------------------------------------------------------

    financial_index = {}

    crosswalk_diagnostic_rows = []

    crosswalk_financial_rows = 0
    crosswalk_financial_resolved = 0

    for period in PERIODS:

        df = performance[
            period
        ][
            "df"
        ]

        id_col = choose_column(
            list(
                df.columns
            ),
            [
                "ACO_ID",
                "ACO_Num",
                "ACO_NUM",
            ],
        )

        earn_col = choose_column(
            list(
                df.columns
            ),
            [
                "EarnSaveLoss",
            ],
        )

        name_col = choose_column(
            list(
                df.columns
            ),
            [
                "ACO_Name",
                "ACO Name",
            ],
        )

        if id_col is None:
            raise RuntimeError(
                f"{period}: financial identifier column not found."
            )

        if earn_col is None:
            raise RuntimeError(
                f"{period}: EarnSaveLoss column not found."
            )

        for source_index, row in df.iterrows():

            raw_id = clean_identifier(
                row[
                    id_col
                ]
            )

            (
                canonical_id,
                identity_method,
            ) = canonical_financial_identifier(
                period,
                raw_id,
                crosswalk_forward,
            )

            if period in {
                "2016",
                "2017",
            }:
                crosswalk_financial_rows += 1

                if canonical_id:
                    crosswalk_financial_resolved += 1

            if not canonical_id:
                continue

            key = (
                period,
                canonical_id,
            )

            if key in financial_index:
                raise RuntimeError(
                    "Canonical financial key is not unique: "
                    f"{key}"
                )

            financial_index[
                key
            ] = {
                "source_index": source_index,
                "raw_financial_identifier": raw_id,
                "canonical_identifier": canonical_id,
                "identity_method": identity_method,
                "earn_col": earn_col,
                "name_col": name_col,
                "row": row,
            }

    # -----------------------------------------------------------------
    # CROSSWALK-YEAR SOURCE CONTROLS
    # -----------------------------------------------------------------

    expected_crosswalk_source_rows = (
        len(
            performance[
                "2016"
            ][
                "df"
            ]
        )
        +
        len(
            performance[
                "2017"
            ][
                "df"
            ]
        )
    )

    check(
        "All 2016-2017 financial rows were presented to the official crosswalk",
        crosswalk_financial_rows
        == expected_crosswalk_source_rows,
        (
            f"{crosswalk_financial_rows}/"
            f"{expected_crosswalk_source_rows}"
        ),
    )

    check(
        "All 2016-2017 financial rows resolve through official CMS crosswalk",
        crosswalk_financial_resolved
        == expected_crosswalk_source_rows,
        (
            f"{crosswalk_financial_resolved}/"
            f"{expected_crosswalk_source_rows}"
        ),
    )

    # -----------------------------------------------------------------
    # JOIN FROZEN BRIDGE
    # -----------------------------------------------------------------

    joined_rows = []
    unmatched_bridge_rows = []

    crosswalk_bridge_rows = 0
    crosswalk_bridge_joined = 0

    for _, bridge_row in bridge.iterrows():

        period = bridge_row[
            "performance_period"
        ]

        bridge_id = normalize_aco_id(
            bridge_row[
                "financial_aco_identifier"
            ]
        )

        key = (
            period,
            bridge_id,
        )

        financial_match = (
            financial_index.get(
                key
            )
        )

        if period in {
            "2016",
            "2017",
        }:
            crosswalk_bridge_rows += 1

        if financial_match is None:

            unmatched_bridge_rows.append(
                {
                    "performance_period": period,
                    "financial_aco_identifier": bridge_id,
                    "reason": (
                        "NO_EXACT_CANONICAL_FINANCIAL_MATCH"
                    ),
                }
            )

            if period in {
                "2016",
                "2017",
            }:
                crosswalk_diagnostic_rows.append(
                    {
                        "performance_period": period,
                        "bridge_aco_id": bridge_id,
                        "financial_aco_num": "",
                        "crosswalk_aco_id": "",
                        "join_status": "UNMATCHED",
                    }
                )

            continue

        if period in {
            "2016",
            "2017",
        }:
            crosswalk_bridge_joined += 1

            crosswalk_diagnostic_rows.append(
                {
                    "performance_period": period,
                    "bridge_aco_id": bridge_id,
                    "financial_aco_num": (
                        financial_match[
                            "raw_financial_identifier"
                        ]
                    ),
                    "crosswalk_aco_id": (
                        financial_match[
                            "canonical_identifier"
                        ]
                    ),
                    "join_status": "MATCHED",
                }
            )

        financial_row = (
            financial_match[
                "row"
            ]
        )

        earn_col = (
            financial_match[
                "earn_col"
            ]
        )

        name_col = (
            financial_match[
                "name_col"
            ]
        )

        earn_value = decimal_from_value(
            financial_row[
                earn_col
            ]
        )

        if earn_value is None:

            earn_class = (
                "NONNUMERIC_OR_MISSING"
            )

            earn_text = ""

        elif earn_value > 0:

            earn_class = "POSITIVE"

            earn_text = str(
                earn_value
            )

        elif earn_value < 0:

            earn_class = "NEGATIVE"

            earn_text = str(
                earn_value
            )

        else:

            earn_class = "ZERO"

            earn_text = str(
                earn_value
            )

        joined_rows.append(
            {
                "performance_period": period,
                "financial_aco_identifier": bridge_id,
                "source_financial_identifier": (
                    financial_match[
                        "raw_financial_identifier"
                    ]
                ),
                "financial_identity_method": (
                    financial_match[
                        "identity_method"
                    ]
                ),
                "aco_name": (
                    financial_row[
                        name_col
                    ]
                    if name_col
                    else bridge_row[
                        "aco_name"
                    ]
                ),
                "bridge_identity_method": bridge_row[
                    "identity_method"
                ],
                "connection_class": bridge_row[
                    "connection_class"
                ],
                "geographic_status": bridge_row[
                    "geographic_status"
                ],
                "earn_save_loss": earn_text,
                "earn_save_loss_class": earn_class,
                "interpretive_status": (
                    "WA_CONNECTED_ACO_OBSERVATION_"
                    "NOT_WA_PAYMENT_INCIDENCE"
                ),
            }
        )

    # -----------------------------------------------------------------
    # JOIN CERTIFICATION
    # -----------------------------------------------------------------

    check(
        "Exactly 12 certified 2016-2017 bridge observations require crosswalk linkage",
        crosswalk_bridge_rows
        == EXPECTED_CROSSWALK_BRIDGE_TOTAL,
        (
            f"{crosswalk_bridge_rows}/"
            f"{EXPECTED_CROSSWALK_BRIDGE_TOTAL}"
        ),
    )

    check(
        "All 12 certified 2016-2017 bridge observations join through official CMS crosswalk",
        crosswalk_bridge_joined
        == EXPECTED_CROSSWALK_BRIDGE_TOTAL,
        (
            f"{crosswalk_bridge_joined}/"
            f"{EXPECTED_CROSSWALK_BRIDGE_TOTAL}"
        ),
    )

    check(
        "All 132 certified bridge observations join exactly once",
        (
            len(
                joined_rows
            )
            == EXPECTED_BRIDGE_TOTAL
            and not unmatched_bridge_rows
        ),
        (
            f"joined={len(joined_rows)}; "
            f"unmatched={len(unmatched_bridge_rows)}"
        ),
    )

    joined_keys = [
        (
            row[
                "performance_period"
            ],
            row[
                "financial_aco_identifier"
            ],
        )
        for row in joined_rows
    ]

    check(
        "Joined observation keys remain unique",
        len(
            joined_keys
        )
        == len(
            set(
                joined_keys
            )
        ),
        (
            f"{len(joined_keys)} rows; "
            f"{len(set(joined_keys))} unique keys"
        ),
    )

    nonnumeric_count = sum(
        1
        for row in joined_rows
        if row[
            "earn_save_loss_class"
        ]
        == "NONNUMERIC_OR_MISSING"
    )

    check(
        "EarnSaveLoss is numeric for every joined observation",
        nonnumeric_count == 0,
        (
            f"{len(joined_rows) - nonnumeric_count}/"
            f"{len(joined_rows)} numeric"
        ),
    )

    # -----------------------------------------------------------------
    # PERIOD PROFILE
    # -----------------------------------------------------------------

    period_profile = []

    grand_positive_count = 0
    grand_negative_count = 0
    grand_zero_count = 0
    grand_nonnumeric_count = 0

    grand_positive = Decimal(
        "0"
    )

    grand_negative = Decimal(
        "0"
    )

    for period in PERIODS:

        rows = [
            row
            for row in joined_rows
            if row[
                "performance_period"
            ]
            == period
        ]

        positive_values = []
        negative_values = []

        zero_count = 0
        nonnumeric_count_period = 0

        for row in rows:

            classification = row[
                "earn_save_loss_class"
            ]

            if (
                classification
                == "NONNUMERIC_OR_MISSING"
            ):
                nonnumeric_count_period += 1
                continue

            value = Decimal(
                row[
                    "earn_save_loss"
                ]
            )

            if value > 0:
                positive_values.append(
                    value
                )

            elif value < 0:
                negative_values.append(
                    value
                )

            else:
                zero_count += 1

        positive_total = sum(
            positive_values,
            Decimal(
                "0"
            ),
        )

        negative_total = sum(
            negative_values,
            Decimal(
                "0"
            ),
        )

        arithmetic_control = (
            positive_total
            + negative_total
        )

        grand_positive_count += len(
            positive_values
        )

        grand_negative_count += len(
            negative_values
        )

        grand_zero_count += (
            zero_count
        )

        grand_nonnumeric_count += (
            nonnumeric_count_period
        )

        grand_positive += (
            positive_total
        )

        grand_negative += (
            negative_total
        )

        period_profile.append(
            {
                "performance_period": period,
                "wa_connected_observations": len(
                    rows
                ),
                "positive_count": len(
                    positive_values
                ),
                "positive_earn_save_loss": str(
                    positive_total
                ),
                "negative_count": len(
                    negative_values
                ),
                "negative_earn_save_loss": str(
                    negative_total
                ),
                "zero_count": zero_count,
                "nonnumeric_count": (
                    nonnumeric_count_period
                ),
                "arithmetic_net_control": str(
                    arithmetic_control
                ),
                "interpretive_status": (
                    "WA_CONNECTED_ACO_OBSERVATIONS_"
                    "NOT_WA_PAYMENT_INCIDENCE"
                ),
            }
        )

    # -----------------------------------------------------------------
    # PERIOD-SPECIFIC CERTIFICATION
    # -----------------------------------------------------------------

    for row in period_profile:

        period = row[
            "performance_period"
        ]

        observed = int(
            row[
                "wa_connected_observations"
            ]
        )

        expected = (
            EXPECTED_BRIDGE_COUNTS[
                period
            ]
        )

        check(
            f"{period} joined financial count reproduces frozen bridge",
            observed == expected,
            f"{observed}/{expected}",
        )

    period_total = sum(
        int(
            row[
                "wa_connected_observations"
            ]
        )
        for row in period_profile
    )

    check(
        "Period-profile observation counts sum to 132",
        period_total
        == EXPECTED_BRIDGE_TOTAL,
        (
            f"{period_total}/"
            f"{EXPECTED_BRIDGE_TOTAL}"
        ),
    )

    classification_total = (
        grand_positive_count
        + grand_negative_count
        + grand_zero_count
        + grand_nonnumeric_count
    )

    check(
        "EarnSaveLoss classifications account for all 132 observations",
        classification_total
        == EXPECTED_BRIDGE_TOTAL,
        (
            f"{classification_total}/"
            f"{EXPECTED_BRIDGE_TOTAL}"
        ),
    )

    # -----------------------------------------------------------------
    # SORT EVIDENCE
    # -----------------------------------------------------------------

    joined_rows.sort(
        key=lambda row: (
            PERIODS.index(
                row[
                    "performance_period"
                ]
            ),
            row[
                "financial_aco_identifier"
            ],
        )
    )

    crosswalk_diagnostic_rows.sort(
        key=lambda row: (
            PERIODS.index(
                row[
                    "performance_period"
                ]
            ),
            row[
                "bridge_aco_id"
            ],
        )
    )

    # -----------------------------------------------------------------
    # WRITE EVIDENCE
    # -----------------------------------------------------------------

    write_csv(
        JOINED_CSV,
        [
            "performance_period",
            "financial_aco_identifier",
            "source_financial_identifier",
            "financial_identity_method",
            "aco_name",
            "bridge_identity_method",
            "connection_class",
            "geographic_status",
            "earn_save_loss",
            "earn_save_loss_class",
            "interpretive_status",
        ],
        joined_rows,
    )

    write_csv(
        PERIOD_PROFILE_CSV,
        [
            "performance_period",
            "wa_connected_observations",
            "positive_count",
            "positive_earn_save_loss",
            "negative_count",
            "negative_earn_save_loss",
            "zero_count",
            "nonnumeric_count",
            "arithmetic_net_control",
            "interpretive_status",
        ],
        period_profile,
    )

    write_csv(
        CROSSWALK_DIAGNOSTIC_CSV,
        [
            "performance_period",
            "bridge_aco_id",
            "financial_aco_num",
            "crosswalk_aco_id",
            "join_status",
        ],
        crosswalk_diagnostic_rows,
    )

    write_csv(
        CHECKS_CSV,
        [
            "check",
            "status",
            "detail",
        ],
        checks,
    )

    overall_pass = all(
        row[
            "status"
        ]
        == "PASS"
        for row in checks
    )

    # -----------------------------------------------------------------
    # REPORT
    # -----------------------------------------------------------------

    lines = []

    lines.append(
        "=" * 120
    )

    lines.append(
        "CMS MSSP WA-CONNECTED SETTLEMENT AMOUNTS PROFILE v0.1"
    )

    lines.append(
        "=" * 120
    )

    lines.append("")

    lines.append(
        "BOUNDARY"
    )

    lines.append(
        "-" * 120
    )

    lines.append(
        "Profiles EarnSaveLoss associated with the 132 certified WA-connected ACO-period observations."
    )

    lines.append(
        "WA organizational connection is NOT Washington payment-dollar incidence."
    )

    lines.append(
        "Positive EarnSaveLoss is NOT certified here as Washington federal inflow."
    )

    lines.append(
        "Negative EarnSaveLoss is NOT classified as negative federal spending."
    )

    lines.append(
        "No allocation, recoupment netting, cash-year inference, FFS-additivity conclusion, database write, or ledger inclusion."
    )

    lines.append("")

    # -----------------------------------------------------------------
    # SOURCE
    # -----------------------------------------------------------------

    lines.append(
        "SOURCE"
    )

    lines.append(
        "-" * 120
    )

    lines.append(
        str(
            PERFORMANCE_ZIP.relative_to(
                REPO_ROOT
            )
        )
    )

    lines.append(
        "Performance ZIP SHA-256: "
        + actual_performance_sha
    )

    lines.append(
        str(
            BRIDGE_CSV.relative_to(
                REPO_ROOT
            )
        )
    )

    lines.append(
        "Bridge SHA-256: "
        + bridge_sha
    )

    lines.append(
        str(
            CROSSWALK_XLSX.relative_to(
                REPO_ROOT
            )
        )
    )

    lines.append(
        "Crosswalk SHA-256: "
        + actual_crosswalk_sha
    )

    lines.append("")

    # -----------------------------------------------------------------
    # IDENTITY METHOD
    # -----------------------------------------------------------------

    lines.append(
        "IDENTITY METHOD"
    )

    lines.append(
        "-" * 120
    )

    lines.append(
        "2015: certified financial identifier treatment from frozen historical-linkage bridge."
    )

    lines.append(
        "2016-2017: financial ACO_Num -> official CMS crosswalk -> canonical ACO_ID."
    )

    lines.append(
        "2018-2024 including 2019A: direct ACO_ID."
    )

    lines.append("")

    # -----------------------------------------------------------------
    # PROFILE
    # -----------------------------------------------------------------

    lines.append(
        "WA-CONNECTED EARNED SHARED SAVINGS / LOSSES"
    )

    lines.append(
        "-" * 120
    )

    for row in period_profile:

        positive = Decimal(
            row[
                "positive_earn_save_loss"
            ]
        )

        negative = Decimal(
            row[
                "negative_earn_save_loss"
            ]
        )

        lines.append(
            f"{row['performance_period']:<6} | "
            f"connected={int(row['wa_connected_observations']):>3} | "
            f"positive={int(row['positive_count']):>3} "
            f"{money(positive):>20} | "
            f"negative={int(row['negative_count']):>3} "
            f"{money(negative):>20} | "
            f"zero={int(row['zero_count']):>3}"
        )

    lines.append(
        "-" * 120
    )

    lines.append(
        "TOTAL connected observations: "
        f"{len(joined_rows)}"
    )

    lines.append(
        "TOTAL positive observations: "
        f"{grand_positive_count}"
    )

    lines.append(
        "TOTAL positive EarnSaveLoss: "
        + money(
            grand_positive
        )
    )

    lines.append(
        "TOTAL negative observations: "
        f"{grand_negative_count}"
    )

    lines.append(
        "TOTAL negative EarnSaveLoss: "
        + money(
            grand_negative
        )
    )

    lines.append(
        "TOTAL zero observations: "
        f"{grand_zero_count}"
    )

    lines.append(
        "TOTAL nonnumeric observations: "
        f"{grand_nonnumeric_count}"
    )

    lines.append(
        "Arithmetic net control only: "
        + money(
            grand_positive
            + grand_negative
        )
    )

    lines.append("")

    # -----------------------------------------------------------------
    # CROSSWALK CERTIFICATION
    # -----------------------------------------------------------------

    lines.append(
        "2016-2017 CROSSWALK CERTIFICATION"
    )

    lines.append(
        "-" * 120
    )

    lines.append(
        "Official CMS unique ACO_Num mappings: "
        f"{len(crosswalk_forward)}"
    )

    lines.append(
        "2016-2017 certified bridge observations requiring crosswalk: "
        f"{crosswalk_bridge_rows}"
    )

    lines.append(
        "2016-2017 certified bridge observations joined through crosswalk: "
        f"{crosswalk_bridge_joined}"
    )

    lines.append("")

    # -----------------------------------------------------------------
    # CHECKS
    # -----------------------------------------------------------------

    lines.append(
        "CHECKS"
    )

    lines.append(
        "-" * 120
    )

    for row in checks:

        lines.append(
            f"{row['status']} | "
            f"{row['check']} | "
            f"{row['detail']}"
        )

    lines.append("")

    lines.append(
        "=" * 120
    )

    lines.append(
        "OVERALL CMS MSSP WA-CONNECTED SETTLEMENT AMOUNTS PROFILE v0.1: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )

    lines.append(
        "=" * 120
    )

    lines.append("")

    lines.append(
        "Interpretive boundary:"
    )

    lines.append(
        "  PASS certifies an exact financial-PUF join for the frozen 132-row WA organizational-connection bridge."
    )

    lines.append(
        "  Dollar amounts remain associated with WA-connected ACO observations, not certified Washington payment incidence."
    )

    lines.append(
        "  Positive EarnSaveLoss remains an additive-in-principle candidate pending economic-overlap reconciliation and payment-incidence evidence."
    )

    lines.append(
        "  Negative EarnSaveLoss remains a separate settlement concept and is not treated as negative federal spending."
    )

    lines.append(
        "  Performance year is not assumed to equal federal cash-payment year."
    )

    lines.append(
        "  No source is additive by default."
    )

    report = "\n".join(
        lines
    )

    REPORT_TXT.write_text(
        report,
        encoding="utf-8",
    )

    print(
        report
    )

    print("")

    print(
        "Evidence written:"
    )

    for path in [
        JOINED_CSV,
        PERIOD_PROFILE_CSV,
        CROSSWALK_DIAGNOSTIC_CSV,
        CHECKS_CSV,
        REPORT_TXT,
    ]:

        print(
            f"  {path.relative_to(REPO_ROOT)}"
        )

    return (
        0
        if overall_pass
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )