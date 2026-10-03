/*
===============================================================================
ETL-174B-5N
VA ASSISTANCE / VA GDX RECONCILIATION PROFILE
===============================================================================

PURPOSE
-------
Profile the unresolved USAspending Veterans Affairs assistance universe and
the authoritative VA GDX database structure before making any additional
accounting decision.

READ ONLY.
NO DATABASE WRITES.

GOVERNING PRINCIPLE
-------------------
VA GDX is the preferred authoritative accounting source where its expenditure
scope demonstrably contains the corresponding USAspending assistance stream.

This profile does NOT assume that every CFDA 64.* program overlaps VA GDX.

No program is excluded merely because:
    - it is funded by the Department of Veterans Affairs; or
    - its assistance listing begins with 64.

The objective is to establish the evidence required for a subsequent explicit
program-level reconciliation.

BASELINE
--------
ETL-174B-5M established:

    Total certified assistance       $348,524,407,674.34
    Remaining UNCLASSIFIED_REVIEW    $130,991,929,515.49
    Unclassified VA assistance        $23,707,643,332.28

Nothing in this script changes those accounting dispositions.
===============================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5N - VA ASSISTANCE / VA GDX RECONCILIATION PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO DATABASE WRITES'
\echo ''


/* ============================================================================
   SECTION 1
   VA DATABASE OBJECT INVENTORY
   ========================================================================== */

\echo ''
\echo 'SECTION 1 - VA SCHEMA OBJECT INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        WHEN 'f' THEN 'FOREIGN TABLE'
        ELSE c.relkind::text
    END AS object_type
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname IN ('va', 'analysis', 'reporting')
  AND (
        c.relname ILIKE '%va%'
     OR c.relname ILIKE '%gdx%'
     OR c.relname ILIKE '%veteran%'
  )
ORDER BY
    n.nspname,
    c.relname;


/* ============================================================================
   SECTION 2
   VA OBJECT COLUMN INVENTORY

   This intentionally profiles the structure before attempting a semantic
   category crosswalk.
   ========================================================================== */

\echo ''
\echo 'SECTION 2 - VA / GDX OBJECT COLUMN INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema IN ('va', 'analysis', 'reporting')
  AND (
        table_name ILIKE '%va%'
     OR table_name ILIKE '%gdx%'
     OR table_name ILIKE '%veteran%'
  )
ORDER BY
    table_schema,
    table_name,
    ordinal_position;


/* ============================================================================
   SECTION 3
   CURRENT VA SOURCE POLICY
   ========================================================================== */

\echo ''
\echo 'SECTION 3 - CURRENT VA SOURCE POLICY'
\echo '----------------------------------------------------------------------------------------------------'

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
WHERE
       inflow_family ILIKE '%VETERAN%'
    OR inflow_subfamily ILIKE '%VETERAN%'
    OR preferred_source ILIKE '%VA%'
    OR allocation_source ILIKE '%VA%'
ORDER BY
    inflow_family,
    inflow_subfamily,
    methodology_version;


/* ============================================================================
   SECTION 4
   CURRENT VA PROGRAM CLASSIFICATIONS
   ========================================================================== */

\echo ''
\echo 'SECTION 4 - CURRENT CFDA 64.* PROGRAM CLASSIFICATIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
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
  AND source_program_code LIKE '64.%'
ORDER BY
    source_program_code,
    methodology_version;


/* ============================================================================
   SECTION 5
   CURRENT VA PROGRAM-POLICY MAPPINGS

   Expected to be empty at the start of ETL-174B-5N.
   ========================================================================== */

\echo ''
\echo 'SECTION 5 - CURRENT CFDA 64.* PROGRAM-POLICY MAPPINGS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.mapping_basis,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.inflow_family,
    p.inflow_subfamily,
    p.preferred_source,
    p.ledger_treatment,
    p.methodology_version AS source_policy_methodology
FROM reference.federal_inflow_program_policy_mapping AS m
JOIN reference.federal_inflow_source_policy AS p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code LIKE '64.%'
ORDER BY
    m.source_program_code,
    m.methodology_version;


/* ============================================================================
   SECTION 6
   CURRENT VA AWARD-SPECIFIC CLASSIFICATIONS
   ========================================================================== */

\echo ''
\echo 'SECTION 6 - CURRENT CFDA 64.* AWARD-SPECIFIC CLASSIFICATIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_program_code,
    source_award_identifier,
    accounting_disposition,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code LIKE '64.%'
ORDER BY
    source_program_code,
    source_award_identifier,
    methodology_version;


/* ============================================================================
   SECTION 7
   COMPLETE VA ASSISTANCE CONTROL

   This is the entire certified CFDA 64.* universe, irrespective of its
   current accounting disposition.
   ========================================================================== */

\echo ''
\echo 'SECTION 7 - COMPLETE CERTIFIED CFDA 64.* ASSISTANCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS distinct_programs,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_dollars,
    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS iija_dollars,
    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number LIKE '64.%';


/* ============================================================================
   SECTION 8
   VA ASSISTANCE BY FISCAL YEAR
   ========================================================================== */

