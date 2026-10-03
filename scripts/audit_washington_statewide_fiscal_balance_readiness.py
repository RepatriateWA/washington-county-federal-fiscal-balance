"""
Washington Statewide Federal Fiscal Balance Readiness Audit v0.2
================================================================

Purpose
-------
Inventory the project's current ability to construct a Washington State
federal fiscal balance and produce a preliminary statewide accounting view
from already certified or provisionally usable state-level streams.

This script implements two project rules:

    1. State completeness first; county precision later.
    2. Show the preliminary number as soon as it is defensible,
       not only when it is perfect.

The script is deliberately read-only.

It does NOT:
    * write to the database;
    * create or alter views;
    * authorize a final ledger;
    * convert calendar-year measures to federal fiscal years;
    * annualize incomplete Medicare 2024 Part C / Part D values;
    * impute missing dollars;
    * add unresolved USAspending obligations to authoritative program controls;
    * treat IRS Washington gross collections as a final economic-incidence model;
    * claim that the preliminary accounting difference is a certified final
      Washington federal fiscal balance.

The preliminary accounting view uses:

OUTFLOW / WORKING RECEIPTS CONTROL
    * IRS Washington gross collections.

INFLOW / INCLUDE_PRELIMINARY
    * SSA/OASDI annualized December benefits;
    * certified Medicare core:
          Original Medicare + Part C + Part D;
    * Medicaid federal expenditures;
    * CHIP federal expenditures;
    * VA GDX expenditures;
    * OMB-controlled civilian federal wage allocation;
    * OMB-controlled military federal wage allocation.

WITHHOLD_UNRESOLVED
    * USAspending assistance residual;
    * USAspending procurement residual;
    * Medicare Retiree Drug Subsidy (RDS);
    * Medicare MFFS.

EXCLUDE_DUPLICATE
    * Medicare Shared Savings Program (MSSP) EarnSaveLoss.

REFERENCE_ONLY
    * Rockefeller Institute balance-of-payments evidence
      (not queried by this script).

Methodological principle
------------------------
Measure first. Explain later.

A source receives an additional plus sign only when it represents an
economically distinct federal expenditure stream relative to the preferred
accounting sources already included.

The preliminary annual difference retains the project's existing sign
convention:

    preliminary_net_federal_outflow
        = IRS gross collections
        - identified federal inflows

Positive values therefore indicate that the working receipts control exceeds
the identified federal inflow subtotal.

Because the included streams mix federal fiscal year, calendar year, and
annualized-December measures, the resulting difference is an accounting
readiness measure, not a timing-harmonized final balance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from etl.db import get_connection


AUDIT_VERSION = "WA-STATEWIDE-FISCAL-BALANCE-READINESS-v0.2"

STUDY_START_YEAR = 2015
STUDY_END_YEAR = 2024
STUDY_YEARS = tuple(range(STUDY_START_YEAR, STUDY_END_YEAR + 1))

INCLUDE_PRELIMINARY = "INCLUDE_PRELIMINARY"
WITHHOLD_UNRESOLVED = "WITHHOLD_UNRESOLVED"
EXCLUDE_DUPLICATE = "EXCLUDE_DUPLICATE"
REFERENCE_ONLY = "REFERENCE_ONLY"

VALID_TREATMENTS = {
    INCLUDE_PRELIMINARY,
    WITHHOLD_UNRESOLVED,
    EXCLUDE_DUPLICATE,
    REFERENCE_ONLY,
}

ZERO = Decimal("0")


@dataclass
class StreamAudit:
    stream: str
    side: str
    source: str
    years_available: set[int] = field(default_factory=set)
    annual_amounts: dict[int, Decimal] = field(default_factory=dict)
    amount_measure: str = "UNKNOWN"
    time_basis: str = "UNKNOWN"
    geography: str = "WASHINGTON_STATE"
    state_control_available: str = "UNKNOWN"
    county_detail_available: str = "NOT_REQUIRED_FOR_STATE_READINESS"
    source_policy: str = "NONE"
    overlap_status: str = "UNRESOLVED"
    preliminary_treatment: str = WITHHOLD_UNRESOLVED
    limitation: str = ""
    observations: Optional[int] = None
    amount_total: Optional[Decimal] = None
    completeness_by_year: dict[int, str] = field(default_factory=dict)

    def year_span(self) -> str:
        if not self.years_available:
            return "NONE"

        years = sorted(self.years_available)

        if years == list(range(years[0], years[-1] + 1)):
            return f"{years[0]}-{years[-1]}"

        return ",".join(str(year) for year in years)

    def study_year_coverage(self) -> str:
        present = len(set(STUDY_YEARS) & self.years_available)
        return f"{present}/{len(STUDY_YEARS)}"

    def validate(self) -> None:
        if self.preliminary_treatment not in VALID_TREATMENTS:
            raise ValueError(
                f"{self.stream}: invalid preliminary treatment "
                f"{self.preliminary_treatment!r}"
            )

        if self.side not in {"OUTFLOW", "INFLOW", "REFERENCE"}:
            raise ValueError(
                f"{self.stream}: invalid side {self.side!r}"
            )


def relation_exists(cur, qualified_name: str) -> bool:
    cur.execute(
        """
        SELECT to_regclass(%s)
        """,
        (qualified_name,),
    )
    return cur.fetchone()[0] is not None


def fetch_source_policies(cur) -> list[dict[str, Any]]:
    relation = "reference.federal_inflow_source_policy"

    if not relation_exists(cur, relation):
        return []

    cur.execute(
        f"""
        SELECT
            inflow_family,
            inflow_subfamily,
            accounting_measure,
            preferred_source,
            allocation_source,
            overlapping_sources,
            ledger_treatment,
            source_selection_basis,
            methodology_version,
            valid_from_fiscal_year,
            valid_through_fiscal_year
        FROM {relation}
        ORDER BY
            inflow_family,
            inflow_subfamily,
            valid_from_fiscal_year
        """
    )

    columns = [
        "inflow_family",
        "inflow_subfamily",
        "accounting_measure",
        "preferred_source",
        "allocation_source",
        "overlapping_sources",
        "ledger_treatment",
        "source_selection_basis",
        "methodology_version",
        "valid_from_fiscal_year",
        "valid_through_fiscal_year",
    ]

    return [
        dict(zip(columns, row))
        for row in cur.fetchall()
    ]


def format_policy(policy: dict[str, Any]) -> str:
    family = policy.get("inflow_family")
    subfamily = policy.get("inflow_subfamily")
    treatment = policy.get("ledger_treatment")
    method = policy.get("methodology_version")

    identity = "/".join(
        str(value)
        for value in (family, subfamily)
        if value
    )

    pieces = [identity]

    if treatment:
        pieces.append(str(treatment))

    if method:
        pieces.append(str(method))

    return " | ".join(piece for piece in pieces if piece)


def exact_policy_matches(
    policies: list[dict[str, Any]],
    *,
    family: Optional[str] = None,
    subfamily: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Match only explicit policy identity fields.

    v0.1 searched every textual value in a policy row. That allowed incidental
    words in long methodology text to create false policy associations.
    v0.2 deliberately restricts matching to inflow_family and
    inflow_subfamily.
    """

    matches: list[dict[str, Any]] = []

    family_upper = family.upper() if family is not None else None
    subfamily_upper = subfamily.upper() if subfamily is not None else None

    for policy in policies:
        policy_family = str(
            policy.get("inflow_family") or ""
        ).upper()

        policy_subfamily = str(
            policy.get("inflow_subfamily") or ""
        ).upper()

        if family_upper is not None and policy_family != family_upper:
            continue

        if (
            subfamily_upper is not None
            and policy_subfamily != subfamily_upper
        ):
            continue

        matches.append(policy)

    return matches


