/*
===============================================================================
ETL-174B-5I
MEDICARE 93.777 CONTROL-SCOPE RECONCILIATION
===============================================================================

PURPOSE
-------
Determine whether USAspending assistance program 93.777:

    State Survey and Certification of Health Care Providers and Suppliers
    (Title XVIII) Medicare

is already represented in an authoritative Medicare expenditure path used or
being considered for the Washington federal-inflow ledger.

BACKGROUND
----------
ETL-174B-5G established:

1. reporting.v_medicare_expenditures_by_state_year is an aggregation of the
   county geographic-payment layer.

2. That reporting series equals Original Medicare FFS dollars.

3. cms.medicare_core_state_year expands the Medicare accounting concept to:
       Original Medicare FFS
       + Part C
       + Part D

4. The Medicare core remains NOT_YET_AUTHORIZED for the final FFY ledger.

5. USAspending 93.777 is a state survey/certification assistance program.

GOVERNING RULE
--------------
Do not classify 93.777 as additive merely because its program description
looks administratively distinct.

Do not classify it as duplicate merely because it is Medicare-related.

Inspect the accounting scope actually represented by the Medicare controls.

READ ONLY.
NO ACCOUNTING DISPOSITION IS PERSISTED BY THIS SCRIPT.
NO DB WRITES.
===============================================================================
*/

\pset pager off


/* ============================================================================
   1. CURRENT MEDICARE REPORTING VIEW DEFINITION
   ========================================================================== */

SELECT
    pg_get_viewdef(
        'reporting.v_medicare_expenditures_by_state_year'::regclass,
        true
    ) AS medicare_state_reporting_view_definition;


/* ============================================================================
   2. COUNTY MEDICARE REPORTING VIEW DEFINITION

   The state view aggregates this layer, so inspect its actual source fields.
   ========================================================================== */

SELECT
    pg_get_viewdef(
        'reporting.v_medicare_expenditures_by_county_year'::regclass,
        true
    ) AS medicare_county_reporting_view_definition;


/* ============================================================================
   3. LIVE MEDICARE CORE STATE CONTRACT
   ========================================================================== */

SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable

FROM information_schema.columns

WHERE table_schema = 'cms'
  AND table_name = 'medicare_core_state_year'

ORDER BY ordinal_position;


/* ============================================================================
   4. LIVE MEDICARE CORE COUNTY CONTRACT
   ========================================================================== */

SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable

FROM information_schema.columns

WHERE table_schema = 'cms'
  AND table_name = 'medicare_core_county_year'

ORDER BY ordinal_position;


/* ============================================================================
   5. MEDICARE CORE STATE VALUES AND ACCOUNTING STATUS
   ========================================================================== */

SELECT
    calendar_year,

    ROUND(
        original_medicare_actual_ffs_dollars,
        2
    ) AS original_medicare_ffs_dollars,

    ROUND(
        partc_reconstructed_dollars,
        2
    ) AS partc_dollars,

    ROUND(
        partd_reconstructed_dollars,
        2
    ) AS partd_dollars,

    ROUND(
        core_medicare_sum_dollars,
        2
    ) AS core_medicare_dollars,

    partc_months_processed,
    partc_year_completeness,
    partc_reconstruction_coverage_pct,
    partc_accounting_coverage_pct,

    partd_dollar_source_field,
    partd_coverage_status,

    combined_period_status,
    timing_basis_status,
    ledger_status,
    methodology_version,
    source_file

FROM cms.medicare_core_state_year

WHERE calendar_year BETWEEN 2015 AND 2024

ORDER BY calendar_year;


/* ============================================================================
   6. SEARCH MEDICARE DATABASE OBJECTS FOR SURVEY/CERTIFICATION/ADMIN SCOPE

   Object names alone do not prove accounting scope, but they identify any
   purpose-built Medicare administrative expenditure layer that may exist.
   ========================================================================== */

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_type

FROM pg_class AS c

JOIN pg_namespace AS n
  ON n.oid = c.relnamespace

WHERE n.nspname IN (
        'cms',
        'cms_raw',
        'analysis',
        'reporting',
        'reference'
      )

  AND (
       LOWER(c.relname) LIKE '%medicare%'
    OR LOWER(c.relname) LIKE '%survey%'
    OR LOWER(c.relname) LIKE '%certif%'
  )

ORDER BY
    schema_name,
    object_name;


/* ============================================================================
   7. SEARCH LIVE DATABASE COLUMN NAMES FOR POSSIBLE ADMINISTRATIVE COMPONENTS
   ========================================================================== */

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type

FROM information_schema.columns

WHERE table_schema IN (
        'cms',
        'cms_raw',
        'analysis',
        'reporting',
        'reference'
      )

  AND (
       LOWER(table_name) LIKE '%medicare%'
    OR LOWER(column_name) LIKE '%survey%'
    OR LOWER(column_name) LIKE '%certif%'
    OR LOWER(column_name) LIKE '%admin%'
  )

ORDER BY
    table_schema,
    table_name,
    ordinal_position;


/* ============================================================================
   8. MEDICARE SOURCE POLICIES

   Inspect all durable Medicare accounting decisions already present.
   ========================================================================== */

SELECT
    federal_inflow_source_policy_id,
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

FROM reference.federal_inflow_source_policy