\echo ''
\echo 'SECTION 8 - CFDA 64.* ASSISTANCE BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS distinct_programs,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_dollars,
    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number LIKE '64.%'
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


/* ============================================================================
   SECTION 9
   COMPLETE VA PROGRAM MATERIALITY PROFILE
   ========================================================================== */

\echo ''
\echo 'SECTION 9 - COMPLETE CFDA 64.* PROGRAM MATERIALITY PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT NULLIF(award_id_fain, '')) AS distinct_nonblank_fains,
    ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars,
    ROUND(
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS covid_dollars,
    ROUND(
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS iija_dollars,
    ROUND(
        SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation
                 ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars,
    COUNT(*) FILTER (
        WHERE NULLIF(award_id_fain, '') IS NULL
    ) AS blank_fain_transactions,
    ROUND(
        SUM(
            CASE
                WHEN NULLIF(award_id_fain, '') IS NULL
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS blank_fain_dollars
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number LIKE '64.%'
GROUP BY cfda_number
ORDER BY obligation_dollars DESC;


/* ============================================================================
   SECTION 10
   VA PROGRAM x FISCAL YEAR MATRIX
   ========================================================================== */

\echo ''
\echo 'SECTION 10 - CFDA 64.* PROGRAM x FISCAL YEAR MATRIX'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (WHERE action_date_fiscal_year = 2020),
        2
    ) AS fy2020,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (WHERE action_date_fiscal_year = 2021),
        2
    ) AS fy2021,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (WHERE action_date_fiscal_year = 2022),
        2
    ) AS fy2022,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (WHERE action_date_fiscal_year = 2023),
        2
    ) AS fy2023,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (WHERE action_date_fiscal_year = 2024),
        2
    ) AS fy2024,

    ROUND(SUM(federal_action_obligation), 2) AS total_2020_2024

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number LIKE '64.%'

GROUP BY cfda_number
ORDER BY total_2020_2024 DESC;


/* ============================================================================
   SECTION 11
   VA PROGRAM RECIPIENT PROFILE

   Useful for distinguishing aggregate benefit representations from grants
   to identifiable institutions, governments, or organizations.
   ========================================================================== */

\echo ''
\echo 'SECTION 11 - CFDA 64.* PROGRAM / RECIPIENT PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

WITH recipient_totals AS (
    SELECT
        cfda_number,
        cfda_title,
        recipient_name,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation) AS obligation_dollars,

        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY
                SUM(federal_action_obligation) DESC,
                recipient_name
        ) AS recipient_rank

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number LIKE '64.%'

    GROUP BY
        cfda_number,
        cfda_title,
        recipient_name
)

SELECT
    cfda_number,
    cfda_title,
    recipient_rank,
    recipient_name,
    transaction_count,
    ROUND(obligation_dollars, 2) AS obligation_dollars

FROM recipient_totals

WHERE recipient_rank <= 5

ORDER BY
    cfda_number,
    recipient_rank;


/* ============================================================================
   SECTION 12
   VA DESCRIPTION SEMANTIC PROFILE

   Descriptions are evidence only. They do NOT create an accounting decision.
   ========================================================================== */

\echo ''
\echo 'SECTION 12 - VA TRANSACTION DESCRIPTION SEMANTIC PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,

    COUNT(*) AS transaction_count,

    COUNT(*) FILTER (
        WHERE UPPER(COALESCE(transaction_description, ''))
            LIKE '%COMPENSATION%'
    ) AS compensation_hits,

    COUNT(*) FILTER (
        WHERE UPPER(COALESCE(transaction_description, ''))
            LIKE '%PENSION%'
    ) AS pension_hits,

    COUNT(*) FILTER (
        WHERE UPPER(COALESCE(transaction_description, ''))
            LIKE '%EDUCATION%'
           OR UPPER(COALESCE(transaction_description, ''))
            LIKE '%GI BILL%'
    ) AS education_hits,

    COUNT(*) FILTER (
        WHERE UPPER(COALESCE(transaction_description, ''))
            LIKE '%MEDICAL%'
           OR UPPER(COALESCE(transaction_description, ''))
            LIKE '%HEALTH%'
           OR UPPER(COALESCE(transaction_description, ''))
            LIKE '%VHA%'
    ) AS medical_hits,

    COUNT(*) FILTER (
        WHERE UPPER(COALESCE(transaction_description, ''))
            LIKE '%CEMETERY%'
           OR UPPER(COALESCE(transaction_description, ''))
            LIKE '%BURIAL%'
           OR UPPER(COALESCE(transaction_description, ''))
            LIKE '%MEMORIAL%'
    ) AS memorial_hits,

    COUNT(*) FILTER (
        WHERE UPPER(COALESCE(transaction_description, ''))
            LIKE '%CONSTRUCTION%'
    ) AS construction_hits,

    ROUND(SUM(federal_action_obligation), 2)
        AS obligation_dollars

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number LIKE '64.%'

GROUP BY cfda_number

ORDER BY obligation_dollars DESC;


