/*
================================================================================
ETL-174B-5V
FEDERAL TRANSPORTATION ASSISTANCE FAMILY ACCOUNTING PROFILE
================================================================================

Purpose
-------
Determine whether major unresolved Washington Department of Transportation
assistance programs can be governed by a coherent transportation-assistance
source/accounting policy.

READ ONLY.
NO PERSISTENT DATABASE WRITES.
NO ACCOUNTING CLASSIFICATIONS ARE CREATED BY THIS SCRIPT.

Primary questions
-----------------
1. What is the complete unresolved DOT assistance universe?
2. How concentrated is that universe in the major programs?
3. Do the major programs represent direct federal transportation investment
   sufficiently consistently to support a common family policy?
4. Are any programs likely to overlap another authoritative WCFFBP ledger
   source?
5. Are COVID and IIJA amounts provenance dimensions rather than distinct
   accounting dispositions?
6. Can one source policy govern multiple Assistance Listings while preserving
   program-level mappings and exceptions?

Deep-profile programs
---------------------
20.205  Highway Planning and Construction
20.507  Federal Transit Formula Grants
20.500  Federal Transit Capital Investment Grants
20.106  Airport Improvement Program / COVID / IIJA
20.525  State of Good Repair Grants Program
20.509  Formula Grants for Rural Areas and Tribal Transit Program

Important
---------
Funding agency is contextual evidence only. Assistance Listing identity remains
the program-classification identity.

================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5V FEDERAL TRANSPORTATION ASSISTANCE FAMILY ACCOUNTING PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO PERSISTENT DATABASE WRITES'
\echo ''


-- ================================================================================================
-- 1. RECONSTRUCT CURRENT EFFECTIVE ACCOUNTING BRIDGE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5v_base;

CREATE TEMP TABLE etl174b_5v_base AS
SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024;


DROP TABLE IF EXISTS pg_temp.etl174b_5v_award_resolution;

CREATE TEMP TABLE etl174b_5v_award_resolution AS
SELECT DISTINCT ON (b.assistance_transaction_id)
    b.assistance_transaction_id,
    a.accounting_disposition,
    a.methodology_version
FROM etl174b_5v_base b
JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = b.cfda_number
 AND a.source_award_identifier =
        COALESCE(NULLIF(b.award_id_fain, ''), NULLIF(b.award_id_uri, ''))
 AND (
        a.valid_from_fiscal_year IS NULL
        OR b.action_date_fiscal_year >= a.valid_from_fiscal_year
     )
 AND (
        a.valid_through_fiscal_year IS NULL
        OR b.action_date_fiscal_year <= a.valid_through_fiscal_year
     )
ORDER BY
    b.assistance_transaction_id,
    a.updated_at DESC,
    a.federal_inflow_award_classification_id DESC;


DROP TABLE IF EXISTS pg_temp.etl174b_5v_program_resolution;

CREATE TEMP TABLE etl174b_5v_program_resolution AS
SELECT DISTINCT ON (b.assistance_transaction_id)
    b.assistance_transaction_id,
    m.resolved_accounting_disposition AS accounting_disposition,
    m.methodology_version
FROM etl174b_5v_base b
JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND m.source_program_code = b.cfda_number
 AND (
        m.valid_from_fiscal_year IS NULL
        OR b.action_date_fiscal_year >= m.valid_from_fiscal_year
     )
 AND (
        m.valid_through_fiscal_year IS NULL
        OR b.action_date_fiscal_year <= m.valid_through_fiscal_year
     )
ORDER BY
    b.assistance_transaction_id,
    m.updated_at DESC,
    m.federal_inflow_program_policy_mapping_id DESC;


DROP TABLE IF EXISTS pg_temp.etl174b_5v_bridge;

CREATE TEMP TABLE etl174b_5v_bridge AS
SELECT
    b.*,
    CASE
        WHEN ar.assistance_transaction_id IS NOT NULL
            THEN ar.accounting_disposition
        WHEN pr.assistance_transaction_id IS NOT NULL
            THEN pr.accounting_disposition
        ELSE 'UNCLASSIFIED_REVIEW'
    END AS effective_accounting_disposition,
    CASE
        WHEN ar.assistance_transaction_id IS NOT NULL THEN 'AWARD'
        WHEN pr.assistance_transaction_id IS NOT NULL THEN 'PROGRAM'
        ELSE 'UNCLASSIFIED'
    END AS resolution_level
FROM etl174b_5v_base b
LEFT JOIN etl174b_5v_award_resolution ar
  ON ar.assistance_transaction_id = b.assistance_transaction_id
LEFT JOIN etl174b_5v_program_resolution pr
  ON pr.assistance_transaction_id = b.assistance_transaction_id;


-- ================================================================================================
-- 2. CURRENT 5U RESIDUAL CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. CURRENT 5U UNCLASSIFIED CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS residual_amount
FROM etl174b_5v_bridge
WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW';


DO $$
DECLARE
    v_total numeric;
BEGIN
    SELECT COALESCE(SUM(federal_action_obligation), 0)
    INTO v_total
    FROM etl174b_5v_bridge
    WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW';

    IF ABS(v_total - 82843039059.13::numeric) > 0.01 THEN
        RAISE EXCEPTION
            '5V RESIDUAL CONTROL FAILED: expected 82843039059.13; found %',
            v_total;
    END IF;

    RAISE NOTICE
        '5V 5U-RESIDUAL CONTROL PASS: %',
        v_total;
END
$$;


-- ================================================================================================
-- 3. COMPLETE UNRESOLVED DOT POPULATION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5v_dot;

CREATE TEMP TABLE etl174b_5v_dot AS
SELECT *
FROM etl174b_5v_bridge
WHERE effective_accounting_disposition = 'UNCLASSIFIED_REVIEW'
  AND funding_agency_name = 'Department of Transportation';


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. COMPLETE UNRESOLVED DOT POPULATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5v_dot;


-- ================================================================================================
-- 4. COMPLETE DOT PROGRAM INVENTORY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. COMPLETE UNRESOLVED DOT PROGRAM INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5v_dot
GROUP BY cfda_number
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 5. DEEP-PROFILE POPULATION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.etl174b_5v_major;

CREATE TEMP TABLE etl174b_5v_major AS
SELECT *
FROM etl174b_5v_dot
WHERE cfda_number IN (
    '20.205',
    '20.507',
    '20.500',
    '20.106',
    '20.525',
    '20.509'
);


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. MAJOR TRANSPORTATION PROGRAM CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5v_major;


-- ================================================================================================
-- 6. MAJOR PROGRAM ANNUAL PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. MAJOR PROGRAM x FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5v_major
GROUP BY action_date_fiscal_year, cfda_number
ORDER BY action_date_fiscal_year, cfda_number;


-- ================================================================================================
-- 7. TRANSACTION SIGN PROFILE BY PROGRAM
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. MAJOR PROGRAM TRANSACTION SIGN PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,

    COUNT(*) FILTER (
        WHERE federal_action_obligation > 0
    ) AS positive_transactions,

    ROUND(
        COALESCE(
            SUM(federal_action_obligation)
                FILTER (WHERE federal_action_obligation > 0),
            0
        )::numeric,
        2
    ) AS positive_obligations,

    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions,

    ROUND(
        COALESCE(
            SUM(federal_action_obligation)
                FILTER (WHERE federal_action_obligation < 0),
            0
        )::numeric,
        2
    ) AS negative_obligations,

    COUNT(*) FILTER (
        WHERE federal_action_obligation = 0
    ) AS zero_transactions,

    ROUND(SUM(federal_action_obligation)::numeric, 2) AS net_obligations

FROM etl174b_5v_major
GROUP BY cfda_number
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 8. FUNDING PROVENANCE BY PROGRAM
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. MAJOR PROGRAM FUNDING PROVENANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount
FROM etl174b_5v_major
GROUP BY
    cfda_number,
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary
ORDER BY
    cfda_number,
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 9. RECIPIENT CONCENTRATION BY PROGRAM
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. TOP RECIPIENTS BY MAJOR PROGRAM'
\echo '----------------------------------------------------------------------------------------------------'

WITH recipient_totals AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        recipient_name,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT COALESCE(award_id_fain, award_id_uri)) AS award_count,
        SUM(federal_action_obligation) AS obligation_amount
    FROM etl174b_5v_major
    GROUP BY cfda_number, recipient_name
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY obligation_amount DESC
        ) AS recipient_rank
    FROM recipient_totals
)
SELECT
    cfda_number,
    cfda_title,
    recipient_rank,
    recipient_name,
    transaction_count,
    award_count,
    ROUND(obligation_amount::numeric, 2) AS obligation_amount
FROM ranked
WHERE recipient_rank <= 15
ORDER BY cfda_number, recipient_rank;


-- ================================================================================================
-- 10. AWARD CONCENTRATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. TOP AWARDS BY MAJOR PROGRAM'
\echo '----------------------------------------------------------------------------------------------------'

WITH award_totals AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        COALESCE(NULLIF(award_id_fain, ''), NULLIF(award_id_uri, '')) AS award_identifier,
        MAX(recipient_name) AS recipient_name,
        MIN(action_date_fiscal_year) AS first_fiscal_year,
        MAX(action_date_fiscal_year) AS last_fiscal_year,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation) AS obligation_amount
    FROM etl174b_5v_major
    GROUP BY
        cfda_number,
        COALESCE(NULLIF(award_id_fain, ''), NULLIF(award_id_uri, ''))
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY obligation_amount DESC
        ) AS award_rank
    FROM award_totals
)
SELECT
    cfda_number,
    cfda_title,
    award_rank,
    award_identifier,
    recipient_name,
    first_fiscal_year,
    last_fiscal_year,
    transaction_count,
    ROUND(obligation_amount::numeric, 2) AS obligation_amount
FROM ranked
WHERE award_rank <= 15
ORDER BY cfda_number, award_rank;


-- ================================================================================================
-- 11. TRANSACTION DESCRIPTION PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. MAJOR PROGRAM TRANSACTION DESCRIPTION PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

WITH description_totals AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        COALESCE(NULLIF(BTRIM(transaction_description), ''), '[BLANK]') AS transaction_description,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation) AS obligation_amount,
        SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation
                 ELSE 0
            END
        ) AS covid_amount,
        SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation
                 ELSE 0
            END
        ) AS iija_amount
    FROM etl174b_5v_major
    GROUP BY
        cfda_number,
        COALESCE(NULLIF(BTRIM(transaction_description), ''), '[BLANK]')
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY obligation_amount DESC
        ) AS description_rank
    FROM description_totals
)
SELECT
    cfda_number,
    cfda_title,
    description_rank,
    transaction_description,
    transaction_count,
    ROUND(obligation_amount::numeric, 2) AS obligation_amount,
    ROUND(covid_amount::numeric, 2) AS covid_amount,
    ROUND(iija_amount::numeric, 2) AS iija_amount
FROM ranked
WHERE description_rank <= 30
ORDER BY cfda_number, description_rank;


-- ================================================================================================
-- 12. EXISTING PROGRAM CLASSIFICATIONS FOR DOT PROGRAMS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. EXISTING DOT PROGRAM CLASSIFICATIONS'
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
  AND source_program_code IN (
        SELECT DISTINCT cfda_number
        FROM etl174b_5v_dot
  )
ORDER BY source_program_code, methodology_version;


-- ================================================================================================
-- 13. EXISTING PROGRAM-POLICY MAPPINGS FOR DOT PROGRAMS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. EXISTING DOT PROGRAM-POLICY MAPPINGS'
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
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment,
    p.methodology_version AS source_policy_methodology_version
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code IN (
        SELECT DISTINCT cfda_number
        FROM etl174b_5v_dot
  )
ORDER BY m.source_program_code, m.methodology_version;


-- ================================================================================================
-- 14. POSSIBLY RELATED EXISTING SOURCE POLICIES
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. POSSIBLY RELATED EXISTING TRANSPORTATION SOURCE POLICIES'
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
       UPPER(COALESCE(inflow_family, '')) LIKE '%TRANSPORT%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%TRANSPORT%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%HIGHWAY%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%HIGHWAY%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%TRANSIT%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%TRANSIT%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%AIRPORT%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%AIRPORT%'
ORDER BY federal_inflow_source_policy_id;


-- ================================================================================================
-- 15. POSSIBLE LEDGER-OVERLAP KEYWORD DIAGNOSTIC
--
-- Diagnostic only. Keywords do not create classifications.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. POSSIBLE OVERLAP / ACCOUNTING KEYWORD DIAGNOSTIC'
\echo '----------------------------------------------------------------------------------------------------'

WITH tagged AS (
    SELECT
        *,
        CASE
            WHEN UPPER(COALESCE(transaction_description, '')) ~
                 '(REIMBURS|REIMBURSEMENT)'
                THEN 'REIMBURSEMENT_TEXT'

            WHEN UPPER(COALESCE(transaction_description, '')) ~
                 '(OPERATING|OPERATIONS)'
                THEN 'OPERATING_TEXT'

            WHEN UPPER(COALESCE(transaction_description, '')) ~
                 '(CAPITAL|CONSTRUCTION|BUILD|IMPROVEMENT|REHABILITATION)'
                THEN 'CAPITAL_CONSTRUCTION_TEXT'

            WHEN UPPER(COALESCE(transaction_description, '')) ~
                 '(PLANNING|PLAN)'
                THEN 'PLANNING_TEXT'

            WHEN UPPER(COALESCE(transaction_description, '')) ~
                 '(COVID|CORONAVIRUS|CARES|CRRSA|ARP)'
                THEN 'COVID_TEXT'

            WHEN UPPER(COALESCE(transaction_description, '')) ~
                 '(INFRASTRUCTURE|IIJA|BIPARTISAN INFRASTRUCTURE)'
                THEN 'INFRASTRUCTURE_TEXT'

            ELSE 'OTHER_OR_UNSPECIFIED_TEXT'
        END AS semantic_bucket
    FROM etl174b_5v_major
)
SELECT
    cfda_number,
    semantic_bucket,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount
FROM tagged
GROUP BY cfda_number, semantic_bucket
ORDER BY cfda_number, SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 16. FAMILY MATERIALITY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. TRANSPORTATION FAMILY MATERIALITY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS major_six_amount,

    ROUND(
        100.0 * SUM(federal_action_obligation)
        / 82843039059.13::numeric,
        4
    ) AS major_six_pct_of_5u_residual,

    ROUND(
        (
            82843039059.13::numeric
            - SUM(federal_action_obligation)
        ),
        2
    ) AS hypothetical_residual_if_major_six_fully_resolved

FROM etl174b_5v_major;


-- ================================================================================================
-- 17. MAJOR-SIX SHARE OF COMPLETE DOT RESIDUAL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. MAJOR-SIX SHARE OF COMPLETE DOT RESIDUAL'
\echo '----------------------------------------------------------------------------------------------------'

WITH totals AS (
    SELECT
        (SELECT SUM(federal_action_obligation)
         FROM etl174b_5v_major) AS major_amount,

        (SELECT SUM(federal_action_obligation)
         FROM etl174b_5v_dot) AS dot_amount
)
SELECT
    ROUND(major_amount::numeric, 2) AS major_six_amount,
    ROUND(dot_amount::numeric, 2) AS complete_dot_amount,
    ROUND(
        100.0 * major_amount / NULLIF(dot_amount, 0),
        4
    ) AS major_six_pct_of_dot
FROM totals;


-- ================================================================================================
-- 18. COMPLETION MARKER
-- ================================================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-174B-5V PROFILE COMPLETE - TRANSPORTATION ASSISTANCE FAMILY REVIEW - NO PERSISTENT DB WRITES';
END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5V COMPLETE'
\echo '===================================================================================================='
\echo 'NO PERSISTENT DATABASE WRITES'