WHERE UPPER(COALESCE(inflow_family, '')) LIKE '%MEDICARE%'
   OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%MEDICARE%'
   OR UPPER(COALESCE(accounting_measure, '')) LIKE '%MEDICARE%'
   OR UPPER(COALESCE(preferred_source, '')) LIKE '%MEDICARE%'
   OR EXISTS (
        SELECT 1
        FROM unnest(
            COALESCE(overlapping_sources, ARRAY[]::text[])
        ) AS src
        WHERE UPPER(src) LIKE '%MEDICARE%'
   )

ORDER BY
    inflow_family,
    inflow_subfamily,
    valid_from_fiscal_year;


/* ============================================================================
   9. PROGRAM-CLASSIFICATION SEARCH FOR 93.777
   ========================================================================== */

SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_classification
WHERE source_program_code = '93.777'
   OR UPPER(COALESCE(source_program_title, ''))
        LIKE '%SURVEY%'
   OR UPPER(COALESCE(source_program_title, ''))
        LIKE '%CERTIFICATION%'
ORDER BY
    source_program_code,
    valid_from_fiscal_year;


/* ============================================================================
   10. EXACT USAspending 93.777 CONTROL
   ========================================================================== */

SELECT
    action_date_fiscal_year AS fiscal_year,

    cfda_number,

    MIN(cfda_title)
        AS cfda_title,

    COUNT(*)
        AS transaction_count,

    COUNT(DISTINCT award_id_fain)
        AS distinct_fain_count,

    COUNT(DISTINCT recipient_name)
        AS distinct_recipient_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.777'

GROUP BY
    action_date_fiscal_year,
    cfda_number

ORDER BY fiscal_year;


/* ============================================================================
   11. 93.777 AWARD-LEVEL PROFILE
   ========================================================================== */

SELECT
    action_date_fiscal_year AS fiscal_year,

    award_id_fain,

    MIN(canonical_award_description)
        AS canonical_award_description,

    MIN(recipient_name)
        AS recipient_name,

    MIN(funding_agency_name)
        AS funding_agency_name,

    COUNT(*)
        AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_obligation_dollars

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.777'

GROUP BY
    action_date_fiscal_year,
    award_id_fain

ORDER BY
    fiscal_year,
    ABS(SUM(federal_action_obligation)) DESC,
    award_id_fain;


/* ============================================================================
   12. 93.777 TRANSACTION DESCRIPTION EVIDENCE

   Preserve transaction-level text so the eventual decision can cite what the
   federal assistance actually finances.
   ========================================================================== */

SELECT
    action_date_fiscal_year AS fiscal_year,
    award_id_fain,
    federal_action_obligation,
    is_covid,
    canonical_award_description,
    transaction_description,
    recipient_name,
    funding_agency_name

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.777'

ORDER BY
    fiscal_year,
    award_id_fain,
    ABS(federal_action_obligation) DESC;


/* ============================================================================
   13. CURRENT MEDICARE REPORTING SERIES VS CORE

   Reproduce the semantic bridge one final time beside the 93.777 evidence.
   ========================================================================== */

WITH reporting AS (

    SELECT
        report_year AS calendar_year,
        SUM(actual_medicare_payments_dollars)
            AS reporting_dollars

    FROM reporting.v_medicare_expenditures_by_state_year

    WHERE report_year BETWEEN 2015 AND 2024

    GROUP BY report_year
),

core AS (

    SELECT
        calendar_year,
        original_medicare_actual_ffs_dollars,
        partc_reconstructed_dollars,
        partd_reconstructed_dollars,
        core_medicare_sum_dollars

    FROM cms.medicare_core_state_year

    WHERE calendar_year BETWEEN 2015 AND 2024
)

SELECT
    c.calendar_year,

    ROUND(
        r.reporting_dollars,
        2
    ) AS current_reporting_dollars,

    ROUND(
        c.original_medicare_actual_ffs_dollars,
        2
    ) AS original_medicare_ffs_dollars,

    ROUND(
        c.partc_reconstructed_dollars,
        2
    ) AS partc_dollars,

    ROUND(
        c.partd_reconstructed_dollars,
        2
    ) AS partd_dollars,

    ROUND(
        c.core_medicare_sum_dollars,
        2
    ) AS core_medicare_dollars,

    ROUND(
        r.reporting_dollars
        - c.original_medicare_actual_ffs_dollars,
        2
    ) AS reporting_minus_ffs

FROM core AS c

LEFT JOIN reporting AS r
  ON r.calendar_year = c.calendar_year

ORDER BY c.calendar_year;


/* ============================================================================
   14. DECISION-EVIDENCE SUMMARY

   This does NOT make the accounting decision.

   It provides compact evidence about what is and is not currently represented
   by the known Medicare control architecture.
   ========================================================================== */

SELECT
    '93.777' AS program_identifier,

    'State Survey and Certification - Title XVIII Medicare'
        AS program_under_review,

    'Original Medicare FFS + reconstructed Part C + reconstructed Part D'
        AS known_core_medicare_components,

    'NO ACCOUNTING DISPOSITION WRITTEN'
        AS disposition_status,

    'Review Sections 1-13 before persistence'
        AS required_action;


/* ============================================================================
   15. END MARKER
   ========================================================================== */

SELECT
    'ETL-174B-5I PROFILE COMPLETE - NO DB WRITES'
        AS final_status;