def exact_policy_summary(
    policies: list[dict[str, Any]],
    *,
    family: Optional[str] = None,
    subfamily: Optional[str] = None,
) -> str:
    matches = exact_policy_matches(
        policies,
        family=family,
        subfamily=subfamily,
    )

    if not matches:
        return "NONE"

    return "; ".join(
        format_policy(policy)
        for policy in matches
    )


def decimal_or_zero(value: Any) -> Decimal:
    if value is None:
        return ZERO

    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))


def fetch_simple_annual_amounts(
    cur,
    *,
    relation: str,
    year_column: str,
    amount_expression: str,
    where_sql: str = "",
    params: tuple[Any, ...] = (),
) -> dict[int, Decimal]:
    if not relation_exists(cur, relation):
        return {}

    sql = f"""
        SELECT
            {year_column} AS report_year,
            SUM({amount_expression}) AS amount_dollars
        FROM {relation}
        WHERE {year_column} BETWEEN %s AND %s
    """

    query_params: list[Any] = [
        STUDY_START_YEAR,
        STUDY_END_YEAR,
    ]

    if where_sql:
        sql += f" AND ({where_sql})"
        query_params.extend(params)

    sql += f"""
        GROUP BY {year_column}
        ORDER BY {year_column}
    """

    cur.execute(sql, tuple(query_params))

    return {
        int(year): decimal_or_zero(amount)
        for year, amount in cur.fetchall()
        if year is not None
    }


def fetch_count(cur, relation: str) -> Optional[int]:
    if not relation_exists(cur, relation):
        return None

    cur.execute(f"SELECT COUNT(*) FROM {relation}")
    return int(cur.fetchone()[0])


def audit_irs(cur, policies) -> StreamAudit:
    relation = "reporting.v_washington_revenue_summary"

    amounts = fetch_simple_annual_amounts(
        cur,
        relation=relation,
        year_column="fiscal_year",
        amount_expression="gross_collections_dollars",
    )

    return StreamAudit(
        stream="IRS_GROSS_COLLECTIONS",
        side="OUTFLOW",
        source=relation,
        years_available=set(amounts),
        annual_amounts=amounts,
        amount_measure="IRS Washington gross collections — Total",
        time_basis=(
            "IRS_FISCAL_YEAR_LABEL — FINAL ECONOMIC-INCIDENCE "
            "RECONSTRUCTION PENDING"
        ),
        geography="WASHINGTON_STATE",
        state_control_available="YES" if amounts else "NO",
        county_detail_available=(
            "NOT_REQUIRED_FOR_STATE_READINESS — separate county SOI evidence "
            "is not asserted to equal this state gross-collections control"
        ),
        source_policy="NOT_APPLICABLE — OUTFLOW CONTROL",
        overlap_status="NOT_APPLICABLE_OUTFLOW_CONTROL",
        preliminary_treatment=INCLUDE_PRELIMINARY,
        limitation=(
            "Used only as the working preliminary taxes-out control. "
            "It is not represented as the final WCFFBP economic-incidence "
            "allocation of federal receipts. Receipt-category reconstruction "
            "remains pending."
        ),
    )


def audit_ssa(cur, policies) -> StreamAudit:
    relation = "reporting.v_washington_ssa_summary"

    amounts = fetch_simple_annual_amounts(
        cur,
        relation=relation,
        year_column="report_year",
        amount_expression="annualized_benefits_dollars",
    )

    return StreamAudit(
        stream="SSA_OASDI",
        side="INFLOW",
        source=relation,
        years_available=set(amounts),
        annual_amounts=amounts,
        amount_measure="Annualized December OASDI benefit amount",
        time_basis="ANNUALIZED_DECEMBER_SNAPSHOT",
        geography="WASHINGTON_STATE_WITH_COUNTY_SOURCE_DETAIL",
        state_control_available="YES" if amounts else "NO",
        county_detail_available="YES — NOT REQUIRED FOR CURRENT STATE PHASE",
        source_policy=exact_policy_summary(
            policies,
            family="SOCIAL_SECURITY",
            subfamily="OASDI",
        ),
        overlap_status=(
            "USAspending OASDI assistance overlap controlled by "
            "ANALYSIS-116-v1"
        ),
        preliminary_treatment=INCLUDE_PRELIMINARY,
        limitation=(
            "Annual amount is constructed from December benefit amounts. "
            "No FFY/CY transformation is performed by this audit."
        ),
    )


