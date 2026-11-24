\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '===================================================='
\echo 'ETL-221K - HISTORICAL ASSISTANCE GEOGRAPHY'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '===================================================='

\echo ''
\echo '1. HISTORICAL SOURCE GEOGRAPHY FIELD PROFILE'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COALESCE(
        NULLIF(BTRIM(performance_state_code), ''),
        '<NULL>'
    ) AS performance_state_code,
    COALESCE(
        NULLIF(BTRIM(performance_state_fips), ''),
        '<NULL>'
    ) AS performance_state_fips,
    COALESCE(
        NULLIF(BTRIM(reference_state_abbreviation), ''),
        '<NULL>'
    ) AS reference_state,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS obligations_dollars
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year IN (2018, 2019)
GROUP BY 1, 2, 3, 4
ORDER BY fiscal_year, transaction_rows DESC;

\echo ''
\echo '2. HISTORICAL ATTRIBUTION REASONS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    geographic_attribution_class,
    geographic_attribution_reason,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS obligations_dollars
FROM analysis.v_assistance_geographic_attribution
WHERE action_date_fiscal_year IN (2018, 2019)
GROUP BY 1, 2, 3
ORDER BY fiscal_year, transaction_rows DESC;

\echo ''
\echo '3. HISTORICAL SOURCE BATCH PROFILE'

SELECT
    action_date_fiscal_year AS fiscal_year,
    load_batch_id,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS obligations_dollars,
    COUNT(*) FILTER (
        WHERE reference_state_abbreviation = 'WA'
    ) AS wa_reference_rows,
    COUNT(*) FILTER (
        WHERE performance_state_code = 'WA'
    ) AS wa_performance_rows,
    COUNT(*) FILTER (
        WHERE BTRIM(performance_state_fips) = '53'
    ) AS wa_fips_rows,
    COUNT(*) FILTER (
        WHERE place_of_performance_id IS NULL
    ) AS missing_place_rows
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year IN (2018, 2019)
GROUP BY 1, 2
ORDER BY fiscal_year, load_batch_id;

\echo ''
\echo '4. EXISTING GEOGRAPHIC ATTRIBUTION LOGIC'

SELECT pg_get_viewdef(
    'analysis.v_assistance_geographic_attribution'::regclass,
    true
) AS view_definition;

\echo ''
\echo '5. HISTORICAL COUNTY FIELD COVERAGE'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_rows,
    COUNT(*) FILTER (
        WHERE performance_county_fips IS NOT NULL
    ) AS county_fips_present,
    COUNT(*) FILTER (
        WHERE reference_county_id IS NOT NULL
    ) AS county_registry_matched,
    COUNT(*) FILTER (
        WHERE place_of_performance_id IS NOT NULL
    ) AS place_record_present
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year IN (2018, 2019)
GROUP BY 1
ORDER BY 1;

ROLLBACK;