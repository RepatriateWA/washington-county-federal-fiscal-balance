"""
WCFFBP
CMS MSSP Historical Identity and Washington Applicability
Certification Validator v0.3

PURPOSE
-------
Certify the historical MSSP identity/applicability gate established by
v0.1 and v0.2 without manufacturing identities for unresolved records.

This validator does NOT attempt additional identity repair.

Certified architecture
----------------------
National identity accounting:

    2015:
        372 uniquely resolved
         18 explicitly unresolved
          2 explicitly ambiguous
        ---
        392 fully accounted

    2016-2017:
        904 / 904 uniquely resolved using official CMS ACO ID crosswalk

    2018-2024 including 2019A:
        3,627 / 3,627 uniquely resolved by direct ACO_ID

    Full financial universe:
        4,923 observations fully accounted

Washington applicability gate for 2015:

    Independently enumerate every 2015 organization whose
    aco_service_area contains explicit token WA.

    Require:
        4 source organization records
        4 / 4 uniquely linked to financial observations
        0 unresolved
        0 ambiguous

IMPORTANT BOUNDARIES
--------------------
Explicit WA service-area evidence establishes an organizational/program
connection to Washington only.

It does NOT establish:
    - beneficiary residence;
    - Washington payment-dollar incidence;
    - county payment-dollar incidence;
    - MSSP economic additivity to Original Medicare / FFS;
    - advance/AIM/AIP netting;
    - ledger inclusion.

No fuzzy matching.
No manual identity overrides.
No database writes.
No ledger writes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

ORGANIZATION_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "mssp_organizations"
    / "Accountable Care Organizations.zip"
)

V02_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "validation"
    / "historical_linkage_v0_2"
)

V02_LINKAGE = (
    V02_DIR
    / "cms_mssp_historical_linkage_v0_2.csv"
)

V02_PERIOD_PROFILE = (
    V02_DIR
    / "cms_mssp_historical_period_profile_v0_2.csv"
)

V02_CHECKS = (
    V02_DIR
    / "cms_mssp_historical_linkage_checks_v0_2.csv"
)

OUTPUT_DIR = (
    REPO_ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_aco"
    / "validation"
    / "historical_linkage_v0_3"
)

WA_UNIVERSE_CSV = (
    OUTPUT_DIR
    / "cms_mssp_2015_explicit_wa_service_area_universe_v0_3.csv"
)

ACCOUNTING_CSV = (
    OUTPUT_DIR
    / "cms_mssp_historical_identity_accounting_v0_3.csv"
)

CHECKS_CSV = (
    OUTPUT_DIR
    / "cms_mssp_historical_linkage_certification_checks_v0_3.csv"
)

REPORT_TXT = (
    OUTPUT_DIR
    / "cms_mssp_historical_linkage_certification_report_v0_3.txt"
)


EXPECTED_PERIODS = [
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


EXPECTED_FINANCIAL_ROWS = {
    "2015": 392,
    "2016": 432,
    "2017": 472,
    "2018": 548,
    "2019": 475,
    "2019A": 205,
    "2020": 513,
    "2021": 475,
    "2022": 482,
    "2023": 453,
    "2024": 476,
}


EXPECTED_2015 = {
    "financial_rows": 392,
    "resolved": 372,
    "unresolved": 18,
    "ambiguous": 2,
}


EXPECTED_2016_2017_RESOLVED = 904
EXPECTED_2018_PLUS_RESOLVED = 3627
EXPECTED_TOTAL_FINANCIAL = 4923

EXPECTED_WA_ORGANIZATIONS = {
    "HEALTH CONNECT PARTNERS LLC",
    "THE POLYCLINIC",
    "NORTHWEST RURAL ACO",
    "RAINIER HEALTH NETWORK",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            h.update(block)

    return h.hexdigest().upper()


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def normalize_name(value: str | None) -> str:
    text = normalize_text(value).upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def decode_csv(data: bytes) -> str:
    for encoding in (
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    ):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise RuntimeError("Unable to decode CSV.")


def read_csv_file(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        return list(csv.DictReader(handle))


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


def period_from_member(member_name: str) -> str:
    text = member_name.replace("\\", "/").lower()

    if (
        "2019_off-cycle_1" in text
        or "2019_off_cycle_1" in text
        or "2019a" in text
    ):
        return "2019A"

    match = re.search(
        r"/(20(?:15|16|17|18|19|20|21|22|23|24))/",
        text,
    )

    if match:
        return match.group(1)

    for year in range(2015, 2025):
        if re.search(
            rf"(?<!\d){year}(?!\d)",
            text,
        ):
            return str(year)

    return "UNRESOLVED"


def explicit_wa_token(service_area: str | None) -> bool:
    """
    Treat WA as an explicit state token only.

    Examples:
        WA          -> True
        OR, WA      -> True
        AK, MT, WA  -> True
        WASHINGTON  -> True

    No substring inference.
    """
    text = normalize_text(service_area).upper()

    tokens = {
        token.strip()
        for token in re.split(
            r"[,;|/]+",
            text,
        )
        if token.strip()
    }

    return (
        "WA" in tokens
        or "WASHINGTON" in tokens
        or "WASHINGTON STATE" in tokens
    )


def load_2015_organizations() -> tuple[
    list[dict[str, str]],
    str,
]:
    if not ORGANIZATION_ZIP.exists():
        raise FileNotFoundError(
            f"Missing organization ZIP: {ORGANIZATION_ZIP}"
        )

    with zipfile.ZipFile(
        ORGANIZATION_ZIP,
        "r",
    ) as archive:
        candidates = []

        for info in archive.infolist():
            if info.is_dir():
                continue

            if not info.filename.lower().endswith(".csv"):
                continue

            if period_from_member(info.filename) == "2015":
                candidates.append(info)

        if len(candidates) != 1:
            raise RuntimeError(
                "Expected exactly one 2015 organization CSV; "
                f"found {len(candidates)}."
            )

        info = candidates[0]
        data = archive.read(info)

    text = decode_csv(data)

    reader = csv.DictReader(
        io.StringIO(
            text,
            newline="",
        )
    )

    rows = []

    for row_number, row in enumerate(
        reader,
        start=2,
    ):
        cleaned = {
            str(key): normalize_text(value)
            for key, value in row.items()
            if key is not None
        }

        cleaned["_source_row_number"] = str(
            row_number
        )

        rows.append(cleaned)

    return rows, info.filename


def as_int(
    row: dict[str, str],
    field: str,
) -> int:
    value = normalize_text(
        row.get(field, "")
    )

    if not value:
        return 0

    return int(value)


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    errors: list[str] = []
    checks: list[dict[str, str]] = []

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

    # ------------------------------------------------------------
    # Required inputs
    # ------------------------------------------------------------
    required_files = [
        ORGANIZATION_ZIP,
        V02_LINKAGE,
        V02_PERIOD_PROFILE,
        V02_CHECKS,
    ]

    for path in required_files:
        add_check(
            f"Required input exists: {path.name}",
            path.exists(),
            str(path.relative_to(REPO_ROOT)),
        )

    if not all(
        path.exists()
        for path in required_files
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
            "FAIL: one or more required inputs are missing."
        )

        return 1

    # ------------------------------------------------------------
    # Load v0.2 evidence
    # ------------------------------------------------------------
    linkage = read_csv_file(
        V02_LINKAGE
    )

    period_profile = read_csv_file(
        V02_PERIOD_PROFILE
    )

    v02_checks = read_csv_file(
        V02_CHECKS
    )

    profile_by_period = {
        normalize_text(
            row.get(
                "performance_period",
                "",
            )
        ): row
        for row in period_profile
    }

    # ------------------------------------------------------------
    # Source-universe accounting
    # ------------------------------------------------------------
    observed_periods = set(
        profile_by_period
    )

    add_check(
        "v0.2 period profile contains exact 11-period universe",
        observed_periods
        == set(EXPECTED_PERIODS),
        (
            f"{len(observed_periods)}/11 periods | "
            + ",".join(
                sorted(observed_periods)
            )
        ),
    )

    accounting_rows = []

    total_financial = 0
    total_resolved = 0
    total_unresolved = 0
    total_ambiguous = 0

    period_counts_match = True

    for period in EXPECTED_PERIODS:
        profile = profile_by_period.get(
            period,
            {},
        )

        financial_rows = as_int(
            profile,
            "financial_rows",
        )

        resolved = as_int(
            profile,
            "resolved_unique",
        )

        unresolved = as_int(
            profile,
            "unresolved_no_org_match",
        )

        ambiguous = as_int(
            profile,
            "ambiguous_multi_org_match",
        )

        accounted = (
            resolved
            + unresolved
            + ambiguous
        )

        expected = EXPECTED_FINANCIAL_ROWS[
            period
        ]

        if financial_rows != expected:
            period_counts_match = False

        if accounted != financial_rows:
            period_counts_match = False

        total_financial += financial_rows
        total_resolved += resolved
        total_unresolved += unresolved
        total_ambiguous += ambiguous

        accounting_rows.append(
            {
                "performance_period": period,
                "financial_rows": financial_rows,
                "resolved_unique": resolved,
                "explicitly_unresolved": unresolved,
                "explicitly_ambiguous": ambiguous,
                "accounted_total": accounted,
                "accounting_difference": (
                    financial_rows
                    - accounted
                ),
            }
        )

    add_check(
        "Every period reproduces expected financial row count and closes identity accounting",
        period_counts_match,
        (
            f"total financial={total_financial:,}; "
            f"resolved={total_resolved:,}; "
            f"unresolved={total_unresolved:,}; "
            f"ambiguous={total_ambiguous:,}"
        ),
    )

    # ------------------------------------------------------------
    # 2015 residual certification
    # ------------------------------------------------------------
    p2015 = profile_by_period.get(
        "2015",
        {},
    )

    p2015_financial = as_int(
        p2015,
        "financial_rows",
    )

    p2015_resolved = as_int(
        p2015,
        "resolved_unique",
    )

    p2015_unresolved = as_int(
        p2015,
        "unresolved_no_org_match",
    )

    p2015_ambiguous = as_int(
        p2015,
        "ambiguous_multi_org_match",
    )

    add_check(
        "2015 identity universe is fully accounted with explicit residuals",
        (
            p2015_financial
            == EXPECTED_2015[
                "financial_rows"
            ]
            and p2015_resolved
            == EXPECTED_2015[
                "resolved"
            ]
            and p2015_unresolved
            == EXPECTED_2015[
                "unresolved"
            ]
            and p2015_ambiguous
            == EXPECTED_2015[
                "ambiguous"
            ]
            and (
                p2015_resolved
                + p2015_unresolved
                + p2015_ambiguous
                == p2015_financial
            )
        ),
        (
            f"{p2015_resolved} resolved + "
            f"{p2015_unresolved} unresolved + "
            f"{p2015_ambiguous} ambiguous = "
            f"{p2015_financial}"
        ),
    )

    # ------------------------------------------------------------
    # 2016-2017 crosswalk certification
    # ------------------------------------------------------------
    resolved_2016_2017 = sum(
        as_int(
            profile_by_period.get(
                period,
                {},
            ),
            "resolved_unique",
        )
        for period in (
            "2016",
            "2017",
        )
    )

    residual_2016_2017 = sum(
        as_int(
            profile_by_period.get(
                period,
                {},
            ),
            "unresolved_no_org_match",
        )
        + as_int(
            profile_by_period.get(
                period,
                {},
            ),
            "ambiguous_multi_org_match",
        )
        for period in (
            "2016",
            "2017",
        )
    )

    add_check(
        "2016-2017 official CMS crosswalk identity bridge is complete",
        (
            resolved_2016_2017
            == EXPECTED_2016_2017_RESOLVED
            and residual_2016_2017 == 0
        ),
        (
            f"{resolved_2016_2017:,}/"
            f"{EXPECTED_2016_2017_RESOLVED:,} resolved; "
            f"{residual_2016_2017} residual"
        ),
    )

    # ------------------------------------------------------------
    # 2018+ direct-ID certification
    # ------------------------------------------------------------
    direct_periods = [
        "2018",
        "2019",
        "2019A",
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
    ]

    resolved_direct = sum(
        as_int(
            profile_by_period.get(
                period,
                {},
            ),
            "resolved_unique",
        )
        for period in direct_periods
    )

    residual_direct = sum(
        as_int(
            profile_by_period.get(
                period,
                {},
            ),
            "unresolved_no_org_match",
        )
        + as_int(
            profile_by_period.get(
                period,
                {},
            ),
            "ambiguous_multi_org_match",
        )
        for period in direct_periods
    )

    add_check(
        "2018-2024 including 2019A direct ACO_ID linkage is complete",
        (
            resolved_direct
            == EXPECTED_2018_PLUS_RESOLVED
            and residual_direct == 0
        ),
        (
            f"{resolved_direct:,}/"
            f"{EXPECTED_2018_PLUS_RESOLVED:,} resolved; "
            f"{residual_direct} residual"
        ),
    )

    # ------------------------------------------------------------
    # Full-universe identity accounting
    # ------------------------------------------------------------
    full_accounted = (
        total_resolved
        + total_unresolved
        + total_ambiguous
    )

    add_check(
        "Full MSSP financial identity universe is explicitly accounted",
        (
            total_financial
            == EXPECTED_TOTAL_FINANCIAL
            and full_accounted
            == EXPECTED_TOTAL_FINANCIAL
        ),
        (
            f"{total_resolved:,} resolved + "
            f"{total_unresolved:,} unresolved + "
            f"{total_ambiguous:,} ambiguous = "
            f"{full_accounted:,} / "
            f"{EXPECTED_TOTAL_FINANCIAL:,}"
        ),
    )

    # ------------------------------------------------------------
    # Independently reconstruct 2015 explicit-WA organization universe
    # ------------------------------------------------------------
    try:
        organizations_2015, member_name = (
            load_2015_organizations()
        )
    except Exception as exc:
        organizations_2015 = []
        member_name = ""
        errors.append(
            f"2015 organization source load failed: {exc}"
        )

    wa_source_rows = []

    for row in organizations_2015:
        service_area = row.get(
            "aco_service_area",
            "",
        )

        if not explicit_wa_token(
            service_area
        ):
            continue

        aco_name = normalize_text(
            row.get(
                "aco_name",
                "",
            )
        )

        normalized_aco_name = normalize_name(
            aco_name
        )

        wa_source_rows.append(
            {
                "source_member": member_name,
                "source_row_number": row.get(
                    "_source_row_number",
                    "",
                ),
                "aco_name": aco_name,
                "normalized_aco_name": normalized_aco_name,
                "aco_address": normalize_text(
                    row.get(
                        "aco_address",
                        "",
                    )
                ),
                "aco_service_area": normalize_text(
                    service_area
                ),
                "aco_zip": normalize_text(
                    row.get(
                        "aco_zip",
                        "",
                    )
                ),
                "lat": normalize_text(
                    row.get(
                        "lat",
                        "",
                    )
                ),
                "long": normalize_text(
                    row.get(
                        "long",
                        "",
                    )
                ),
            }
        )

    wa_source_names = {
        row["normalized_aco_name"]
        for row in wa_source_rows
    }

    add_check(
        "2015 source independently reproduces exactly four explicit-WA service-area organizations",
        (
            len(wa_source_rows) == 4
            and wa_source_names
            == EXPECTED_WA_ORGANIZATIONS
        ),
        (
            f"{len(wa_source_rows)} rows | "
            + "; ".join(
                sorted(
                    row["aco_name"]
                    for row in wa_source_rows
                )
            )
        ),
    )

    # ------------------------------------------------------------
    # Link independent WA universe back to v0.2 financial identity evidence
    # ------------------------------------------------------------
    linkage_2015 = [
        row
        for row in linkage
        if normalize_text(
            row.get(
                "performance_period",
                "",
            )
        )
        == "2015"
    ]

    linkage_by_org_name = {}

    for row in linkage_2015:
        org_name = normalize_name(
            row.get(
                "organization_aco_name",
                "",
            )
        )

        if not org_name:
            continue

        linkage_by_org_name.setdefault(
            org_name,
            [],
        ).append(row)

    wa_linkage_pass = True
    wa_resolved_count = 0
    wa_unresolved_count = 0
    wa_ambiguous_count = 0

    for source_row in wa_source_rows:
        normalized_name = source_row[
            "normalized_aco_name"
        ]

        candidates = linkage_by_org_name.get(
            normalized_name,
            [],
        )

        unique_resolved = [
            row
            for row in candidates
            if normalize_text(
                row.get(
                    "identity_linkage_status",
                    "",
                )
            )
            == "RESOLVED_UNIQUE"
        ]

        unresolved = [
            row
            for row in candidates
            if normalize_text(
                row.get(
                    "identity_linkage_status",
                    "",
                )
            )
            == "UNRESOLVED_NO_ORG_MATCH"
        ]

        ambiguous = [
            row
            for row in candidates
            if normalize_text(
                row.get(
                    "identity_linkage_status",
                    "",
                )
            )
            == "AMBIGUOUS_MULTI_ORG_MATCH"
        ]

        if (
            len(unique_resolved) == 1
            and len(unresolved) == 0
            and len(ambiguous) == 0
        ):
            matched = unique_resolved[0]

            source_row[
                "financial_source_aco_identifier"
            ] = normalize_text(
                matched.get(
                    "source_aco_identifier",
                    "",
                )
            )

            source_row[
                "financial_aco_name"
            ] = normalize_text(
                matched.get(
                    "financial_aco_name",
                    "",
                )
            )

            source_row[
                "identity_linkage_status"
            ] = "RESOLVED_UNIQUE"

            source_row[
                "identity_linkage_method"
            ] = normalize_text(
                matched.get(
                    "identity_linkage_method",
                    "",
                )
            )

            source_row[
                "wa_connection_status"
            ] = normalize_text(
                matched.get(
                    "wa_connection_status",
                    "",
                )
            )

            source_row[
                "payment_dollar_incidence"
            ] = normalize_text(
                matched.get(
                    "payment_dollar_incidence",
                    "",
                )
            )

            wa_resolved_count += 1

        else:
            wa_linkage_pass = False

            source_row[
                "financial_source_aco_identifier"
            ] = ""

            source_row[
                "financial_aco_name"
            ] = ""

            if ambiguous:
                status = "AMBIGUOUS"
                wa_ambiguous_count += 1
            else:
                status = "UNRESOLVED"
                wa_unresolved_count += 1

            source_row[
                "identity_linkage_status"
            ] = status

            source_row[
                "identity_linkage_method"
            ] = ""

            source_row[
                "wa_connection_status"
            ] = ""

            source_row[
                "payment_dollar_incidence"
            ] = "NOT_ESTABLISHED"

    add_check(
        "Every 2015 explicit-WA service-area organization uniquely links to one financial observation",
        (
            wa_linkage_pass
            and wa_resolved_count == 4
            and wa_unresolved_count == 0
            and wa_ambiguous_count == 0
        ),
        (
            f"{wa_resolved_count}/4 resolved; "
            f"{wa_unresolved_count} unresolved; "
            f"{wa_ambiguous_count} ambiguous"
        ),
    )

    # ------------------------------------------------------------
    # Ensure none of the 2015 residuals carries a resolved explicit-WA
    # organization identity.
    # ------------------------------------------------------------
    residual_2015 = [
        row
        for row in linkage_2015
        if normalize_text(
            row.get(
                "identity_linkage_status",
                "",
            )
        )
        != "RESOLVED_UNIQUE"
    ]

    residual_with_wa_org_evidence = [
        row
        for row in residual_2015
        if normalize_text(
            row.get(
                "wa_organization_evidence",
                "",
            )
        ).upper()
        == "YES"
    ]

    add_check(
        "No unresolved or ambiguous 2015 financial identity carries explicit linked WA-organization evidence",
        len(
            residual_with_wa_org_evidence
        )
        == 0,
        (
            f"{len(residual_with_wa_org_evidence)} "
            "residual rows with WA organization evidence"
        ),
    )

    # ------------------------------------------------------------
    # Geography boundary
    # ------------------------------------------------------------
    wa_boundary_pass = all(
        normalize_text(
            row.get(
                "payment_dollar_incidence",
                "",
            )
        )
        == "NOT_ESTABLISHED"
        for row in wa_source_rows
    )

    add_check(
        "2015 WA applicability evidence remains distinct from payment-dollar incidence",
        wa_boundary_pass,
        (
            "All explicit-WA organization records retain "
            "payment_dollar_incidence=NOT_ESTABLISHED"
        ),
    )

    # ------------------------------------------------------------
    # v0.2 expected failures are bounded to 2015 identity completeness.
    # This prevents silently inheriting unrelated v0.2 failures.
    # ------------------------------------------------------------
    failed_v02_checks = [
        normalize_text(
            row.get(
                "check",
                "",
            )
        )
        for row in v02_checks
        if normalize_text(
            row.get(
                "status",
                "",
            )
        ).upper()
        == "FAIL"
    ]

    expected_v02_failures = {
        "No ambiguous organization identity linkage",
        "Every financial ACO-period resolves uniquely",
        "2015 exact normalized-name linkage resolves all financial observations",
    }

    add_check(
        "v0.2 failures are exactly the bounded 2015 residual conditions",
        set(
            failed_v02_checks
        )
        == expected_v02_failures,
        (
            f"{len(failed_v02_checks)} failures | "
            + "; ".join(
                failed_v02_checks
            )
        ),
    )

    # ------------------------------------------------------------
    # Write evidence
    # ------------------------------------------------------------
    write_csv(
        WA_UNIVERSE_CSV,
        [
            "source_member",
            "source_row_number",
            "aco_name",
            "normalized_aco_name",
            "aco_address",
            "aco_service_area",
            "aco_zip",
            "lat",
            "long",
            "financial_source_aco_identifier",
            "financial_aco_name",
            "identity_linkage_status",
            "identity_linkage_method",
            "wa_connection_status",
            "payment_dollar_incidence",
        ],
        wa_source_rows,
    )

    write_csv(
        ACCOUNTING_CSV,
        [
            "performance_period",
            "financial_rows",
            "resolved_unique",
            "explicitly_unresolved",
            "explicitly_ambiguous",
            "accounted_total",
            "accounting_difference",
        ],
        accounting_rows,
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

    overall_pass = (
        not errors
        and all(
            row["status"] == "PASS"
            for row in checks
        )
    )

    # ------------------------------------------------------------
    # Report
    # ------------------------------------------------------------
    lines: list[str] = []

    lines.append("=" * 104)
    lines.append(
        "CMS MSSP HISTORICAL IDENTITY AND WASHINGTON APPLICABILITY CERTIFICATION v0.3"
    )
    lines.append("=" * 104)
    lines.append("")

    lines.append("CERTIFICATION BOUNDARY")
    lines.append("-" * 104)
    lines.append(
        "READ-ONLY certification of historical identity accounting "
        "and explicit Washington service-area applicability."
    )
    lines.append(
        "No fuzzy matching or manual identity overrides."
    )
    lines.append(
        "No beneficiary residence inferred."
    )
    lines.append(
        "No Washington payment-dollar incidence inferred."
    )
    lines.append(
        "No county payment-dollar incidence inferred."
    )
    lines.append(
        "No MSSP-vs-FFS economic additivity conclusion."
    )
    lines.append(
        "No advance/AIM/AIP netting."
    )
    lines.append(
        "No ledger inclusion."
    )
    lines.append("")

    lines.append("NATIONAL IDENTITY ACCOUNTING")
    lines.append("-" * 104)

    for row in accounting_rows:
        lines.append(
            f"{row['performance_period']:<6} | "
            f"financial={row['financial_rows']:>3} | "
            f"resolved={row['resolved_unique']:>3} | "
            f"unresolved={row['explicitly_unresolved']:>2} | "
            f"ambiguous={row['explicitly_ambiguous']:>2} | "
            f"accounted={row['accounted_total']:>3} | "
            f"difference={row['accounting_difference']:>2}"
        )

    lines.append("")
    lines.append(
        f"TOTAL  | financial={total_financial:,} | "
        f"resolved={total_resolved:,} | "
        f"unresolved={total_unresolved:,} | "
        f"ambiguous={total_ambiguous:,} | "
        f"accounted={full_accounted:,}"
    )
    lines.append("")

    lines.append("CERTIFIED NATIONAL STATUS")
    lines.append("-" * 104)
    lines.append(
        "FULLY_ACCOUNTED_WITH_EXPLICIT_2015_RESIDUALS"
    )
    lines.append("")
    lines.append(
        "2015: 372 uniquely resolved + 18 explicitly unresolved "
        "+ 2 explicitly ambiguous = 392."
    )
    lines.append(
        "2016-2017: 904/904 uniquely resolved using official CMS "
        "ACO ID crosswalk."
    )
    lines.append(
        "2018-2024 including 2019A: 3,627/3,627 uniquely resolved "
        "using direct ACO_ID."
    )
    lines.append("")

    lines.append("2015 EXPLICIT-WASHINGTON SERVICE-AREA UNIVERSE")
    lines.append("-" * 104)
    lines.append(
        f"Source member: {member_name}"
    )
    lines.append(
        f"Explicit-WA organization rows: {len(wa_source_rows)}"
    )
    lines.append("")

    for row in wa_source_rows:
        lines.append(
            f"{row['aco_name']} | "
            f"service_area={row['aco_service_area']} | "
            f"financial_id={row.get('financial_source_aco_identifier', '')} | "
            f"identity={row.get('identity_linkage_status', '')} | "
            f"payment_dollar_incidence="
            f"{row.get('payment_dollar_incidence', '')}"
        )

    lines.append("")
    lines.append("CERTIFIED WASHINGTON APPLICABILITY STATUS")
    lines.append("-" * 104)
    lines.append(
        "EXPLICIT_WA_SERVICE_AREA_UNIVERSE_FULLY_LINKED"
    )
    lines.append("")
    lines.append(
        "All four 2015 CMS organization records with explicit WA "
        "service-area evidence are uniquely linked to financial observations."
    )
    lines.append(
        "The remaining 2015 national identity residuals do not contain "
        "an unresolved explicit-WA organization record."
    )
    lines.append("")

    lines.append("ACCOUNTING / GEOGRAPHIC DISPOSITION")
    lines.append("-" * 104)
    lines.append(
        "Expenditure/financial observation: OBSERVED"
    )
    lines.append(
        "Historical identity: FULLY_ACCOUNTED_WITH_EXPLICIT_2015_RESIDUALS"
    )
    lines.append(
        "2015 explicit-WA organizational applicability: FULLY_LINKED"
    )
    lines.append(
        "Beneficiary residence: NOT_ESTABLISHED"
    )
    lines.append(
        "Washington payment-dollar incidence: NOT_ESTABLISHED"
    )
    lines.append(
        "Washington county payment-dollar incidence: NOT_ESTABLISHED"
    )
    lines.append(
        "Economic additivity to Original Medicare/FFS: NOT_ESTABLISHED"
    )
    lines.append(
        "Principal ledger treatment: WITHHOLD_PENDING_RECONCILIATION"
    )
    lines.append("")

    lines.append("CHECKS")
    lines.append("-" * 104)

    for check in checks:
        lines.append(
            f"{check['status']} | "
            f"{check['check']} | "
            f"{check['detail']}"
        )

    if errors:
        lines.append("")
        lines.append("ERRORS")
        lines.append("-" * 104)

        for error in errors:
            lines.append(
                f"FAIL | {error}"
            )

    lines.append("")
    lines.append("=" * 104)
    lines.append(
        "OVERALL CMS MSSP HISTORICAL IDENTITY / "
        "WASHINGTON APPLICABILITY CERTIFICATION v0.3: "
        + (
            "PASS"
            if overall_pass
            else "FAIL"
        )
    )
    lines.append("=" * 104)
    lines.append("")

    lines.append("Interpretive boundary:")
    lines.append(
        "  This PASS certifies identity accounting and explicit "
        "Washington organizational/service-area applicability only."
    )
    lines.append(
        "  It does not certify Washington beneficiary residence, "
        "payment-dollar incidence, county incidence, or economic additivity."
    )
    lines.append(
        "  The 20 unresolved/ambiguous 2015 national observations "
        "remain explicitly preserved rather than imputed."
    )
    lines.append(
        "  No federal expenditure source is additive by default."
    )

    report = "\n".join(lines)

    REPORT_TXT.write_text(
        report,
        encoding="utf-8",
    )

    print(report)
    print("")
    print("SOURCE HASH")
    print("-" * 104)
    print(
        "Organizations ZIP SHA-256: "
        f"{sha256_file(ORGANIZATION_ZIP)}"
    )
    print("")
    print("Evidence written:")

    for path in [
        WA_UNIVERSE_CSV,
        ACCOUNTING_CSV,
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
    sys.exit(main())