def audit_medicare_core(cur, policies) -> StreamAudit:
    relation = "cms.medicare_core_state_year"

    if not relation_exists(cur, relation):
        return StreamAudit(
            stream="MEDICARE_CORE",
            side="INFLOW",
            source=relation,
            state_control_available="NO_RELATION",
            source_policy=(
                exact_policy_summary(
                    policies,
                    family="MEDICARE",
                    subfamily="SUPPLEMENTARY_MEDICAL_INSURANCE",
                )
            ),
            overlap_status="CERTIFIED CORE RELATION NOT FOUND",
            preliminary_treatment=WITHHOLD_UNRESOLVED,
            limitation=(
                "ETL-170 state accounting relation not found."
            ),
        )

    cur.execute(
        f"""
        SELECT
            calendar_year,
            core_medicare_sum_dollars,
            partc_months_processed,
            partc_year_completeness,
            partd_coverage_status,
            combined_period_status,
            timing_basis_status,
            ledger_status,
            methodology_version
        FROM {relation}
        WHERE calendar_year BETWEEN %s AND %s
        ORDER BY calendar_year
        """,
        (STUDY_START_YEAR, STUDY_END_YEAR),
    )

    amounts: dict[int, Decimal] = {}
    completeness: dict[int, str] = {}
    methodologies: set[str] = set()
    ledger_statuses: set[str] = set()

    for row in cur.fetchall():
        (
            year,
            amount,
            partc_months,
            partc_completeness,
            partd_status,
            combined_status,
            timing_status,
            ledger_status,
            methodology_version,
        ) = row

        year = int(year)
        amounts[year] = decimal_or_zero(amount)

        completeness[year] = (
            f"Part C months={partc_months}; "
            f"Part C={partc_completeness}; "
            f"Part D={partd_status}; "
            f"combined={combined_status}; "
            f"timing={timing_status}"
        )

        if methodology_version:
            methodologies.add(str(methodology_version))

        if ledger_status:
            ledger_statuses.add(str(ledger_status))

    methodology_text = (
        ", ".join(sorted(methodologies))
        if methodologies
        else "UNKNOWN"
    )

    ledger_text = (
        ", ".join(sorted(ledger_statuses))
        if ledger_statuses
        else "UNKNOWN"
    )

    policy_parts = [
        exact_policy_summary(
            policies,
            family="MEDICARE",
            subfamily="SUPPLEMENTARY_MEDICAL_INSURANCE",
        ),
        exact_policy_summary(
            policies,
            family="MEDICARE",
            subfamily="MEDICARE_SHARED_SAVINGS_PROGRAM",
        ),
    ]

    policy_text = "; ".join(
        part
        for part in policy_parts
        if part != "NONE"
    ) or "NONE"

    return StreamAudit(
        stream="MEDICARE_CORE",
        side="INFLOW",
        source=relation,
        years_available=set(amounts),
        annual_amounts=amounts,
        amount_measure=(
            "Certified Medicare core: Original Medicare actual FFS + "
            "Part C reconstructed + Part D reconstructed"
        ),
        time_basis="CALENDAR_YEAR / SOURCE-NATIVE CORE",
        geography="WASHINGTON_STATE",
        state_control_available="YES" if amounts else "NO",
        county_detail_available=(
            "CERTIFIED SEPARATELY — STATE CONTROL DOES NOT DEPEND ON "
            "COUNTY SUM"
        ),
        source_policy=policy_text,
        overlap_status=(
            "REPLACES LEGACY ORIGINAL-MEDICARE-ONLY REPORTING; "
            "MSSP EXCLUDED DUPLICATE; USAspending 93.774 EXCLUDED DUPLICATE"
        ),
        preliminary_treatment=INCLUDE_PRELIMINARY,
        limitation=(
            f"ETL-170 methodology={methodology_text}; "
            f"stored ledger status={ledger_text}. "
            "Use here is preliminary accounting only and does not override "
            "ETL-170's non-authorization status. 2024 Part C and Part D are "
            "partial-year and are not extrapolated."
        ),
        completeness_by_year=completeness,
    )


def audit_medicaid(cur, policies) -> StreamAudit:
    relation = "reporting.v_washington_medicaid_expenditures"

    amounts = fetch_simple_annual_amounts(
        cur,
        relation=relation,
        year_column="fiscal_year",
        amount_expression="federal_expenditure_amount",
        where_sql="is_additive_to_fiscal_balance = TRUE",
    )

    return StreamAudit(
        stream="MEDICAID",
        side="INFLOW",
        source=relation,
        years_available=set(amounts),
        annual_amounts=amounts,
        amount_measure="Federal Total Net Expenditures control",
        time_basis="FEDERAL_FISCAL_YEAR",
        geography="WASHINGTON_STATE",
        state_control_available="YES" if amounts else "NO",
        county_detail_available=(
            "PROJECT ALLOCATION EVIDENCE EXISTS — NOT REQUIRED FOR "
            "CURRENT STATE PHASE"
        ),
        source_policy="NONE",
        overlap_status=(
            "SERVICE-LEVEL ROWS EXCLUDED FROM STATE CONTROL; "
            "USAspending representations are not separately additive "
            "without reconciliation"
        ),
        preliminary_treatment=INCLUDE_PRELIMINARY,
        limitation=(
            "Federal-share state control included on its native FFY basis. "
            "No cross-period conversion is performed."
        ),
    )


