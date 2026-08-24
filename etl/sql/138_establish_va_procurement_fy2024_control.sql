-- 138_establish_va_procurement_fy2024_control.sql
--
-- Purpose:
--   Establish the canonical FY2024 Washington VA procurement population
--   before performing any PSC/NAICS classification.
--
-- Questions answered:
--   1. How is the Department of Veterans Affairs represented in the
--      procurement.agency hierarchy?
--   2. What FY2024 Washington procurement total results when VA is:
--        a. the funding agency,
--        b. the awarding agency,
--        c. either funding or awarding agency,
--        d. both funding and awarding agency?
--
-- Methodological status:
--   CONTROL / DISCOVERY ONLY.
--   No GDX overlap determination is made here.
--
-- Geographic rule:
--   Washington is determined by transaction place of performance.
--
-- Important:
--   EXISTS is used for place_of_performance so that a transaction cannot
--   be duplicated merely because of multiple geography rows.


-- =====================================================================
-- 1. Inspect all agency records that appear to be VA-related
-- =====================================================================

SELECT
    agency_id,
    agency_code,
    agency_name,
    agency_name_normalized,
    parent_agency_id,
    agency_level
FROM procurement.agency
WHERE
       upper(coalesce(agency_name, '')) LIKE '%VETERAN%'
    OR upper(coalesce(agency_name_normalized, '')) LIKE '%VETERAN%'
ORDER BY
    parent_agency_id NULLS FIRST,
    agency_id;


-- =====================================================================
-- 2. Build the VA agency hierarchy and calculate FY2024 WA controls
-- =====================================================================

WITH RECURSIVE va_roots AS (

    -- Candidate top-level Department of Veterans Affairs records.
    --
    -- We deliberately identify the root by name rather than hard-coding
    -- an agency_id before inspecting the actual database representation.

    SELECT
        agency_id,
        agency_code,
        agency_name,
        agency_name_normalized,
        parent_agency_id,
        agency_level
    FROM procurement.agency
    WHERE
        (
               upper(coalesce(agency_name, ''))
                   = 'DEPARTMENT OF VETERANS AFFAIRS'
            OR upper(coalesce(agency_name_normalized, ''))
                   = 'DEPARTMENT OF VETERANS AFFAIRS'
        )
),

va_agencies AS (

    SELECT
        agency_id,
        agency_code,
        agency_name,
        agency_name_normalized,
        parent_agency_id,
        agency_level
    FROM va_roots

    UNION ALL

    SELECT
        child.agency_id,
        child.agency_code,
        child.agency_name,
        child.agency_name_normalized,
        child.parent_agency_id,
        child.agency_level
    FROM procurement.agency child
    JOIN va_agencies parent
      ON child.parent_agency_id = parent.agency_id
),

fy2024_wa AS (

    SELECT
        t.award_transaction_id,
        t.usaspending_transaction_id,
        t.award_id,
        t.action_date,
        t.fiscal_year,
        t.federal_action_obligation,
        t.psc_code,
        t.naics_code,
        t.transaction_description,

        a.awarding_agency_id,
        a.awarding_subagency_id,
        a.funding_agency_id,
        a.funding_subagency_id,

        EXISTS (
            SELECT 1
            FROM va_agencies va
            WHERE va.agency_id = a.awarding_agency_id
               OR va.agency_id = a.awarding_subagency_id
        ) AS is_va_awarding,

        EXISTS (
            SELECT 1
            FROM va_agencies va
            WHERE va.agency_id = a.funding_agency_id
               OR va.agency_id = a.funding_subagency_id
        ) AS is_va_funding

    FROM procurement.award_transaction t

    JOIN procurement.award a
      ON a.award_id = t.award_id

    WHERE
        t.fiscal_year = 2024

        AND EXISTS (
            SELECT 1
            FROM procurement.place_of_performance pop
            WHERE pop.award_transaction_id = t.award_transaction_id
              AND upper(coalesce(pop.state_code, '')) = 'WA'
        )
),

control_categories AS (

    SELECT
        CASE
            WHEN is_va_funding AND is_va_awarding
                THEN 'VA funding AND awarding'
            WHEN is_va_funding AND NOT is_va_awarding
                THEN 'VA funding only'
            WHEN is_va_awarding AND NOT is_va_funding
                THEN 'VA awarding only'
            ELSE
                'Neither VA'
        END AS agency_relationship,

        COUNT(*) AS transaction_count,

        SUM(federal_action_obligation)
            AS federal_action_obligation

    FROM fy2024_wa

    WHERE is_va_funding OR is_va_awarding

    GROUP BY 1
)

SELECT
    agency_relationship,
    transaction_count,
    federal_action_obligation,
    ROUND(federal_action_obligation / 1000000.0, 3)
        AS obligation_millions
FROM control_categories

UNION ALL

SELECT
    'VA funding -- total',
    COUNT(*),
    SUM(federal_action_obligation),
    ROUND(SUM(federal_action_obligation) / 1000000.0, 3)
FROM fy2024_wa
WHERE is_va_funding

UNION ALL

SELECT
    'VA awarding -- total',
    COUNT(*),
    SUM(federal_action_obligation),
    ROUND(SUM(federal_action_obligation) / 1000000.0, 3)
FROM fy2024_wa
WHERE is_va_awarding

UNION ALL

SELECT
    'VA funding OR awarding -- deduplicated total',
    COUNT(*),
    SUM(federal_action_obligation),
    ROUND(SUM(federal_action_obligation) / 1000000.0, 3)
FROM fy2024_wa
WHERE is_va_funding OR is_va_awarding

ORDER BY 1;