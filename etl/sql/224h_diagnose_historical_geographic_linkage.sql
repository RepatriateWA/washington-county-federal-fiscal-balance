
\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-224H - HISTORICAL ASSISTANCE GEOGRAPHIC LINKAGE'
\echo 'FY2018-FY2019 / READ ONLY'

BEGIN TRANSACTION READ ONLY;

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(*) FILTER (
        WHERE place_of_performance_id IS NULL
    ) AS missing_place_id,
    COUNT(*) FILTER (
        WHERE place_of_performance_id IS NOT NULL
    ) AS populated_place_id,
    COUNT(*) FILTER (
        WHERE reference_state_abbreviation = 'WA'
    ) AS normalized_wa_state,
    COUNT(*) FILTER (
        WHERE performance_state_fips = '53'
    ) AS performance_fips_53,
    COUNT(*) FILTER (
        WHERE performance_state_name ILIKE 'Washington'
    ) AS performance_name_wa,
    COUNT(*) FILTER (
        WHERE geographic_attribution_class = 'NON_WASHINGTON'
    ) AS classified_non_wa,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS total_net_obligations
FROM analysis.v_assistance_geographic_attribution
WHERE
    (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR
    (load_batch_id = 21 AND action_date_fiscal_year = 2019)
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;

ROLLBACK;

\echo 'ETL-224H COMPLETE - NO DATABASE WRITES'