def audit_chip(cur, policies) -> StreamAudit:
    relation = "reporting.v_washington_chip_expenditures"

    amounts = fetch_simple_annual_amounts(
        cur,
        relation=relation,
        year_column="fiscal_year",
        amount_expression="federal_expenditure_amount",
        where_sql="is_additive_to_fiscal_balance = TRUE",
    )

    return StreamAudit(
        stream="CHIP",
        side="INFLOW",
        source=relation,
        years_available=set(amounts),
        annual_amounts=amounts,
        amount_measure=(
            "Federal share of additive CHIP + MCHIP controls; "
            "MCHIP 20% financing adjustment excluded"
        ),
        time_basis="FEDERAL_FISCAL_YEAR",
        geography="WASHINGTON_STATE",
        state_control_available="YES" if amounts else "NO",
        county_detail_available="DEFERRED — NOT REQUIRED FOR STATE READINESS",
        source_policy="NONE",
        overlap_status=(
            "INTERNAL FINANCING ADJUSTMENT EXCLUDED; USAspending "
            "representations withheld from additive treatment"
        ),
        preliminary_treatment=INCLUDE_PRELIMINARY,
        limitation=(
            "State accounting is usable without completing county allocation."
        ),
    )


def audit_va(cur, policies) -> StreamAudit:
    relation = "va.v_washington_county_gdx_control_total"

    amounts = fetch_simple_annual_amounts(
        cur,
        relation=relation,
        year_column="fiscal_year",
        amount_expression="va_gdx_expenditure_amount",
    )

    return StreamAudit(
        stream="VA_GDX",
        side="INFLOW",
        source=relation,
        years_available=set(amounts),
        annual_amounts=amounts,
        amount_measure="VA GDX annual expenditures",
        time_basis="SOURCE FISCAL YEAR / FINAL TIMING LABEL REVIEW PENDING",
        geography="WASHINGTON_STATE_FROM_COUNTY_GDX_CONTROLS",
        state_control_available="YES" if amounts else "NO",
        county_detail_available="YES — NOT REQUIRED FOR CURRENT STATE PHASE",
        source_policy=exact_policy_summary(
            policies,
            family="VETERANS_AFFAIRS",
            subfamily="TOTAL_VA_EXPENDITURES",
        ),
        overlap_status=(
            "USAspending VA assistance/procurement retained for "
            "reconciliation and not separately additive by default"
        ),
        preliminary_treatment=INCLUDE_PRELIMINARY,
        limitation=(
            "Uses the preserved VA GDX state total constructed from county "
            "controls. ANALYSIS-149-v1 directly certifies FY2024 source "
            "selection; this audit does not silently extend that empirical "
            "FY2024 procurement reconciliation to every prior year."
        ),
    )


def audit_civilian_wages(cur, policies) -> StreamAudit:
    relation = "opm.v_omb_civilian_wage_allocation"

    amounts = fetch_simple_annual_amounts(
        cur,
        relation=relation,
        year_column="fiscal_year",
        amount_expression="allocated_wa_civilian_wage_dollars",
    )

    return StreamAudit(
        stream="FEDERAL_CIVILIAN_WAGES",
        side="INFLOW",
        source=relation,
        years_available=set(amounts),
        annual_amounts=amounts,
        amount_measure=(
            "OMB nonmilitary federal wage obligation control allocated "
            "to Washington using OPM FedScope evidence"
        ),
        time_basis="FEDERAL_FISCAL_YEAR",
        geography="WASHINGTON_STATE_ALLOCATION",
        state_control_available="YES" if amounts else "NO",
        county_detail_available=(
            "NOT REQUIRED FOR STATE READINESS — OPM allocation evidence "
            "retained separately"
        ),
        source_policy=exact_policy_summary(
            policies,
            family="FEDERAL_WAGES",
            subfamily="CIVILIAN_WAGES",
        ),
        overlap_status=(
            "DIRECT OPM/BEA WASHINGTON WAGE DOLLARS ARE DIAGNOSTIC ONLY; "
            "DO NOT ADD SEPARATELY"
        ),
        preliminary_treatment=INCLUDE_PRELIMINARY,
        limitation=(
            "Washington allocation is an OMB-controlled estimate. "
            "Public FedScope salary suppression affects allocation confidence, "
            "especially after FY2016."
        ),
    )


def audit_military_wages(cur, policies) -> StreamAudit:
    relation = "bea.v_omb_military_wage_allocation"

    amounts = fetch_simple_annual_amounts(
        cur,
        relation=relation,
        year_column="fiscal_year",
        amount_expression="allocated_wa_military_wage_dollars",
    )

    return StreamAudit(
        stream="FEDERAL_MILITARY_WAGES",
        side="INFLOW",
        source=relation,
        years_available=set(amounts),
        annual_amounts=amounts,
        amount_measure=(
            "OMB military federal wage obligation control allocated "
            "to Washington using BEA SAINC7N military-wage share"
        ),
        time_basis="FEDERAL_FISCAL_YEAR",
        geography="WASHINGTON_STATE_ALLOCATION",
        state_control_available="YES" if amounts else "NO",
        county_detail_available=(
            "NOT REQUIRED FOR STATE READINESS — BEA geographic evidence "
            "retained separately"
        ),
        source_policy=exact_policy_summary(
            policies,
            family="FEDERAL_WAGES",
            subfamily="MILITARY_WAGES",
        ),
        overlap_status=(
            "DIRECT BEA WASHINGTON MILITARY WAGE DOLLARS ARE ALLOCATION/"
            "RECONCILIATION EVIDENCE ONLY; DO NOT ADD SEPARATELY"
        ),
        preliminary_treatment=INCLUDE_PRELIMINARY,
        limitation=(
            "BEA calendar-year geographic share is applied to matching-year "
            "OMB FFY military wage obligations under ANALYSIS-157-v1."
        ),
    )


