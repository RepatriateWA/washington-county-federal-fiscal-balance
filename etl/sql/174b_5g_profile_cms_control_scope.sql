/*
===============================================================================
ETL-174B-5G
CMS CONTROL-SCOPE RECONCILIATION
===============================================================================

PURPOSE
-------
Read-only diagnostic of the Washington Medicaid and Medicare accounting controls
used by WCFFBP.

This stage addresses two related questions:

1. What accounting measures are actually represented by the existing Medicaid
   and Medicare reporting controls?

2. Are CMS-related USAspending assistance programs such as:

       93.791  Money Follows the Person
       93.796  Medicaid Survey and Certification
       93.777  Medicare Survey and Certification
       93.775  Medicaid Fraud Control Units

   already represented in those controls, or are they economically distinct
   federal expenditures?

This stage also investigates the previously observed Medicare discrepancy
between:

    reporting.v_medicare_expenditures_by_state_year

and the earlier, broader Medicare-core construction.

READ ONLY.
NO accounting-policy changes.
NO ledger writes.
NO final inclusion/exclusion decisions.

GOVERNING PRINCIPLE
-------------------
Program administration by CMS does not itself establish overlap.

Overlap exists only if the authoritative control already contains the same
economic expenditure represented by the USAspending transaction.
===============================================================================
*/

\pset pager off


/* ============================================================================
   1. REPORTING VIEW DEFINITIONS

   PostgreSQL's catalog gives us the actual SQL definitions currently governing
   the reporting layer. This is the most important starting point.
   ========================================================================== */

SELECT
    'MEDICAID REPORTING VIEW DEFINITION' AS section,
    pg_get_viewdef(
        'reporting.v_washington_medicaid_expenditures'::regclass,
        true
    ) AS view_definition;

SELECT
    'MEDICARE REPORTING VIEW DEFINITION' AS section,
    pg_get_viewdef(
        'reporting.v_medicare_expenditures_by_state_year'::regclass,
        true
    ) AS view_definition;


/* ============================================================================
   2. COLUMN CONTRACTS

   Establish exact live semantics and data types before tracing dependencies.
   ========================================================================== */

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type

FROM information_schema.columns

WHERE
       (table_schema = 'reporting'
        AND table_name = 'v_washington_medicaid_expenditures')

    OR (table_schema = 'reporting'
        AND table_name = 'v_medicare_expenditures_by_state_year')

ORDER BY
    table_schema,
    table_name,
    ordinal_position;


/* ============================================================================
   3. DIRECT VIEW OUTPUTS

   Do not reinterpret yet. Show exactly what each reporting view currently
   contains.
   ========================================================================== */

SELECT
    'MEDICAID REPORTING VIEW OUTPUT' AS section,
    m.*

FROM reporting.v_washington_medicaid_expenditures AS m

ORDER BY 1, 2;


SELECT
    'MEDICARE REPORTING VIEW OUTPUT' AS section,
    m.*

FROM reporting.v_medicare_expenditures_by_state_year AS m

ORDER BY 1, 2;


/* ============================================================================
   4. REPORTING VIEW DEPENDENCIES

   Identify all relations directly referenced by each reporting view.
   ========================================================================== */

WITH target_views AS (

    SELECT
        c.oid AS view_oid,
        n.nspname AS view_schema,
        c.relname AS view_name

    FROM pg_class AS c

    JOIN pg_namespace AS n
      ON n.oid = c.relnamespace

    WHERE c.relkind IN ('v', 'm')
      AND n.nspname = 'reporting'
      AND c.relname IN (
          'v_washington_medicaid_expenditures',
          'v_medicare_expenditures_by_state_year'
      )
)

SELECT DISTINCT
    tv.view_schema,
    tv.view_name,
    source_ns.nspname AS source_schema,
    source.relname AS source_relation,
    source.relkind AS source_relkind

FROM target_views AS tv

JOIN pg_rewrite AS rw
  ON rw.ev_class = tv.view_oid

JOIN pg_depend AS dep
  ON dep.objid = rw.oid

JOIN pg_class AS source
  ON source.oid = dep.refobjid

JOIN pg_namespace AS source_ns
  ON source_ns.oid = source.relnamespace

WHERE source.oid <> tv.view_oid

ORDER BY
    tv.view_name,
    source_schema,
    source_relation;


/* ============================================================================
   5. CMS-RELATED DATABASE INVENTORY

   Find relations whose names indicate Medicare / Medicaid / CMS provenance.

   This is metadata discovery only.
   ========================================================================== */

