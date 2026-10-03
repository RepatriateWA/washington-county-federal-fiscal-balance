/*
================================================================================
ETL-174B-5V-1
TRANSPORTATION SIX-PROGRAM SCOPE-DIFFERENCE PROFILE

Purpose
-------
Explain why the six Assistance Listings contain 9,823 WA FY2020-FY2024
transactions in the certified ledger, while ETL-174B-5V profiled 9,606
transactions funded by the Department of Transportation.

READ ONLY.
NO PERSISTENT DATABASE WRITES.
================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5V-1 TRANSPORTATION SIX-PROGRAM SCOPE-DIFFERENCE PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO PERSISTENT DATABASE WRITES'
\echo ''


DROP TABLE IF EXISTS pg_temp.etl174b_5v1_all;

CREATE TEMP TABLE etl174b_5v1_all AS
SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number IN (
        '20.205',
        '20.500',
        '20.507',
        '20.509',
        '20.525',
        '20.106'
  );


-- ================================================================================================
-- 1. FULL SIX-PROGRAM CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. FULL SIX-PROGRAM CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5v1_all;


-- ================================================================================================
-- 2. FUNDING-AGENCY SPLIT
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. FUNDING-AGENCY SPLIT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COALESCE(funding_agency_name, '[NULL]') AS funding_agency_name,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount
FROM etl174b_5v1_all
GROUP BY COALESCE(funding_agency_name, '[NULL]')
ORDER BY SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 3. NON-DOT DIFFERENCE CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. NON-DOT DIFFERENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,
    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount,
    ROUND(
        SUM(CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS extraordinary_amount
FROM etl174b_5v1_all
WHERE funding_agency_name IS DISTINCT FROM 'Department of Transportation';


-- ================================================================================================
-- 4. NON-DOT DIFFERENCE BY PROGRAM AND FUNDING AGENCY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. NON-DOT DIFFERENCE BY PROGRAM AND FUNDING AGENCY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    COALESCE(funding_agency_name, '[NULL]') AS funding_agency_name,
    COUNT(*) AS transaction_count,
    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount
FROM etl174b_5v1_all
WHERE funding_agency_name IS DISTINCT FROM 'Department of Transportation'
GROUP BY
    cfda_number,
    COALESCE(funding_agency_name, '[NULL]')
ORDER BY
    cfda_number,
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 5. NON-DOT DIFFERENCE BY FISCAL YEAR
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. NON-DOT DIFFERENCE BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,
    cfda_number,
    COALESCE(funding_agency_name, '[NULL]') AS funding_agency_name,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount
FROM etl174b_5v1_all
WHERE funding_agency_name IS DISTINCT FROM 'Department of Transportation'
GROUP BY
    action_date_fiscal_year,
    cfda_number,
    COALESCE(funding_agency_name, '[NULL]')
ORDER BY
    action_date_fiscal_year,
    cfda_number,
    funding_agency_name;


-- ================================================================================================
-- 6. NON-DOT RECIPIENT PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. NON-DOT RECIPIENT PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    COALESCE(funding_agency_name, '[NULL]') AS funding_agency_name,
    recipient_name,
    COUNT(*) AS transaction_count,
    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount
FROM etl174b_5v1_all
WHERE funding_agency_name IS DISTINCT FROM 'Department of Transportation'
GROUP BY
    cfda_number,
    COALESCE(funding_agency_name, '[NULL]'),
    recipient_name
ORDER BY
    cfda_number,
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 7. NON-DOT AWARD PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. NON-DOT AWARD PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, ''),
        '[NO AWARD ID]'
    ) AS award_identifier,
    COALESCE(funding_agency_name, '[NULL]') AS funding_agency_name,
    MAX(recipient_name) AS recipient_name,
    MIN(action_date_fiscal_year) AS first_fiscal_year,
    MAX(action_date_fiscal_year) AS last_fiscal_year,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount,
    ROUND(
        SUM(CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS covid_amount,
    ROUND(
        SUM(CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END)::numeric,
        2
    ) AS iija_amount
FROM etl174b_5v1_all
WHERE funding_agency_name IS DISTINCT FROM 'Department of Transportation'
GROUP BY
    cfda_number,
    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, ''),
        '[NO AWARD ID]'
    ),
    COALESCE(funding_agency_name, '[NULL]')
ORDER BY
    cfda_number,
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 8. NON-DOT DESCRIPTION PROFILE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. NON-DOT TRANSACTION DESCRIPTION PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    COALESCE(funding_agency_name, '[NULL]') AS funding_agency_name,
    COALESCE(
        NULLIF(BTRIM(transaction_description), ''),
        '[BLANK]'
    ) AS transaction_description,
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation)::numeric, 2) AS obligation_amount
FROM etl174b_5v1_all
WHERE funding_agency_name IS DISTINCT FROM 'Department of Transportation'
GROUP BY
    cfda_number,
    COALESCE(funding_agency_name, '[NULL]'),
    COALESCE(
        NULLIF(BTRIM(transaction_description), ''),
        '[BLANK]'
    )
ORDER BY
    cfda_number,
    SUM(federal_action_obligation) DESC;


-- ================================================================================================
-- 9. ACCOUNTING-DISPOSITION CHECK FOR ALL 9,823 TRANSACTIONS
--
-- This establishes whether any of the extra transactions are already governed
-- by award- or program-level accounting decisions.
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. EXISTING AWARD CLASSIFICATIONS TOUCHING SIX-PROGRAM UNIVERSE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    a.source_program_code,
    a.source_award_identifier,
    a.inflow_family,
    a.inflow_subfamily,
    a.accounting_disposition,
    a.classification_basis,
    a.methodology_version,
    a.valid_from_fiscal_year,
    a.valid_through_fiscal_year
FROM reference.federal_inflow_award_classification a
WHERE a.source_system = 'USASPENDING_ASSISTANCE'
  AND a.source_program_code IN (
        '20.205',
        '20.500',
        '20.507',
        '20.509',
        '20.525',
        '20.106'
  )
ORDER BY
    a.source_program_code,
    a.source_award_identifier,
    a.methodology_version;


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. EXISTING PROGRAM MAPPINGS TOUCHING SIX-PROGRAM UNIVERSE'
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
    p.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code IN (
        '20.205',
        '20.500',
        '20.507',
        '20.509',
        '20.525',
        '20.106'
  )
ORDER BY
    m.source_program_code,
    m.methodology_version;


-- ================================================================================================
-- 11. COMPLETION
-- ================================================================================================

DO $$
BEGIN
    RAISE NOTICE
        'ETL-174B-5V-1 COMPLETE - six-program scope difference profiled - NO PERSISTENT DB WRITES';
END
$$;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5V-1 COMPLETE'
\echo '===================================================================================================='
\echo 'NO PERSISTENT DATABASE WRITES'