def audit_assistance(cur, policies) -> StreamAudit:
    relation = "analysis.v_statewide_assistance_by_year"

    amounts = fetch_simple_annual_amounts(
        cur,
        relation=relation,
        year_column="fiscal_year",
        amount_expression="total_obligation",
    )

    observations: Optional[int] = None

    if relation_exists(cur, relation):
        cur.execute(
            f"""
            SELECT SUM(transaction_count)
            FROM {relation}
            WHERE fiscal_year BETWEEN %s AND %s
            """,
            (STUDY_START_YEAR, STUDY_END_YEAR),
        )
        value = cur.fetchone()[0]
        if value is not None:
            observations = int(value)

    return StreamAudit(
        stream="USASPENDING_ASSISTANCE_GROSS",
        side="INFLOW",
        source=relation,
        years_available=set(amounts),
        annual_amounts=amounts,
        amount_measure="Gross Washington-attributed federal action obligations",
        time_basis="FEDERAL_FISCAL_YEAR_OBLIGATION",
        geography="WASHINGTON_ATTRIBUTION_WITH_CONFLICT_CLASSES",
        state_control_available=(
            "TRANSACTION_AGGREGATE" if amounts else "NO"
        ),
        county_detail_available=(
            "PARTIAL_WITH_WA_UNSPECIFIED_AND_GEOGRAPHY_CONFLICT — "
            "NOT REQUIRED FOR CURRENT STATE PHASE"
        ),
        source_policy="MULTIPLE PROGRAM-SPECIFIC POLICIES — SEE REGISTER",
        overlap_status=(
            "MAJOR AUTHORITATIVE-PROGRAM OVERLAP — RESIDUAL NOT YET CERTIFIED"
        ),
        preliminary_treatment=WITHHOLD_UNRESOLVED,
        limitation=(
            "Gross assistance obligations are displayed diagnostically only. "
            "They must not be added wholesale to SSA, Medicare, Medicaid, "
            "CHIP, VA, or other preferred program controls. COVID/IIJA/"
            "ordinary classification does not by itself establish additivity."
        ),
        observations=observations,
    )


def audit_procurement(cur, policies) -> StreamAudit:
    relation = "procurement.award_transaction"

    amounts = fetch_simple_annual_amounts(
        cur,
        relation=relation,
        year_column="fiscal_year",
        amount_expression="federal_action_obligation",
    )

    count = fetch_count(cur, relation)

    return StreamAudit(
        stream="USASPENDING_PROCUREMENT_GROSS",
        side="INFLOW",
        source=relation,
        years_available=set(amounts),
        annual_amounts=amounts,
        amount_measure="Gross federal action obligation",
        time_basis="FEDERAL_FISCAL_YEAR_OBLIGATION",
        geography="PLACE_OF_PERFORMANCE / TRANSACTION GEOGRAPHY",
        state_control_available=(
            "TRANSACTION_AGGREGATE" if amounts else "NO"
        ),
        county_detail_available=(
            "YES_WITH_GEOGRAPHIC_QUALIFICATIONS — NOT REQUIRED FOR "
            "CURRENT STATE PHASE"
        ),
        source_policy="MULTIPLE PROGRAM-SPECIFIC POLICIES — SEE REGISTER",
        overlap_status=(
            "PROGRAM-SPECIFIC AUTHORITATIVE-SOURCE OVERLAP; "
            "VA PROCUREMENT ALREADY SUBJECT TO ANALYSIS-149-v1"
        ),
        preliminary_treatment=WITHHOLD_UNRESOLVED,
        limitation=(
            "Gross procurement obligations are displayed diagnostically only. "
            "They are not added to the preliminary inflow subtotal until a "
            "defensibly additive residual is certified. Obligation timing "
            "also differs from expenditure timing."
        ),
        observations=count,
    )


def policy_only_stream(
    policies: list[dict[str, Any]],
    *,
    stream: str,
    family: str,
    subfamily: str,
    treatment: str,
    overlap_status: str,
    limitation: str,
) -> StreamAudit:
    matches = exact_policy_matches(
        policies,
        family=family,
        subfamily=subfamily,
    )

    years: set[int] = set()

    for policy in matches:
        start = policy.get("valid_from_fiscal_year")
        end = policy.get("valid_through_fiscal_year")

        if start is None:
            continue

        if end is None:
            end = STUDY_END_YEAR

        try:
            start_int = max(STUDY_START_YEAR, int(start))
            end_int = min(STUDY_END_YEAR, int(end))
        except (TypeError, ValueError):
            continue

        if start_int <= end_int:
            years.update(range(start_int, end_int + 1))

    return StreamAudit(
        stream=stream,
        side="INFLOW",
        source="ENCODED SOURCE POLICY / SUPPORTING EVIDENCE",
        years_available=years,
        amount_measure="POLICY_CLASSIFICATION_ONLY",
        time_basis="SOURCE_DEPENDENT",
        geography="SOURCE_DEPENDENT",
        state_control_available="NOT_ASSESSED_BY_POLICY_ONLY_ROW",
        county_detail_available="NOT REQUIRED FOR CURRENT STATE PHASE",
        source_policy=exact_policy_summary(
            policies,
            family=family,
            subfamily=subfamily,
        ),
        overlap_status=overlap_status,
        preliminary_treatment=treatment,
        limitation=limitation,
    )


def audit_mssp(policies) -> StreamAudit:
    return policy_only_stream(
        policies,
        stream="MEDICARE_MSSP",
        family="MEDICARE",
        subfamily="MEDICARE_SHARED_SAVINGS_PROGRAM",
        treatment=EXCLUDE_DUPLICATE,
        overlap_status="EXCLUDE_DUPLICATE",
        limitation=(
            "MSSP EarnSaveLoss is retained as provenance and reconciliation "
            "evidence but is not separately additive to the CMS-native "
            "Medicare accounting universe."
        ),
    )


def audit_rds(policies) -> StreamAudit:
    # RDS is intentionally represented as a methodological hold rather than
    # inferred from a possibly unrelated policy row.
        return StreamAudit(
        stream="MEDICARE_RDS",
        side="INFLOW",
        source="CERTIFIED SUPPORTING EVIDENCE / METHODOLOGY HOLD",
        amount_measure="ADDITIVE_IN_PRINCIPLE / DOLLAR INCIDENCE UNRESOLVED",
        time_basis="SOURCE_DEPENDENT",
        geography="WASHINGTON_DOLLAR_INCIDENCE_UNRESOLVED",
        state_control_available="WITHHELD",
        county_detail_available="DEFERRED",
        source_policy=exact_policy_summary(
            policies,
            family="MEDICARE",
            subfamily="SUPPLEMENTARY_MEDICAL_INSURANCE",
        ),
        overlap_status="ADDITIVE_IN_PRINCIPLE / WITHHOLD_UNRESOLVED",
        preliminary_treatment=WITHHOLD_UNRESOLVED,
        limitation=(
            "RDS expenditure exists, but Washington payment-dollar incidence "
            "has not been certified. No zero or proxy amount is inserted."
        ),
    )