SELECT
    table_schema,
    table_name,
    table_type

FROM information_schema.tables

WHERE
       UPPER(table_name) LIKE '%MEDICARE%'
    OR UPPER(table_name) LIKE '%MEDICAID%'
    OR UPPER(table_name) LIKE '%CMS%'

ORDER BY
    table_schema,
    table_name;


/* ============================================================================
   6. CMS-RELATED VIEW INVENTORY
   ========================================================================== */

SELECT
    table_schema,
    table_name

FROM information_schema.views

WHERE
       UPPER(table_name) LIKE '%MEDICARE%'
    OR UPPER(table_name) LIKE '%MEDICAID%'
    OR UPPER(table_name) LIKE '%CMS%'

ORDER BY
    table_schema,
    table_name;


/* ============================================================================
   7. CMS-RELATED COLUMN INVENTORY

   This often exposes source measures that are not obvious from relation names:
   payment, expenditure, benefit, capitation, FFP, grant, admin, etc.
   ========================================================================== */

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type

FROM information_schema.columns

WHERE
       UPPER(table_name) LIKE '%MEDICARE%'
    OR UPPER(table_name) LIKE '%MEDICAID%'
    OR UPPER(table_name) LIKE '%CMS%'
    OR UPPER(column_name) LIKE '%MEDICARE%'
    OR UPPER(column_name) LIKE '%MEDICAID%'
    OR UPPER(column_name) LIKE '%CMS%'

ORDER BY
    table_schema,
    table_name,
    ordinal_position;


/* ============================================================================
   8. MEDICARE VIEW - EXACT CURRENT ANNUAL CONTROL

   This deliberately reproduces the calculation that exposed the discrepancy.
   ========================================================================== */

SELECT
    'CURRENT MEDICARE REPORTING CONTROL' AS section,

    report_year AS fiscal_year,

    ROUND(
        SUM(actual_medicare_payments_dollars),
        2
    ) AS medicare_reporting_control_dollars

FROM reporting.v_medicare_expenditures_by_state_year

WHERE report_year BETWEEN 2015 AND 2024

GROUP BY report_year

ORDER BY report_year;

/* ============================================================================
   8B. PURPOSE-BUILT MEDICARE CORE STATE CONTROL

   This table represents the later Medicare reconstruction and explicitly
   separates Original Medicare FFS, Part C, and Part D.

   It must be compared with the older geographic-payment reporting view before
   choosing the statewide Medicare accounting control.
   ========================================================================== */

SELECT
    'MEDICARE CORE STATE CONTROL' AS section,

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
   8C. OLD REPORTING VIEW VS MEDICARE CORE

   Quantifies the discrepancy directly.
   ========================================================================== */

WITH old_reporting AS (

    SELECT
        report_year AS calendar_year,

        SUM(actual_medicare_payments_dollars)
            AS old_reporting_dollars

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
        o.old_reporting_dollars,
        2
    ) AS old_reporting_dollars,

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
        c.core_medicare_sum_dollars
        - o.old_reporting_dollars,
        2
    ) AS core_minus_old_reporting,

    ROUND(
        100.0
        * (
            c.core_medicare_sum_dollars
            - o.old_reporting_dollars
          )
        / NULLIF(o.old_reporting_dollars, 0),
        4
    ) AS difference_percent

FROM core AS c

LEFT JOIN old_reporting AS o
  ON o.calendar_year = c.calendar_year

ORDER BY c.calendar_year;

/* ============================================================================
   9. MEDICAID VIEW - EXACT CURRENT ANNUAL CONTROL
   ========================================================================== */

SELECT
    'CURRENT MEDICAID REPORTING CONTROL' AS section,

    fiscal_year,

    ROUND(
        SUM(federal_expenditure_amount)
    ) AS medicaid_reporting_control_dollars

FROM reporting.v_washington_medicaid_expenditures

WHERE fiscal_year BETWEEN 2015 AND 2024

GROUP BY fiscal_year

ORDER BY fiscal_year;


/* ============================================================================
   10. DURABLE SOURCE-POLICY CONTRACT

   These rows tell us what WCFFBP has already claimed about source hierarchy.
   ========================================================================== */

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

FROM reference.federal_inflow_source_policy

WHERE inflow_family IN (
    'MEDICARE',
    'MEDICAID',
    'CHIP',
    'HEALTH'
)

ORDER BY
    inflow_family,
    inflow_subfamily,
    methodology_version;


/* ============================================================================
   11. EXISTING PROGRAM CLASSIFICATIONS FOR THE FOUR LARGE CMS PROGRAMS
   ========================================================================== */