/* ============================================================================
   SECTION 13
   GDX CONTROL TABLE - ANNUAL WA TOTALS

   We know this object exists from the established project contract.
   This query deliberately requests only fields already used in the project:
   fiscal year and the Washington control total.

   If its exact column contract has changed, Sections 1-2 above will tell us
   the current names without authorizing a workaround.
   ========================================================================== */

\echo ''
\echo 'SECTION 13 - VA GDX WASHINGTON CONTROL TOTAL - RAW ROWS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM va.v_washington_county_gdx_control_total
ORDER BY 1;


/* ============================================================================
   SECTION 14
   GDX CONTROL OBJECT DEFINITION

   The view definition is valuable evidence for exactly how its control total
   is constructed.
   ========================================================================== */

\echo ''
\echo 'SECTION 14 - VA GDX CONTROL VIEW DEFINITION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    pg_get_viewdef(
        'va.v_washington_county_gdx_control_total'::regclass,
        TRUE
    ) AS view_definition;


/* ============================================================================
   SECTION 15
   VA GDX RELATED TABLE SAMPLE

   Rather than guessing which underlying object contains expenditure
   categories, identify likely GDX tables/views dynamically.
   ========================================================================== */

\echo ''
\echo 'SECTION 15 - LIKELY VA GDX CATEGORY-BEARING OBJECTS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    table_schema,
    table_name,
    STRING_AGG(
        column_name,
        ', '
        ORDER BY ordinal_position
    ) AS columns
FROM information_schema.columns
WHERE table_schema = 'va'
GROUP BY
    table_schema,
    table_name
HAVING
       BOOL_OR(column_name ILIKE '%category%')
    OR BOOL_OR(column_name ILIKE '%expenditure%')
    OR BOOL_OR(column_name ILIKE '%medical%')
    OR BOOL_OR(column_name ILIKE '%compensation%')
    OR BOOL_OR(column_name ILIKE '%pension%')
    OR BOOL_OR(column_name ILIKE '%education%')
    OR BOOL_OR(column_name ILIKE '%construction%')
ORDER BY table_name;


/* ============================================================================
   SECTION 16
   VA ASSISTANCE MATERIALITY CONCENTRATION
   ========================================================================== */

\echo ''
\echo 'SECTION 16 - VA ASSISTANCE MATERIALITY CONCENTRATION'
\echo '----------------------------------------------------------------------------------------------------'

WITH program_totals AS (
    SELECT
        cfda_number,
        SUM(federal_action_obligation) AS obligation_dollars
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number LIKE '64.%'
    GROUP BY cfda_number
),

ranked AS (
    SELECT
        cfda_number,
        obligation_dollars,
        ROW_NUMBER() OVER (
            ORDER BY obligation_dollars DESC
        ) AS materiality_rank
    FROM program_totals
),

control AS (
    SELECT SUM(obligation_dollars) AS va_total
    FROM ranked
)

SELECT
    COUNT(*) AS distinct_va_programs,
    ROUND(c.va_total, 2) AS va_total,

    ROUND(
        SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 5),
        2
    ) AS top_5_programs,

    ROUND(
        100.0
        * SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 5)
        / NULLIF(c.va_total, 0),
        2
    ) AS top_5_percent,

    ROUND(
        SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 10),
        2
    ) AS top_10_programs,

    ROUND(
        100.0
        * SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 10)
        / NULLIF(c.va_total, 0),
        2
    ) AS top_10_percent,

    ROUND(
        SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 20),
        2
    ) AS top_20_programs,

    ROUND(
        100.0
        * SUM(r.obligation_dollars)
            FILTER (WHERE r.materiality_rank <= 20)
        / NULLIF(c.va_total, 0),
        2
    ) AS top_20_percent

FROM ranked AS r
CROSS JOIN control AS c
GROUP BY c.va_total;


/* ============================================================================
   SECTION 17
   HARD VA CONTROL ASSERTION

   ETL-174B-5M established the unresolved VA amount exactly.
   Since Migration 178 intentionally created no blanket VA mapping, the
   complete CFDA 64.* assistance amount should reproduce that amount unless
   a previously classified VA award exists.

   We report rather than assume that relationship first.
   ========================================================================== */

\echo ''
\echo 'SECTION 17 - VA CONTROL COMPARISON TO 5M BASELINE'
\echo '----------------------------------------------------------------------------------------------------'

WITH current_va AS (
    SELECT
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT cfda_number) AS distinct_programs,
        ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number LIKE '64.%'
)

SELECT
    transaction_count,
    distinct_programs,
    obligation_dollars AS current_cfda_64_total,
    23707643332.28::numeric AS etl174b_5m_unclassified_va_control,
    ROUND(
        obligation_dollars
        - 23707643332.28::numeric,
        2
    ) AS difference
FROM current_va;


/* ============================================================================
   SECTION 18
   COMPLETION MARKER
   ========================================================================== */

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5N PROFILE COMPLETE - VA ASSISTANCE / GDX STRUCTURE PROFILE - NO DB WRITES'
\echo '===================================================================================================='