def audit_mffs() -> StreamAudit:
    return StreamAudit(
        stream="MEDICARE_MFFS",
        side="INFLOW",
        source="CERTIFIED SUPPORTING EVIDENCE / METHODOLOGY HOLD",
        amount_measure="ADDITIVE_IN_PRINCIPLE / ANNUAL CASH TIMING UNRESOLVED",
        time_basis="ANNUAL_FFY_CASH_TIMING_UNRESOLVED",
        geography="WASHINGTON_STATE_DIRECT / COUNTY_DEFERRED",
        state_control_available="WITHHELD",
        county_detail_available="DEFERRED",
        source_policy="NONE",
        overlap_status="ADDITIVE_IN_PRINCIPLE / WITHHOLD_UNRESOLVED",
        preliminary_treatment=WITHHOLD_UNRESOLVED,
        limitation=(
            "MFFS represents a federal payment to Washington and is additive "
            "in principle, but annual FFY cash timing remains unresolved. "
            "No amount is inserted into the preliminary subtotal."
        ),
    )


def audit_rockefeller_reference() -> StreamAudit:
    return StreamAudit(
        stream="ROCKEFELLER_BOP",
        side="REFERENCE",
        source="ROCKEFELLER INSTITUTE BALANCE-OF-PAYMENTS EVIDENCE",
        amount_measure="EXTERNAL COMPARISON / SANITY CHECK",
        time_basis="REPORT-SPECIFIC",
        geography="WASHINGTON_STATE",
        state_control_available="REFERENCE_ONLY",
        county_detail_available="NOT_APPLICABLE",
        source_policy="NOT_APPLICABLE",
        overlap_status="NOT AN ADDITIVE WCFFBP LEDGER STREAM",
        preliminary_treatment=REFERENCE_ONLY,
        limitation=(
            "Rockefeller results are external comparison evidence. "
            "WCFFBP values are not forced to reproduce Rockefeller."
        ),
    )


def print_section(title: str) -> None:
    print()
    print("=" * 132)
    print(title)
    print("=" * 132)


def format_money(value: Optional[Decimal]) -> str:
    if value is None:
        return "—"

    return f"${value:,.2f}"


def print_matrix(streams: list[StreamAudit]) -> None:
    print_section("STATEWIDE ACCOUNTING READINESS MATRIX")

    header = (
        f"{'STREAM':<36}"
        f"{'SIDE':<11}"
        f"{'YEARS':<13}"
        f"{'COVERAGE':<11}"
        f"{'STATE CONTROL':<24}"
        f"{'PRELIMINARY TREATMENT':<24}"
    )

    print(header)
    print("-" * len(header))

    for stream in streams:
        print(
            f"{stream.stream:<36}"
            f"{stream.side:<11}"
            f"{stream.year_span():<13}"
            f"{stream.study_year_coverage():<11}"
            f"{stream.state_control_available:<24}"
            f"{stream.preliminary_treatment:<24}"
        )


def print_stream(stream: StreamAudit) -> None:
    stream.validate()

    print(f"STREAM                         : {stream.stream}")
    print(f"SIDE                           : {stream.side}")
    print(f"SOURCE                         : {stream.source}")
    print(f"YEARS AVAILABLE                : {stream.year_span()}")
    print(
        f"STUDY-YEAR COVERAGE            : "
        f"{stream.study_year_coverage()}"
    )
    print(f"AMOUNT MEASURE                 : {stream.amount_measure}")
    print(f"TIME BASIS                     : {stream.time_basis}")
    print(f"GEOGRAPHY                      : {stream.geography}")
    print(
        f"STATE CONTROL AVAILABLE        : "
        f"{stream.state_control_available}"
    )
    print(
        f"COUNTY DETAIL AVAILABLE        : "
        f"{stream.county_detail_available}"
    )
    print(f"SOURCE POLICY                  : {stream.source_policy}")
    print(f"OVERLAP STATUS                 : {stream.overlap_status}")
    print(
        f"PRELIMINARY TREATMENT          : "
        f"{stream.preliminary_treatment}"
    )

    if stream.observations is not None:
        print(
            f"OBSERVATIONS                   : "
            f"{stream.observations:,}"
        )

    if stream.annual_amounts:
        print(
            f"STUDY-PERIOD AMOUNT TOTAL      : "
            f"{format_money(sum(stream.annual_amounts.values(), ZERO))}"
        )

    print(f"LIMITATION                     : {stream.limitation}")

    if stream.completeness_by_year:
        print("COMPLETENESS DETAIL")
        for year in sorted(stream.completeness_by_year):
            print(
                f"  {year}: "
                f"{stream.completeness_by_year[year]}"
            )

    print("-" * 132)


def print_annual_stream_amounts(streams: list[StreamAudit]) -> None:
    print_section("ANNUAL SOURCE AMOUNTS — NATIVE ACCOUNTING BASIS")

    amount_streams = [
        stream
        for stream in streams
        if stream.annual_amounts
    ]

    for year in STUDY_YEARS:
        print(f"{year}")
        print("-" * 132)

        found = False

        for stream in amount_streams:
            if year not in stream.annual_amounts:
                continue

            found = True

            print(
                f"  {stream.stream:<36}"
                f"{format_money(stream.annual_amounts[year]):>24}  "
                f"{stream.preliminary_treatment}"
            )

        if not found:
            print("  No annual dollar observations found.")

        print()