SELECT
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

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN (
      '93.791',
      '93.796',
      '93.777',
      '93.775'
  )

ORDER BY
    source_program_code,
    methodology_version;


/* ============================================================================
   12. FOUR-PROGRAM TRANSACTION CONTROL

   Reproduce the exact amounts being adjudicated.
   ========================================================================== */

SELECT
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    COUNT(*) AS transaction_count,

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
    ) AS covid_obligation_dollars,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024

  AND cfda_number IN (
      '93.791',
      '93.796',
      '93.777',
      '93.775'
  )

GROUP BY cfda_number

ORDER BY obligation_dollars DESC;


/* ============================================================================
   13. FOUR-PROGRAM ANNUAL PROFILE

   Needed for later year-specific reconciliation against CMS controls.
   ========================================================================== */

SELECT
    action_date_fiscal_year AS fiscal_year,
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    COUNT(*) AS transaction_count,

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

  AND cfda_number IN (
      '93.791',
      '93.796',
      '93.777',
      '93.775'
  )

GROUP BY
    action_date_fiscal_year,
    cfda_number

ORDER BY
    fiscal_year,
    obligation_dollars DESC;


/* ============================================================================
   14. FOUR-PROGRAM AWARD / RECIPIENT PROFILE

   This helps distinguish state administrative grants, demonstrations, and
   benefit-payment structures.
   ========================================================================== */

SELECT
    cfda_number,
    MIN(cfda_title) AS cfda_title,

    award_id_fain,
    recipient_name,

    MIN(assistance_type_code)
        AS assistance_type_code,

    MIN(assistance_type_description)
        AS assistance_type_description,

    MIN(canonical_award_description)
        AS award_description,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024

  AND cfda_number IN (
      '93.791',
      '93.796',
      '93.777',
      '93.775'
  )

GROUP BY
    cfda_number,
    award_id_fain,
    recipient_name

ORDER BY
    cfda_number,
    obligation_dollars DESC;


/* ============================================================================
   15. MEDICARE COMPONENT SEARCH

   Search the catalog for likely Medicare component fields.

   This is intentionally broad because we want to rediscover the earlier
   Medicare-core construction from the live database rather than rely on
   memory.
   ========================================================================== */

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type

FROM information_schema.columns

WHERE
       UPPER(column_name) LIKE '%PART_A%'
    OR UPPER(column_name) LIKE '%PART_B%'
    OR UPPER(column_name) LIKE '%PART_C%'
    OR UPPER(column_name) LIKE '%PART_D%'
    OR UPPER(column_name) LIKE '%ORIGINAL_MEDICARE%'
    OR UPPER(column_name) LIKE '%MEDICARE_ADVANTAGE%'
    OR UPPER(column_name) LIKE '%PRIVATE_HEALTH%'
    OR UPPER(column_name) LIKE '%PRESCRIPTION_DRUG%'
    OR UPPER(column_name) LIKE '%FFS%'
    OR UPPER(column_name) LIKE '%CAPITATION%'
    OR UPPER(column_name) LIKE '%BENEFIT_PAYMENT%'

ORDER BY
    table_schema,
    table_name,
    ordinal_position;


/* ============================================================================
   16. CMS ACCOUNTING-SCOPE KEYWORD SEARCH IN COLUMN NAMES

   Useful for Medicaid FFP/admin/grant distinctions.
   ========================================================================== */

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type

FROM information_schema.columns

WHERE
       UPPER(column_name) LIKE '%EXPENDITURE%'
    OR UPPER(column_name) LIKE '%PAYMENT%'
    OR UPPER(column_name) LIKE '%BENEFIT%'
    OR UPPER(column_name) LIKE '%ADMIN%'
    OR UPPER(column_name) LIKE '%GRANT%'
    OR UPPER(column_name) LIKE '%FEDERAL_SHARE%'
    OR UPPER(column_name) LIKE '%FFP%'
    OR UPPER(column_name) LIKE '%MEDICAL_ASSISTANCE%'

AND (
       UPPER(table_name) LIKE '%MEDICARE%'
    OR UPPER(table_name) LIKE '%MEDICAID%'
    OR UPPER(table_name) LIKE '%CMS%'
)

ORDER BY
    table_schema,
    table_name,
    ordinal_position;


/* ============================================================================
   17. END MARKER
   ========================================================================== */

SELECT
    'ETL-174B-5G PROFILE COMPLETE - NO DB WRITES' AS final_status;