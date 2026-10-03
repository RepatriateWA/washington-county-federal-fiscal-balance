"""
WCFFBP
CMS MSSP Historical Linkage and Washington Applicability Profiler v0.1

READ-ONLY.

Purpose
-------
Certify historical linkage among:
    1. MSSP Performance Year Financial and Quality Results
    2. MSSP Accountable Care Organizations
    3. MSSP ACO Participants

for the common analytical universe:
    2015-2019, 2019A, 2020-2024.

The profiler also identifies contemporaneous Washington organizational
and participant evidence and attaches selected financial-accounting
fields WITHOUT treating those observations as Washington payment-dollar
incidence.

This profiler DOES:
    - open the three preserved CMS ZIPs directly;
    - require the same 11-period universe in all three;
    - hash every embedded CSV;
    - profile schemas and row counts;
    - identify ACO identifier fields by period/source;
    - test direct historical linkage;
    - inventory organization and participant geography fields;
    - identify Washington organizational evidence;
    - identify Washington participant evidence;
    - attach selected MSSP financial fields to linked ACO-periods;
    - preserve 2019 and 2019A separately;
    - write reproducible validation evidence.

This profiler DOES NOT:
    - infer beneficiary residence from ACO location;
    - infer payment-dollar incidence from organization/participant geography;
    - allocate payments to Washington or counties;
    - aggregate MSSP dollars as Washington inflow;
    - determine economic additivity versus Original Medicare/FFS;
    - net advance/AIM/AIP amounts;
    - write to PostgreSQL;
    - authorize ledger inclusion.

Fail-closed principle
---------------------
A financial ACO-period must resolve to zero or one contemporaneous
organization identity. One-to-many organization identity linkage is a
certification failure.

Washington organizational or participant evidence establishes only a
Washington CONNECTION. It does not establish Washington beneficiary
payment-dollar incidence.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

FINANCIAL_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_performance_results"
    / "Performance Year Financial and Quality Results.zip"
)

ORGANIZATION_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_organizations"
    / "Accountable Care Organizations.zip"
)

PARTICIPANT_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_participants"
    / "Accountable Care Organization Participants.zip"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "validation"
    / "historical_linkage_v0_1"
)

SOURCE_INVENTORY_CSV = (
    OUTPUT_DIR / "cms_mssp_historical_source_inventory_v0_1.csv"
)

SCHEMA_CSV = (
    OUTPUT_DIR / "cms_mssp_historical_schema_v0_1.csv"
)

PERIOD_PROFILE_CSV = (
    OUTPUT_DIR / "cms_mssp_historical_period_profile_v0_1.csv"
)

LINKAGE_CSV = (
    OUTPUT_DIR / "cms_mssp_historical_linkage_v0_1.csv"
)

WA_CANDIDATES_CSV = (
    OUTPUT_DIR / "cms_mssp_washington_connection_candidates_v0_1.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR / "cms_mssp_historical_linkage_checks_v0_1.csv"
)

REPORT_TXT = (
    OUTPUT_DIR / "cms_mssp_historical_linkage_report_v0_1.txt"
)


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


FINANCIAL_FIELDS = [
    "EarnSaveLoss",
    "GenSaveLoss",
    "ABtotExp",
    "ABtotBnchmk",
    "Adv_Pay",
    "AIM",
    "Adv_Pay_Amt",
    "Adv_Pay_Recoup",
    "AIP",
    "AIPBalance",
    "AIPRecoup",
    "AIPOwe",
]


ID_CANDIDATES = [
    "ACO_ID",
    "ACO_Num",
    "ACO_NUM",
    "ACO ID",
    "ACO Number",
    "ACO_Number",
]


NAME_CANDIDATES = [
    "ACO_Name",
    "ACO Name",
    "ACO_NAME",
    "Name",
]


# Geography candidates are deliberately broad for discovery.
# Washington classification below uses explicit values, not field names alone.
ORG_GEO_PATTERNS = [
    r"state",
    r"address",
    r"city",
    r"zip",
    r"service",
    r"county",
]

PARTICIPANT_GEO_PATTERNS = [
    r"state",
    r"address",
    r"city",
    r"zip",
    r"county",
]


WA_VALUES = {
    "WA",
    "WASHINGTON",
    "WASHINGTON STATE",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalized_upper(value: str | None) -> str:
    return normalize_text(value).upper()


def decode_csv(data: bytes) -> str:
    for encoding in [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    ]:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise RuntimeError("Unable to decode CSV.")


def read_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = decode_csv(data)

    reader = csv.DictReader(
        io.StringIO(text, newline="")
    )

    headers = reader.fieldnames or []

    rows = []

    for row in reader:
        rows.append(
            {
                str(key): normalize_text(value)
                for key, value in row.items()
                if key is not None
            }
        )

    return headers, rows


def period_from_member(member_name: str) -> str:
    text = member_name.replace("\\", "/").lower()

    if (
        "2019_off-cycle_1" in text
        or "2019_off_cycle_1" in text
        or "2019a" in text
    ):
        return "2019A"

    # Directory-based period is preferred.
    match = re.search(r"/(20(?:15|16|17|18|19|20|21|22|23|24))/", text)

    if match:
        return match.group(1)

    # Fallback to filename.
    for year in range(2015, 2025):
        if re.search(rf"(?<!\d){year}(?!\d)", text):
            return str(year)

    return "UNRESOLVED"


def find_header(
    headers: list[str],
    candidates: list[str],
) -> str | None:
    normalized = {
        normalize_header(header): header
        for header in headers
    }

    for candidate in candidates:
        key = normalize_header(candidate)

        if key in normalized:
            return normalized[key]

    return None


def geo_headers(
    headers: list[str],
    patterns: list[str],
) -> list[str]:
    result = []

    for header in headers:
        normalized = header.lower()

        if any(
            re.search(pattern, normalized)
            for pattern in patterns
        ):
            result.append(header)

    return result


def is_explicit_wa_value(value: str | None) -> bool:
    text = normalized_upper(value)

    if text in WA_VALUES:
        return True

    # Some fields may contain a delimited list of states.
    tokens = {
        token.strip()
        for token in re.split(r"[,;|/]+", text)
        if token.strip()
    }

    if "WA" in tokens or "WASHINGTON" in tokens:
        return True

    return False


def washington_evidence(
    row: dict[str, str],
    geography_headers: list[str],
) -> tuple[bool, str]:
    evidence = []

    for header in geography_headers:
        value = row.get(header, "")

        if is_explicit_wa_value(value):
            evidence.append(
                f"{header}={value}"
            )

    return (
        bool(evidence),
        "; ".join(evidence),
    )


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


def load_source_zip(
    source_name: str,
    zip_path: Path,
) -> tuple[
    dict[str, dict],
    list[dict],
    list[dict],
    list[str],
]:
    """
    Return:
        period_data
        source_inventory_rows
        schema_rows
        errors
    """

    period_data: dict[str, dict] = {}
    inventory_rows = []
    schema_rows = []
    errors = []

    if not zip_path.exists():
        errors.append(
            f"{source_name}: ZIP not found: {zip_path}"
        )

        return (
            period_data,
            inventory_rows,
            schema_rows,
            errors,
        )

    with zipfile.ZipFile(zip_path, "r") as archive:
        csv_members = [
            info
            for info in archive.infolist()
            if (
                not info.is_dir()
                and info.filename.lower().endswith(".csv")
            )
        ]

        for info in csv_members:
            period = period_from_member(
                info.filename
            )

            data = archive.read(info)
            digest = sha256_bytes(data)

            try:
                headers, rows = read_csv(data)
                parse_status = "PASS"
            except Exception as exc:
                headers = []
                rows = []
                parse_status = "FAIL"

                errors.append(
                    f"{source_name} {info.filename}: "
                    f"CSV parse failure: {exc}"
                )

            inventory_rows.append(
                {
                    "source": source_name,
                    "performance_period": period,
                    "member_name": info.filename,
                    "member_bytes": len(data),
                    "sha256": digest,
                    "row_count": len(rows),
                    "column_count": len(headers),
                    "parse_status": parse_status,
                }
            )

            for position, header in enumerate(
                headers,
                start=1,
            ):
                schema_rows.append(
                    {
                        "source": source_name,
                        "performance_period": period,
                        "column_position": position,
                        "field_name": header,
                    }
                )

            if period == "UNRESOLVED":
                errors.append(
                    f"{source_name}: unresolved period for "
                    f"{info.filename}"
                )
                continue

            if period in period_data:
                errors.append(
                    f"{source_name}: duplicate CSV period "
                    f"{period}"
                )
                continue

            period_data[period] = {
                "member_name": info.filename,
                "sha256": digest,
                "headers": headers,
                "rows": rows,
            }

    return (
        period_data,
        inventory_rows,
        schema_rows,
        errors,
    )


def canonical_id_value(
    row: dict[str, str],
    id_header: str | None,
) -> str:
    if id_header is None:
        return ""

    return normalize_text(
        row.get(id_header, "")
    )


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_errors = []

    (
        financial,
        financial_inventory,
        financial_schema,
        errors,
    ) = load_source_zip(
        "FINANCIAL",
        FINANCIAL_ZIP,
    )

    all_errors.extend(errors)

    (
        organizations,
        organization_inventory,
        organization_schema,
        errors,
    ) = load_source_zip(
        "ORGANIZATION",
        ORGANIZATION_ZIP,
    )

    all_errors.extend(errors)

    (
        participants,
        participant_inventory,
        participant_schema,
        errors,
    ) = load_source_zip(
        "PARTICIPANT",
        PARTICIPANT_ZIP,
    )

    all_errors.extend(errors)

    source_inventory_rows = (
        financial_inventory
        + organization_inventory
        + participant_inventory
    )

    schema_rows = (
        financial_schema
        + organization_schema
        + participant_schema
    )

    period_profile_rows = []
    linkage_rows = []
    wa_candidate_rows = []

    one_to_many_org_links = 0
    unresolved_financial_org_links = 0

    total_financial_rows = 0
    total_financial_linked_org = 0

    total_org_aco_periods = 0
    total_org_with_participants = 0

    # ------------------------------------------------------------
    # Period-by-period historical linkage.
    # ------------------------------------------------------------
    for period in PERIODS:
        fin = financial.get(period)
        org = organizations.get(period)
        part = participants.get(period)

        if not fin or not org or not part:
            continue

        fin_headers = fin["headers"]
        org_headers = org["headers"]
        part_headers = part["headers"]

        fin_id_header = find_header(
            fin_headers,
            ID_CANDIDATES,
        )

        org_id_header = find_header(
            org_headers,
            ID_CANDIDATES,
        )

        part_id_header = find_header(
            part_headers,
            ID_CANDIDATES,
        )

        fin_name_header = find_header(
            fin_headers,
            NAME_CANDIDATES,
        )

        org_name_header = find_header(
            org_headers,
            NAME_CANDIDATES,
        )

        part_name_header = find_header(
            part_headers,
            NAME_CANDIDATES,
        )

        org_geo_headers = geo_headers(
            org_headers,
            ORG_GEO_PATTERNS,
        )

        part_geo_headers = geo_headers(
            part_headers,
            PARTICIPANT_GEO_PATTERNS,
        )

        if not fin_id_header:
            all_errors.append(
                f"{period}: no financial ACO identifier field"
            )

        if not org_id_header:
            all_errors.append(
                f"{period}: no organization ACO identifier field"
            )

        if not part_id_header:
            all_errors.append(
                f"{period}: no participant ACO identifier field"
            )

        # Build organization index.
        org_index: dict[
            str,
            list[dict[str, str]],
        ] = defaultdict(list)

        for row in org["rows"]:
            key = canonical_id_value(
                row,
                org_id_header,
            )

            if key:
                org_index[key].append(row)

        # Build participant index.
        participant_index: dict[
            str,
            list[dict[str, str]],
        ] = defaultdict(list)

        for row in part["rows"]:
            key = canonical_id_value(
                row,
                part_id_header,
            )

            if key:
                participant_index[key].append(row)

        period_financial_rows = len(
            fin["rows"]
        )

        period_linked_org = 0
        period_unresolved_org = 0
        period_one_to_many = 0
        period_wa_org = 0
        period_wa_participant = 0
        period_wa_either = 0
        period_wa_both = 0

        total_financial_rows += (
            period_financial_rows
        )

        total_org_aco_periods += len(
            org_index
        )

        for fin_row_number, fin_row in enumerate(
            fin["rows"],
            start=2,
        ):
            aco_id = canonical_id_value(
                fin_row,
                fin_id_header,
            )

            aco_name = (
                normalize_text(
                    fin_row.get(
                        fin_name_header,
                        "",
                    )
                )
                if fin_name_header
                else ""
            )

            org_matches = (
                org_index.get(
                    aco_id,
                    [],
                )
                if aco_id
                else []
            )

            if len(org_matches) == 1:
                organization_link_status = (
                    "EXACT_ONE"
                )

                period_linked_org += 1
                total_financial_linked_org += 1

            elif len(org_matches) == 0:
                organization_link_status = (
                    "NO_MATCH"
                )

                period_unresolved_org += 1
                unresolved_financial_org_links += 1

            else:
                organization_link_status = (
                    "ONE_TO_MANY"
                )

                period_one_to_many += 1
                one_to_many_org_links += 1

            org_row = (
                org_matches[0]
                if len(org_matches) == 1
                else {}
            )

            org_name = (
                normalize_text(
                    org_row.get(
                        org_name_header,
                        "",
                    )
                )
                if (
                    org_row
                    and org_name_header
                )
                else ""
            )

            (
                wa_org,
                wa_org_evidence,
            ) = washington_evidence(
                org_row,
                org_geo_headers,
            )

            participant_rows = (
                participant_index.get(
                    aco_id,
                    [],
                )
                if aco_id
                else []
            )

            participant_evidence = []
            wa_participant_count = 0

            for participant_row in participant_rows:
                (
                    is_wa,
                    evidence,
                ) = washington_evidence(
                    participant_row,
                    part_geo_headers,
                )

                if is_wa:
                    wa_participant_count += 1

                    if evidence:
                        participant_evidence.append(
                            evidence
                        )

            wa_participant = (
                wa_participant_count > 0
            )

            if participant_rows:
                total_org_with_participants += 1

            if wa_org:
                period_wa_org += 1

            if wa_participant:
                period_wa_participant += 1

            if wa_org or wa_participant:
                period_wa_either += 1

            if wa_org and wa_participant:
                period_wa_both += 1

            if wa_org and wa_participant:
                wa_connection_status = (
                    "WA_ORGANIZATION_AND_PARTICIPANT"
                )

            elif wa_org:
                wa_connection_status = (
                    "WA_ORGANIZATION_ONLY"
                )

            elif wa_participant:
                wa_connection_status = (
                    "WA_PARTICIPANT_ONLY"
                )

            else:
                wa_connection_status = (
                    "NO_DIRECT_WA_CONNECTION_OBSERVED"
                )

            output_row = {
                "performance_period": period,
                "financial_row_number": fin_row_number,
                "aco_id": aco_id,
                "financial_aco_name": aco_name,
                "organization_link_status": (
                    organization_link_status
                ),
                "organization_match_count": (
                    len(org_matches)
                ),
                "organization_aco_name": org_name,
                "participant_row_count": (
                    len(participant_rows)
                ),
                "wa_organization_evidence": (
                    "YES" if wa_org else "NO"
                ),
                "wa_organization_evidence_detail": (
                    wa_org_evidence
                ),
                "wa_participant_evidence": (
                    "YES"
                    if wa_participant
                    else "NO"
                ),
                "wa_participant_row_count": (
                    wa_participant_count
                ),
                "wa_participant_evidence_detail": (
                    " || ".join(
                        sorted(
                            set(
                                participant_evidence
                            )
                        )
                    )
                ),
                "wa_connection_status": (
                    wa_connection_status
                ),
                "geographic_interpretation": (
                    "ORGANIZATIONAL_OR_PARTICIPANT_CONNECTION_ONLY"
                ),
                "payment_dollar_incidence": (
                    "NOT_ESTABLISHED"
                ),
            }

            for field_name in FINANCIAL_FIELDS:
                output_row[field_name] = (
                    fin_row.get(
                        field_name,
                        ""
                    )
                )

            linkage_rows.append(
                output_row
            )

            if wa_org or wa_participant:
                wa_candidate_rows.append(
                    dict(output_row)
                )

        period_profile_rows.append(
            {
                "performance_period": period,
                "financial_rows": (
                    period_financial_rows
                ),
                "organization_rows": (
                    len(org["rows"])
                ),
                "participant_rows": (
                    len(part["rows"])
                ),
                "financial_id_field": (
                    fin_id_header or ""
                ),
                "organization_id_field": (
                    org_id_header or ""
                ),
                "participant_id_field": (
                    part_id_header or ""
                ),
                "financial_name_field": (
                    fin_name_header or ""
                ),
                "organization_name_field": (
                    org_name_header or ""
                ),
                "participant_name_field": (
                    part_name_header or ""
                ),
                "organization_geography_fields": (
                    ";".join(
                        org_geo_headers
                    )
                ),
                "participant_geography_fields": (
                    ";".join(
                        part_geo_headers
                    )
                ),
                "financial_exact_one_org_links": (
                    period_linked_org
                ),
                "financial_no_org_match": (
                    period_unresolved_org
                ),
                "financial_one_to_many_org_match": (
                    period_one_to_many
                ),
                "wa_organization_aco_periods": (
                    period_wa_org
                ),
                "wa_participant_aco_periods": (
                    period_wa_participant
                ),
                "wa_either_aco_periods": (
                    period_wa_either
                ),
                "wa_both_aco_periods": (
                    period_wa_both
                ),
            }
        )

    # ------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------
    checks = []

    def add_check(
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

    required_periods = set(
        PERIODS
    )

    add_check(
        "Financial source has exact 11-period universe",
        set(financial) == required_periods,
        (
            f"{len(financial)}/11 periods: "
            + ",".join(financial.keys())
        ),
    )

    add_check(
        "Organization source has exact 11-period universe",
        set(organizations) == required_periods,
        (
            f"{len(organizations)}/11 periods: "
            + ",".join(organizations.keys())
        ),
    )

    add_check(
        "Participant source has exact 11-period universe",
        set(participants) == required_periods,
        (
            f"{len(participants)}/11 periods: "
            + ",".join(participants.keys())
        ),
    )

    add_check(
        "All embedded source CSVs parse",
        all(
            row["parse_status"] == "PASS"
            for row in source_inventory_rows
        ),
        (
            f"{sum(row['parse_status'] != 'PASS' for row in source_inventory_rows)} "
            "parse failures"
        ),
    )

    add_check(
        "All periods expose financial ACO identifier",
        all(
            row[
                "financial_id_field"
            ]
            for row in period_profile_rows
        ),
        (
            f"{sum(not row['financial_id_field'] for row in period_profile_rows)} "
            "missing"
        ),
    )

    add_check(
        "All periods expose organization ACO identifier",
        all(
            row[
                "organization_id_field"
            ]
            for row in period_profile_rows
        ),
        (
            f"{sum(not row['organization_id_field'] for row in period_profile_rows)} "
            "missing"
        ),
    )

    add_check(
        "All periods expose participant ACO identifier",
        all(
            row[
                "participant_id_field"
            ]
            for row in period_profile_rows
        ),
        (
            f"{sum(not row['participant_id_field'] for row in period_profile_rows)} "
            "missing"
        ),
    )

    add_check(
        "No financial ACO-period links one-to-many to organizations",
        one_to_many_org_links == 0,
        (
            f"{one_to_many_org_links} "
            "one-to-many financial->organization links"
        ),
    )

    # NO_MATCH is not automatically a certification failure at this
    # discovery stage because identifier generations may require the
    # separately acquired CMS ACO ID crosswalk.  It is explicitly
    # surfaced for the next gate.
    add_check(
        "Financial-to-organization linkage profiled without silent fallback",
        True,
        (
            f"{total_financial_linked_org:,}/"
            f"{total_financial_rows:,} exact direct links; "
            f"{unresolved_financial_org_links:,} unresolved direct links"
        ),
    )

    add_check(
        "Washington candidates retain payment-dollar-incidence boundary",
        all(
            row[
                "payment_dollar_incidence"
            ] == "NOT_ESTABLISHED"
            for row in wa_candidate_rows
        ),
        (
            f"{len(wa_candidate_rows):,} "
            "WA-connected ACO-period candidates"
        ),
    )

    add_check(
        "No Washington candidate is promoted to ledger treatment",
        all(
            row[
                "geographic_interpretation"
            ]
            == "ORGANIZATIONAL_OR_PARTICIPANT_CONNECTION_ONLY"
            for row in wa_candidate_rows
        ),
        "No beneficiary/payment-dollar geography inferred",
    )

    # ------------------------------------------------------------
    # Write evidence
    # ------------------------------------------------------------
    write_csv(
        SOURCE_INVENTORY_CSV,
        [
            "source",
            "performance_period",
            "member_name",
            "member_bytes",
            "sha256",
            "row_count",
            "column_count",
            "parse_status",
        ],
        source_inventory_rows,
    )

    write_csv(
        SCHEMA_CSV,
        [
            "source",
            "performance_period",
            "column_position",
            "field_name",
        ],
        schema_rows,
    )

    write_csv(
        PERIOD_PROFILE_CSV,
        [
            "performance_period",
            "financial_rows",
            "organization_rows",
            "participant_rows",
            "financial_id_field",
            "organization_id_field",
            "participant_id_field",
            "financial_name_field",
            "organization_name_field",
            "participant_name_field",
            "organization_geography_fields",
            "participant_geography_fields",
            "financial_exact_one_org_links",
            "financial_no_org_match",
            "financial_one_to_many_org_match",
            "wa_organization_aco_periods",
            "wa_participant_aco_periods",
            "wa_either_aco_periods",
            "wa_both_aco_periods",
        ],
        period_profile_rows,
    )

    linkage_fields = [
        "performance_period",
        "financial_row_number",
        "aco_id",
        "financial_aco_name",
        "organization_link_status",
        "organization_match_count",
        "organization_aco_name",
        "participant_row_count",
        "wa_organization_evidence",
        "wa_organization_evidence_detail",
        "wa_participant_evidence",
        "wa_participant_row_count",
        "wa_participant_evidence_detail",
        "wa_connection_status",
        "geographic_interpretation",
        "payment_dollar_incidence",
    ] + FINANCIAL_FIELDS

    write_csv(
        LINKAGE_CSV,
        linkage_fields,
        linkage_rows,
    )

    write_csv(
        WA_CANDIDATES_CSV,
        linkage_fields,
        wa_candidate_rows,
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

    # ------------------------------------------------------------
    # Report
    # ------------------------------------------------------------
    overall_pass = (
        not all_errors
        and all(
            check["status"] == "PASS"
            for check in checks
        )
    )

    lines = []

    lines.append("=" * 100)
    lines.append(
        "CMS MSSP HISTORICAL LINKAGE AND WASHINGTON APPLICABILITY PROFILE v0.1"
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("BOUNDARY")
    lines.append("-" * 100)
    lines.append("READ-ONLY historical linkage/applicability profiling.")
    lines.append("No Washington payment-dollar incidence inferred.")
    lines.append("No beneficiary residence inferred.")
    lines.append("No MSSP dollar aggregation as Washington inflow.")
    lines.append("No FFS overlap/additivity conclusion.")
    lines.append("No advance/AIM/AIP netting.")
    lines.append("No database writes.")
    lines.append("No ledger inclusion.")
    lines.append("")

    lines.append("SOURCE UNIVERSE")
    lines.append("-" * 100)

    for source_name, source_data in [
        ("FINANCIAL", financial),
        ("ORGANIZATION", organizations),
        ("PARTICIPANT", participants),
    ]:
        lines.append(
            f"{source_name:<14} "
            f"periods={len(source_data)} | "
            + ",".join(source_data.keys())
        )

    lines.append("")

    lines.append("PERIOD PROFILE")
    lines.append("-" * 100)

    for row in period_profile_rows:
        lines.append(
            f"{row['performance_period']:<6} | "
            f"financial={row['financial_rows']:,} | "
            f"organizations={row['organization_rows']:,} | "
            f"participants={row['participant_rows']:,} | "
            f"IDs={row['financial_id_field']}/"
            f"{row['organization_id_field']}/"
            f"{row['participant_id_field']}"
        )

        lines.append(
            f"       linkage exact={row['financial_exact_one_org_links']:,} | "
            f"no_match={row['financial_no_org_match']:,} | "
            f"one_to_many={row['financial_one_to_many_org_match']:,}"
        )

        lines.append(
            f"       WA org={row['wa_organization_aco_periods']:,} | "
            f"WA participant={row['wa_participant_aco_periods']:,} | "
            f"either={row['wa_either_aco_periods']:,} | "
            f"both={row['wa_both_aco_periods']:,}"
        )

        lines.append(
            f"       org_geo_fields="
            f"{row['organization_geography_fields'] or 'NONE'}"
        )

        lines.append(
            f"       participant_geo_fields="
            f"{row['participant_geography_fields'] or 'NONE'}"
        )

    lines.append("")

    lines.append("WASHINGTON-CONNECTED FINANCIAL OBSERVATIONS")
    lines.append("-" * 100)
    lines.append(
        f"Candidate ACO-period observations: {len(wa_candidate_rows):,}"
    )

    status_counts = Counter(
        row["wa_connection_status"]
        for row in wa_candidate_rows
    )

    for status, count in sorted(
        status_counts.items()
    ):
        lines.append(
            f"{status:<40} {count:>6,}"
        )

    lines.append("")

    lines.append(
        "NOTE: Financial values below are attached source observations."
    )

    lines.append(
        "They are NOT certified Washington payment-dollar incidence."
    )

    for row in wa_candidate_rows:
        lines.append(
            f"{row['performance_period']} | "
            f"{row['aco_id']} | "
            f"{row['financial_aco_name']} | "
            f"{row['wa_connection_status']} | "
            f"EarnSaveLoss={row.get('EarnSaveLoss', '')} | "
            f"Adv_Pay_Recoup={row.get('Adv_Pay_Recoup', '')} | "
            f"AIPRecoup={row.get('AIPRecoup', '')}"
        )

    lines.append("")

    lines.append("CHECKS")
    lines.append("-" * 100)

    for check in checks:
        lines.append(
            f"{check['status']} | "
            f"{check['check']} | "
            f"{check['detail']}"
        )

    if all_errors:
        lines.append("")
        lines.append("ERRORS")
        lines.append("-" * 100)

        for error in all_errors:
            lines.append(
                f"FAIL | {error}"
            )

    lines.append("")
    lines.append("=" * 100)
    lines.append(
        "OVERALL CMS MSSP HISTORICAL LINKAGE PROFILE v0.1: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )
    lines.append("=" * 100)
    lines.append("")

    lines.append("Interpretive boundary:")
    lines.append(
        "  Washington organization or participant evidence establishes "
        "a historical Washington connection only."
    )
    lines.append(
        "  It does not establish beneficiary residence or Washington "
        "payment-dollar incidence."
    )
    lines.append(
        "  EarnSaveLoss and other financial values remain attached "
        "source observations pending separate geographic and "
        "economic-overlap certification."
    )
    lines.append(
        "  Direct identifier nonmatches are surfaced rather than "
        "silently repaired. The separately acquired CMS ACO ID "
        "crosswalk may be used in a subsequent linkage gate."
    )
    lines.append(
        "  One-to-many financial-to-organization identity linkage is "
        "a certification failure."
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

    print(report)
    print("")
    print("Evidence written:")

    for path in [
        SOURCE_INVENTORY_CSV,
        SCHEMA_CSV,
        PERIOD_PROFILE_CSV,
        LINKAGE_CSV,
        WA_CANDIDATES_CSV,
        CHECKS_CSV,
        REPORT_TXT,
    ]:
        print(
            f"  {path.relative_to(REPO_ROOT)}"
        )

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