def build_preliminary_rows(
    streams: list[StreamAudit],
) -> list[dict[str, Any]]:
    outflow_streams = [
        stream
        for stream in streams
        if (
            stream.side == "OUTFLOW"
            and stream.preliminary_treatment == INCLUDE_PRELIMINARY
        )
    ]

    inflow_streams = [
        stream
        for stream in streams
        if (
            stream.side == "INFLOW"
            and stream.preliminary_treatment == INCLUDE_PRELIMINARY
        )
    ]

    rows: list[dict[str, Any]] = []

    for year in STUDY_YEARS:
        outflow_values = [
            stream.annual_amounts.get(year)
            for stream in outflow_streams
        ]

        inflow_values = [
            stream.annual_amounts.get(year)
            for stream in inflow_streams
        ]

        missing_outflow = [
            stream.stream
            for stream in outflow_streams
            if year not in stream.annual_amounts
        ]

        missing_inflow = [
            stream.stream
            for stream in inflow_streams
            if year not in stream.annual_amounts
        ]

        receipts = (
            sum(
                (
                    value
                    for value in outflow_values
                    if value is not None
                ),
                ZERO,
            )
            if not missing_outflow
            else None
        )

        inflows = (
            sum(
                (
                    value
                    for value in inflow_values
                    if value is not None
                ),
                ZERO,
            )
            if not missing_inflow
            else None
        )

        difference = (
            receipts - inflows
            if receipts is not None and inflows is not None
            else None
        )

        status_parts: list[str] = []

        if missing_outflow:
            status_parts.append(
                "MISSING OUTFLOW: " + ",".join(missing_outflow)
            )

        if missing_inflow:
            status_parts.append(
                "MISSING INFLOW: " + ",".join(missing_inflow)
            )

        if year == 2024:
            status_parts.append("MEDICARE C/D PARTIAL YEAR")

        if not status_parts:
            status_parts.append("PRELIMINARY / MIXED NATIVE PERIODS")

        rows.append(
            {
                "year": year,
                "receipts": receipts,
                "inflows": inflows,
                "difference": difference,
                "status": "; ".join(status_parts),
            }
        )

    return rows


def print_preliminary_accounting_view(
    streams: list[StreamAudit],
) -> None:
    print_section(
        "WASHINGTON PRELIMINARY STATEWIDE ACCOUNTING VIEW"
    )

    print(
        "INFORMATIONAL ACCOUNTING READINESS VIEW — "
        "NOT A FINAL CERTIFIED FEDERAL FISCAL BALANCE"
    )
    print(
        "NO CROSS-PERIOD CONVERSION | NO MISSING-VALUE IMPUTATION | "
        "NO 2024 MEDICARE EXTRAPOLATION"
    )
    print(
        "UNRESOLVED USAspending RESIDUALS, RDS, AND MFFS ARE "
        "WITHHELD FROM THE INFLOW SUBTOTAL"
    )
    print(
        "SIGN CONVENTION: IRS WORKING RECEIPTS CONTROL "
        "MINUS IDENTIFIED FEDERAL INFLOWS"
    )
    print()

    rows = build_preliminary_rows(streams)

    header = (
        f"{'YEAR':<7}"
        f"{'IRS WORKING RECEIPTS':>24}"
        f"{'IDENTIFIED INFLOWS':>24}"
        f"{'PRELIM NET OUTFLOW':>24}  "
        f"STATUS"
    )

    print(header)
    print("-" * len(header))

    for row in rows:
        print(
            f"{row['year']:<7}"
            f"{format_money(row['receipts']):>24}"
            f"{format_money(row['inflows']):>24}"
            f"{format_money(row['difference']):>24}  "
            f"{row['status']}"
        )


def print_component_contributions(
    streams: list[StreamAudit],
) -> None:
    print_section(
        "PRELIMINARY INFLOW COMPONENTS BY YEAR"
    )

    included = [
        stream
        for stream in streams
        if (
            stream.side == "INFLOW"
            and stream.preliminary_treatment == INCLUDE_PRELIMINARY
        )
    ]

    header = (
        f"{'YEAR':<7}"
        + "".join(
            f"{stream.stream[:18]:>20}"
            for stream in included
        )
        + f"{'TOTAL':>20}"
    )

    print(header)
    print("-" * len(header))

    for year in STUDY_YEARS:
        values: list[Optional[Decimal]] = [
            stream.annual_amounts.get(year)
            for stream in included
        ]

        total = (
            sum(
                (value for value in values if value is not None),
                ZERO,
            )
            if all(value is not None for value in values)
            else None
        )

        line = f"{year:<7}"

        for value in values:
            if value is None:
                display = "MISSING"
            else:
                display = f"${value / Decimal('1000000000'):,.3f}B"

            line += f"{display:>20}"

        if total is None:
            total_display = "MISSING"
        else:
            total_display = (
                f"${total / Decimal('1000000000'):,.3f}B"
            )

        line += f"{total_display:>20}"

        print(line)

    print()
    print(
        "Component table shown in billions of dollars for compact review."
    )


def print_withheld_diagnostics(
    streams: list[StreamAudit],
) -> None:
    print_section(
        "WITHHELD / EXCLUDED / REFERENCE ACCOUNTING REGISTER"
    )

    for treatment in (
        WITHHOLD_UNRESOLVED,
        EXCLUDE_DUPLICATE,
        REFERENCE_ONLY,
    ):
        print(treatment)
        print("-" * 132)

        matches = [
            stream
            for stream in streams
            if stream.preliminary_treatment == treatment
        ]

        if not matches:
            print("  NONE")
            print()
            continue

        for stream in matches:
            observed_total = (
                sum(stream.annual_amounts.values(), ZERO)
                if stream.annual_amounts
                else None
            )

            if observed_total is not None:
                amount_text = (
                    f"observed gross diagnostic total="
                    f"{format_money(observed_total)}"
                )
            else:
                amount_text = "no additive dollar amount asserted"

            print(
                f"  {stream.stream:<38} {amount_text}"
            )

        print()


def print_timing_matrix(streams: list[StreamAudit]) -> None:
    print_section("ACCOUNTING-PERIOD / TIMING MATRIX")

    for stream in streams:
        print(
            f"{stream.stream:<38} "
            f"{stream.time_basis}"
        )


