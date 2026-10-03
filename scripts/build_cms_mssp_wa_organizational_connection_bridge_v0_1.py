"""
WCFFBP
CMS MSSP Washington Organizational Connection Bridge v0.1
Attempt 2

PURPOSE
-------
Create a machine-readable bridge between MSSP financial observations
and the Washington organizational-connection universe previously
certified by historical linkage v0.3.

The bridge is deliberately narrow:

    performance period
        +
    financial ACO identifier
        +
    Washington organizational-connection evidence

It contains NO settlement dollars.

CERTIFIED HISTORICAL-LINKAGE RULES REPRODUCED
----------------------------------------------
2015
    - Exact normalized ACO name only.
    - No fuzzy matching.
    - Washington applicability is independently established from the
      organization source by exact WA token in aco_service_area.
    - The four explicit-WA organization rows must all uniquely link.

2016-2017
    - Financial ACO_Num -> official CMS ACO ID crosswalk -> ACO_ID.
    - Washington organizational connection is independently determined
      from organization and/or participant source evidence.

2018-2024, including 2019A
    - Direct ACO_ID linkage.
    - 2019A remains an independent CMS performance period.

SOURCE DECODING POLICY
----------------------
CSV members are decoded deterministically using the first successful
strict encoding from:

    utf-8-sig
    utf-8
    cp1252
    latin-1

No undecodable byte is silently replaced or ignored.

The successful encoding for every CSV member is written to the
source-encoding inventory.

GEOGRAPHIC BOUNDARY
-------------------
A bridge row means only:

    ORGANIZATIONAL_CONNECTION_ONLY_NOT_PAYMENT_INCIDENCE

It does NOT establish:
    - beneficiary residence;
    - provider-service incidence;
    - Washington payment-dollar incidence;
    - county payment-dollar incidence;
    - economic additivity;
    - cash timing;
    - principal-ledger inclusion.

No settlement amount is written to this bridge.
No source is additive by default.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import unicodedata
import zipfile

from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]


# =====================================================================
# PRESERVED SOURCES
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

ORGANIZATIONS_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_organizations"
    / "Accountable Care Organizations.zip"
)

PARTICIPANTS_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_participants"
    / "Accountable Care Organization Participants.zip"
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


# =====================================================================
# EXPECTED SOURCE HASHES
# =====================================================================

EXPECTED_PERFORMANCE_SHA = (
    "C7555FA4849ADCA9AB4ECACAC607715F3B6BAA2DDA5CE4D422CA8668B1A9F128"
)

EXPECTED_ORGANIZATIONS_SHA = (
    "157BAF296573BC1D18AC1E0DE10121855508D6C919CC11188C3892A094D16259"
)

EXPECTED_PARTICIPANTS_SHA = (
    "B2E45C33A2F6D9DB4D3A5FEF8C9D6E0BEE8F75A37666202E4268E0E08F689BAF"
)

EXPECTED_CROSSWALK_SHA = (
    "0996CC8DC0C15961FB99012734F236B656F4CA935D4D4B793EDB11F281B244F4"
)


# =====================================================================
# OUTPUTS
# =====================================================================

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "validation"
    / "wa_organizational_connection_bridge_v0_1"
)

BRIDGE_CSV = (
    OUTPUT_DIR
    / "cms_mssp_wa_organizational_connection_bridge_v0_1.csv"
)

PERIOD_ACCOUNTING_CSV = (
    OUTPUT_DIR
    / "cms_mssp_wa_organizational_connection_period_accounting_v0_1.csv"
)

ENCODING_INVENTORY_CSV = (
    OUTPUT_DIR
    / "cms_mssp_wa_organizational_connection_source_encoding_inventory_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_wa_organizational_connection_bridge_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_mssp_wa_organizational_connection_bridge_report_v0_1.txt"
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


# =====================================================================
# FROZEN v0.3 WA ORGANIZATIONAL-CONNECTION TARGETS
# =====================================================================

EXPECTED_WA_COUNTS = {
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

EXPECTED_WA_TOTAL = 132

EXPECTED_2015_EXPLICIT_WA = {
    "A17898",
    "A64316",
    "A65906",
    "A78337",
}


# =====================================================================
# ENCODING POLICY
# =====================================================================

ENCODING_CANDIDATES = [
    "utf-8-sig",
    "utf-8",
    "cp1252",
    "latin-1",
]


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
        writer.writerows(rows)


def normalize_name(value) -> str:
    """
    Conservative exact-name normalization.

    No fuzzy matching.
    """
    if value is None:
        return ""

    text = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    text = text.casefold()

    text = text.replace(
        "&",
        " and ",
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def clean_identifier(value) -> str:
    if value is None:
        return ""

    text = str(value).strip()

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


def normalize_aco_id(value) -> str:
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
            + text.zfill(5)
        )

    return text


def exact_wa_token(value) -> bool:
    """
    Exact WA token in a list-like state/service-area field.

    Does not search arbitrary substrings.
    """
    if value is None:
        return False

    text = str(value).upper()

    tokens = [
        token.strip()
        for token in re.split(
            r"[,;|]",
            text,
        )
    ]

    return "WA" in tokens


def infer_period(
    member_name: str,
) -> str:
    text = member_name.replace(
        "\\",
        "/",
    ).lower()

    if (
        "2019_off-cycle_1"
        in text
        or "2019_off_cycle_1"
        in text
        or "2019a"
        in text
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
            return str(year)

    return "UNRESOLVED"


def choose_column(
    columns: list[str],
    candidates: list[str],
) -> str | None:
    lower_map = {
        str(column).casefold(): column
        for column in columns
    }

    for candidate in candidates:
        actual = lower_map.get(
            candidate.casefold()
        )

        if actual is not None:
            return actual

    return None


# =====================================================================
# STRICT DECODING
# =====================================================================

def decode_csv_bytes(
    raw: bytes,
) -> tuple[str, str]:
    """
    Decode a CSV member using the first successful strict encoding.

    No errors='replace'.
    No errors='ignore'.
    """
    failures = []

    for encoding in ENCODING_CANDIDATES:
        try:
            text = raw.decode(
                encoding,
                errors="strict",
            )

            return (
                text,
                encoding,
            )

        except UnicodeDecodeError as exc:
            failures.append(
                f"{encoding}: {exc}"
            )

    raise UnicodeDecodeError(
        "unknown",
        raw,
        0,
        min(
            len(raw),
            1,
        ),
        "No configured strict encoding succeeded: "
        + " | ".join(
            failures
        ),
    )


def dataframe_from_csv_bytes(
    raw: bytes,
) -> tuple[pd.DataFrame, str]:
    text, encoding = decode_csv_bytes(
        raw
    )

    df = pd.read_csv(
        io.StringIO(
            text
        ),
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    return (
        df,
        encoding,
    )


# =====================================================================
# ZIP CSV READER
# =====================================================================

def read_csv_members(
    archive_path: Path,
    source_label: str,
    encoding_inventory: list[dict],
) -> dict[str, dict]:
    result = {}

    with zipfile.ZipFile(
        archive_path,
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
                    "Multiple CSV members inferred for "
                    f"{period} in {archive_path.name}: "
                    f"{result[period]['member_name']} "
                    f"and {info.filename}"
                )

            raw = archive.read(
                info
            )

            df, encoding = (
                dataframe_from_csv_bytes(
                    raw
                )
            )

            encoding_inventory.append(
                {
                    "source_label": source_label,
                    "archive_path": str(
                        archive_path.relative_to(
                            REPO_ROOT
                        )
                    ),
                    "performance_period": period,
                    "member_name": info.filename,
                    "member_bytes": len(
                        raw
                    ),
                    "encoding": encoding,
                    "rows": len(
                        df
                    ),
                    "columns": len(
                        df.columns
                    ),
                }
            )

            result[
                period
            ] = {
                "member_name": info.filename,
                "encoding": encoding,
                "df": df,
            }

    return result


# =====================================================================
# CROSSWALK
# =====================================================================

def load_crosswalk() -> tuple[
    dict[str, str],
    int,
]:
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
            "Could not identify ACO_ID / ACO_NUM columns "
            "in official CMS crosswalk."
        )

    mapping = {}

    for _, row in df.iterrows():

        aco_id = normalize_aco_id(
            row[
                id_col
            ]
        )

        aco_num = clean_identifier(
            row[
                num_col
            ]
        )

        if (
            not aco_id
            or not aco_num
        ):
            continue

        if (
            aco_num in mapping
            and mapping[
                aco_num
            ]
            != aco_id
        ):
            raise RuntimeError(
                "Crosswalk ACO_NUM maps to multiple "
                f"ACO_ID values: {aco_num}"
            )

        mapping[
            aco_num
        ] = aco_id

    return (
        mapping,
        len(mapping),
    )


# =====================================================================
# 2015 EXPLICIT-WA LINKAGE
# =====================================================================

def build_2015_explicit_wa_financial_links(
    financial_df: pd.DataFrame,
    organization_df: pd.DataFrame,
) -> list[dict]:
    """
    Reproduce the frozen v0.3 2015 rule:

        explicit WA service-area organization
            ->
        exact normalized name
            ->
        unique financial observation

    No fuzzy matching.
    No participant evidence is asserted here.
    """
    financial_name_col = choose_column(
        list(
            financial_df.columns
        ),
        [
            "ACO_Name",
            "ACO Name",
        ],
    )

    financial_id_col = choose_column(
        list(
            financial_df.columns
        ),
        [
            "ACO_Num",
            "ACO_NUM",
            "ACO_ID",
        ],
    )

    organization_name_col = choose_column(
        list(
            organization_df.columns
        ),
        [
            "aco_name",
            "ACO Name",
            "ACO Legal or Name/Doing Business As",
        ],
    )

    service_area_col = choose_column(
        list(
            organization_df.columns
        ),
        [
            "aco_service_area",
            "ACO Service Area",
        ],
    )

    if financial_name_col is None:
        raise RuntimeError(
            "2015 financial ACO name column not found."
        )

    if financial_id_col is None:
        raise RuntimeError(
            "2015 financial identifier column not found."
        )

    if organization_name_col is None:
        raise RuntimeError(
            "2015 organization ACO name column not found."
        )

    if service_area_col is None:
        raise RuntimeError(
            "2015 organization service-area column not found."
        )

    # Identify explicit-WA organization rows first.
    explicit_wa_org_rows = []

    for org_index, row in organization_df.iterrows():

        if not exact_wa_token(
            row[
                service_area_col
            ]
        ):
            continue

        name_key = normalize_name(
            row[
                organization_name_col
            ]
        )

        if not name_key:
            continue

        explicit_wa_org_rows.append(
            {
                "org_index": org_index,
                "name_key": name_key,
                "aco_name": row[
                    organization_name_col
                ],
            }
        )

    # Financial rows indexed by normalized exact name.
    financial_by_name = defaultdict(
        list
    )

    for financial_index, row in financial_df.iterrows():

        name_key = normalize_name(
            row[
                financial_name_col
            ]
        )

        if not name_key:
            continue

        financial_by_name[
            name_key
        ].append(
            financial_index
        )

    links = []

    for org in explicit_wa_org_rows:

        matches = financial_by_name.get(
            org[
                "name_key"
            ],
            [],
        )

        if len(matches) != 1:
            # Do not force ambiguous/unresolved linkage.
            continue

        financial_index = matches[
            0
        ]

        financial_row = financial_df.loc[
            financial_index
        ]

        financial_id = normalize_aco_id(
            financial_row[
                financial_id_col
            ]
        )

        if not financial_id:
            continue

        links.append(
            {
                "financial_index": financial_index,
                "financial_aco_identifier": financial_id,
                "aco_name": financial_row[
                    financial_name_col
                ],
            }
        )

    return links


# =====================================================================
# WA ORGANIZATION EVIDENCE
# =====================================================================

def organization_wa_ids(
    df: pd.DataFrame,
) -> set[str]:
    """
    Return ACO IDs carrying explicit WA service-area evidence.

    No address-only inference.
    """
    columns = list(
        df.columns
    )

    id_col = choose_column(
        columns,
        [
            "ACO_ID",
            "ACO ID",
            "aco_id",
        ],
    )

    service_area_col = choose_column(
        columns,
        [
            "aco_service_area",
            "ACO Service Area",
            "ACO_Service_Area",
        ],
    )

    if (
        id_col is None
        or service_area_col is None
    ):
        return set()

    result = set()

    for _, row in df.iterrows():

        if not exact_wa_token(
            row[
                service_area_col
            ]
        ):
            continue

        aco_id = normalize_aco_id(
            row[
                id_col
            ]
        )

        if aco_id:
            result.add(
                aco_id
            )

    return result


# =====================================================================
# WA PARTICIPANT EVIDENCE
# =====================================================================

def participant_wa_ids(
    df: pd.DataFrame,
) -> set[str]:
    """
    Identify participant-source WA evidence only where the participant
    source itself exposes an explicit state/service-area field.

    No address parsing.
    No organization-name inference.
    """
    columns = list(
        df.columns
    )

    id_col = choose_column(
        columns,
        [
            "ACO_ID",
            "ACO_Num",
            "ACO_NUM",
            "ACO ID",
        ],
    )

    state_col = choose_column(
        columns,
        [
            "State",
            "state",
            "Participant State",
            "participant_state",
            "ACO Service Area",
            "aco_service_area",
        ],
    )

    if (
        id_col is None
        or state_col is None
    ):
        return set()

    result = set()

    for _, row in df.iterrows():

        raw_state = str(
            row[
                state_col
            ]
        ).strip().upper()

        is_wa = (
            raw_state == "WA"
            or raw_state == "WASHINGTON"
            or exact_wa_token(
                raw_state
            )
        )

        if not is_wa:
            continue

        aco_id = normalize_aco_id(
            row[
                id_col
            ]
        )

        if aco_id:
            result.add(
                aco_id
            )

    return result


# =====================================================================
# MAIN
# =====================================================================

def main() -> int:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    checks = []
    encoding_inventory = []

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
    # SOURCE PROVENANCE
    # -----------------------------------------------------------------

    sources = [
        (
            "Performance results",
            PERFORMANCE_ZIP,
            EXPECTED_PERFORMANCE_SHA,
        ),
        (
            "Organizations",
            ORGANIZATIONS_ZIP,
            EXPECTED_ORGANIZATIONS_SHA,
        ),
        (
            "Participants",
            PARTICIPANTS_ZIP,
            EXPECTED_PARTICIPANTS_SHA,
        ),
        (
            "ACO ID crosswalk",
            CROSSWALK_XLSX,
            EXPECTED_CROSSWALK_SHA,
        ),
    ]

    source_hashes = {}

    for (
        label,
        path,
        expected_sha,
    ) in sources:

        exists = path.exists()

        check(
            f"{label} source exists",
            exists,
            str(
                path.relative_to(
                    REPO_ROOT
                )
            ),
        )

        if not exists:
            continue

        actual_sha = sha256_file(
            path
        )

        source_hashes[
            label
        ] = actual_sha

        check(
            f"{label} SHA-256 matches preserved acquisition",
            actual_sha
            == expected_sha,
            actual_sha,
        )

    if not all(
        path.exists()
        for _, path, _
        in sources
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
            "FAIL: one or more required preserved sources are missing."
        )

        return 1

    # -----------------------------------------------------------------
    # READ SOURCE UNIVERSES WITH STRICT ENCODING INVENTORY
    # -----------------------------------------------------------------

    financial = read_csv_members(
        PERFORMANCE_ZIP,
        "Performance results",
        encoding_inventory,
    )

    organizations = read_csv_members(
        ORGANIZATIONS_ZIP,
        "Organizations",
        encoding_inventory,
    )

    participants = read_csv_members(
        PARTICIPANTS_ZIP,
        "Participants",
        encoding_inventory,
    )

    crosswalk, crosswalk_count = (
        load_crosswalk()
    )

    check(
        "Financial source reproduces exact 11-period universe",
        set(
            financial
        )
        == set(
            PERIODS
        ),
        ",".join(
            financial.keys()
        ),
    )

    check(
        "Organization source reproduces exact 11-period universe",
        set(
            organizations
        )
        == set(
            PERIODS
        ),
        ",".join(
            organizations.keys()
        ),
    )

    check(
        "Participant source reproduces exact 11-period universe",
        set(
            participants
        )
        == set(
            PERIODS
        ),
        ",".join(
            participants.keys()
        ),
    )

    check(
        "Official ACO ID crosswalk reproduces 767 unique mappings",
        crosswalk_count
        == 767,
        str(
            crosswalk_count
        ),
    )

    # -----------------------------------------------------------------
    # ENCODING ACCOUNTING
    # -----------------------------------------------------------------

    expected_csv_members = (
        len(financial)
        + len(organizations)
        + len(participants)
    )

    check(
        "Every consumed CSV member has an explicit successful encoding",
        len(
            encoding_inventory
        )
        == expected_csv_members
        and all(
            row[
                "encoding"
            ]
            in ENCODING_CANDIDATES
            for row in encoding_inventory
        ),
        (
            f"{len(encoding_inventory)}/"
            f"{expected_csv_members}"
        ),
    )

    # -----------------------------------------------------------------
    # BUILD BRIDGE
    # -----------------------------------------------------------------

    bridge_rows = []
    period_accounting = []

    for period in PERIODS:

        fin_df = financial[
            period
        ][
            "df"
        ]

        org_df = organizations[
            period
        ][
            "df"
        ]

        part_df = participants[
            period
        ][
            "df"
        ]

        # =============================================================
        # 2015
        # =============================================================

        if period == "2015":

            links_2015 = (
                build_2015_explicit_wa_financial_links(
                    fin_df,
                    org_df,
                )
            )

            observed_ids = {
                row[
                    "financial_aco_identifier"
                ]
                for row in links_2015
            }

            check(
                "2015 explicit-WA exact-name universe reproduces four certified financial IDs",
                observed_ids
                == EXPECTED_2015_EXPLICIT_WA,
                ",".join(
                    sorted(
                        observed_ids
                    )
                ),
            )

            for row in links_2015:

                bridge_rows.append(
                    {
                        "performance_period": "2015",
                        "financial_aco_identifier": row[
                            "financial_aco_identifier"
                        ],
                        "aco_name": row[
                            "aco_name"
                        ],
                        "identity_method": "EXACT_NORMALIZED_NAME",
                        "organization_wa_evidence": "YES",
                        "participant_wa_evidence": "NOT_EVALUATED",
                        "connection_class": "ORGANIZATION_ONLY",
                        "geographic_status": (
                            "ORGANIZATIONAL_CONNECTION_ONLY_"
                            "NOT_PAYMENT_INCIDENCE"
                        ),
                    }
                )

            period_accounting.append(
                {
                    "performance_period": "2015",
                    "wa_connected_rows": len(
                        links_2015
                    ),
                    "organization_only": len(
                        links_2015
                    ),
                    "participant_only": 0,
                    "organization_and_participant": 0,
                    "expected_v0_3": EXPECTED_WA_COUNTS[
                        "2015"
                    ],
                }
            )

            continue

        # =============================================================
        # 2016+
        # =============================================================

        org_ids = organization_wa_ids(
            org_df
        )

        participant_ids = participant_wa_ids(
            part_df
        )

        fin_id_col = choose_column(
            list(
                fin_df.columns
            ),
            [
                "ACO_ID",
                "ACO_Num",
                "ACO_NUM",
            ],
        )

        name_col = choose_column(
            list(
                fin_df.columns
            ),
            [
                "ACO_Name",
                "ACO Name",
            ],
        )

        if fin_id_col is None:
            raise RuntimeError(
                f"{period}: financial identifier column not found."
            )

        seen = set()

        org_only = 0
        participant_only = 0
        both = 0

        for _, row in fin_df.iterrows():

            raw_fin_id = clean_identifier(
                row[
                    fin_id_col
                ]
            )

            if not raw_fin_id:
                continue

            # ---------------------------------------------------------
            # 2016-2017 official crosswalk
            # ---------------------------------------------------------

            if period in {
                "2016",
                "2017",
            }:

                canonical_id = crosswalk.get(
                    raw_fin_id,
                    "",
                )

                identity_method = (
                    "OFFICIAL_CMS_ACO_ID_CROSSWALK"
                )

            # ---------------------------------------------------------
            # 2018+ direct ACO_ID
            # ---------------------------------------------------------

            else:

                canonical_id = normalize_aco_id(
                    raw_fin_id
                )

                identity_method = (
                    "DIRECT_ACO_ID"
                )

            if not canonical_id:
                continue

            org_evidence = (
                canonical_id
                in org_ids
            )

            participant_evidence = (
                canonical_id
                in participant_ids
            )

            if not (
                org_evidence
                or participant_evidence
            ):
                continue

            key = (
                period,
                canonical_id,
            )

            if key in seen:
                raise RuntimeError(
                    "Duplicate bridge key encountered: "
                    f"{key}"
                )

            seen.add(
                key
            )

            if (
                org_evidence
                and participant_evidence
            ):

                connection_class = (
                    "ORG_AND_PARTICIPANT"
                )

                both += 1

            elif org_evidence:

                connection_class = (
                    "ORGANIZATION_ONLY"
                )

                org_only += 1

            else:

                connection_class = (
                    "PARTICIPANT_ONLY"
                )

                participant_only += 1

            bridge_rows.append(
                {
                    "performance_period": period,
                    "financial_aco_identifier": canonical_id,
                    "aco_name": (
                        row[
                            name_col
                        ]
                        if name_col
                        else ""
                    ),
                    "identity_method": identity_method,
                    "organization_wa_evidence": (
                        "YES"
                        if org_evidence
                        else "NO"
                    ),
                    "participant_wa_evidence": (
                        "YES"
                        if participant_evidence
                        else "NO"
                    ),
                    "connection_class": connection_class,
                    "geographic_status": (
                        "ORGANIZATIONAL_CONNECTION_ONLY_"
                        "NOT_PAYMENT_INCIDENCE"
                    ),
                }
            )

        count = (
            org_only
            + participant_only
            + both
        )

        period_accounting.append(
            {
                "performance_period": period,
                "wa_connected_rows": count,
                "organization_only": org_only,
                "participant_only": participant_only,
                "organization_and_participant": both,
                "expected_v0_3": EXPECTED_WA_COUNTS[
                    period
                ],
            }
        )

    # -----------------------------------------------------------------
    # CERTIFICATION CHECKS
    # -----------------------------------------------------------------

    observed_counts = Counter(
        row[
            "performance_period"
        ]
        for row in bridge_rows
    )

    for period in PERIODS:

        observed = observed_counts[
            period
        ]

        expected = EXPECTED_WA_COUNTS[
            period
        ]

        check(
            f"{period} WA organizational-connection count reproduces frozen v0.3",
            observed
            == expected,
            f"{observed}/{expected}",
        )

    check(
        "Total WA organizational-connection observations reproduce frozen v0.3",
        len(
            bridge_rows
        )
        == EXPECTED_WA_TOTAL,
        (
            f"{len(bridge_rows)}/"
            f"{EXPECTED_WA_TOTAL}"
        ),
    )

    bridge_keys = [
        (
            row[
                "performance_period"
            ],
            row[
                "financial_aco_identifier"
            ],
        )
        for row in bridge_rows
    ]

    check(
        "Bridge has zero duplicate period + financial identifier keys",
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
        "Every bridge row preserves non-incidence geographic boundary",
        all(
            row[
                "geographic_status"
            ]
            == expected_geo_status
            for row in bridge_rows
        ),
        (
            f"{len(bridge_rows)}/"
            f"{len(bridge_rows)}"
        ),
    )

    prohibited_dollar_tokens = [
        "earnsaveloss",
        "gensaveloss",
        "payment_amount",
        "payment_dollar",
        "recoup",
        "aipbalance",
        "aipowe",
        "amount",
        "dollars",
    ]

    bridge_columns = (
        list(
            bridge_rows[
                0
            ].keys()
        )
        if bridge_rows
        else []
    )

    dollar_columns = [
        column
        for column in bridge_columns
        if any(
            token in column.casefold()
            for token in prohibited_dollar_tokens
        )
    ]

    check(
        "Bridge contains no settlement-dollar fields",
        not dollar_columns,
        (
            "identity/geographic evidence only"
            if not dollar_columns
            else ",".join(
                dollar_columns
            )
        ),
    )

    # -----------------------------------------------------------------
    # SORT OUTPUTS
    # -----------------------------------------------------------------

    bridge_rows.sort(
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

    period_accounting.sort(
        key=lambda row: PERIODS.index(
            row[
                "performance_period"
            ]
        )
    )

    encoding_inventory.sort(
        key=lambda row: (
            row[
                "source_label"
            ],
            PERIODS.index(
                row[
                    "performance_period"
                ]
            ),
        )
    )

    # -----------------------------------------------------------------
    # WRITE ARTIFACTS
    # -----------------------------------------------------------------

    write_csv(
        BRIDGE_CSV,
        [
            "performance_period",
            "financial_aco_identifier",
            "aco_name",
            "identity_method",
            "organization_wa_evidence",
            "participant_wa_evidence",
            "connection_class",
            "geographic_status",
        ],
        bridge_rows,
    )

    write_csv(
        PERIOD_ACCOUNTING_CSV,
        [
            "performance_period",
            "wa_connected_rows",
            "organization_only",
            "participant_only",
            "organization_and_participant",
            "expected_v0_3",
        ],
        period_accounting,
    )

    write_csv(
        ENCODING_INVENTORY_CSV,
        [
            "source_label",
            "archive_path",
            "performance_period",
            "member_name",
            "member_bytes",
            "encoding",
            "rows",
            "columns",
        ],
        encoding_inventory,
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
        "CMS MSSP WASHINGTON ORGANIZATIONAL CONNECTION BRIDGE v0.1"
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
        "Machine-readable bridge reproducing the Washington organizational-connection universe certified by historical linkage v0.3."
    )

    lines.append(
        "NO settlement dollars are contained in this bridge."
    )

    lines.append(
        "ACO organizational connection is NOT Washington payment-dollar incidence."
    )

    lines.append(
        "No beneficiary residence inferred."
    )

    lines.append(
        "No county incidence inferred."
    )

    lines.append(
        "No economic additivity inferred."
    )

    lines.append(
        "No cash timing inferred."
    )

    lines.append(
        "No ledger inclusion."
    )

    lines.append("")

    # -----------------------------------------------------------------
    # SOURCE PROVENANCE
    # -----------------------------------------------------------------

    lines.append(
        "SOURCE PROVENANCE"
    )

    lines.append(
        "-" * 120
    )

    for (
        label,
        path,
        _,
    ) in sources:

        lines.append(
            f"{label}: "
            f"{path.relative_to(REPO_ROOT)}"
        )

        if label in source_hashes:

            lines.append(
                "  SHA-256: "
                + source_hashes[
                    label
                ]
            )

    lines.append("")

    # -----------------------------------------------------------------
    # ENCODING INVENTORY
    # -----------------------------------------------------------------

    lines.append(
        "SOURCE CSV ENCODING INVENTORY"
    )

    lines.append(
        "-" * 120
    )

    encoding_counts = Counter(
        row[
            "encoding"
        ]
        for row in encoding_inventory
    )

    for encoding in ENCODING_CANDIDATES:

        count = encoding_counts.get(
            encoding,
            0,
        )

        if count:

            lines.append(
                f"{encoding:<12} | "
                f"{count:>3} CSV members"
            )

    lines.append("")

    for row in encoding_inventory:

        lines.append(
            f"{row['source_label']:<20} | "
            f"{row['performance_period']:<6} | "
            f"{row['encoding']:<10} | "
            f"rows={row['rows']:<6} | "
            f"{row['member_name']}"
        )

    lines.append("")

    # -----------------------------------------------------------------
    # PERIOD ACCOUNTING
    # -----------------------------------------------------------------

    lines.append(
        "PERIOD ACCOUNTING"
    )

    lines.append(
        "-" * 120
    )

    for row in period_accounting:

        lines.append(
            f"{row['performance_period']:<6} | "
            f"connected={row['wa_connected_rows']:>3} | "
            f"org_only={row['organization_only']:>3} | "
            f"participant_only={row['participant_only']:>3} | "
            f"both={row['organization_and_participant']:>3} | "
            f"expected_v0_3={row['expected_v0_3']:>3}"
        )

    lines.append(
        "-" * 120
    )

    lines.append(
        f"TOTAL | connected={len(bridge_rows)} | "
        f"expected_v0_3={EXPECTED_WA_TOTAL}"
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
        "OVERALL CMS MSSP WASHINGTON ORGANIZATIONAL CONNECTION BRIDGE v0.1: "
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
        "  PASS means this bridge reproduces the frozen v0.3 Washington organizational-connection universe."
    )

    lines.append(
        "  A bridge row establishes organizational connection only."
    )

    lines.append(
        "  It does not establish that the ACO's settlement dollars economically accrued to Washington."
    )

    lines.append(
        "  It does not establish beneficiary residence, county incidence, cash timing, or ledger inclusion."
    )

    lines.append(
        "  2015 participant evidence is NOT asserted by this bridge unless independently demonstrated."
    )

    lines.append(
        "  Source CSV encodings are explicitly inventoried; no undecodable bytes are silently replaced."
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
        BRIDGE_CSV,
        PERIOD_ACCOUNTING_CSV,
        ENCODING_INVENTORY_CSV,
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