def print_policy_register(
    policies: list[dict[str, Any]],
) -> None:
    print_section("ENCODED FEDERAL INFLOW SOURCE POLICIES")

    if not policies:
        print("No rows found.")
        return

    for policy in policies:
        print(format_policy(policy))

        preferred = policy.get("preferred_source")
        allocation = policy.get("allocation_source")
        overlap = policy.get("overlapping_sources")
        start = policy.get("valid_from_fiscal_year")
        end = policy.get("valid_through_fiscal_year")

        if preferred is not None:
            print(f"  preferred source : {preferred}")

        if allocation is not None:
            print(f"  allocation source: {allocation}")

        if overlap is not None:
            print(f"  overlap source   : {overlap}")

        if start is not None or end is not None:
            print(
                f"  valid years      : "
                f"{start if start is not None else '?'}"
                f"-"
                f"{end if end is not None else '?'}"
            )

        print()


def print_next_priorities(streams: list[StreamAudit]) -> None:
    print_section(
        "REMAINING PRIORITIES BEFORE FINAL STATEWIDE BALANCE"
    )

    priorities = [
        (
            "1",
            "USASPENDING ADDITIVE RESIDUAL",
            "Separate authoritative-program overlap from assistance and "
            "procurement so that only defensibly distinct residual federal "
            "dollars can receive an additional plus sign.",
        ),
        (
            "2",
            "FEDERAL RECEIPTS ACCOUNTING ARCHITECTURE",
            "Decompose the IRS working control into mutually exclusive "
            "federal receipt categories and construct a transparent "
            "Washington economic-incidence model, including corporate "
            "income-tax allocation.",
        ),
        (
            "3",
            "ACCOUNTING-PERIOD PRESENTATION",
            "Preserve native source periods in the preliminary view, then "
            "decide whether a final common-period presentation can be "
            "constructed without unsupported transformations.",
        ),
        (
            "4",
            "2024 MEDICARE COMPLETENESS",
            "Resolve or explicitly retain the Part C / Part D Jan-Sep 2024 "
            "limitation. No extrapolation is authorized by this audit.",
        ),
        (
            "5",
            "KNOWN WITHHELD STREAMS",
            "Quantify RDS and MFFS only if their plausible magnitude is "
            "material enough to affect statewide interpretation.",
        ),
        (
            "6",
            "EXTERNAL RECONCILIATION",
            "Compare the independently constructed WCFFBP state series with "
            "Rockefeller Institute results as a diagnostic sanity check; "
            "do not force agreement.",
        ),
    ]

    for number, name, description in priorities:
        print(f"{number}. {name}")
        print(f"   {description}")
        print()

    counts = {
        treatment: len(
            [
                stream
                for stream in streams
                if stream.preliminary_treatment == treatment
            ]
        )
        for treatment in VALID_TREATMENTS
    }

    print("CURRENT TREATMENT COUNTS")
    print("-" * 132)
    print(
        f"INCLUDE_PRELIMINARY            : "
        f"{counts[INCLUDE_PRELIMINARY]}"
    )
    print(
        f"WITHHOLD_UNRESOLVED            : "
        f"{counts[WITHHOLD_UNRESOLVED]}"
    )
    print(
        f"EXCLUDE_DUPLICATE              : "
        f"{counts[EXCLUDE_DUPLICATE]}"
    )
    print(
        f"REFERENCE_ONLY                 : "
        f"{counts[REFERENCE_ONLY]}"
    )


def main() -> None:
    print("=" * 132)
    print(
        "WASHINGTON STATEWIDE FEDERAL FISCAL BALANCE "
        "READINESS AUDIT v0.2"
    )
    print("=" * 132)
    print(f"Certification ID               : {AUDIT_VERSION}")
    print(
        f"Study period                   : "
        f"{STUDY_START_YEAR}-{STUDY_END_YEAR}"
    )
    print("Database writes                : NONE")
    print("Final ledger authorization     : NONE")
    print("Timing conversion              : NONE")
    print("Missing-value imputation       : NONE")
    print("2024 Medicare extrapolation    : NONE")
    print(
        "Preliminary accounting view    : YES — "
        "INFORMATIONAL / NOT FINAL CERTIFICATION"
    )
    print(
        "Sign convention                : "
        "working receipts minus identified inflows"
    )

    connection = get_connection()

    try:
        with connection.cursor() as cur:
            policies = fetch_source_policies(cur)

            streams = [
                audit_irs(cur, policies),
                audit_ssa(cur, policies),
                audit_medicare_core(cur, policies),
                audit_medicaid(cur, policies),
                audit_chip(cur, policies),
                audit_va(cur, policies),
                audit_civilian_wages(cur, policies),
                audit_military_wages(cur, policies),
                audit_assistance(cur, policies),
                audit_procurement(cur, policies),
                audit_mssp(policies),
                audit_rds(policies),
                audit_mffs(),
                audit_rockefeller_reference(),
            ]

            for stream in streams:
                stream.validate()

            print_matrix(streams)

            print_section("DETAILED STREAM AUDIT")
            for stream in streams:
                print_stream(stream)

            print_annual_stream_amounts(streams)

            print_component_contributions(streams)

            print_preliminary_accounting_view(streams)

            print_withheld_diagnostics(streams)

            print_timing_matrix(streams)

            print_policy_register(policies)

            print_next_priorities(streams)

            print_section("AUDIT RESULT")
            print(
                "STATEWIDE READINESS AUDIT v0.2 COMPLETED."
            )
            print(
                "PRELIMINARY ACCOUNTING VIEW CALCULATED FROM "
                "INCLUDE_PRELIMINARY STREAMS ONLY."
            )
            print(
                "RESULT IS NOT A FINAL CERTIFIED WASHINGTON "
                "FEDERAL FISCAL BALANCE."
            )
            print(
                "NEXT ANALYTICAL PRIORITY: inspect the magnitude and "
                "composition of the withheld USAspending residual universe."
            )

    finally:
        connection.close()


if __name__ == "__main__":
    main()